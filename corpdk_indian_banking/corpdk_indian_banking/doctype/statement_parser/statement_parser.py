import frappe
from frappe import _
from frappe.model.document import Document

_SYNC_FLAG = "corpdk_indian_banking_sync_parser"
_REGISTRY_FIELDS = frozenset(
	{
		"parser_code",
		"title",
		"description",
		"primary_extension",
		"companion_extension",
		"import_primary_type",
		"parser_version",
	}
)


class StatementParser(Document):
	def before_insert(self):
		if not self._allow_registry_write():
			frappe.throw(
				_("Statement Parsers are installed from app code. You cannot create new records."),
				title=_("Not allowed"),
			)

	def validate(self):
		if self.is_new():
			if not self._allow_registry_write():
				frappe.throw(
					_("Statement Parsers are installed from app code. You cannot create new records."),
					title=_("Not allowed"),
				)
			return
		if self._allow_registry_write():
			return
		old = self.get_doc_before_save()
		if not old:
			return
		for fieldname in _REGISTRY_FIELDS:
			if self.get(fieldname) != old.get(fieldname):
				frappe.throw(
					_("Only the Active flag can be changed. Parser metadata comes from the app."),
					title=_("Not allowed"),
				)

	def on_trash(self):
		if not self._allow_registry_write():
			frappe.throw(
				_("Statement Parsers cannot be deleted."),
				title=_("Not allowed"),
			)

	def _allow_registry_write(self) -> bool:
		return bool(self.flags.get(_SYNC_FLAG) or frappe.flags.in_install or frappe.flags.in_migrate)


def mark_parser_sync(doc) -> None:
	doc.flags.corpdk_indian_banking_sync_parser = True