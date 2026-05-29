from __future__ import annotations

import frappe


def execute():
	"""Backfill Project child-table linkage and a single default mapping per project."""
	project_groups: dict[str, list[dict]] = {}
	for row in frappe.get_all(
		"GitLab Project Mapping",
		fields=["name", "project", "parent", "parenttype", "idx", "enabled", "is_default", "creation"],
		order_by="creation asc",
	):
		project = row.get("parent") or row.get("project")
		if not project:
			continue
		project_groups.setdefault(project, []).append(row)

	for project, rows in project_groups.items():
		enabled_rows = [row for row in rows if row.get("enabled")]
		default_name = next((row["name"] for row in enabled_rows if row.get("is_default")), None)
		if not default_name and len(enabled_rows) == 1:
			default_name = enabled_rows[0]["name"]
		if not default_name and enabled_rows:
			default_name = enabled_rows[0]["name"]

		for index, row in enumerate(rows, start=1):
			updates = {
				"project": project,
				"parent": project,
				"parenttype": "Project",
				"parentfield": "custom_git_project_mappings",
				"idx": index,
			}
			if row.get("enabled"):
				updates["is_default"] = 1 if row["name"] == default_name else 0
			else:
				updates["is_default"] = 0
			frappe.db.set_value("GitLab Project Mapping", row["name"], updates, update_modified=False)
