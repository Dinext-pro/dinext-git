from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.webhook_admin import (
	get_enabled_mappings_for_instance,
	verify_and_sync_instance_webhooks,
)
from dinext_git.tests.test_utils import make_gitlab_instance, make_mapping, make_project


class TestGitLabWebhookAdminBulk(FrappeTestCase):
	def setUp(self):
		self.instance_a = make_gitlab_instance()
		self.instance_b = make_gitlab_instance()
		self.project_a = make_project()
		self.project_b = make_project()
		self.mapping_active = make_mapping(self.project_a, self.instance_a)
		self.mapping_drifted = make_mapping(self.project_a, self.instance_a)
		self.mapping_missing = make_mapping(self.project_a, self.instance_a)
		self.mapping_disabled = make_mapping(self.project_a, self.instance_a)
		self.mapping_other_instance = make_mapping(self.project_b, self.instance_b)

		frappe.db.set_value(
			"GitLab Project Mapping",
			self.mapping_disabled,
			"enabled",
			0,
		)

	def test_get_enabled_mappings_scoped_to_instance(self):
		names = {row["name"] for row in get_enabled_mappings_for_instance(self.instance_a)}
		self.assertIn(self.mapping_active, names)
		self.assertIn(self.mapping_drifted, names)
		self.assertIn(self.mapping_missing, names)
		self.assertNotIn(self.mapping_disabled, names)
		self.assertNotIn(self.mapping_other_instance, names)

	@patch("dinext_git.services.gitlab.webhook_admin.sync_mapping_webhook")
	@patch("dinext_git.services.gitlab.webhook_admin.verify_mapping_webhook")
	def test_verify_and_sync_only_problematic_mappings(self, mock_verify, mock_sync):
		def verify_side_effect(mapping_name: str):
			status_by_mapping = {
				self.mapping_active: "active",
				self.mapping_drifted: "drifted",
				self.mapping_missing: "missing",
			}
			return {"status": status_by_mapping[mapping_name]}

		mock_verify.side_effect = verify_side_effect

		summary = verify_and_sync_instance_webhooks(self.instance_a)

		self.assertEqual(summary["instance"], self.instance_a)
		self.assertEqual(summary["checked_count"], 3)
		self.assertEqual(summary["synced_count"], 2)
		self.assertEqual(mock_sync.call_count, 2)
		synced_mappings = {call.args[0] for call in mock_sync.call_args_list}
		self.assertEqual(synced_mappings, {self.mapping_drifted, self.mapping_missing})
		self.assertFalse(any(call.args[0] == self.mapping_active for call in mock_sync.call_args_list))

	@patch("dinext_git.services.gitlab.webhook_admin.sync_mapping_webhook")
	@patch("dinext_git.services.gitlab.webhook_admin.verify_mapping_webhook")
	def test_failed_status_triggers_sync(self, mock_verify, mock_sync):
		mock_verify.return_value = {"status": "failed"}

		summary = verify_and_sync_instance_webhooks(self.instance_a)

		self.assertGreaterEqual(summary["synced_count"], 1)
		self.assertTrue(mock_sync.called)

	@patch("dinext_git.services.gitlab.webhook_admin.sync_mapping_webhook")
	@patch("dinext_git.services.gitlab.webhook_admin.verify_mapping_webhook")
	def test_reverify_after_sync_updates_active_count(self, mock_verify, mock_sync):
		post_sync = set()

		def verify_side_effect(mapping_name: str):
			if mapping_name == self.mapping_active:
				return {"status": "active"}
			if mapping_name in post_sync:
				return {"status": "active"}
			return {"status": "drifted"}

		def sync_side_effect(mapping_name: str):
			post_sync.add(mapping_name)

		mock_verify.side_effect = verify_side_effect
		mock_sync.side_effect = sync_side_effect

		summary = verify_and_sync_instance_webhooks(self.instance_a)

		self.assertEqual(summary["active_count"], 3)
		self.assertEqual(summary["still_problematic_count"], 0)

	@patch("dinext_git.services.gitlab.webhook_admin.sync_mapping_webhook")
	@patch("dinext_git.services.gitlab.webhook_admin.verify_mapping_webhook")
	def test_verify_error_continues_batch(self, mock_verify, mock_sync):
		def verify_side_effect(mapping_name: str):
			if mapping_name == self.mapping_missing:
				raise RuntimeError("verify failed")
			return {"status": "active"}

		mock_verify.side_effect = verify_side_effect

		summary = verify_and_sync_instance_webhooks(self.instance_a)

		self.assertEqual(summary["checked_count"], 3)
		self.assertEqual(summary["error_count"], 1)
		self.assertFalse(mock_sync.called)
		failed = next(row for row in summary["results"] if row["mapping"] == self.mapping_missing)
		self.assertIn("verify failed", failed["error"])

	@patch("dinext_git.services.gitlab.webhook_admin.sync_mapping_webhook")
	@patch("dinext_git.services.gitlab.webhook_admin.verify_mapping_webhook")
	def test_sync_error_recorded_without_stopping_batch(self, mock_verify, mock_sync):
		mock_verify.return_value = {"status": "drifted"}

		def sync_side_effect(mapping_name: str):
			if mapping_name == self.mapping_drifted:
				raise RuntimeError("sync failed")

		mock_sync.side_effect = sync_side_effect

		summary = verify_and_sync_instance_webhooks(self.instance_a)

		self.assertEqual(summary["error_count"], 1)
		self.assertEqual(summary["checked_count"], 3)
		drifted_row = next(row for row in summary["results"] if row["mapping"] == self.mapping_drifted)
		self.assertIn("sync failed", drifted_row["error"])

	def test_empty_instance_returns_zero_counts(self):
		instance = make_gitlab_instance()
		summary = verify_and_sync_instance_webhooks(instance)
		self.assertEqual(summary["checked_count"], 0)
		self.assertEqual(summary["synced_count"], 0)
		self.assertEqual(summary["results"], [])

	def test_unknown_instance_raises(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			verify_and_sync_instance_webhooks("missing-instance")
