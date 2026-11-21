frappe.ui.form.on("Statement Parser", {
	refresh(frm) {
		frm.disable_save_to_new_button();
		if (frm.is_new()) {
			frappe.msgprint({
				title: __("Not allowed"),
				message: __("Statement Parsers are created by the app on install/migrate."),
				indicator: "orange",
			});
			frappe.set_route("List", "Statement Parser");
			return;
		}
		[
			"parser_code",
			"title",
			"description",
			"primary_extension",
			"companion_extension",
			"import_primary_type",
			"parser_version",
		].forEach((field) => frm.set_df_property(field, "read_only", 1));
	},
});