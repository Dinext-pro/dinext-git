"""Apply configurable workflow transitions from development events."""

from __future__ import annotations

import frappe
from frappe import _

from dinext_git.services.gitlab.workflow_fields import DEFAULT_TARGET_FIELDNAME


def apply_rules(
	target_doctype: str,
	target_name: str,
	development_event: str,
	*,
	context: dict | None = None,
) -> list[str]:
	rules = _load_matching_rules(target_doctype, target_name, development_event)
	if not rules:
		return []

	applied: list[str] = []
	current_values: dict[str, object | None] = {}

	for rule in rules:
		if _apply_single_rule(rule, target_doctype, target_name, current_values, development_event, context):
			applied.append(rule["name"])
			if rule.get("stop_after_apply"):
				break

	return applied


def apply_rules_for_links(
	links: list[dict[str, str]],
	development_event: str,
	*,
	context: dict | None = None,
) -> dict[str, list[str]]:
	results: dict[str, list[str]] = {}
	for link in links:
		key = f"{link['target_doctype']}::{link['target_name']}"
		results[key] = apply_rules(
			link["target_doctype"],
			link["target_name"],
			development_event,
			context=context,
		)
	return results


def _load_matching_rules(target_doctype: str, target_name: str, development_event: str) -> list[dict]:
	project = frappe.db.get_value(target_doctype, target_name, "project")
	rules = frappe.get_all(
		"Development Workflow Rule",
		filters={
			"target_doctype": target_doctype,
			"development_event": development_event,
			"enabled": 1,
		},
		fields=[
			"name",
			"project",
			"target_fieldname",
			"target_status",
			"only_when_current_status",
			"stop_after_apply",
		],
		order_by="priority asc, modified asc",
	)
	if not rules:
		return []

	filtered = []
	for rule in rules:
		rule_project = rule.get("project")
		if rule_project and rule_project != project:
			continue
		filtered.append(rule)
	return filtered


def _apply_single_rule(
	rule: dict,
	target_doctype: str,
	target_name: str,
	current_values: dict[str, object | None],
	development_event: str,
	context: dict | None,
) -> bool:
	fieldname = rule.get("target_fieldname") or DEFAULT_TARGET_FIELDNAME
	target_value = rule.get("target_status")
	expected = rule.get("only_when_current_status")

	if fieldname not in current_values:
		if not frappe.get_meta(target_doctype).has_field(fieldname):
			_log_workflow_failure(
				rule=rule,
				target_doctype=target_doctype,
				target_name=target_name,
				development_event=development_event,
				fieldname=fieldname,
				target_value=target_value,
				message=f"{target_doctype} has no field {fieldname}",
			)
			return False
		current_values[fieldname] = frappe.db.get_value(target_doctype, target_name, fieldname)

	current_value = current_values[fieldname]
	if expected and current_value != expected:
		return False

	if current_value == target_value:
		return True

	try:
		doc = frappe.get_doc(target_doctype, target_name)
		doc.set(fieldname, target_value)
		doc.flags.ignore_permissions = True
		doc.save()
		current_values[fieldname] = target_value
		return True
	except Exception as exc:
		_log_workflow_failure(
			rule=rule,
			target_doctype=target_doctype,
			target_name=target_name,
			development_event=development_event,
			fieldname=fieldname,
			target_value=target_value,
			message=str(exc),
			exc=exc,
		)
		return False


def _log_workflow_failure(
	*,
	rule: dict,
	target_doctype: str,
	target_name: str,
	development_event: str,
	fieldname: str,
	target_value: str,
	message: str,
	exc: Exception | None = None,
) -> None:
	details = {
		"rule": rule.get("name"),
		"target_doctype": target_doctype,
		"target_name": target_name,
		"development_event": development_event,
		"fieldname": fieldname,
		"target_value": target_value,
		"message": message,
		"context": exc,
	}
	frappe.log_error(
		title=_("Dinext Git workflow rule failed"),
		message=frappe.as_json(details, indent=2),
	)
