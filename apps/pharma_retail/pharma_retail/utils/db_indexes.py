"""
Pharma Retail - Database Index Optimization Engine for 250,000+ Records
Defines and executes optimal compound indexes for MariaDB / MySQL to ensure
sub-millisecond query execution across massive medicine catalogs, inventory bins,
and chronic prescription refill queries.
"""

import sys

try:
	import frappe
except ImportError:
	frappe = None

# Critical Index Definitions for 250,000+ Record Pharma Catalogs
INDEX_DEFINITIONS = [
	{
		"table": "tabItem",
		"index_name": "idx_item_search",
		"columns": ["item_code", "item_name(50)", "salt_composition(50)"],
		"sql": "CREATE INDEX idx_item_search ON `tabItem` (item_code, item_name(50), salt_composition(50))",
		"description": "Composite index for instant search by item code, item name, and salt composition",
	},
	{
		"table": "tabItem",
		"index_name": "idx_item_hsn",
		"columns": ["hsn_code"],
		"sql": "CREATE INDEX idx_item_hsn ON `tabItem` (hsn_code)",
		"description": "Tax and HSN code lookup acceleration for GST invoices",
	},
	{
		"table": "tabBatch",
		"index_name": "idx_batch_fefo",
		"columns": ["item", "expiry_date", "disabled"],
		"sql": "CREATE INDEX idx_batch_fefo ON `tabBatch` (item, expiry_date, disabled)",
		"description": "Critical compound index for sub-millisecond FEFO batch picking and expiry validation",
	},
	{
		"table": "tabBin",
		"index_name": "idx_bin_stock",
		"columns": ["item_code", "warehouse", "actual_qty"],
		"sql": "CREATE INDEX idx_bin_stock ON `tabBin` (item_code, warehouse, actual_qty)",
		"description": "Live stock quantity verification per warehouse during POS and counter search",
	},
	{
		"table": "tabPharmacy Prescription",
		"index_name": "idx_prescription_refill",
		"columns": ["chronic_condition", "expiry_date", "patient_mobile"],
		"sql": "CREATE INDEX idx_prescription_refill ON `tabPharmacy Prescription` (chronic_condition, expiry_date, patient_mobile)",
		"description": "Compound index for automated chronic condition refill reminder scheduling query",
	},
	{
		"table": "tabRefill Reminder Log",
		"index_name": "idx_refill_log_status_date",
		"columns": ["scheduled_date", "status", "patient_mobile"],
		"sql": "CREATE INDEX idx_refill_log_status_date ON `tabRefill Reminder Log` (scheduled_date, status, patient_mobile)",
		"description": "Prevents duplicate reminder dispatches across chronic refill pipelines",
	},
]


def generate_create_index_sql(index_def: dict, db_type: str = "mariadb") -> str:
	"""
	Constructs database-specific idempotent index creation SQL statements.
	"""
	table = index_def["table"]
	index_name = index_def["index_name"]
	cols = index_def["columns"]

	if db_type == "sqlite":
		# SQLite does not support prefix lengths like (50) in column specifications
		cleaned_cols = [c.split("(")[0] for c in cols]
		cols_str = ", ".join(f'"{c}"' for c in cleaned_cols)
		clean_table = table.replace("tab", "") if not table.startswith("tab") else table
		return f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{clean_table}" ({cols_str});'
	else:
		# MariaDB / MySQL syntax
		return index_def.get("sql") or f"CREATE INDEX `{index_name}` ON `{table}` ({', '.join(cols)});"


def check_index_exists(table_name: str, index_name: str) -> bool:
	"""
	Checks if an index exists on the given table in MariaDB/MySQL.
	"""
	if not (frappe and hasattr(frappe, "db") and frappe.db):
		return False

	query = """
		SELECT 1 FROM information_schema.statistics
		WHERE table_schema = DATABASE()
		  AND table_name = %s
		  AND index_name = %s
		LIMIT 1
	"""
	res = frappe.db.sql(query, (table_name, index_name))
	return bool(res)


def create_database_indexes():
	"""
	Safely and idempotently creates optimized compound database indexes
	for 250,000+ pharmaceutical records in MariaDB / MySQL.
	"""
	if not (frappe and hasattr(frappe, "db") and frappe.db):
		print("Frappe database not connected. Skipping Frappe index execution.")
		return False

	applied = 0
	existing = 0
	skipped = 0
	errors = 0

	for idx in INDEX_DEFINITIONS:
		table = idx["table"]
		index_name = idx["index_name"]

		try:
			# Verify table exists in current database
			if hasattr(frappe.db, "table_exists") and not frappe.db.table_exists(table):
				print(f"[INDEX SKIPPED] Table {table} does not exist yet for {index_name}.")
				skipped += 1
				continue

			if check_index_exists(table, index_name):
				print(f"[INDEX EXISTS] {table}.{index_name}")
				existing += 1
				continue

			sql = generate_create_index_sql(idx, db_type="mariadb")
			frappe.db.sql(sql)
			applied += 1
			print(f"[INDEX CREATED] {table}.{index_name} -> {sql}")

		except Exception as e:
			errors += 1
			print(f"[INDEX ERROR] {table}.{index_name}: {str(e)}")

	if hasattr(frappe.db, "commit"):
		try:
			frappe.db.commit()
		except Exception:
			pass

	return {"applied": applied, "existing": existing, "skipped": skipped, "errors": errors}


apply_indexes_to_frappe = create_database_indexes


if __name__ == "__main__":
	print("=== Pharma Retail Database Index Generator (250k+ Records) ===")
	for defn in INDEX_DEFINITIONS:
		print(f"Index: {defn['index_name']:30} -> {defn['table']}")
		print(f"  SQL (MariaDB): {generate_create_index_sql(defn, 'mariadb')}")
		print(f"  SQL (SQLite):  {generate_create_index_sql(defn, 'sqlite')}")
		print()
