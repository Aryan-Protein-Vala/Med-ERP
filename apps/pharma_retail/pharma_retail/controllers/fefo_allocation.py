# Copyright (c) 2026, Aryan Sharma and contributors
# For license information, please see license.txt

import copy
try:
	import frappe
	from frappe import _
	from frappe.utils import add_days, flt, getdate, today
except ImportError:
	frappe = None
	_ = lambda s: s
	from datetime import datetime, timedelta
	def today(): return datetime.now().strftime("%Y-%m-%d")
	def getdate(d):
		if hasattr(d, "date"): return d.date()
		return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
	def add_days(d, days):
		base = getdate(d) if not isinstance(d, datetime) else d.date()
		return (base + timedelta(days=days)).strftime("%Y-%m-%d")
	def flt(v): return float(v or 0)



def get_fefo_batches(item_code, warehouse=None, required_qty=1.0, allow_partial=True, min_shelf_life_days=0):
	"""
	Strict FEFO (First-Expired, First-Out) batch allocation query and calculation.

	Parameters:
	- item_code (str): Item to allocate batches for
	- warehouse (str): Target warehouse (optional, will filter stock ledger if provided)
	- required_qty (float): Total quantity required
	- allow_partial (bool): If False, raises ValidationError when unexpired stock < required_qty
	- min_shelf_life_days (int): Days buffer; batches expiring within this threshold are rejected

	Returns:
	- list of dicts: [
	    {
	        "batch_no": str,
	        "qty": float,
	        "expiry_date": date,
	        "available_qty": float
	    },
	    ...
	  ]
	"""
	if not item_code:
		return []

	required_qty = flt(required_qty)
	if required_qty <= 0:
		return []

	today_date = getdate(today())
	cutoff_date = add_days(today_date, min_shelf_life_days or 0)

	candidate_batches = []

	if warehouse:
		# Query available unexpired batches directly from Stock Ledger Entries joined with Batch
		query = """
			SELECT
				b.name AS batch_no,
				b.expiry_date,
				b.manufacturing_date,
				b.disabled,
				SUM(sle.actual_qty) AS available_qty
			FROM
				`tabBatch` b
			INNER JOIN
				`tabStock Ledger Entry` sle ON sle.batch_no = b.name
			WHERE
				sle.item_code = %(item_code)s
				AND sle.warehouse = %(warehouse)s
				AND sle.is_cancelled = 0
				AND ifnull(b.disabled, 0) = 0
				AND b.expiry_date IS NOT NULL
				AND b.expiry_date > %(cutoff_date)s
			GROUP BY
				b.name, b.expiry_date, b.manufacturing_date, b.disabled
			HAVING
				available_qty > 0
			ORDER BY
				b.expiry_date ASC,
				b.creation ASC
		"""
		candidate_batches = frappe.db.sql(
			query,
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"cutoff_date": cutoff_date,
			},
			as_dict=True,
		)

	# Fallback if no warehouse specified or no SLE entries found (e.g. testing / master batch qty)
	if not candidate_batches:
		batch_filters = {
			"item": item_code,
			"disabled": 0,
			"expiry_date": [">", cutoff_date],
		}
		batches = frappe.get_all(
			"Batch",
			filters=batch_filters,
			fields=["name as batch_no", "expiry_date", "manufacturing_date", "batch_qty as available_qty"],
			order_by="expiry_date ASC, creation ASC",
		)
		candidate_batches = [b for b in batches if flt(b.get("available_qty", 0)) > 0]

	allocated_batches = []
	remaining_qty = required_qty

	for candidate in candidate_batches:
		avail = flt(candidate.get("available_qty", 0))
		if avail <= 0:
			continue

		alloc_qty = min(avail, remaining_qty)
		allocated_batches.append({
			"batch_no": candidate.batch_no,
			"qty": alloc_qty,
			"expiry_date": candidate.expiry_date,
			"available_qty": avail,
		})
		remaining_qty -= alloc_qty

		if remaining_qty <= 0:
			break

	total_allocated = sum(b["qty"] for b in allocated_batches)

	if remaining_qty > 0 and not allow_partial:
		frappe.throw(
			_(
				"Strict FEFO Allocation Failed: Insufficient unexpired stock for item {0} in warehouse {1}. "
				"Required: {2}, Available unexpired: {3}."
			).format(item_code, warehouse or "All", required_qty, total_allocated),
			frappe.ValidationError,
		)

	return allocated_batches


def validate_batch_expiry(batch_no, item_code=None):
	"""
	Validates that a batch exists, is active, and is not expired.
	Raises ValidationError if expired.
	"""
	if not batch_no:
		return

	batch = frappe.db.get_value(
		"Batch",
		batch_no,
		["name", "item", "expiry_date", "disabled"],
		as_dict=True,
	)

	if not batch:
		frappe.throw(_("Batch {0} does not exist.").format(batch_no), frappe.ValidationError)

	if item_code and batch.item != item_code:
		frappe.throw(
			_("Batch {0} belongs to item {1}, not {2}.").format(batch_no, batch.item, item_code),
			frappe.ValidationError,
		)

	if batch.disabled:
		frappe.throw(_("Batch {0} is disabled and cannot be picked.").format(batch_no), frappe.ValidationError)

	if batch.expiry_date:
		today_date = getdate(today())
		if getdate(batch.expiry_date) <= today_date:
			frappe.throw(
				_(
					"FEFO Violation: Batch {0} expired on {1} and cannot be dispensed or invoiced!"
				).format(batch_no, batch.expiry_date),
				frappe.ValidationError,
			)


def apply_fefo_to_doc(doc, method=None):
	"""
	Hook applied to Sales Invoice, POS Invoice, Delivery Note, and Material Request.
	Validates pre-selected batches for expiry and automatically allocates unallocated
	batches according to strict FEFO principles.
	"""
	items = doc.get("items")
	if not items:
		return

	for row in list(items):
		if not row.item_code:
			continue

		# Check if item is batch-managed
		item_meta = frappe.db.get_value(
			"Item",
			row.item_code,
			["has_batch_no", "is_stock_item"],
			as_dict=True,
		)
		if not item_meta or not item_meta.has_batch_no:
			continue

		# If batch already provided, strictly validate expiry
		if getattr(row, "batch_no", None):
			validate_batch_expiry(row.batch_no, row.item_code)
			continue

		# If no batch provided, auto-allocate using FEFO
		warehouse = (
			getattr(row, "warehouse", None)
			or getattr(row, "from_warehouse", None)
			or getattr(doc, "set_warehouse", None)
			or getattr(doc, "from_warehouse", None)
		)

		qty_to_allocate = flt(row.qty)
		if qty_to_allocate <= 0:
			continue

		fefo_allocations = get_fefo_batches(
			item_code=row.item_code,
			warehouse=warehouse,
			required_qty=qty_to_allocate,
			allow_partial=False,
		)

		if not fefo_allocations:
			frappe.throw(
				_(
					"Row #{0}: No unexpired batch available for item {1} in warehouse {2} under FEFO."
				).format(row.idx, row.item_code, warehouse or "default"),
				frappe.ValidationError,
			)

		# Assign first batch to existing row
		first_alloc = fefo_allocations[0]
		row.batch_no = first_alloc["batch_no"]
		original_qty = row.qty
		row.qty = first_alloc["qty"]
		if hasattr(row, "stock_qty"):
			row.stock_qty = flt(row.qty) * flt(getattr(row, "conversion_factor", 1) or 1)

		# If required qty spans multiple batches, prepare additional split rows
		for subsequent_alloc in fefo_allocations[1:]:
			new_row = doc.append("items", {})
			row_data = row.as_dict() if hasattr(row, "as_dict") and callable(row.as_dict) else dict(row)
			for fieldname, val in row_data.items():
				if fieldname not in ["name", "idx", "batch_no", "qty", "stock_qty", "amount"]:
					if hasattr(new_row, "set") and callable(new_row.set):
						new_row.set(fieldname, val)
					else:
						setattr(new_row, fieldname, val)
			new_row.batch_no = subsequent_alloc["batch_no"]
			new_row.qty = subsequent_alloc["qty"]
			if hasattr(new_row, "stock_qty"):
				new_row.stock_qty = flt(new_row.qty) * flt(getattr(new_row, "conversion_factor", 1) or 1)
			if hasattr(new_row, "rate") and hasattr(new_row, "amount"):
				new_row.amount = flt(new_row.rate) * flt(new_row.qty)
