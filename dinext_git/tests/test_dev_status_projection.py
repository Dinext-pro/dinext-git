from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.projector import collect_work_item_summary
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestDevStatusProjection(FrappeTestCase):
	def test_summary_reflects_branch_and_failed_pipeline(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		branch = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id="feature/TASK-2026-00001-sample",
				data={"artifact_name": "feature/TASK-2026-00001-sample", "artifact_status": "active"},
			)
		)
		pipeline = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="pipeline",
				external_id="100",
				data={"artifact_name": "Pipeline 100", "artifact_status": "failed"},
			)
		)
		upsert_artifact_link(build_artifact_link_payload(artifact=branch, target_doctype="Task", target_name=task, link_source="branch_create"))
		upsert_artifact_link(build_artifact_link_payload(artifact=pipeline, target_doctype="Task", target_name=task, link_source="pipeline_ref"))

		summary = collect_work_item_summary("Task", task)
		self.assertEqual(summary["artifact_count"], 2)
		self.assertEqual(summary["development_status"], "pipeline_failed")
		self.assertIn("pipeline_failed", summary["discrepancy_flags"])

	def test_deleted_artifacts_are_ignored_in_summary(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		branch = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=f"feature/{task}-sample",
				data={"artifact_name": f"feature/{task}-sample", "artifact_status": "active"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=branch,
				target_doctype="Task",
				target_name=task,
				link_source="branch_name",
			)
		)
		mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=f"feature/{task}-sample",
			payload={"reason": "test"},
		)

		summary = collect_work_item_summary("Task", task)
		self.assertEqual(summary["artifact_count"], 0)
		self.assertEqual(summary["development_status"], "not_started")
		self.assertEqual(frappe.db.get_value("Development Artifact", branch, "artifact_status"), "deleted")
