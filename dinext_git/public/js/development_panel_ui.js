frappe.provide("dinext_git.development_panel");

dinext_git.development_panel.DEVELOPMENT_STATUS_COLORS = {
	not_started: "gray",
	in_progress: "orange",
	merged: "green",
	declined: "red",
	pipeline_failed: "red",
	deployed: "cyan",
};

dinext_git.development_panel.get_development_status_color = function (statusCode) {
	return dinext_git.development_panel.DEVELOPMENT_STATUS_COLORS[statusCode] || "gray";
};

dinext_git.development_panel.render_status_pill = function (summary) {
	const statusCode = summary.development_status || "not_started";
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
		<div class="dinext-git-artifact-title">${nameMarkup}</div>
		<div class="dinext-git-artifact-meta">
			${statusPill}
			${updated}
			${author}
		</div>
	</li>`;
};

dinext_git.development_panel.render_type_heading = function (artifactType, rows, lastUpdatedByType) {
	const label = frappe.utils.to_title_case((rows[0]?.artifact_type_label || artifactType).replaceAll("_", " "));
	const typeUpdated = lastUpdatedByType?.[artifactType];
	const typeUpdatedMarkup = typeUpdated
		? `<span class="dinext-git-type-updated text-muted">${dinext_git.development_panel.render_updated_on(typeUpdated)}</span>`
		: "";
	return `<h6 class="dinext-git-type-heading">${label}${typeUpdatedMarkup}</h6>`;
};

dinext_git.development_panel.render_summary_meta = function (summary) {
	const lastUpdated = summary.last_updated_on
		? `<div class="dinext-git-last-updated text-muted">${__("Last updated")}: ${frappe.datetime.comment_when(summary.last_updated_on)}</div>`
		: "";
	const lastByType = summary.last_updated_on_by_type || {};
	const typeEntries = Object.entries(lastByType);
	const typeSummary = typeEntries.length
		? `<div class="dinext-git-type-summary">${typeEntries
				.map(
					([artifactType, timestamp]) =>
						`<span class="dinext-git-type-summary-item text-muted">${frappe.utils.to_title_case(artifactType.replaceAll("_", " "))}: ${frappe.datetime.comment_when(timestamp)}</span>`
				)
				.join("")}</div>`
		: "";

	if (!lastUpdated && !typeSummary) {
		return "";
	}

	return `<div class="dinext-git-summary-meta">${lastUpdated}${typeSummary}</div>`;
};

dinext_git.development_panel.render_grouped_artifacts = function (groupedArtifacts, summary, { strongLink = false } = {}) {
	const lastUpdatedByType = summary.last_updated_on_by_type || {};
	return Object.values(groupedArtifacts || {})
		.map((group) => {
			const typeSections = Object.entries(group.artifacts_by_type || {})
				.map(([artifactType, rows]) => {
					const items = rows
						.map((row) => dinext_git.development_panel.render_artifact_item(row, { strongLink }))
						.join("");
					return `<div class="mb-3">${dinext_git.development_panel.render_type_heading(artifactType, rows, lastUpdatedByType)}<ul class="list-unstyled mb-0">${items}</ul></div>`;
				})
				.join("");
			const defaultBadge = group.is_default
				? `<span class="indicator-pill gray no-indicator-dot ml-2">${__("★")}</span>`
				: "";
			return `<div class="mb-4">
				<h5>${frappe.utils.escape_html(group.gitlab_project_path || "")}${defaultBadge}</h5>
				${typeSections}
			</div>`;
		})
		.join("");
};

dinext_git.development_panel.render_panel_html = function (payload, { strongLink = false } = {}) {
	const summary = payload.summary || {};
	const flags = (summary.discrepancy_badges || [])
		.map((flag) => `<span class="indicator-pill red" title="${frappe.utils.escape_html(flag.code)}">${frappe.utils.escape_html(flag.label)}</span>`)
		.join(" ");
	const statusCount = Number(summary.status_merge_request_count || 0);
	const statusCountTitle = frappe.utils.escape_html(summary.status_merge_request_label || __("Merge requests"));
	const statusCountMarkup = statusCount
		? summary.status_merge_request_url
			? ` <a href="${frappe.utils.escape_html(summary.status_merge_request_url)}" target="_blank" rel="noopener noreferrer" title="${statusCountTitle}">(${statusCount})</a>`
			: ` <span class="text-muted" title="${statusCountTitle}">(${statusCount})</span>`
		: "";
	const sections = dinext_git.development_panel.render_grouped_artifacts(payload.grouped_artifacts, summary, {
		strongLink,
	});
	const body =
		sections || `<p class="text-muted">${payload.empty_state_message || __("No development activity yet.")}</p>`;
	const summaryMeta = dinext_git.development_panel.render_summary_meta(summary);

	const statusPill = dinext_git.development_panel.render_status_pill(summary);

	return `<div class="dinext-git-development">
		<div class="mb-2">
			<div class="dinext-git-status-row">
				<strong>${__("Development status")}:</strong>
				${statusPill}${statusCountMarkup}
			</div>
			${summaryMeta}
			${flags ? `<div class="mt-2 dinext-git-discrepancy-badges">${flags}</div>` : ""}
		</div>
		${body}
	</div>`;
};
