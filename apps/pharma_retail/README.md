# Pharma Retail

Pharma Retail is a specialized Frappe application built on ERPNext designed for retail pharmacies, drugstores, and medical retail chains.

## Features

- **Inventory & Batch Tracking**: Real-time batch-level tracking with expiry alerts, FEFO enforcement, and rack/shelf storage allocation.
- **Doctor & Prescription Management**: Track doctor details, prescription uploads, dosage schedules, and refills.
- **Fast Billing & POS**: Rapid counter sales with quick barcode scanning, generic drug substitution suggestions, and schedule drug validations.
- **Regulatory Compliance**: Indian CDSCO compliance, Schedule H / H1 / X drug registers, and GST-compliant invoicing (CGST, SGST, IGST).
- **Purchasing & Supplier Return**: Automated PO generation based on reorder levels, near-expiry vendor returns, and batch cost tracking.

## Installation

```bash
bench get-app pharma_retail
bench --site pharmacy.local install-app pharma_retail
```

## License

MIT
