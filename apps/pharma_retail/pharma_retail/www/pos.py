import frappe
from frappe import _

def get_context(context):
    """
    Supplies context dictionary for the Pharma Retail Point of Sale web application.
    Route: /pos
    """
    context.no_cache = 1
    context.show_sidebar = False
    context.title = _("PharmaRetail Point of Sale")

    # Fetch store details from Pharmacy / Company settings if available
    settings = {
        "store_name": "Aarogya MediPoint Pharmacy",
        "store_address": "Shop 4-5, Ground Floor, Sai Plaza, MG Road, Mumbai 400001",
        "dl_numbers": "20B/MH-28491 | 21B/MH-28492",
        "gstin": "27AABCP1234F1ZM",
        "phone": "+91 98200 12345",
        "upi_vpa": "aarogyamed@icici",
        "cashier": frappe.session.user if hasattr(frappe, "session") and frappe.session.user != "Guest" else "Clerk-01"
    }

    try:
        # If Frappe / ERPNext settings doctypes exist, pull company details
        if frappe.db.exists("DocType", "Company"):
            company = frappe.db.get_single_value("Global Defaults", "default_company")
            if company:
                company_doc = frappe.get_doc("Company", company)
                if getattr(company_doc, "company_name", None):
                    settings["store_name"] = company_doc.company_name
                if getattr(company_doc, "tax_id", None):
                    settings["gstin"] = company_doc.tax_id
    except Exception:
        pass

    context.pos_settings = settings
    context.csrf_token = frappe.sessions.get_csrf_token() if hasattr(frappe, "sessions") else ""
    return context
