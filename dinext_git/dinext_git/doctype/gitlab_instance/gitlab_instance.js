// Copyright (c) 2026, Dinext and contributors
// For license information, please see license.txt

const DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT = "DinextGit.WebhookAdmin";

function format_bulk_webhook_summary(summary) {
	const lines = [
		__("Checked mappings: {0}", [summary.checked_count || 0], DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
		__("Synced mappings: {0}", [summary.synced_count || 0], DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
		__("Active mappings: {0}", [summary.active_count || 0], DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
		__(
			"Still problematic mappings: {0}",
			[summary.still_problematic_count || 0],
			DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT
		),
	];

	if (summary.error_count) {
		lines.push(
			__("Errors: {0}", [summary.error_count], DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT)
		);
	}

	const problematic = (summary.results || []).filter(
		(row) => row.status && row.status !== "active"
	);
	if (problematic.length) {
		lines.push("");
		lines.push(__("Problematic mappings:", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT));
		for (const row of problematic) {
			const label = row.gitlab_project_path || row.mapping;
			const detail = row.error || row.status;
			lines.push(`- ${label}: ${detail}`);
		}
	}

	return lines.join("<br>");
}

async function run_instance_webhook_verify_and_sync(frm) {
	const summary = await frappe.call({
		method: "dinext_git.api.gitlab_webhook_admin.verify_and_sync_instance",
		args: {
			instance_name: frm.doc.name,
		},
		freeze: true,
		freeze_message: __("Verifying and syncing GitLab webhooks...", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
	});

	const message = summary.message || {};
	if (!message.checked_count) {
		frappe.msgprint({
			title: __("GitLab webhooks", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
			message: __("No enabled GitLab project mappings were found for this instance.", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
			indicator: "orange",
		});
		return;
	}

	const indicator =
		message.still_problematic_count || message.error_count ? "orange" : "green";
	frappe.msgprint({
		title: __("GitLab webhooks", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
		message: format_bulk_webhook_summary(message),
		indicator,
	});
}

frappe.ui.form.on("GitLab Instance", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(
			__("Verify and Sync Webhooks", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT),
			() => run_instance_webhook_verify_and_sync(frm),
			__("Actions", null, DINEXT_GIT_WEBHOOK_ADMIN_CONTEXT)
		);
	},
});
