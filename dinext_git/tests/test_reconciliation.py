from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.reconcile import reconcile_mapping
from dinext_git.services.gitlab.store import build_artifact_link_payload, build_artifact_payload, upsert_artifact, upsert_artifact_link
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

	@patch("dinext_git.services.gitlab.reconcile.GitLabClient")
	def test_reconciliation_marks_missing_branch_deleted(self, client_cls):
		project = make_project()
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id="feature/test-branch",
				data={"artifact_name": "feature/test-branch", "artifact_status": "active"},
			)
		)
		task = frappe.get_doc(
			{
				"doctype": "Task",
				"subject": "Reconcile branch delete",
				"project": project,
				"status": "Open",
			}
		)
		task.insert(ignore_permissions=True)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task.name,
				link_source="branch_name",
			)
		)

		client = client_cls.return_value
		client.get_project.return_value = {"id": 99}
		client.list_merge_requests.return_value = []
		client.list_pipelines.return_value = []
		client.list_branches.return_value = []

		result = reconcile_mapping(mapping)

		self.assertEqual(result["branches_deleted"], 1)
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact, "artifact_status"), "deleted")
