frappe.listview_settings.Issue = {
	formatters: {
		custom_git_development_status(value) {
			return value ? __(value) : __("Not started");
		},
	},
};
