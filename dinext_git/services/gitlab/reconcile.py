"""Scheduled reconciliation against GitLab REST API."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_git.services.gitlab.client import GitLabClient
from dinext_git.services.gitlab.normalizer import (
	log_event,
	normalize_merge_request_event,
	normalize_pipeline_event,
	normalize_release_event,
	release_payload_from_api,
)
from dinext_git.services.gitlab.payloads import flatten_artifact_names
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.store import get_mapping, mark_artifact_deleted
from dinext_git.services.gitlab.webhook_admin import verify_mapping_webhook
from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS
from dinext_git.services.gitlab.workflow_sync import apply_rules


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


def _apply_branch_deleted_workflow(deleted_artifact_names: list[str]) -> None:
	if not deleted_artifact_names:
		return

	links = frappe.get_all(
		"Development Artifact Link",
		filters={"artifact": ["in", deleted_artifact_names]},
		fields=["target_doctype", "target_name"],
	)
	seen: set[tuple[str, str]] = set()
	for link in links:
		target_key = (link["target_doctype"], link["target_name"])
		if target_key in seen:
			continue
		seen.add(target_key)
		apply_rules(link["target_doctype"], link["target_name"], "branch_deleted")


def _update_summaries_for_artifacts(artifact_names: set[str]) -> None:
	if not artifact_names:
		return

	linked_targets = frappe.get_all(
		"Development Artifact Link",
		filters={"artifact": ["in", list(artifact_names)]},
		fields=["target_doctype", "target_name"],
		group_by="target_doctype, target_name",
	)
	for row in linked_targets:
		update_work_item_summary(row["target_doctype"], row["target_name"])


def _reconcile_deleted_branches(mapping: dict[str, Any], client: GitLabClient, project_id: str | int) -> list[str]:
	remote_branch_names = {row["name"] for row in client.list_branches(project_id)}
	local_branches = frappe.get_all(
		"Development Artifact",
		filters={
			"project_mapping": mapping["name"],
			"artifact_type": "branch",
		},
		fields=["name", "external_id", "artifact_status"],
	)

	deleted_artifacts: list[str] = []
	for branch in local_branches:
		if branch.get("artifact_status") == DELETED_ARTIFACT_STATUS:
			continue
		if branch["external_id"] in remote_branch_names:
			continue
		artifact_name = mark_artifact_deleted(
			instance=mapping["gitlab_instance"],
			mapping=mapping["name"],
			artifact_type="branch",
			external_id=branch["external_id"],
			payload={"reconcile_reason": "branch_missing_in_gitlab", "branch_name": branch["external_id"]},
		)
		if artifact_name:
			deleted_artifacts.append(artifact_name)

	return deleted_artifacts


def reconcile_mapping(mapping_name: str) -> dict[str, Any]:
	mapping = get_mapping(mapping_name)
	client = GitLabClient(mapping["gitlab_instance"])
	project_id = mapping["gitlab_project_id"] or client.get_project(project_path=mapping["gitlab_project_path"])["id"]

	results: dict[str, Any] = {"merge_requests": 0, "pipelines": 0, "releases": 0, "branches_deleted": 0}
	touched_artifact_names: set[str] = set()

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
			normalized = normalize_merge_request_event(mapping["gitlab_instance"], mapping_name, payload)
			touched_artifact_names.update(flatten_artifact_names(normalized))
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
			normalized = normalize_pipeline_event(mapping["gitlab_instance"], mapping_name, payload)
			touched_artifact_names.update(flatten_artifact_names(normalized))
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

	_touch_cursor(mapping_name, "release", status="running")
	try:
		for release in client.list_releases(project_id, updated_after=mapping.get("last_reconciled_release_at")):
			payload = release_payload_from_api(release)
			log_event(
				instance=mapping["gitlab_instance"],
				mapping=mapping_name,
				event_type="reconcile_release",
				delivery_id=str(release.get("tag_name") or release.get("name")),
				payload=payload,
				status="processed",
			)
			normalized = normalize_release_event(mapping["gitlab_instance"], mapping_name, payload)
			touched_artifact_names.update(flatten_artifact_names(normalized))
			results["releases"] += 1
		frappe.db.set_value(
			"GitLab Project Mapping",
			mapping_name,
			"last_reconciled_release_at",
			frappe.utils.now_datetime(),
		)
		_touch_cursor(mapping_name, "release", status="idle")
	except Exception as exc:
		_touch_cursor(mapping_name, "release", status="failed", error=str(exc))
		raise

	deleted_branch_artifacts = _reconcile_deleted_branches(mapping, client, project_id)
	results["branches_deleted"] = len(deleted_branch_artifacts)
	touched_artifact_names.update(deleted_branch_artifacts)
	_update_summaries_for_artifacts(touched_artifact_names)
	_apply_branch_deleted_workflow(deleted_branch_artifacts)

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
