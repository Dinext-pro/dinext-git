"""Task and Issue development panel payloads."""

from __future__ import annotations

from urllib.parse import quote, urlparse

import frappe
from frappe import _

from dinext_git.services.gitlab.constants import (
	DELETED_ARTIFACT_STATUS,
	DEVELOPMENT_STATUS_NOT_STARTED,
	DEVELOPMENT_STATUS_VALUES,
)
from dinext_git.services.gitlab.branch_actions import DEFAULT_BRANCH_TEMPLATE, get_branch_dialog_options, preview_branch
from dinext_git.services.gitlab.panel_metadata import (
	build_summary_timestamps,
	build_user_avatar_lookup,
	decorate_artifact_row,
)
from dinext_git.services.gitlab.projector import collect_work_item_summary
from dinext_git.services.gitlab.store import get_default_mapping_for_project, get_instance, get_mappings_for_project

DISCREPANCY_FLAG_LABELS = {
	"no_merge_request": _("No merge request"),
	"pipeline_failed": _("Pipeline failed"),
	"release_without_merge": _("Release without merge"),
}

MERGE_REQUEST_STATE_LABELS = {
	"opened": _("Open merge requests"),
	"merged": _("Merged merge requests"),
	"closed": _("Declined merge requests"),
}


def _development_status_label(status: str | None) -> str:
	if status in DEVELOPMENT_STATUS_VALUES:
		return _(status)
	return _(status or DEVELOPMENT_STATUS_NOT_STARTED)


def _decorate_summary(summary: dict) -> dict:
	decorated = dict(summary)
	status_code = decorated.get("development_status")
	decorated["development_status_label"] = _development_status_label(status_code)
	state_code = decorated.get("status_merge_request_state")
	decorated["status_merge_request_label"] = MERGE_REQUEST_STATE_LABELS.get(
		state_code, frappe.unscrub(state_code or "merge_requests")
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


def _gitlab_instance_host(instance_name: str | None) -> str | None:
	if not instance_name:
		return None

	try:
		instance = get_instance(instance_name)
	except Exception:
		return instance_name

	base_url = (instance.get("base_url") or "").strip()
	if not base_url:
		return instance_name

	host = urlparse(base_url).netloc
	return host or instance_name


def _build_gitlab_project_tree_url(mapping: dict | None) -> str | None:
	if not mapping:
		return None

	project_path = (mapping.get("gitlab_project_path") or "").strip()
	instance_name = mapping.get("gitlab_instance")
	if not project_path or not instance_name:
		return None

	try:
		instance = get_instance(instance_name)
	except Exception:
		return None

	base_url = (instance.get("base_url") or "").rstrip("/")
	if not base_url:
		return None

	branch = (mapping.get("default_base_branch") or "develop").strip()
	return f"{base_url}/{project_path}/-/tree/{quote(branch, safe='/')}"


def _build_group_metadata(mapping: dict | None) -> dict:
	default_base_branch = (mapping or {}).get("default_base_branch") or "develop" if mapping else None
	return {
		"mapping_name": (mapping or {}).get("name"),
		"is_default": bool(mapping and mapping.get("is_default")),
		"gitlab_project_path": (mapping or {}).get("gitlab_project_path") or _("Unmapped"),
		"gitlab_instance": (mapping or {}).get("gitlab_instance"),
		"default_base_branch": default_base_branch,
		"gitlab_project_url": _build_gitlab_project_tree_url(mapping),
		"artifacts_by_type": {},
	}


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
				"author_name",
				"author_email",
				"author_avatar_url",
				"modified",
			],
			order_by="modified desc",
		)
		artifact_rows = [row for row in artifact_rows if row.get("artifact_status") != DELETED_ARTIFACT_STATUS]
		user_lookup = build_user_avatar_lookup([row.get("author_email") for row in artifact_rows])
		link_by_artifact = {row["artifact"]: row for row in links}
		for artifact in artifact_rows:
			artifact["link"] = link_by_artifact.get(artifact["name"])
			artifact["artifact_type_label"] = frappe.unscrub(artifact["artifact_type"] or "")
			artifact["artifact_status_label"] = frappe.unscrub(artifact["artifact_status"] or "n/a")
			artifacts.append(decorate_artifact_row(artifact, user_lookup))

	last_updated_on, last_updated_on_by_type = build_summary_timestamps(artifacts)
	summary["last_updated_on"] = last_updated_on
	summary["last_updated_on_by_type"] = last_updated_on_by_type

	mapping_lookup = {row["name"]: row for row in mappings}
	grouped = {}
	for artifact in artifacts:
		mapping_name = artifact.get("project_mapping")
		mapping = mapping_lookup.get(mapping_name)
		group_key = mapping_name or "unmapped"
		group = grouped.setdefault(group_key, _build_group_metadata(mapping))
		if mapping_name:
			group["mapping_name"] = mapping_name
		group["artifacts_by_type"].setdefault(artifact["artifact_type"], []).append(artifact)

	branch_preview = None
	can_create_branch = False
	branch_error = None
	default_mapping = get_default_mapping_for_project(doc.get("project"))
	mapping_options = [
		{
			"name": row["name"],
			"gitlab_project_path": row.get("gitlab_project_path"),
			"gitlab_instance": row.get("gitlab_instance"),
			"gitlab_instance_host": _gitlab_instance_host(row.get("gitlab_instance")),
			"default_base_branch": row.get("default_base_branch"),
			"branch_naming_template": row.get("branch_naming_template") or DEFAULT_BRANCH_TEMPLATE,
			"is_default": bool(row.get("is_default")),
		}
		for row in mappings
	]
	selected_mapping_name = (default_mapping or {}).get("name") or (mapping_options[0] if mapping_options else {}).get("name")
	selected_mapping = mapping_lookup.get(selected_mapping_name) if selected_mapping_name else None
	available_base_branches: list[str] = []
	default_branch_template = (selected_mapping or {}).get("branch_naming_template") or DEFAULT_BRANCH_TEMPLATE
	default_base_branch = (selected_mapping or {}).get("default_base_branch") or "develop"
	try:
		dialog_options = get_branch_dialog_options(doctype, name, selected_mapping_name)
		branch_preview = dialog_options["branch_preview"]
		available_base_branches = dialog_options["available_base_branches"]
		default_branch_template = dialog_options["branch_template"]
		default_base_branch = dialog_options["base_branch"]
		can_create_branch = True
	except Exception as exc:
		branch_error = str(exc)
		try:
			branch_preview = preview_branch(doctype, name, selected_mapping_name)
		except Exception:
			branch_preview = None

	return {
		"work_item": doc,
		"show_gitlab_tab": True,
		"summary": summary,
		"can_create_branch": can_create_branch,
		"branch_error": branch_error,
		"branch_preview": branch_preview,
		"default_branch_template": default_branch_template,
		"default_base_branch": default_base_branch,
		"available_base_branches": available_base_branches,
		"branch_mapping_options": mapping_options,
		"show_branch_mapping_details": len(mapping_options) > 1,
		"default_mapping_name": (default_mapping or {}).get("name") or selected_mapping_name,
		"grouped_artifacts": grouped,
		"empty_state_message": _("No GitLab development activity has been linked yet."),
	}


@frappe.whitelist()
def get_panel(doctype: str, name: str):
	return _panel_payload(doctype, name)
