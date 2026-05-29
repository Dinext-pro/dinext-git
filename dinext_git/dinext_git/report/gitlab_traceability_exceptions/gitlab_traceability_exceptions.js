frappe.query_reports["GitLab Traceability Exceptions"] = {
	filters: [
		{
			fieldname: "mode",
			label: __("Mode"),
			fieldtype: "Select",
			options: [
				"tasks_without_mr",
				"mr_without_task",
				"failed_pipelines",
				"stuck_reviews",
				"tasks_in_release_without_merge",
			].join("\n"),
			default: "tasks_without_mr",
			reqd: 1,
		},
	],
};
