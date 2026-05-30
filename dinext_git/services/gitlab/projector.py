"""Project normalized artifact truth back onto Task and Issue."""

from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlencode

import frappe

from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS, RELEASE_SIDE_ARTIFACT_TYPES
from dinext_git.services.gitlab.store import get_instance, get_mapping

OPEN_MERGE_REQUEST_STATES = {"open", "opened", "reopen", "reopened"}
MERGED_MERGE_REQUEST_STATES = {"merged"}
CLOSED_MERGE_REQUEST_STATES = {"closed", "declined", "rejected"}


def _empty_summary() -> dict[str, Any]:
	return {
		"artifact_count": 0,
		"artifact_types": {},
		"last_merge_request": None,
		"last_pipeline_status": None,
		"last_deployment_status": None,
		"discrepancy_flags": [],
		"development_status": "not_started",
		"status_merge_request_count": 0,
		"status_merge_request_state": None,
		"status_merge_request_url": None,
	}


def _get_merge_request_state_family(status: str | None) -> str | None:
	normalized = (status or "").strip().lower()
	if normalized in OPEN_MERGE_REQUEST_STATES:
		return "opened"
	if normalized in MERGED_MERGE_REQUEST_STATES:
		return "merged"
	if normalized in CLOSED_MERGE_REQUEST_STATES:
		return "closed"
	return None


def _get_status_merge_request_state(development_status: str) -> str | None:
	if development_status == "in_progress":
		return "opened"
	if development_status in {"merged", "pipeline_failed", "deployed"}:
		return "merged"
	if development_status == "declined":
		return "closed"
	return None


def _build_status_merge_request_url(merge_requests: list[dict[str, Any]], state: str | None) -> str | None:
	if not merge_requests or not state:
		return None

	project_mappings = {artifact.get("project_mapping") for artifact in merge_requests if artifact.get("project_mapping")}
	if len(project_mappings) != 1:
		return None

	mapping = get_mapping(next(iter(project_mappings)))
	instance = get_instance(mapping["gitlab_instance"])
	query = urlencode({"scope": "all", "state": state})
	return f"{instance['base_url']}/{mapping['gitlab_project_path']}/-/merge_requests?{query}"


def collect_work_item_summary(target_doctype: str, target_name: str) -> dict[str, Any]:
	links = frappe.get_all(
		"Development Artifact Link",
		filters={"target_doctype": target_doctype, "target_name": target_name},
		fields=["artifact", "link_source", "is_primary"],
	)
	if not links:
		return _empty_summary()

	artifact_names = [link["artifact"] for link in links]
	artifacts = frappe.get_all(
		"Development Artifact",
		filters={"name": ["in", artifact_names]},
		fields=[
			"name",
			"project_mapping",
			"artifact_type",
			"artifact_status",
			"artifact_name",
			"web_url",
			"ref_name",
			"modified",
		],
		order_by="modified desc",
	)
	artifacts = [artifact for artifact in artifacts if artifact.get("artifact_status") != DELETED_ARTIFACT_STATUS]
	if not artifacts:
		return _empty_summary()
	type_counter = Counter(artifact["artifact_type"] for artifact in artifacts)
	last_merge_request = next((row for row in artifacts if row["artifact_type"] == "merge_request"), None)
	last_pipeline = next((row for row in artifacts if row["artifact_type"] == "pipeline"), None)
	last_deployment = next((row for row in artifacts if row["artifact_type"] == "deployment"), None)
	merge_requests = [artifact for artifact in artifacts if artifact["artifact_type"] == "merge_request"]
	open_merge_requests = [
		artifact for artifact in merge_requests if _get_merge_request_state_family(artifact.get("artifact_status")) == "opened"
	]
	merged_merge_requests = [
		artifact for artifact in merge_requests if _get_merge_request_state_family(artifact.get("artifact_status")) == "merged"
	]
	closed_merge_requests = [
		artifact for artifact in merge_requests if _get_merge_request_state_family(artifact.get("artifact_status")) == "closed"
	]

	flags = []
	if type_counter.get("branch", 0) and not type_counter.get("merge_request", 0):
		flags.append("no_merge_request")
	if any(
		artifact["artifact_type"] == "pipeline" and artifact["artifact_status"] == "failed"
		for artifact in artifacts
	):
		flags.append("pipeline_failed")
	has_release_side = any(artifact["artifact_type"] in RELEASE_SIDE_ARTIFACT_TYPES for artifact in artifacts)
	if has_release_side and not any(
		artifact["artifact_type"] == "merge_request" and artifact["artifact_status"] == "merged"
		for artifact in artifacts
	):
		flags.append("release_without_merge")

	development_status = "not_started"
	if type_counter.get("branch", 0) or open_merge_requests:
		development_status = "in_progress"
	if merged_merge_requests:
		development_status = "merged"
	if closed_merge_requests and not open_merge_requests and not merged_merge_requests:
		development_status = "declined"
	if last_pipeline and last_pipeline.get("artifact_status") == "failed":
		development_status = "pipeline_failed"
	if last_deployment and last_deployment.get("artifact_status") == "success":
		development_status = "deployed"
	status_merge_request_state = _get_status_merge_request_state(development_status)
	status_merge_requests = [
		artifact
		for artifact in merge_requests
		if _get_merge_request_state_family(artifact.get("artifact_status")) == status_merge_request_state
	]

	return {
		"artifact_count": len(artifacts),
		"artifact_types": dict(type_counter),
		"last_merge_request": last_merge_request,
		"last_pipeline_status": last_pipeline["artifact_status"] if last_pipeline else None,
		"last_deployment_status": last_deployment["artifact_status"] if last_deployment else None,
		"discrepancy_flags": flags,
		"development_status": development_status,
		"status_merge_request_count": len(status_merge_requests),
		"status_merge_request_state": status_merge_request_state,
		"status_merge_request_url": _build_status_merge_request_url(status_merge_requests, status_merge_request_state),
	}


def update_work_item_summary(target_doctype: str, target_name: str) -> dict[str, Any]:
	summary = collect_work_item_summary(target_doctype, target_name)
	field_map = {
		"custom_git_development_status": summary["development_status"],
		"custom_git_artifact_count": summary["artifact_count"],
		"custom_git_artifact_types": frappe.as_json(summary["artifact_types"]),
		"custom_git_last_pipeline_status": summary["last_pipeline_status"],
		"custom_git_last_deployment_status": summary["last_deployment_status"],
		"custom_git_discrepancy_flags": frappe.as_json(summary["discrepancy_flags"]),
	}
	if summary["last_merge_request"]:
		field_map["custom_git_last_merge_request"] = summary["last_merge_request"]["artifact_name"]

	field_map = {key: value for key, value in field_map.items() if value is not None}
	if field_map:
		frappe.db.set_value(target_doctype, target_name, field_map, update_modified=False)

	return summary
