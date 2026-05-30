from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.password import remove_encrypted_password

from dinext_git.services.gitlab.branch_actions import (
	create_branch,
	get_branch_dialog_options,
	preview_branch,
)
from dinext_git.services.gitlab.utils import slugify_fragment
from dinext_git.services.gitlab.constants import DEVELOPMENT_STATUS_IN_PROGRESS
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


def _mock_branch_lookup(base_branch: str = "develop"):
	def side_effect(project_id, branch_name):
		if branch_name == base_branch:
			return {"name": base_branch}
		return None

	return side_effect


class TestBranchActions(FrappeTestCase):
	def setUp(self):
		frappe.db.set_value("User", "Administrator", "custom_gitlab_branch_api_token", "user-token")

	def test_preview_branch_defaults_slug_from_subject(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		subject = frappe.db.get_value("Task", task, "subject")

		preview = preview_branch("Task", task)

		self.assertEqual(preview["slug_fragment"], slugify_fragment(subject))
		self.assertEqual(preview["branch_name"], f"feature/{task}-{slugify_fragment(subject)}")
		self.assertEqual(preview["branch_template"], "feature/{key}-{slug}")
		self.assertEqual(preview["base_branch"], "develop")

	def test_preview_branch_uses_branch_template_override(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		preview = preview_branch("Task", task, branch_template="hotfix/{key}-{slug}")

		self.assertEqual(preview["branch_template"], "hotfix/{key}-{slug}")
		self.assertTrue(preview["branch_name"].startswith(f"hotfix/{task}-"))

	@patch("dinext_git.services.gitlab.branch_actions.list_available_base_branches")
	def test_get_branch_dialog_options_returns_template_base_and_branches(self, list_branches_mock):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		list_branches_mock.return_value = ["develop", "main"]

		options = get_branch_dialog_options("Task", task, mapping)

		self.assertEqual(options["mapping"]["name"], mapping)
		self.assertEqual(options["branch_template"], "feature/{key}-{slug}")
		self.assertEqual(options["base_branch"], "develop")
		self.assertEqual(options["available_base_branches"], ["develop", "main"])
		self.assertEqual(options["branch_preview"]["branch_name"], options["branch_preview"]["branch_name"])

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
				"target_fieldname": "status",
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
		client.get_branch.side_effect = _mock_branch_lookup()
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/sample",
			"commit": {"id": "abc123"},
		}

		result = create_branch("Task", task)

		self.assertTrue(result["artifact"])
		self.assertEqual(
			frappe.db.get_value("Task", task, "custom_git_development_status"),
			DEVELOPMENT_STATUS_IN_PROGRESS,
		)
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Working")
		client_cls.assert_called_once_with(instance, api_token="user-token")
		client.create_branch.assert_called_once()
		self.assertEqual(client.create_branch.call_args.args[2], "develop")

	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_uses_selected_base_branch(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.get_branch.side_effect = _mock_branch_lookup(base_branch="main")
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/sample",
			"commit": {"id": "abc123"},
		}

		create_branch("Task", task, base_branch="main")

		client.create_branch.assert_called_once()
		self.assertEqual(client.create_branch.call_args.args[2], "main")

	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_allows_multiple_branches_for_same_work_item(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.get_branch.side_effect = _mock_branch_lookup()
		client.create_branch.side_effect = [
			{
				"name": f"feature/{task}-sample",
				"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/sample",
				"commit": {"id": "abc123"},
			},
			{
				"name": f"feature/{task}-hotfix",
				"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/hotfix",
				"commit": {"id": "def456"},
			},
		]

		first = create_branch("Task", task, branch_template="feature/{key}-sample")
		second = create_branch("Task", task, branch_template="feature/{key}-hotfix")

		self.assertNotEqual(first["artifact"], second["artifact"])
		self.assertNotEqual(first["artifact_uid"], second["artifact_uid"])
		self.assertEqual(first["branch_name"], f"feature/{task}-sample")
		self.assertEqual(second["branch_name"], f"feature/{task}-hotfix")

		links = frappe.get_all(
			"Development Artifact Link",
			filters={"target_doctype": "Task", "target_name": task},
			fields=["artifact"],
		)
		self.assertEqual(len(links), 2)

		artifacts = frappe.get_all(
			"Development Artifact",
			filters={"name": ["in", [row["artifact"] for row in links]]},
			fields=["ref_name"],
			order_by="ref_name asc",
		)
		self.assertEqual(
			[row["ref_name"] for row in artifacts],
			[f"feature/{task}-hotfix", f"feature/{task}-sample"],
		)

	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_rejects_duplicate_branch_name(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.get_branch.side_effect = _mock_branch_lookup()
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": "https://gitlab.example.com/dinext/project/-/tree/feature/sample",
			"commit": {"id": "abc123"},
		}

		create_branch("Task", task, branch_template="feature/{key}-sample")

		with self.assertRaisesRegex(frappe.ValidationError, "already linked"):
			create_branch("Task", task, branch_template="feature/{key}-sample")

	@patch("dinext_git.services.gitlab.branch_actions.GitLabClient")
	def test_create_branch_persists_long_gitlab_web_url(self, client_cls):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		make_mapping(project, instance)

		long_url = f"https://gitlab.example.com/dinext/project/-/tree/feature/{'a' * 180}"
		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.get_branch.side_effect = _mock_branch_lookup()
		client.create_branch.return_value = {
			"name": f"feature/{task}-sample",
			"web_url": long_url,
			"commit": {"id": "abc123"},
		}

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
