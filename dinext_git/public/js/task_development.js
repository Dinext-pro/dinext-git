function set_gitlab_visibility(frm, { showTab, showButton }) {
	frm.set_df_property("custom_gitlab_tab", "hidden", showTab ? 0 : 1);
	frm.set_df_property("custom_gitlab_create_branch", "hidden", showTab && showButton ? 0 : 1);
	frm.set_df_property("custom_gitlab_panel", "hidden", showTab ? 0 : 1);
	frm.refresh_fields(["custom_gitlab_tab", "custom_gitlab_create_branch", "custom_gitlab_panel"]);
}

async function get_branch_options(frm, mappingName) {
	const response = await frappe.call({
		method: "dinext_git.api.gitlab_branches.options",
		args: {
			doctype: frm.doctype,
			name: frm.doc.name,
			mapping_name: mappingName,
		},
	});
	return response.message || {};
}

async function get_branch_preview(frm, { mappingName, branchTemplate, baseBranch }) {
	const response = await frappe.call({
		method: "dinext_git.api.gitlab_branches.preview",
		args: {
			doctype: frm.doctype,
			name: frm.doc.name,
			mapping_name: mappingName,
			branch_template: branchTemplate,
			base_branch: baseBranch,
		},
	});
	return response.message || {};
}

function set_base_branch_options(dialog, branchNames, selectedBranch) {
	const field = dialog.get_field("base_branch");
	if (!field) {
		return;
	}
	field.df.options = branchNames || [];
	field.refresh();
	if (selectedBranch) {
		dialog.set_value("base_branch", selectedBranch);
	}
}

function set_dialog_help(dialog, message, cssClass = "text-muted") {
	const field = dialog.get_field("preview_help");
	if (!field?.$wrapper) {
		return;
	}
	field.$wrapper.html(message ? `<p class="${cssClass} mb-0">${frappe.utils.escape_html(message)}</p>` : "");
}

async function open_create_branch_dialog(frm, payload) {
	const preview = payload.branch_preview || null;
	const options = payload.branch_mapping_options || [];
	const mappingNames = options.map((row) => row.name);
	const defaultMappingName =
		payload.default_mapping_name || preview?.mapping?.name || mappingNames[0] || null;
	const defaultBranchTemplate =
		payload.default_branch_template || preview?.branch_template || "feature/{key}-{slug}";
	const defaultBaseBranch = payload.default_base_branch || preview?.base_branch || "develop";
	const initialBaseBranches = payload.available_base_branches || [defaultBaseBranch];

	const dialog = new frappe.ui.Dialog({
		title: __("Create Branch"),
		fields: [
			...(options.length > 1
				? [
						{
							fieldtype: "Select",
							fieldname: "mapping_name",
							label: __("GitLab project"),
							reqd: 1,
							default: defaultMappingName,
							options: mappingNames,
						},
					]
				: []),
			{
				fieldtype: "Data",
				fieldname: "branch_template",
				label: __("Branch naming template"),
				reqd: 1,
				default: defaultBranchTemplate,
				description: __("One-time override for this branch creation. Mapping defaults are not changed."),
			},
			{
				fieldtype: "Select",
				fieldname: "base_branch",
				label: __("Base branch"),
				reqd: 1,
				default: defaultBaseBranch,
				options: initialBaseBranches,
			},
			{
				fieldtype: "Data",
				fieldname: "branch_name_preview",
				label: __("Branch preview"),
				read_only: 1,
			},
			{
				fieldtype: "HTML",
				fieldname: "preview_help",
			},
		],
		primary_action_label: __("Create"),
		primary_action: async (values) => {
			if (!dialog.__preview) {
				await updatePreview();
				if (!dialog.__preview) {
					return;
				}
			}

			await frappe.call({
				method: "dinext_git.api.gitlab_branches.create",
				args: {
					doctype: frm.doctype,
					name: frm.doc.name,
					mapping_name: values.mapping_name || defaultMappingName,
					branch_template: values.branch_template,
					base_branch: values.base_branch,
				},
			});
			dialog.hide();
			await frm.reload_doc();
		},
	});

	let previewRequestId = 0;
	let optionsRequestId = 0;

	const getSelectedMappingName = () =>
		options.length > 1 ? dialog.get_value("mapping_name") : defaultMappingName;

	const loadMappingOptions = async () => {
		const requestId = ++optionsRequestId;
		const mappingName = getSelectedMappingName();
		if (!mappingName) {
			return;
		}

		dialog.get_primary_btn().prop("disabled", true);
		set_dialog_help(dialog, __("Loading branch options..."));

		try {
			const mappingOptions = await get_branch_options(frm, mappingName);
			if (requestId !== optionsRequestId) {
				return;
			}

			dialog.set_value("branch_template", mappingOptions.branch_template || defaultBranchTemplate);
			set_base_branch_options(
				dialog,
				mappingOptions.available_base_branches || [],
				mappingOptions.base_branch || defaultBaseBranch
			);
			dialog.__preview = mappingOptions.branch_preview || null;
			dialog.set_value("branch_name_preview", dialog.__preview?.branch_name || "");
			dialog.get_primary_btn().prop("disabled", !dialog.__preview);
			set_dialog_help(dialog, dialog.__preview ? "" : __("Unable to build branch preview."));
		} catch (error) {
			if (requestId !== optionsRequestId) {
				return;
			}
			dialog.__preview = null;
			dialog.set_value("branch_name_preview", "");
			dialog.get_primary_btn().prop("disabled", true);
			set_dialog_help(dialog, error?.message || __("Unable to load branch options."), "text-danger");
		}
	};

	const updatePreview = async () => {
		const requestId = ++previewRequestId;
		const mappingName = getSelectedMappingName();
		const branchTemplate = (dialog.get_value("branch_template") || "").trim();
		const baseBranch = dialog.get_value("base_branch");

		if (!mappingName) {
			dialog.__preview = null;
			dialog.set_value("branch_name_preview", "");
			dialog.get_primary_btn().prop("disabled", true);
			set_dialog_help(dialog, __("Select a GitLab project to preview the branch name."));
			return;
		}

		if (!branchTemplate) {
			dialog.__preview = null;
			dialog.set_value("branch_name_preview", "");
			dialog.get_primary_btn().prop("disabled", true);
			set_dialog_help(dialog, __("Enter a branch naming template to preview the branch name."));
			return;
		}

		if (!baseBranch) {
			dialog.__preview = null;
			dialog.set_value("branch_name_preview", "");
			dialog.get_primary_btn().prop("disabled", true);
			set_dialog_help(dialog, __("Select a base branch to preview the branch name."));
			return;
		}

		dialog.get_primary_btn().prop("disabled", true);
		set_dialog_help(dialog, __("Loading branch preview..."));

		try {
			const nextPreview = await get_branch_preview(frm, {
				mappingName,
				branchTemplate,
				baseBranch,
			});
			if (requestId !== previewRequestId) {
				return;
			}

			dialog.__preview = nextPreview;
			dialog.set_value("branch_name_preview", nextPreview.branch_name || "");
			dialog.get_primary_btn().prop("disabled", false);
			set_dialog_help(dialog, "");
		} catch (error) {
			if (requestId !== previewRequestId) {
				return;
			}

			dialog.__preview = null;
			dialog.set_value("branch_name_preview", "");
			dialog.get_primary_btn().prop("disabled", true);
			set_dialog_help(dialog, error?.message || __("Unable to build branch preview."), "text-danger");
		}
	};

	dialog.show();
	set_base_branch_options(dialog, initialBaseBranches, defaultBaseBranch);
	if (options.length > 1) {
		dialog.get_field("mapping_name").$input?.on("change", loadMappingOptions);
	}
	const debouncedPreviewUpdate = frappe.utils.debounce(updatePreview, 250);
	dialog.get_field("branch_template").$input?.on("input", debouncedPreviewUpdate);
	dialog.get_field("branch_template").$input?.on("change", updatePreview);
	dialog.get_field("base_branch").$input?.on("change", updatePreview);
	await updatePreview();
}

async function trigger_create_branch(frm) {
	const payload = frm.__dinext_git_payload || {};
	if (!payload.can_create_branch) {
		return;
	}
	await open_create_branch_dialog(frm, payload);
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
		showButton: Boolean(payload.can_create_branch),
	});
	const summary = payload.summary || {};
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
	const statusCount = Number(summary.status_merge_request_count || 0);
	const statusCountTitle = frappe.utils.escape_html(summary.status_merge_request_label || __("Merge requests"));
	const statusCountMarkup = statusCount
		? summary.status_merge_request_url
			? ` <a href="${summary.status_merge_request_url}" target="_blank" rel="noopener noreferrer" title="${statusCountTitle}">(${statusCount})</a>`
			: ` <span class="text-muted" title="${statusCountTitle}">(${statusCount})</span>`
		: "";
	const body = sections || `<p class="text-muted">${payload.empty_state_message || __("No development activity yet.")}</p>`;

	panel.$wrapper.html(
		`<div class="dinext-git-development">
			<div class="mb-2">
				<strong>${__("Development status")}:</strong> ${summary.development_status_label || __("Not started")}${statusCountMarkup}
				${flags ? `<div class="mt-2">${flags}</div>` : ""}
			</div>
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
