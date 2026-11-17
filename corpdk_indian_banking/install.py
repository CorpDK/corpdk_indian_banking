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
		"parser_version": "2026.11.0",
		"is_active": 1,
	},
	{
		"parser_code": "amex_in_rewards_pdf",
		"title": "Amex India Rewards PDF",
		"description": "American Express India Rewards monthly statement PDF (layout parser).",
		"primary_extension": ".pdf",
		"companion_extension": "",
		"import_primary_type": "pdf",
		"parser_version": "2026.11.0",
		"is_active": 1,
	},
]

DEFAULT_CONFIGS = [
	{
		"bank_account": "ICICI Savings - Personal - ICICI Bank",
		"enabled": 1,
		"statement_parser": "icici_jasper_xls",
		"account_mask": "6788",
		"drive_account_root": "Banking/ICICI Savings - Personal/",
		"statement_kind": "Savings",
		"transaction_id_prefix": "ICICI|",
		"naming_series_rule": "transaction_year",
		"import_requires_primary": "xls",
		"recommend_companion_pdf": 1,
	},
	{
		"bank_account": "ICICI PPF - Personal - ICICI Bank",
		"enabled": 1,
		"statement_parser": "icici_jasper_xls",
		"account_mask": "4018",
		"drive_account_root": "Banking/ICICI PPF - Personal/",
		"statement_kind": "PPF",
		"transaction_id_prefix": "ICICI-PPF|",
		"naming_series_rule": "transaction_year",
		"import_requires_primary": "xls",
		"recommend_companion_pdf": 1,
	},
	{
		"bank_account": "CC Amex Rewards - Personal - American Express",
		"enabled": 1,
		"statement_parser": "amex_in_rewards_pdf",
		"account_mask": "",
		"drive_account_root": "Banking/CC Amex Rewards - Personal/",
		"statement_kind": "Amex",
		"transaction_id_prefix": "AMEX|",
		"naming_series_rule": "insertion_year",
		"import_requires_primary": "pdf",
		"recommend_companion_pdf": 0,
	},
]


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


def _personal_evidence_team() -> str | None:
	return frappe.db.get_value("Drive Team", {"title": "Personal Evidence"}, "name")


def _ensure_settings() -> None:
	_ensure_parsers()
	team = _personal_evidence_team()
	doc = frappe.get_single("Banking Statement Settings")
	if team and not doc.default_drive_team:
		doc.default_drive_team = team
	if not doc.default_statements_subpath:
		doc.default_statements_subpath = "Statements/"
	if doc.reject_cross_fy is None:
		doc.reject_cross_fy = 1
	existing = {r.bank_account for r in doc.bank_account_configs or []}
	for cfg in DEFAULT_CONFIGS:
		if cfg["bank_account"] in existing:
			continue
		if not frappe.db.exists("Bank Account", cfg["bank_account"]):
			continue
		doc.append("bank_account_configs", cfg)
	doc.save(ignore_permissions=True)


def after_install() -> None:
	_ensure_role()
	_ensure_settings()
	frappe.db.commit()


def after_migrate() -> None:
	_ensure_parsers()
	_ensure_settings()
	frappe.db.commit()