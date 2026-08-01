"""Public GitLab webhook entrypoint."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_git.services.gitlab.normalizer import (
	is_branch_delete_push,
	log_event,
	normalize_merge_request_event,
	normalize_pipeline_event,
	normalize_push_event,
	normalize_release_event,
	normalize_tag_push_event,
)
from dinext_git.services.gitlab.utils import is_branch_ref, project_id_from_payload, project_path_from_payload
from dinext_git.services.gitlab.payloads import flatten_artifact_names, read_webhook_payload
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
	project_id = project_id_from_payload(payload)
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

	project_path = project_path_from_payload(payload)
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
		if not is_branch_ref(payload.get("ref")):
			return []
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
	payload = read_webhook_payload()
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
	elif event_type == "Tag Push Hook":
		normalized = normalize_tag_push_event(instance_name, mapping["name"] if mapping else None, payload)
	elif event_type == "Release Hook":
		normalized = normalize_release_event(instance_name, mapping["name"] if mapping else None, payload)

	artifact_names = flatten_artifact_names(normalized)
	workflow_events = _resolve_workflow_events(event_type, payload)
	_process_linked_work_items(artifact_names, workflow_events)

	event_log_update: dict[str, Any] = {
		"status": "processed",
		"processed_on": frappe.utils.now_datetime(),
	}
	if (
		event_type == "Push Hook"
		and is_branch_delete_push(payload)
		and not artifact_names
	):
		event_log_update["status"] = "ignored"
		event_log_update["error_message"] = (
			"Delete push received but no matching branch artifacts were found."
		)

	frappe.db.set_value("GitLab Event Log", log_event_name, event_log_update)
	return {"ok": True, "event_log": log_event_name, "event_type": event_type}
