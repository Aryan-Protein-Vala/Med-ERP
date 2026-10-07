# Copyright (c) 2026, Aryan Sharma and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
	"Item": [
		{
			"fieldname": "pharma_section",
			"label": "Pharmaceutical Specifications",
			"fieldtype": "Section Break",
			"insert_after": "item_name",
			"collapsible": 0,
		},
		{
			"fieldname": "salt_composition",
			"label": "Salt Composition",
			"fieldtype": "Link",
			"options": "Salt Composition",
			"insert_after": "pharma_section",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"description": "Generic chemical formulation / active pharmaceutical molecule",
		},
		{
			"fieldname": "therapeutic_class",
			"label": "Therapeutic Class",
			"fieldtype": "Select",
			"options": "\nAntibiotic\nAnalgesic\nAntipyretic\nAntidiabetic\nAntihypertensive\nAntacid\nAntihistamine\nCardiovascular\nDermatological\nRespiratory\nOther",
			"insert_after": "salt_composition",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"description": "Medical classification / therapeutic domain",
		},
		{
			"fieldname": "pharma_col_break",
			"fieldtype": "Column Break",
			"insert_after": "therapeutic_class",
		},
		{
			"fieldname": "hsn_code",
			"label": "HSN Code",
			"fieldtype": "Data",
			"default": "3004",
			"insert_after": "pharma_col_break",
			"in_list_view": 1,
			"description": "Harmonized System Nomenclature (Pharma default 3004)",
		},
		{
			"fieldname": "minimum_reorder_level",
			"label": "Minimum Reorder Level",
			"fieldtype": "Int",
			"default": 10,
			"insert_after": "hsn_code",
			"in_list_view": 1,
			"description": "Safety threshold for automated stock reordering",
		},
	]
}


def setup_custom_fields():
	"""
	Idempotently creates or updates custom fields for Item doctype.
	Called during app installation and migration.
	"""
	create_custom_fields(CUSTOM_FIELDS, update=True)
