# -*- coding: utf-8 -*-
"""
Pharma Retail - Indian GST Taxation Controller
Implements automated Indian GST calculation rules (5%, 12%, 18% slabs)
matching pharmaceutical HSN codes, supporting intra-state (CGST + SGST 50/50 split)
and inter-state (IGST) transactions.
"""

from __future__ import unicode_literals
import json
from decimal import Decimal, ROUND_HALF_UP

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


# Standard Indian GST Slabs for Pharmaceuticals & Healthcare Goods
# Ref: Central Board of Indirect Taxes and Customs (CBIC) Pharma Tax Schedule
HSN_TAX_MAP = {
    # 5% Slabs: Life-saving drugs, insulin, ORS, artificial limbs, diagnostic kits
    "3004.10": 5.0,     # Penicillins / Streptomycins life-saving formulations
    "3004.31": 5.0,     # Insulin and its salts
    "3004.90.11": 5.0,  # Oncology & anti-cancer medications
    "3004.90.12": 5.0,  # Life-saving vaccines & formulations
    "3006.10": 5.0,     # Sterile surgical catgut / sutures (life-saving)
    "9021": 5.0,        # Orthopaedic appliances, splints, hearing aids

    # 12% Slabs: Standard allopathic drugs, bulk medicaments, medical supplies
    "3004": 12.0,       # Medicaments consisting of mixed or unmixed products for retail sale
    "3003": 12.0,       # Bulk medicaments not in dosage form
    "3002": 12.0,       # Human blood, antisera, vaccines, toxins
    "3005": 12.0,       # Bandages, dressings, wadding, gauze
    "3006": 12.0,       # Pharmaceutical goods, first aid kits, ostomy appliances
    "9018": 12.0,       # Medical, surgical, dental or veterinary instruments

    # 18% Slabs: Nutraceuticals, dietary supplements, antiseptics, high-tech devices
    "2106": 18.0,       # Food preparations / Dietary supplements / Nutraceuticals
    "2106.90": 18.0,    # Protein powders, multi-vitamin food supplements
    "3808": 18.0,       # Disinfectants, hand sanitizers, antiseptic liquids
    "3808.94": 18.0,    # Chemical disinfectants
    "3304": 18.0,       # Medicated skincare, barrier creams, acne lotions
    "9018.90": 18.0,    # Advanced electronic diagnostic & surgical capital equipment

    # 0% Exempt Slabs:
    "3002.90": 0.0,     # Whole human blood and cord blood
    "3006.60": 0.0,     # Chemical contraceptive preparations
}

# Special Life-saving keywords that trigger 5% GST on HSN 3004
LIFE_SAVING_SALTS = {
    "insulin", "glargine", "lispro", "aspart", "streptokinase",
    "erythropoietin", "trastuzumab", "imatinib", "rituximab",
    "paclitaxel", "carboplatin", "cisplatin", "doxorubicin",
    "tenecteplase", "amphotericin", "remdesivir", "oral rehydration salts",
    "ors", "heparin", "enoxaparin"
}


def round_currency(value):
    """Accurate banker's / half-up 2 decimal place currency rounding."""
    if isinstance(value, (int, float, str)):
        d = Decimal(str(value))
    elif isinstance(value, Decimal):
        d = value
    else:
        d = Decimal("0.0")
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def resolve_gst_rate(hsn_code=None, salt_composition=None, item_name=None, is_lifesaving=False, override_rate=None):
    """
    Resolve applicable Indian GST rate (0%, 5%, 12%, 18%) based on HSN code and clinical context.
    
    Priority:
    1. Explicit override_rate if passed (> 0).
    2. Exact HSN match (e.g. 3004.31 -> 5%).
    3. Life-saving flag or life-saving salt keyword match in HSN 3004 -> 5%.
    4. 4-digit HSN prefix match (e.g. 3004 -> 12%, 2106 -> 18%, 9018 -> 12%).
    5. 2-digit chapter fallback (30 -> 12%).
    6. Default retail pharmacy slab: 12.0%.
    """
    if override_rate is not None and override_rate != "":
        try:
            return float(override_rate)
        except (ValueError, TypeError):
            pass

    clean_hsn = str(hsn_code or "").strip().replace(" ", "")
    clean_hsn_nodot = clean_hsn.replace(".", "")

    # Priority 1: Life-saving medications under formulations or explicit flag
    if is_lifesaving or clean_hsn_nodot in ("300431", "300410", "30049011", "30049012", "300610"):
        return 5.0

    # Priority 2: Specific exact HSN subhead match (e.g. 3004.31 -> 5%, 3004.10 -> 5%)
    if clean_hsn in ("3004.10", "3004.31", "3004.90.11", "3004.90.12", "3006.10", "9021"):
        return HSN_TAX_MAP[clean_hsn]

    # Priority 3: Life-saving salt keyword match in salt composition or item name
    text_corpus = f"{salt_composition or ''} {item_name or ''}".lower()
    for kw in LIFE_SAVING_SALTS:
        if kw in text_corpus:
            return 5.0

    # Priority 4: Exact HSN match in HSN_TAX_MAP
    if clean_hsn in HSN_TAX_MAP:
        return HSN_TAX_MAP[clean_hsn]

    # Priority 5: 4-digit HSN prefix match
    hsn_4 = clean_hsn[:4] if len(clean_hsn) >= 4 else clean_hsn
    if hsn_4 in HSN_TAX_MAP:
        return HSN_TAX_MAP[hsn_4]

    # Priority 6: 2-digit chapter
    hsn_2 = clean_hsn[:2] if len(clean_hsn) >= 2 else clean_hsn
    if hsn_2 == "30":
        return 12.0
    elif hsn_2 == "21":
        return 18.0
    elif hsn_2 == "90":
        return 12.0

    # Default pharmaceutical retail rate
    return 12.0


def calculate_item_gst(item, is_interstate=False):
    """
    Calculate GST for a single item dictionary.
    
    Item dictionary schema:
    {
        "item_code": "ITM-001",
        "item_name": "Paracetamol 500mg",
        "hsn_code": "3004",
        "qty": 2,
        "rate": 25.0,
        "salt_composition": "Paracetamol 500mg",
        "is_lifesaving": False,
        "gst_rate": 12.0 (optional override)
    }
    """
    qty = float(item.get("qty", 1) or 1)
    rate = float(item.get("rate", 0) or 0)
    net_amount = round_currency(qty * rate)

    hsn_code = str(item.get("hsn_code") or "3004").strip()
    salt = item.get("salt_composition") or ""
    name = item.get("item_name") or item.get("item_code") or ""
    is_lifesaving = bool(item.get("is_lifesaving") or False)
    gst_rate_param = item.get("gst_rate")

    gst_rate = resolve_gst_rate(
        hsn_code=hsn_code,
        salt_composition=salt,
        item_name=name,
        is_lifesaving=is_lifesaving,
        override_rate=gst_rate_param
    )

    if is_interstate:
        cgst_rate = 0.0
        sgst_rate = 0.0
        igst_rate = gst_rate

        cgst_amount = 0.0
        sgst_amount = 0.0
        igst_amount = round_currency(net_amount * (igst_rate / 100.0))
        total_tax = igst_amount
    else:
        cgst_rate = gst_rate / 2.0
        sgst_rate = gst_rate / 2.0
        igst_rate = 0.0

        cgst_amount = round_currency(net_amount * (cgst_rate / 100.0))
        sgst_amount = round_currency(net_amount * (sgst_rate / 100.0))
        igst_amount = 0.0
        total_tax = round_currency(cgst_amount + sgst_amount)

    total_amount = round_currency(net_amount + total_tax)

    return {
        "item_code": item.get("item_code"),
        "item_name": name,
        "hsn_code": hsn_code,
        "qty": qty,
        "rate": rate,
        "taxable_amount": net_amount,
        "gst_rate": gst_rate,
        "cgst_rate": cgst_rate,
        "cgst_amount": cgst_amount,
        "sgst_rate": sgst_rate,
        "sgst_amount": sgst_amount,
        "igst_rate": igst_rate,
        "igst_amount": igst_amount,
        "total_tax": total_tax,
        "total_amount": total_amount,
        "is_lifesaving": is_lifesaving
    }


@whitelist(allow_guest=True)
def calculate_tax(items, is_interstate=False):
    """
    Whitelisted API for Indian GST calculation on cart items.
    
    Args:
        items: List of item dicts or JSON string representation.
        is_interstate: Boolean or truthy string indicating IGST vs (CGST + SGST).
        
    Returns:
        Structured GST summary with itemized tax and HSN breakups.
    """
    # Parse items if passed as JSON string
    if isinstance(items, (str, bytes)):
        try:
            items = json.loads(items)
        except Exception as e:
            if frappe:
                frappe.throw(_("Invalid items JSON: {0}").format(str(e)))
            raise ValueError(f"Invalid items JSON: {e}")

    if not isinstance(items, list):
        items = [items] if items else []

    # Parse boolean
    if isinstance(is_interstate, str):
        is_interstate = is_interstate.strip().lower() in ("true", "1", "yes", "t")
    else:
        is_interstate = bool(is_interstate)

    calculated_items = []
    total_taxable_amount = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_igst = 0.0
    total_tax = 0.0
    
    hsn_summary = {}
    slab_summary = {
        "5%": {"taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_tax": 0.0},
        "12%": {"taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_tax": 0.0},
        "18%": {"taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_tax": 0.0},
        "0%": {"taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_tax": 0.0},
    }

    for itm in items:
        res = calculate_item_gst(itm, is_interstate=is_interstate)
        calculated_items.append(res)

        taxable = res["taxable_amount"]
        cgst = res["cgst_amount"]
        sgst = res["sgst_amount"]
        igst = res["igst_amount"]
        tax = res["total_tax"]
        rate = res["gst_rate"]
        hsn = res["hsn_code"]

        total_taxable_amount += taxable
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst
        total_tax += tax

        # HSN breakdown
        if hsn not in hsn_summary:
            hsn_summary[hsn] = {
                "hsn_code": hsn,
                "taxable_amount": 0.0,
                "gst_rate": rate,
                "cgst_amount": 0.0,
                "sgst_amount": 0.0,
                "igst_amount": 0.0,
                "total_tax": 0.0
            }
        hsn_summary[hsn]["taxable_amount"] = round_currency(hsn_summary[hsn]["taxable_amount"] + taxable)
        hsn_summary[hsn]["cgst_amount"] = round_currency(hsn_summary[hsn]["cgst_amount"] + cgst)
        hsn_summary[hsn]["sgst_amount"] = round_currency(hsn_summary[hsn]["sgst_amount"] + sgst)
        hsn_summary[hsn]["igst_amount"] = round_currency(hsn_summary[hsn]["igst_amount"] + igst)
        hsn_summary[hsn]["total_tax"] = round_currency(hsn_summary[hsn]["total_tax"] + tax)

        # Slab breakdown
        slab_key = f"{int(rate)}%"
        if slab_key not in slab_summary:
            slab_summary[slab_key] = {"taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "total_tax": 0.0}
        slab_summary[slab_key]["taxable_amount"] = round_currency(slab_summary[slab_key]["taxable_amount"] + taxable)
        slab_summary[slab_key]["cgst"] = round_currency(slab_summary[slab_key]["cgst"] + cgst)
        slab_summary[slab_key]["sgst"] = round_currency(slab_summary[slab_key]["sgst"] + sgst)
        slab_summary[slab_key]["igst"] = round_currency(slab_summary[slab_key]["igst"] + igst)
        slab_summary[slab_key]["total_tax"] = round_currency(slab_summary[slab_key]["total_tax"] + tax)

    total_taxable_amount = round_currency(total_taxable_amount)
    total_cgst = round_currency(total_cgst)
    total_sgst = round_currency(total_sgst)
    total_igst = round_currency(total_igst)
    total_tax = round_currency(total_tax)
    grand_total = round_currency(total_taxable_amount + total_tax)

    return {
        "success": True,
        "is_interstate": is_interstate,
        "tax_type": "IGST" if is_interstate else "CGST + SGST",
        "total_taxable_amount": total_taxable_amount,
        "total_cgst": total_cgst,
        "total_sgst": total_sgst,
        "total_igst": total_igst,
        "total_tax": total_tax,
        "grand_total": grand_total,
        "items": calculated_items,
        "hsn_summary": hsn_summary,
        "slab_summary": slab_summary
    }


def get_gst_rate_for_hsn(hsn_code, salt_composition=None, item_name=None, is_lifesaving=False):
    """Convenience alias for resolve_gst_rate matching QA and API expectations."""
    return resolve_gst_rate(
        hsn_code=hsn_code,
        salt_composition=salt_composition,
        item_name=item_name,
        is_lifesaving=is_lifesaving
    )


def calculate_invoice_taxes(items, is_interstate=False):
    """
    Convenience wrapper for calculate_tax providing direct top-level
    cgst_amount, sgst_amount, igst_amount attributes.
    """
    res = calculate_tax(items=items, is_interstate=is_interstate)
    res["cgst_amount"] = res.get("total_cgst", 0.0)
    res["sgst_amount"] = res.get("total_sgst", 0.0)
    res["igst_amount"] = res.get("total_igst", 0.0)
    return res

