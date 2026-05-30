from __future__ import annotations

import frappe

from dinext_git.services.gitlab.constants import DEVELOPMENT_STATUS_LEGACY_CODES, WORK_ITEM_DOCTYPES


def execute():
	"""Backfill legacy machine-code development statuses to canonical Select values."""
	for doctype in WORK_ITEM_DOCTYPES:
		for legacy_code, canonical_value in DEVELOPMENT_STATUS_LEGACY_CODES.items():
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype}`
				SET custom_git_development_status = %s
				WHERE custom_git_development_status = %s
				""",
				(canonical_value, legacy_code),
			)
	frappe.db.commit()
