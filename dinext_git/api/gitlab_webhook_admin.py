"""Whitelisted admin actions for GitLab webhook lifecycle."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.webhook_admin import (
	sync_mapping_webhook,
	verify_and_sync_instance_webhooks,
	verify_mapping_webhook,
)


@frappe.whitelist()
def sync(mapping_name: str, force: int = 0):
	return sync_mapping_webhook(mapping_name, force=bool(force))


@frappe.whitelist()
def verify(mapping_name: str):
	return verify_mapping_webhook(mapping_name)


@frappe.whitelist()
def verify_and_sync_instance(instance_name: str):
	frappe.has_permission("GitLab Instance", "write", throw=True)
	return verify_and_sync_instance_webhooks(instance_name)
