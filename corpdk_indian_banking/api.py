from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils.file_manager import save_file

from corpdk_indian_banking.services.config import list_importable_accounts
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
def upload_statement_file(filename: str, content: str, is_private: int = 1) -> dict:
	"""Save base64-less content from client upload; use with frappe.upload_file from desk."""
	frappe.has_permission("Banking Statement Settings", "write", throw=True)
	doc = save_file(filename, content, None, None, is_private=bool(is_private))
	return {"file_url": doc.file_url, "name": doc.name}