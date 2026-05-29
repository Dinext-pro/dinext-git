"""Project normalized artifact truth back onto Task and Issue."""

from __future__ import annotations

from collections import Counter
from typing import Any

import frappe


def collect_work_item_summary(target_doctype: str, target_name: str) -> dict[str, Any]:
	links = frappe.get_all(
		"Development Artifact Link",
		filters={"target_doctype": target_doctype, "target_name": target_name},
		fields=["artifact", "link_source", "is_primary"],
	)
	if not links:
		return {
			"artifact_count": 0,
			"artifact_types": {},
			"last_merge_request": None,
			"last_pipeline_status": None,
			"last_deployment_status": None,
			"discrepancy_flags": [],
			"development_status": "not_started",
		}

	artifact_names = [link["artifact"] for link in links]
	artifacts = frappe.get_all(
		"Development Artifact",
		filters={"name": ["in", artifact_names]},
		fields=[
			"name",
			"artifact_type",
			"artifact_status",
			"artifact_name",
			"web_url",
			"ref_name",
			"modified",
		],
		order_by="modified desc",
	)
	type_counter = Counter(artifact["artifact_type"] for artifact in artifacts)
	last_merge_request = next((row for row in artifacts if row["artifact_type"] == "merge_request"), None)
	last_pipeline = next((row for row in artifacts if row["artifact_type"] == "pipeline"), None)
	last_deployment = next((row for row in artifacts if row["artifact_type"] == "deployment"), None)

	flags = []
	if type_counter.get("branch", 0) and not type_counter.get("merge_request", 0):
		flags.append("no_merge_request")
	if any(
		artifact["artifact_type"] == "pipeline" and artifact["artifact_status"] == "failed"
		for artifact in artifacts
	):
		flags.append("pipeline_failed")
	if type_counter.get("release", 0) and not any(
		artifact["artifact_type"] == "merge_request" and artifact["artifact_status"] == "merged"
		for artifact in artifacts
	):
		flags.append("release_without_merge")

	development_status = "not_started"
	if type_counter.get("branch", 0):
		development_status = "in_progress"
	if last_merge_request and last_merge_request.get("artifact_status") == "merged":
		development_status = "merged"
	if last_pipeline and last_pipeline.get("artifact_status") == "failed":
		development_status = "pipeline_failed"
	if last_deployment and last_deployment.get("artifact_status") == "success":
		development_status = "deployed"

	return {
		"artifact_count": len(artifacts),
		"artifact_types": dict(type_counter),
		"last_merge_request": last_merge_request,
		"last_pipeline_status": last_pipeline["artifact_status"] if last_pipeline else None,
		"last_deployment_status": last_deployment["artifact_status"] if last_deployment else None,
		"discrepancy_flags": flags,
		"development_status": development_status,
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
