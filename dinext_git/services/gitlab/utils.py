"""Small helper utilities shared across Dinext Git services."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import frappe
from frappe import _


def slugify_fragment(value: str, *, max_length: int = 48) -> str:
	"""Build a Git-safe slug for branch naming."""
	value = re.sub(r"[^\w\s/-]+", "", (value or "").strip().lower(), flags=re.UNICODE)
	value = value.replace("/", "-")
	value = re.sub(r"[\s_]+", "-", value)
	value = re.sub(r"-{2,}", "-", value).strip("-")
	return value[:max_length].strip("-")


def make_uid(*parts: Any) -> str:
	"""Create a deterministic short UID from ordered parts."""
	normalized = "||".join("" if part is None else str(part) for part in parts)
	return hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def json_dumps(payload: Any) -> str:
	return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def parse_json(value: str | None, *, default: Any) -> Any:
	if not value:
		return default

	try:
		return json.loads(value)
	except json.JSONDecodeError:
		frappe.log_error(title=_("Dinext Git invalid JSON"), message=value)
		return default
