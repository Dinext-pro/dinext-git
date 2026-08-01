# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.tests.test_utils import make_gitlab_instance, make_project

test_ignore = ["GitLab Instance", "Project"]


class TestGitLabProjectMapping(FrappeTestCase):
	def test_invalid_branch_template_without_key_is_rejected(self):
		project = make_project()
		instance = make_gitlab_instance()

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "GitLab Project Mapping",
					"project": project,
					"gitlab_instance": instance,
					"gitlab_project_path": "dinext/project",
					"branch_naming_template": "feature/{slug}",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
