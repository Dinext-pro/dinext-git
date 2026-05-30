# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.constants import WORKFLOW_EVENTS, WORK_ITEM_DOCTYPES
from dinext_git.services.gitlab.workflow_fields import (
	DEFAULT_TARGET_FIELDNAME,
	get_field_allowed_values,
	get_workflow_target_fields,
	validate_field_value,
	validate_target_fieldname,
)


class DevelopmentWorkflowRule(Document):
	def validate(self):
		if self.target_doctype not in WORK_ITEM_DOCTYPES:
			frappe.throw(_("Unsupported workflow target doctype: {0}").format(self.target_doctype))
		if self.development_event not in WORKFLOW_EVENTS:
			frappe.throw(_("Unsupported development event: {0}").format(self.development_event))

		if not self.target_fieldname:
			self.target_fieldname = DEFAULT_TARGET_FIELDNAME

		validate_target_fieldname(self.target_doctype, self.target_fieldname)

		if not self.target_status:
			frappe.throw(_("Target value is required."))

		validate_field_value(
			self.target_doctype,
			self.target_fieldname,
			self.target_status,
			label=_("Target value"),
		)
		if self.only_when_current_status:
			validate_field_value(
				self.target_doctype,
				self.target_fieldname,
				self.only_when_current_status,
				label=_("Only when current value"),
			)


@frappe.whitelist()
def get_target_field_options(target_doctype: str) -> list[dict[str, str]]:
	frappe.only_for("System Manager")
	if target_doctype not in WORK_ITEM_DOCTYPES:
		frappe.throw(_("Unsupported workflow target doctype: {0}").format(target_doctype))
	return get_workflow_target_fields(target_doctype)


@frappe.whitelist()
def get_target_value_options(target_doctype: str, target_fieldname: str) -> list[str]:
	frappe.only_for("System Manager")
	if target_doctype not in WORK_ITEM_DOCTYPES:
		frappe.throw(_("Unsupported workflow target doctype: {0}").format(target_doctype))
	validate_target_fieldname(target_doctype, target_fieldname)
	return get_field_allowed_values(target_doctype, target_fieldname)
