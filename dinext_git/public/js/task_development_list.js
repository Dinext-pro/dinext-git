frappe.listview_settings.Task = {
	formatters: {
		custom_git_development_status(value) {
			return value ? __(value) : __("Not started");
		},
	},
};
