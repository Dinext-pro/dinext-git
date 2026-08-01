"""Author and timestamp metadata for Development panel payloads."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cstr, get_abbr


def _normalize_email(email: str | None) -> str | None:
	value = (email or "").strip().lower()
	return value or None


def build_user_avatar_lookup(emails: list[str | None]) -> dict[str, dict[str, Any]]:
	normalized = sorted({email for email in (_normalize_email(item) for item in emails) if email})
	if not normalized:
		return {}

	lookup: dict[str, dict[str, Any]] = {}
	for row in frappe.get_all(
		"User",
		filters={"email": ["in", normalized], "enabled": 1},
		fields=["email", "full_name", "name", "user_image"],
	):
		email = _normalize_email(row.get("email"))
		if email and email not in lookup:
			lookup[email] = row
	return lookup


def resolve_author_metadata(artifact: dict[str, Any], user_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
	author_name = (artifact.get("author_name") or "").strip()
	author_email = (artifact.get("author_email") or "").strip()
	gitlab_avatar = (artifact.get("author_avatar_url") or "").strip()

	display_name = author_name or author_email or ""
	tooltip_parts = [part for part in [author_name, author_email] if part]
	author_tooltip = " · ".join(dict.fromkeys(tooltip_parts)) if tooltip_parts else ""

	avatar_url = None
	avatar_source = "initials"

	if gitlab_avatar:
		avatar_url = gitlab_avatar
		avatar_source = "gitlab"
	else:
		user = user_lookup.get(_normalize_email(author_email) or "")
		if user and user.get("user_image"):
			avatar_url = user["user_image"]
			avatar_source = "dinext_user"
			if not display_name:
				display_name = user.get("full_name") or user.get("name") or author_email

	return {
		"author_display_name": display_name,
		"author_tooltip": author_tooltip,
		"author_avatar_url": avatar_url,
		"author_avatar_source": avatar_source,
		"author_initials": get_abbr(display_name or "?"),
	}


def decorate_artifact_row(artifact: dict[str, Any], user_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
	row = dict(artifact)
	modified = row.get("modified")
	row["updated_on"] = cstr(modified) if modified else None
	row.update(resolve_author_metadata(row, user_lookup))
	return row


def build_summary_timestamps(artifacts: list[dict[str, Any]]) -> tuple[str | None, dict[str, str]]:
	last_updated_on = None
	last_by_type: dict[str, str] = {}

	for artifact in artifacts:
		updated = artifact.get("updated_on")
		if not updated:
			continue
		if not last_updated_on or updated > last_updated_on:
			last_updated_on = updated

		artifact_type = artifact.get("artifact_type") or "unknown"
		current = last_by_type.get(artifact_type)
		if not current or updated > current:
			last_by_type[artifact_type] = updated

	return last_updated_on, last_by_type
