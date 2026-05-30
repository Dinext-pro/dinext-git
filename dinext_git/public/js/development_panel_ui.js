frappe.provide("dinext_git.development_panel");

dinext_git.development_panel.DEVELOPMENT_STATUS_COLORS = {
	"Not started": "gray",
	"In progress": "orange",
	"Merged": "green",
	"Declined": "red",
	"Pipeline failed": "red",
	"Deployed": "cyan",
};

dinext_git.development_panel.get_development_status_color = function (statusCode) {
	return dinext_git.development_panel.DEVELOPMENT_STATUS_COLORS[statusCode] || "gray";
};

dinext_git.development_panel.format_mapping_select_label = function (row) {
	const path = row.gitlab_project_path || row.name;
	const host = row.gitlab_instance_host || row.gitlab_instance;
	return host ? `${path} @ ${host}` : path;
};

dinext_git.development_panel.build_mapping_select_options = function (options) {
	return (options || []).map((row) => ({
		value: row.name,
		label: dinext_git.development_panel.format_mapping_select_label(row),
	}));
};

dinext_git.development_panel.render_status_pill = function (summary) {
	const statusCode = summary.development_status || "Not started";
	const label = frappe.utils.escape_html(summary.development_status_label || __("Not started"));
	const color = dinext_git.development_panel.get_development_status_color(statusCode);
	return `<span class="indicator-pill ${color} no-indicator-dot">${label}</span>`;
};

dinext_git.development_panel.ARTIFACT_STATUS_COLORS = {
	merged: "green",
	success: "green",
	passed: "green",
	approved: "green",
	opened: "blue",
	open: "blue",
	active: "blue",
	running: "orange",
	pending: "orange",
	created: "cyan",
	closed: "red",
	declined: "red",
	failed: "red",
	failure: "red",
	canceled: "red",
	cancelled: "red",
	recorded: "gray",
};

dinext_git.development_panel.get_artifact_status_color = function (artifactType, statusCode) {
	const normalized = (statusCode || "").toLowerCase();
	const mapped = dinext_git.development_panel.ARTIFACT_STATUS_COLORS[normalized];
	if (mapped) {
		return mapped;
	}

	if (frappe.utils && frappe.utils.guess_colour) {
		const label = frappe.utils.to_title_case(normalized.replaceAll("_", " "));
		return frappe.utils.guess_colour(label);
	}

	return "gray";
};

dinext_git.development_panel.render_artifact_status_pill = function (row) {
	const statusCode = row.artifact_status || "n/a";
	const label = frappe.utils.escape_html(row.artifact_status_label || row.artifact_status || "n/a");
	const color = dinext_git.development_panel.get_artifact_status_color(row.artifact_type, statusCode);
	return `<span class="indicator-pill ${color} no-indicator-dot dinext-git-artifact-status">${label}</span>`;
};

dinext_git.development_panel.ensure_assets = function (callback) {
	frappe.require(["/assets/dinext_git/css/development_panel.css"], callback);
};

dinext_git.development_panel.render_author_chip = function (row) {
	if (!row.author_display_name && !row.author_tooltip) {
		return "";
	}

	const title = frappe.utils.escape_html(row.author_tooltip || row.author_display_name || "");
	if (row.author_avatar_url) {
		const url = frappe.utils.escape_html(row.author_avatar_url);
		return `<span class="dinext-git-author-chip" title="${title}">
			<span class="avatar avatar-xs">
				<span class="avatar-frame" style="background-image: url('${url}')"></span>
			</span>
		</span>`;
	}

	const initials = frappe.utils.escape_html(
		(row.author_initials || frappe.get_abbr(row.author_display_name || "?")).substr(0, 1)
	);
	return `<span class="dinext-git-author-chip" title="${title}">
		<span class="avatar avatar-xs">
			<div class="avatar-frame standard-image">${initials}</div>
		</span>
	</span>`;
};

dinext_git.development_panel.render_updated_on = function (timestamp) {
	if (!timestamp) {
		return "";
	}

	const absolute = frappe.datetime.str_to_user(timestamp);
	return `<span class="dinext-git-updated-on text-muted" title="${frappe.utils.escape_html(absolute)}">${frappe.datetime.comment_when(timestamp)}</span>`;
};

dinext_git.development_panel.render_artifact_item = function (row, { strongLink = false } = {}) {
	const label = frappe.utils.escape_html(row.artifact_name || row.ref_name || row.name);
	const linkContent = row.web_url
		? `<a href="${frappe.utils.escape_html(row.web_url)}" target="_blank" rel="noopener noreferrer">${label}</a>`
		: label;
	const nameMarkup = strongLink ? `<strong>${linkContent}</strong>` : linkContent;
	const statusPill = dinext_git.development_panel.render_artifact_status_pill(row);
	const updated = dinext_git.development_panel.render_updated_on(row.updated_on);
	const author = dinext_git.development_panel.render_author_chip(row);

	return `<li class="dinext-git-artifact-item">
		<div class="dinext-git-artifact-primary">${nameMarkup}</div>
		<div class="dinext-git-artifact-secondary">
			${statusPill}
			${updated}
			${author}
		</div>
	</li>`;
};

dinext_git.development_panel.render_type_label = function (artifactType, rows) {
	return frappe.utils.to_title_case((rows[0]?.artifact_type_label || artifactType).replaceAll("_", " "));
};

dinext_git.development_panel.render_type_section = function (artifactType, rows, { strongLink = false } = {}) {
	const label = dinext_git.development_panel.render_type_label(artifactType, rows);
	const count = rows.length;
	const items = rows
		.map((row) => dinext_git.development_panel.render_artifact_item(row, { strongLink }))
		.join("");

	return `<div class="dinext-git-type-section">
		<div class="dinext-git-type-header">
			<span class="dinext-git-type-label">${frappe.utils.escape_html(label)} (${count})</span>
		</div>
		<ul class="dinext-git-artifact-list list-unstyled mb-0">${items}</ul>
	</div>`;
};

dinext_git.development_panel.render_project_path = function (group) {
	const path = frappe.utils.escape_html(group.gitlab_project_path || "");
	if (!path) {
		return "";
	}

	if (group.gitlab_project_url) {
		const url = frappe.utils.escape_html(group.gitlab_project_url);
		return `<a href="${url}" target="_blank" rel="noopener noreferrer">${path}</a>`;
	}

	return path;
};

dinext_git.development_panel.render_project_section = function (group, { strongLink = false } = {}) {
	const typeSections = Object.entries(group.artifacts_by_type || {})
		.map(([artifactType, rows]) =>
			dinext_git.development_panel.render_type_section(artifactType, rows, { strongLink })
		)
		.join("");

	const defaultBadge = group.is_default
		? `<span class="indicator-pill gray no-indicator-dot dinext-git-default-badge">${__("★")}</span>`
		: "";

	return `<section class="dinext-git-project-section">
		<div class="dinext-git-project-header">
			<span class="dinext-git-project-path">${dinext_git.development_panel.render_project_path(group)}</span>
			${defaultBadge}
		</div>
		<div class="dinext-git-project-body">${typeSections}</div>
	</section>`;
};

dinext_git.development_panel.render_summary_chip = function (label, timestamp, { primary = false } = {}) {
	const primaryClass = primary ? " dinext-git-summary-chip--primary" : "";
	const labelText = frappe.utils.escape_html(label);
	return `<span class="dinext-git-summary-chip text-muted${primaryClass}">
		<span class="dinext-git-summary-chip-label">${labelText}:</span>
		${frappe.datetime.comment_when(timestamp)}
	</span>`;
};

dinext_git.development_panel.render_summary_meta = function (summary) {
	const lastByType = summary.last_updated_on_by_type || {};
	const typeEntries = Object.entries(lastByType);
	const chips = typeEntries
		.map(([artifactType, timestamp]) =>
			dinext_git.development_panel.render_summary_chip(
				frappe.utils.to_title_case(artifactType.replaceAll("_", " ")),
				timestamp
			)
		)
		.join("");

	const lastUpdated = summary.last_updated_on
		? dinext_git.development_panel.render_summary_chip(__("Last updated"), summary.last_updated_on, {
				primary: true,
			})
		: "";

	if (!lastUpdated && !chips) {
		return "";
	}

	return `<div class="dinext-git-summary-meta">${lastUpdated}${chips}</div>`;
};

dinext_git.development_panel.render_discrepancy_badges = function (summary) {
	const flags = (summary.discrepancy_badges || [])
		.map(
			(flag) =>
				`<span class="indicator-pill red no-indicator-dot" title="${frappe.utils.escape_html(flag.code)}">${frappe.utils.escape_html(flag.label)}</span>`
		)
		.join("");

	if (!flags) {
		return "";
	}

	return `<div class="dinext-git-discrepancy-badges">${flags}</div>`;
};

dinext_git.development_panel.render_status_count_markup = function (summary) {
	const statusCount = Number(summary.status_merge_request_count || 0);
	if (!statusCount) {
		return "";
	}

	const statusCountTitle = frappe.utils.escape_html(summary.status_merge_request_label || __("Merge requests"));
	if (summary.status_merge_request_url) {
		return `<a class="dinext-git-status-count" href="${frappe.utils.escape_html(summary.status_merge_request_url)}" target="_blank" rel="noopener noreferrer" title="${statusCountTitle}">${statusCount}</a>`;
	}

	return `<span class="dinext-git-status-count text-muted" title="${statusCountTitle}">${statusCount}</span>`;
};

dinext_git.development_panel.render_panel_header = function (summary) {
	const statusPill = dinext_git.development_panel.render_status_pill(summary);
	const statusCountMarkup = dinext_git.development_panel.render_status_count_markup(summary);
	const summaryMeta = dinext_git.development_panel.render_summary_meta(summary);
	const discrepancyBadges = dinext_git.development_panel.render_discrepancy_badges(summary);

	return `<header class="dinext-git-header">
		<div class="dinext-git-status-row">
			<span class="dinext-git-status-label">${__("Development status")}</span>
			<div class="dinext-git-status-value">
				${statusPill}${statusCountMarkup}
			</div>
		</div>
		${summaryMeta}
		${discrepancyBadges}
	</header>`;
};

dinext_git.development_panel.render_empty_state = function (payload) {
	const message = payload.empty_state_message || __("No development activity yet.");
	return `<div class="dinext-git-empty-state">
		<div class="dinext-git-empty-state-title">${__("No development activity")}</div>
		<p class="dinext-git-empty-state-message text-muted mb-0">${frappe.utils.escape_html(message)}</p>
	</div>`;
};

dinext_git.development_panel.render_grouped_artifacts = function (groupedArtifacts, { strongLink = false } = {}) {
	const sections = Object.values(groupedArtifacts || {})
		.map((group) => dinext_git.development_panel.render_project_section(group, { strongLink }))
		.join("");

	if (!sections) {
		return "";
	}

	return `<div class="dinext-git-body">${sections}</div>`;
};

dinext_git.development_panel.render_panel_html = function (payload, { strongLink = false } = {}) {
	const summary = payload.summary || {};
	const header = dinext_git.development_panel.render_panel_header(summary);
	const body =
		dinext_git.development_panel.render_grouped_artifacts(payload.grouped_artifacts, { strongLink }) ||
		dinext_git.development_panel.render_empty_state(payload);

	return `<div class="dinext-git-development">${header}${body}</div>`;
};
