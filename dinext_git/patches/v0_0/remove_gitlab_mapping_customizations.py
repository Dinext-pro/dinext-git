from __future__ import annotations

import frappe

PROPERTY_SETTER_NAMES = (
	"GitLab Project Mapping-remote_webhook_id-read_only",
	"GitLab Project Mapping-gitlab_project_id-read_only",
	"GitLab Project Mapping-last_reconciled_release_at-read_only",
	"GitLab Project Mapping-webhook_status-read_only",
	"GitLab Project Mapping-webhook_last_error-read_only",
	"GitLab Project Mapping-last_reconciled_mr_at-read_only",
	"GitLab Project Mapping-webhook_callback_url-read_only",
	"GitLab Project Mapping-webhook_last_verified_on-read_only",
	"GitLab Project Mapping-last_reconciled_pipeline_at-read_only",
	"GitLab Project Mapping-project-hidden",
	"GitLab Project Mapping-project-reqd",
	"GitLab Project Mapping-project-in_list_view",
)

CUSTOM_FIELD_NAMES = ("GitLab Project Mapping-is_default",)


def execute():
	"""Drop legacy Property Setter / Custom Field rows superseded by DocType JSON."""
	for name in PROPERTY_SETTER_NAMES:
		if frappe.db.exists("Property Setter", name):
			frappe.delete_doc("Property Setter", name, force=True, ignore_permissions=True)

	for name in CUSTOM_FIELD_NAMES:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)

	frappe.clear_cache(doctype="GitLab Project Mapping")
