# Copyright (c) 2026, Aryan Sharma and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, today


class PharmacyPrescription(Document):
	def validate(self):
		self.validate_mobile()
		self.validate_items()
		self.set_expiry_date()
		self.set_child_item_refill_dates()
		self.check_status_expiry()

	def validate_mobile(self):
		if not self.patient_mobile:
			frappe.throw(_("Patient Mobile number is mandatory."), frappe.ValidationError)
		cleaned_mobile = re.sub(r"[^\d+]", "", str(self.patient_mobile).strip())
		if len(cleaned_mobile) < 10:
			frappe.throw(_("Patient Mobile must contain at least 10 valid digits."), frappe.ValidationError)
		self.patient_mobile = cleaned_mobile

	def validate_items(self):
		if not self.get("items"):
			frappe.throw(_("Prescription must contain at least one prescribed medication item."), frappe.ValidationError)

	def set_expiry_date(self):
		if not self.prescription_date:
			self.prescription_date = today()
		duration = int(self.duration_days or 30)
		if duration <= 0:
			duration = 30
			self.duration_days = 30
		if not self.expiry_date:
			self.expiry_date = add_days(self.prescription_date, duration)

	def set_child_item_refill_dates(self):
		rx_date = getdate(self.prescription_date or today())
		for item in self.get("items", []):
			days = int(item.days_supply or 30)
			if not item.next_refill_date:
				item.next_refill_date = add_days(rx_date, days)

	def check_status_expiry(self):
		if self.expiry_date and getdate(self.expiry_date) < getdate(today()):
			if self.status not in ["Refilled", "Cancelled"]:
				self.status = "Expired"


def validate_prescription(doc, method=None):
	"""Hook function callable from doc_events"""
	if isinstance(doc, PharmacyPrescription):
		doc.validate()
