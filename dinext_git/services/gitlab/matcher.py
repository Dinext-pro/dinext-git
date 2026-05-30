"""Resolve Dinext and legacy work-item keys from GitLab metadata."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import frappe

from dinext_git.services.gitlab.constants import WORK_ITEM_DOCTYPES

# Backward-compatible legacy pattern for Jira-style keys.
LEGACY_KEY_PATTERN = re.compile(r"\b(?P<key>[A-Z][A-Z0-9]+-\d+)\b")
GENERIC_KEY_TOKEN = re.compile(
	r"\b(?P<key>[A-Z][A-Z0-9]{1,}(?:[-._][A-Z0-9]+)*)\b",
	re.IGNORECASE,
)

_NAMING_SERIES_NUMERIC = re.compile(r"^#+$")
_NAMING_SERIES_DATE_PARTS = frozenset({"YY", "YYYY", "MM", "DD", "WW"})


def naming_series_to_regex(series: str) -> str:
	"""Convert a Frappe naming series / autoname expression into a regex fragment."""
	parts = (series or "").split(".")
	regex_parts: list[str] = []
	for part in parts:
		if not part:
			continue
		if _NAMING_SERIES_NUMERIC.match(part):
			regex_parts.append(rf"\d{{{len(part)}}}")
		elif part in _NAMING_SERIES_DATE_PARTS:
			regex_parts.append(r"\d{2}" if part in {"YY", "MM", "DD", "WW"} else r"\d{4}")
		elif part == "timestamp":
			regex_parts.append(r".+?")
		else:
			regex_parts.append(re.escape(part))
	return "".join(regex_parts)


def _collect_doctype_name_patterns(doctype: str) -> list[re.Pattern[str]]:
	meta = frappe.get_meta(doctype)
	autoname = (meta.autoname or "").strip()
	raw_series: list[str] = []

	if not autoname or autoname.lower() == "hash":
		pass
	elif autoname.lower().startswith("prompt"):
		pass
	elif autoname.lower().startswith("naming_series:"):
		for option in meta.get_naming_series_options() or []:
			if option:
				raw_series.append(f"{option}.#####")
	elif autoname.lower().startswith("format:") or autoname.lower().startswith("field:"):
		pass
	elif "#" in autoname:
		raw_series.append(autoname)

	patterns: list[re.Pattern[str]] = []
	for series in raw_series:
		regex = naming_series_to_regex(series)
		if regex:
			patterns.append(re.compile(rf"\b({regex})\b", re.IGNORECASE))
	return patterns


@lru_cache(maxsize=1)
def _get_meta_key_patterns() -> tuple[re.Pattern[str], ...]:
	patterns: list[re.Pattern[str]] = []
	for doctype in WORK_ITEM_DOCTYPES:
		patterns.extend(_collect_doctype_name_patterns(doctype))
	return tuple(patterns)


def clear_matcher_caches() -> None:
	"""Clear cached meta/alias lookups (for tests and metadata changes)."""
	_get_meta_key_patterns.cache_clear()
	_get_enabled_alias_values.cache_clear()


@lru_cache(maxsize=1)
def _get_enabled_alias_values() -> tuple[str, ...]:
	if not frappe.db.table_exists("Development Key Alias"):
		return ()
	aliases = frappe.get_all(
		"Development Key Alias",
		filters={"enabled": 1},
		pluck="alias_value",
	)
	return tuple(sorted({(alias or "").strip().upper() for alias in aliases if alias}, key=len, reverse=True))


def _append_unique_key(keys: list[str], seen: set[str], key: str) -> None:
	normalized = (key or "").strip()
	if not normalized:
		return
	lookup = normalized.upper()
	if lookup in seen:
		return
	seen.add(lookup)
	keys.append(normalized)


def _extract_meta_pattern_keys(text: str, seen: set[str]) -> list[str]:
	keys: list[str] = []
	for pattern in _get_meta_key_patterns():
		for match in pattern.finditer(text):
			_append_unique_key(keys, seen, match.group(1))
	return keys


def _extract_alias_keys(text: str, seen: set[str]) -> list[str]:
	upper_text = text.upper()
	keys: list[str] = []
	for alias in _get_enabled_alias_values():
		if alias in upper_text:
			_append_unique_key(keys, seen, alias)
	return keys


def _expand_key_prefix_candidates(token: str) -> list[str]:
	"""Try full token and progressively shorter hyphen prefixes for branch slug suffixes."""
	candidates: list[str] = []
	parts = (token or "").split("-")
	for end in range(len(parts), 0, -1):
		candidate = "-".join(parts[:end])
		if candidate and candidate not in candidates:
			candidates.append(candidate)
	return candidates


def _extract_generic_token_keys(text: str, seen: set[str]) -> list[str]:
	keys: list[str] = []
	for match in GENERIC_KEY_TOKEN.finditer(text):
		for candidate in _expand_key_prefix_candidates(match.group("key")):
			_append_unique_key(keys, seen, candidate)
	return keys


def _extract_legacy_pattern_keys(text: str, seen: set[str]) -> list[str]:
	keys: list[str] = []
	for match in LEGACY_KEY_PATTERN.finditer(text):
		_append_unique_key(keys, seen, match.group("key"))
	return keys


def extract_candidate_keys(*texts: str | None) -> list[str]:
	keys: list[str] = []
	seen: set[str] = set()
	for text in texts:
		if not text:
			continue
		keys.extend(_extract_meta_pattern_keys(text, seen))
		keys.extend(_extract_alias_keys(text, seen))
		keys.extend(_extract_generic_token_keys(text, seen))
		keys.extend(_extract_legacy_pattern_keys(text, seen))
	return keys


def _lookup_work_item_by_name(name: str) -> dict[str, Any] | None:
	for doctype in WORK_ITEM_DOCTYPES:
		if frappe.db.exists(doctype, name):
			doc = frappe.db.get_value(doctype, name, ["name", "project", "subject", "status"], as_dict=True)
			doc["doctype"] = doctype
			doc["resolved_by"] = "name"
			return doc
	return None


def resolve_key(key: str) -> dict[str, Any] | None:
	key = (key or "").strip()
	if not key:
		return None

	for candidate in dict.fromkeys([key, key.upper()]):
		doc = _lookup_work_item_by_name(candidate)
		if doc:
			return doc

	upper_key = key.upper()
	if not frappe.db.table_exists("Development Key Alias"):
		return None

	alias = frappe.db.get_value(
		"Development Key Alias",
		{"alias_value": upper_key, "enabled": 1},
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
