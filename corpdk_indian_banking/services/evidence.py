from __future__ import annotations

from datetime import date

from corpdk_indian_banking.services.fy import (
	IndianFY,
	fy_file_label,
	indian_fy_for_date,
	partial_range_apr_sep,
)


def statements_root(drive_account_root: str, drive_statements_subpath: str = "Statements/") -> str:
	root = (drive_account_root or "").rstrip("/")
	sub = (drive_statements_subpath or "Statements/").lstrip("/")
	return f"{root}/{sub}" if root else sub


def build_icici_filename(
	*,
	kind: str,
	mask: str,
	period_end: date,
	fy: IndianFY,
	period_start: date,
	ext: str,
) -> str:
	partial = partial_range_apr_sep(period_start, period_end, fy)
	label = fy_file_label(fy, period_start, period_end, partial_range=partial)
	return f"{period_end:%Y-%m-%d} - ICICI - {kind} Statement · {mask} · {label}.{ext.lstrip('.')}"


def build_amex_filename(*, close_date: date, fy: IndianFY) -> str:
	return f"{close_date:%Y-%m-%d} - Amex - Rewards Statement · {fy.label}.pdf"


def vault_logical_path(
	drive_statements_root: str,
	fy: IndianFY,
	filename: str,
) -> str:
	root = statements_root_from_config(drive_statements_root)
	folder = fy.folder_name()
	return f"{root.rstrip('/')}/{folder}/{filename}"


def statements_root_from_config(drive_statements_root: str) -> str:
	return drive_statements_root.rstrip("/") if drive_statements_root else "Statements"


def fy_for_close_date(close_date: date) -> IndianFY:
	return indian_fy_for_date(close_date)