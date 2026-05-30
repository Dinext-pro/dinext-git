"""Workspace metadata tests for the Разработки git-development cockpit.

v1 ships summary number cards, warning quick lists, report shortcuts and link cards.
v2 (deferred): dashboard charts, custom dev board block, additional KPI cards.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_JSON = APP_ROOT / "dinext_git" / "workspace" / "разработки" / "разработки.json"
NUMBER_CARD_FIXTURE = APP_ROOT / "fixtures" / "number_card.json"


class TestDevelopmentWorkspace(FrappeTestCase):
	def test_workspace_json_structure(self):
		payload = json.loads(WORKSPACE_JSON.read_text(encoding="utf-8"))
		self.assertEqual(payload["label"], "Разработки")
		self.assertEqual(payload["module"], "Dinext Git")
		self.assertEqual(len(payload["number_cards"]), 8)
		self.assertEqual(len(payload["quick_lists"]), 4)
		report_links = {
			link["link_to"] for link in payload["links"] if link.get("type") == "Link" and link.get("link_type") == "Report"
		}
		self.assertIn("GitLab Traceability Exceptions", report_links)
		self.assertIn("GitLab Release Composition", report_links)
		content = json.loads(payload["content"])
		block_types = {block["type"] for block in content}
		content_text = payload["content"]
		self.assertNotIn("Git-статусы work items", content_text)
		self.assertIn("number_card", block_types)
		self.assertIn("quick_list", block_types)
		self.assertIn("card", block_types)

	def test_number_card_fixture_matches_workspace(self):
		cards = json.loads(NUMBER_CARD_FIXTURE.read_text(encoding="utf-8"))
		workspace = json.loads(WORKSPACE_JSON.read_text(encoding="utf-8"))
		card_names = {row["name"] for row in cards}
		workspace_card_names = {row["number_card_name"] for row in workspace["number_cards"]}
		self.assertEqual(card_names, workspace_card_names)

	def test_workspace_is_installed(self):
		if not frappe.db.exists("Workspace", "Разработки"):
			self.skipTest("Workspace is available after dinext_git migrate on the test site")
		doc = frappe.get_doc("Workspace", "Разработки")
		self.assertEqual(doc.module, "Dinext Git")
		self.assertGreaterEqual(len(doc.number_cards), 8)
		self.assertGreaterEqual(len(doc.quick_lists), 4)
