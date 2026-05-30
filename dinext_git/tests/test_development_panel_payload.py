from __future__ import annotations

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
		self.assertTrue(payload["show_gitlab_tab"])
		self.assertEqual(len(payload["grouped_artifacts"]), 2)
		self.assertIn("summary", payload)
		self.assertTrue(payload["can_create_branch"])
		self.assertEqual(payload["branch_preview"]["base_branch"], "develop")
		self.assertEqual(payload["summary"]["development_status_label"], "Pipeline failed")
		self.assertEqual(len(payload["branch_mapping_options"]), 2)
		self.assertTrue(payload["show_branch_mapping_details"])

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

	def test_panel_hides_create_branch_after_branch_artifact_exists(self):
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

		self.assertFalse(payload["can_create_branch"])
		self.assertIsNone(payload["branch_preview"])
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
