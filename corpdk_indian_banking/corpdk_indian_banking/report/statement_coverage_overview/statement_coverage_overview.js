frappe.query_reports["Statement Coverage Overview"] = {
	filters: [
		{
			fieldname: "bank_account",
			label: __("Bank Account"),
			fieldtype: "Link",
			options: "Bank Account",
		},
		{
			fieldname: "from_year",
			label: __("From Year"),
			fieldtype: "Int",
		},
		{
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Int",
		},
		{
			fieldname: "to_year",
			label: __("To Year"),
			fieldtype: "Int",
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Int",
		},
	],
	onload(report) {
		report.page.add_inner_button(__("Run Verification"), () => {
			const fields = [
				{
					fieldname: "bank_account",
					label: __("Bank Account"),
					fieldtype: "Link",
					options: "Bank Account",
					default: report.get_filter_value("bank_account"),
					description: __("Leave blank to verify all enabled accounts in Banking Statement Settings."),
				},
				{
					fieldname: "from_year",
					label: __("From Year"),
					fieldtype: "Int",
					default: report.get_filter_value("from_year"),
				},
				{
					fieldname: "from_month",
					label: __("From Month"),
					fieldtype: "Int",
					default: report.get_filter_value("from_month"),
				},
				{
					fieldname: "to_year",
					label: __("To Year"),
					fieldtype: "Int",
					default: report.get_filter_value("to_year"),
				},
				{
					fieldname: "to_month",
					label: __("To Month"),
					fieldtype: "Int",
					default: report.get_filter_value("to_month"),
				},
				{
					fieldname: "skip_verified",
					label: __("Skip months already verified"),
					fieldtype: "Check",
					default: 1,
					description: __("Recommended. Verified months are those with a Last Verified timestamp."),
				},
			];
			if (frappe.user.has_role("System Manager")) {
				fields.push({
					fieldname: "force_reverify",
					label: __("Force re-verify all in scope (admin)"),
					fieldtype: "Check",
					default: 0,
					description: __("Re-run verification even for months that were already verified."),
				});
			}
			frappe.prompt(
				fields,
				(values) => {
					frappe.call({
						method: "corpdk_indian_banking.api.reconcile_coverage_api",
						args: {
							bank_account: values.bank_account || null,
							from_year: values.from_year || null,
							from_month: values.from_month || null,
							to_year: values.to_year || null,
							to_month: values.to_month || null,
							skip_verified: values.skip_verified ? 1 : 0,
							force_reverify: values.force_reverify ? 1 : 0,
						},
						freeze: true,
						freeze_message: __("Verifying coverage (read-only)…"),
						callback(r) {
							if (!r.message) return;
							const m = r.message;
							frappe.msgprint({
								title: __("Verification complete"),
								message: __("Run {0}: {1} months updated, {2} skipped, {3} issues.", [
									m.run,
									m.months_updated || 0,
									m.months_skipped || 0,
									m.issues || 0,
								]),
								indicator: m.issues ? "orange" : "green",
							});
							report.refresh();
						},
					});
				},
				__("Run statement coverage verification"),
				__("Verify")
			);
		});
	},
};