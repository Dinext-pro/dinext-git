// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

const WORKFLOW_RULE_METHOD = "dinext_git.dinext_git.doctype.development_workflow_rule.development_workflow_rule";

function set_select_options(frm, fieldname, options, current_value) {
	const normalized = [...new Set((options || []).filter(Boolean))];
	if (current_value && !normalized.includes(current_value)) {
		normalized.unshift(current_value);
	}
	frm.set_df_property(fieldname, "options", normalized.join("\n"));
	if (current_value && !normalized.includes(frm.doc[fieldname])) {
		frm.set_value(fieldname, "");
	}
}

function refresh_target_field_options(frm) {
	if (!frm.doc.target_doctype) {
		return Promise.resolve();
	}

	return frappe
		.call({
			method: `${WORKFLOW_RULE_METHOD}.get_target_field_options`,
			args: { target_doctype: frm.doc.target_doctype },
		})
		.then((response) => {
			const fields = (response.message || []).map((row) => row.fieldname);
			if (!fields.includes("status")) {
				fields.unshift("status");
			}
			set_select_options(frm, "target_fieldname", fields, frm.doc.target_fieldname || "status");
			if (!frm.doc.target_fieldname) {
				frm.set_value("target_fieldname", "status");
			}
		});
}

function refresh_target_value_options(frm) {
	if (!frm.doc.target_doctype || !frm.doc.target_fieldname) {
		return Promise.resolve();
	}

	return frappe
		.call({
			method: `${WORKFLOW_RULE_METHOD}.get_target_value_options`,
			args: {
				target_doctype: frm.doc.target_doctype,
				target_fieldname: frm.doc.target_fieldname,
			},
		})
		.then((response) => {
			const options = response.message || [];
			set_select_options(frm, "target_status", options, frm.doc.target_status);
			set_select_options(frm, "only_when_current_status", options, frm.doc.only_when_current_status);
		});
}

frappe.ui.form.on("Development Workflow Rule", {
	refresh(frm) {
		refresh_target_field_options(frm).then(() => refresh_target_value_options(frm));
	},
	target_doctype(frm) {
		frm.set_value("target_fieldname", "status");
		frm.set_value("target_status", "");
		frm.set_value("only_when_current_status", "");
		refresh_target_field_options(frm).then(() => refresh_target_value_options(frm));
	},
	target_fieldname(frm) {
		frm.set_value("target_status", "");
		frm.set_value("only_when_current_status", "");
		refresh_target_value_options(frm);
	},
});
