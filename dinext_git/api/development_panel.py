"""Task and Issue development panel payloads."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_git.services.gitlab.branch_actions import preview_branch
from dinext_git.services.gitlab.projector import collect_work_item_summary
from dinext_git.services.gitlab.store import get_default_mapping_for_project, get_mappings_for_project

DEVELOPMENT_STATUS_LABELS = {
	"not_started": _("Not started"),
	"in_progress": _("In progress"),
	"merged": _("Merged"),
	"pipeline_failed": _("Pipeline failed"),
	"deployed": _("Deployed"),
}

DISCREPANCY_FLAG_LABELS = {
	"no_merge_request": _("No merge request"),
	"pipeline_failed": _("Pipeline failed"),
	"release_without_merge": _("Release without merge"),
}


def _decorate_summary(summary: dict) -> dict:
	decorated = dict(summary)
	status_code = decorated.get("development_status")
	decorated["development_status_label"] = DEVELOPMENT_STATUS_LABELS.get(
		status_code, frappe.unscrub(status_code or "not_started")
	)
	decorated["discrepancy_badges"] = [
		{
			"code": flag,
			"label": DISCREPANCY_FLAG_LABELS.get(flag, frappe.unscrub(flag)),
		}
		for flag in decorated.get("discrepancy_flags", [])
	]
	return decorated


def _get_type_fieldname(doctype: str) -> str | None:
	if doctype == "Task":
		return "type"
	if doctype == "Issue":
		return "issue_type"
	return None


def _get_allowed_types_for_doctype(project: str | None, doctype: str) -> tuple[bool, set[str]]:
	if not project:
		return False, set()

	rows = frappe.get_all(
		"GitLab Type Visibility Rule",
		filters={
			"parent": project,
			"parenttype": "Project",
			"parentfield": "custom_git_type_visibility_rules",
			"target_doctype": doctype,
		},
		fields=["task_type", "issue_type"],
		order_by="idx asc",
	)
	allow_all = False
	allowed = set()
	for row in rows:
		type_name = row.get("task_type") or row.get("issue_type")
		if not type_name:
			allow_all = True
			continue
		allowed.add(type_name)
	return allow_all, allowed


def _should_show_gitlab_tab(doctype: str, doc: dict, mappings: list[dict]) -> bool:
	if not mappings:
		return False

	type_fieldname = _get_type_fieldname(doctype)
	if not type_fieldname:
		return True

	allow_all_types, allowed_types = _get_allowed_types_for_doctype(doc.get("project"), doctype)
	if allow_all_types or not allowed_types:
		return True

	return (doc.get(type_fieldname) or "") in allowed_types


def _panel_payload(doctype: str, name: str) -> dict:
	fields = ["name", "subject", "project", "status"]
	type_fieldname = _get_type_fieldname(doctype)
	if type_fieldname:
		fields.append(type_fieldname)
	doc = frappe.db.get_value(doctype, name, fields, as_dict=True)
	mappings = get_mappings_for_project(doc.get("project"))
	show_gitlab_tab = _should_show_gitlab_tab(doctype, doc, mappings)
	if not show_gitlab_tab:
		return {
			"work_item": doc,
			"show_gitlab_tab": False,
		}

	summary = _decorate_summary(collect_work_item_summary(doctype, name))
	links = frappe.get_all(
		"Development Artifact Link",
		filters={"target_doctype": doctype, "target_name": name},
		fields=["artifact", "link_source", "extracted_key", "is_primary"],
		order_by="modified desc",
	)
	artifacts = []
	if links:
		artifact_names = [row["artifact"] for row in links]
		artifact_rows = frappe.get_all(
			"Development Artifact",
			filters={"name": ["in", artifact_names]},
			fields=[
				"name",
				"project_mapping",
				"artifact_type",
				"artifact_name",
				"artifact_status",
				"web_url",
				"ref_name",
				"source_branch",
				"target_branch",
				"commit_sha",
				"modified",
			],
			order_by="modified desc",
		)
		link_by_artifact = {row["artifact"]: row for row in links}
		for artifact in artifact_rows:
			artifact["link"] = link_by_artifact.get(artifact["name"])
			artifact["artifact_type_label"] = frappe.unscrub(artifact["artifact_type"] or "")
			artifact["artifact_status_label"] = frappe.unscrub(artifact["artifact_status"] or "n/a")
			artifacts.append(artifact)

	mapping_lookup = {row["name"]: row for row in mappings}
	grouped = {}
	for artifact in artifacts:
		mapping_name = artifact.get("project_mapping")
		mapping = mapping_lookup.get(mapping_name)
		group_key = mapping_name or "unmapped"
		group = grouped.setdefault(
			group_key,
			{
				"mapping_name": mapping_name,
				"is_default": bool(mapping and mapping.get("is_default")),
				"gitlab_project_path": (mapping or {}).get("gitlab_project_path") or _("Unmapped"),
				"gitlab_instance": (mapping or {}).get("gitlab_instance"),
				"artifacts_by_type": {},
			},
		)
		group["artifacts_by_type"].setdefault(artifact["artifact_type"], []).append(artifact)

	has_branch_artifact = any(artifact.get("artifact_type") == "branch" for artifact in artifacts)
	branch_preview = None
	can_create_branch = False
	branch_error = None
	default_mapping = get_default_mapping_for_project(doc.get("project"))
	mapping_options = [
		{
			"name": row["name"],
			"gitlab_project_path": row.get("gitlab_project_path"),
			"default_base_branch": row.get("default_base_branch"),
			"is_default": bool(row.get("is_default")),
		}
		for row in mappings
	]
	if not has_branch_artifact:
		try:
			selected_mapping_name = (default_mapping or {}).get("name")
			branch_preview = preview_branch(doctype, name, selected_mapping_name)
			can_create_branch = True
		except Exception as exc:
			branch_error = str(exc)

	return {
		"work_item": doc,
		"show_gitlab_tab": True,
		"summary": summary,
		"can_create_branch": can_create_branch,
		"branch_error": branch_error,
		"branch_preview": branch_preview,
		"branch_mapping_options": mapping_options,
		"show_branch_mapping_details": len(mapping_options) > 1,
		"default_mapping_name": (default_mapping or {}).get("name"),
		"grouped_artifacts": grouped,
		"empty_state_message": _("No GitLab development activity has been linked yet."),
	}


@frappe.whitelist()
def get_panel(doctype: str, name: str):
	return _panel_payload(doctype, name)


def get_task_dashboard_data(data=None):
	return {"transactions": [{"label": _("Development"), "items": ["Development Artifact", "Development Artifact Link"]}]}


def get_issue_dashboard_data(data=None):
	return {"transactions": [{"label": _("Development"), "items": ["Development Artifact", "Development Artifact Link"]}]}
