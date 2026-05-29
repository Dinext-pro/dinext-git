"""GitLab webhook payload helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


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
