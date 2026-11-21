"""Re-import standard Dock/Sidebar JSON so desk matches the app (fixes stale Sidebar Item rows)."""
from __future__ import annotations

from pathlib import Path

import frappe
from frappe.modules.import_file import import_file_by_path


def sync_standard_desk_navigation() -> None:
	root = Path(frappe.get_app_path("corpdk_indian_banking"))
	files = [
		root / "dock" / "corpdk_indian_banking" / "corpdk_indian_banking.json",
		root / "corpdk_indian_banking" / "sidebar" / "indian_banking_home" / "indian_banking_home.json",
		root / "corpdk_indian_banking" / "sidebar" / "indian_banking_import" / "indian_banking_import.json",
		root / "corpdk_indian_banking" / "sidebar" / "indian_banking_coverage" / "indian_banking_coverage.json",
		root / "corpdk_indian_banking" / "sidebar" / "indian_banking_settings" / "indian_banking_settings.json",
		root / "corpdk_indian_banking" / "workspace" / "indian_banking_home" / "indian_banking_home.json",
	]
	for path in files:
		if not path.is_file():
			continue
		import_file_by_path(str(path), force=True, reset_permissions=False)