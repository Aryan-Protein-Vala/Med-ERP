#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pharma Retail - Comprehensive Automated Test Suite
End-to-End Validation covering Step 1 through Step 5:
- Step 1: Environment files, hooks.py, site_config.json (INR ₹, India domain).
- Step 2: DocTypes, Custom Fields, FEFO batch allocation, DB indexes.
- Step 3: Importer chunked 1,000-row streaming ingestion & master auto-creation.
- Step 4: POS SPA assets, API endpoints, salt substitute lookup, 3-inch thermal print layout.
- Step 5: Indian GST taxation (5%, 12%, 18% slabs) and chronic 3-day refill reminder payloads.
"""

import os
import sys
import json
import time
import unittest
import threading
import urllib.request
import urllib.parse
from decimal import Decimal
from datetime import datetime, timedelta

# Path configuration
BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BENCH_DIR, "apps", "pharma_retail")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if BENCH_DIR not in sys.path:
    sys.path.insert(0, BENCH_DIR)

try:
    import frappe
    if hasattr(frappe, "local") and not hasattr(frappe.local, "flags"):
        frappe.local.flags = getattr(frappe, "_dict", dict)(in_test=True, in_request=False)
except Exception:
    pass

from pharma_retail.controllers import gst_taxation, fefo_allocation
from pharma_retail.tasks import cron_refills
from pharma_retail.api import pos, taxation, refills
from pharma_retail.utils import importer, db_indexes, medicine_seeder, db_seeder
from pharma_retail import commands
from click.testing import CliRunner
import tempfile


# =============================================================================
# STEP 1: ENVIRONMENT, BENCH HOOKS & SITE CONFIGURATION TESTS
# =============================================================================
class TestStep1_EnvironmentAndBench(unittest.TestCase):
    """Audits Step 1: Frappe bench directory structure, apps, sites, and hooks."""

    def test_01_apps_txt_installed_apps(self):
        apps_path = os.path.join(BENCH_DIR, "sites", "apps.txt")
        self.assertTrue(os.path.isfile(apps_path), "sites/apps.txt must exist")
        with open(apps_path, "r", encoding="utf-8") as f:
            content = f.read().splitlines()
        self.assertIn("frappe", content, "frappe must be in apps.txt")
        self.assertIn("erpnext", content, "erpnext must be in apps.txt")
        self.assertIn("pharma_retail", content, "pharma_retail must be in apps.txt")

    def test_02_site_config_indian_compliance(self):
        site_cfg_path = os.path.join(BENCH_DIR, "sites", "pharmacy.local", "site_config.json")
        self.assertTrue(os.path.isfile(site_cfg_path), "sites/pharmacy.local/site_config.json must exist")
        with open(site_cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        
        self.assertEqual(cfg.get("default_currency"), "INR", "Site currency must be INR")
        self.assertEqual(cfg.get("currency_symbol"), "₹", "Site currency symbol must be ₹")
        self.assertEqual(cfg.get("country"), "India", "Site country must be India")
        self.assertEqual(cfg.get("time_zone"), "Asia/Kolkata", "Site timezone must be Asia/Kolkata")
        self.assertIn("pharma_retail", cfg.get("installed_apps", []), "pharma_retail must be in installed_apps")

    def test_03_common_site_config(self):
        common_cfg_path = os.path.join(BENCH_DIR, "sites", "common_site_config.json")
        self.assertTrue(os.path.isfile(common_cfg_path), "sites/common_site_config.json must exist")
        with open(common_cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(cfg.get("webserver_port"), 8000, "Webserver port must be configured to 8000")

    def test_04_hooks_app_and_scheduler(self):
        hooks_path = os.path.join(APP_DIR, "pharma_retail", "hooks.py")
        self.assertTrue(os.path.isfile(hooks_path), "hooks.py must exist")
        
        # Load hooks module or parse AST
        import pharma_retail.hooks as hooks
        self.assertEqual(hooks.app_name, "pharma_retail")
        self.assertEqual(hooks.app_title, "Pharma Retail")
        
        # Verify scheduled task is registered
        self.assertTrue(hasattr(hooks, "scheduler_events"), "hooks must declare scheduler_events")
        daily_events = hooks.scheduler_events.get("daily", [])
        self.assertIn(
            "pharma_retail.tasks.cron_refills.process_chronic_refill_reminders",
            daily_events,
            "Daily cron refill reminder must be registered in hooks.py scheduler_events"
        )

        # Verify FEFO doc_events
        self.assertTrue(hasattr(hooks, "doc_events"), "hooks must declare doc_events")
        self.assertIn("Sales Invoice", hooks.doc_events)


# =============================================================================
# STEP 2: DOCTYPES, CUSTOM FIELDS & FEFO ALLOCATION TESTS
# =============================================================================
class TestStep2_DocTypesAndFEFO(unittest.TestCase):
    """Audits Step 2: Custom DocTypes, Custom Field fixtures, DB indexes, and FEFO allocation."""

    def test_01_doctypes_exist_and_valid_json(self):
        doctypes = [
            "salt_composition",
            "pharmacy_prescription",
            "prescription_item",
            "refill_reminder_log"
        ]
        for dt in doctypes:
            dt_json_path = os.path.join(APP_DIR, "pharma_retail", "doctype", dt, f"{dt}.json")
            self.assertTrue(os.path.isfile(dt_json_path), f"DocType JSON for {dt} must exist at {dt_json_path}")
            with open(dt_json_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            self.assertEqual(schema.get("doctype"), "DocType")
            self.assertTrue(len(schema.get("fields", [])) > 0, f"DocType {dt} must have defined fields")

    def test_02_custom_field_fixtures(self):
        fixtures_path = os.path.join(APP_DIR, "pharma_retail", "fixtures", "custom_field.json")
        self.assertTrue(os.path.isfile(fixtures_path), "fixtures/custom_field.json must exist")
        with open(fixtures_path, "r", encoding="utf-8") as f:
            fixtures = json.load(f)
        
        fieldnames = [f.get("fieldname") for f in fixtures]
        self.assertIn("salt_composition", fieldnames, "Item must have custom field: salt_composition")
        self.assertIn("hsn_code", fieldnames, "Item must have custom field: hsn_code")
        self.assertIn("therapeutic_class", fieldnames, "Item must have custom field: therapeutic_class")
        self.assertIn("minimum_reorder_level", fieldnames, "Item must have custom field: minimum_reorder_level")

    def test_03_database_indexes_definition(self):
        self.assertTrue(hasattr(db_indexes, "INDEX_DEFINITIONS"))
        idx_names = [idx["index_name"] for idx in db_indexes.INDEX_DEFINITIONS]
        self.assertIn("idx_item_search", idx_names)
        self.assertIn("idx_item_hsn", idx_names)
        self.assertIn("idx_batch_fefo", idx_names)
        self.assertIn("idx_bin_stock", idx_names)
        self.assertIn("idx_prescription_refill", idx_names)
        self.assertIn("idx_refill_log_status_date", idx_names)

    def test_04_fefo_batch_sorting_chronological(self):
        """Batches must sort strictly by expiry_date ASC, with nearest expiry picked first."""
        batches = [
            {"batch_id": "BT-C", "expiry_date": "2027-10-31", "stock": 50},
            {"batch_id": "BT-A", "expiry_date": "2026-11-30", "stock": 20},
            {"batch_id": "BT-B", "expiry_date": "2027-02-28", "stock": 30},
        ]
        sorted_batches = pos._filter_and_sort_batches(batches)
        self.assertEqual(sorted_batches[0]["batch_id"], "BT-A")
        self.assertEqual(sorted_batches[1]["batch_id"], "BT-B")
        self.assertEqual(sorted_batches[2]["batch_id"], "BT-C")

    def test_05_fefo_expired_batches_rejection(self):
        """Expired batches (expiry_date < today) must be excluded from dispensing."""
        past_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        future_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        batches = [
            {"batch_id": "BT-EXPIRED", "expiry_date": past_date, "stock": 100},
            {"batch_id": "BT-VALID", "expiry_date": future_date, "stock": 40},
        ]
        sorted_batches = pos._filter_and_sort_batches(batches)
        self.assertEqual(len(sorted_batches), 1)
        self.assertEqual(sorted_batches[0]["batch_id"], "BT-VALID")


# =============================================================================
# STEP 3: HIGH-PERFORMANCE DATA INGESTION & IMPORTER TESTS
# =============================================================================
class TestStep3_DataIngestionAndImporter(unittest.TestCase):
    """Audits Step 3: Chunked 1,000-row streaming ingestion, master auto-creation & FK integrity."""

    def test_01_importer_benchmark_1000_rows(self):
        """Executes transactional 1,000-row ingestion and verifies 0 FK violations."""
        result = importer.run_benchmark(num_records=1000, chunk_size=1000)
        self.assertEqual(result["total_records"], 1000)
        self.assertEqual(result["total_inserted"], 1000)
        self.assertEqual(result["failed_chunks"], 0)
        self.assertEqual(len(result["foreign_key_violations"]), 0, "No foreign key violations allowed")
        self.assertGreater(result["throughput_records_per_sec"], 5000, "Ingestion throughput must exceed 5,000 rows/sec")

    def test_02_dependency_master_auto_creation(self):
        """Verify on-the-fly creation of missing UOM, Manufacturer, Brand, Salt Composition masters."""
        engine = importer.SQLiteEngine(":memory:")
        engine.initialize_schema()
        
        sample_row = {
            "item_name": "Amoxicillin 500mg Capsule",
            "brand": "Mox",
            "salt_composition": "Amoxicillin Trihydrate 500mg",
            "packaging": "Strip of 10 Capsules",
            "mrp": "78.50",
            "manufacturer": "Ranbaxy Laboratories",
            "hsn_code": "3004.10",
            "therapeutic_class": "Antibiotic"
        }
        item_data = importer.map_row_to_item(sample_row)
        
        # Auto-create missing masters
        engine.create_missing_masters(
            item_groups={"Pharmaceuticals"},
            uoms={item_data["stock_uom"]},
            manufacturers={item_data["manufacturer"]},
            brands={item_data["brand"]},
            salts={item_data["salt_composition"]}
        )
        engine.insert_items_batch([item_data])
        
        # Verify master tables have records
        engine.cursor.execute("SELECT COUNT(*) FROM `tabManufacturer` WHERE name = 'Ranbaxy Laboratories'")
        self.assertEqual(engine.cursor.fetchone()[0], 1)
        
        engine.cursor.execute("SELECT COUNT(*) FROM `tabSalt Composition` WHERE name = 'Amoxicillin Trihydrate 500mg'")
        self.assertEqual(engine.cursor.fetchone()[0], 1)

        engine.cursor.execute("SELECT COUNT(*) FROM `tabItem` WHERE item_name = 'Amoxicillin 500mg Capsule'")
        self.assertEqual(engine.cursor.fetchone()[0], 1)
        engine.close()

    def test_03_streaming_seeder_2000_row_batching(self):
        """Test streaming parser with 2,000-row batching and constant memory O(1) execution."""
        sqlite_engine = medicine_seeder.SQLiteEngine(":memory:")
        # Execute streaming ingestion of 4,000 simulated records with 2,000 chunk_size
        result = medicine_seeder.stream_seed_medicines(
            use_simulated=True,
            limit=4000,
            chunk_size=2000,
            engine=sqlite_engine,
            verbose=False
        )
        self.assertEqual(result["total_processed"], 4000)
        self.assertEqual(result["total_inserted"], 4000)
        self.assertEqual(result["batches_committed"], 2, "4,000 records must yield exactly 2 batches of 2,000 rows")
        self.assertEqual(result["db_counts"]["tabItem"], 4000)
        self.assertGreater(result["throughput_records_per_sec"], 5000)
        self.assertEqual(medicine_seeder.DEFAULT_BATCH_SIZE, 2000)
        sqlite_engine.close()

    def test_04_streaming_seeder_dependency_auto_creation(self):
        """Test dynamic auto-creation of missing parent dependencies before batch item insertion."""
        engine = medicine_seeder.SQLiteEngine(":memory:")
        engine.initialize_schema()

        # Test data minimization and mapping
        raw_row = {
            "name": "<span>Augmentin 625 Duo Tablet</span>",
            "price(₹)": "₹ 223.42",
            "manufacturer_name": "GlaxoSmithKline Pharmaceuticals Ltd",
            "pack_size_label": "Strip of 10 Tablets",
            "short_composition1": "Amoxycillin (500mg) + Clavulanic Acid (125mg)"
        }
        mapped = medicine_seeder.map_medicine_row(raw_row)
        self.assertEqual(mapped["item_name"], "Augmentin 625 Duo Tablet")
        self.assertEqual(mapped["standard_rate"], 223.42)
        self.assertEqual(mapped["stock_uom"], "Strip")
        self.assertEqual(mapped["manufacturer"], "GlaxoSmithKline Pharmaceuticals Ltd")
        self.assertEqual(mapped["salt_composition"], "Amoxycillin (500mg) + Clavulanic Acid (125mg)")
        self.assertNotIn("<span>", mapped["item_name"])

        # Auto-create dependencies
        created = engine.create_missing_masters(
            item_groups={"Pharmaceuticals"},
            uoms={mapped["stock_uom"]},
            manufacturers={mapped["manufacturer"]},
            brands={mapped["brand"]},
            salts={mapped["salt_composition"]}
        )
        self.assertEqual(created["uoms"], 1)
        self.assertEqual(created["manufacturers"], 1)
        self.assertEqual(created["brands"], 1)
        self.assertEqual(created["salts"], 1)

        # Bulk insert mapped item
        inserted = engine.bulk_insert_items([mapped])
        engine.commit()
        self.assertEqual(inserted, 1)

        counts = engine.get_counts()
        self.assertEqual(counts["tabItem"], 1)
        self.assertEqual(counts["tabUOM"], 1)
        self.assertEqual(counts["tabManufacturer"], 1)
        self.assertEqual(counts["tabBrand"], 1)
        self.assertEqual(counts["tabSalt Composition"], 1)
        engine.close()

    def test_05_bench_click_command_cli_invocation(self):
        """Test bench CLI Click commands 'seed-pharma-db' and 'seed_pharma_db'."""
        runner = CliRunner()

        # 1. Test CLI help display and parameter declarations
        help_result = runner.invoke(commands.seed_pharma_db, ["--help"])
        self.assertEqual(help_result.exit_code, 0)
        self.assertIn("seed-pharma-db", help_result.output)
        self.assertIn("--chunk-size", help_result.output)
        self.assertIn("--limit", help_result.output)
        self.assertIn("--file", help_result.output)
        self.assertIn("--url", help_result.output)

        # 2. Test actual CLI execution using a temporary CSV file with 20 records and chunk_size=10
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tf:
            tf.write("id,name,price(₹),Is_discontinued,manufacturer_name,type,pack_size_label,short_composition1\n")
            for i in range(1, 21):
                tf.write(f'{i},Test Medicine {i},99.00,FALSE,Cipla Ltd,allopathy,Strip of 10,Paracetamol 500mg\n')
            temp_path = tf.name

        try:
            cli_res = runner.invoke(
                commands.seed_pharma_db,
                ["--file", temp_path, "--chunk-size", "10", "--limit", "20", "--site", "pharmacy.local"]
            )
            self.assertEqual(cli_res.exit_code, 0, f"CLI command failed: {cli_res.output}")
            self.assertIn("SEEDING COMPLETE", cli_res.output)
            self.assertIn("Records Inserted : 20", cli_res.output)
            self.assertIn("Target Site : pharmacy.local", cli_res.output)

            # 3. Test alias command
            alias_res = runner.invoke(
                commands.seed_pharma_db_alias,
                ["--file", temp_path, "--chunk-size", "20", "--limit", "20"]
            )
            self.assertEqual(alias_res.exit_code, 0)
            self.assertIn("SEEDING COMPLETE", alias_res.output)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_06_seeder_alias_and_telemetry_configuration(self):
        """Test db_seeder backwards compatibility module and telemetry constants."""
        self.assertEqual(db_seeder.DEFAULT_BATCH_SIZE, 2000)
        self.assertEqual(db_seeder.DEFAULT_PROGRESS_INTERVAL, 10000)
        self.assertEqual(db_seeder.DEFAULT_HSN, "30049099")
        self.assertEqual(db_seeder.DEFAULT_ITEM_GROUP, "Pharmaceuticals")
        self.assertTrue(callable(db_seeder.stream_seed_medicines))
        self.assertTrue(callable(db_seeder.clean_text))
        self.assertTrue(callable(db_seeder.normalize_uom))
        self.assertTrue(callable(db_seeder.parse_price))


# =============================================================================
# STEP 4: POS SPA FRONTEND, THERMAL RECEIPT & API ENDPOINTS TESTS
# =============================================================================
class TestStep4_POSFrontendAndAPI(unittest.TestCase):
    """Audits Step 4: POS SPA files, API endpoints, Salt Substitutes, and 3-inch thermal printer output."""

    def test_01_pos_spa_assets_exist(self):
        pos_dir = os.path.join(APP_DIR, "pharma_retail", "public", "pos")
        self.assertTrue(os.path.isfile(os.path.join(pos_dir, "index.html")), "pos/index.html must exist")
        self.assertTrue(os.path.isfile(os.path.join(pos_dir, "pos.css")), "pos/pos.css must exist")
        self.assertTrue(os.path.isfile(os.path.join(pos_dir, "pos.js")), "pos/pos.js must exist")

    def test_02_pos_meta_api(self):
        meta = pos.get_pos_meta()
        self.assertIn("store_name", meta)
        self.assertIn("dl_numbers", meta)
        self.assertIn("gstin", meta)
        self.assertTrue(meta["gstin"].startswith("27AABC"))

    def test_03_search_items_api(self):
        # Alphanumeric brand search
        res = pos.search_items(query="dolo")
        self.assertTrue(res["success"])
        self.assertGreater(res["count"], 0)
        first_item = res["items"][0]
        self.assertEqual(first_item["item_code"], "MED-DOLO-650")
        self.assertTrue(len(first_item["batches"]) > 0)
        self.assertEqual(first_item["hsn_code"], "3004")

        # Salt composition search
        res_salt = pos.search_items(query="Paracetamol")
        self.assertTrue(res_salt["success"])
        self.assertGreaterEqual(res_salt["count"], 2)

    def test_04_salt_substitutes_generic_lookup(self):
        """Looking up Paracetamol 650mg must return alternative brands sorted by price/stock."""
        res = pos.get_salt_substitutes(salt_composition="Paracetamol 650mg")
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["count"], 2)
        
        # Verify brand variety
        brands = [s["brand"] for s in res["substitutes"]]
        self.assertTrue("Dolo" in brands or "Calpol" in brands or "Pacimol" in brands)

    def test_05_fefo_batches_api(self):
        res = pos.get_fefo_batches(item_code="MED-DOLO-650")
        self.assertTrue(res["success"])
        batches = res["batches"]
        self.assertGreaterEqual(len(batches), 2)
        # Verify expiry order
        for i in range(len(batches) - 1):
            self.assertLessEqual(batches[i]["expiry_date"], batches[i + 1]["expiry_date"])

    def test_06_create_invoice_and_thermal_receipt_layout(self):
        """Creates invoice, computes GST, and verifies 3-inch (80mm) thermal receipt format."""
        cart_data = {
            "patient_name": "Amitabh Bachchan",
            "doctor_name": "Dr. P. K. Sen",
            "payment_method": "UPI",
            "is_interstate": False,
            "items": [
                {
                    "item_code": "MED-DOLO-650",
                    "item_name": "Dolo 650 Tablet",
                    "qty": 2,
                    "rate": 34.00,
                    "hsn_code": "3004"
                },
                {
                    "item_code": "MED-REVITAL-H",
                    "item_name": "Revital H Daily Supplement",
                    "qty": 1,
                    "rate": 310.00,
                    "hsn_code": "2106"
                }
            ]
        }
        res = pos.create_invoice(cart_data)
        self.assertTrue(res["success"])
        inv = res["invoice"]
        
        # Financial checks
        # Dolo: 2 * 34 = 68.00 (12% GST = 8.16)
        # Revital H: 1 * 310 = 310.00 (18% GST = 55.80)
        # Total Taxable = 378.00, Total Tax = 63.96, Grand Total = 441.96
        self.assertEqual(inv["total_taxable_amount"], 378.00)
        self.assertEqual(inv["total_tax"], 63.96)
        self.assertEqual(inv["grand_total"], 441.96)
        self.assertEqual(inv["total_cgst"], 31.98)
        self.assertEqual(inv["total_sgst"], 31.98)

        # Thermal receipt layout checks
        receipt = inv["thermal_receipt"]
        self.assertIn("PHARMACY RETAIL STORE", receipt)
        self.assertIn("GSTIN:", receipt)
        self.assertIn("DL:", receipt)
        self.assertIn("Amitabh Bachchan", receipt)
        self.assertIn("Dolo 650 Tablet", receipt)
        self.assertIn("Revital H Daily", receipt)
        self.assertIn("GRAND TOTAL", receipt)
        self.assertIn("UPI", receipt)


# =============================================================================
# STEP 5: INDIAN GST TAXATION & CHRONIC REFILL AUTOMATION TESTS
# =============================================================================
class TestStep5_GSTTaxationAndChronicRefills(unittest.TestCase):
    """Audits Step 5: Indian GST (5%, 12%, 18%) slabs, intra/inter-state split, and 3-day refill cron."""

    def test_01_gst_slab_resolution_by_hsn(self):
        # 5% Slabs
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3004.31"), 5.0, "Insulin (3004.31) must be 5%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3004.10"), 5.0, "Penicillins life-saving must be 5%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3004", is_lifesaving=True), 5.0, "Life-saving flag must resolve 5%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3004", salt_composition="Insulin Glargine"), 5.0, "Insulin salt must resolve 5%")

        # 12% Slabs
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3004"), 12.0, "General medicaments (3004) must be 12%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3002"), 12.0, "Vaccines/antisera (3002) must be 12%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="9018"), 12.0, "Medical devices (9018) must be 12%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3005"), 12.0, "Bandages/waddings (3005) must be 12%")

        # 18% Slabs
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="2106"), 18.0, "Nutraceuticals (2106) must be 18%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3808"), 18.0, "Disinfectants/sanitizers (3808) must be 18%")
        self.assertEqual(gst_taxation.resolve_gst_rate(hsn_code="3304"), 18.0, "Medicated skincare (3304) must be 18%")

    def test_02_intra_state_gst_50_50_split(self):
        """Intra-state must divide tax equally between CGST and SGST with 0 IGST."""
        items = [
            {"item_code": "INS-01", "item_name": "Lantus Insulin", "hsn_code": "3004.31", "qty": 1, "rate": 1000.00}, # 5%
            {"item_code": "MED-01", "item_name": "Dolo 650", "hsn_code": "3004", "qty": 1, "rate": 1000.00},         # 12%
            {"item_code": "NUT-01", "item_name": "Protein Powder", "hsn_code": "2106", "qty": 1, "rate": 1000.00}     # 18%
        ]
        res = gst_taxation.calculate_tax(items, is_interstate=False)
        self.assertTrue(res["success"])
        self.assertFalse(res["is_interstate"])
        self.assertEqual(res["total_taxable_amount"], 3000.00)

        # Expected Tax:
        # Item 1 (5%):  CGST 25.00, SGST 25.00, Total 50.00
        # Item 2 (12%): CGST 60.00, SGST 60.00, Total 120.00
        # Item 3 (18%): CGST 90.00, SGST 90.00, Total 180.00
        # Total CGST = 175.00, SGST = 175.00, IGST = 0.00, Total Tax = 350.00
        self.assertEqual(res["total_cgst"], 175.00)
        self.assertEqual(res["total_sgst"], 175.00)
        self.assertEqual(res["total_igst"], 0.00)
        self.assertEqual(res["total_tax"], 350.00)
        self.assertEqual(res["grand_total"], 3350.00)

        # Verify slab summaries
        self.assertEqual(res["slab_summary"]["5%"]["total_tax"], 50.00)
        self.assertEqual(res["slab_summary"]["12%"]["total_tax"], 120.00)
        self.assertEqual(res["slab_summary"]["18%"]["total_tax"], 180.00)

    def test_03_inter_state_gst_igst(self):
        """Inter-state must apply full slab rate to IGST with 0 CGST and 0 SGST."""
        items = [
            {"item_code": "MED-01", "item_name": "Dolo 650", "hsn_code": "3004", "qty": 2, "rate": 500.00} # 12% on 1000.00
        ]
        res = gst_taxation.calculate_tax(items, is_interstate=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["is_interstate"])
        self.assertEqual(res["total_taxable_amount"], 1000.00)
        self.assertEqual(res["total_cgst"], 0.00)
        self.assertEqual(res["total_sgst"], 0.00)
        self.assertEqual(res["total_igst"], 120.00)
        self.assertEqual(res["total_tax"], 120.00)
        self.assertEqual(res["grand_total"], 1120.00)

    def test_04_chronic_refill_reminder_cron_detection(self):
        """Background cron job must scan and identify patients whose supplies expire in 3 days."""
        cron_refills.clear_stored_reminders()
        result = cron_refills.process_chronic_refill_reminders(target_days_remaining=3, channel="whatsapp")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(result["count"], 4, "Should identify at least 4 patients with 3 days supply remaining")
        
        conditions_found = set(r["condition"] for r in result["reminders"])
        self.assertIn("Diabetes", conditions_found)
        self.assertIn("Hypertension", conditions_found)
        self.assertIn("Cardiac", conditions_found)
        self.assertIn("Asthma", conditions_found)

    def test_05_refill_payload_dictionary_schema(self):
        """Verify the exact dictionary structure required for WhatsApp/SMS integration."""
        reminders = cron_refills.get_stored_reminders()
        self.assertTrue(len(reminders) > 0)
        
        sample = reminders[0]
        # Must contain required keys:
        required_keys = ["patient_name", "mobile", "channel", "condition", "medications", "days_remaining", "message", "refill_url"]
        for key in required_keys:
            self.assertIn(key, sample, f"Payload must contain key '{key}'")

        self.assertEqual(sample["days_remaining"], 3)
        self.assertEqual(sample["channel"], "whatsapp")
        self.assertTrue(sample["mobile"].startswith("+91"))
        self.assertTrue(sample["refill_url"].startswith("https://pharmacy.local/refill?id="))
        self.assertIn("Dear", sample["message"])
        self.assertIn("expires in 3 days", sample["message"])

    def test_06_whitelisted_apis(self):
        """Test API endpoints in api/taxation.py and api/refills.py."""
        # Taxation API
        tax_res = taxation.calculate_tax(
            items=[{"item_code": "T-1", "rate": 100, "qty": 1, "hsn_code": "3004"}],
            is_interstate=False
        )
        self.assertTrue(tax_res["success"])
        self.assertEqual(tax_res["total_tax"], 12.0)

        # Refills API
        pending = refills.get_pending_reminders()
        self.assertTrue(pending["success"])
        self.assertGreater(pending["count"], 0)

        triggered = refills.trigger_refill_job(target_days_ahead=3)
        self.assertTrue(triggered["success"])


# =============================================================================
# STEP 6: ALL-IN-ONE RUNNABLE SERVER INTEGRATION TEST
# =============================================================================
class TestStep6_RunnableServerIntegration(unittest.TestCase):
    """Audits the standalone HTTP server serving POS SPA and Frappe APIs on port 8008."""

    @classmethod
    def setUpClass(cls):
        from run_pharma_erp import PharmaHTTPRequestHandler
        from http.server import HTTPServer

        cls.port = 8008
        cls.server = HTTPServer(("127.0.0.1", cls.port), PharmaHTTPRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_01_server_ping_and_cors(self):
        url = f"http://127.0.0.1:{self.port}/api/method/ping"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            cors = resp.headers.get("Access-Control-Allow-Origin")
            self.assertEqual(cors, "*")
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["message"]["status"], "online")

    def test_02_server_pos_search_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/method/pharma_retail.api.pos.search_items?query=calpol"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("message")
            if isinstance(msg, dict):
                self.assertTrue(msg.get("success", True))
                items = msg.get("items", [])
            else:
                items = msg
            self.assertTrue(len(items) > 0)
            self.assertEqual(items[0]["item_code"], "MED-CALPOL-650")

    def test_03_server_taxation_calculate_endpoint_post(self):
        url = f"http://127.0.0.1:{self.port}/api/method/pharma_retail.api.taxation.calculate_tax"
        payload = json.dumps({
            "items": [
                {"item_code": "MED-TEST", "rate": 200, "qty": 2, "hsn_code": "3004"}
            ],
            "is_interstate": False
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["message"]["success"])
            self.assertEqual(data["message"]["total_tax"], 48.00)

    def test_04_server_serves_spa_html(self):
        url = f"http://127.0.0.1:{self.port}/"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode("utf-8")
            self.assertIn("PharmaRetail POS", html)
            self.assertIn("data-theme=\"dark\"", html)


# =============================================================================
# MAIN TEST RUNNER WITH DETAILED SUMMARY REPORT
# =============================================================================
def run_test_suite():
    print("\n" + "=" * 78)
    print("  PHARMA RETAIL ERP - COMPREHENSIVE AUTOMATED TEST SUITE (STEPS 1 - 5)")
    print("=" * 78)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestStep1_EnvironmentAndBench,
        TestStep2_DocTypesAndFEFO,
        TestStep3_DataIngestionAndImporter,
        TestStep4_POSFrontendAndAPI,
        TestStep5_GSTTaxationAndChronicRefills,
        TestStep6_RunnableServerIntegration
    ]

    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))

    runner = unittest.TextTestRunner(verbosity=2)
    start_time = time.time()
    result = runner.run(suite)
    elapsed = time.time() - start_time

    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total - failures - errors
    pass_rate = (passed / total) * 100 if total > 0 else 0

    print("\n" + "=" * 78)
    print("  TEST AUDIT SUMMARY")
    print("=" * 78)
    print(f"  • Total Tests Run    : {total}")
    print(f"  • Tests Passed       : {passed}")
    print(f"  • Test Failures      : {failures}")
    print(f"  • Test Errors        : {errors}")
    print(f"  • Pass Rate          : {pass_rate:.1f}%")
    print(f"  • Elapsed Execution  : {elapsed:.3f} seconds")
    print("=" * 78)

    if failures == 0 and errors == 0:
        print("  🎉 ALL 5 STEPS PASSED 100% WITH ZERO ERRORS OR WARNINGS!")
        print("=" * 78 + "\n")
        return 0
    else:
        print("  ❌ TEST FAILURES DETECTED! AUDIT FAILED.")
        print("=" * 78 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_test_suite())
