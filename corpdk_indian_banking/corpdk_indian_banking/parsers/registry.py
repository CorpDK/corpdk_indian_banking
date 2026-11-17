from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from corpdk_indian_banking.parsers import amex_rewards, icici_jasper


class ParseResult:
	def __init__(
		self,
		rows: list[dict[str, Any]],
		*,
		period_start,
		period_end,
		statement_close_date=None,
		statement_reference: str = "",
	):
		self.rows = rows
		self.period_start = period_start
		self.period_end = period_end
		self.statement_close_date = statement_close_date or period_end
		self.statement_reference = statement_reference


class StatementParser(Protocol):
	parser_code: str

	def parse_file(self, path: Path, *, transaction_id_prefix: str) -> ParseResult: ...


class ICICIJasperParser:
	parser_code = "icici_jasper_xls"

	def parse_file(self, path: Path, *, transaction_id_prefix: str) -> ParseResult:
		raw = icici_jasper.parse_workbook(str(path), transaction_id_prefix)
		if not raw:
			raise ValueError(f"No rows parsed from {path.name}")
		dates = [r["date"] for r in raw if r.get("date")]
		from frappe.utils import getdate

		parsed_dates = [getdate(d) for d in dates]
		ps, pe = min(parsed_dates), max(parsed_dates)
		return ParseResult(
			raw,
			period_start=ps,
			period_end=pe,
			statement_close_date=pe,
			statement_reference=path.stem,
		)


class AmexRewardsParser:
	parser_code = "amex_in_rewards_pdf"

	def parse_file(self, path: Path, *, transaction_id_prefix: str) -> ParseResult:
		rows = amex_rewards.parse_amex_pdf(path)
		if not rows:
			raise ValueError(f"No rows parsed from {path.name}")
		from frappe.utils import getdate

		dates = [getdate(r["date"]) for r in rows]
		close = getdate(rows[0].get("reference_number") or path.stem)
		meta_close = amex_rewards._statement_end_from_name(path)
		if meta_close:
			close = meta_close
		return ParseResult(
			rows,
			period_start=min(dates),
			period_end=max(dates),
			statement_close_date=close,
			statement_reference=path.stem,
		)


_REGISTRY: dict[str, StatementParser] = {
	ICICIJasperParser.parser_code: ICICIJasperParser(),
	AmexRewardsParser.parser_code: AmexRewardsParser(),
}


def get_parser(parser_code: str) -> StatementParser:
	try:
		return _REGISTRY[parser_code]
	except KeyError as e:
		raise ValueError(f"Unknown parser: {parser_code}") from e