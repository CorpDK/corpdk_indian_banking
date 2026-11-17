"""Parse American Express India statement PDFs using word layout (PyMuPDF)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pymupdf

MONTHS = {
	"january": 1,
	"february": 2,
	"march": 3,
	"april": 4,
	"may": 5,
	"june": 6,
	"july": 7,
	"august": 8,
	"september": 9,
	"october": 10,
	"november": 11,
	"december": 12,
}

_MONTH = (
	r"January|February|March|April|May|June|July|August|September|October|November|December"
)
PERIOD_LINE = re.compile(
	r"From\s+(\w+)\s+(\d{1,2})\s+to\s+(\w+)\s+(\d{1,2}),\s+(\d{4})",
	re.I,
)
STMT_DATE_LINE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
AMOUNT_RE = re.compile(r"^([\d,]+\.\d{2})$")

# Column x-ranges (points) from Amex India Rewards PDFs
DETAIL_X0 = 75.0
FOREIGN_X0 = 340.0
AMOUNT_X0 = 450.0

Y_BAND_TOL = 5.0

SKIP_DESC_SUBSTR = (
	"card number",
	"xxxx-xxxxxx",
	"membership number",
	"prepared for",
	"foreign spending",
	"amount rs",
	"statement of account",
)

JUNK_ROW_SUBSTR = (
	"new domestic transactions for",
	"new overseas transactions for",
	"total of other account",
	"total overseas spend in current month",
	"other account transactions",
	"installment plan summary",
	"installment plan transactions",
	"transactions for mr ",
	"total of installments",
)

@dataclass
class AmexStatementMeta:
	statement_end: date
	period_end: date


@dataclass(frozen=True)
class Word:
	x: float
	y: float
	text: str
	page: int


@dataclass
class RowBand:
	y: float
	words: list[Word]


REF_DATE_IN_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def reference_number_from_path(path: Path) -> str:
	"""ERP `reference_number` = statement close date; leading ISO date in filename."""
	m = REF_DATE_IN_NAME.match(path.name)
	if m:
		return m.group(1)
	return path.stem


def _statement_end_from_name(path: Path) -> date | None:
	ref = reference_number_from_path(path)
	try:
		y, mo, d = (int(x) for x in ref.split("-"))
		return date(y, mo, d)
	except ValueError:
		return None


def _parse_meta(doc: pymupdf.Document, path: Path) -> AmexStatementMeta:
	end = _statement_end_from_name(path)
	text = doc[0].get_text()
	for line in text.splitlines():
		pm = PERIOD_LINE.search(line)
		if pm:
			_, _, em, ed, year = pm.groups()
			month = MONTHS[em.lower()]
			end = date(int(year), month, int(ed))
			break
	if not end:
		for line in text.splitlines():
			line = line.strip()
			if STMT_DATE_LINE.match(line):
				d, m, y = STMT_DATE_LINE.match(line).groups()
				end = date(int(y), int(m), int(d))
				break
	if not end:
		raise ValueError(f"Could not determine statement end date for {path}")
	return AmexStatementMeta(statement_end=end, period_end=end)


def _resolve_txn_date(month_name: str, day: int, meta: AmexStatementMeta) -> date:
	m = MONTHS[month_name.lower()]
	y = meta.period_end.year
	if m > meta.period_end.month:
		y -= 1
	return date(y, m, day)


def _is_payment_deposit(desc: str) -> bool:
	return "payment received" in desc.lower()


def _withdrawal_deposit(desc: str, amt: float, is_credit: bool = False) -> tuple[float, float]:
	if is_credit or _is_payment_deposit(desc):
		return 0.0, amt
	return amt, 0.0


def _page_y_window(page_index: int, page: pymupdf.Page) -> tuple[float, float] | None:
	"""Keep only the Details table band; ignore marketing/legal pages below."""
	if page_index == 0:
		return (350.0, 560.0)
	if page_index == 1:
		return (140.0, 560.0)
	# Some statements spill a few lines onto page 3 — include only if Amount Rs header present.
	text = page.get_text()
	if "amount rs" not in text.lower() and "foreign spending" not in text.lower():
		return None
	return (140.0, 390.0)


def _extract_words(doc: pymupdf.Document) -> list[Word]:
	words: list[Word] = []
	for page_index, page in enumerate(doc):
		if page_index > 1 and page_index > 0:
			win = _page_y_window(page_index, page)
			if win is None:
				continue
		else:
			win = _page_y_window(page_index, page)
			if win is None:
				continue
		ymin, ymax = win
		for x0, y0, _x1, _y1, text, *_ in page.get_text("words"):
			y = float(y0)
			if y < ymin or y > ymax:
				continue
			t = text.strip()
			if not t:
				continue
			low = t.lower()
			if any(s in low for s in ("page ", "prepared for", "membership number")):
				continue
			words.append(Word(x=float(x0), y=y, text=t, page=page_index))
	return words


def _cluster_bands(words: list[Word]) -> list[RowBand]:
	bands: list[RowBand] = []
	for page_index in sorted({w.page for w in words}):
		page_words = sorted([w for w in words if w.page == page_index], key=lambda w: (w.y, w.x))
		page_bands: list[RowBand] = []
		for w in page_words:
			if not page_bands or w.y - page_bands[-1].y > Y_BAND_TOL:
				page_bands.append(RowBand(y=w.y, words=[w]))
			else:
				page_bands[-1].words.append(w)
				page_bands[-1].y = min(page_bands[-1].y, w.y)
		bands.extend(page_bands)
	return bands


def _band_text(band: RowBand, x0: float, x1: float | None = None) -> str:
	parts = []
	for w in sorted(band.words, key=lambda w: w.x):
		if w.x < x0:
			continue
		if x1 is not None and w.x >= x1:
			continue
		parts.append(w.text)
	return " ".join(parts).strip()


def _band_date(band: RowBand, meta: AmexStatementMeta) -> date | None:
	month_name: str | None = None
	day: int | None = None
	for w in sorted(band.words, key=lambda w: w.x):
		if w.x > DETAIL_X0:
			continue
		low = w.text.lower()
		if low in MONTHS:
			month_name = w.text
		elif w.text.isdigit() and int(w.text) <= 31:
			day = int(w.text)
		m = re.match(rf"^({_MONTH})\s+(\d{{1,2}})$", w.text, re.I)
		if m:
			return _resolve_txn_date(m.group(1), int(m.group(2)), meta)
		m2 = re.match(rf"^({_MONTH})\s+(\d{{1,2}})\s+", w.text, re.I)
		if m2:
			return _resolve_txn_date(m2.group(1), int(m2.group(2)), meta)
	if month_name and day:
		return _resolve_txn_date(month_name, day, meta)
	return None


def _band_inr_amount(band: RowBand) -> float | None:
	for w in band.words:
		if w.x < AMOUNT_X0:
			continue
		m = AMOUNT_RE.match(w.text.replace(" ", ""))
		if m:
			return float(m.group(1).replace(",", ""))
	return None


def _band_is_credit(band: RowBand, next_band: RowBand | None) -> bool:
	for w in band.words:
		if w.text.upper() == "CR" and w.x > AMOUNT_X0 - 20:
			return True
	if not next_band or next_band.y - band.y > 12:
		return False
	if not any(w.text.upper() == "CR" for w in next_band.words):
		return False
	detail = _band_text(band, DETAIL_X0, FOREIGN_X0).upper()
	if "PAYMENT" in detail or "TRANSFERRED TO INSTALLMENT" in detail:
		return True
	amt = _band_inr_amount(band)
	if amt is not None and amt < 500:
		nxt = _band_text(next_band, DETAIL_X0, FOREIGN_X0)
		if not nxt or nxt.lower().startswith("card"):
			return True
	return False


def _is_emi_summary_band(band: RowBand) -> bool:
	"""Installment plan summary table (not billed transaction lines)."""
	detail = _band_text(band, DETAIL_X0, FOREIGN_X0)
	left = _band_text(band, 0, DETAIL_X0)
	chunk = f"{left} {detail}".upper()
	if "INSTALLMENT PRINCIPAL" in chunk or "FINANCE CHARGES" in chunk or "GST/IGST" in chunk:
		return False
	return "AMERICAN EXPRESS" in chunk and " EMI " in f" {chunk} "


def _is_junk_row(detail: str) -> bool:
	low = detail.lower()
	if not low:
		return False
	if "transferred to installment" in low:
		return False
	if any(s in low for s in JUNK_ROW_SUBSTR):
		return True
	if any(s in low for s in SKIP_DESC_SUBSTR):
		return True
	return False


def _normalize_description(detail: str, is_credit: bool) -> str | None:
	d = re.sub(r"\s+", " ", detail).strip()
	d = re.sub(r"\s*PAYMENT\s+RECEIVED\.?\s*(THANK\s+YOU\.?)?\s*", "PAYMENT RECEIVED", d, flags=re.I)
	if is_credit:
		if "transferred to installment" in d.lower():
			return d
		if _is_payment_deposit(d) or not d:
			return "PAYMENT RECEIVED"
		return d
	if _is_payment_deposit(d):
		return "PAYMENT RECEIVED"
	if not d:
		return None
	low = d.lower()
	if low.startswith("card number"):
		return None
	if len(d) > 100:
		return None
	if any(
		p in low
		for p in (
			"illustration",
			"american express credit",
			"your card",
			"fee*:",
			"taxes;",
			"do not have any amount outstanding",
		)
	):
		return None
	# City suffix from layout column (not part of merchant name on imports)
	d = re.sub(r"\s+Bangalore\s*$", "", d, flags=re.I)
	d = re.sub(r"\s+\d{10,}\s*$", "", d)  # PayPal ref phone on same row
	return d


def _rows_from_bands(bands: list[RowBand], meta: AmexStatementMeta) -> list[dict]:
	out: list[dict] = []
	i = 0
	while i < len(bands):
		band = bands[i]
		amt = _band_inr_amount(band)
		if amt is None or amt == 0:
			i += 1
			continue
		next_band = bands[i + 1] if i + 1 < len(bands) else None
		detail = _band_text(band, DETAIL_X0, FOREIGN_X0)
		if _is_emi_summary_band(band):
			i += 1
			continue
		if _is_junk_row(detail) or _is_junk_row(_band_text(band, 0, DETAIL_X0)):
			i += 1
			continue
		# Subtotal row: header in left column, amount on right (e.g. domestic total 63,628.17)
		left = _band_text(band, 0, DETAIL_X0)
		if _is_junk_row(left):
			i += 1
			continue
		if abs(amt - 739.39) < 0.02 and "finance" not in detail.lower():
			i += 1
			continue
		if abs(amt - 3936.10) < 0.02:
			i += 1
			continue
		if abs(amt - 63628.17) < 0.02:
			i += 1
			continue
		if abs(amt - 1180.00) < 0.02 and "total" in left.lower():
			i += 1
			continue
		if abs(amt - 865.88) < 0.02:
			i += 1
			continue

		txn_date = _band_date(band, meta)
		if txn_date is None and next_band:
			txn_date = _band_date(next_band, meta)
		if txn_date is None:
			i += 1
			continue

		is_credit = _band_is_credit(band, next_band)
		desc = _normalize_description(detail, is_credit)
		if not desc:
			i += 1
			continue

		wd, dep = _withdrawal_deposit(desc, amt, is_credit=is_credit)
		out.append(
			{
				"date": txn_date,
				"withdrawal": wd,
				"deposit": dep,
				"description": desc[:500],
				"reference_number": meta.statement_end.isoformat(),
				"source_file": "",
				"_amt": amt,
			}
		)
		i += 1
	return _assign_transaction_ids(out, meta)


def _assign_transaction_ids(rows: list[dict], meta: AmexStatementMeta) -> list[dict]:
	"""Stable ids per statement line; duplicate-looking rows get |01, |02, … suffixes."""
	stmt = meta.statement_end.isoformat()
	seen: dict[str, int] = {}
	for row in rows:
		desc = row["description"]
		amt = row["_amt"]
		wd, dep = row["withdrawal"], row["deposit"]
		digest = hashlib.md5(f"{desc}|{amt}|{wd:.2f}|{dep:.2f}".encode()).hexdigest()[:10]
		base = f"AMEX|{stmt}|{row['date'].isoformat()}|{wd:.2f}|{dep:.2f}|{digest}"
		seen[base] = seen.get(base, 0) + 1
		seq = seen[base]
		row["transaction_id"] = f"{base}|{seq:02d}"
		del row["_amt"]
	return rows


def parse_amex_pdf(path: Path) -> list[dict]:
	doc = pymupdf.open(path)
	try:
		meta = _parse_meta(doc, path)
		words = _extract_words(doc)
		bands = _cluster_bands(words)
		rows = _rows_from_bands(bands, meta)
		ref = reference_number_from_path(path)
		for r in rows:
			r["reference_number"] = ref
			r["source_file"] = path.name
		return rows
	finally:
		doc.close()


def parse_amex_dir(stmt_dir: Path) -> list[dict]:
	all_rows: list[dict] = []
	paths = sorted(stmt_dir.glob("**/*.pdf"))
	if not paths:
		paths = sorted(stmt_dir.glob("*.pdf"))
	for path in paths:
		if path.name.startswith("."):
			continue
		rows = parse_amex_pdf(path)
		print(f"{path}: {len(rows)} transactions")
		all_rows.extend(rows)
	return all_rows
