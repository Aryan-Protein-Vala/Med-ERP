app_name = "pharma_retail"
app_title = "Pharma Retail"
app_publisher = "Aryan Sharma"
app_description = "Pharmacy Retail Management Application for Frappe and ERPNext"
app_email = "admin@pharmacy.local"
app_license = "mit"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pharma_retail/css/pharma_retail.css"
# app_include_js = "/assets/pharma_retail/js/pharma_retail.js"

# include js, css files in header of web template
# web_include_css = "/assets/pharma_retail/css/pharma_retail.css"
# web_include_js = "/assets/pharma_retail/js/pharma_retail.js"

# Installation & Migrations
# -------------------------
after_install = [
	"pharma_retail.custom_fields.setup_custom_fields",
	"pharma_retail.utils.db_indexes.create_database_indexes",
]

after_migrate = [
	"pharma_retail.custom_fields.setup_custom_fields",
	"pharma_retail.utils.db_indexes.create_database_indexes",
]

# Fixtures Export/Sync
# --------------------
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Item-salt_composition",
					"Item-hsn_code",
					"Item-therapeutic_class",
					"Item-minimum_reorder_level",
				],
			]
		],
	}
]

# Document Events & Hooks
# -----------------------
# Hook on document methods and events for Strict FEFO and prescription validation
doc_events = {
	"Sales Invoice": {
		"validate": "pharma_retail.controllers.fefo_allocation.apply_fefo_to_doc"
	},
	"POS Invoice": {
		"validate": "pharma_retail.controllers.fefo_allocation.apply_fefo_to_doc"
	},
	"Delivery Note": {
		"validate": "pharma_retail.controllers.fefo_allocation.apply_fefo_to_doc"
	},
	"Material Request": {
		"validate": "pharma_retail.controllers.fefo_allocation.apply_fefo_to_doc"
	},
	"Pharmacy Prescription": {
		"validate": "pharma_retail.doctype.pharmacy_prescription.pharmacy_prescription.validate_prescription"
	},
}

# Scheduled Tasks
# ---------------
scheduler_events = {
	"daily": [
		"pharma_retail.tasks.cron_refills.process_chronic_refill_reminders"
	]
}

# Commands
# --------
commands = ["pharma_retail.commands.commands"]


