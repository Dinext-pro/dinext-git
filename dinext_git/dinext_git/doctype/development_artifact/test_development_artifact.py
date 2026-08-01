# Copyright (c) 2026, Dinext and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project

test_ignore = ["GitLab Instance", "GitLab Project Mapping", "Project"]


class TestDevelopmentArtifact(FrappeTestCase):
	def test_duplicate_artifact_is_rejected(self):
		project = make_project()
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		frappe.get_doc(
			{
				"doctype": "Development Artifact",
				"artifact_uid": "artifact-uid-1",
				"gitlab_instance": instance,
				"project_mapping": mapping,
				"artifact_type": "merge_request",
				"external_id": "42",
				"artifact_name": "MR 42",
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Development Artifact",
					"artifact_uid": "artifact-uid-2",
					"gitlab_instance": instance,
					"project_mapping": mapping,
					"artifact_type": "merge_request",
					"external_id": "42",
					"artifact_name": "MR 42 duplicate",
				}
			).insert(ignore_permissions=True)
