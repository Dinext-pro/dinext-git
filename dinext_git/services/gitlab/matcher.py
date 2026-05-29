"""Resolve Dinext and legacy work-item keys from GitLab metadata."""

from __future__ import annotations

import re
from typing import Any

import frappe

from dinext_git.services.gitlab.constants import WORK_ITEM_DOCTYPES

DINEXT_KEY_PATTERN = re.compile(r"\b(?P<key>(?:TASK|ISS)-\d{4}-\d{5})\b", re.IGNORECASE)
LEGACY_KEY_PATTERN = re.compile(r"\b(?P<key>[A-Z][A-Z0-9]+-\d+)\b")


def extract_candidate_keys(*texts: str | None) -> list[str]:
	keys: list[str] = []
	for text in texts:
		if not text:
			continue
		for pattern in (DINEXT_KEY_PATTERN, LEGACY_KEY_PATTERN):
			for match in pattern.finditer(text):
				key = match.group("key").upper()
				if key not in keys:
					keys.append(key)
	return keys


def resolve_key(key: str) -> dict[str, Any] | None:
	key = (key or "").upper()
	if not key:
		return None

	for doctype in WORK_ITEM_DOCTYPES:
		if frappe.db.exists(doctype, key):
			doc = frappe.db.get_value(doctype, key, ["name", "project", "subject", "status"], as_dict=True)
			doc["doctype"] = doctype
			doc["resolved_by"] = "name"
			return doc

	alias = frappe.db.get_value(
		"Development Key Alias",
		{"alias_value": key, "enabled": 1},
		["target_doctype", "target_name", "alias_type"],
		as_dict=True,
	)
	if not alias:
		return None

	doc = frappe.db.get_value(
		alias["target_doctype"],
		alias["target_name"],
		["name", "project", "subject", "status"],
		as_dict=True,
	)
	if not doc:
		return None

	doc["doctype"] = alias["target_doctype"]
	doc["resolved_by"] = alias["alias_type"]
	return doc


def resolve_keys(*texts: str | None) -> list[dict[str, Any]]:
	resolved = []
	seen = set()
	for key in extract_candidate_keys(*texts):
		doc = resolve_key(key)
		if not doc:
			continue
		marker = (doc["doctype"], doc["name"])
		if marker in seen:
			continue
		seen.add(marker)
		doc["matched_key"] = key
		resolved.append(doc)
	return resolved
