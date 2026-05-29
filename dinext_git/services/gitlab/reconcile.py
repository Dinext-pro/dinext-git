"""Scheduled reconciliation against GitLab REST API."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_git.services.gitlab.client import GitLabClient
from dinext_git.services.gitlab.normalizer import (
	log_event,
	normalize_merge_request_event,
	normalize_pipeline_event,
)
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.store import get_mapping
from dinext_git.services.gitlab.webhook_admin import verify_mapping_webhook


def _touch_cursor(mapping_name: str, artifact_type: str, *, status: str, error: str | None = None) -> None:
	cursor_name = frappe.db.get_value(
		"Reconciliation Cursor",
		{"project_mapping": mapping_name, "artifact_type": artifact_type},
		"name",
	)
	values = {
		"status": status,
		"last_error": error,
		"last_finished_on": frappe.utils.now_datetime() if status != "running" else None,
		"last_started_on": frappe.utils.now_datetime() if status == "running" else None,
	}
	if cursor_name:
		frappe.db.set_value("Reconciliation Cursor", cursor_name, values)
	else:
		frappe.get_doc(
			{
				"doctype": "Reconciliation Cursor",
				"project_mapping": mapping_name,
				"artifact_type": artifact_type,
				"status": status,
				"last_error": error,
				"enabled": 1,
				"last_started_on": values["last_started_on"],
				"last_finished_on": values["last_finished_on"],
			}
		).insert(ignore_permissions=True)


def reconcile_mapping(mapping_name: str) -> dict[str, Any]:
	mapping = get_mapping(mapping_name)
	client = GitLabClient(mapping["gitlab_instance"])
	project_id = mapping["gitlab_project_id"] or client.get_project(project_path=mapping["gitlab_project_path"])["id"]

	results: dict[str, Any] = {"merge_requests": 0, "pipelines": 0}

	_touch_cursor(mapping_name, "merge_request", status="running")
	try:
		for mr in client.list_merge_requests(project_id, updated_after=mapping.get("last_reconciled_mr_at")):
			payload = {
				"object_attributes": {
					"id": mr["id"],
					"iid": mr["iid"],
					"title": mr["title"],
					"description": mr.get("description"),
					"state": mr["state"],
					"url": mr["web_url"],
					"source_branch": mr["source_branch"],
					"target_branch": mr["target_branch"],
				},
				"user": {"name": (mr.get("author") or {}).get("name")},
			}
			log_event(
				instance=mapping["gitlab_instance"],
				mapping=mapping_name,
				event_type="reconcile_merge_request",
				delivery_id=str(mr["id"]),
				payload=payload,
				status="processed",
			)
			normalize_merge_request_event(mapping["gitlab_instance"], mapping_name, payload)
			results["merge_requests"] += 1
		frappe.db.set_value("GitLab Project Mapping", mapping_name, "last_reconciled_mr_at", frappe.utils.now_datetime())
		_touch_cursor(mapping_name, "merge_request", status="idle")
	except Exception as exc:
		_touch_cursor(mapping_name, "merge_request", status="failed", error=str(exc))
		raise

	_touch_cursor(mapping_name, "pipeline", status="running")
	try:
		for pipeline in client.list_pipelines(project_id, updated_after=mapping.get("last_reconciled_pipeline_at")):
			details = client.get_pipeline(project_id, pipeline["id"])
			jobs = client.get_pipeline_jobs(project_id, pipeline["id"])
			payload = {
				"object_attributes": {
					"id": details["id"],
					"iid": details["iid"],
					"status": details["status"],
					"ref": details["ref"],
					"sha": details["sha"],
					"url": details["web_url"],
				},
				"builds": jobs,
				"commit": {"message": ""},
			}
			log_event(
				instance=mapping["gitlab_instance"],
				mapping=mapping_name,
				event_type="reconcile_pipeline",
				delivery_id=str(pipeline["id"]),
				payload=payload,
				status="processed",
			)
			normalize_pipeline_event(mapping["gitlab_instance"], mapping_name, payload)
			results["pipelines"] += 1
		frappe.db.set_value(
			"GitLab Project Mapping",
			mapping_name,
			"last_reconciled_pipeline_at",
			frappe.utils.now_datetime(),
		)
		_touch_cursor(mapping_name, "pipeline", status="idle")
	except Exception as exc:
		_touch_cursor(mapping_name, "pipeline", status="failed", error=str(exc))
		raise

	linked_targets = frappe.get_all(
		"Development Artifact Link",
		filters={"project": mapping["project"]},
		fields=["target_doctype", "target_name"],
		group_by="target_doctype, target_name",
	)
	for row in linked_targets:
		update_work_item_summary(row["target_doctype"], row["target_name"])

	return results


def reconcile_all_enabled_mappings() -> list[dict[str, Any]]:
	results = []
	for row in frappe.get_all("GitLab Project Mapping", filters={"enabled": 1}, fields=["name"]):
		results.append({"mapping": row["name"], **reconcile_mapping(row["name"])})
	return results


def verify_all_mapping_webhooks() -> list[dict[str, Any]]:
	results = []
	for row in frappe.get_all("GitLab Project Mapping", filters={"enabled": 1}, fields=["name"]):
		results.append({"mapping": row["name"], **verify_mapping_webhook(row["name"])})
	return results
