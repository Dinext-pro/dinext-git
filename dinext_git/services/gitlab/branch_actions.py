"""Create GitLab branches from Dinext work items."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from dinext_git.services.gitlab.client import GitLabClient
from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	get_default_mapping_for_project,
	get_mapping,
	get_mappings_for_project,
	get_work_item,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.services.gitlab.utils import make_uid, slugify_fragment
from dinext_git.services.gitlab.validators import validate_branch_template
from dinext_git.services.gitlab.workflow_sync import apply_rules

DEFAULT_BRANCH_TEMPLATE = "feature/{key}-{slug}"


def _get_user_gitlab_branch_token() -> str:
	user = frappe.get_doc("User", frappe.session.user)
	token = user.get_password("custom_gitlab_branch_api_token", raise_exception=False)
	if not token:
		frappe.throw(
			_(
				"Create Branch requires a personal GitLab token in your user profile. Fill in GitLab Branch Token and try again."
			)
		)
	return token


def _resolve_branch_mapping(doc: dict[str, Any], mapping_name: str | None = None) -> dict[str, Any]:
	project = doc.get("project")
	if mapping_name:
		mapping = get_mapping(mapping_name)
		if mapping.get("project") != project:
			frappe.throw(
				_("GitLab project mapping {0} does not belong to Dinext project {1}.").format(mapping_name, project)
			)
		if not mapping.get("enabled"):
			frappe.throw(_("GitLab project mapping {0} is disabled.").format(mapping_name))
		return mapping

	default_mapping = get_default_mapping_for_project(project)
	if default_mapping:
		return default_mapping

	mappings = get_mappings_for_project(project)
	if not mappings:
		frappe.throw(_("No enabled GitLab project mapping was found for project {0}.").format(project))
	if len(mappings) > 1:
		frappe.throw(
			_(
				"Select a GitLab repository before creating a branch because project {0} has multiple mappings and no default."
			).format(project)
		)
	return mappings[0]


def _resolve_branch_slug_fragment(doc: dict[str, Any]) -> str:
	source = doc.get("subject") or doc["name"]
	resolved = slugify_fragment(source or "")
	if not resolved:
		frappe.throw(_("Branch slug must contain at least one letter or number."))
	return resolved


def _resolve_branch_template(mapping: dict[str, Any], branch_template: str | None = None) -> str:
	template = (branch_template if branch_template is not None else mapping.get("branch_naming_template") or DEFAULT_BRANCH_TEMPLATE).strip()
	validate_branch_template(template)
	return template


def _resolve_base_branch(mapping: dict[str, Any], base_branch: str | None = None) -> str:
	resolved = (base_branch if base_branch is not None else mapping.get("default_base_branch") or "develop").strip()
	if not resolved:
		frappe.throw(_("Base branch is required."))
	return resolved


def _get_project_id(client: GitLabClient, mapping: dict[str, Any]) -> str | int:
	project_id = mapping.get("gitlab_project_id")
	if project_id:
		return project_id

	project = client.get_project(project_path=mapping["gitlab_project_path"])
	project_id = project["id"]
	frappe.db.set_value("GitLab Project Mapping", mapping["name"], "gitlab_project_id", project_id)
	return project_id


def _normalize_branch_names(branches: list[dict[str, Any]] | None) -> list[str]:
	if not branches:
		return []
	return sorted({row["name"] for row in branches if row.get("name")})


def _ensure_default_base_branch_in_list(branch_names: list[str], default_base_branch: str | None) -> list[str]:
	default = (default_base_branch or "develop").strip()
	if not default:
		return branch_names
	if default in branch_names:
		return branch_names
	return [default, *branch_names]


def list_available_base_branches(mapping_name: str) -> list[str]:
	user_token = _get_user_gitlab_branch_token()
	mapping = get_mapping(mapping_name)
	client = GitLabClient(mapping["gitlab_instance"], api_token=user_token)
	project_id = _get_project_id(client, mapping)
	branch_names = _normalize_branch_names(client.list_branches(project_id))
	return _ensure_default_base_branch_in_list(branch_names, mapping.get("default_base_branch"))


def _has_active_branch_artifact(doctype: str, name: str) -> bool:
	links = frappe.get_all(
		"Development Artifact Link",
		filters={"target_doctype": doctype, "target_name": name},
		fields=["artifact"],
	)
	if not links:
		return False

	active_branch_names = frappe.get_all(
		"Development Artifact",
		filters={
			"name": ["in", [row["artifact"] for row in links]],
			"artifact_type": "branch",
			"artifact_status": ["!=", DELETED_ARTIFACT_STATUS],
		},
		pluck="name",
		limit=1,
	)
	return bool(active_branch_names)


def _ensure_branch_name_available(mapping: dict[str, Any], client: GitLabClient, project_id: str | int, branch_name: str) -> None:
	artifact_uid = make_uid(mapping["gitlab_instance"], mapping["name"], "branch", branch_name)
	existing_artifact = frappe.db.get_value(
		"Development Artifact",
		{"artifact_uid": artifact_uid},
		["name", "artifact_status"],
		as_dict=True,
	)
	if existing_artifact and existing_artifact.get("artifact_status") != DELETED_ARTIFACT_STATUS:
		frappe.throw(_("Branch {0} is already linked. Choose another branch name.").format(branch_name))

	if client.get_branch(project_id, branch_name):
		frappe.throw(_("GitLab branch {0} already exists in the selected repository. Choose another branch name.").format(branch_name))


def _ensure_base_branch_exists(client: GitLabClient, project_id: str | int, base_branch: str) -> None:
	if client.get_branch(project_id, base_branch):
		return
	frappe.throw(_("Base branch {0} was not found in the selected repository.").format(base_branch))


def build_branch_name(
	doc: dict[str, Any],
	mapping: dict[str, Any],
	branch_template: str | None = None,
) -> str:
	template = _resolve_branch_template(mapping, branch_template)
	resolved_slug = _resolve_branch_slug_fragment(doc)
	context = {
		"key": doc["name"],
		"slug": resolved_slug,
		"doctype": doc["doctype"].lower(),
		"type_slug": "bugfix" if doc["doctype"] == "Issue" else "feature",
		"project": slugify_fragment(mapping.get("project") or ""),
	}
	branch_name = template.format(**context)
	branch_name = branch_name.strip().replace(" ", "-")
	if doc["name"] not in branch_name:
		frappe.throw(_("Branch naming template must include the Dinext key."))
	if ".." in branch_name or branch_name.endswith("/"):
		frappe.throw(_("Generated branch name is not a valid Git ref."))
	return branch_name


def get_branch_dialog_options(doctype: str, name: str, mapping_name: str | None = None) -> dict[str, Any]:
	doc = get_work_item(doctype, name)
	mapping = _resolve_branch_mapping(doc, mapping_name)
	branch_template = _resolve_branch_template(mapping)
	base_branch = _resolve_base_branch(mapping)
	available_base_branches = list_available_base_branches(mapping["name"])
	if base_branch not in available_base_branches:
		available_base_branches = [base_branch, *available_base_branches]

	return {
		"mapping": mapping,
		"branch_template": branch_template,
		"base_branch": base_branch,
		"available_base_branches": available_base_branches,
		"branch_preview": preview_branch(
			doctype,
			name,
			mapping["name"],
			branch_template=branch_template,
			base_branch=base_branch,
		),
	}


def preview_branch(
	doctype: str,
	name: str,
	mapping_name: str | None = None,
	branch_template: str | None = None,
	base_branch: str | None = None,
) -> dict[str, Any]:
	doc = get_work_item(doctype, name)
	mapping = _resolve_branch_mapping(doc, mapping_name)
	resolved_template = _resolve_branch_template(mapping, branch_template)
	resolved_slug = _resolve_branch_slug_fragment(doc)
	resolved_base_branch = _resolve_base_branch(mapping, base_branch)

	return {
		"work_item": doc,
		"mapping": mapping,
		"branch_template": resolved_template,
		"slug_fragment": resolved_slug,
		"branch_name": build_branch_name(doc, mapping, resolved_template),
		"base_branch": resolved_base_branch,
	}


def create_branch(
	doctype: str,
	name: str,
	mapping_name: str | None = None,
	branch_template: str | None = None,
	base_branch: str | None = None,
) -> dict[str, Any]:
	user_token = _get_user_gitlab_branch_token()
	preview = preview_branch(doctype, name, mapping_name, branch_template, base_branch)
	doc = preview["work_item"]
	mapping = get_mapping(preview["mapping"]["name"])
	client = GitLabClient(mapping["gitlab_instance"], api_token=user_token)
	project_id = _get_project_id(client, mapping)
	_ensure_base_branch_exists(client, project_id, preview["base_branch"])
	_ensure_branch_name_available(mapping, client, project_id, preview["branch_name"])

	try:
		branch_data = client.create_branch(project_id, preview["branch_name"], preview["base_branch"])
	except Exception as exc:
		if client.get_branch(project_id, preview["branch_name"]):
			frappe.throw(
				_("GitLab branch {0} already exists in the selected repository. Choose another branch name.").format(
					preview["branch_name"]
				)
			)
		raise exc

	session_user = frappe.get_doc("User", frappe.session.user)
	artifact_name = upsert_artifact(
		build_artifact_payload(
			instance=mapping["gitlab_instance"],
			mapping=mapping["name"],
			artifact_type="branch",
			external_id=preview["branch_name"],
			data={
				"artifact_name": preview["branch_name"],
				"ref_name": preview["branch_name"],
				"artifact_status": "active",
				"web_url": branch_data.get("web_url"),
				"commit_sha": (branch_data.get("commit") or {}).get("id"),
				"title": doc.get("subject"),
				"author_name": session_user.full_name or session_user.name,
				"author_email": session_user.email,
				"author_avatar_url": session_user.user_image,
			},
		)
	)
	upsert_artifact_link(
		build_artifact_link_payload(
			artifact=artifact_name,
			target_doctype=doctype,
			target_name=name,
			link_source="branch_create",
			extracted_key=doc["name"],
			is_primary=0 if _has_active_branch_artifact(doctype, name) else 1,
		)
	)
	update_work_item_summary(doctype, name)
	apply_rules(doctype, name, "branch_created")

	return {
		"branch_template": preview["branch_template"],
		"slug_fragment": preview["slug_fragment"],
		"branch_name": preview["branch_name"],
		"base_branch": preview["base_branch"],
		"artifact": artifact_name,
		"project_mapping": mapping["name"],
		"project_id": project_id,
		"artifact_uid": make_uid(mapping["gitlab_instance"], mapping["name"], "branch", preview["branch_name"]),
	}
