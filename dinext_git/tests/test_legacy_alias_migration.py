from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.patches.v0_0.migrate_legacy_jira_aliases import execute
from dinext_git.services.gitlab.matcher import resolve_key
from dinext_git.tests.test_utils import make_issue, make_project


class TestLegacyAliasMigration(FrappeTestCase):
	def test_patch_bootstraps_issue_identification_as_legacy_alias(self):
		project = make_project()
		issue_name = make_issue(project)
		issue = frappe.get_doc("Issue", issue_name)
		issue.append(
			"identification",
			{
				"type": frappe.db.get_value("Issue Identification Type", {}, "name"),
				"code": "JIRA-123",
			},
		)
		issue.save(ignore_permissions=True)

		execute()

		alias = frappe.db.get_value(
			"Development Key Alias",
			{"alias_value": "JIRA-123", "target_doctype": "Issue", "target_name": issue_name},
			["alias_type", "source_system"],
			as_dict=True,
		)
		self.assertTrue(alias)
		self.assertEqual(alias["alias_type"], "Jira Legacy Key")
		self.assertEqual(alias["source_system"], "Jira")

		resolved = resolve_key("JIRA-123")
		self.assertTrue(resolved)
		self.assertEqual(resolved["doctype"], "Issue")
		self.assertEqual(resolved["name"], issue_name)
