app_name = "corpdk_indian_banking"
app_title = "CorpDK Indian Banking"
app_publisher = "CorpDK"
app_description = "Indian bank and card statement parsers, Drive evidence, and Bank Transaction import"
app_email = "ops@corpdk.local"
app_license = "MIT"

required_apps = ["erpnext", "drive"]

app_include_icons = [
	"/assets/corpdk_indian_banking/icons/module-icons.svg",
]

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/corpdk_indian_banking/images/indian-banking.svg",
		"title": app_title,
		"route": "/desk/indian-banking-home/indian-banking-home",
		"has_permission": "corpdk_indian_banking.permissions.has_app_permission",
	},
]

before_install = "corpdk_indian_banking.patches.check_version_compatibility.execute"
before_migrate = "corpdk_indian_banking.patches.check_version_compatibility.execute"

after_install = "corpdk_indian_banking.install.after_install"
after_migrate = "corpdk_indian_banking.install.after_migrate"