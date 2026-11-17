"""Parse ICICI Jasper .xls exports (savings + PPF)."""
from __future__ import annotations

import xlrd


def parse_icici_date(s) -> str | None:
	s = str(s).strip()
	if not s:
		return None
	parts = s.split(",")
	if len(parts) == 3:
		d, m, y = (int(p) for p in parts)
		return f"{y:04d}-{m:02d}-{d:02d}"
	from frappe.utils import getdate

	return str(getdate(s))


def amt(v) -> float:
	if v in ("", None, "-"):
		return 0.0
	return float(str(v).replace(",", "").strip() or 0)


def col_map(header_row: list) -> dict[str, int]:
	m = {}
	for i, v in enumerate(header_row):
		key = str(v).strip()
		if key:
			m[key] = i
	return m


def col_index(cols: dict[str, int], *names: str) -> int | None:
	for n in names:
		if n in cols:
			return cols[n]
		for k, i in cols.items():
			if k.replace(" ", "") == n.replace(" ", ""):
				return i
	return None


def parse_workbook(path: str, transaction_id_prefix: str) -> list[dict]:
	sh = xlrd.open_workbook(path).sheet_by_index(0)
	header_idx = None
	cols = None
	for r in range(sh.nrows):
		row = [sh.cell_value(r, c) for c in range(sh.ncols)]
		texts = [str(x).strip() for x in row]
		if "Transaction Date" in texts:
			header_idx = r
			cols = col_map(texts)
			break
	if header_idx is None or cols is None:
		return []

	idx_date = cols.get("Transaction Date")
	idx_remarks = cols.get("Transaction Remarks")
	idx_wd = col_index(cols, "Withdrawal Amount(INR)", "Withdrawal Amount (INR)", "Withdrawal Amount (INR )")
	idx_dep = col_index(cols, "Deposit Amount(INR)", "Deposit Amount (INR)", "Deposit Amount (INR )")
	idx_bal = col_index(cols, "Balance(INR)", "Balance (INR )")
	idx_chq = cols.get("Cheque Number")
	idx_sno = cols.get("Sr No.") or cols.get("S No.")

	out = []
	pending_remark = ""
	for r in range(header_idx + 1, sh.nrows):
		row = [sh.cell_value(r, c) for c in range(sh.ncols)]
		texts = [str(x).strip() for x in row]
		if any("Legends Used" in t for t in texts):
			break
		sno = texts[idx_sno] if idx_sno is not None else ""
		wd_try = amt(row[idx_wd]) if idx_wd is not None else 0
		dep_try = amt(row[idx_dep]) if idx_dep is not None else 0
		if not sno and wd_try == 0 and dep_try == 0:
			if idx_remarks is not None and texts[idx_remarks]:
				cont = texts[idx_remarks]
				if out:
					prev = out[-1]
					prev["description"] = (prev["description"] + " " + cont).strip()[:500]
				else:
					pending_remark += " " + cont
			continue
		dt = parse_icici_date(row[idx_date]) if idx_date is not None else None
		if not dt:
			continue
		remarks = (pending_remark + " " + (texts[idx_remarks] if idx_remarks is not None else "")).strip()
		pending_remark = ""
		wd, dep = wd_try, dep_try
		bal = amt(row[idx_bal]) if idx_bal is not None else 0
		if wd == 0 and dep == 0:
			continue
		chq = texts[idx_chq] if idx_chq is not None else ""
		tid = f"{transaction_id_prefix}{dt}|{wd:.2f}|{dep:.2f}|{bal:.2f}|{remarks[:180]}"
		out.append(
			{
				"date": dt,
				"withdrawal": wd,
				"deposit": dep,
				"description": remarks[:500],
				"reference_number": chq or sno,
				"transaction_id": tid,
			}
		)
	return out
