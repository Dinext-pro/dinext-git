"""Selectors for traceability exception reporting."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _

from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS


EXCEPTION_MODES = {
	"tasks_without_mr",
	"mr_without_task",
	"failed_pipelines",
	"stuck_reviews",
	"tasks_in_release_without_merge",
}


def run(mode: str, filters: dict | None = None) -> list[dict]:
	if mode not in EXCEPTION_MODES:
		frappe.throw(_("Unsupported traceability report mode: {0}").format(mode))

	filters = filters or {}
	links = frappe.get_all(
		"Development Artifact Link",
		fields=["artifact", "target_doctype", "target_name", "project"],
	)
	artifacts = frappe.get_all(
		"Development Artifact",
		fields=["name", "artifact_type", "artifact_status", "artifact_name", "web_url", "ref_name"],
	)
	artifacts = [row for row in artifacts if row.get("artifact_status") != DELETED_ARTIFACT_STATUS]
	artifact_map = {row["name"]: row for row in artifacts}
	links_by_target = defaultdict(list)
	links_by_artifact = defaultdict(list)
	for link in links:
		links_by_target[(link["target_doctype"], link["target_name"])].append(link)
		links_by_artifact[link["artifact"]].append(link)

	rows: list[dict] = []
	if mode == "tasks_without_mr":
		for task in frappe.get_all("Task", fields=["name", "subject", "project", "status"]):
			task_links = [link for link in links_by_target.get(("Task", task["name"]), []) if artifact_map.get(link["artifact"])]
			has_mr = any(artifact_map.get(link["artifact"], {}).get("artifact_type") == "merge_request" for link in task_links)
			if task_links and not has_mr:
				rows.append(task)
	elif mode == "mr_without_task":
		for artifact in artifacts:
			if artifact["artifact_type"] != "merge_request":
				continue
			if not links_by_artifact.get(artifact["name"]):
				rows.append(artifact)
	elif mode == "failed_pipelines":
		for artifact in artifacts:
			if artifact["artifact_type"] == "pipeline" and artifact["artifact_status"] == "failed":
				row = artifact.copy()
				targets = links_by_artifact.get(artifact["name"], [])
				if targets:
					row["target_doctype"] = targets[0]["target_doctype"]
					row["target_name"] = targets[0]["target_name"]
				rows.append(row)
	elif mode == "stuck_reviews":
		for artifact in artifacts:
			if artifact["artifact_type"] == "merge_request" and artifact["artifact_status"] in {"opened", "locked"}:
				rows.append(artifact)
	elif mode == "tasks_in_release_without_merge":
		for target, target_links in links_by_target.items():
			has_release = any(artifact_map.get(link["artifact"], {}).get("artifact_type") == "release" for link in target_links)
			has_merged_mr = any(
				artifact_map.get(link["artifact"], {}).get("artifact_type") == "merge_request"
				and artifact_map.get(link["artifact"], {}).get("artifact_status") == "merged"
				for link in target_links
			)
			if has_release and not has_merged_mr:
				rows.append({"target_doctype": target[0], "target_name": target[1]})

	return rows
