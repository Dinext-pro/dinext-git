# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value, validate_branch_template


class GitLabProjectMapping(Document):
	def validate(self):
		validate_branch_template(self.branch_naming_template)
		if self.parenttype == "Project" and self.parent:
			self.project = self.parent
		self.gitlab_project_path = (self.gitlab_project_path or "").strip()
		self.gitlab_group_path = (self.gitlab_group_path or "").strip()
		if not self.webhook_callback_url:
			self.webhook_callback_url = f"{frappe.utils.get_url()}/api/method/dinext_git.api.gitlab_webhooks.receive"
		if self.is_default and not self.enabled:
			frappe.throw(_("The default GitLab project mapping must remain enabled."))

		project_name = self.project or self.parent
		if self.is_default and project_name:
			parent_doc = self.parent_doc or frappe.get_cached_doc("Project", project_name)
			default_rows = [
				row
				for row in (parent_doc.get("custom_git_project_mappings") or [])
				if row.name != self.name and row.enabled and row.is_default
			]
			if default_rows:
				frappe.throw(_("Only one default GitLab project mapping is allowed per project."))

		existing = frappe.db.get_value(
			"GitLab Project Mapping",
			{
				"gitlab_instance": self.gitlab_instance,
				"gitlab_project_path": self.gitlab_project_path,
			},
			"name",
		)
		if existing and existing != self.name:
			frappe.throw(_("This GitLab project path is already mapped as {0}.").format(existing))
