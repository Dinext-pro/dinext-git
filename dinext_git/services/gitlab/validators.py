"""Validation helpers for Dinext Git DocTypes."""

from __future__ import annotations

import re

import frappe
from frappe import _

from dinext_git.services.gitlab.constants import ARTIFACT_TYPES, LINK_SOURCES


GIT_REF_INVALID_PATTERN = re.compile(r"(^/|//|[ ~^:?*\[]|\.lock$|@$|\\)")


def ensure_unique_value(
	doctype: str,
	fieldname: str,
	value: str | None,
	*,
	name: str | None = None,
	filters: dict | None = None,
	label: str | None = None,
) -> None:
	if not value:
		return

	query_filters = {fieldname: value}
	if filters:
		query_filters.update(filters)

	existing_name = frappe.db.get_value(doctype, query_filters, "name")
	if existing_name and existing_name != name:
		frappe.throw(_("{0} {1} is already in use.").format(label or fieldname, value))


def validate_branch_template(template: str | None) -> None:
	template = template or ""
	if "{key}" not in template:
		frappe.throw(_("Branch naming template must include {key}."))

	candidate = (
		template.replace("{key}", "TASK-2026-00001")
		.replace("{slug}", "sample-work-item")
		.replace("{doctype}", "task")
		.replace("{type_slug}", "feature")
		.replace("{project}", "sample-project")
	)
	if "{" in candidate or "}" in candidate:
		frappe.throw(_("Branch naming template contains unsupported placeholders."))
	if GIT_REF_INVALID_PATTERN.search(candidate) or candidate.endswith(".") or candidate.endswith("/"):
		frappe.throw(_("Branch naming template produces an invalid Git ref."))


def validate_alias_value(alias_value: str | None) -> str:
	if not alias_value:
		frappe.throw(_("Alias value is required."))
	return alias_value.strip().upper()


def validate_artifact_type(artifact_type: str | None) -> None:
	if artifact_type not in ARTIFACT_TYPES:
		frappe.throw(_("Unsupported artifact type: {0}").format(artifact_type))


def validate_link_source(link_source: str | None) -> None:
	if link_source not in LINK_SOURCES:
		frappe.throw(_("Unsupported artifact link source: {0}").format(link_source))
