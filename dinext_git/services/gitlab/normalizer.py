"""Normalize GitLab webhook and reconciliation payloads into Dinext artifacts."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_git.services.gitlab.matcher import resolve_keys
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifacts_deleted,
	mark_branch_artifacts_deleted,
	upsert_artifact,
	upsert_artifact_link,
	write_event_log,
)
from dinext_git.services.gitlab.utils import (
	branch_name_from_ref,
	is_branch_ref,
	is_tag_ref,
	json_dumps,
	make_uid,
	project_id_from_payload,
	project_path_from_payload,
	tag_name_from_ref,
)


def log_event(
	*,
	instance: str,
	mapping: str | None,
	event_type: str,
	delivery_id: str | None,
	payload: dict[str, Any],
	status: str = "received",
	error_message: str | None = None,
) -> str:
	event_uid = make_uid(instance, mapping, event_type, delivery_id or payload.get("object_kind"), payload)
	return write_event_log(
		{
			"event_uid": event_uid,
			"gitlab_instance": instance,
			"project_mapping": mapping,
			"event_type": event_type,
			"delivery_id": delivery_id,
			"status": status,
			"payload_json": json_dumps(payload),
			"error_message": error_message,
			"processed_on": frappe.utils.now_datetime() if status != "received" else None,
		}
	)


def _link_resolved_keys(artifact_name: str, resolved_docs: list[dict[str, Any]], link_source: str) -> None:
	for idx, doc in enumerate(resolved_docs):
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact_name,
				target_doctype=doc["doctype"],
				target_name=doc["name"],
				link_source=link_source,
				extracted_key=doc["matched_key"],
				is_primary=1 if idx == 0 else 0,
			)
		)


def _is_zero_sha(value: str | None) -> bool:
	return bool(value) and set(value) == {"0"}


def _user_avatar(user: dict[str, Any] | None) -> str | None:
	if not user:
		return None
	return user.get("avatar_url")


def is_branch_delete_push(payload: dict[str, Any]) -> bool:
	if not is_branch_ref(payload.get("ref")):
		return False

	before = payload.get("before")
	after = payload.get("after")
	if before and not _is_zero_sha(before) and _is_zero_sha(after):
		return True

	checkout_sha = payload.get("checkout_sha")
	return _is_zero_sha(after) or _is_zero_sha(checkout_sha)


def is_tag_delete_push(payload: dict[str, Any]) -> bool:
	if not is_tag_ref(payload.get("ref")):
		return False

	before = payload.get("before")
	after = payload.get("after")
	if before and not _is_zero_sha(before) and _is_zero_sha(after):
		return True

	checkout_sha = payload.get("checkout_sha")
	return _is_zero_sha(after) or _is_zero_sha(checkout_sha)


def _release_external_id(payload: dict[str, Any]) -> str | None:
	tag = payload.get("tag") or payload.get("tag_name")
	if tag:
		return str(tag)
	release_id = payload.get("id")
	return str(release_id) if release_id not in (None, "") else None


def _release_link_texts(payload: dict[str, Any]) -> tuple[str | None, ...]:
	commit = payload.get("commit") or {}
	return (
		payload.get("tag") or payload.get("tag_name"),
		payload.get("name"),
		payload.get("description"),
		commit.get("message"),
		commit.get("title"),
	)


def normalize_push_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	ref_name = branch_name_from_ref(payload.get("ref"))
	if not ref_name:
		return {}

	if is_branch_delete_push(payload):
		deleted_branches = mark_branch_artifacts_deleted(
			instance=instance,
			mapping=mapping,
			external_id=ref_name,
			payload=payload,
			project_id=project_id_from_payload(payload),
			project_path=project_path_from_payload(payload),
		)
		return {
			"branch": deleted_branches[0] if deleted_branches else None,
			"branches": deleted_branches,
			"commits": [],
		}

	resolved = resolve_keys(ref_name, *(commit.get("message") for commit in payload.get("commits", [])))

	branch_artifact = upsert_artifact(
		build_artifact_payload(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=ref_name,
			data={
				"artifact_name": ref_name,
				"ref_name": ref_name,
				"artifact_status": "active",
				"web_url": payload.get("project", {}).get("web_url"),
				"commit_sha": payload.get("checkout_sha"),
				"title": payload.get("message"),
				"author_name": payload.get("user_name"),
				"author_email": payload.get("user_email"),
				"author_avatar_url": _user_avatar(payload.get("user")),
			},
		)
	)
	_link_resolved_keys(branch_artifact, resolved, "branch_name")

	commit_artifacts = []
	for commit in payload.get("commits", []):
		commit_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="commit",
				external_id=commit["id"],
				data={
					"artifact_name": commit.get("title"),
					"ref_name": ref_name,
					"artifact_status": "recorded",
					"web_url": commit.get("url"),
					"commit_sha": commit["id"],
					"title": commit.get("title"),
					"author_name": commit.get("author", {}).get("name"),
					"author_email": commit.get("author", {}).get("email"),
				},
			)
		)
		_link_resolved_keys(commit_artifact, resolve_keys(commit.get("message")), "commit_message")
		commit_artifacts.append(commit_artifact)

	return {"branch": branch_artifact, "commits": commit_artifacts}


def normalize_merge_request_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	attributes = payload.get("object_attributes") or {}
	resolved = resolve_keys(
		attributes.get("source_branch"),
		attributes.get("title"),
		attributes.get("description"),
	)
	artifact_name = upsert_artifact(
		build_artifact_payload(
			instance=instance,
			mapping=mapping,
			artifact_type="merge_request",
			external_id=str(attributes.get("id") or attributes.get("iid")),
			data={
				"external_iid": attributes.get("iid"),
				"artifact_name": attributes.get("title"),
				"ref_name": attributes.get("source_branch"),
				"artifact_status": attributes.get("state") or attributes.get("action"),
				"web_url": attributes.get("url"),
				"source_branch": attributes.get("source_branch"),
				"target_branch": attributes.get("target_branch"),
				"title": attributes.get("title"),
				"author_name": payload.get("user", {}).get("name"),
				"author_email": payload.get("user", {}).get("email"),
				"author_avatar_url": _user_avatar(payload.get("user")),
			},
		)
	)
	_link_resolved_keys(artifact_name, resolved, "mr_title")
	return {"merge_request": artifact_name}


def normalize_pipeline_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	attributes = payload.get("object_attributes") or {}
	mr = payload.get("merge_request") or {}
	resolved = resolve_keys(
		attributes.get("ref"),
		(payload.get("commit") or {}).get("message"),
		mr.get("title"),
	)
	pipeline_artifact = upsert_artifact(
		build_artifact_payload(
			instance=instance,
			mapping=mapping,
			artifact_type="pipeline",
			external_id=str(attributes.get("id") or attributes.get("iid")),
			data={
				"external_iid": attributes.get("iid"),
				"artifact_name": attributes.get("name") or f"Pipeline {attributes.get('id')}",
				"ref_name": attributes.get("ref"),
				"artifact_status": attributes.get("status"),
				"web_url": attributes.get("url"),
				"source_branch": mr.get("source_branch"),
				"target_branch": mr.get("target_branch"),
				"commit_sha": attributes.get("sha"),
				"title": (payload.get("commit") or {}).get("title"),
				"author_name": payload.get("user", {}).get("name"),
				"author_email": payload.get("user", {}).get("email"),
				"author_avatar_url": _user_avatar(payload.get("user")),
			},
		)
	)
	_link_resolved_keys(pipeline_artifact, resolved, "pipeline_ref")

	job_artifacts = []
	for build in payload.get("builds", []):
		job_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="job",
				external_id=str(build["id"]),
				data={
					"artifact_name": build.get("name"),
					"ref_name": attributes.get("ref"),
					"artifact_status": build.get("status"),
					"web_url": None,
					"commit_sha": attributes.get("sha"),
					"title": build.get("stage"),
					"author_name": (build.get("user") or {}).get("name"),
					"author_email": (build.get("user") or {}).get("email"),
					"author_avatar_url": _user_avatar(build.get("user")),
				},
			)
		)
		_link_resolved_keys(job_artifact, resolved, "pipeline_ref")
		job_artifacts.append(job_artifact)

		environment = build.get("environment") or {}
		if environment.get("name"):
			deployment_artifact = upsert_artifact(
				build_artifact_payload(
					instance=instance,
					mapping=mapping,
					artifact_type="deployment",
					external_id=f"{attributes.get('id')}::{build['id']}",
					data={
						"artifact_name": environment["name"],
						"ref_name": attributes.get("ref"),
						"artifact_status": build.get("status"),
						"web_url": None,
						"commit_sha": attributes.get("sha"),
						"title": build.get("stage"),
						"author_name": (build.get("user") or {}).get("name"),
						"author_email": (build.get("user") or {}).get("email"),
						"author_avatar_url": _user_avatar(build.get("user")),
					},
				)
			)
			_link_resolved_keys(deployment_artifact, resolved, "deployment_ref")

	return {"pipeline": pipeline_artifact, "jobs": job_artifacts}


def normalize_tag_push_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	tag_name = tag_name_from_ref(payload.get("ref"))
	if not tag_name:
		return {}

	if is_tag_delete_push(payload):
		deleted_tags = mark_artifacts_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="tag",
			external_id=tag_name,
			payload=payload,
			project_id=project_id_from_payload(payload),
			project_path=project_path_from_payload(payload),
			identity_fields={
				"artifact_name": tag_name,
				"ref_name": tag_name,
			},
		)
		return {"tag": deleted_tags[0] if deleted_tags else None, "tags": deleted_tags}

	commit_messages = [commit.get("message") for commit in payload.get("commits", []) if commit.get("message")]
	resolved = resolve_keys(tag_name, *commit_messages)
	commit_sha = payload.get("checkout_sha") or payload.get("after")
	tag_artifact = upsert_artifact(
		build_artifact_payload(
			instance=instance,
			mapping=mapping,
			artifact_type="tag",
			external_id=tag_name,
			data={
				"artifact_name": tag_name,
				"ref_name": tag_name,
				"artifact_status": "active",
				"web_url": (payload.get("project") or {}).get("web_url"),
				"commit_sha": commit_sha,
				"author_name": payload.get("user_name"),
				"author_email": payload.get("user_email"),
				"author_avatar_url": _user_avatar(payload.get("user")),
			},
		)
	)
	_link_resolved_keys(tag_artifact, resolved, "release_ref")
	return {"tag": tag_artifact}


def release_payload_from_api(release: dict[str, Any]) -> dict[str, Any]:
	"""Shape a GitLab REST release record for normalize_release_event."""
	commit = release.get("commit") if isinstance(release.get("commit"), dict) else {}
	links = release.get("_links") if isinstance(release.get("_links"), dict) else {}
	return {
		"id": release.get("tag_name"),
		"name": release.get("name"),
		"tag": release.get("tag_name"),
		"tag_name": release.get("tag_name"),
		"description": release.get("description"),
		"url": links.get("self"),
		"action": "create",
		"commit": {
			"id": commit.get("id"),
			"message": commit.get("message"),
			"title": commit.get("title"),
			"author": {
				"name": commit.get("author_name"),
				"email": commit.get("author_email"),
			},
		},
	}


def normalize_release_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	external_id = _release_external_id(payload)
	if not external_id:
		return {}

	action = (payload.get("action") or "").strip().lower()
	if action == "delete":
		deleted_releases = mark_artifacts_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="release",
			external_id=external_id,
			payload=payload,
			project_id=project_id_from_payload(payload),
			project_path=project_path_from_payload(payload),
			identity_fields={
				"artifact_name": payload.get("name") or external_id,
				"ref_name": external_id,
			},
		)
		return {"release": deleted_releases[0] if deleted_releases else None, "releases": deleted_releases}

	commit = payload.get("commit") or {}
	resolved = resolve_keys(*_release_link_texts(payload))
	release_name = payload.get("name") or external_id
	release_artifact = upsert_artifact(
		build_artifact_payload(
			instance=instance,
			mapping=mapping,
			artifact_type="release",
			external_id=external_id,
			data={
				"external_iid": str(payload.get("id")) if payload.get("id") not in (None, "") else None,
				"artifact_name": release_name,
				"ref_name": external_id,
				"artifact_status": "active",
				"web_url": payload.get("url"),
				"commit_sha": commit.get("id"),
				"title": commit.get("title") or release_name,
				"author_name": (commit.get("author") or {}).get("name") or payload.get("user_name"),
				"author_email": (commit.get("author") or {}).get("email") or payload.get("user_email"),
			},
		)
	)
	_link_resolved_keys(release_artifact, resolved, "release_ref")
	return {"release": release_artifact}
