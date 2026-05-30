frappe.query_reports["GitLab Traceability Exceptions"] = {
	filters: [
		{
			fieldname: "mode",
			label: __("Mode"),
			fieldtype: "Select",
			options: [
				{ value: "tasks_without_mr", label: __("Tasks without merge request") },
				{ value: "mr_without_task", label: __("Merge requests without task") },
				{ value: "failed_pipelines", label: __("Failed pipelines") },
				{ value: "stuck_reviews", label: __("Stuck reviews") },
				{ value: "tasks_in_release_without_merge", label: __("Tasks in release without merge") },
			],
			default: "tasks_without_mr",
			reqd: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname !== "web_url" || !value) {
			return value;
		}
		const url = String(value).trim();
		if (!url) {
			return value;
		}
		const safeUrl = frappe.utils.escape_html(url);
		return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>`;
	},
};
