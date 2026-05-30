"""Resolve normalized GitLab payloads into Development Workflow Rule events."""

from __future__ import annotations

from typing import Any


def resolve_push_workflow_event(payload: dict[str, Any], *, is_delete_push: bool) -> str | None:
	if is_delete_push:
		return "branch_deleted"
	return "branch_linked"


def resolve_merge_request_workflow_events(payload: dict[str, Any]) -> list[str]:
	attrs = payload.get("object_attributes") or {}
	action = (attrs.get("action") or "").lower()
	state = (attrs.get("state") or "").lower()
	events: list[str] = []

	if state == "merged" or action == "merge":
		return ["mr_merged"]

	if action == "approved":
		events.append("mr_approved")
	elif action == "unapproved":
		events.append("mr_changes_requested")
	elif action == "update":
		changes = payload.get("changes") or {}
		if changes.get("reviewers") or changes.get("reviewer_ids"):
			events.append("mr_review_started")
	elif action in ("open", "reopen"):
		events.append("mr_opened")
	elif state == "opened" and not events:
		events.append("mr_opened")

	return events


def resolve_pipeline_workflow_events(payload: dict[str, Any]) -> list[str]:
	attrs = payload.get("object_attributes") or {}
	status = (attrs.get("status") or "").lower()
	events: list[str] = []

	if status == "failed":
		events.append("pipeline_failed")
	elif status == "success":
		events.append("pipeline_succeeded")

	for build in payload.get("builds") or []:
		environment = build.get("environment") or {}
		if environment.get("name") and (build.get("status") or "").lower() == "success":
			events.append("deployment_succeeded")
			break

	return events
