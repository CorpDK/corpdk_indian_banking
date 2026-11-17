from __future__ import annotations

import frappe


def has_app_permission() -> bool:
	if frappe.session.user == "Administrator":
		return True
	roles = frappe.get_roles()
	return bool({"Accounts Manager", "Accounts User", "Statement Import Manager"} & set(roles))