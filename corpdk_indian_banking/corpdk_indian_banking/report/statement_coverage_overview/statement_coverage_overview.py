from __future__ import annotations

from corpdk_indian_banking.services.coverage_reconcile import coverage_report_rows


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Bank Account", "fieldname": "bank_account", "fieldtype": "Link", "options": "Bank Account", "width": 220},
		{"label": "Year", "fieldname": "year", "fieldtype": "Int", "width": 70},
		{"label": "Month", "fieldname": "month", "fieldtype": "Int", "width": 70},
		{"label": "BT Rows", "fieldname": "bt_row_count", "fieldtype": "Int", "width": 80},
		{"label": "Parsed Rows", "fieldname": "parsed_row_count", "fieldtype": "Int", "width": 90},
		{"label": "XLS", "fieldname": "xls_in_drive", "fieldtype": "Data", "width": 60},
		{"label": "PDF", "fieldname": "pdf_in_drive", "fieldtype": "Data", "width": 60},
		{"label": "Evidence Status", "fieldname": "evidence_status", "fieldtype": "Data", "width": 110},
		{"label": "Open Issues", "fieldname": "open_issues", "fieldtype": "Int", "width": 90},
		{"label": "Last Verified", "fieldname": "last_verified_at", "fieldtype": "Datetime", "width": 150},
		{"label": "Verification Run", "fieldname": "last_verification_run", "fieldtype": "Link", "options": "Statement Coverage Verification Run", "width": 140},
	]
	raw = coverage_report_rows(
		bank_account=filters.get("bank_account") or None,
		from_year=filters.get("from_year"),
		from_month=filters.get("from_month"),
		to_year=filters.get("to_year"),
		to_month=filters.get("to_month"),
	)
	data = [
		{
			"bank_account": r[0],
			"year": r[1],
			"month": r[2],
			"bt_row_count": r[3],
			"parsed_row_count": r[4],
			"xls_in_drive": r[5],
			"pdf_in_drive": r[6],
			"evidence_status": r[7],
			"open_issues": r[8],
			"last_verified_at": r[9],
			"last_verification_run": r[10],
		}
		for r in raw
	]
	return columns, data