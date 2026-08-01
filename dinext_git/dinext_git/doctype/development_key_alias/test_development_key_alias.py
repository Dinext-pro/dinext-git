# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.tests.test_utils import make_issue, make_project

test_ignore = ["Issue", "Project"]


class TestDevelopmentKeyAlias(FrappeTestCase):
	def test_same_alias_cannot_point_to_two_work_items_in_same_scope(self):
		project = make_project()
		issue_one = make_issue(project)
		issue_two = make_issue(project)

		frappe.get_doc(
			{
				"doctype": "Development Key Alias",
				"alias_value": "LEGACY-77",
				"alias_type": "Jira Legacy Key",
				"target_doctype": "Issue",
				"target_name": issue_one,
				"project": project,
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Development Key Alias",
					"alias_value": "LEGACY-77",
					"alias_type": "Jira Legacy Key",
					"target_doctype": "Issue",
					"target_name": issue_two,
					"project": project,
				}
			).insert(ignore_permissions=True)
