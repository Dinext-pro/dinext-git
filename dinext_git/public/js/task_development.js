function set_gitlab_visibility(frm, { showTab, showButton }) {
	frm.set_df_property("custom_gitlab_tab", "hidden", showTab ? 0 : 1);
	frm.set_df_property("custom_gitlab_create_branch", "hidden", showTab && showButton ? 0 : 1);
	frm.set_df_property("custom_gitlab_panel", "hidden", showTab ? 0 : 1);
	frm.refresh_fields(["custom_gitlab_tab", "custom_gitlab_create_branch", "custom_gitlab_panel"]);
}

async function trigger_create_branch(frm) {
	const payload = frm.__dinext_git_payload || {};
	const preview = payload.branch_preview || null;
	if (!payload.can_create_branch || !preview) {
		return;
	}

	let mappingName = payload.default_mapping_name || preview?.mapping?.name || null;
	const options = payload.branch_mapping_options || [];
	if (options.length > 1) {
		const values = await frappe.prompt(
			[
				{
					fieldtype: "Select",
					fieldname: "mapping_name",
					label: __("GitLab project"),
					reqd: 1,
					default: mappingName,
					options: options.map((row) => row.name),
				},
			],
			null,
			__("Create Branch"),
			__("Continue")
		);
		mappingName = values.mapping_name;
	}

	await frappe.call({
		method: "dinext_git.api.gitlab_branches.create",
		args: { doctype: frm.doctype, name: frm.doc.name, mapping_name: mappingName },
	});
	await frm.reload_doc();
}

async function render_dinext_git_panel(frm) {
	frm.__dinext_git_payload = null;

	if (frm.is_new()) {
		set_gitlab_visibility(frm, { showTab: false, showButton: false });
		return;
	}

	const response = await frappe.call({
		method: "dinext_git.api.development_panel.get_panel",
		args: { doctype: frm.doctype, name: frm.doc.name },
	});

	const payload = response.message || {};
	const panel = frm.get_field("custom_gitlab_panel");
	if (!payload.show_gitlab_tab || !panel) {
		set_gitlab_visibility(frm, { showTab: false, showButton: false });
		if (panel?.$wrapper) {
			panel.$wrapper.empty();
		}
		return;
	}

	frm.__dinext_git_payload = payload;
	set_gitlab_visibility(frm, {
		showTab: true,
		showButton: Boolean(payload.can_create_branch && payload.branch_preview),
	});
	const summary = payload.summary || {};
	const preview = payload.branch_preview || null;
	const showBranchMappingDetails = Boolean(payload.show_branch_mapping_details);
	const sections = Object.values(payload.grouped_artifacts || {})
		.map((group) => {
			const typeSections = Object.entries(group.artifacts_by_type || {})
				.map(([artifactType, rows]) => {
					const items = rows
						.map((row) => {
							const label = row.artifact_name || row.ref_name || row.name;
							const link = row.web_url
								? `<a href="${row.web_url}" target="_blank" rel="noopener noreferrer">${label}</a>`
								: label;
							return `<li><strong>${link}</strong> <span class="text-muted">(${row.artifact_status_label || row.artifact_status || "n/a"})</span></li>`;
						})
						.join("");
					return `<div class="mb-3"><h6>${frappe.utils.to_title_case((rows[0]?.artifact_type_label || artifactType).replaceAll("_", " "))}</h6><ul>${items}</ul></div>`;
				})
				.join("");
			const defaultBadge = group.is_default ? `<span class="indicator-pill green ml-2">${__("Default")}</span>` : "";
			return `<div class="mb-4">
				<h5>${group.gitlab_project_path}${defaultBadge}</h5>
				${typeSections}
			</div>`;
		})
		.join("");

	const flags = (summary.discrepancy_badges || [])
		.map((flag) => `<span class="indicator-pill red" title="${flag.code}">${flag.label}</span>`)
		.join(" ");
	const body = sections || `<p class="text-muted">${payload.empty_state_message || __("No development activity yet.")}</p>`;
	const previewBlock = preview
		? `<div class="mb-3 text-muted">
			<div><strong>${__("Branch preview")}:</strong> <code>${preview.branch_name}</code></div>
			${
				showBranchMappingDetails
					? `<div><strong>${__("GitLab project")}:</strong> ${preview.mapping?.gitlab_project_path || "-"}</div>`
					: ""
			}
			<div><strong>${__("Base branch")}:</strong> <code>${preview.base_branch}</code></div>
		</div>`
		: "";

	panel.$wrapper.html(
		`<div class="dinext-git-development">
			<div class="mb-2">
				<strong>${__("Development status")}:</strong> ${summary.development_status_label || __("Not started")}
				${flags ? `<div class="mt-2">${flags}</div>` : ""}
			</div>
			${previewBlock}
			${body}
		</div>`
	);
}

frappe.ui.form.on("Task", {
	refresh(frm) {
		render_dinext_git_panel(frm);
	},
	custom_gitlab_create_branch(frm) {
		return trigger_create_branch(frm);
	},
});
