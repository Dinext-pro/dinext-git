from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.workflow_events import (
	resolve_merge_request_workflow_events,
	resolve_pipeline_workflow_events,
	resolve_push_workflow_event,
)
from dinext_git.services.gitlab.workflow_sync import apply_rules
from dinext_git.tests.test_utils import make_issue, make_project, make_task


class TestWorkflowEvents(FrappeTestCase):
	def test_resolve_push_delete_event(self):
		self.assertEqual(resolve_push_workflow_event({}, is_delete_push=True), "branch_deleted")
		self.assertEqual(resolve_push_workflow_event({}, is_delete_push=False), "branch_linked")

	def test_resolve_merge_request_events(self):
		self.assertEqual(
			resolve_merge_request_workflow_events({"object_attributes": {"state": "merged", "action": "merge"}}),
			["mr_merged"],
		)
		self.assertEqual(
			resolve_merge_request_workflow_events({"object_attributes": {"action": "approved", "state": "opened"}}),
			["mr_approved"],
		)
		self.assertEqual(
			resolve_merge_request_workflow_events({"object_attributes": {"action": "unapproved", "state": "opened"}}),
			["mr_changes_requested"],
		)
		self.assertEqual(
			resolve_merge_request_workflow_events(
				{
					"object_attributes": {"action": "update", "state": "opened"},
					"changes": {"reviewers": {"previous": [], "current": [{"id": 1}]}},
				}
			),
			["mr_review_started"],
		)
		self.assertEqual(
			resolve_merge_request_workflow_events({"object_attributes": {"action": "open", "state": "opened"}}),
			["mr_opened"],
		)

	def test_resolve_pipeline_events(self):
		self.assertEqual(
			resolve_pipeline_workflow_events({"object_attributes": {"status": "failed"}}),
			["pipeline_failed"],
		)
		self.assertEqual(
			resolve_pipeline_workflow_events({"object_attributes": {"status": "success"}}),
			["pipeline_succeeded"],
		)
		self.assertEqual(
			resolve_pipeline_workflow_events(
				{
					"object_attributes": {"status": "success"},
					"builds": [{"status": "success", "environment": {"name": "production"}}],
				}
			),
			["pipeline_succeeded", "deployment_succeeded"],
		)


class TestWorkflowSync(FrappeTestCase):
	def _make_rule(self, **overrides):
		values = {
			"doctype": "Development Workflow Rule",
			"target_doctype": "Task",
			"target_fieldname": "status",
			"development_event": "branch_created",
			"target_status": "Working",
			"priority": 10,
			"enabled": 1,
			"stop_after_apply": 1,
		}
		values.update(overrides)
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def test_apply_rules_uses_document_save_cycle(self):
		project = make_project()
		task = make_task(project)
		rule_name = self._make_rule(project=project, only_when_current_status="Open")

		applied = apply_rules("Task", task, "branch_created")

		self.assertEqual(applied, [rule_name])
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Working")

	def test_apply_rules_respects_project_filter(self):
		project_a = make_project()
		project_b = make_project()
		task = make_task(project_a)
		rule_name = self._make_rule(project=project_b, target_status="Pending Review")

		applied = apply_rules("Task", task, "branch_created")

		self.assertEqual(applied, [])
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")

		frappe.db.set_value("Development Workflow Rule", rule_name, "project", project_a)
		applied = apply_rules("Task", task, "branch_created")
		self.assertEqual(len(applied), 1)
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Pending Review")

	def test_apply_rules_honors_only_when_current_value(self):
		project = make_project()
		task = make_task(project)
		self._make_rule(project=project, only_when_current_status="Working", target_status="Pending Review")

		applied = apply_rules("Task", task, "branch_created")

		self.assertEqual(applied, [])
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")

	def test_apply_rules_stops_after_first_successful_rule(self):
		project = make_project()
		task = make_task(project)
		first = self._make_rule(
			project=project,
			target_status="Working",
			only_when_current_status="Open",
			priority=10,
			stop_after_apply=1,
		)
		second = self._make_rule(
			project=project,
			target_status="Pending Review",
			only_when_current_status="Open",
			priority=20,
			stop_after_apply=0,
		)

		applied = apply_rules("Task", task, "branch_created")

		self.assertEqual(applied, [first])
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Working")
		self.assertNotIn(second, applied)

	def test_apply_rules_logs_and_skips_invalid_save(self):
		project = make_project()
		task = make_task(project)
		self._make_rule(project=project, target_status="Completed", only_when_current_status="Open")

		with patch("dinext_git.services.gitlab.workflow_sync.frappe.log_error") as log_error:
			applied = apply_rules("Task", task, "branch_created")

		self.assertEqual(applied, [])
		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")
		log_error.assert_called_once()

	def test_apply_rules_supports_custom_select_field(self):
		project = make_project()
		issue = make_issue(project)
		frappe.get_doc(
			{
				"doctype": "Development Workflow Rule",
				"target_doctype": "Issue",
				"project": project,
				"target_fieldname": "status",
				"development_event": "mr_opened",
				"target_status": "Replied",
				"only_when_current_status": "Open",
				"priority": 10,
				"enabled": 1,
				"stop_after_apply": 1,
			}
		).insert(ignore_permissions=True)

		applied = apply_rules("Issue", issue, "mr_opened")

		self.assertEqual(len(applied), 1)
		self.assertEqual(frappe.db.get_value("Issue", issue, "status"), "Replied")
