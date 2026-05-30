"""Meta-driven helpers for Development Workflow Rule field configuration."""

from __future__ import annotations

import frappe
from frappe import _

WORKFLOW_TARGET_FIELD_TYPES = ("Select", "Link")
DEFAULT_TARGET_FIELDNAME = "status"


def get_workflow_target_fields(target_doctype: str) -> list[dict[str, str]]:
	meta = frappe.get_meta(target_doctype)
	fields: list[dict[str, str]] = []
	for df in meta.fields:
		if df.fieldtype not in WORKFLOW_TARGET_FIELD_TYPES:
			continue
		if df.hidden:
			continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
				"options": df.options or "",
			}
		)
	return fields


def get_field_meta(target_doctype: str, fieldname: str):
	meta = frappe.get_meta(target_doctype)
	return meta.get_field(fieldname)


def get_field_allowed_values(target_doctype: str, fieldname: str, *, limit: int = 200) -> list[str]:
	df = get_field_meta(target_doctype, fieldname)
	if not df:
		return []

	if df.fieldtype == "Select":
		return [row.strip() for row in (df.options or "").split("\n") if row.strip()]

	if df.fieldtype == "Link" and df.options:
		return frappe.get_all(df.options, pluck="name", limit=limit, order_by="modified desc")

	return []


def validate_target_fieldname(target_doctype: str, fieldname: str) -> None:
	if not fieldname:
		frappe.throw(_("Target field is required."))

	df = get_field_meta(target_doctype, fieldname)
	if not df:
		frappe.throw(_("Field {0} does not exist on {1}.").format(fieldname, target_doctype))
	if df.fieldtype not in WORKFLOW_TARGET_FIELD_TYPES:
		frappe.throw(
			_("Field {0} on {1} must be Select or Link.").format(fieldname, target_doctype)
		)


def validate_field_value(target_doctype: str, fieldname: str, value: str, *, label: str) -> None:
	if not value:
		return

	df = get_field_meta(target_doctype, fieldname)
	if not df:
		frappe.throw(_("Field {0} does not exist on {1}.").format(fieldname, target_doctype))

	if df.fieldtype == "Select":
		allowed = set(get_field_allowed_values(target_doctype, fieldname))
		if value not in allowed:
			frappe.throw(_("{0} {1} does not exist on {2}.").format(label, value, target_doctype))
		return

	if df.fieldtype == "Link" and df.options:
		if not frappe.db.exists(df.options, value):
			frappe.throw(_("{0} {1} does not exist in {2}.").format(label, value, df.options))
