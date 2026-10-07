"""
High-Performance Chunked Streaming Importer for Indian Pharmaceutical Records
Handles massive datasets (250,000+ items) with constant memory footprint,
transactional 1,000-row batching, dynamic dependency master creation,
and dual Frappe DB / Standalone (SQLite/MariaDB) backend engines.
"""

import os
import sys
import csv
import time
import argparse
import logging
from abc import ABC, abstractmethod
from typing import Generator, List, Dict, Any, Tuple, Set, Optional

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("pharma_importer")


# =====================================================================
# Database Engine Abstraction
# =====================================================================

class BaseDatabaseEngine(ABC):
    """Abstract interface for database engines supporting batch pharma ingestion."""

    @abstractmethod
    def initialize_schema(self) -> None:
        """Create tables, indexes, and constraints if they do not exist."""
        pass

    @abstractmethod
    def load_master_caches(self) -> Dict[str, Set[str]]:
        """Pre-populate in-memory sets of existing masters."""
        pass

    @abstractmethod
    def create_missing_masters(
        self,
        item_groups: Set[str],
        uoms: Set[str],
        manufacturers: Set[str],
        brands: Set[str],
        salts: Set[str]
    ) -> Dict[str, int]:
        """Insert newly discovered dependency master records."""
        pass

    @abstractmethod
    def begin_transaction(self) -> None:
        """Begin an isolated transactional block."""
        pass

    @abstractmethod
    def commit_transaction(self) -> None:
        """Commit the current transaction."""
        pass

    @abstractmethod
    def rollback_transaction(self) -> None:
        """Rollback the current transaction on error."""
        pass

    @abstractmethod
    def insert_items_batch(self, items: List[Dict[str, Any]]) -> int:
        """Batch insert item records."""
        pass

    @abstractmethod
    def verify_foreign_keys(self) -> List[str]:
        """Verify foreign key integrity; returns list of violation descriptions."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, int]:
        """Return counts of items and dependency masters."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close connection and clean up resources."""
        pass


# =====================================================================
# Standalone SQLite Engine (Zero-dependency & strict FK testing)
# =====================================================================

class SQLiteEngine(BaseDatabaseEngine):
    """
    High-performance SQLite engine with strict foreign key constraints,
    WAL mode, and executemany batching.
    """

    def __init__(self, db_path: str = ":memory:"):
        import sqlite3
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.isolation_level = None  # Autocommit mode, manual BEGIN/COMMIT
        self.cursor = self.conn.cursor()
        
        # Configure SQLite for high-throughput writes and foreign key enforcement
        self.cursor.execute("PRAGMA foreign_keys = ON;")
        if db_path != ":memory:":
            self.cursor.execute("PRAGMA journal_mode = WAL;")
            self.cursor.execute("PRAGMA synchronous = NORMAL;")
        self.cursor.execute("PRAGMA cache_size = -64000;")  # 64MB cache
        self.cursor.execute("PRAGMA temp_store = MEMORY;")

    def initialize_schema(self) -> None:
        self.cursor.execute("BEGIN IMMEDIATE;")
        
        # Dependency Masters
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabItem Group` (
                name TEXT PRIMARY KEY,
                item_group_name TEXT NOT NULL,
                parent_item_group TEXT
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabUOM` (
                name TEXT PRIMARY KEY,
                uom_name TEXT NOT NULL
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabManufacturer` (
                name TEXT PRIMARY KEY,
                manufacturer_name TEXT NOT NULL
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabBrand` (
                name TEXT PRIMARY KEY,
                brand_name TEXT NOT NULL
            );
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabSalt Composition` (
                name TEXT PRIMARY KEY,
                salt_name TEXT NOT NULL
            );
        """)
        
        # Main Medicine Item Master with foreign key constraints
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabItem` (
                item_code TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                item_group TEXT NOT NULL REFERENCES `tabItem Group`(name),
                stock_uom TEXT NOT NULL REFERENCES `tabUOM`(name),
                manufacturer TEXT REFERENCES `tabManufacturer`(name),
                brand TEXT REFERENCES `tabBrand`(name),
                salt_composition TEXT REFERENCES `tabSalt Composition`(name),
                hsn_code TEXT,
                standard_rate REAL DEFAULT 0.0,
                valuation_rate REAL DEFAULT 0.0,
                description TEXT
            );
        """)
        
        # Performance Indexes
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_salt ON `tabItem`(salt_composition);")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_mfg ON `tabItem`(manufacturer);")
        self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_item_hsn ON `tabItem`(hsn_code);")
        
        self.cursor.execute("COMMIT;")

    def load_master_caches(self) -> Dict[str, Set[str]]:
        caches = {
            "item_groups": set(),
            "uoms": set(),
            "manufacturers": set(),
            "brands": set(),
            "salts": set(),
            "items": set()
        }
        
        self.cursor.execute("SELECT name FROM `tabItem Group`;")
        caches["item_groups"] = {row[0] for row in self.cursor.fetchall()}
        
        self.cursor.execute("SELECT name FROM `tabUOM`;")
        caches["uoms"] = {row[0] for row in self.cursor.fetchall()}
        
        self.cursor.execute("SELECT name FROM `tabManufacturer`;")
        caches["manufacturers"] = {row[0] for row in self.cursor.fetchall()}
        
        self.cursor.execute("SELECT name FROM `tabBrand`;")
        caches["brands"] = {row[0] for row in self.cursor.fetchall()}
        
        self.cursor.execute("SELECT name FROM `tabSalt Composition`;")
        caches["salts"] = {row[0] for row in self.cursor.fetchall()}
        
        self.cursor.execute("SELECT item_code FROM `tabItem`;")
        caches["items"] = {row[0] for row in self.cursor.fetchall()}
        
        return caches

    def create_missing_masters(
        self,
        item_groups: Set[str],
        uoms: Set[str],
        manufacturers: Set[str],
        brands: Set[str],
        salts: Set[str]
    ) -> Dict[str, int]:
        counts = {"item_groups": 0, "uoms": 0, "manufacturers": 0, "brands": 0, "salts": 0}
        
        if item_groups:
            params = [(name, name, "All Item Groups") for name in item_groups]
            self.cursor.executemany("INSERT OR IGNORE INTO `tabItem Group` VALUES (?, ?, ?);", params)
            counts["item_groups"] = len(params)
            
        if uoms:
            params = [(name, name) for name in uoms]
            self.cursor.executemany("INSERT OR IGNORE INTO `tabUOM` VALUES (?, ?);", params)
            counts["uoms"] = len(params)
            
        if manufacturers:
            params = [(name, name) for name in manufacturers]
            self.cursor.executemany("INSERT OR IGNORE INTO `tabManufacturer` VALUES (?, ?);", params)
            counts["manufacturers"] = len(params)
            
        if brands:
            params = [(name, name) for name in brands]
            self.cursor.executemany("INSERT OR IGNORE INTO `tabBrand` VALUES (?, ?);", params)
            counts["brands"] = len(params)
            
        if salts:
            params = [(name, name) for name in salts]
            self.cursor.executemany("INSERT OR IGNORE INTO `tabSalt Composition` VALUES (?, ?);", params)
            counts["salts"] = len(params)
            
        return counts

    def begin_transaction(self) -> None:
        self.cursor.execute("BEGIN IMMEDIATE;")

    def commit_transaction(self) -> None:
        self.cursor.execute("COMMIT;")

    def rollback_transaction(self) -> None:
        self.cursor.execute("ROLLBACK;")

    def insert_items_batch(self, items: List[Dict[str, Any]]) -> int:
        query = """
            INSERT OR REPLACE INTO `tabItem` (
                item_code, item_name, item_group, stock_uom,
                manufacturer, brand, salt_composition,
                hsn_code, standard_rate, valuation_rate, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = [
            (
                it["item_code"],
                it["item_name"],
                it["item_group"],
                it["stock_uom"],
                it["manufacturer"],
                it["brand"],
                it["salt_composition"],
                it["hsn_code"],
                it["standard_rate"],
                it["valuation_rate"],
                it["description"]
            )
            for it in items
        ]
        self.cursor.executemany(query, params)
        return len(params)

    def verify_foreign_keys(self) -> List[str]:
        self.cursor.execute("PRAGMA foreign_key_check;")
        rows = self.cursor.fetchall()
        violations = []
        for r in rows:
            violations.append(f"Table '{r[0]}' row {r[1]} failed FK to '{r[2]}'")
        return violations

    def get_stats(self) -> Dict[str, int]:
        stats = {}
        for table in ["tabItem", "tabItem Group", "tabUOM", "tabManufacturer", "tabBrand", "tabSalt Composition"]:
            self.cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
            stats[table] = self.cursor.fetchone()[0]
        return stats

    def close(self) -> None:
        self.conn.close()


# =====================================================================
# Standalone MariaDB Engine (Direct PyMySQL)
# =====================================================================

class MariaDBEngine(BaseDatabaseEngine):
    """
    Direct MariaDB engine using PyMySQL for batching and transactional chunks.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 3306, user: str = "root", password: str = "", db: str = "pharma_retail"):
        import pymysql
        self.conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=db,
            charset="utf8mb4",
            autocommit=False
        )
        self.cursor = self.conn.cursor()

    def initialize_schema(self) -> None:
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabItem Group` (
                `name` VARCHAR(140) PRIMARY KEY,
                `item_group_name` VARCHAR(140) NOT NULL,
                `parent_item_group` VARCHAR(140)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabUOM` (
                `name` VARCHAR(140) PRIMARY KEY,
                `uom_name` VARCHAR(140) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabManufacturer` (
                `name` VARCHAR(140) PRIMARY KEY,
                `manufacturer_name` VARCHAR(140) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabBrand` (
                `name` VARCHAR(140) PRIMARY KEY,
                `brand_name` VARCHAR(140) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabSalt Composition` (
                `name` VARCHAR(255) PRIMARY KEY,
                `salt_name` VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS `tabItem` (
                `item_code` VARCHAR(140) PRIMARY KEY,
                `item_name` VARCHAR(255) NOT NULL,
                `item_group` VARCHAR(140) NOT NULL,
                `stock_uom` VARCHAR(140) NOT NULL,
                `manufacturer` VARCHAR(140),
                `brand` VARCHAR(140),
                `salt_composition` VARCHAR(255),
                `hsn_code` VARCHAR(30),
                `standard_rate` DECIMAL(18, 6) DEFAULT 0.0,
                `valuation_rate` DECIMAL(18, 6) DEFAULT 0.0,
                `description` TEXT,
                CONSTRAINT `fk_item_group` FOREIGN KEY (`item_group`) REFERENCES `tabItem Group` (`name`) ON UPDATE CASCADE,
                CONSTRAINT `fk_item_uom` FOREIGN KEY (`stock_uom`) REFERENCES `tabUOM` (`name`) ON UPDATE CASCADE,
                CONSTRAINT `fk_item_mfg` FOREIGN KEY (`manufacturer`) REFERENCES `tabManufacturer` (`name`) ON UPDATE CASCADE,
                CONSTRAINT `fk_item_salt` FOREIGN KEY (`salt_composition`) REFERENCES `tabSalt Composition` (`name`) ON UPDATE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        self.conn.commit()

    def load_master_caches(self) -> Dict[str, Set[str]]:
        caches = {
            "item_groups": set(),
            "uoms": set(),
            "manufacturers": set(),
            "brands": set(),
            "salts": set(),
            "items": set()
        }
        for table, key in [
            ("tabItem Group", "item_groups"),
            ("tabUOM", "uoms"),
            ("tabManufacturer", "manufacturers"),
            ("tabBrand", "brands"),
            ("tabSalt Composition", "salts"),
            ("tabItem", "items")
        ]:
            col = "item_code" if table == "tabItem" else "name"
            self.cursor.execute(f"SELECT `{col}` FROM `{table}`;")
            caches[key] = {row[0] for row in self.cursor.fetchall()}
        return caches

    def create_missing_masters(
        self,
        item_groups: Set[str],
        uoms: Set[str],
        manufacturers: Set[str],
        brands: Set[str],
        salts: Set[str]
    ) -> Dict[str, int]:
        counts = {"item_groups": 0, "uoms": 0, "manufacturers": 0, "brands": 0, "salts": 0}
        if item_groups:
            self.cursor.executemany(
                "INSERT IGNORE INTO `tabItem Group` (`name`, `item_group_name`, `parent_item_group`) VALUES (%s, %s, %s);",
                [(n, n, "All Item Groups") for n in item_groups]
            )
            counts["item_groups"] = len(item_groups)
        if uoms:
            self.cursor.executemany(
                "INSERT IGNORE INTO `tabUOM` (`name`, `uom_name`) VALUES (%s, %s);",
                [(n, n) for n in uoms]
            )
            counts["uoms"] = len(uoms)
        if manufacturers:
            self.cursor.executemany(
                "INSERT IGNORE INTO `tabManufacturer` (`name`, `manufacturer_name`) VALUES (%s, %s);",
                [(n, n) for n in manufacturers]
            )
            counts["manufacturers"] = len(manufacturers)
        if brands:
            self.cursor.executemany(
                "INSERT IGNORE INTO `tabBrand` (`name`, `brand_name`) VALUES (%s, %s);",
                [(n, n) for n in brands]
            )
            counts["brands"] = len(brands)
        if salts:
            self.cursor.executemany(
                "INSERT IGNORE INTO `tabSalt Composition` (`name`, `salt_name`) VALUES (%s, %s);",
                [(n, n) for n in salts]
            )
            counts["salts"] = len(salts)
        return counts

    def begin_transaction(self) -> None:
        self.conn.begin()

    def commit_transaction(self) -> None:
        self.conn.commit()

    def rollback_transaction(self) -> None:
        self.conn.rollback()

    def insert_items_batch(self, items: List[Dict[str, Any]]) -> int:
        query = """
            INSERT INTO `tabItem` (
                `item_code`, `item_name`, `item_group`, `stock_uom`,
                `manufacturer`, `brand`, `salt_composition`,
                `hsn_code`, `standard_rate`, `valuation_rate`, `description`
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `item_name` = VALUES(`item_name`),
                `item_group` = VALUES(`item_group`),
                `stock_uom` = VALUES(`stock_uom`),
                `manufacturer` = VALUES(`manufacturer`),
                `brand` = VALUES(`brand`),
                `salt_composition` = VALUES(`salt_composition`),
                `hsn_code` = VALUES(`hsn_code`),
                `standard_rate` = VALUES(`standard_rate`),
                `valuation_rate` = VALUES(`valuation_rate`),
                `description` = VALUES(`description`);
        """
        params = [
            (
                it["item_code"],
                it["item_name"],
                it["item_group"],
                it["stock_uom"],
                it["manufacturer"],
                it["brand"],
                it["salt_composition"],
                it["hsn_code"],
                it["standard_rate"],
                it["valuation_rate"],
                it["description"]
            )
            for it in items
        ]
        self.cursor.executemany(query, params)
        return len(params)

    def verify_foreign_keys(self) -> List[str]:
        # InnoDB enforces foreign keys at insert time
        return []

    def get_stats(self) -> Dict[str, int]:
        stats = {}
        for table in ["tabItem", "tabItem Group", "tabUOM", "tabManufacturer", "tabBrand", "tabSalt Composition"]:
            self.cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
            stats[table] = self.cursor.fetchone()[0]
        return stats

    def close(self) -> None:
        self.conn.close()


# =====================================================================
# Native Frappe Database Engine
# =====================================================================

class FrappeEngine(BaseDatabaseEngine):
    """
    Frappe framework native engine using frappe.db API, transactional commits,
    and bulk SQL execution.
    """

    def __init__(self, site: str = "pharmacy.local"):
        import frappe
        self.frappe = frappe
        if not getattr(self.frappe, "db", None):
            self.frappe.init(site=site)
            self.frappe.connect()

    def initialize_schema(self) -> None:
        # Check if tabSalt Composition exists in database; create custom doctype/table if absent
        has_salt = self.frappe.db.sql(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'tabSalt Composition';"
        )
        if not (has_salt and has_salt[0][0] > 0):
            try:
                self.frappe.db.sql("""
                    CREATE TABLE IF NOT EXISTS `tabSalt Composition` (
                        `name` VARCHAR(255) PRIMARY KEY,
                        `salt_name` VARCHAR(255) NOT NULL,
                        `creation` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        `modified` DATETIME DEFAULT CURRENT_TIMESTAMP,
                        `modified_by` VARCHAR(140) DEFAULT 'Administrator',
                        `owner` VARCHAR(140) DEFAULT 'Administrator',
                        `docstatus` INT DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                self.frappe.db.commit()
            except Exception as e:
                logger.warning(f"Note on tabSalt Composition creation: {e}")

    def load_master_caches(self) -> Dict[str, Set[str]]:
        caches = {
            "item_groups": set(),
            "uoms": set(),
            "manufacturers": set(),
            "brands": set(),
            "salts": set(),
            "items": set()
        }
        
        try:
            records = self.frappe.db.sql("SELECT `name` FROM `tabItem Group`;")
            caches["item_groups"] = {r[0] for r in records}
        except Exception:
            pass
            
        try:
            records = self.frappe.db.sql("SELECT `name` FROM `tabUOM`;")
            caches["uoms"] = {r[0] for r in records}
        except Exception:
            pass
            
        try:
            records = self.frappe.db.sql("SELECT `name` FROM `tabManufacturer`;")
            caches["manufacturers"] = {r[0] for r in records}
        except Exception:
            pass
            
        try:
            records = self.frappe.db.sql("SELECT `name` FROM `tabBrand`;")
            caches["brands"] = {r[0] for r in records}
        except Exception:
            pass
            
        try:
            records = self.frappe.db.sql("SELECT `name` FROM `tabSalt Composition`;")
            caches["salts"] = {r[0] for r in records}
        except Exception:
            pass
            
        try:
            records = self.frappe.db.sql("SELECT `item_code` FROM `tabItem`;")
            caches["items"] = {r[0] for r in records}
        except Exception:
            pass
            
        return caches

    def create_missing_masters(
        self,
        item_groups: Set[str],
        uoms: Set[str],
        manufacturers: Set[str],
        brands: Set[str],
        salts: Set[str]
    ) -> Dict[str, int]:
        counts = {"item_groups": 0, "uoms": 0, "manufacturers": 0, "brands": 0, "salts": 0}
        
        for g in item_groups:
            try:
                self.frappe.db.sql(
                    "INSERT IGNORE INTO `tabItem Group` (`name`, `item_group_name`, `parent_item_group`, `is_group`) VALUES (%s, %s, %s, 0);",
                    (g, g, "All Item Groups")
                )
                counts["item_groups"] += 1
            except Exception:
                pass
                
        for u in uoms:
            try:
                self.frappe.db.sql(
                    "INSERT IGNORE INTO `tabUOM` (`name`, `uom_name`, `must_be_whole_number`) VALUES (%s, %s, 0);",
                    (u, u)
                )
                counts["uoms"] += 1
            except Exception:
                pass
                
        for m in manufacturers:
            try:
                self.frappe.db.sql(
                    "INSERT IGNORE INTO `tabManufacturer` (`name`, `short_name`) VALUES (%s, %s);",
                    (m, m)
                )
                counts["manufacturers"] += 1
            except Exception:
                pass
                
        for b in brands:
            try:
                self.frappe.db.sql(
                    "INSERT IGNORE INTO `tabBrand` (`name`, `brand`) VALUES (%s, %s);",
                    (b, b)
                )
                counts["brands"] += 1
            except Exception:
                pass
                
        for s in salts:
            try:
                self.frappe.db.sql(
                    "INSERT IGNORE INTO `tabSalt Composition` (`name`, `salt_name`) VALUES (%s, %s);",
                    (s, s)
                )
                counts["salts"] += 1
            except Exception:
                pass
                
        return counts

    def begin_transaction(self) -> None:
        pass  # Frappe transactions are managed via commit/rollback

    def commit_transaction(self) -> None:
        self.frappe.db.commit()

    def rollback_transaction(self) -> None:
        self.frappe.db.rollback()

    def insert_items_batch(self, items: List[Dict[str, Any]]) -> int:
        for it in items:
            query = """
                INSERT INTO `tabItem` (
                    `name`, `item_code`, `item_name`, `item_group`, `stock_uom`,
                    `brand`, `description`, `standard_rate`, `valuation_rate`
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    `item_name` = VALUES(`item_name`),
                    `item_group` = VALUES(`item_group`),
                    `stock_uom` = VALUES(`stock_uom`),
                    `brand` = VALUES(`brand`),
                    `description` = VALUES(`description`),
                    `standard_rate` = VALUES(`standard_rate`),
                    `valuation_rate` = VALUES(`valuation_rate`);
            """
            self.frappe.db.sql(
                query,
                (
                    it["item_code"],
                    it["item_code"],
                    it["item_name"],
                    it["item_group"],
                    it["stock_uom"],
                    it["brand"],
                    it["description"],
                    it["standard_rate"],
                    it["valuation_rate"]
                )
            )
        return len(items)

    def verify_foreign_keys(self) -> List[str]:
        return []

    def get_stats(self) -> Dict[str, int]:
        stats = {}
        for t in ["tabItem", "tabItem Group", "tabUOM", "tabManufacturer", "tabBrand"]:
            try:
                res = self.frappe.db.sql(f"SELECT COUNT(*) FROM `{t}`;")
                stats[t] = res[0][0] if res else 0
            except Exception:
                stats[t] = 0
        return stats

    def close(self) -> None:
        if getattr(self.frappe, "db", None):
            self.frappe.destroy()


# =====================================================================
# Engine Factory
# =====================================================================

def create_engine(engine_name: str = "auto", site: Optional[str] = "pharmacy.local", db_path: Optional[str] = None) -> BaseDatabaseEngine:
    """
    Factory creating appropriate database engine based on availability or choice.
    """
    engine_name = engine_name.lower()
    
    if engine_name == "frappe":
        return FrappeEngine(site=site or "pharmacy.local")
        
    if engine_name == "sqlite":
        return SQLiteEngine(db_path=db_path or ":memory:")
        
    if engine_name == "mariadb":
        return MariaDBEngine()
        
    # Auto-detection
    if engine_name == "auto":
        # Check if running in live Frappe environment
        try:
            import frappe
            if getattr(frappe, "db", None) and frappe.db.get_list:
                logger.info("Using Native Frappe DB Engine")
                return FrappeEngine(site=site or "pharmacy.local")
        except Exception:
            pass
            
        # Standalone default to high-performance SQLite engine
        logger.info(f"Using Standalone SQLite Engine (path={db_path or ':memory:'})")
        return SQLiteEngine(db_path=db_path or ":memory:")
        
    raise ValueError(f"Unknown engine: {engine_name}. Choose from 'auto', 'frappe', 'sqlite', 'mariadb'.")


# =====================================================================
# High-Performance Streaming Reader & Data Transformer
# =====================================================================

def stream_csv_chunks(file_path: str, chunk_size: int = 1000) -> Generator[List[Dict[str, str]], None, None]:
    """
    Streams CSV file in transactional chunks of specified size.
    Never loads the entire file into memory; footprint remains O(chunk_size).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")
        
    with open(file_path, mode="r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        chunk = []
        for row in reader:
            chunk.append(row)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def normalize_uom(packaging_str: str) -> str:
    """
    Extracts or normalizes a standard UOM from Packaging_Size string.
    e.g. 'Strip of 10 Tablets' -> 'Strip', '100 ml Bottle' -> 'Bottle', '10 Capsules' -> 'Strip'
    """
    p = packaging_str.strip().lower()
    if "strip" in p:
        return "Strip"
    elif "bottle" in p or "syrup" in p or "suspension" in p or "ml" in p:
        return "Bottle"
    elif "tube" in p or "gel" in p or "ointment" in p:
        return "Tube"
    elif "vial" in p:
        return "Vial"
    elif "ampoule" in p:
        return "Ampoule"
    elif "inhaler" in p or "mdi" in p or "rotacap" in p:
        return "Inhaler"
    elif "sachet" in p or "powder" in p:
        return "Sachet"
    elif "box" in p:
        return "Box"
    elif "tablet" in p or "tab" in p:
        return "Tab"
    elif "capsule" in p or "cap" in p:
        return "Cap"
    return "Nos"


def parse_mrp(mrp_str: Any) -> float:
    """Safely extracts floating point rate from string (handling ₹, commas, etc.)."""
    if mrp_str is None:
        return 0.0
    cleaned = str(mrp_str).replace("₹", "").replace("Rs.", "").replace(",", "").strip()
    try:
        val = float(cleaned)
        return max(0.0, round(val, 2))
    except ValueError:
        return 0.0


def map_row_to_item(row: Dict[str, str], default_item_group: str = "Pharmaceuticals") -> Dict[str, Any]:
    """
    Maps CSV row adhering to standard Indian pharma master schema to ERP item record:
    [Brand Name, Manufacturer, Composition, HSN, Packaging_Size, MRP]
    """
    # Key normalization
    normalized = {k.strip().lower(): v.strip() for k, v in row.items() if k}
    
    brand_name = (
        normalized.get("brand name") or
        normalized.get("brand_name") or
        normalized.get("item_name") or
        normalized.get("brand") or
        "Unknown Drug"
    )
    
    manufacturer = (
        normalized.get("manufacturer") or
        normalized.get("manufacturer_name") or
        normalized.get("mfg") or
        "General Pharma"
    )
    
    composition = (
        normalized.get("composition") or
        normalized.get("salt_composition") or
        normalized.get("salt") or
        "Standard Formulation"
    )
    
    hsn = (
        normalized.get("hsn") or
        normalized.get("hsn_code") or
        "30049099"
    )
    
    packaging = (
        normalized.get("packaging_size") or
        normalized.get("packaging") or
        normalized.get("pack_size") or
        "10 Tablets"
    )
    
    mrp_raw = (
        normalized.get("mrp") or
        normalized.get("rate") or
        normalized.get("standard_rate") or
        "0.0"
    )
    mrp = parse_mrp(mrp_raw)
    stock_uom = normalize_uom(packaging)
    
    return {
        "item_code": brand_name,
        "item_name": brand_name,
        "item_group": default_item_group,
        "stock_uom": stock_uom,
        "manufacturer": manufacturer,
        "brand": manufacturer,
        "salt_composition": composition,
        "hsn_code": hsn,
        "standard_rate": mrp,
        "valuation_rate": mrp,
        "description": f"Pack: {packaging} | Composition: {composition} | HSN: {hsn}"
    }


# =====================================================================
# Core Importer Pipeline
# =====================================================================

class PharmaImporter:
    """
    Streaming transactional bulk importer for 250,000+ pharmaceutical records.
    Features:
    - O(chunk_size) streaming memory usage
    - 1,000-row transactional isolation blocks
    - In-memory master caching to avoid redundant queries
    - On-the-fly missing master creation (Item Group, UOM, Manufacturer, Brand, Salt Composition)
    - Full telemetry and error accounting
    """

    def __init__(
        self,
        engine: BaseDatabaseEngine,
        chunk_size: int = 1000,
        default_item_group: str = "Pharmaceuticals"
    ):
        self.engine = engine
        self.chunk_size = chunk_size
        self.default_item_group = default_item_group
        
        # Initialize schema and pre-populate in-memory master caches
        self.engine.initialize_schema()
        self.caches = self.engine.load_master_caches()
        
        # Ensure default item group is cached & created
        if self.default_item_group not in self.caches["item_groups"]:
            self.engine.create_missing_masters(
                item_groups={self.default_item_group},
                uoms=set(),
                manufacturers=set(),
                brands=set(),
                salts=set()
            )
            self.caches["item_groups"].add(self.default_item_group)

    def import_file(self, file_path: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Main entry point for streaming CSV ingestion.
        
        Returns:
            Dictionary containing benchmark telemetry and ingestion statistics.
        """
        start_time = time.time()
        total_records = 0
        total_chunks = 0
        total_inserted = 0
        failed_chunks = 0
        total_masters_created = 0
        
        if verbose:
            logger.info(f"Starting chunked ingestion from '{file_path}' (chunk_size={self.chunk_size})")

        for chunk_idx, raw_chunk in enumerate(stream_csv_chunks(file_path, chunk_size=self.chunk_size), start=1):
            chunk_start = time.time()
            chunk_len = len(raw_chunk)
            total_records += chunk_len
            total_chunks += 1
            
            # 1. Transform raw rows
            transformed_items = [map_row_to_item(r, self.default_item_group) for r in raw_chunk]
            
            # 2. Identify missing dependency masters in this chunk
            missing_uoms = set()
            missing_mfgs = set()
            missing_brands = set()
            missing_salts = set()
            
            for it in transformed_items:
                if it["stock_uom"] not in self.caches["uoms"]:
                    missing_uoms.add(it["stock_uom"])
                if it["manufacturer"] not in self.caches["manufacturers"]:
                    missing_mfgs.add(it["manufacturer"])
                if it["brand"] not in self.caches["brands"]:
                    missing_brands.add(it["brand"])
                if it["salt_composition"] not in self.caches["salts"]:
                    missing_salts.add(it["salt_composition"])

            # 3. Auto-create missing masters if any
            if missing_uoms or missing_mfgs or missing_brands or missing_salts:
                created = self.engine.create_missing_masters(
                    item_groups=set(),
                    uoms=missing_uoms,
                    manufacturers=missing_mfgs,
                    brands=missing_brands,
                    salts=missing_salts
                )
                total_masters_created += sum(created.values())
                
                # Update in-memory sets immediately
                self.caches["uoms"].update(missing_uoms)
                self.caches["manufacturers"].update(missing_mfgs)
                self.caches["brands"].update(missing_brands)
                self.caches["salts"].update(missing_salts)

            # 4. Transactional Item Batch Insertion
            try:
                self.engine.begin_transaction()
                inserted = self.engine.insert_items_batch(transformed_items)
                self.engine.commit_transaction()
                total_inserted += inserted
                
                # Update item cache
                for it in transformed_items:
                    self.caches["items"].add(it["item_code"])
                    
            except Exception as e:
                self.engine.rollback_transaction()
                failed_chunks += 1
                logger.error(f"Chunk #{chunk_idx} failed during transactional commit: {e}")
                continue

            chunk_elapsed = time.time() - chunk_start
            chunk_rate = chunk_len / chunk_elapsed if chunk_elapsed > 0 else 0
            
            if verbose and (chunk_idx % 10 == 0 or chunk_len < self.chunk_size):
                overall_elapsed = time.time() - start_time
                overall_rate = total_records / overall_elapsed if overall_elapsed > 0 else 0
                logger.info(
                    f"Chunk #{chunk_idx}: {chunk_len} records in {chunk_elapsed:.3f}s ({chunk_rate:,.0f} rec/s) | "
                    f"Total: {total_records:,} ({overall_rate:,.0f} rec/s)"
                )

        total_elapsed = time.time() - start_time
        avg_throughput = total_records / total_elapsed if total_elapsed > 0 else 0
        
        # Verify foreign keys
        fk_violations = self.engine.verify_foreign_keys()
        
        summary = {
            "total_records": total_records,
            "total_chunks": total_chunks,
            "total_inserted": total_inserted,
            "failed_chunks": failed_chunks,
            "total_masters_created": total_masters_created,
            "elapsed_seconds": round(total_elapsed, 3),
            "throughput_records_per_sec": round(avg_throughput, 1),
            "foreign_key_violations": fk_violations,
            "db_stats": self.engine.get_stats()
        }
        
        if verbose:
            logger.info("=" * 60)
            logger.info("INGESTION PIPELINE COMPLETED")
            logger.info(f"Records Ingested : {total_inserted:,} / {total_records:,}")
            logger.info(f"Chunks Processed : {total_chunks:,} (Failed: {failed_chunks})")
            logger.info(f"Masters Created  : {total_masters_created:,}")
            logger.info(f"Total Time       : {total_elapsed:.2f} seconds")
            logger.info(f"Throughput       : {avg_throughput:,.1f} records/second")
            logger.info(f"FK Violations    : {len(fk_violations)}")
            logger.info("=" * 60)
            
        return summary


def ingest_csv_pipeline(
    file_path: str,
    engine: Optional[BaseDatabaseEngine] = None,
    chunk_size: int = 1000,
    default_item_group: str = "Pharmaceuticals",
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Convenience functional streaming pipeline for CSV ingestion and QA benchmarking.
    """
    if engine is None:
        engine = SQLiteEngine(db_path=":memory:")
    
    importer = PharmaImporter(engine=engine, chunk_size=chunk_size, default_item_group=default_item_group)
    res = importer.import_file(file_path=file_path, verbose=verbose)
    
    db_stats = res.get("db_stats", {})
    masters_created = {
        "item_groups": db_stats.get("tabItem Group", 0),
        "uoms": db_stats.get("tabUOM", 0),
        "manufacturers": db_stats.get("tabManufacturer", 0),
        "brands": db_stats.get("tabBrand", 0),
        "salts": db_stats.get("tabSalt Composition", 0)
    }
    
    return {
        "total_records": res.get("total_records", 0),
        "total_chunks": res.get("total_chunks", 0),
        "chunks_processed": res.get("total_chunks", 0),
        "total_inserted": res.get("total_inserted", 0),
        "failed_chunks": res.get("failed_chunks", 0),
        "failed_records": res.get("failed_chunks", 0),
        "total_masters_created": res.get("total_masters_created", 0),
        "masters_created": masters_created,
        "elapsed_seconds": res.get("elapsed_seconds", 0.0),
        "throughput_records_per_sec": res.get("throughput_records_per_sec", 0.0),
        "foreign_key_violations": res.get("foreign_key_violations", []),
        "db_stats": db_stats
    }


# =====================================================================
# Automated Benchmark & Self-Test Function
# =====================================================================

def run_benchmark(num_records: int = 10000, chunk_size: int = 1000, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Automated self-test and throughput benchmark.
    Generates a realistic mock dataset, ingests through PharmaImporter with strict FK validation,
    and asserts zero integrity errors.
    """
    import tempfile
    from pharma_retail.utils.generate_mock_pharma_dataset import generate_pharma_dataset
    
    print("\n" + "=" * 65)
    print(f"🚀 PHARMA RETAIL INGESTION BENCHMARK: {num_records:,} RECORDS")
    print("=" * 65)
    
    # Create temporary CSV file
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp_csv:
        csv_path = tmp_csv.name
        
    try:
        # 1. Generate realistic dataset
        print(f"[*] Step 1: Generating {num_records:,} authentic Indian pharma records...")
        gen_start = time.time()
        generate_pharma_dataset(csv_path, row_count=num_records, chunk_size=5000, quiet=True)
        gen_time = time.time() - gen_start
        file_size_mb = os.path.getsize(csv_path) / (1024 * 1024)
        print(f"    ✓ Dataset generated in {gen_time:.2f}s ({file_size_mb:.2f} MB)")
        
        # 2. Initialize database engine with strict foreign key constraints
        print(f"[*] Step 2: Initializing SQLite engine with PRAGMA foreign_keys = ON...")
        engine = SQLiteEngine(db_path=db_path or ":memory:")
        importer = PharmaImporter(engine, chunk_size=chunk_size)
        
        # 3. Stream and ingest
        print(f"[*] Step 3: Executing streaming ingestion (chunk_size={chunk_size})...")
        import_start = time.time()
        results = importer.import_file(csv_path, verbose=False)
        import_time = time.time() - import_start
        
        # 4. Relational integrity assertions
        print(f"[*] Step 4: Verifying foreign key and relational integrity...")
        fk_errors = results["foreign_key_violations"]
        assert len(fk_errors) == 0, f"Foreign key errors detected: {fk_errors}"
        assert results["total_inserted"] == num_records, f"Mismatch in inserted records: {results['total_inserted']} != {num_records}"
        assert results["failed_chunks"] == 0, f"Failed chunks encountered: {results['failed_chunks']}"
        print("    ✓ PRAGMA foreign_key_check: 0 violations found. Strict FK integrity verified.")
        
        # 5. Throughput reporting
        throughput = num_records / import_time if import_time > 0 else 0
        stats = results["db_stats"]
        
        print("\n" + "-" * 65)
        print("📊 BENCHMARK PERFORMANCE RESULTS")
        print("-" * 65)
        print(f"  • Total Records Ingested   : {results['total_inserted']:,}")
        print(f"  • Batch Chunk Size         : {chunk_size:,} rows")
        print(f"  • Total Elapsed Time       : {import_time:.3f} seconds")
        print(f"  • Ingestion Throughput     : {throughput:,.1f} records/second")
        print(f"  • Item Group Masters       : {stats.get('tabItem Group', 0)}")
        print(f"  • UOM Masters              : {stats.get('tabUOM', 0)}")
        print(f"  • Manufacturer Masters     : {stats.get('tabManufacturer', 0)}")
        print(f"  • Brand Masters            : {stats.get('tabBrand', 0)}")
        print(f"  • Salt Composition Masters : {stats.get('tabSalt Composition', 0)}")
        print(f"  • Foreign Key Violations   : 0 (PASSED)")
        print("-" * 65 + "\n")
        
        engine.close()
        return results
        
    finally:
        if os.path.exists(csv_path):
            os.remove(csv_path)


# =====================================================================
# CLI Entry Point
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="High-Performance Chunked Streaming Importer for Indian Pharma Records"
    )
    parser.add_argument("--file", "-f", type=str, help="Path to medicine master CSV file")
    parser.add_argument("--chunk-size", "-c", type=int, default=1000, help="Batch transaction chunk size (default: 1000)")
    parser.add_argument("--engine", "-e", type=str, default="auto", choices=["auto", "frappe", "sqlite", "mariadb"], help="Database engine backend")
    parser.add_argument("--db-path", type=str, default=":memory:", help="SQLite database path (default: :memory:)")
    parser.add_argument("--site", type=str, default="pharmacy.local", help="Frappe site name (default: pharmacy.local)")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Run automated self-test & benchmark")
    parser.add_argument("--benchmark-records", type=int, default=10000, help="Record count for benchmark (default: 10,000)")
    
    args = parser.parse_args()
    
    if args.benchmark:
        run_benchmark(num_records=args.benchmark_records, chunk_size=args.chunk_size, db_path=args.db_path)
        return
        
    if not args.file:
        parser.print_help()
        print("\nError: --file argument is required when not running --benchmark")
        sys.exit(1)
        
    engine = create_engine(engine_name=args.engine, site=args.site, db_path=args.db_path)
    try:
        importer = PharmaImporter(engine, chunk_size=args.chunk_size)
        importer.import_file(args.file, verbose=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
