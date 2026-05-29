"""Whitelisted API for GitLab branch actions."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.branch_actions import create_branch, preview_branch


@frappe.whitelist()
def preview(doctype: str, name: str, mapping_name: str | None = None):
	return preview_branch(doctype, name, mapping_name)


@frappe.whitelist()
def create(doctype: str, name: str, mapping_name: str | None = None):
	return create_branch(doctype, name, mapping_name)
