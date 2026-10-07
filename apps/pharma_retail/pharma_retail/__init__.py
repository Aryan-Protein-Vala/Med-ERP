__version__ = "0.0.1"

# Ensure frappe.local is safely initialized for standalone execution and unit tests
try:
    import frappe
    if hasattr(frappe, "local") and not hasattr(frappe.local, "flags"):
        frappe.local.flags = getattr(frappe, "_dict", dict)(in_test=True, in_request=False)
except Exception:
    pass
