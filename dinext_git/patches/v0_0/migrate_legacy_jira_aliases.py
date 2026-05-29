from __future__ import annotations

import frappe

from dinext_git.services.gitlab.matcher import LEGACY_KEY_PATTERN


def _iter_issue_legacy_codes() -> list[tuple[str, str | None, str]]:
	issues = frappe.get_all("Issue", fields=["name", "project"])
	rows: list[tuple[str, str | None, str]] = []
	for issue in issues:
		doc = frappe.get_doc("Issue", issue["name"])
		for row in doc.get("identification") or []:
			code = (row.get("code") or "").strip().upper()
			if not code or not LEGACY_KEY_PATTERN.fullmatch(code):
				continue
			rows.append((issue["name"], issue.get("project"), code))
	return rows


def _upsert_alias(issue_name: str, project: str | None, alias_value: str) -> None:
	existing = frappe.db.get_value(
		"Development Key Alias",
		{"alias_value": alias_value},
		["name", "target_doctype", "target_name"],
		as_dict=True,
	)
	if existing:
		if existing["target_doctype"] == "Issue" and existing["target_name"] == issue_name:
			return
		frappe.logger("dinext_git.patch").warning(
			"Skipping legacy alias %s because it already points to %s %s",
			alias_value,
			existing["target_doctype"],
			existing["target_name"],
		)
		return

	frappe.get_doc(
		{
			"doctype": "Development Key Alias",
			"alias_value": alias_value,
			"alias_type": "Jira Legacy Key",
			"target_doctype": "Issue",
			"target_name": issue_name,
			"project": project,
			"enabled": 1,
			"is_canonical": 0,
			"source_system": "Jira",
			"notes": "Bootstrapped from Issue.identification during Dinext Git migration.",
		}
	).insert(ignore_permissions=True)


def execute():
	"""Migrate legacy Jira-style identifiers from Issue.identification into the alias registry."""
	for issue_name, project, alias_value in _iter_issue_legacy_codes():
		_upsert_alias(issue_name, project, alias_value)
