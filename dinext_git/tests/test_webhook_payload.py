from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.payloads import read_webhook_payload


class TestWebhookPayload(FrappeTestCase):
	def test_read_webhook_payload_uses_form_dict_and_ignores_frappe_keys(self):
		frappe.local.form_dict = frappe._dict(
			cmd="dinext_git.api.gitlab_webhooks.receive",
			ref="refs/heads/feature/sample",
			project={"id": 42, "path_with_namespace": "group/project"},
			commits=[],
		)

		payload = read_webhook_payload()

		self.assertEqual(payload["ref"], "refs/heads/feature/sample")
		self.assertEqual(payload["project"]["id"], 42)
		self.assertNotIn("cmd", payload)

	def test_read_webhook_payload_returns_empty_dict_without_body(self):
		frappe.local.form_dict = frappe._dict(cmd="dinext_git.api.gitlab_webhooks.receive")

		payload = read_webhook_payload()

		self.assertEqual(payload, {})
