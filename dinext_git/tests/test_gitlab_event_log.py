from __future__ import annotations

import frappe
from frappe.core.doctype.log_settings.log_settings import _supports_log_clearing, run_log_clean_up
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from dinext_git.services.gitlab.utils import json_dumps, make_uid
from dinext_git.tests.test_utils import make_gitlab_instance


class TestGitLabEventLog(FrappeTestCase):
	def test_gitlab_event_log_is_supported_by_log_settings(self):
		self.assertTrue(_supports_log_clearing("GitLab Event Log"))

	def test_run_log_clean_up_registers_gitlab_event_log_default(self):
		log_settings = frappe.get_doc("Log Settings")
		log_settings.logs_to_clear = [
			row for row in (log_settings.logs_to_clear or []) if row.ref_doctype != "GitLab Event Log"
		]
		log_settings.save()

		run_log_clean_up()

		log_settings.reload()
		entry = next((row for row in log_settings.logs_to_clear if row.ref_doctype == "GitLab Event Log"), None)
		self.assertIsNotNone(entry)
		self.assertEqual(entry.days, 30)

	def test_run_log_clean_up_deletes_old_gitlab_event_logs(self):
		now = now_datetime()
		old_timestamp = add_to_date(now, days=-40)
		instance = make_gitlab_instance()

		old_name = self._create_event_log(
			instance=instance, event_type="Push Hook", delivery_id="old", modified=old_timestamp
		)
		new_name = self._create_event_log(instance=instance, event_type="Pipeline Hook", delivery_id="new")

		run_log_clean_up()

		self.assertFalse(frappe.db.exists("GitLab Event Log", old_name))
		self.assertTrue(frappe.db.exists("GitLab Event Log", new_name))

	def _create_event_log(self, *, instance: str, event_type: str, delivery_id: str, modified=None) -> str:
		payload = {"event_type": event_type, "delivery_id": delivery_id}
		doc = frappe.get_doc(
			{
				"doctype": "GitLab Event Log",
				"event_uid": make_uid("test-instance", event_type, delivery_id),
				"gitlab_instance": instance,
				"event_type": event_type,
				"delivery_id": delivery_id,
				"payload_json": json_dumps(payload),
			}
		)
		doc.insert(ignore_permissions=True)
		if modified:
			doc.db_set("creation", modified, update_modified=False)
			doc.db_set("modified", modified, update_modified=False)
		return doc.name
