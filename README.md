# corpdk_indian_banking

**ERPNext / Frappe v16** app (**CorpDK Indian Banking**): configure statement parsers per **Bank Account**, vault exports on **Frappe Drive**, and create **Bank Transaction** rows (ICICI Jasper XLS, Amex India Rewards PDF in v1).

Design notes live in the private [CorpDK/ERP](https://github.com/CorpDK/ERP) repo: `docs/corpdk-indian-banking-app-design.md`.

**Requires:** `erpnext`, `drive` on the site.

On install/migrate, if missing, the app adds a **Property Setter** on **Drive Team** (`show_title_field_in_link`) so Link fields show the team **title** instead of the hash id — equivalent to a one-time desk Customize Form; we do **not** patch the Drive app. Drop that hook once upstream Drive ships the default.

## Install

```bash
bench get-app https://github.com/CorpDK/corpdk_indian_banking
bench --site personal.localhost install-app corpdk_indian_banking
```

CorpDK local bench: cloned in the ERP bench image from this repo ([`CorpDK/ERP`](https://github.com/CorpDK/ERP) `local/Dockerfile`).

Desk: open **CorpDK Indian Banking** from the app switcher → v16 **dock** (Home / Import / Coverage / Settings rails) with **sidebar** menus and workspace home (`/desk/indian-banking-home/indian-banking-home`). Install seeds **Statement Parser** masters, the **Statement Import Manager** role, and singleton defaults (`Statements/`, reject cross-FY) only — no **Bank Account** mapping rows. Set **Default Drive Team** in Desk, or before first install set `indian_banking_default_drive_team` in the site’s `site_config.json` to a **Drive Team** name (applied only when the field is still empty).

**API:** `list_importable_accounts_api`, `preview_import_api`, `run_import_api`, `reconcile_coverage_api`.

**Coverage:** Query report **Statement Coverage Overview** (Run Verification → read-only reconcile of Bank Transactions vs Drive statements; updates **Statement Coverage Month**, logs **Statement Coverage Issue**).