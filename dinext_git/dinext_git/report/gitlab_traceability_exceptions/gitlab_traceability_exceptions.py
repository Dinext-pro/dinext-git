from __future__ import annotations

from frappe import _

from dinext_git.services.reports.traceability import run


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"fieldname": "name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 220},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 180},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "artifact_name", "label": _("Artifact"), "fieldtype": "Data", "width": 220},
		{"fieldname": "artifact_status", "label": _("Artifact Status"), "fieldtype": "Data", "width": 130},
		{"fieldname": "target_doctype", "label": _("Target DocType"), "fieldtype": "Data", "width": 120},
		{"fieldname": "target_name", "label": _("Target Name"), "fieldtype": "Dynamic Link", "options": "target_doctype", "width": 160},
		{"fieldname": "web_url", "label": _("GitLab URL"), "fieldtype": "Data", "width": 260},
	]
	return columns, run(filters.get("mode") or "tasks_without_mr", filters)
