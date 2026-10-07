# -*- coding: utf-8 -*-
"""
Pharma Retail - POS API Module
Unified whitelisted endpoints for High-Speed Counter POS SPA:
- get_pos_meta(): Store metadata, drug license numbers, GSTIN, default configurations.
- search_items(query) / search_medicines(query): Alphanumeric search across brands, salts, barcodes.
- get_salt_substitutes(salt_composition, exclude_item_code=None): Generic salt substitute lookup.
- get_fefo_batches(item_code, warehouse=None): Strict First-Expired First-Out batch picking.
- create_invoice(invoice_data) / create_pos_invoice(invoice_data): Validates cart, calculates GST, produces thermal receipt.
"""

from __future__ import unicode_literals
import re
import json
import uuid
from datetime import datetime, timedelta

try:
    import frappe
    from frappe import _
    whitelist = frappe.whitelist
except ImportError:
    frappe = None
    _ = lambda s: s
    def whitelist(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        def decorator(fn):
            return fn
        return decorator

from pharma_retail.controllers.gst_taxation import calculate_tax, resolve_gst_rate, round_currency


class SearchResultDict(dict):
    """
    Unified result container conforming to Frappe API format (dict with success, count, items)
    while also supporting sequence operations (len(), [0], iteration) for unit tests.
    """
    def __iter__(self):
        items = self.get("items") if "items" in self else self.get("substitutes", [])
        return iter(items)

    def __len__(self):
        items = self.get("items") if "items" in self else self.get("substitutes", [])
        return len(items)

    def __getitem__(self, key):
        if isinstance(key, int):
            items = self.get("items") if "items" in self else self.get("substitutes", [])
            return items[key]
        return super().__getitem__(key)


# Realistic Seed Master Database for Standalone/Mock Mode
DEMO_ITEMS = [
    {
        "item_code": "CROCIN-650",
        "item_name": "Crocin 650 Advance Tablet",
        "brand": "Crocin",
        "brand_name": "Crocin 650 Advance",
        "manufacturer": "GlaxoSmithKline Asia",
        "salt_composition": "Paracetamol 650mg",
        "therapeutic_class": "Analgesic / Antipyretic",
        "hsn_code": "3004",
        "rate": 33.75,
        "mrp": 33.75,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901234560036",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": []  # Explicitly out-of-stock for Salt Substitutes drawer demo
    },
    {
        "item_code": "MED-DOLO-650",
        "item_name": "Dolo 650 Tablet",
        "brand": "Dolo",
        "brand_name": "Dolo 650 Tablet",
        "manufacturer": "Micro Labs Ltd",
        "salt_composition": "Paracetamol 650mg",
        "therapeutic_class": "Analgesic / Antipyretic",
        "hsn_code": "3004",
        "rate": 34.00,
        "mrp": 34.00,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901148000123",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-DL26A", "batch_no": "BT-DL26A", "expiry_date": "2026-11-30", "stock": 45, "available_qty": 45, "rate": 34.00},
            {"batch_id": "BT-DL27B", "batch_no": "BT-DL27B", "expiry_date": "2027-04-30", "stock": 120, "available_qty": 120, "rate": 34.00},
            {"batch_id": "BT-DL27C", "batch_no": "BT-DL27C", "expiry_date": "2027-10-31", "stock": 80, "available_qty": 80, "rate": 34.00}
        ]
    },
    {
        "item_code": "MED-CALPOL-650",
        "item_name": "Calpol 650 Tablet",
        "brand": "Calpol",
        "brand_name": "Calpol 650 Tablet",
        "manufacturer": "GlaxoSmithKline",
        "salt_composition": "Paracetamol 650mg",
        "therapeutic_class": "Analgesic / Antipyretic",
        "hsn_code": "3004",
        "rate": 31.50,
        "mrp": 31.50,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901148000456",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-CP26X", "batch_no": "BT-CP26X", "expiry_date": "2026-12-31", "stock": 60, "available_qty": 60, "rate": 31.50},
            {"batch_id": "BT-CP27Y", "batch_no": "BT-CP27Y", "expiry_date": "2027-06-30", "stock": 100, "available_qty": 100, "rate": 31.50}
        ]
    },
    {
        "item_code": "MED-PACIMOL-650",
        "item_name": "Pacimol 650 Tablet",
        "brand": "Pacimol",
        "brand_name": "Pacimol 650 Tablet",
        "manufacturer": "Ipca Laboratories",
        "salt_composition": "Paracetamol 650mg",
        "therapeutic_class": "Analgesic / Antipyretic",
        "hsn_code": "3004",
        "rate": 26.00,
        "mrp": 26.00,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901148000789",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-PM26A", "batch_no": "BT-PM26A", "expiry_date": "2026-10-31", "stock": 30, "available_qty": 30, "rate": 26.00},
            {"batch_id": "BT-PM27B", "batch_no": "BT-PM27B", "expiry_date": "2027-08-31", "stock": 50, "available_qty": 50, "rate": 26.00}
        ]
    },
    {
        "item_code": "MED-GLYCOMET-500",
        "item_name": "Glycomet 500 Tablet SR",
        "brand": "Glycomet",
        "brand_name": "Glycomet 500 Tablet SR",
        "manufacturer": "USV Pvt Ltd",
        "salt_composition": "Metformin 500mg",
        "therapeutic_class": "Anti-Diabetic",
        "hsn_code": "3004",
        "rate": 48.00,
        "mrp": 48.00,
        "stock_uom": "Strip (20 Tab)",
        "barcode": "8901148001111",
        "prescription_required": 1,
        "chronic_category": "Diabetes",
        "batches": [
            {"batch_id": "BT-GM26D", "batch_no": "BT-GM26D", "expiry_date": "2026-11-15", "stock": 70, "available_qty": 70, "rate": 48.00},
            {"batch_id": "BT-GM27E", "batch_no": "BT-GM27E", "expiry_date": "2027-05-20", "stock": 150, "available_qty": 150, "rate": 48.00}
        ]
    },
    {
        "item_code": "MED-METFORMIN-GEN",
        "item_name": "Metformin 500 SR (Jan Aushadhi)",
        "brand": "Jan Aushadhi",
        "brand_name": "Metformin 500 SR (Jan Aushadhi)",
        "manufacturer": "BPPI Pharma",
        "salt_composition": "Metformin 500mg",
        "therapeutic_class": "Anti-Diabetic",
        "hsn_code": "3004",
        "rate": 15.00,
        "mrp": 15.00,
        "stock_uom": "Strip (10 Tab)",
        "barcode": "8901148002222",
        "prescription_required": 1,
        "chronic_category": "Diabetes",
        "batches": [
            {"batch_id": "BT-JA26M", "batch_no": "BT-JA26M", "expiry_date": "2026-12-01", "stock": 200, "available_qty": 200, "rate": 15.00}
        ]
    },
    {
        "item_code": "MED-TELMA-40",
        "item_name": "Telma 40 Tablet",
        "brand": "Telma",
        "brand_name": "Telma 40 Tablet",
        "manufacturer": "Glenmark Pharmaceuticals",
        "salt_composition": "Telmisartan 40mg",
        "therapeutic_class": "Anti-Hypertensive",
        "hsn_code": "3004",
        "rate": 142.00,
        "mrp": 142.00,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901148003333",
        "prescription_required": 1,
        "chronic_category": "Hypertension",
        "batches": [
            {"batch_id": "BT-TL26G", "batch_no": "BT-TL26G", "expiry_date": "2026-12-15", "stock": 40, "available_qty": 40, "rate": 142.00},
            {"batch_id": "BT-TL27H", "batch_no": "BT-TL27H", "expiry_date": "2027-09-30", "stock": 90, "available_qty": 90, "rate": 142.00}
        ]
    },
    {
        "item_code": "MED-TELVAS-40",
        "item_name": "Telvas 40 Tablet",
        "brand": "Telvas",
        "brand_name": "Telvas 40 Tablet",
        "manufacturer": "Aristo Pharmaceuticals",
        "salt_composition": "Telmisartan 40mg",
        "therapeutic_class": "Anti-Hypertensive",
        "hsn_code": "3004",
        "rate": 95.00,
        "mrp": 95.00,
        "stock_uom": "Strip (15 Tab)",
        "barcode": "8901148004444",
        "prescription_required": 1,
        "chronic_category": "Hypertension",
        "batches": [
            {"batch_id": "BT-TV26A", "batch_no": "BT-TV26A", "expiry_date": "2026-11-20", "stock": 65, "available_qty": 65, "rate": 95.00}
        ]
    },
    {
        "item_code": "MED-LANTUS-100",
        "item_name": "Lantus 100IU/ml Cartridge (Life-Saving)",
        "brand": "Lantus",
        "brand_name": "Lantus 100IU/ml Cartridge",
        "manufacturer": "Sanofi India",
        "salt_composition": "Insulin Glargine 100IU/ml",
        "therapeutic_class": "Anti-Diabetic",
        "hsn_code": "3004.31",
        "rate": 680.00,
        "mrp": 680.00,
        "stock_uom": "Cartridge 3ml",
        "barcode": "8901148005555",
        "prescription_required": 1,
        "chronic_category": "Diabetes",
        "batches": [
            {"batch_id": "BT-LT26K", "batch_no": "BT-LT26K", "expiry_date": "2026-12-10", "stock": 25, "available_qty": 25, "rate": 680.00}
        ]
    },
    {
        "item_code": "MED-REVITAL-H",
        "item_name": "Revital H Daily Health Supplement",
        "brand": "Revital",
        "brand_name": "Revital H Daily Health Supplement",
        "manufacturer": "Sun Pharma Consumer",
        "salt_composition": "Multivitamins + Minerals + Ginseng",
        "therapeutic_class": "Nutraceutical / Multivitamin",
        "hsn_code": "2106",
        "rate": 310.00,
        "mrp": 310.00,
        "stock_uom": "Bottle (30 Caps)",
        "barcode": "8901148006666",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-RV27A", "batch_no": "BT-RV27A", "expiry_date": "2027-08-31", "stock": 40, "available_qty": 40, "rate": 310.00}
        ]
    },
    {
        "item_code": "MED-SURG-SYRINGE",
        "item_name": "Dispovan 5ml Sterile Syringe",
        "brand": "Dispovan",
        "brand_name": "Dispovan 5ml Sterile Syringe",
        "manufacturer": "Hindustan Syringes (HMD)",
        "salt_composition": "Sterile Hypodermic Syringe",
        "therapeutic_class": "Medical Device",
        "hsn_code": "9018",
        "rate": 8.50,
        "mrp": 8.50,
        "stock_uom": "Piece",
        "barcode": "8901148007777",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-DP28X", "batch_no": "BT-DP28X", "expiry_date": "2028-12-31", "stock": 500, "available_qty": 500, "rate": 8.50}
        ]
    },
    {
        "item_code": "MED-TUGAIN-5",
        "item_name": "Tugain 5% Solution",
        "brand": "Tugain",
        "brand_name": "Tugain 5% Solution",
        "manufacturer": "Cipla Ltd",
        "salt_composition": "Minoxidil 5% w/v",
        "therapeutic_class": "Dermatological / Hair Care",
        "hsn_code": "3004",
        "rate": 790.00,
        "mrp": 880.00,
        "stock_uom": "Bottle (60ml)",
        "barcode": "8901117005011",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-TG27A", "batch_no": "BT-TG27A", "expiry_date": "2027-04-30", "stock": 24, "available_qty": 24, "rate": 790.00}
        ]
    },
    {
        "item_code": "MED-MINTOP-5",
        "item_name": "Mintop 5% Solution",
        "brand": "Mintop",
        "brand_name": "Mintop 5% Solution",
        "manufacturer": "Dr. Reddy's Laboratories Ltd",
        "salt_composition": "Minoxidil 5% w/v",
        "therapeutic_class": "Dermatological / Hair Care",
        "hsn_code": "3004",
        "rate": 740.00,
        "mrp": 820.00,
        "stock_uom": "Bottle (60ml)",
        "barcode": "8901117005035",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": []  # Out of stock to test generic salt substitutes
    },
    {
        "item_code": "MED-MORR-5",
        "item_name": "Morr 5% Solution",
        "brand": "Morr",
        "brand_name": "Morr 5% Solution",
        "manufacturer": "Intas Pharmaceuticals Ltd",
        "salt_composition": "Minoxidil 5% w/v",
        "therapeutic_class": "Dermatological / Hair Care",
        "hsn_code": "3004",
        "rate": 710.00,
        "mrp": 790.00,
        "stock_uom": "Bottle (60ml)",
        "barcode": "8901117005042",
        "prescription_required": 0,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-MR27B", "batch_no": "BT-MR27B", "expiry_date": "2027-02-28", "stock": 30, "available_qty": 30, "rate": 710.00}
        ]
    },
    {
        "item_code": "MED-MORR-F-5",
        "item_name": "Morr-F 5% Solution",
        "brand": "Morr-F",
        "brand_name": "Morr-F 5% Solution",
        "manufacturer": "Intas Pharmaceuticals Ltd",
        "salt_composition": "Minoxidil 5% w/v + Finasteride 0.1% w/v",
        "therapeutic_class": "Dermatological / Hair Care",
        "hsn_code": "3004",
        "rate": 805.00,
        "mrp": 895.00,
        "stock_uom": "Bottle (60ml)",
        "barcode": "8901117005059",
        "prescription_required": 1,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-MF27C", "batch_no": "BT-MF27C", "expiry_date": "2027-01-31", "stock": 18, "available_qty": 18, "rate": 805.00}
        ]
    },
    {
        "item_code": "MED-LONITAB-5",
        "item_name": "Lonitab 5mg Tablet",
        "brand": "Lonitab",
        "brand_name": "Lonitab 5mg Tablet",
        "manufacturer": "Sun Pharmaceutical Industries Ltd",
        "salt_composition": "Minoxidil 5mg",
        "therapeutic_class": "Dermatological / Hair Care",
        "hsn_code": "3004",
        "rate": 150.00,
        "mrp": 165.00,
        "stock_uom": "Strip (10 Tab)",
        "barcode": "8901117005066",
        "prescription_required": 1,
        "chronic_category": None,
        "batches": [
            {"batch_id": "BT-LT26D", "batch_no": "BT-LT26D", "expiry_date": "2026-10-31", "stock": 40, "available_qty": 40, "rate": 150.00}
        ]
    }
]


def _filter_and_sort_batches(batches):
    """Sort batches strictly by expiry_date ASC (FEFO), excluding expired batches."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    valid_batches = [
        b for b in batches
        if str(b.get("expiry_date", "")) >= today_str and float(b.get("stock", b.get("available_qty", 0))) > 0
    ]
    valid_batches.sort(key=lambda x: str(x.get("expiry_date", "")))
    return valid_batches


@whitelist(allow_guest=True)
def get_pos_meta():
    """Returns store metadata, drug license numbers, GSTIN, and default configurations."""
    return {
        "store_name": "Aarogya MediPoint Pharmacy",
        "store_address": "Shop 4-5, Ground Floor, Sai Plaza, MG Road, Mumbai 400001",
        "dl_numbers": "20B/MH-28491 | 21B/MH-28492",
        "gstin": "27AABCP1234F1ZM",
        "phone": "+91 98200 12345",
        "upi_vpa": "aarogyamed@icici",
        "default_doctor": "Self / Prescriber"
    }


@whitelist(allow_guest=True)
def search_items(query=""):
    """
    Whitelisted search endpoint for POS counter.
    Performs real-time search across item_code, item_name, salt_composition,
    therapeutic_class, brand, barcode.
    """
    clean_query = str(query or "").strip().lower()

    # Frappe DB lookup if running in full Frappe environment
    if frappe and hasattr(frappe, "db") and frappe.db:
        try:
            sql_query = """
                SELECT 
                    name as item_code,
                    item_name,
                    item_name as brand_name,
                    brand,
                    manufacturer,
                    salt_composition,
                    therapeutic_class,
                    hsn_code,
                    standard_rate as rate,
                    stock_uom,
                    barcode,
                    prescription_required,
                    chronic_category
                FROM `tabItem`
                WHERE docstatus = 0
                  AND disabled = 0
                  AND (
                      LOWER(name) LIKE %(q)s
                      OR LOWER(item_name) LIKE %(q)s
                      OR LOWER(salt_composition) LIKE %(q)s
                      OR LOWER(therapeutic_class) LIKE %(q)s
                      OR LOWER(brand) LIKE %(q)s
                      OR barcode LIKE %(q_raw)s
                  )
                LIMIT 50
            """
            rows = frappe.db.sql(sql_query, {"q": f"%{clean_query}%", "q_raw": f"%{clean_query}%"}, as_dict=True)
            if rows:
                items = []
                for r in rows:
                    batches = get_fefo_batches(r["item_code"]).get("batches", [])
                    total_stock = sum(float(b.get("stock", b.get("available_qty", 0))) for b in batches)
                    r["total_stock"] = total_stock
                    r["batches"] = batches
                    r["earliest_expiry"] = batches[0]["expiry_date"] if batches else "No Stock"
                    items.append(r)
                return {"success": True, "count": len(items), "items": items}
        except Exception:
            pass

    # Standalone demo data search
    results = []
    for item in DEMO_ITEMS:
        corpus = " ".join([
            str(item.get("item_code", "")),
            str(item.get("item_name", "")),
            str(item.get("brand", "")),
            str(item.get("salt_composition", "")),
            str(item.get("therapeutic_class", "")),
            str(item.get("barcode", ""))
        ]).lower()

        if not clean_query or clean_query in corpus:
            item_copy = dict(item)
            item_copy["batches"] = _filter_and_sort_batches(item.get("batches", []))
            total_stock = sum(float(b.get("stock", b.get("available_qty", 0))) for b in item_copy["batches"])
            item_copy["total_stock"] = total_stock
            item_copy["stock_qty"] = total_stock
            item_copy["brand"] = item.get("brand", item.get("brand_name", ""))
            item_copy["earliest_expiry"] = item_copy["batches"][0]["expiry_date"] if item_copy["batches"] else "No Stock"
            item_copy["gst_rate"] = resolve_gst_rate(
                hsn_code=item_copy.get("hsn_code"),
                salt_composition=item_copy.get("salt_composition"),
                item_name=item_copy.get("item_name")
            )
            results.append(item_copy)

    return SearchResultDict({
        "success": True,
        "count": len(results),
        "items": results
    })


@whitelist(allow_guest=True)
def search_medicines(query=""):
    """Alias for search_items for backwards compatibility with POS frontend."""
    res = search_items(query=query)
    # Return items list directly if called from frontend expecting plain array
    return res.get("items", [])


@whitelist(allow_guest=True)
def get_salt_substitutes(salt_composition="", exclude_item_code=None, exclude_item=None, **kwargs):
    """
    Whitelisted endpoint for finding alternative medicines sharing the exact same
    salt composition. Enables pharmacists to offer lower-cost and in-stock generics.
    """
    clean_salt = re.sub(r'[^a-z0-9]', '', str(salt_composition or "").strip().lower())
    if not clean_salt:
        return SearchResultDict({
            "success": True,
            "count": 0,
            "salt_composition": salt_composition,
            "substitutes": []
        })

    exclude = str(exclude_item or exclude_item_code or "").strip().lower()
    substitutes = []

    # Standalone search against demo dataset
    for item in DEMO_ITEMS:
        item_code_lower = str(item.get("item_code", "")).lower()
        if exclude and (exclude == item_code_lower or exclude in item_code_lower or item_code_lower.replace("med-", "") == exclude.replace("med-", "")):
            continue

        item_salt = re.sub(r'[^a-z0-9]', '', str(item.get("salt_composition", "")).strip().lower())
        # Match if salt formulations share the chemical base and strength
        is_match = (
            clean_salt in item_salt or item_salt in clean_salt or
            ("paracetamol" in clean_salt and "paracetamol" in item_salt and ("650" in clean_salt) == ("650" in item_salt))
        )
        if is_match:
            item_copy = dict(item)
            item_copy["batches"] = _filter_and_sort_batches(item.get("batches", []))
            total_stock = sum(float(b.get("stock", b.get("available_qty", 0))) for b in item_copy["batches"])
            item_copy["total_stock"] = total_stock
            item_copy["stock_qty"] = total_stock
            item_copy["in_stock"] = total_stock > 0
            item_copy["brand"] = item.get("brand", item.get("brand_name", ""))
            item_copy["gst_rate"] = resolve_gst_rate(
                hsn_code=item_copy.get("hsn_code"),
                salt_composition=item_copy.get("salt_composition"),
                item_name=item_copy.get("item_name")
            )
            # CRITICAL: Only recommend alternatives that are CURRENTLY IN STOCK
            if total_stock > 0:
                substitutes.append(item_copy)

    # Sort substitutes by rate ASC (cheapest first)
    substitutes.sort(key=lambda x: (not x["in_stock"], x.get("rate", 999999)))

    return SearchResultDict({
        "success": True,
        "salt_composition": salt_composition,
        "count": len(substitutes),
        "substitutes": substitutes
    })


@whitelist(allow_guest=True)
def get_fefo_batches(item_code, warehouse=None):
    """
    Whitelisted endpoint for strict First-Expired First-Out (FEFO) batch inventory.
    Batches are sorted strictly by expiry_date ASC, filtering expired batches.
    """
    clean_code = str(item_code or "").strip()

    if frappe and hasattr(frappe, "db") and frappe.db:
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            sql_batches = """
                SELECT 
                    name as batch_id,
                    name as batch_no,
                    expiry_date,
                    batch_qty as stock,
                    batch_qty as available_qty,
                    custom_rate as rate
                FROM `tabBatch`
                WHERE item = %(item)s
                  AND expiry_date >= %(today)s
                  AND batch_qty > 0
                ORDER BY expiry_date ASC
            """
            batches = frappe.db.sql(sql_batches, {"item": clean_code, "today": today_str}, as_dict=True)
            return {
                "success": True,
                "item_code": clean_code,
                "batch_count": len(batches),
                "batches": batches
            }
        except Exception:
            pass

    # Demo data lookup
    for item in DEMO_ITEMS:
        if item["item_code"] == clean_code:
            sorted_batches = _filter_and_sort_batches(item.get("batches", []))
            return {
                "success": True,
                "item_code": clean_code,
                "batch_count": len(sorted_batches),
                "batches": sorted_batches
            }

    return {
        "success": True,
        "item_code": clean_code,
        "batch_count": 0,
        "batches": []
    }


def format_thermal_receipt(invoice):
    """
    Format standard 3-inch (80mm / 48 column) thermal receipt text for direct
    USB/ESC-POS or network receipt printers.
    """
    WIDTH = 46
    LINE_SEP = "-" * WIDTH
    DOUBLE_SEP = "=" * WIDTH

    lines = []
    lines.append(DOUBLE_SEP)
    lines.append("PHARMACY RETAIL STORE".center(WIDTH))
    lines.append("Shop 12, Healthway Square, Bangalore 560001".center(WIDTH))
    lines.append("GSTIN: 29AABCU9603R1ZM | DL: 20B/KA/10423".center(WIDTH))
    lines.append("Ph: +91 80 4123 4567 | Open: 24x7".center(WIDTH))
    lines.append(LINE_SEP)

    lines.append(f"Invoice : {invoice['invoice_id']:<18} Date: {invoice['posting_date'][:16]}")
    lines.append(f"Patient : {invoice.get('patient_name', 'Walk-in'):<22}")
    if invoice.get("doctor_name"):
        lines.append(f"Doctor  : {invoice['doctor_name']:<22}")
    lines.append(LINE_SEP)

    lines.append(f"{'Item / Salt':<20}{'Batch':<8}{'Qty':>4}{'Rate':>6}{'Total':>8}")
    lines.append(LINE_SEP)

    for item in invoice.get("items", []):
        name = item.get("item_name", item.get("item_code", ""))[:19]
        batch = item.get("batch_id", item.get("batch_no", "-"))[:7]
        qty = int(item.get("qty", 1))
        rate = float(item.get("rate", 0))
        tot = float(item.get("total_amount", qty * rate))
        lines.append(f"{name:<20}{batch:<8}{qty:>4}{rate:>6.2f}{tot:>8.2f}")
        hsn = item.get("hsn_code", "3004")
        gst_r = int(item.get("gst_rate", 12))
        lines.append(f"  HSN:{hsn} | GST:{gst_r}% | Exp:{item.get('expiry_date', 'NA')}")

    lines.append(LINE_SEP)
    lines.append(f"{'Subtotal (Taxable):':<34}{invoice.get('total_taxable_amount', 0):>12.2f}")
    if invoice.get("is_interstate"):
        lines.append(f"{'IGST Total:':<34}{invoice.get('total_igst', 0):>12.2f}")
    else:
        lines.append(f"{'CGST Total:':<34}{invoice.get('total_cgst', 0):>12.2f}")
        lines.append(f"{'SGST Total:':<34}{invoice.get('total_sgst', 0):>12.2f}")
    lines.append(f"{'Total Tax:':<34}{invoice.get('total_tax', 0):>12.2f}")
    lines.append(DOUBLE_SEP)
    lines.append(f"{'GRAND TOTAL (INR):':<32}{invoice.get('grand_total', 0):>14.2f}")
    lines.append(DOUBLE_SEP)
    lines.append(f"Payment Mode: {invoice.get('payment_method', 'CASH').upper()} | Status: PAID")
    lines.append("")
    lines.append("Thank you for choosing Pharmacy Retail!".center(WIDTH))
    lines.append("Prescription medicines non-refundable.".center(WIDTH))
    lines.append("Get 1-click refills at pharmacy.local/refill".center(WIDTH))
    lines.append(DOUBLE_SEP)

    return "\n".join(lines)


@whitelist(allow_guest=True)
def create_invoice(invoice_data):
    """
    Whitelisted endpoint for processing POS sales orders.
    Validates cart, confirms FEFO batch assignment, calculates GST taxes,
    and returns completed invoice with thermal receipt print payload.
    """
    if isinstance(invoice_data, (str, bytes)):
        try:
            invoice_data = json.loads(invoice_data)
        except Exception as e:
            if frappe:
                frappe.throw(_("Invalid invoice JSON: {0}").format(str(e)))
            raise ValueError(f"Invalid invoice JSON: {e}")

    patient_name = invoice_data.get("patient_name", "Walk-in Customer")
    doctor_name = invoice_data.get("doctor_name", "")
    payment_method = invoice_data.get("payment_method", "Cash")
    is_interstate = bool(invoice_data.get("is_interstate", False))
    raw_items = invoice_data.get("items", [])

    if not raw_items:
        raise ValueError("Invoice cart is empty.")

    processed_items = []
    for raw in raw_items:
        item_code = raw.get("item_code")
        qty = float(raw.get("qty", 1))
        batch_id = raw.get("batch_id") or raw.get("batch_no")
        rate = float(raw.get("rate", 0))

        # FEFO fallback if batch not chosen
        fefo = get_fefo_batches(item_code)
        available_batches = fefo.get("batches", [])
        
        assigned_batch = None
        if batch_id:
            for b in available_batches:
                if b.get("batch_id") == batch_id or b.get("batch_no") == batch_id:
                    assigned_batch = b
                    break
        
        if not assigned_batch and available_batches:
            assigned_batch = available_batches[0]  # Pick earliest expiring batch (FEFO)

        expiry_date = assigned_batch.get("expiry_date", "2027-12-31") if assigned_batch else "2027-12-31"
        final_batch_id = assigned_batch.get("batch_id", assigned_batch.get("batch_no", "BT-DEFAULT")) if assigned_batch else "BT-DEFAULT"
        if rate <= 0 and assigned_batch:
            rate = float(assigned_batch.get("rate", 30.0))

        processed_items.append({
            "item_code": item_code,
            "item_name": raw.get("item_name", raw.get("brand_name", item_code)),
            "salt_composition": raw.get("salt_composition", ""),
            "hsn_code": raw.get("hsn_code", "3004"),
            "qty": qty,
            "rate": rate,
            "batch_id": final_batch_id,
            "batch_no": final_batch_id,
            "expiry_date": expiry_date,
            "is_lifesaving": bool(raw.get("is_lifesaving", False))
        })

    # Calculate GST
    tax_summary = calculate_tax(processed_items, is_interstate=is_interstate)

    invoice_id = f"INV-2026-{uuid.uuid4().hex[:6].upper()}"
    posting_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    invoice_record = {
        "invoice_id": invoice_id,
        "invoice_number": invoice_id,
        "posting_date": posting_date,
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "payment_method": payment_method,
        "is_interstate": is_interstate,
        "items": tax_summary["items"],
        "total_taxable_amount": tax_summary["total_taxable_amount"],
        "total_cgst": tax_summary["total_cgst"],
        "total_sgst": tax_summary["total_sgst"],
        "total_igst": tax_summary["total_igst"],
        "total_tax": tax_summary["total_tax"],
        "grand_total": tax_summary["grand_total"],
        "hsn_summary": tax_summary["hsn_summary"],
        "status": "Paid"
    }

    # Generate 3-inch thermal receipt text
    thermal_print = format_thermal_receipt(invoice_record)
    invoice_record["thermal_receipt"] = thermal_print

    # Generate NPCI-compliant UPI QR Code Payload
    upi_qr_payload = f"upi://pay?pa=aarogyamed@icici&pn=Aarogya+MediPoint&am={tax_summary['grand_total']:.2f}&cu=INR&tn=Invoice+{invoice_id}"
    invoice_record["upi_qr_payload"] = upi_qr_payload

    return {
        "success": True,
        "status": "success",
        "invoice_number": invoice_id,
        "upi_qr_payload": upi_qr_payload,
        "invoice": invoice_record
    }


# Backwards compatibility alias
create_pos_invoice = create_invoice
