"""Small helper utilities shared across Dinext Git services."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import frappe
from frappe import _


REF_HEADS_PREFIX = "refs/heads/"
REF_TAGS_PREFIX = "refs/tags/"


def branch_name_from_ref(ref: str | None) -> str | None:
	"""Return the Git branch name from a push hook ref, or None for non-branch refs."""
	ref = (ref or "").strip()
	if not ref.startswith(REF_HEADS_PREFIX):
		return None
	name = ref[len(REF_HEADS_PREFIX) :].strip()
	return name or None


def is_branch_ref(ref: str | None) -> bool:
	return branch_name_from_ref(ref) is not None


def tag_name_from_ref(ref: str | None) -> str | None:
	"""Return the Git tag name from a tag push hook ref, or None for non-tag refs."""
	ref = (ref or "").strip()
	if not ref.startswith(REF_TAGS_PREFIX):
		return None
	name = ref[len(REF_TAGS_PREFIX) :].strip()
	return name or None


def is_tag_ref(ref: str | None) -> bool:
	return tag_name_from_ref(ref) is not None


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


def coerce_project_dict(project: Any) -> dict[str, Any]:
	if isinstance(project, dict):
		return project
	if isinstance(project, str):
		parsed = parse_json(project, default={})
		return parsed if isinstance(parsed, dict) else {}
	return {}


def project_id_from_payload(payload: dict[str, Any]) -> str | int | None:
	project = coerce_project_dict(payload.get("project"))
	project_id = project.get("id") or project.get("project_id")
	if project_id in (None, ""):
		project_id = (payload.get("object_attributes") or {}).get("target_project_id")
	return project_id


def project_path_from_payload(payload: dict[str, Any]) -> str | None:
	project = coerce_project_dict(payload.get("project"))
	project_path = project.get("path_with_namespace")
	if project_path:
		return project_path

	namespace = project.get("namespace")
	path = project.get("path")
	if not path:
		return None
	if isinstance(namespace, dict):
		namespace = namespace.get("full_path") or namespace.get("path") or namespace.get("name")
	if isinstance(namespace, str) and namespace.strip():
		return f"{namespace.strip()}/{path.strip()}"
	return None
