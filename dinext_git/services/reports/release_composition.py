"""Release composition selectors derived from normalized artifacts."""

from __future__ import annotations

from collections import defaultdict

import frappe

from dinext_git.services.gitlab.constants import DELETED_ARTIFACT_STATUS, RELEASE_SIDE_ARTIFACT_TYPES


def run(filters: dict | None = None) -> list[dict]:
	filters = filters or {}
	links = frappe.get_all(
		"Development Artifact Link",
		fields=["artifact", "target_doctype", "target_name", "project"],
	)
	artifacts = frappe.get_all(
		"Development Artifact",
		fields=[
			"name",
			"artifact_type",
			"artifact_status",
			"artifact_name",
			"web_url",
			"ref_name",
		],
		order_by="modified desc",
	)
	artifacts = [row for row in artifacts if row.get("artifact_status") != DELETED_ARTIFACT_STATUS]
	artifact_map = {row["name"]: row for row in artifacts}
	links_by_target = defaultdict(list)
	for link in links:
		links_by_target[(link["target_doctype"], link["target_name"])].append(link)

	rows: list[dict] = []
	for target, target_links in links_by_target.items():
		release_artifacts = [
			artifact_map[link["artifact"]]
			for link in target_links
			if artifact_map.get(link["artifact"], {}).get("artifact_type") in RELEASE_SIDE_ARTIFACT_TYPES
		]
		if not release_artifacts:
			continue

		merge_artifacts = [
			artifact_map[link["artifact"]]
			for link in target_links
			if artifact_map.get(link["artifact"], {}).get("artifact_type") == "merge_request"
		]
		if not any(artifact["artifact_status"] == "merged" for artifact in merge_artifacts):
			continue

		rows.append(
			{
				"target_doctype": target[0],
				"target_name": target[1],
				"release_names": ", ".join(sorted({artifact["artifact_name"] for artifact in release_artifacts if artifact["artifact_name"]})),
				"deployment_statuses": ", ".join(
					sorted(
						{
							artifact["artifact_status"]
							for artifact in release_artifacts
							if artifact["artifact_type"] == "deployment" and artifact["artifact_status"]
						}
					)
				),
				"release_urls": ", ".join(sorted({artifact["web_url"] for artifact in release_artifacts if artifact["web_url"]})),
			}
		)

	return rows
