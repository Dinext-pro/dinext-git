"""Public GitLab webhook entrypoint."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.normalizer import (
	is_branch_delete_push,
	log_event,
	normalize_merge_request_event,
	normalize_pipeline_event,
	normalize_push_event,
)
from dinext_git.services.gitlab.payloads import flatten_artifact_names
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.workflow_sync import apply_rules


def _resolve_mapping(instance_name: str, payload: dict):
	project_id = (payload.get("project") or {}).get("id") or (payload.get("project") or {}).get("project_id")
	if not project_id:
		project_id = ((payload.get("object_attributes") or {}).get("target_project_id"))
	filters = {"gitlab_instance": instance_name}
	if project_id:
		mapping = frappe.db.get_value(
			"GitLab Project Mapping",
			{**filters, "gitlab_project_id": project_id},
			["name", "project", "parent"],
			as_dict=True,
		)
		if mapping:
			mapping["project"] = mapping.get("project") or mapping.get("parent")
			return mapping
		mapping = frappe.db.get_value(
			"GitLab Project Mapping",
			{**filters, "gitlab_project_id": str(project_id)},
			["name", "project", "parent"],
			as_dict=True,
		)
		if mapping:
			mapping["project"] = mapping.get("project") or mapping.get("parent")
			return mapping

	project = payload.get("project") or {}
	project_path = project.get("path_with_namespace")
	if not project_path:
		namespace = project.get("namespace")
		path = project.get("path")
		if namespace and path:
			project_path = f"{namespace}/{path}"
	if project_path:
		mapping = frappe.db.get_value(
			"GitLab Project Mapping",
			{**filters, "gitlab_project_path": project_path},
			["name", "project", "parent"],
			as_dict=True,
		)
		if mapping:
			mapping["project"] = mapping.get("project") or mapping.get("parent")
			return mapping
	return None


@frappe.whitelist(allow_guest=True)
def receive():
	event_type = frappe.get_request_header("X-Gitlab-Event") or ""
	delivery_id = frappe.get_request_header("X-Gitlab-Event-UUID")
	token = frappe.get_request_header("X-Gitlab-Token")
	payload = frappe.request.get_json() or {}
	instance_name = frappe.db.get_value("GitLab Instance", {"webhook_secret": token, "enabled": 1}, "name")
	if not instance_name:
		frappe.throw("Unknown GitLab webhook source", frappe.PermissionError)

	mapping = _resolve_mapping(instance_name, payload)
	log_event_name = log_event(
		instance=instance_name,
		mapping=mapping["name"] if mapping else None,
		event_type=event_type,
		delivery_id=delivery_id,
		payload=payload,
	)

	normalized = {}
	event_name = None
	if event_type == "Push Hook":
		normalized = normalize_push_event(instance_name, mapping["name"] if mapping else None, payload)
		if not is_branch_delete_push(payload):
			event_name = "branch_linked"
	elif event_type == "Merge Request Hook":
		normalized = normalize_merge_request_event(instance_name, mapping["name"] if mapping else None, payload)
		attrs = payload.get("object_attributes") or {}
		event_name = "mr_merged" if attrs.get("state") == "merged" else "mr_opened"
	elif event_type == "Pipeline Hook":
		normalized = normalize_pipeline_event(instance_name, mapping["name"] if mapping else None, payload)
		status = (payload.get("object_attributes") or {}).get("status")
		event_name = "pipeline_failed" if status == "failed" else "pipeline_succeeded"

	artifact_names = flatten_artifact_names(normalized)
	links = []
	if artifact_names:
		links = frappe.get_all(
			"Development Artifact Link",
			filters={"artifact": ["in", artifact_names]},
			fields=["target_doctype", "target_name"],
		)
	for link in links:
		update_work_item_summary(link["target_doctype"], link["target_name"])
		if event_name:
			apply_rules(link["target_doctype"], link["target_name"], event_name)

	frappe.db.set_value(
		"GitLab Event Log",
		log_event_name,
		{"status": "processed", "processed_on": frappe.utils.now_datetime()},
	)
	return {"ok": True, "event_log": log_event_name, "event_type": event_type}
