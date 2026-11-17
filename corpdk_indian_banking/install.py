from __future__ import annotations

import frappe

PARSERS = [
	{
		"parser_code": "icici_jasper_xls",
		"title": "ICICI Jasper XLS",
		"description": "ICICI net banking detailed statement (.xls) with Transaction Date header row.",
		"primary_extension": ".xls",
		"companion_extension": ".pdf",
		"import_primary_type": "xls",
		"parser_version": "2026.11.1",
		"is_active": 1,
	},
	{
		"parser_code": "amex_in_rewards_pdf",
		"title": "Amex India Rewards PDF",
		"description": "American Express India Rewards monthly statement PDF (layout parser).",
		"primary_extension": ".pdf",
		"companion_extension": "",
		"import_primary_type": "pdf",
		"parser_version": "2026.11.1",
		"is_active": 1,
	},
]


def _ensure_drive_team_link_titles() -> None:
	"""Same as Customize Form on Drive Team → Show Title in Link Fields (no Drive app code fork)."""
	if frappe.db.exists(
		"Property Setter",
		{"doc_type": "Drive Team", "property": "show_title_field_in_link", "doctype_or_field": "DocType"},
	):
		return
	frappe.make_property_setter(
		{
			"doctype": "Drive Team",
			"doctype_or_field": "DocType",
			"property": "show_title_field_in_link",
			"property_type": "Check",
			"value": "1",
		},
		is_system_generated=True,
	)


def _ensure_role() -> None:
	if frappe.db.exists("Role", "Statement Import Manager"):
		return
	frappe.get_doc({"doctype": "Role", "role_name": "Statement Import Manager", "desk_access": 1}).insert(
		ignore_permissions=True
	)


def _ensure_parsers() -> None:
	for row in PARSERS:
		if frappe.db.exists("Statement Parser", row["parser_code"]):
			doc = frappe.get_doc("Statement Parser", row["parser_code"])
			doc.update({k: v for k, v in row.items() if k != "parser_code"})
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Statement Parser", **row})
			doc.insert(ignore_permissions=True)


def _install_default_drive_team() -> str | None:
	"""Site-specific install default: site_config key ``indian_banking_default_drive_team`` (Drive Team name)."""
	raw = frappe.conf.get("indian_banking_default_drive_team")
	if not raw:
		return None
	if not frappe.db.exists("Drive Team", raw):
		frappe.log_error(
			title="Indian Banking install",
			message=f"site_config indian_banking_default_drive_team={raw!r} is not a Drive Team name",
		)
		return None
	return raw


def _ensure_settings() -> None:
	_ensure_parsers()
	doc = frappe.get_single("Banking Statement Settings")
	if not doc.default_drive_team:
		team = _install_default_drive_team()
		if team:
			doc.default_drive_team = team
	if not doc.default_statements_subpath:
		doc.default_statements_subpath = "Statements/"
	if doc.reject_cross_fy is None:
		doc.reject_cross_fy = 1
	doc.save(ignore_permissions=True)


def after_install() -> None:
	_ensure_drive_team_link_titles()
	_ensure_role()
	_ensure_settings()
	frappe.db.commit()


def after_migrate() -> None:
	_ensure_drive_team_link_titles()
	_ensure_parsers()
	_ensure_settings()
	frappe.db.commit()