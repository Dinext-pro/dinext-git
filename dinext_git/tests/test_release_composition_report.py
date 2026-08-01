from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.reports.release_composition import run
from dinext_git.services.gitlab.store import (
	build_artifact_link_payload,
	build_artifact_payload,
	mark_artifact_deleted,
	upsert_artifact,
	upsert_artifact_link,
)
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestReleaseCompositionReport(FrappeTestCase):
	def test_row_when_release_and_merged_mr_exist(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		release = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="release",
				external_id="v1.0.0",
				data={
					"artifact_name": "v1.0.0",
					"artifact_status": "active",
					"web_url": "https://gitlab.example.com/-/releases/v1.0.0",
				},
			)
		)
		mr = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="501",
				data={"artifact_name": "MR 501", "artifact_status": "merged"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=release, target_doctype="Task", target_name=task, link_source="release_ref")
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=mr, target_doctype="Task", target_name=task, link_source="mr_title")
		)

		rows = run()
		match = next((row for row in rows if row["target_name"] == task), None)
		self.assertIsNotNone(match)
		self.assertIn("v1.0.0", match["release_names"])
		self.assertIn("https://gitlab.example.com/-/releases/v1.0.0", match["release_urls"])

	def test_row_when_tag_and_merged_mr_exist(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		tag = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="tag",
				external_id="v2.0.0",
				data={"artifact_name": "v2.0.0", "artifact_status": "active"},
			)
		)
		mr = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="502",
				data={"artifact_name": "MR 502", "artifact_status": "merged"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=tag, target_doctype="Task", target_name=task, link_source="release_ref")
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=mr, target_doctype="Task", target_name=task, link_source="mr_title")
		)

		rows = run()
		self.assertTrue(any(row["target_name"] == task for row in rows))

	def test_no_row_without_merged_mr(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		release = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="release",
				external_id="v3.0.0",
				data={"artifact_name": "v3.0.0", "artifact_status": "active"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=release, target_doctype="Task", target_name=task, link_source="release_ref")
		)

		rows = run()
		self.assertFalse(any(row["target_name"] == task for row in rows))

	def test_deployment_statuses_only_from_deployment_artifacts(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		release = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="release",
				external_id="v4.0.0",
				data={"artifact_name": "v4.0.0", "artifact_status": "active"},
			)
		)
		deployment = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="deployment",
				external_id="100::200",
				data={"artifact_name": "production", "artifact_status": "success"},
			)
		)
		mr = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="503",
				data={"artifact_name": "MR 503", "artifact_status": "merged"},
			)
		)
		for artifact in (release, deployment, mr):
			upsert_artifact_link(
				build_artifact_link_payload(artifact=artifact, target_doctype="Task", target_name=task, link_source="release_ref")
			)

		rows = run()
		match = next((row for row in rows if row["target_name"] == task), None)
		self.assertIsNotNone(match)
		self.assertEqual(match["deployment_statuses"], "success")

	def test_deleted_release_artifacts_are_excluded(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		release = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="release",
				external_id="v5.0.0",
				data={"artifact_name": "v5.0.0", "artifact_status": "active"},
			)
		)
		mr = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="merge_request",
				external_id="504",
				data={"artifact_name": "MR 504", "artifact_status": "merged"},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=release, target_doctype="Task", target_name=task, link_source="release_ref")
		)
		upsert_artifact_link(
			build_artifact_link_payload(artifact=mr, target_doctype="Task", target_name=task, link_source="mr_title")
		)
		mark_artifact_deleted(
			instance=instance,
			mapping=mapping,
			artifact_type="release",
			external_id="v5.0.0",
			payload={"reason": "test"},
		)

		rows = run()
		self.assertFalse(any(row["target_name"] == task for row in rows))
