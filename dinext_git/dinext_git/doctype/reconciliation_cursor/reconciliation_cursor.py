# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value, validate_artifact_type


class ReconciliationCursor(Document):
	def validate(self):
		validate_artifact_type(self.artifact_type)
		existing = frappe.db.get_value(
			"Reconciliation Cursor",
			{
				"project_mapping": self.project_mapping,
				"artifact_type": self.artifact_type,
			},
			"name",
		)
		if existing and existing != self.name:
			frappe.throw(
				_("A reconciliation cursor already exists for {0} / {1}.").format(
					self.project_mapping,
					self.artifact_type,
				)
			)
