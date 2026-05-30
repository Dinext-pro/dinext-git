from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.handler import execute_cmd
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.store import build_artifact_link_payload, build_artifact_payload, upsert_artifact, upsert_artifact_link
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project, make_task


class TestGitLabWebhookReceive(FrappeTestCase):
	def test_receive_marks_branch_deleted_from_form_dict_payload(self):
		instance = make_gitlab_instance()
		secret = frappe.get_doc("GitLab Instance", instance).get_password("webhook_secret")
		project = make_project()
		task = make_task(project)
		mapping = make_mapping(project, instance)
		mapping_doc = frappe.get_doc("GitLab Project Mapping", mapping)
		mapping_doc.gitlab_project_id = "515151"
		mapping_doc.save(ignore_permissions=True)
		branch_name = f"feature/{task}-receive-delete"

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

		payload = {
			"ref": f"refs/heads/{branch_name}",
			"before": "abc12345678901234567890123456789012345678",
			"after": "0" * 40,
			"project": {"id": 515151, "path_with_namespace": mapping_doc.gitlab_project_path},
			"commits": [],
		}
		frappe.local.request = frappe._dict(method="POST")
		frappe.local.form_dict = frappe._dict(cmd="dinext_git.api.gitlab_webhooks.receive", **payload)

		def _header(name, default=None):
			headers = {
				"X-Gitlab-Event": "Push Hook",
				"X-Gitlab-Token": secret,
			}
			return headers.get(name, default)

		with patch("frappe.get_request_header", side_effect=_header):
			result = execute_cmd("dinext_git.api.gitlab_webhooks.receive")

		self.assertTrue(result["ok"])
		self.assertEqual(frappe.db.get_value("Development Artifact", artifact_name, "artifact_status"), "deleted")
