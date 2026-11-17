from __future__ import annotations

from typing import Any

import frappe


def get_settings() -> frappe.model.document.Document:
	return frappe.get_single("Banking Statement Settings")


def get_account_config(bank_account: str) -> dict[str, Any]:
	settings = get_settings()
	for row in settings.bank_account_configs or []:
		if row.bank_account == bank_account and row.enabled:
			return _merge_row(settings, row)
	frappe.throw(
		f"Bank Account {bank_account!r} is not enabled for statement import. "
		f"Configure it in Banking Statement Settings.",
		title="Missing import config",
	)


def _merge_row(settings, row) -> dict[str, Any]:
	drive_team = row.drive_team or settings.default_drive_team
	subpath = (row.drive_statements_root or "").strip()
	if not subpath:
		base = (row.drive_account_root or "").rstrip("/")
		default_sub = (settings.default_statements_subpath or "Statements/").strip("/")
		subpath = f"{base}/{default_sub}/" if base else default_sub
	elif not subpath.endswith("/"):
		subpath += "/"
	return {
		"bank_account": row.bank_account,
		"parser_code": frappe.db.get_value("Statement Parser", row.statement_parser, "parser_code"),
		"statement_parser": row.statement_parser,
		"account_mask": row.account_mask,
		"drive_team": drive_team,
		"drive_account_root": row.drive_account_root,
		"drive_statements_root": subpath,
		"statement_kind": row.statement_kind or "Savings",
		"transaction_id_prefix": row.transaction_id_prefix or "",
		"naming_series_rule": row.naming_series_rule or "transaction_year",
		"import_requires_primary": row.import_requires_primary or "xls",
		"recommend_companion_pdf": row.recommend_companion_pdf,
		"reject_cross_fy": settings.reject_cross_fy,
	}


def list_importable_accounts() -> list[dict[str, str]]:
	settings = get_settings()
	out = []
	for row in settings.bank_account_configs or []:
		if not row.enabled:
			continue
		out.append(
			{
				"bank_account": row.bank_account,
				"parser_code": frappe.db.get_value("Statement Parser", row.statement_parser, "parser_code"),
			}
		)
	return out