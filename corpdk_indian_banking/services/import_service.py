from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import getdate

from corpdk_indian_banking.parsers.registry import get_parser
from corpdk_indian_banking.services import bank_transaction, evidence, fy
from corpdk_indian_banking.services.config import get_account_config
from corpdk_indian_banking.services.drive_vault import attach_drive_link, vault_file


def _txn_dates(rows: list[dict]) -> list[date]:
	return [getdate(r["date"]) for r in rows if r.get("date")]


def _covered_months(dates: list[date]) -> list[str]:
	out = sorted({f"{d.year:04d}-{d.month:02d}" for d in dates})
	return out


def _save_upload(upload, suffix: str) -> Path:
	content = upload.read()
	dest = Path(tempfile.mkdtemp()) / f"stmt{suffix}"
	dest.write_bytes(content)
	return dest


def preview_import(
	bank_account: str,
	*,
	primary_path: Path | None = None,
	companion_path: Path | None = None,
	fy_hint: str | None = None,
	month_hint: str | None = None,
) -> dict[str, Any]:
	return _run(
		bank_account,
		primary_path=primary_path,
		companion_path=companion_path,
		fy_hint=fy_hint,
		month_hint=month_hint,
		dry_run=True,
	)


def run_import(
	bank_account: str,
	*,
	primary_path: Path,
	companion_path: Path | None = None,
	fy_hint: str | None = None,
	month_hint: str | None = None,
	vault_evidence: bool = True,
) -> dict[str, Any]:
	return _run(
		bank_account,
		primary_path=primary_path,
		companion_path=companion_path,
		fy_hint=fy_hint,
		month_hint=month_hint,
		dry_run=False,
		vault_evidence=vault_evidence,
	)


def _run(
	bank_account: str,
	*,
	primary_path: Path | None,
	companion_path: Path | None,
	fy_hint: str | None,
	month_hint: str | None,
	dry_run: bool,
	vault_evidence: bool = True,
) -> dict[str, Any]:
	cfg = get_account_config(bank_account)
	if not primary_path:
		frappe.throw("Primary statement file is required.")
	primary_suffix = primary_path.suffix.lower()
	required = f".{cfg['import_requires_primary']}"
	if primary_suffix != required and not (required == ".xls" and primary_suffix == ".xlsx"):
		frappe.throw(f"Primary file must be {required}, got {primary_suffix}")
	if cfg["import_requires_primary"] == "xls" and companion_path and companion_path.suffix.lower() != ".pdf":
		frappe.throw("Companion evidence for ICICI must be a .pdf")

	parser = get_parser(cfg["parser_code"])
	parse_result = parser.parse_file(primary_path, transaction_id_prefix=cfg["transaction_id_prefix"])

	dates = _txn_dates(parse_result.rows)
	if not dates:
		frappe.throw("No transactions parsed.")

	if cfg["reject_cross_fy"]:
		indian_fy = fy.assert_single_fy(dates)
	else:
		indian_fy = fy.indian_fy_for_date(parse_result.period_end)

	ps, pe = min(dates), max(dates)
	covered = _covered_months(dates)

	if month_hint:
		mh = month_hint.strip()
		if mh not in covered and not dry_run:
			frappe.msgprint(
				f"Hint month {mh} not in parsed months {', '.join(covered)}.",
				indicator="orange",
				alert=True,
			)

	vault_plan = []
	company = frappe.db.get_value("Bank Account", bank_account, "company")
	currency = frappe.db.get_value("Bank Account", bank_account, "account_currency") or "INR"

	if cfg["parser_code"] == "icici_jasper_xls":
		xls_name = evidence.build_icici_filename(
			kind=cfg["statement_kind"],
			mask=cfg["account_mask"],
			period_end=getdate(pe),
			fy=indian_fy,
			period_start=getdate(ps),
			ext="xls",
		)
		xls_path = evidence.vault_logical_path(cfg["drive_statements_root"], indian_fy, xls_name)
		vault_plan.append({"role": "Primary XLS", "logical_path": xls_path, "local": str(primary_path)})
		if companion_path:
			pdf_name = evidence.build_icici_filename(
				kind=cfg["statement_kind"],
				mask=cfg["account_mask"],
				period_end=getdate(pe),
				fy=indian_fy,
				period_start=getdate(ps),
				ext="pdf",
			)
			pdf_path = evidence.vault_logical_path(cfg["drive_statements_root"], indian_fy, pdf_name)
			vault_plan.append({"role": "Companion PDF", "logical_path": pdf_path, "local": str(companion_path)})
	elif cfg["parser_code"] == "amex_in_rewards_pdf":
		close = getdate(parse_result.statement_close_date)
		fy_close = fy.indian_fy_for_date(close)
		pdf_name = evidence.build_amex_filename(close_date=close, fy=fy_close)
		logical = evidence.vault_logical_path(cfg["drive_statements_root"], fy_close, pdf_name)
		vault_plan.append({"role": "Primary PDF", "logical_path": logical, "local": str(primary_path)})

	existing = set()
	if dry_run and parse_result.rows:
		prefix = cfg["transaction_id_prefix"] or parse_result.rows[0]["transaction_id"].split("|", 1)[0] + "|"
		if cfg["parser_code"] == "amex_in_rewards_pdf":
			existing = set(
				frappe.db.sql_list(
					"select transaction_id from `tabBank Transaction` where transaction_id like 'AMEX|%'"
				)
			)
		else:
			existing = set(
				frappe.db.sql_list(
					"select transaction_id from `tabBank Transaction` where transaction_id like %s",
					(f"{prefix}%",),
				)
			)
	to_create = 0
	to_skip = 0
	for row in parse_result.rows:
		if bank_transaction.already_imported(
			row, existing, amex=cfg["parser_code"] == "amex_in_rewards_pdf"
		):
			to_skip += 1
		else:
			to_create += 1

	result = {
		"bank_account": bank_account,
		"parser_code": cfg["parser_code"],
		"period_start": str(ps),
		"period_end": str(pe),
		"indian_fy": indian_fy.label,
		"fy_folder": indian_fy.folder_name(),
		"covered_months": covered,
		"rows_parsed": len(parse_result.rows),
		"rows_to_create": to_create,
		"rows_to_skip": to_skip,
		"vault_plan": vault_plan,
		"pdf_missing": cfg["recommend_companion_pdf"] and not companion_path,
		"dry_run": dry_run,
		"fy_hint": fy_hint,
	}

	if dry_run:
		return result

	batch = frappe.get_doc(
		{
			"doctype": "Statement Import Batch",
			"bank_account": bank_account,
			"statement_parser": cfg["statement_parser"],
			"status": "Importing",
			"period_start": ps,
			"period_end": pe,
			"indian_fy": indian_fy.label,
			"covered_months_json": frappe.as_json(covered),
			"rows_parsed": len(parse_result.rows),
			"dry_run": 0,
		}
	)
	batch.insert(ignore_permissions=True)

	drive_results = []
	if vault_evidence:
		for item in vault_plan:
			vr = vault_file(Path(item["local"]), item["logical_path"], cfg["drive_team"])
			drive_results.append(vr)
			batch.append(
				"import_files",
				{
					"file_role": item["role"],
					"drive_logical_path": item["logical_path"],
					"drive_entity": vr.get("entity"),
					"vault_status": vr.get("status"),
				},
			)
			if vr.get("entity"):
				attach_drive_link(vr["entity"], Path(item["logical_path"]).name, "Bank Account", bank_account)

	created, skipped = bank_transaction.insert_rows(
		parse_result.rows,
		bank_account=bank_account,
		company=company,
		currency=currency,
		naming_series_rule=cfg["naming_series_rule"],
		transaction_id_prefix=cfg["transaction_id_prefix"],
		amex=cfg["parser_code"] == "amex_in_rewards_pdf",
	)
	bank_transaction.resync_bank_transaction_series()

	batch.rows_created = created
	batch.rows_skipped = skipped
	batch.status = "Completed"
	batch.save(ignore_permissions=True)
	_update_coverage(bank_account, covered, cfg, companion_path is not None, batch.name)

	frappe.db.commit()
	result["batch"] = batch.name
	result["rows_created"] = created
	result["rows_skipped"] = skipped
	result["drive"] = drive_results
	return result


def _update_coverage(
	bank_account: str,
	covered: list[str],
	cfg: dict,
	has_pdf: bool,
	batch_name: str,
) -> None:
	for ym in covered:
		year_s, month_s = ym.split("-")
		year, month = int(year_s), int(month_s)
		name = frappe.db.exists(
			"Statement Coverage Month",
			{"bank_account": bank_account, "year": year, "month": month},
		)
		status = "Complete" if has_pdf or not cfg["recommend_companion_pdf"] else "PDF missing"
		if cfg["import_requires_primary"] == "pdf":
			status = "Complete"
		payload = {
			"last_batch": batch_name,
			"transactions_imported": 1,
			"evidence_status": status,
			"xls_in_drive": 1 if cfg["import_requires_primary"] == "xls" else 0,
			"pdf_in_drive": 1 if has_pdf else 0,
		}
		if name:
			doc = frappe.get_doc("Statement Coverage Month", name)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Statement Coverage Month",
					"bank_account": bank_account,
					"year": year,
					"month": month,
					**payload,
				}
			)
			doc.insert(ignore_permissions=True)


def path_from_uploaded_file(file_url: str) -> Path:
	"""Resolve a File doc or site path to local path for parsing."""
	if file_url.startswith("/files/") or file_url.startswith("/private/"):
		site_path = frappe.get_site_path("public", file_url.lstrip("/"))
		if not Path(site_path).exists():
			site_path = frappe.get_site_path(file_url.lstrip("/"))
		return Path(site_path)
	if frappe.db.exists("File", {"file_url": file_url}):
		f = frappe.get_doc("File", frappe.db.get_value("File", {"file_url": file_url}))
		return Path(f.get_full_path())
	frappe.throw(f"Cannot resolve file: {file_url}")