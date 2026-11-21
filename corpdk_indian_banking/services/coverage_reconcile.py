"""Read-only reconciliation: BT rows, Drive evidence, parser counts → coverage + issues."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import get_datetime, now, getdate

from corpdk_indian_banking.parsers.registry import get_parser
from corpdk_indian_banking.services.config import _merge_row, get_settings
from corpdk_indian_banking.services.import_service import _covered_months, _txn_dates


def reconcile_coverage(
	*,
	bank_account: str | None = None,
	from_year: int | None = None,
	from_month: int | None = None,
	to_year: int | None = None,
	to_month: int | None = None,
	skip_verified: bool = True,
	force_reverify: bool = False,
) -> dict[str, Any]:
	"""Verify imports vs Drive evidence; update Statement Coverage Month; log issues. No BT writes."""
	frappe.has_permission("Banking Statement Settings", "write", throw=True)
	if force_reverify and "System Manager" not in frappe.get_roles():
		frappe.throw("Only System Manager can force re-verification.", title="Not permitted")

	settings = get_settings()
	scope = {
		"bank_account": bank_account,
		"from_year": from_year,
		"from_month": from_month,
		"to_year": to_year,
		"to_month": to_month,
		"skip_verified": skip_verified,
		"force_reverify": force_reverify,
	}
	accounts: list[str] = []
	for row in settings.bank_account_configs or []:
		if not row.enabled:
			continue
		if bank_account and row.bank_account != bank_account:
			continue
		accounts.append(row.bank_account)

	if not accounts:
		frappe.throw("No enabled bank accounts to verify.")

	run = frappe.get_doc(
		{
			"doctype": "Statement Coverage Verification Run",
			"status": "Running",
			"started_at": now(),
			"triggered_by": frappe.session.user,
			"account_scope": ", ".join(accounts),
			"issue_count": 0,
		}
	)
	run.insert(ignore_permissions=True)
	frappe.db.commit()
	_supersede_open_issues(accounts, run.name)

	summary: dict[str, Any] = {"scope": scope, "accounts": {}, "issues": 0, "months_updated": 0, "months_skipped": 0}

	try:
		for acct in accounts:
			cfg = _merge_row(settings, _config_row(settings, acct))
			summary["accounts"][acct] = _reconcile_account(
				acct,
				cfg,
				run.name,
				summary,
				from_year=from_year,
				from_month=from_month,
				to_year=to_year,
				to_month=to_month,
				skip_verified=skip_verified and not force_reverify,
			)
		run.status = "Completed"
	except Exception:
		run.status = "Failed"
		raise
	finally:
		run.completed_at = now()
		run.issue_count = summary.get("issues", 0)
		run.summary_json = frappe.as_json(summary)
		run.save(ignore_permissions=True)
		frappe.db.commit()

	return {"run": run.name, **summary}


def _supersede_open_issues(bank_accounts: list[str], run_name: str) -> None:
	for acct in bank_accounts:
		for row in frappe.get_all(
			"Statement Coverage Issue",
			filters={"bank_account": acct, "status": "Open"},
			pluck="name",
		):
			doc = frappe.get_doc("Statement Coverage Issue", row)
			doc.status = "Resolved"
			doc.detail = (doc.detail or "") + f" [Superseded by {run_name}]"
			doc.save(ignore_permissions=True)


def _month_already_verified(bank_account: str, year: int, month: int) -> bool:
	return bool(
		frappe.db.get_value(
			"Statement Coverage Month",
			{"bank_account": bank_account, "year": year, "month": month},
			"last_verified_at",
		)
	)


def _config_row(settings, bank_account: str):
	for row in settings.bank_account_configs or []:
		if row.bank_account == bank_account:
			return row
	frappe.throw(f"No config for {bank_account!r}")


def _reconcile_account(
	bank_account: str,
	cfg: dict[str, Any],
	run_name: str,
	summary: dict[str, Any],
	*,
	from_year: int | None,
	from_month: int | None,
	to_year: int | None,
	to_month: int | None,
	skip_verified: bool,
) -> dict[str, Any]:
	bt_by_month = _bt_counts_by_month(bank_account)
	xls_files, pdf_titles = _drive_statement_index(cfg)
	parsed_by_month: dict[str, int] = defaultdict(int)
	xls_by_month: set[str] = set()
	pdf_by_month: set[str] = set()
	file_for_month: dict[str, str] = {}

	for f in xls_files:
		months, per_month, err = _parse_drive_xls(f, cfg)
		if err:
			y, m = _period_from_statement_title(f.get("title") or "")
			_log_issue(
				run_name,
				bank_account,
				y,
				m,
				"Parse Failed",
				err,
				reference_file=f.get("title"),
			)
			summary["issues"] = summary.get("issues", 0) + 1
			continue
		base = (f.get("title") or "").rsplit(".", 1)[0]
		has_pdf = f"{base}.pdf" in pdf_titles or f"{base}.PDF" in pdf_titles
		for ym in months:
			if ym in xls_by_month and ym in file_for_month:
				y, m = _ym_parts(ym)
				_log_issue(
					run_name,
					bank_account,
					y,
					m,
					"Ambiguous Coverage",
					f"Multiple XLS cover {ym}: {file_for_month[ym]!r} and {f.get('title')!r}",
					reference_file=f.get("title"),
				)
				summary["issues"] = summary.get("issues", 0) + 1
			xls_by_month.add(ym)
			file_for_month[ym] = f.get("title") or ""
			parsed_by_month[ym] += per_month.get(ym, 0)
			if has_pdf:
				pdf_by_month.add(ym)

	all_months = sorted(set(bt_by_month) | xls_by_month)
	acct_summary = {"months": 0, "months_skipped": 0, "issues": 0}
	verified_at = now()

	for ym in all_months:
		year, month = _ym_parts(ym)
		if not _month_in_range(year, month, from_year, from_month, to_year, to_month):
			continue
		if skip_verified and _month_already_verified(bank_account, year, month):
			acct_summary["months_skipped"] += 1
			summary["months_skipped"] = summary.get("months_skipped", 0) + 1
			continue
		acct_summary["months"] += 1
		bt_count = bt_by_month.get(ym, 0)
		parsed_count = parsed_by_month.get(ym, 0)
		has_xls = ym in xls_by_month
		has_pdf = ym in pdf_by_month
		has_bt = bt_count > 0

		status = _evidence_status(cfg, has_xls, has_pdf, has_bt)
		issues_here = _check_month_issues(
			run_name,
			bank_account,
			year,
			month,
			ym,
			bt_count,
			parsed_count,
			has_xls,
			has_pdf,
			cfg,
			file_for_month.get(ym, ""),
		)
		acct_summary["issues"] += len(issues_here)
		summary["issues"] = summary.get("issues", 0) + len(issues_here)

		_upsert_coverage_month(
			bank_account,
			year,
			month,
			has_xls,
			has_pdf,
			has_bt,
			bt_count,
			parsed_count,
			status,
			run_name,
			verified_at,
		)
		summary["months_updated"] = summary.get("months_updated", 0) + 1

	return acct_summary


def _bt_counts_by_month(bank_account: str) -> dict[str, int]:
	rows = frappe.db.sql(
		"""
		SELECT YEAR(`date`) AS y, MONTH(`date`) AS m, COUNT(*) AS c
		FROM `tabBank Transaction`
		WHERE bank_account = %s AND `date` IS NOT NULL
		GROUP BY y, m
		""",
		bank_account,
		as_dict=True,
	)
	return {f"{int(r.y):04d}-{int(r.m):02d}": int(r.c) for r in rows}


def _drive_statement_index(cfg: dict[str, Any]) -> tuple[list[dict], set[str]]:
	team = cfg.get("drive_team")
	if not team:
		return [], set()
	path_needle = (cfg.get("drive_account_root") or "").strip("/")
	mask = cfg.get("account_mask") or ""
	kind = cfg.get("statement_kind") or ""

	files = frappe.get_all(
		"Drive File",
		filters={"is_group": 0, "is_active": 1, "team": team},
		fields=["name", "title", "path", "mime_type"],
		limit_page_length=0,
	)
	xls: list[dict] = []
	pdf_titles: set[str] = set()
	for f in files:
		path = f.path or ""
		if path_needle and path_needle not in path:
			continue
		if "/Statements/" not in path:
			continue
		title = f.title or ""
		if mask and mask not in title:
			continue
		if kind and kind not in title:
			continue
		low = title.lower()
		if low.endswith(".xls") or low.endswith(".xlsx"):
			xls.append(f)
		elif low.endswith(".pdf"):
			pdf_titles.add(title)

	return xls, pdf_titles


def _parse_drive_xls(
	file_row: dict,
	cfg: dict[str, Any],
) -> tuple[list[str], dict[str, int], str | None]:
	path = _drive_local_path(file_row["name"], cfg["drive_team"])
	if not path:
		return [], {}, f"Drive file not on disk: {file_row.get('title')}"
	try:
		parser = get_parser(cfg["parser_code"])
		result = parser.parse_file(path, transaction_id_prefix=cfg["transaction_id_prefix"])
	except Exception as exc:
		return [], {}, f"{file_row.get('title')}: {exc}"

	dates = _txn_dates(result.rows)
	months = _covered_months(dates) if dates else []
	per_month: dict[str, int] = defaultdict(int)
	for row in result.rows:
		if not row.get("date"):
			continue
		d = getdate(row["date"])
		per_month[f"{d.year:04d}-{d.month:02d}"] += 1
	return months, dict(per_month), None


def _drive_local_path(entity: str, team: str) -> Path | None:
	path = frappe.db.get_value("Drive File", entity, "path")
	if path:
		site_file = Path(frappe.get_site_path("private", "files", path))
		if site_file.is_file():
			return site_file
	frappe.set_user("Administrator")
	from drive.utils import get_home_folder
	from drive.utils.files import FileManager

	try:
		doc = frappe.get_doc("Drive File", entity)
		home = get_home_folder(team)
		disk = FileManager().get_disk_path(doc, home)
	except Exception:
		return None
	if not disk:
		return None
	p = Path(disk)
	return p if p.is_file() else None


def _evidence_status(cfg: dict, has_xls: bool, has_pdf: bool, has_bt: bool) -> str:
	if not has_xls and not has_bt:
		return "Nothing"
	if not has_xls and has_bt:
		return "XLS missing"
	if has_xls and cfg.get("recommend_companion_pdf") and not has_pdf:
		return "PDF missing"
	if has_xls or has_bt:
		return "Complete"
	return "Nothing"


def _check_month_issues(
	run_name: str,
	bank_account: str,
	year: int,
	month: int,
	ym: str,
	bt_count: int,
	parsed_count: int,
	has_xls: bool,
	has_pdf: bool,
	cfg: dict,
	ref_file: str,
) -> list[str]:
	out: list[str] = []
	if bt_count and not has_xls:
		_log_issue(
			run_name,
			bank_account,
			year,
			month,
			"BT Without Evidence",
			f"{ym}: {bt_count} BT rows, no statement XLS in Drive for this month.",
		)
		out.append("BT Without Evidence")
	elif has_xls and not bt_count and parsed_count:
		_log_issue(
			run_name,
			bank_account,
			year,
			month,
			"Evidence Without BT",
			f"{ym}: XLS covers {parsed_count} parsed rows but no Bank Transactions.",
			ref_file,
		)
		out.append("Evidence Without BT")
	if has_xls and not has_pdf and cfg.get("recommend_companion_pdf"):
		_log_issue(
			run_name,
			bank_account,
			year,
			month,
			"PDF Missing",
			f"{ym}: XLS present, companion PDF missing.",
			ref_file,
		)
		out.append("PDF Missing")
	if has_xls and bt_count and parsed_count and parsed_count != bt_count:
		_log_issue(
			run_name,
			bank_account,
			year,
			month,
			"BT Count Mismatch",
			f"{ym}: Bank Transactions={bt_count}, parsed statement rows={parsed_count} (read-only verify).",
			ref_file,
		)
		out.append("BT Count Mismatch")
	return out


def _period_from_statement_title(title: str) -> tuple[int, int]:
	if len(title) >= 10:
		try:
			d = getdate(title[:10])
			return d.year, d.month
		except Exception:
			pass
	return 2000, 1


def _log_issue(
	run_name: str,
	bank_account: str,
	year: int,
	month: int,
	issue_type: str,
	detail: str,
	reference_file: str = "",
) -> None:
	doc = frappe.get_doc(
		{
			"doctype": "Statement Coverage Issue",
			"bank_account": bank_account,
			"year": year,
			"month": month,
			"issue_type": issue_type,
			"detail": detail,
			"verification_run": run_name,
			"reference_file": reference_file,
			"status": "Open",
		}
	)
	doc.insert(ignore_permissions=True)


def _upsert_coverage_month(
	bank_account: str,
	year: int,
	month: int,
	has_xls: bool,
	has_pdf: bool,
	has_bt: bool,
	bt_count: int,
	parsed_count: int,
	evidence_status: str,
	run_name: str,
	verified_at,
) -> None:
	name = frappe.db.exists(
		"Statement Coverage Month",
		{"bank_account": bank_account, "year": year, "month": month},
	)
	payload = {
		"xls_in_drive": 1 if has_xls else 0,
		"pdf_in_drive": 1 if has_pdf else 0,
		"transactions_imported": 1 if has_bt else 0,
		"bt_row_count": bt_count,
		"parsed_row_count": parsed_count,
		"evidence_status": evidence_status,
		"last_verified_at": verified_at,
		"last_verification_run": run_name,
	}
	if name:
		doc = frappe.get_doc("Statement Coverage Month", name)
		doc.update(payload)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Statement Coverage Month",
				"bank_account": bank_account,
				"year": year,
				"month": month,
				**payload,
			}
		).insert(ignore_permissions=True)


def _ym_parts(ym: str) -> tuple[int, int]:
	y_s, m_s = ym.split("-", 1)
	return int(y_s), int(m_s)


def coverage_report_rows(
	*,
	bank_account: str | None = None,
	from_year: int | None = None,
	from_month: int | None = None,
	to_year: int | None = None,
	to_month: int | None = None,
) -> list[list]:
	filters: dict[str, Any] = {}
	if bank_account:
		filters["bank_account"] = bank_account
	rows = frappe.get_all(
		"Statement Coverage Month",
		filters=filters,
		fields=[
			"bank_account",
			"year",
			"month",
			"bt_row_count",
			"parsed_row_count",
			"xls_in_drive",
			"pdf_in_drive",
			"transactions_imported",
			"evidence_status",
			"last_verified_at",
			"last_verification_run",
		],
		order_by="bank_account, year, month",
		limit_page_length=0,
	)
	out: list[list] = []
	for r in rows:
		if not _month_in_range(r.year, r.month, from_year, from_month, to_year, to_month):
			continue
		open_issues = frappe.db.count(
			"Statement Coverage Issue",
			{"bank_account": r.bank_account, "year": r.year, "month": r.month, "status": "Open"},
		)
		out.append(
			[
				r.bank_account,
				r.year,
				r.month,
				r.bt_row_count or 0,
				r.parsed_row_count or 0,
				"Yes" if r.xls_in_drive else "",
				"Yes" if r.pdf_in_drive else "",
				r.evidence_status or "",
				open_issues,
				get_datetime(r.last_verified_at) if r.last_verified_at else None,
				r.last_verification_run or "",
			]
		)
	return out


def _month_in_range(
	year: int,
	month: int,
	from_year: int | None,
	from_month: int | None,
	to_year: int | None,
	to_month: int | None,
) -> bool:
	cur = date(year, month, 1)
	if from_year and from_month:
		if cur < date(from_year, from_month, 1):
			return False
	if to_year and to_month:
		if cur > date(to_year, to_month, 1):
			return False
	return True