# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value, validate_alias_value


class DevelopmentKeyAlias(Document):
	def validate(self):
		self.alias_value = validate_alias_value(self.alias_value)
		if self.target_doctype == "Task":
			task_project = frappe.db.get_value("Task", self.target_name, "project")
			self.project = self.project or task_project
		elif self.target_doctype == "Issue":
			issue_project = frappe.db.get_value("Issue", self.target_name, "project")
			self.project = self.project or issue_project

		filters = {"alias_type": self.alias_type, "project": self.project or ["is", "not set"]}
		existing = frappe.get_all(
			"Development Key Alias",
			filters={"alias_value": self.alias_value, "alias_type": self.alias_type, "name": ["!=", self.name]},
			fields=["name", "target_doctype", "target_name", "project"],
		)
		for row in existing:
			same_scope = (row.get("project") or "") == (self.project or "")
			if same_scope and (row["target_doctype"], row["target_name"]) != (self.target_doctype, self.target_name):
				frappe.throw(
					_("Alias {0} already points to {1} {2} in the same scope.").format(
						self.alias_value,
						row["target_doctype"],
						row["target_name"],
					)
				)

		ensure_unique_value(
			"Development Key Alias",
			"alias_value",
			self.alias_value,
			name=self.name,
			filters={"alias_type": self.alias_type, "target_doctype": self.target_doctype, "target_name": self.target_name},
			label="Alias",
		)
