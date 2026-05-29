# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value, validate_artifact_type


class DevelopmentArtifact(Document):
	def validate(self):
		validate_artifact_type(self.artifact_type)
		if not self.artifact_uid:
			self.artifact_uid = "::".join(
				part
				for part in (
					self.gitlab_instance,
					self.project_mapping,
					self.artifact_type,
					self.external_id,
				)
				if part
			)

		ensure_unique_value(
			"Development Artifact",
			"artifact_uid",
			self.artifact_uid,
			name=self.name,
			label=_("Artifact UID"),
		)

		existing = frappe.db.get_value(
			"Development Artifact",
			{
				"gitlab_instance": self.gitlab_instance,
				"project_mapping": self.project_mapping,
				"artifact_type": self.artifact_type,
				"external_id": self.external_id,
			},
			"name",
		)
		if existing and existing != self.name:
			frappe.throw(_("This GitLab artifact has already been recorded as {0}.").format(existing))
