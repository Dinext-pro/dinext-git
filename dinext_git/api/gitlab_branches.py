"""Whitelisted API for GitLab branch actions."""

from __future__ import annotations

import frappe

from dinext_git.services.gitlab.branch_actions import (
	create_branch,
	get_branch_dialog_options,
	preview_branch,
)


@frappe.whitelist()
def preview(
	doctype: str,
	name: str,
	mapping_name: str | None = None,
	branch_template: str | None = None,
	base_branch: str | None = None,
):
	return preview_branch(doctype, name, mapping_name, branch_template, base_branch)


@frappe.whitelist()
def create(
	doctype: str,
	name: str,
	mapping_name: str | None = None,
	branch_template: str | None = None,
	base_branch: str | None = None,
):
	return create_branch(doctype, name, mapping_name, branch_template, base_branch)


@frappe.whitelist()
def options(doctype: str, name: str, mapping_name: str | None = None):
	return get_branch_dialog_options(doctype, name, mapping_name)
