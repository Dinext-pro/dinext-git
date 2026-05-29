from __future__ import annotations

import frappe


def execute():
	"""Alias types are embedded in DocType metadata; keep the patch for migration traceability."""
	frappe.logger("dinext_git.patch").info(
		"Development Key Alias types are already defined in metadata; bootstrap patch is a no-op."
	)
