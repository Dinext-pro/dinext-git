# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.constants import WORKFLOW_EVENTS, WORK_ITEM_DOCTYPES


class DevelopmentWorkflowRule(Document):
	def validate(self):
		if self.target_doctype not in WORK_ITEM_DOCTYPES:
			frappe.throw(_("Unsupported workflow target doctype: {0}").format(self.target_doctype))
		if self.development_event not in WORKFLOW_EVENTS:
			frappe.throw(_("Unsupported development event: {0}").format(self.development_event))
		if not self.target_status:
			frappe.throw(_("Target status is required."))

		status_options = frappe.get_meta(self.target_doctype).get_field("status").options or ""
		available_statuses = {row.strip() for row in status_options.split("\n") if row.strip()}
		if self.target_status not in available_statuses:
			frappe.throw(
				_("Status {0} does not exist on {1}.").format(self.target_status, self.target_doctype)
			)
		if self.only_when_current_status and self.only_when_current_status not in available_statuses:
			frappe.throw(
				_("Current-status guard {0} does not exist on {1}.").format(
					self.only_when_current_status,
					self.target_doctype,
				)
			)
