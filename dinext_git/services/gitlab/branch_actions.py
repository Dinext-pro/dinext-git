"""Create GitLab branches from Dinext work items."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from dinext_git.services.gitlab.client import GitLabClient
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


def build_branch_name(doc: dict[str, Any], mapping: dict[str, Any]) -> str:
	template = mapping.get("branch_naming_template") or DEFAULT_BRANCH_TEMPLATE
	context = {
		"key": doc["name"],
		"slug": slugify_fragment(doc.get("subject") or doc["name"]),
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


def preview_branch(doctype: str, name: str, mapping_name: str | None = None) -> dict[str, Any]:
	doc = get_work_item(doctype, name)
	mapping = _resolve_branch_mapping(doc, mapping_name)

	return {
		"work_item": doc,
		"mapping": mapping,
		"branch_name": build_branch_name(doc, mapping),
		"base_branch": mapping.get("default_base_branch") or "develop",
	}


def create_branch(doctype: str, name: str, mapping_name: str | None = None) -> dict[str, Any]:
	preview = preview_branch(doctype, name, mapping_name)
	doc = preview["work_item"]
	mapping = get_mapping(preview["mapping"]["name"])
	client = GitLabClient(mapping["gitlab_instance"], api_token=_get_user_gitlab_branch_token())

	project_id = mapping.get("gitlab_project_id")
	if not project_id:
		project = client.get_project(project_path=mapping["gitlab_project_path"])
		project_id = project["id"]
		frappe.db.set_value("GitLab Project Mapping", mapping["name"], "gitlab_project_id", project_id)

	try:
		branch_data = client.create_branch(project_id, preview["branch_name"], preview["base_branch"])
	except Exception:
		if client.request("GET", f"projects/{project_id}/repository/branches/{preview['branch_name']}"):
			branch_data = {
				"name": preview["branch_name"],
				"web_url": f"{client.base_url}/{mapping['gitlab_project_path']}/-/tree/{preview['branch_name']}",
				"commit": {},
			}
		else:
			raise

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
				"author_name": frappe.session.user,
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
			is_primary=1,
		)
	)
	update_work_item_summary(doctype, name)
	apply_rules(doctype, name, "branch_created")

	return {
		"branch_name": preview["branch_name"],
		"base_branch": preview["base_branch"],
		"artifact": artifact_name,
		"project_mapping": mapping["name"],
		"project_id": project_id,
		"artifact_uid": make_uid(mapping["gitlab_instance"], mapping["name"], "branch", preview["branch_name"]),
	}
