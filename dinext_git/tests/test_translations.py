from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from frappe.tests.utils import FrappeTestCase

APP_ROOT = Path(__file__).resolve().parents[1]


def collect_translatable_strings() -> set[str]:
	strings: set[str] = set()

	def add(value: str | None) -> None:
		if value and str(value).strip():
			strings.add(str(value).strip())

	for path in (APP_ROOT / "dinext_git/doctype").glob("*/*.json"):
		data = json.loads(path.read_text(encoding="utf-8"))
		add(data.get("name"))
		add(data.get("description"))
		for field in data.get("fields", []):
			add(field.get("label"))
			add(field.get("description"))
			options = field.get("options")
			if options and field.get("fieldtype") in {"Select", "MultiSelect"}:
				for option in options.split("\n"):
					add(option)

	for custom_field in json.loads((APP_ROOT / "fixtures/custom_field.json").read_text(encoding="utf-8")):
		add(custom_field.get("label"))
		add(custom_field.get("description"))

	for path in APP_ROOT.rglob("*"):
		if path.suffix not in {".py", ".js"}:
			continue
		if "node_modules" in path.parts:
			continue
		text = path.read_text(encoding="utf-8", errors="ignore")
		for match in re.finditer(r'(?:_\(|__\()\s*f?["\']([^"\']+)["\']', text):
			add(match.group(1))

	for path in (APP_ROOT / "dinext_git/report").glob("*/*.json"):
		data = json.loads(path.read_text(encoding="utf-8"))
		add(data.get("name"))
		add(data.get("report_name"))

	return strings


def load_ru_translations() -> dict[str, str]:
	translations: dict[str, str] = {}
	with open(APP_ROOT / "translations/ru.csv", newline="", encoding="utf-8") as handle:
		for row in csv.reader(handle):
			if len(row) >= 2 and row[0]:
				translations[row[0]] = row[1]
	return translations


class TestTranslations(FrappeTestCase):
	def test_all_translatable_strings_have_ru_translation(self):
		strings = collect_translatable_strings()
		translations = load_ru_translations()
		missing = sorted(string for string in strings if string not in translations)
		self.assertEqual(missing, [])
