from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.reconcile import reconcile_mapping
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project


class TestReconciliation(FrappeTestCase):
	@patch("dinext_git.services.gitlab.reconcile.GitLabClient")
	def test_reconciliation_updates_mapping_watermarks(self, client_cls):
		project = make_project()
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		client = client_cls.return_value
		client.list_merge_requests.return_value = []
		client.list_pipelines.return_value = []

		result = reconcile_mapping(mapping)

		self.assertEqual(result["merge_requests"], 0)
		self.assertEqual(result["pipelines"], 0)

	def test_project_can_have_multiple_enabled_mappings(self):
		project = make_project()
		first_instance = make_gitlab_instance()
		second_instance = make_gitlab_instance()

		first_mapping = make_mapping(project, first_instance)
		second_mapping = make_mapping(project, second_instance)

		rows = frappe.get_all(
			"GitLab Project Mapping",
			filters={"parent": project, "parenttype": "Project", "enabled": 1},
			fields=["name"],
		)
		self.assertEqual({row["name"] for row in rows}, {first_mapping, second_mapping})
