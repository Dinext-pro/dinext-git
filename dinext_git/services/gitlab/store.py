"""Persistence helpers for Dinext Git documents."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS, find_non_deleted_artifact_name
from dinext_git.services.gitlab.utils import json_dumps, make_uid, project_id_from_payload, project_path_from_payload


def get_mapping(name: str) -> dict[str, Any]:
	mapping = frappe.db.get_value(
		"GitLab Project Mapping",
		name,
		[
			"name",
			"project",
			"parent",
			"parenttype",
			"gitlab_instance",
			"gitlab_group_path",
			"gitlab_project_path",
			"gitlab_project_id",
			"default_base_branch",
			"branch_naming_template",
			"is_default",
			"enabled",
			"remote_webhook_id",
			"webhook_status",
			"webhook_last_verified_on",
			"webhook_callback_url",
		],
		as_dict=True,
	)
	if not mapping:
		frappe.throw(_("GitLab project mapping {0} was not found.").format(name))
	mapping["project"] = mapping.get("project") or mapping.get("parent")
	return mapping


def get_mappings_for_project(project: str | None) -> list[dict[str, Any]]:
	if not project:
		return []

	rows = frappe.get_all(
		"GitLab Project Mapping",
		filters={
			"parent": project,
			"parenttype": "Project",
			"enabled": 1,
		},
		fields=[
			"name",
			"project",
			"parent",
			"parenttype",
			"gitlab_instance",
			"gitlab_group_path",
			"gitlab_project_path",
			"gitlab_project_id",
			"default_base_branch",
			"branch_naming_template",
			"is_default",
			"enabled",
			"remote_webhook_id",
			"webhook_status",
		],
		order_by="is_default desc, idx asc, creation asc",
	)
	if not rows:
		rows = frappe.get_all(
			"GitLab Project Mapping",
			filters={"project": project, "enabled": 1},
			fields=[
				"name",
				"project",
				"parent",
				"parenttype",
				"gitlab_instance",
				"gitlab_group_path",
				"gitlab_project_path",
				"gitlab_project_id",
				"default_base_branch",
				"branch_naming_template",
				"is_default",
				"enabled",
				"remote_webhook_id",
				"webhook_status",
			],
			order_by="is_default desc, creation asc",
		)
	for row in rows:
		row["project"] = row.get("project") or row.get("parent")
	return rows


def get_default_mapping_for_project(project: str | None) -> dict[str, Any] | None:
	rows = get_mappings_for_project(project)
	if not rows:
		return None

	default_rows = [row for row in rows if row.get("is_default")]
	if len(default_rows) > 1:
		frappe.throw(_("Only one default GitLab project mapping is allowed for project {0}.").format(project))
	if len(default_rows) == 1:
		return default_rows[0]
	if len(rows) == 1:
		return rows[0]
	return None


def get_mapping_for_project(project: str | None) -> dict[str, Any] | None:
	"""Backward-compatible alias for legacy callers that expect a single mapping."""
	return get_default_mapping_for_project(project)


def get_instance(name: str) -> dict[str, Any]:
	doc = frappe.get_doc("GitLab Instance", name)
	return {
		"name": doc.name,
		"base_url": doc.base_url,
		"api_token": doc.get_password("api_token"),
		"webhook_secret": doc.get_password("webhook_secret"),
		"verify_ssl": doc.verify_ssl,
		"timeout_seconds": doc.timeout_seconds,
		"enabled": doc.enabled,
	}


def get_work_item(doctype: str, name: str) -> dict[str, Any]:
	doc = frappe.db.get_value(
		doctype,
		name,
		["name", "subject", "project", "status", "modified"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("{0} {1} was not found.").format(doctype, name))
	doc["doctype"] = doctype
	return doc


def upsert_artifact(payload: dict[str, Any]) -> str:
	artifact_uid = payload["artifact_uid"]
	existing_name = frappe.db.get_value("Development Artifact", {"artifact_uid": artifact_uid}, "name")

	if existing_name:
		frappe.get_doc("Development Artifact", existing_name).update(payload).save(ignore_permissions=True)
		return existing_name

	doc = frappe.get_doc({"doctype": "Development Artifact", **payload})
	doc.insert(ignore_permissions=True)
	return doc.name


def mark_artifact_deleted(
	*,
	instance: str,
	mapping: str | None,
	artifact_type: str,
	external_id: str,
	payload: dict[str, Any] | None = None,
) -> str | None:
	deleted = mark_branch_artifacts_deleted(
		instance=instance,
		mapping=mapping,
		external_id=external_id,
		payload=payload,
		project_id=None,
		project_path=None,
	)
	return deleted[0] if deleted else None


def _branch_external_id_candidates(external_id: str) -> list[str]:
	candidates = [external_id]
	if "/" in external_id:
		legacy_external_id = external_id.rsplit("/", 1)[-1]
		if legacy_external_id not in candidates:
			candidates.append(legacy_external_id)
	return candidates


def _mapping_names_for_gitlab_project(
	instance: str,
	*,
	mapping: str | None = None,
	project_id: str | int | None = None,
	project_path: str | None = None,
) -> list[str]:
	mapping_names: list[str] = []
	if mapping:
		mapping_names.append(mapping)

	if project_id not in (None, ""):
		for candidate in {project_id, str(project_id)}:
			for name in frappe.get_all(
				"GitLab Project Mapping",
				filters={"gitlab_instance": instance, "gitlab_project_id": candidate, "enabled": 1},
				pluck="name",
			):
				if name not in mapping_names:
					mapping_names.append(name)

	if project_path:
		for name in frappe.get_all(
			"GitLab Project Mapping",
			filters={"gitlab_instance": instance, "gitlab_project_path": project_path, "enabled": 1},
			pluck="name",
		):
			if name not in mapping_names:
				mapping_names.append(name)

	return mapping_names


def find_branch_artifacts_for_delete(
	*,
	instance: str,
	external_id: str,
	mapping: str | None = None,
	project_id: str | int | None = None,
	project_path: str | None = None,
) -> list[str]:
	mapping_names = _mapping_names_for_gitlab_project(
		instance,
		mapping=mapping,
		project_id=project_id,
		project_path=project_path,
	)
	if not mapping_names:
		return []

	found: list[str] = []
	seen: set[str] = set()

	for mapping_name in mapping_names:
		for ext_id in _branch_external_id_candidates(external_id):
			artifact_uid = make_uid(instance, mapping_name, "branch", ext_id)
			artifact_name = find_non_deleted_artifact_name(
				{"artifact_uid": artifact_uid, "artifact_type": "branch"}
			)
			if artifact_name and artifact_name not in seen:
				seen.add(artifact_name)
				found.append(artifact_name)
				continue

			artifact_name = find_non_deleted_artifact_name(
				{
					"gitlab_instance": instance,
					"project_mapping": mapping_name,
					"artifact_type": "branch",
					"external_id": ext_id,
				}
			)
			if artifact_name and artifact_name not in seen:
				seen.add(artifact_name)
				found.append(artifact_name)

	return found


def mark_branch_artifacts_deleted(
	*,
	instance: str,
	external_id: str,
	payload: dict[str, Any] | None = None,
	mapping: str | None = None,
	project_id: str | int | None = None,
	project_path: str | None = None,
) -> list[str]:
	artifact_names = find_branch_artifacts_for_delete(
		instance=instance,
		external_id=external_id,
		mapping=mapping,
		project_id=project_id,
		project_path=project_path,
	)
	if not artifact_names:
		return []

	values: dict[str, Any] = {"artifact_status": DELETED_ARTIFACT_STATUS}
	if payload is not None:
		values["payload_json"] = json_dumps(payload)

	normalized_identity = {
		"external_id": external_id,
		"ref_name": external_id,
		"artifact_name": external_id,
	}

	for artifact_name in artifact_names:
		frappe.db.set_value(
			"Development Artifact",
			artifact_name,
			{**values, **normalized_identity},
			update_modified=True,
		)

	return artifact_names


def upsert_artifact_link(payload: dict[str, Any]) -> str:
	link_uid = payload["link_uid"]
	existing_name = frappe.db.get_value("Development Artifact Link", {"link_uid": link_uid}, "name")

	if existing_name:
		frappe.get_doc("Development Artifact Link", existing_name).update(payload).save(ignore_permissions=True)
		return existing_name

	doc = frappe.get_doc({"doctype": "Development Artifact Link", **payload})
	doc.insert(ignore_permissions=True)
	return doc.name


def build_artifact_payload(
	*,
	instance: str,
	mapping: str | None,
	artifact_type: str,
	external_id: str,
	data: dict[str, Any],
) -> dict[str, Any]:
	artifact_uid = make_uid(instance, mapping, artifact_type, external_id)
	return {
		"artifact_uid": artifact_uid,
		"gitlab_instance": instance,
		"project_mapping": mapping,
		"artifact_type": artifact_type,
		"external_id": external_id,
		"external_iid": data.get("external_iid"),
		"artifact_name": data.get("artifact_name"),
		"ref_name": data.get("ref_name"),
		"artifact_status": data.get("artifact_status"),
		"web_url": data.get("web_url"),
		"source_branch": data.get("source_branch"),
		"target_branch": data.get("target_branch"),
		"commit_sha": data.get("commit_sha"),
		"title": data.get("title"),
		"author_name": data.get("author_name"),
		"author_email": data.get("author_email"),
		"author_avatar_url": data.get("author_avatar_url"),
		"payload_json": json_dumps(data),
	}


def build_artifact_link_payload(
	*,
	artifact: str,
	target_doctype: str,
	target_name: str,
	link_source: str,
	extracted_key: str | None = None,
	is_primary: int = 0,
) -> dict[str, Any]:
	link_uid = make_uid(artifact, target_doctype, target_name, link_source, extracted_key)
	return {
		"link_uid": link_uid,
		"artifact": artifact,
		"target_doctype": target_doctype,
		"target_name": target_name,
		"project": frappe.db.get_value(target_doctype, target_name, "project"),
		"link_source": link_source,
		"extracted_key": extracted_key,
		"is_primary": is_primary,
	}


def write_event_log(payload: dict[str, Any]) -> str:
	event_uid = payload["event_uid"]
	existing = frappe.db.get_value("GitLab Event Log", {"event_uid": event_uid}, "name")

	if existing:
		frappe.get_doc("GitLab Event Log", existing).update(payload).save(ignore_permissions=True)
		return existing

	doc = frappe.get_doc({"doctype": "GitLab Event Log", **payload})
	doc.insert(ignore_permissions=True)
	return doc.name
