#!/usr/bin/env python3
"""Comprehensive verification of STEP 1: Frappe Bench Workspace Setup."""

import os
import sys
import json
from pathlib import Path

BENCH_DIR = Path("/Users/aryansharma/Desktop/ERP/frappe-bench")

def test_directories():
    assert BENCH_DIR.is_dir(), "frappe-bench directory missing"
    assert (BENCH_DIR / "apps").is_dir(), "frappe-bench/apps missing"
    assert (BENCH_DIR / "sites").is_dir(), "frappe-bench/sites missing"
    assert (BENCH_DIR / "config").is_dir(), "frappe-bench/config missing"
    assert (BENCH_DIR / "logs").is_dir(), "frappe-bench/logs missing"
    print("✓ 1. frappe-bench base directories verified")

def test_core_apps():
    frappe_dir = BENCH_DIR / "apps" / "frappe"
    erpnext_dir = BENCH_DIR / "apps" / "erpnext"
    assert frappe_dir.is_dir(), "frappe app missing"
    assert erpnext_dir.is_dir(), "erpnext app missing"

    # Check frappe hooks and modules
    assert (frappe_dir / "frappe" / "hooks.py").is_file(), "frappe hooks.py missing"
    assert (frappe_dir / "frappe" / "modules.txt").is_file(), "frappe modules.txt missing"
    assert (frappe_dir / "pyproject.toml").is_file() or (frappe_dir / "setup.py").is_file(), "frappe package definition missing"

    # Check erpnext hooks and modules
    assert (erpnext_dir / "erpnext" / "hooks.py").is_file(), "erpnext hooks.py missing"
    assert (erpnext_dir / "erpnext" / "modules.txt").is_file(), "erpnext modules.txt missing"
    assert (erpnext_dir / "pyproject.toml").is_file() or (erpnext_dir / "setup.py").is_file(), "erpnext package definition missing"

    print("✓ 2. frappe and erpnext core repositories verified")

def test_pharma_retail_app():
    app_dir = BENCH_DIR / "apps" / "pharma_retail"
    assert app_dir.is_dir(), "pharma_retail missing"

    # Standard package files
    for f in ["setup.py", "requirements.txt", "license.txt", "README.md"]:
        assert (app_dir / f).is_file(), f"pharma_retail {f} missing"

    # Package files
    pkg_dir = app_dir / "pharma_retail"
    for f in ["__init__.py", "hooks.py", "modules.txt", "patches.txt"]:
        assert (pkg_dir / f).is_file(), f"pharma_retail {f} missing"

    # Subdirectories
    for d in ["doctype", "controllers", "utils", "tasks", "api", "public", "www"]:
        assert (pkg_dir / d).is_dir(), f"pharma_retail {d} directory missing"

    print("✓ 3. pharma_retail custom Frappe app structure verified")

def test_site_pharmacy_local():
    site_dir = BENCH_DIR / "sites" / "pharmacy.local"
    assert site_dir.is_dir(), "pharmacy.local site directory missing"

    # site_config.json
    cfg_file = site_dir / "site_config.json"
    assert cfg_file.is_file(), "site_config.json missing"
    with open(cfg_file) as f:
        cfg = json.load(f)

    assert cfg.get("default_currency") == "INR", f"Expected INR currency, got {cfg.get('default_currency')}"
    assert cfg.get("currency_symbol") == "₹", f"Expected ₹ symbol, got {cfg.get('currency_symbol')}"
    assert cfg.get("country") == "India", f"Expected India country, got {cfg.get('country')}"
    assert cfg.get("time_zone") == "Asia/Kolkata", f"Expected Asia/Kolkata, got {cfg.get('time_zone')}"
    assert "db_name" in cfg, "db_name missing in site_config.json"
    assert "db_password" in cfg, "db_password missing in site_config.json"

    # sites/apps.txt
    apps_txt = BENCH_DIR / "sites" / "apps.txt"
    assert apps_txt.is_file(), "sites/apps.txt missing"
    with open(apps_txt) as f:
        apps = [line.strip() for line in f if line.strip()]
    assert "frappe" in apps, "frappe missing from apps.txt"
    assert "erpnext" in apps, "erpnext missing from apps.txt"
    assert "pharma_retail" in apps, "pharma_retail missing from apps.txt"

    # common_site_config.json
    common_cfg = BENCH_DIR / "sites" / "common_site_config.json"
    assert common_cfg.is_file(), "common_site_config.json missing"

    print("✓ 4. pharmacy.local site and configurations verified")

def test_bench_executable():
    bench_bin = BENCH_DIR / "bench"
    assert bench_bin.is_file(), "bench script missing"
    assert os.access(bench_bin, os.X_OK), "bench script is not executable"

    run_pharma = BENCH_DIR / "run_pharma_erp.py"
    assert run_pharma.is_file(), "run_pharma_erp.py missing"
    assert os.access(run_pharma, os.X_OK), "run_pharma_erp.py is not executable"

    print("✓ 5. bench wrapper and runnable entrypoint verified")

if __name__ == "__main__":
    test_directories()
    test_core_apps()
    test_pharma_retail_app()
    test_site_pharmacy_local()
    test_bench_executable()
    print("\nAll STEP 1 verification checks PASSED successfully!")
