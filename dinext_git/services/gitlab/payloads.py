"""GitLab webhook payload helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe

_FRAPPE_FORM_KEYS = frozenset({"cmd", "data", "_"})


def read_webhook_payload() -> dict[str, Any]:
	"""Return the GitLab webhook JSON body.

	Frappe parses JSON request bodies into ``form_dict`` before whitelisted
	handlers run. Calling ``request.get_json()`` afterwards reads an already
	consumed stream and raises HTTP 400 on GitLab deliveries.
	"""
	if frappe.form_dict:
		return {key: value for key, value in frappe.form_dict.items() if key not in _FRAPPE_FORM_KEYS}

	if frappe.request:
		payload = frappe.request.get_json(silent=True)
		if isinstance(payload, dict):
			return payload
	return {}


def flatten_artifact_names(normalized: dict[str, Any]) -> list[str]:
	names: list[str] = []
	for value in (normalized or {}).values():
		if isinstance(value, str):
			names.append(value)
		elif isinstance(value, Iterable):
			for item in value:
				if isinstance(item, str):
					names.append(item)
	return names
