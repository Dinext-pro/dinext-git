# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

from dinext_git.services.gitlab.validators import ensure_unique_value


class GitLabInstance(Document):
	def validate(self):
		self.base_url = (self.base_url or "").strip().rstrip("/")
		parsed = urlparse(self.base_url)
		if parsed.scheme not in {"http", "https"} or not parsed.netloc:
			frappe.throw(_("Base URL must be a full GitLab URL, for example https://gitlab.example.com"))

		ensure_unique_value(
			"GitLab Instance",
			"base_url",
			self.base_url,
			name=self.name,
			label=_("GitLab base URL"),
		)
