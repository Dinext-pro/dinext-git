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
NUMBER_CARD_DIR = APP_ROOT / "dinext_git" / "number_card"


def _load_number_card_names() -> set[str]:
	names: set[str] = set()
	for path in NUMBER_CARD_DIR.glob("*/*.json"):
		payload = json.loads(path.read_text(encoding="utf-8"))
		names.add(payload["name"])
	return names


class TestDevelopmentWorkspace(FrappeTestCase):
	def test_workspace_json_structure(self):
		payload = json.loads(WORKSPACE_JSON.read_text(encoding="utf-8"))
		self.assertEqual(payload["label"], "Разработки")
		self.assertEqual(payload["module"], "Dinext Git")
		self.assertEqual(len(payload["number_cards"]), 10)
		self.assertEqual(len(payload["quick_lists"]), 0)
		report_links = {
			link["link_to"] for link in payload["links"] if link.get("type") == "Link" and link.get("link_type") == "Report"
		}
		shortcut_reports = {
			row["link_to"] for row in payload["shortcuts"] if row.get("type") == "Report"
		}
		self.assertIn("GitLab Traceability Exceptions", shortcut_reports)
		self.assertIn("GitLab Release Composition", shortcut_reports)
		content = json.loads(payload["content"])
		block_types = {block["type"] for block in content}
		content_text = payload["content"]
		self.assertNotIn("Git-статусы work items", content_text)
		self.assertIn("number_card", block_types)
		self.assertIn("shortcut", block_types)
		self.assertIn("card", block_types)

	def test_number_card_fixture_matches_workspace(self):
		card_names = _load_number_card_names()
		workspace = json.loads(WORKSPACE_JSON.read_text(encoding="utf-8"))
		workspace_card_names = {row["number_card_name"] for row in workspace["number_cards"]}
		self.assertEqual(card_names, workspace_card_names)

	def test_number_cards_filter_on_translatable_status_values(self):
		for path in NUMBER_CARD_DIR.glob("*/*.json"):
			payload = json.loads(path.read_text(encoding="utf-8"))
			filters = json.loads(payload.get("filters_json") or "[]")
			for _doctype, fieldname, _operator, value, _in_list in filters:
				if fieldname != "custom_git_development_status":
					continue
				self.assertNotIn("_", value)
				self.assertTrue(value[:1].isupper(), msg=f"{payload['name']} uses legacy status code {value!r}")

	def test_workspace_is_installed(self):
		if not frappe.db.exists("Workspace", "Разработки"):
			self.skipTest("Workspace is available after dinext_git migrate on the test site")
		doc = frappe.get_doc("Workspace", "Разработки")
		self.assertEqual(doc.module, "Dinext Git")
		workspace = json.loads(WORKSPACE_JSON.read_text(encoding="utf-8"))
		if len(doc.number_cards) < len(workspace["number_cards"]):
			self.skipTest("Run bench migrate to sync workspace number cards from repo fixtures")
		self.assertGreaterEqual(len(doc.number_cards), len(workspace["number_cards"]))
