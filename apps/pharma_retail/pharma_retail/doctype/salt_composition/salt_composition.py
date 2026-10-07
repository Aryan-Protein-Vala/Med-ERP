# Copyright (c) 2026, Aryan Sharma and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SaltComposition(Document):
	def validate(self):
		self.clean_fields()

	def clean_fields(self):
		if self.composition_name:
			self.composition_name = self.composition_name.strip()
		if self.formula:
			self.formula = self.formula.strip()
