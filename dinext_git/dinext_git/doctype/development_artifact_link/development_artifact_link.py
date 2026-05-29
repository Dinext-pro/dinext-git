# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value, validate_link_source


class DevelopmentArtifactLink(Document):
	def validate(self):
		validate_link_source(self.link_source)
		if not self.link_uid:
			self.link_uid = "::".join(
				part
				for part in (
					self.artifact,
					self.target_doctype,
					self.target_name,
					self.link_source,
					self.extracted_key,
				)
				if part
			)
		ensure_unique_value(
			"Development Artifact Link",
			"link_uid",
			self.link_uid,
			name=self.name,
			label=_("Artifact link UID"),
		)
		if not self.project and self.target_doctype and self.target_name:
			self.project = frappe.db.get_value(self.target_doctype, self.target_name, "project")
