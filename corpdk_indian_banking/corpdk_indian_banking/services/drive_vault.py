"""Vault statement bytes on Frappe Drive."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import frappe
import mimemapper
from drive.api.files import ensure_path, get_upload_path
from drive.utils import create_drive_file, get_home_folder, update_file_size
from drive.utils.files import FileManager


def vault_file(src: Path, logical_path: str, drive_team: str) -> dict[str, Any]:
	if not src.is_file():
		frappe.throw(f"Missing source file: {src}")
	frappe.set_user("Administrator")
	home = get_home_folder(drive_team)
	parent = ensure_path(drive_team, logical_path, home["name"])
	title = Path(logical_path).name

	existing = frappe.db.get_value(
		"Drive File",
		{
			"parent_entity": parent,
			"title": title,
			"is_group": 0,
			"is_active": 1,
			"team": drive_team,
		},
		"name",
	)
	if existing:
		return {
			"status": "skipped",
			"entity": existing,
			"title": title,
			"path": logical_path,
			"url": f"/drive/f/{existing}/",
		}

	file_size = src.stat().st_size
	mime_type = mimemapper.get_mime_type(str(src), native_first=False) or "application/octet-stream"
	manager = FileManager()
	temp_name = f"{uuid.uuid4().hex}_{title}"
	temp_path = get_upload_path(home["path"], temp_name)
	shutil.copy2(src, temp_path)

	drive_file = create_drive_file(
		drive_team,
		title,
		parent,
		mime_type,
		lambda entity: manager.get_disk_path(entity, home),
		file_size,
	)
	manager.upload_file(temp_path, drive_file, create_thumbnail=True)
	try:
		update_file_size(parent, file_size)
	except Exception:
		pass

	return {
		"status": "uploaded",
		"entity": drive_file.name,
		"title": title,
		"path": drive_file.path or logical_path,
		"url": f"/drive/f/{drive_file.name}/",
	}


def attach_drive_link(entity: str, file_name: str, doctype: str, docname: str) -> dict[str, Any]:
	base = frappe.utils.get_url().rstrip("/")
	url = f"{base}/drive/f/{entity}/"
	existing = frappe.db.get_value(
		"File",
		{"file_url": url, "attached_to_doctype": doctype, "attached_to_name": docname},
		"name",
	)
	if existing:
		return {"status": "skipped", "file_row": existing, "file_url": url}
	row = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"file_url": url,
			"is_private": 0,
			"folder": "Home/Attachments",
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
		}
	)
	row.insert(ignore_permissions=True)
	return {"status": "created", "file_row": row.name, "file_url": url}