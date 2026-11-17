from __future__ import annotations

import hashlib
import re

import frappe
from frappe.utils import getdate

_SEQ_SUFFIX = re.compile(r"\|\d{2}$")


def naming_series_for_transaction_date(transaction_date) -> str:
	year = getdate(transaction_date).year
	return f"ACC-BTN-{year}-"


def naming_series_for_insertion() -> str:
	year = getdate(frappe.utils.today()).year
	return f"ACC-BTN-{year}-"


def resync_bank_transaction_series() -> None:
	prefixes = frappe.db.sql_list(
		"SELECT name FROM `tabSeries` WHERE name LIKE 'ACC-BTN-%' ORDER BY name"
	)
	for prefix in prefixes:
		max_num = frappe.db.sql(
			"""
			SELECT MAX(CAST(SUBSTRING_INDEX(name, '-', -1) AS UNSIGNED))
			FROM `tabBank Transaction`
			WHERE name LIKE %s
			""",
			(f"{prefix}%",),
		)[0][0]
		max_num = int(max_num or 0)
		frappe.db.sql("UPDATE `tabSeries` SET `current` = %s WHERE name = %s", (max_num, prefix))


def legacy_amex_transaction_id(row: dict) -> str:
	tid = row.get("transaction_id") or ""
	if _SEQ_SUFFIX.search(tid):
		return _SEQ_SUFFIX.sub("", tid)
	desc = row["description"]
	wd = float(row.get("withdrawal") or 0)
	dep = float(row.get("deposit") or 0)
	amt = wd or dep
	digest = hashlib.md5(f"{desc}|{amt}|{wd:.2f}|{dep:.2f}".encode()).hexdigest()[:10]
	ref = row.get("reference_number") or ""
	dt = getdate(row["date"]).isoformat()
	return f"AMEX|{ref}|{dt}|{wd:.2f}|{dep:.2f}|{digest}"


def already_imported(row: dict, existing: set[str], *, amex: bool = False) -> bool:
	tid = row["transaction_id"]
	if tid in existing:
		return True
	if not amex:
		return False
	legacy = legacy_amex_transaction_id(row)
	if legacy not in existing:
		return False
	m = _SEQ_SUFFIX.search(tid)
	if m and int(m.group(0)[1:]) > 1:
		return False
	return True


def insert_rows(
	rows: list[dict],
	*,
	bank_account: str,
	company: str,
	currency: str,
	naming_series_rule: str,
	transaction_id_prefix: str = "",
	amex: bool = False,
) -> tuple[int, int]:
	existing: set[str] = set()
	if not rows:
		return 0, 0
	if amex:
		existing = set(
			frappe.db.sql_list(
				"select transaction_id from `tabBank Transaction` where transaction_id like 'AMEX|%'"
			)
		)
	else:
		prefix = transaction_id_prefix or rows[0]["transaction_id"].split("|", 1)[0] + "|"
		existing = set(
			frappe.db.sql_list(
				"select transaction_id from `tabBank Transaction` where transaction_id like %s",
				(f"{prefix}%",),
			)
		)
	created = skipped = 0
	for row in rows:
		if already_imported(row, existing, amex=amex):
			skipped += 1
			continue
		ns = (
			naming_series_for_insertion()
			if naming_series_rule == "insertion_year"
			else naming_series_for_transaction_date(row["date"])
		)
		doc = frappe.get_doc(
			{
				"doctype": "Bank Transaction",
				"naming_series": ns,
				"date": row["date"],
				"withdrawal": row.get("withdrawal") or 0,
				"deposit": row.get("deposit") or 0,
				"description": row["description"],
				"reference_number": row.get("reference_number") or "",
				"transaction_id": row["transaction_id"],
				"bank_account": bank_account,
				"company": company,
				"currency": currency,
				"status": "Pending",
			}
		)
		doc.insert(ignore_permissions=True)
		existing.add(row["transaction_id"])
		created += 1
	return created, skipped