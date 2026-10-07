"""
Pharma Retail - Refill Reminders API Module
Whitelisted endpoints for triggering chronic patient prescription scans and WhatsApp/SMS payloads.
"""

try:
    import frappe
    whitelist = frappe.whitelist
except ImportError:
    frappe = None
    def whitelist(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        def decorator(fn):
            return fn
        return decorator

from pharma_retail.tasks.cron_refills import (
    process_chronic_refill_reminders,
    find_expiring_chronic_prescriptions,
    build_reminder_payloads
)


@whitelist(allow_guest=True)
def trigger_refill_job(target_days_ahead=3, channel="whatsapp"):
    """
    Whitelisted endpoint: pharma_retail.api.refills.trigger_refill_job
    Executes the background chronic prescription scan and returns generated payloads.
    """
    return process_chronic_refill_reminders(
        target_days_ahead=int(target_days_ahead),
        channel=str(channel)
    )


@whitelist(allow_guest=True)
def get_pending_reminders(target_days_ahead=3):
    """
    Whitelisted endpoint: pharma_retail.api.refills.get_pending_reminders
    Queries upcoming patients with expiring chronic prescriptions without sending.
    """
    patients = find_expiring_chronic_prescriptions(target_days_ahead=int(target_days_ahead))
    payloads = build_reminder_payloads(patients=patients, channel="whatsapp")
    return {
        "success": True,
        "count": len(payloads),
        "target_days_ahead": int(target_days_ahead),
        "reminders": payloads
    }
