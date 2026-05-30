from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from dinext_git.services.gitlab.panel_metadata import (
	build_summary_timestamps,
	build_user_avatar_lookup,
	resolve_author_metadata,
)


class TestPanelMetadata(FrappeTestCase):
	def test_resolve_author_metadata_prefers_gitlab_avatar(self):
		metadata = resolve_author_metadata(
			{
				"author_name": "GitLab User",
				"author_email": "gitlab@example.com",
				"author_avatar_url": "https://gitlab.example.com/avatar.png",
			},
			{},
		)

		self.assertEqual(metadata["author_avatar_source"], "gitlab")
		self.assertEqual(metadata["author_avatar_url"], "https://gitlab.example.com/avatar.png")
		self.assertEqual(metadata["author_tooltip"], "GitLab User · gitlab@example.com")

	def test_resolve_author_metadata_falls_back_to_dinext_user(self):
		email = f"panel-meta-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Panel",
				"last_name": "Meta",
				"send_welcome_email": 0,
				"user_image": "https://example.com/panel-meta.png",
			}
		)
		user.insert(ignore_permissions=True)

		lookup = build_user_avatar_lookup([email])
		metadata = resolve_author_metadata(
			{
				"author_name": "GitLab User",
				"author_email": email,
			},
			lookup,
		)

		self.assertEqual(metadata["author_avatar_source"], "dinext_user")
		self.assertEqual(metadata["author_avatar_url"], "https://example.com/panel-meta.png")

	def test_resolve_author_metadata_uses_initials_when_no_avatar(self):
		metadata = resolve_author_metadata(
			{
				"author_name": "Fallback Author",
			},
			{},
		)

		self.assertEqual(metadata["author_avatar_source"], "initials")
		self.assertIsNone(metadata["author_avatar_url"])
		self.assertEqual(metadata["author_initials"], "FA")

	def test_build_summary_timestamps_aggregates_by_type(self):
		artifacts = [
			{"artifact_type": "branch", "updated_on": "2026-05-30 10:00:00"},
			{"artifact_type": "merge_request", "updated_on": "2026-05-30 12:00:00"},
			{"artifact_type": "branch", "updated_on": "2026-05-30 11:00:00"},
		]

		last_updated_on, last_by_type = build_summary_timestamps(artifacts)

		self.assertEqual(last_updated_on, "2026-05-30 12:00:00")
		self.assertEqual(last_by_type["branch"], "2026-05-30 11:00:00")
		self.assertEqual(last_by_type["merge_request"], "2026-05-30 12:00:00")
