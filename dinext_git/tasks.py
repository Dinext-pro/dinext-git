"""Scheduled Dinext Git jobs."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.reconcile import reconcile_all_enabled_mappings, verify_all_mapping_webhooks


def run_hourly_reconciliation():
	if frappe.flags.in_migrate:
		return
	return reconcile_all_enabled_mappings()


def run_daily_reconciliation():
	if frappe.flags.in_migrate:
		return
	return reconcile_all_enabled_mappings()


def verify_webhook_health():
	if frappe.flags.in_migrate:
		return
	return verify_all_mapping_webhooks()
