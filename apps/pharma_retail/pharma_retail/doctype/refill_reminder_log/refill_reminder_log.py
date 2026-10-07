# Copyright (c) 2026, Aryan Sharma and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class RefillReminderLog(Document):
	def validate(self):
		self.validate_payload()

	def validate_payload(self):
		if self.payload_json and isinstance(self.payload_json, str):
			try:
				json.loads(self.payload_json)
			except Exception as e:
				frappe.throw(_("Invalid JSON in Payload: {0}").format(str(e)))

	def mark_sent(self, response_payload=None):
		self.status = "Sent"
		self.sent_at = now_datetime()
		if response_payload:
			self.payload_json = json.dumps(response_payload, indent=2)
		self.save(ignore_permissions=True)

	def mark_failed(self, error_msg):
		self.status = "Failed"
		self.error_message = str(error_msg)
		self.save(ignore_permissions=True)
