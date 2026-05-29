from __future__ import annotations

import frappe


def execute():
	"""Custom fields are provisioned via MCP/UI and exported to fixtures; keep patch for auditability."""
	frappe.logger("dinext_git.patch").info(
		"Dinext Git development summary fields are managed through metadata export; bootstrap patch is a no-op."
	)
