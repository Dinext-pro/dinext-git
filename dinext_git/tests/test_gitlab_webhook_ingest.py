from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.api.gitlab_webhooks import _resolve_instance_name, _resolve_mapping, _resolve_workflow_events
from dinext_git.services.gitlab.normalizer import normalize_push_event
from dinext_git.services.gitlab.projector import update_work_item_summary
from dinext_git.services.gitlab.store import build_artifact_link_payload, upsert_artifact_link
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
