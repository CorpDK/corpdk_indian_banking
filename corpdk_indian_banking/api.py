from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file

from corpdk_indian_banking.services.config import list_importable_accounts
from corpdk_indian_banking.services.coverage_reconcile import reconcile_coverage
from corpdk_indian_banking.services.import_service import path_from_uploaded_file, preview_import, run_import


@frappe.whitelist()
def list_importable_accounts_api() -> list[dict]:
	return list_importable_accounts()


@frappe.whitelist()
def preview_import_api(
	bank_account: str,
	primary_file: str | None = None,
	companion_file: str | None = None,
	fy_hint: str | None = None,
	month_hint: str | None = None,
) -> dict:
	frappe.has_permission("Banking Statement Settings", "read", throw=True)
	primary_path = path_from_uploaded_file(primary_file) if primary_file else None
	companion_path = path_from_uploaded_file(companion_file) if companion_file else None
	return preview_import(
		bank_account,
		primary_path=primary_path,
		companion_path=companion_path,
		fy_hint=fy_hint,
		month_hint=month_hint,
	)


@frappe.whitelist()
def run_import_api(
	bank_account: str,
	primary_file: str,
	companion_file: str | None = None,
	fy_hint: str | None = None,
	month_hint: str | None = None,
	vault_evidence: int = 1,
) -> dict:
	frappe.has_permission("Banking Statement Settings", "write", throw=True)
	primary_path = path_from_uploaded_file(primary_file)
	companion_path = path_from_uploaded_file(companion_file) if companion_file else None
	return run_import(
		bank_account,
		primary_path=primary_path,
		companion_path=companion_path,
		fy_hint=fy_hint,
		month_hint=month_hint,
		vault_evidence=bool(vault_evidence),
	)


@frappe.whitelist()
def reconcile_coverage_api(
	bank_account: str | None = None,
	from_year: int | None = None,
	from_month: int | None = None,
	to_year: int | None = None,
	to_month: int | None = None,
	skip_verified: int = 1,
	force_reverify: int = 0,
) -> dict:
	"""Verify BT vs Drive evidence; refresh Statement Coverage Month; log issues (no BT changes)."""
	frappe.has_permission("Banking Statement Settings", "write", throw=True)
	return reconcile_coverage(
		bank_account=bank_account or None,
		from_year=from_year,
		from_month=from_month,
		to_year=to_year,
		to_month=to_month,
		skip_verified=bool(skip_verified),
		force_reverify=bool(force_reverify),
	)


@frappe.whitelist()
def upload_statement_file(filename: str, content: str, is_private: int = 1) -> dict:
	"""Save base64-less content from client upload; use with frappe.upload_file from desk."""
	frappe.has_permission("Banking Statement Settings", "write", throw=True)
	doc = save_file(filename, content, None, None, is_private=bool(is_private))
	return {"file_url": doc.file_url, "name": doc.name}