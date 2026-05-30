const DINEXT_GIT_TASK_STATUS_LABELS = {
	not_started: __("Not started"),
	in_progress: __("In progress"),
	merged: __("Merged"),
	declined: __("Declined"),
	pipeline_failed: __("Pipeline failed"),
	deployed: __("Deployed"),
};

frappe.listview_settings.Task = {
	formatters: {
		custom_git_development_status(value) {
			return DINEXT_GIT_TASK_STATUS_LABELS[value] || value;
		},
	},
};
