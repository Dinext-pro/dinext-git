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
};
