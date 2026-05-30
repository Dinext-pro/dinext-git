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
from dinext_git.services.gitlab.workflow_events import (
	resolve_merge_request_workflow_events,
	resolve_pipeline_workflow_events,
	resolve_push_workflow_event,
)
from dinext_git.services.gitlab.workflow_sync import apply_rules


def _resolve_instance_name(token: str | None) -> str | None:
	if not token:
		return None

	for instance_name in frappe.get_all("GitLab Instance", filters={"enabled": 1}, pluck="name"):
		if frappe.get_doc("GitLab Instance", instance_name).get_password("webhook_secret") == token:
			return instance_name
	return None


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


def _resolve_workflow_events(event_type: str, payload: dict) -> list[str]:
	if event_type == "Push Hook":
		event_name = resolve_push_workflow_event(payload, is_delete_push=is_branch_delete_push(payload))
		return [event_name] if event_name else []

	if event_type == "Merge Request Hook":
		return resolve_merge_request_workflow_events(payload)

	if event_type == "Pipeline Hook":
		return resolve_pipeline_workflow_events(payload)

	return []


def _process_linked_work_items(artifact_names: list[str], workflow_events: list[str]) -> None:
	if not artifact_names:
		return

	links = frappe.get_all(
		"Development Artifact Link",
		filters={"artifact": ["in", artifact_names]},
		fields=["target_doctype", "target_name"],
	)
	seen: set[tuple[str, str]] = set()
	for link in links:
		target_key = (link["target_doctype"], link["target_name"])
		if target_key in seen:
			continue
		seen.add(target_key)
		update_work_item_summary(link["target_doctype"], link["target_name"])
		for event_name in workflow_events:
			apply_rules(link["target_doctype"], link["target_name"], event_name)


@frappe.whitelist(allow_guest=True)
def receive():
	event_type = frappe.get_request_header("X-Gitlab-Event") or ""
	delivery_id = frappe.get_request_header("X-Gitlab-Event-UUID")
	token = frappe.get_request_header("X-Gitlab-Token")
	payload = frappe.request.get_json() or {}
	instance_name = _resolve_instance_name(token)
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
	if event_type == "Push Hook":
		normalized = normalize_push_event(instance_name, mapping["name"] if mapping else None, payload)
	elif event_type == "Merge Request Hook":
		normalized = normalize_merge_request_event(instance_name, mapping["name"] if mapping else None, payload)
	elif event_type == "Pipeline Hook":
		normalized = normalize_pipeline_event(instance_name, mapping["name"] if mapping else None, payload)

	workflow_events = _resolve_workflow_events(event_type, payload)
	_process_linked_work_items(flatten_artifact_names(normalized), workflow_events)

	frappe.db.set_value(
		"GitLab Event Log",
		log_event_name,
		{"status": "processed", "processed_on": frappe.utils.now_datetime()},
	)
	return {"ok": True, "event_log": log_event_name, "event_type": event_type}
