from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.patches.v0_0 import migrate_development_status_select_values as migration
from dinext_git.services.gitlab.constants import (
	DEVELOPMENT_STATUS_IN_PROGRESS,
	DEVELOPMENT_STATUS_LEGACY_CODES,
)
from dinext_git.tests.test_utils import make_project, make_task


class TestDevelopmentStatusMigration(FrappeTestCase):
	def test_legacy_codes_map_to_canonical_select_values(self):
		self.assertEqual(DEVELOPMENT_STATUS_LEGACY_CODES["in_progress"], DEVELOPMENT_STATUS_IN_PROGRESS)

	def test_migration_backfills_legacy_task_status(self):
		project = make_project()
		task = make_task(project)
		frappe.db.set_value("Task", task, "custom_git_development_status", "in_progress", update_modified=False)

		migration.execute()

		self.assertEqual(
			frappe.db.get_value("Task", task, "custom_git_development_status"),
			DEVELOPMENT_STATUS_IN_PROGRESS,
		)
