"""Indian financial year helpers (Apr 1 → Mar 31)."""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class IndianFY:
	start: date
	end: date
	label: str  # e.g. FY 2025-2026

	def folder_name(self) -> str:
		return self.label


def indian_fy_for_date(d: date) -> IndianFY:
	"""Return the Indian FY containing date *d*."""
	y = d.year
	if d.month >= 4:
		start_year, end_year = y, y + 1
	else:
		start_year, end_year = y - 1, y
	start = date(start_year, 4, 1)
	end = date(end_year, 3, monthrange(end_year, 3)[1])
	label = f"FY {start_year}-{end_year}"
	return IndianFY(start=start, end=end, label=label)


def assert_single_fy(dates: list[date]) -> IndianFY:
	if not dates:
		frappe_throw_empty()
	fys = {indian_fy_for_date(d) for d in dates}
	if len(fys) != 1:
		fy_labels = sorted({fy.label for fy in fys})
		ps, pe = min(dates), max(dates)
		frappe_throw_cross_fy(fy_labels, ps, pe)
	return next(iter(fys))


def fy_file_label(
	fy: IndianFY,
	period_start: date,
	period_end: date,
	*,
	partial_range: str | None = None,
) -> str:
	"""Filename FY segment; partial periods add range in parentheses."""
	if partial_range:
		return f"{fy.label} ({partial_range})"
	if period_start == fy.start and period_end == fy.end:
		return fy.label
	# Partial within FY without explicit range label: infer mon–mon abbreviated
	if period_start.year == period_end.year and period_start.year == fy.start.year and period_start.month >= 4:
		pass
	elif period_start.month >= 4 or period_end.month <= 3:
		start_m = period_start.strftime("%b")
		end_m = period_end.strftime("%b")
		return f"{fy.label} ({start_m}–{end_m})"
	return fy.label


def partial_range_apr_sep(period_start: date, period_end: date, fy: IndianFY) -> str | None:
	"""Detect common Apr–Sep partial export."""
	if period_start == date(fy.start.year, 4, 1) and period_end.month == 9 and period_end.year == fy.start.year:
		return "Apr–Sep"
	return None


def frappe_throw_cross_fy(fy_labels: list[str], period_start: date, period_end: date) -> None:
	import frappe

	frappe.throw(
		f"Statement spans more than one Indian financial year ({', '.join(fy_labels)}). "
		f"Transaction range {period_start.isoformat()} → {period_end.isoformat()}. "
		f"Split exports per FY before importing.",
		exc=frappe.ValidationError,
		title="Cross-FY statement",
	)


def frappe_throw_empty() -> None:
	import frappe

	frappe.throw("No transaction dates found in statement.", title="Empty statement")