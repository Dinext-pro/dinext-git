"""Manage GitLab webhook desired state from Dinext."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from dinext_git.services.gitlab.client import GitLabClient
from dinext_git.services.gitlab.store import get_instance, get_mapping

WEBHOOK_RECEIVE_PATH = "/api/method/dinext_git.api.gitlab_webhooks.receive"

WEBHOOK_PROBLEM_STATUSES = frozenset({"missing", "drifted", "failed"})


def normalize_public_webhook_url(url: str) -> str:
	"""Prefer HTTPS for public callback URLs so GitLab does not depend on HTTP redirects."""
	url = (url or "").strip()
	if url.startswith("http://") and "localhost" not in url and "127.0.0.1" not in url:
		return f"https://{url[len('http://'):]}"
	return url


def resolve_webhook_callback_url(mapping: dict[str, Any] | None = None) -> str:
	callback_url = (mapping or {}).get("webhook_callback_url")
	if callback_url:
		return normalize_public_webhook_url(callback_url)
	return normalize_public_webhook_url(f"{frappe.utils.get_url()}{WEBHOOK_RECEIVE_PATH}")


def desired_hook_payload(mapping: dict[str, Any], instance: dict[str, Any]) -> dict[str, Any]:
	endpoint = resolve_webhook_callback_url(mapping)
	secret = instance["webhook_secret"]
	return {
		"url": endpoint,
		"token": secret,
		"push_events": True,
		"merge_requests_events": True,
		"pipeline_events": True,
		"tag_push_events": True,
		"releases_events": True,
		"enable_ssl_verification": bool(instance.get("verify_ssl", 1)),
	}


def sync_mapping_webhook(mapping_name: str, *, force: bool = False) -> dict[str, Any]:
	mapping = get_mapping(mapping_name)
	instance = get_instance(mapping["gitlab_instance"])
	client = GitLabClient(instance["name"])
	project_id = mapping.get("gitlab_project_id")
	if not project_id:
		project = client.get_project(project_path=mapping["gitlab_project_path"])
		project_id = project["id"]
		frappe.db.set_value("GitLab Project Mapping", mapping_name, "gitlab_project_id", project_id)

	payload = desired_hook_payload(mapping, instance)
	remote_hook_id = mapping.get("remote_webhook_id")

	if remote_hook_id and not force:
		hook = client.update_project_hook(project_id, remote_hook_id, payload)
	else:
		hook = client.create_project_hook(project_id, payload)

	frappe.db.set_value(
		"GitLab Project Mapping",
		mapping_name,
		{
			"remote_webhook_id": hook["id"],
			"webhook_status": "active",
			"webhook_last_verified_on": frappe.utils.now_datetime(),
		},
	)

	return {"project_id": project_id, "hook": hook, "payload": payload}


def verify_mapping_webhook(mapping_name: str) -> dict[str, Any]:
	mapping = get_mapping(mapping_name)
	instance = get_instance(mapping["gitlab_instance"])
	client = GitLabClient(instance["name"])
	project_id = mapping.get("gitlab_project_id")
	hook_id = mapping.get("remote_webhook_id")

	if not project_id or not hook_id:
		frappe.db.set_value("GitLab Project Mapping", mapping_name, "webhook_status", "missing")
		return {"status": "missing", "reason": _("GitLab webhook has not been provisioned yet.")}

	try:
		hook = client.get_project_hook(project_id, hook_id)
	except Exception as exc:
		frappe.db.set_value("GitLab Project Mapping", mapping_name, "webhook_status", "missing")
		return {"status": "missing", "reason": str(exc)}

	desired = desired_hook_payload(mapping, instance)
	drifted = False
	if hook.get("url") != desired["url"]:
		drifted = True
	if (
		not hook.get("push_events")
		or not hook.get("merge_requests_events")
		or not hook.get("pipeline_events")
		or not hook.get("tag_push_events")
		or not hook.get("releases_events")
	):
		drifted = True

	status = "drifted" if drifted else "active"
	frappe.db.set_value(
		"GitLab Project Mapping",
		mapping_name,
		{
			"webhook_status": status,
			"webhook_last_verified_on": frappe.utils.now_datetime(),
		},
	)
	return {"status": status, "hook": hook, "desired": desired}


def get_enabled_mappings_for_instance(instance_name: str) -> list[dict[str, Any]]:
	return frappe.get_all(
		"GitLab Project Mapping",
		filters={"gitlab_instance": instance_name, "enabled": 1},
		fields=["name", "gitlab_project_path", "webhook_status"],
		order_by="name asc",
	)


def verify_and_sync_instance_webhooks(instance_name: str) -> dict[str, Any]:
	"""Verify all enabled mappings for an instance and sync only problematic webhooks."""
	if not frappe.db.exists("GitLab Instance", instance_name):
		frappe.throw(_("GitLab Instance {0} was not found.").format(instance_name))

	mappings = get_enabled_mappings_for_instance(instance_name)
	results: list[dict[str, Any]] = []
	synced_count = 0
	active_count = 0
	still_problematic_count = 0
	error_count = 0

	for row in mappings:
		mapping_name = row["name"]
		entry: dict[str, Any] = {
			"mapping": mapping_name,
			"gitlab_project_path": row.get("gitlab_project_path"),
		}
		try:
			verify_result = verify_mapping_webhook(mapping_name)
			status = verify_result.get("status")
			entry["status"] = status

			if status in WEBHOOK_PROBLEM_STATUSES:
				sync_mapping_webhook(mapping_name)
				entry["synced"] = True
				synced_count += 1
				verify_result = verify_mapping_webhook(mapping_name)
				status = verify_result.get("status")
				entry["status"] = status

			if status == "active":
				active_count += 1
			elif status in WEBHOOK_PROBLEM_STATUSES:
				still_problematic_count += 1
		except Exception as exc:
			entry["error"] = str(exc)
			error_count += 1

		results.append(entry)

	return {
		"instance": instance_name,
		"checked_count": len(mappings),
		"synced_count": synced_count,
		"active_count": active_count,
		"still_problematic_count": still_problematic_count,
		"error_count": error_count,
		"results": results,
	}
