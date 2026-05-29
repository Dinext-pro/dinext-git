"""Whitelisted admin actions for GitLab webhook lifecycle."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.webhook_admin import sync_mapping_webhook, verify_mapping_webhook


@frappe.whitelist()
def sync(mapping_name: str, force: int = 0):
	return sync_mapping_webhook(mapping_name, force=bool(force))


@frappe.whitelist()
def verify(mapping_name: str):
	return verify_mapping_webhook(mapping_name)
