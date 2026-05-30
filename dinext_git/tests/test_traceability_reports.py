from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from dinext_git.services.reports.traceability import run
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestTraceabilityReports(FrappeTestCase):
	def test_tasks_without_merge_request_mode(self):
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
		upsert_artifact_link(build_artifact_link_payload(artifact=branch, target_doctype="Task", target_name=task, link_source="branch_name"))

		rows = run("tasks_without_mr")
		self.assertTrue(any(row["name"] == task for row in rows))

	def test_deleted_artifacts_are_excluded_from_reports(self):
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
		upsert_artifact_link(build_artifact_link_payload(artifact=branch, target_doctype="Task", target_name=task, link_source="branch_name"))
		mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="branch",
			external_id=f"feature/{task}-sample",
			payload={"reason": "test"},
		)

		rows = run("tasks_without_mr")
		self.assertFalse(any(row["name"] == task for row in rows))
