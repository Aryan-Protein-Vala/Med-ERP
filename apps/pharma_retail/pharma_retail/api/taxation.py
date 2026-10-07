# -*- coding: utf-8 -*-
"""
Pharma Retail - Taxation API Module
Provides whitelisted endpoints for Indian GST tax calculations.
"""

from __future__ import unicode_literals
import json

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

from pharma_retail.controllers.gst_taxation import calculate_tax as _calculate_tax, resolve_gst_rate


@whitelist(allow_guest=True)
def calculate_tax(items, is_interstate=False):
    """
    Whitelisted API endpoint: pharma_retail.api.taxation.calculate_tax
    Calculates GST (CGST, SGST, IGST) across 5%, 12%, 18% slabs for line items.
    """
    return _calculate_tax(items, is_interstate=is_interstate)


@whitelist(allow_guest=True)
def get_hsn_rate(hsn_code, salt_composition=None, item_name=None, is_lifesaving=False):
    """
    Whitelisted API endpoint: pharma_retail.api.taxation.get_hsn_rate
    Retrieves the applicable GST slab for a given HSN code.
    """
    rate = resolve_gst_rate(
        hsn_code=hsn_code,
        salt_composition=salt_composition,
        item_name=item_name,
        is_lifesaving=bool(is_lifesaving)
    )
    return {
        "success": True,
        "hsn_code": hsn_code,
        "gst_rate": rate,
        "cgst_rate": rate / 2.0,
        "sgst_rate": rate / 2.0,
        "igst_rate": rate
    }
