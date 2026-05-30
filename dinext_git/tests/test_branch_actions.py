from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import remove_encrypted_password

from dinext_git.services.gitlab.branch_actions import create_branch, preview_branch
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestBranchActions(FrappeTestCase):
	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_updates_summary_and_applies_workflow_rule(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		frappe.get_doc(
			{
				"doctype": "Development Workflow Rule",
				"target_doctype": "Task",
				"project": project,
				"development_event": "branch_created",
				"target_status": "Working",
				"only_when_current_status": "Open",
				"priority": 10,
				"enabled": 1,
				"stop_after_apply": 1,
			}
		).insert(ignore_permissions=True)

		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/sample",
			"commit": {"id": "abc123"},
		}
		frappe.db.set_value("User", "Administrator", "custom_gitlab_branch_api_token", "user-token")

		result = create_branch("Task", task)

		self.assertTrue(result["artifact"])
		self.assertEqual(frappe.db.get_value("Task", task, "custom_git_development_status"), "in_progress")
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Working")
		client_cls.assert_called_once_with(instance, api_token="user-token")

	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_persists_long_gitlab_web_url(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		long_url = f"https://gitlab.example.com/dinext/project/-/tree/feature/{'a' * 180}"
		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": long_url,
			"commit": {"id": "abc123"},
		}
		frappe.db.set_value("User", "Administrator", "custom_gitlab_branch_api_token", "user-token")

		result = create_branch("Task", task)

		self.assertTrue(result["artifact"])
		self.assertEqual(frappe.db.get_value("Development Artifact", result["artifact"], "web_url"), long_url)

	def test_preview_branch_uses_selected_default_mapping(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		default_mapping = make_mapping(project, instance)
		override_mapping = make_mapping(project, instance)
		project_doc = frappe.get_doc("Project", project)
		for row in project_doc.custom_git_project_mappings:
			row.is_default = 1 if row.name == default_mapping else 0
		project_doc.save(ignore_permissions=True)

		default_preview = preview_branch("Task", task)
		override_preview = preview_branch("Task", task, override_mapping)

		self.assertEqual(default_preview["mapping"]["name"], default_mapping)
		self.assertEqual(override_preview["mapping"]["name"], override_mapping)

	def test_create_branch_requires_user_token(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		frappe.db.set_value("User", "Administrator", "custom_gitlab_branch_api_token", "")
		remove_encrypted_password("User", "Administrator", "custom_gitlab_branch_api_token")

		self.assertRaises(frappe.ValidationError, create_branch, "Task", task)
