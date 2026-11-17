from __future__ import annotations

import frappe


def execute() -> None:
	frappe_version = tuple(int(x) for x in frappe.__version__.split(".")[:2])
	if frappe_version[0] < 16:
		frappe.throw("CorpDK Indian Banking requires Frappe v16 or later.")