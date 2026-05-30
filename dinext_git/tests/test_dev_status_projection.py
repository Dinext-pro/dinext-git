from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.projector import collect_work_item_summary
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	get_instance,
	get_mapping,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestDevStatusProjection(FrappeTestCase):
	def _add_linked_artifact(
		self,
		*,
		instance: str,
		mapping: str,
		task: str,
		artifact_type: str,
		external_id: str,
		artifact_status: str,
		artifact_name: str,
		link_source: str = "mr_title",
		web_url: str | None = None,
	) -> str:
		artifact = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type=artifact_type,
				external_id=external_id,
				data={
					"artifact_name": artifact_name,
					"artifact_status": artifact_status,
					"web_url": web_url,
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact,
				target_doctype="Task",
				target_name=task,
				link_source=link_source,
			)
		)
		return artifact

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

	def test_summary_marks_declined_when_only_closed_like_merge_requests_exist(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		mapping_doc = get_mapping(mapping)
		instance_doc = get_instance(instance)

		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="201",
			artifact_status="closed",
			artifact_name="MR 201",
			web_url="https://gitlab.example.com/mr/201",
		)
		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="202",
			artifact_status="rejected",
			artifact_name="MR 202",
			web_url="https://gitlab.example.com/mr/202",
		)

		summary = collect_work_item_summary("Task", task)

		self.assertEqual(summary["development_status"], "declined")
		self.assertEqual(summary["status_merge_request_count"], 2)
		self.assertEqual(summary["status_merge_request_state"], "closed")
		self.assertEqual(
			summary["status_merge_request_url"],
			f"{instance_doc['base_url']}/{mapping_doc['gitlab_project_path']}/-/merge_requests?scope=all&state=closed",
		)

	def test_summary_treats_open_merge_request_as_in_progress(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		mapping_doc = get_mapping(mapping)
		instance_doc = get_instance(instance)

		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="301",
			artifact_status="closed",
			artifact_name="MR 301",
			web_url="https://gitlab.example.com/mr/301",
		)
		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="302",
			artifact_status="opened",
			artifact_name="MR 302",
			web_url="https://gitlab.example.com/mr/302",
		)

		summary = collect_work_item_summary("Task", task)

		self.assertEqual(summary["development_status"], "in_progress")
		self.assertEqual(summary["status_merge_request_count"], 1)
		self.assertEqual(summary["status_merge_request_state"], "opened")
		self.assertEqual(
			summary["status_merge_request_url"],
			f"{instance_doc['base_url']}/{mapping_doc['gitlab_project_path']}/-/merge_requests?scope=all&state=opened",
		)

	def test_summary_uses_merged_merge_requests_for_pipeline_failed_status(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		mapping_doc = get_mapping(mapping)
		instance_doc = get_instance(instance)

		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="401",
			artifact_status="merged",
			artifact_name="MR 401",
			web_url="https://gitlab.example.com/mr/401",
		)
		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="pipeline",
			external_id="402",
			artifact_status="failed",
			artifact_name="Pipeline 402",
			link_source="pipeline_ref",
			web_url="https://gitlab.example.com/pipelines/402",
		)

		summary = collect_work_item_summary("Task", task)

		self.assertEqual(summary["development_status"], "pipeline_failed")
		self.assertEqual(summary["status_merge_request_count"], 1)
		self.assertEqual(summary["status_merge_request_state"], "merged")
		self.assertEqual(
			summary["status_merge_request_url"],
			f"{instance_doc['base_url']}/{mapping_doc['gitlab_project_path']}/-/merge_requests?scope=all&state=merged",
		)

	def test_summary_uses_merged_merge_requests_for_deployed_status(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="merge_request",
			external_id="501",
			artifact_status="merged",
			artifact_name="MR 501",
			web_url="https://gitlab.example.com/mr/501",
		)
		self._add_linked_artifact(
			instance=instance,
			mapping=mapping,
			task=task,
			artifact_type="deployment",
			external_id="502",
			artifact_status="success",
			artifact_name="Deployment 502",
			link_source="pipeline_ref",
			web_url="https://gitlab.example.com/deployments/502",
		)

		summary = collect_work_item_summary("Task", task)

		self.assertEqual(summary["development_status"], "deployed")
		self.assertEqual(summary["status_merge_request_count"], 1)
		self.assertEqual(summary["status_merge_request_state"], "merged")

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
