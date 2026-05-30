from __future__ import annotations

from unittest.mock import patch
from urllib.parse import urlparse

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.api.development_panel import get_panel
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.tests.test_utils import (
	add_type_visibility_rule,
	make_gitlab_instance,
	make_issue,
	make_issue_type,
	make_mapping,
	make_project,
	make_task,
	make_task_type,
)


class TestDevelopmentPanelPayload(FrappeTestCase):
	def setUp(self):
		frappe.db.set_value("User", "Administrator", "custom_gitlab_branch_api_token", "user-token")
		patcher = patch(
			"dinext_git.services.gitlab.branch_actions.list_available_base_branches",
			return_value=["develop", "main"],
		)
		self.list_branches_mock = patcher.start()
		self.addCleanup(patcher.stop)

	def test_panel_hides_gitlab_tab_without_project_mapping(self):
		project = make_project()
		task = make_task(project)

		payload = get_panel("Task", task)

		self.assertFalse(payload["show_gitlab_tab"])

	def test_panel_groups_linked_artifacts_by_mapping(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		first_mapping = make_mapping(project, instance)
		second_mapping = make_mapping(project, instance)

		first_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=first_mapping,
				artifact_type="merge_request",
				external_id="11",
				data={"artifact_name": "MR 11", "artifact_status": "opened", "web_url": "https://gitlab.example.com/mr/11"},
			)
		)
		second_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=second_mapping,
				artifact_type="pipeline",
				external_id="22",
				data={"artifact_name": "Pipeline 22", "artifact_status": "failed", "web_url": "https://gitlab.example.com/pipeline/22"},
			)
		)
		upsert_artifact_link(build_artifact_link_payload(artifact=first_artifact, target_doctype="Task", target_name=task, link_source="mr_title"))
		upsert_artifact_link(build_artifact_link_payload(artifact=second_artifact, target_doctype="Task", target_name=task, link_source="pipeline_ref"))

		payload = get_panel("Task", task)
		base_url = frappe.db.get_value("GitLab Instance", instance, "base_url")
		self.assertTrue(payload["show_gitlab_tab"])
		self.assertEqual(len(payload["grouped_artifacts"]), 2)
		for mapping_name, group in payload["grouped_artifacts"].items():
			project_path = frappe.db.get_value("GitLab Project Mapping", mapping_name, "gitlab_project_path")
			self.assertEqual(group["default_base_branch"], "develop")
			self.assertEqual(group["gitlab_project_url"], f"{base_url}/{project_path}/-/tree/develop")
		self.assertIn("summary", payload)
		self.assertTrue(payload["can_create_branch"])
		self.assertEqual(payload["branch_preview"]["base_branch"], "develop")
		self.assertEqual(payload["default_branch_template"], "feature/{key}-{slug}")
		self.assertEqual(payload["default_base_branch"], "develop")
		self.assertEqual(payload["available_base_branches"], ["develop", "main"])
		self.assertEqual(payload["summary"]["development_status_label"], "Pipeline failed")
		self.assertEqual(len(payload["branch_mapping_options"]), 2)
		self.assertTrue(payload["show_branch_mapping_details"])
		self._assert_branch_mapping_option_metadata(payload["branch_mapping_options"], instance)

	def _assert_branch_mapping_option_metadata(self, mapping_options, instance_name):
		base_url = frappe.db.get_value("GitLab Instance", instance_name, "base_url")
		expected_host = urlparse(base_url).netloc
		for row in mapping_options:
			project_path = frappe.db.get_value("GitLab Project Mapping", row["name"], "gitlab_project_path")
			self.assertEqual(row["gitlab_project_path"], project_path)
			self.assertEqual(row["gitlab_instance"], instance_name)
			self.assertEqual(row["gitlab_instance_host"], expected_host)

	def test_panel_allows_branch_creation_when_multiple_mappings_have_no_default(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		first_mapping = make_mapping(project, instance)
		second_mapping = make_mapping(project, instance)

		project_doc = frappe.get_doc("Project", project)
		for row in project_doc.custom_git_project_mappings:
			row.is_default = 0
		project_doc.save(ignore_permissions=True)

		payload = get_panel("Task", task)

		self.assertTrue(payload["show_gitlab_tab"])
		self.assertTrue(payload["can_create_branch"])
		self.assertEqual(payload["default_mapping_name"], first_mapping)
		self.assertEqual(payload["branch_preview"]["mapping"]["name"], first_mapping)
		self.assertEqual(
			[row["name"] for row in payload["branch_mapping_options"]],
			[first_mapping, second_mapping],
		)
		self._assert_branch_mapping_option_metadata(payload["branch_mapping_options"], instance)

	def test_panel_exposes_declined_label_and_merge_request_link_metadata(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		project_path = frappe.db.get_value("GitLab Project Mapping", mapping, "gitlab_project_path")
		base_url = frappe.db.get_value("GitLab Instance", instance, "base_url")

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="77",
				data={"artifact_name": "MR 77", "artifact_status": "closed", "web_url": "https://gitlab.example.com/mr/77"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source="mr_title",
			)
		)

		payload = get_panel("Task", task)

		self.assertEqual(payload["summary"]["development_status_label"], "Declined")
		self.assertEqual(payload["summary"]["status_merge_request_count"], 1)
		self.assertEqual(payload["summary"]["status_merge_request_label"], "Declined merge requests")
		self.assertEqual(
			payload["summary"]["status_merge_request_url"],
			f"{base_url}/{project_path}/-/merge_requests?scope=all&state=closed",
		)

	def test_panel_keeps_create_branch_available_after_branch_artifact_exists(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=f"feature/{task}-sample",
				data={
					"artifact_name": f"feature/{task}-sample",
					"ref_name": f"feature/{task}-sample",
					"artifact_status": "active",
					"web_url": "https://gitlab.example.com/branch/sample",
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source="branch_create",
				extracted_key=task,
				is_primary=1,
			)
		)

		payload = get_panel("Task", task)

		self.assertTrue(payload["can_create_branch"])
		self.assertIsNotNone(payload["branch_preview"])
		self.assertEqual(payload["default_branch_template"], "feature/{key}-{slug}")
		self.assertEqual(payload["available_base_branches"], ["develop", "main"])
		self.assertFalse(payload["show_branch_mapping_details"])

	def test_panel_hides_deleted_artifacts_and_allows_recreate_branch(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=f"feature/{task}-sample",
				data={
					"artifact_name": f"feature/{task}-sample",
					"ref_name": f"feature/{task}-sample",
					"artifact_status": "active",
					"web_url": "https://gitlab.example.com/branch/sample",
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source="branch_name",
				extracted_key=task,
				is_primary=1,
			)
		)
		mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=f"feature/{task}-sample",
			payload={"reason": "test"},
		)

		payload = get_panel("Task", task)

		self.assertTrue(payload["show_gitlab_tab"])
		self.assertEqual(payload["grouped_artifacts"], {})
		self.assertTrue(payload["can_create_branch"])
		self.assertIsNotNone(payload["branch_preview"])

	def test_panel_shows_task_gitlab_tab_without_task_rules(self):
		project = make_project()
		task_type = make_task_type()
		task = make_task(project, task_type=task_type)
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Issue", make_issue_type())

		payload = get_panel("Task", task)

		self.assertTrue(payload["show_gitlab_tab"])

	def test_panel_hides_task_gitlab_tab_when_type_is_not_allowed(self):
		project = make_project()
		allowed_task_type = make_task_type()
		task = make_task(project, task_type=make_task_type())
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Task", allowed_task_type)

		payload = get_panel("Task", task)

		self.assertFalse(payload["show_gitlab_tab"])

	def test_panel_shows_task_gitlab_tab_when_type_is_allowed(self):
		project = make_project()
		task_type = make_task_type()
		task = make_task(project, task_type=task_type)
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Task", task_type)

		payload = get_panel("Task", task)

		self.assertTrue(payload["show_gitlab_tab"])

	def test_panel_shows_task_gitlab_tab_for_all_types_when_blank_task_rule_exists(self):
		project = make_project()
		task = make_task(project, task_type=make_task_type())
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Task", make_task_type())
		add_type_visibility_rule(project, "Task")

		payload = get_panel("Task", task)

		self.assertTrue(payload["show_gitlab_tab"])

	def test_panel_hides_issue_gitlab_tab_when_type_is_not_allowed(self):
		project = make_project()
		allowed_issue_type = make_issue_type()
		issue = make_issue(project, issue_type=make_issue_type())
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Issue", allowed_issue_type)

		payload = get_panel("Issue", issue)

		self.assertFalse(payload["show_gitlab_tab"])

	def test_panel_shows_issue_gitlab_tab_without_issue_rules(self):
		project = make_project()
		issue = make_issue(project, issue_type=make_issue_type())
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Task", make_task_type())

		payload = get_panel("Issue", issue)

		self.assertTrue(payload["show_gitlab_tab"])

	def test_panel_shows_issue_gitlab_tab_for_all_types_when_blank_issue_rule_exists(self):
		project = make_project()
		issue = make_issue(project, issue_type=make_issue_type())
		instance = make_gitlab_instance()
		make_mapping(project, instance)
		add_type_visibility_rule(project, "Issue", make_issue_type())
		add_type_visibility_rule(project, "Issue")

		payload = get_panel("Issue", issue)

		self.assertTrue(payload["show_gitlab_tab"])

	def test_task_dashboard_has_no_development_links(self):
		transactions = frappe.get_meta("Task").get_dashboard_data().transactions
		items = [item for group in transactions for item in group.get("items", [])]
		self.assertNotIn("Development Artifact", items)
		self.assertNotIn("Development Artifact Link", items)

	def test_issue_dashboard_has_no_development_links(self):
		transactions = frappe.get_meta("Issue").get_dashboard_data().transactions
		items = [item for group in transactions for item in group.get("items", [])]
		self.assertNotIn("Development Artifact", items)
		self.assertNotIn("Development Artifact Link", items)

	def test_panel_exposes_artifact_author_and_updated_metadata(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="meta-11",
				data={
					"artifact_name": "MR Meta",
					"artifact_status": "opened",
					"web_url": "https://gitlab.example.com/mr/meta-11",
					"author_name": "GitLab Author",
					"author_email": "author@example.com",
					"author_avatar_url": "https://gitlab.example.com/avatar.png",
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source="mr_title",
			)
		)
		frappe.db.set_value("Development Artifact", artifact, "modified", "2026-05-30 12:00:00", update_modified=False)

		payload = get_panel("Task", task)
		group = next(iter(payload["grouped_artifacts"].values()))
		row = group["artifacts_by_type"]["merge_request"][0]

		self.assertEqual(row["author_display_name"], "GitLab Author")
		self.assertEqual(row["author_avatar_source"], "gitlab")
		self.assertEqual(row["updated_on"], "2026-05-30 12:00:00")
		self.assertEqual(payload["summary"]["last_updated_on"], "2026-05-30 12:00:00")
		self.assertEqual(payload["summary"]["last_updated_on_by_type"]["merge_request"], "2026-05-30 12:00:00")

	def test_panel_falls_back_to_dinext_user_avatar(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		email = f"panel-fallback-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Dinext",
				"last_name": "Avatar",
				"send_welcome_email": 0,
				"user_image": "https://example.com/dinext-avatar.png",
			}
		)
		user.insert(ignore_permissions=True)

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="pipeline",
				external_id="pipe-99",
				data={
					"artifact_name": "Pipeline 99",
					"artifact_status": "success",
					"author_name": "Pipeline Author",
					"author_email": email,
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source="pipeline_ref",
			)
		)

		payload = get_panel("Task", task)
		group = next(iter(payload["grouped_artifacts"].values()))
		row = group["artifacts_by_type"]["pipeline"][0]

		self.assertEqual(row["author_avatar_source"], "dinext_user")
		self.assertEqual(row["author_avatar_url"], "https://example.com/dinext-avatar.png")

	def test_panel_summary_timestamps_ignore_deleted_artifacts(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		visible_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="visible-22",
				data={"artifact_name": "Visible MR", "artifact_status": "opened"},
			)
		)
		deleted_artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=f"feature/{task}-deleted",
				data={"artifact_name": f"feature/{task}-deleted", "artifact_status": "active"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=visible_artifact,
				target_doctype="Task",
				target_name=task,
				link_source="mr_title",
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=deleted_artifact,
				target_doctype="Task",
				target_name=task,
				link_source="branch_name",
			)
		)
		frappe.db.set_value("Development Artifact", visible_artifact, "modified", "2026-05-30 10:00:00", update_modified=False)
		frappe.db.set_value("Development Artifact", deleted_artifact, "modified", "2026-05-30 15:00:00", update_modified=False)
		mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=f"feature/{task}-deleted",
			payload={"reason": "test"},
		)

		payload = get_panel("Task", task)

		self.assertEqual(payload["summary"]["last_updated_on"], "2026-05-30 10:00:00")
		self.assertNotIn("branch", payload["summary"]["last_updated_on_by_type"])
		self.assertEqual(payload["summary"]["last_updated_on_by_type"]["merge_request"], "2026-05-30 10:00:00")
