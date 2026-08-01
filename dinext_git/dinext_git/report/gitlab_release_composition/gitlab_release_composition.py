from __future__ import annotations

from frappe import _

from dinext_git.services.reports.release_composition import run


def execute(filters=None):
	columns = [
		{"fieldname": "target_doctype", "label": _("Target DocType"), "fieldtype": "Data", "width": 120},
		{"fieldname": "target_name", "label": _("Target Name"), "fieldtype": "Dynamic Link", "options": "target_doctype", "width": 160},
		{"fieldname": "release_names", "label": _("Release Artifacts"), "fieldtype": "Data", "width": 220},
		{"fieldname": "deployment_statuses", "label": _("Deployment Statuses"), "fieldtype": "Data", "width": 160},
		{"fieldname": "release_urls", "label": _("Release URLs"), "fieldtype": "Data", "width": 260},
	]
	return columns, run(filters or {})
