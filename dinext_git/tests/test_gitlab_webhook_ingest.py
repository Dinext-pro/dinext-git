from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.api.gitlab_webhooks import _resolve_instance_name, _resolve_mapping, _resolve_workflow_events
from dinext_git.services.gitlab.normalizer import is_branch_delete_push, normalize_push_event
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.store import build_artifact_link_payload, build_artifact_payload, upsert_artifact, upsert_artifact_link
from dinext_git.services.gitlab.utils import branch_name_from_ref
from dinext_git.services.gitlab.workflow_sync import apply_rules
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestGitLabWebhookIngest(FrappeTestCase):
	def test_resolve_instance_name_matches_password_field_secret(self):
		instance = make_gitlab_instance()
		secret = frappe.get_doc("GitLab Instance", instance).get_password("webhook_secret")

		resolved = _resolve_instance_name(secret)

		self.assertEqual(resolved, instance)

	def test_push_event_links_branch_and_commit(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		payload = {
			"ref": f"refs/heads/feature/{task}-sample",
			"checkout_sha": "abc123",
			"user_name": "Dev User",
			"user_email": "dev@example.com",
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [
				{
					"id": "abc123",
					"title": "Implement feature",
					"message": f"{task} implement feature",
					"url": "https://gitlab.example.com/commit/abc123",
					"author": {"name": "Dev User", "email": "dev@example.com"},
				}
			],
		}

		result = normalize_push_event(instance, mapping, payload)
		self.assertTrue(result["branch"])
		self.assertEqual(len(result["commits"]), 1)
		branch_name = f"feature/{task}-sample"
		self.assertEqual(frappe.db.get_value("Development Artifact", result["branch"], "external_id"), branch_name)

	def test_branch_name_from_ref_keeps_nested_branch_path(self):
		self.assertEqual(branch_name_from_ref("refs/heads/feature/sample"), "feature/sample")
		self.assertIsNone(branch_name_from_ref("refs/tags/v1.0"))

	def test_delete_push_marks_branch_created_from_dinext_ui(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		branch_name = f"feature/{task}-sample"

		artifact_name = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=branch_name,
				data={
					"artifact_name": branch_name,
					"ref_name": branch_name,
					"artifact_status": "active",
				},
			)
		)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=artifact_name,
				target_doctype="Task",
				target_name=task,
				link_source="branch_create",
				extracted_key=task,
				is_primary=1,
			)
		)
		update_work_item_summary("Task", task)
		self.assertEqual(frappe.db.get_value("Task", task, "custom_git_artifact_count"), 1)

		delete_payload = {
			"ref": f"refs/heads/{branch_name}",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		deleted = normalize_push_event(instance, mapping, delete_payload)
		update_work_item_summary("Task", task)

		self.assertEqual(deleted["branch"], artifact_name)
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"), "deleted")
		self.assertEqual(frappe.db.get_value("Task", task, "custom_git_artifact_count"), 0)

	def test_delete_push_falls_back_to_legacy_short_external_id(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		branch_name = f"feature/{task}-sample"
		legacy_external_id = branch_name.rsplit("/", 1)[-1]

		artifact_name = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=legacy_external_id,
				data={
					"artifact_name": legacy_external_id,
					"ref_name": legacy_external_id,
					"artifact_status": "active",
				},
			)
		)

		delete_payload = {
			"ref": f"refs/heads/{branch_name}",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		deleted = normalize_push_event(instance, mapping, delete_payload)

		self.assertEqual(deleted["branch"], artifact_name)
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "external_id"), branch_name)
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"), "deleted")

	def test_delete_push_marks_branch_with_null_artifact_status(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		branch_name = f"feature/{task}-sample"

		artifact_name = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=branch_name,
				data={
					"artifact_name": branch_name,
					"ref_name": branch_name,
				},
			)
		)
		self.assertIsNone(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"))

		delete_payload = {
			"ref": f"refs/heads/{branch_name}",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		deleted = normalize_push_event(instance, mapping, delete_payload)

		self.assertEqual(deleted["branch"], artifact_name)
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"), "deleted")

	def test_tag_delete_push_is_not_treated_as_branch_deleted(self):
		delete_payload = {
			"ref": "refs/tags/v1.0",
			"after": "0" * 40,
			"checkout_sha": "0" * 40,
		}
		self.assertEqual(_resolve_workflow_events("Push Hook", delete_payload), [])

	def test_resolve_mapping_falls_back_to_project_path(self):
		project = make_project()
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		mapping_doc = frappe.get_doc("GitLab Project Mapping", mapping)
		mapping_doc.gitlab_project_id = ""
		mapping_doc.save(ignore_permissions=True)

		payload = {
			"project": {
				"path_with_namespace": mapping_doc.gitlab_project_path,
			}
		}
		resolved = _resolve_mapping(instance, payload)
		self.assertTrue(resolved)
		self.assertEqual(resolved["name"], mapping)

	def test_delete_push_marks_existing_branch_deleted_and_recalculates_summary(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		create_payload = {
			"ref": f"refs/heads/feature/{task}-sample",
			"checkout_sha": "abc123",
			"user_name": "Dev User",
			"user_email": "dev@example.com",
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		result = normalize_push_event(instance, mapping, create_payload)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=result["branch"],
				target_doctype="Task",
				target_name=task,
				link_source="branch_name",
				extracted_key=task,
				is_primary=1,
			)
		)
		update_work_item_summary("Task", task)
		self.assertEqual(frappe.db.get_value("Task", task, "custom_git_artifact_count"), 1)

		delete_payload = {
			"ref": f"refs/heads/feature/{task}-sample",
			"after": "0" * 40,
			"checkout_sha": "0" * 40,
			"user_name": "Dev User",
			"user_email": "dev@example.com",
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		deleted = normalize_push_event(instance, mapping, delete_payload)
		update_work_item_summary("Task", task)

		self.assertEqual(deleted["branch"], result["branch"])
		self.assertEqual(frappe.db.get_value("Development Artifact", result["branch"], "artifact_status"), "deleted")
		self.assertEqual(frappe.db.get_value("Task", task, "custom_git_artifact_count"), 0)

	def test_delete_push_resolves_branch_deleted_event(self):
		delete_payload = {
			"ref": "refs/heads/feature/sample",
			"after": "0" * 40,
			"checkout_sha": "0" * 40,
		}
		self.assertEqual(_resolve_workflow_events("Push Hook", delete_payload), ["branch_deleted"])

	def test_delete_push_applies_branch_deleted_workflow_rule(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)

		frappe.get_doc(
			{
				"doctype": "Development Workflow Rule",
				"target_doctype": "Task",
				"project": project,
				"target_fieldname": "status",
				"development_event": "branch_deleted",
				"target_status": "Open",
				"only_when_current_status": "Working",
				"priority": 10,
				"enabled": 1,
				"stop_after_apply": 1,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Task", task, "status", "Working")

		create_payload = {
			"ref": f"refs/heads/feature/{task}-sample",
			"checkout_sha": "abc123",
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		result = normalize_push_event(instance, mapping, create_payload)
		upsert_artifact_link(
			build_artifact_link_payload(
				artifact=result["branch"],
				target_doctype="Task",
				target_name=task,
				link_source="branch_name",
				extracted_key=task,
				is_primary=1,
			)
		)

		delete_payload = {
			"ref": f"refs/heads/feature/{task}-sample",
			"after": "0" * 40,
			"checkout_sha": "0" * 40,
			"project": {"web_url": "https://gitlab.example.com/dinext/project"},
			"commits": [],
		}
		normalize_push_event(instance, mapping, delete_payload)
		update_work_item_summary("Task", task)
		apply_rules("Task", task, "branch_deleted")

		self.assertEqual(frappe.db.get_value("Task", task, "status"), "Open")

	def test_delete_push_detects_branch_removal_from_before_and_after(self):
		payload = {
			"ref": "refs/heads/feature/sample",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"commits": [],
		}
		self.assertTrue(is_branch_delete_push(payload))

	def test_delete_push_finds_branch_by_project_id_when_mapping_not_passed(self):
		project = make_project()
		task = make_task(project)
		instance = make_gitlab_instance()
		mapping = make_mapping(project, instance)
		mapping_doc = frappe.get_doc("GitLab Project Mapping", mapping)
		mapping_doc.gitlab_project_id = "424242"
		mapping_doc.save(ignore_permissions=True)
		branch_name = f"feature/{task}-sample"

		artifact_name = upsert_artifact(
			build_artifact_payload(
				instance=instance,
				mapping=mapping,
				artifact_type="branch",
				external_id=branch_name,
				data={
					"artifact_name": branch_name,
					"ref_name": branch_name,
					"artifact_status": "active",
				},
			)
		)

		delete_payload = {
			"ref": f"refs/heads/{branch_name}",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"project": {"id": 424242, "path_with_namespace": mapping_doc.gitlab_project_path},
			"commits": [],
		}
		deleted = normalize_push_event(instance, None, delete_payload)

		self.assertEqual(deleted["branch"], artifact_name)
		self.assertEqual(deleted["branches"], [artifact_name])
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"), "deleted")
