"""Normalize GitLab webhook and reconciliation payloads into Dinext artifacts."""

from __future__ import annotations

from typing import Any

import frappe

from dinext_git.services.gitlab.matcher import resolve_keys
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
	write_event_log,
)
from dinext_git.services.gitlab.utils import json_dumps, make_uid


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


def is_branch_delete_push(payload: dict[str, Any]) -> bool:
	after = payload.get("after")
	checkout_sha = payload.get("checkout_sha")
	return _is_zero_sha(after) or _is_zero_sha(checkout_sha)


def normalize_push_event(instance: str, mapping: str | None, payload: dict[str, Any]) -> dict[str, Any]:
	ref_name = (payload.get("ref") or "").split("/")[-1]
	if is_branch_delete_push(payload):
		branch_artifact = mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=ref_name,
			payload=payload,
		)
		return {"branch": branch_artifact, "commits": []}

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
				},
			)
		)
		_link_resolved_keys(job_artifact, resolved, "pipeline_ref")
		job_artifacts.append(job_artifact)

		if build.get("environment", {}).get("name"):
			deployment_artifact = upsert_artifact(
				build_artifact_payload(
					instance=instance,
					mapping=mapping,
					artifact_type="deployment",
					external_id=f"{attributes.get('id')}::{build['id']}",
					data={
						"artifact_name": build["environment"]["name"],
						"ref_name": attributes.get("ref"),
						"artifact_status": build.get("status"),
						"web_url": None,
						"commit_sha": attributes.get("sha"),
						"title": build.get("stage"),
						"author_name": (build.get("user") or {}).get("name"),
						"author_email": (build.get("user") or {}).get("email"),
					},
				)
			)
			_link_resolved_keys(deployment_artifact, resolved, "deployment_ref")

	return {"pipeline": pipeline_artifact, "jobs": job_artifacts}
