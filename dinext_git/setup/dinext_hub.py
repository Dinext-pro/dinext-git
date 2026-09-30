# Copyright (c) 2026, Dinext and contributors
# For license information, please see license.txt

"""Register this app's default Dinext Hub cards."""

from __future__ import annotations

import frappe

APP_NAME = 'dinext_git'

HUB_ITEMS = (
	{
		"section": 'My Work',
		"element_type": 'Workspace',
		"target": 'Разработки',
		"label": 'Development',
		"description": 'GitLab-linked development operations: task and issue status, discrepancies, pipeline failures, traceability exceptions, releases, and artifacts.',
		"icon": 'stock',
	},
)


def register_dinext_hub_items() -> None:
	if "dinext_common" not in frappe.get_installed_apps():
		return

	try:
		from dinext_common.setup.hub_catalog import register_hub_items, relocate_hub_item_section
	except ImportError:
		return

	register_hub_items(HUB_ITEMS, source_app=APP_NAME)
	relocate_hub_item_section(
		element_type="Workspace",
		target="Разработки",
		section="My Work",
	)
