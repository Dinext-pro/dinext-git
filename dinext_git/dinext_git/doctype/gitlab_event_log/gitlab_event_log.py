# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value


class GitLabEventLog(Document):
	def validate(self):
		if not self.event_uid:
			self.event_uid = "::".join(
				part
				for part in (
					self.gitlab_instance,
					self.project_mapping,
					self.event_type,
					self.delivery_id,
				)
				if part
			)
		ensure_unique_value(
			"GitLab Event Log",
			"event_uid",
			self.event_uid,
			name=self.name,
			label=_("Event UID"),
		)
