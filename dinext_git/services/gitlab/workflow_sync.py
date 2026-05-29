"""Apply configurable workflow transitions from development events."""

from __future__ import annotations

import frappe
from frappe import _


def apply_rules(target_doctype: str, target_name: str, development_event: str, *, context: dict | None = None) -> list[str]:
	rules = frappe.get_all(
		"Development Workflow Rule",
		filters={
			"target_doctype": target_doctype,
			"development_event": development_event,
			"enabled": 1,
		},
		fields=["name", "target_status", "only_when_current_status", "stop_after_apply"],
		order_by="priority asc, modified asc",
	)
	applied = []
	current_status = frappe.db.get_value(target_doctype, target_name, "status")
	for rule in rules:
		expected = rule.get("only_when_current_status")
		if expected and current_status != expected:
			continue

		if not frappe.db.has_column(target_doctype, "status"):
			frappe.log_error(title=_("Dinext Git workflow sync"), message=f"{target_doctype} has no status column")
			break

		frappe.db.set_value(target_doctype, target_name, "status", rule["target_status"])
		applied.append(rule["name"])
		current_status = rule["target_status"]
		if rule.get("stop_after_apply"):
			break

	return applied
