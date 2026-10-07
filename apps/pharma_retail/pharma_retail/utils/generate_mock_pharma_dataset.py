"""
High-Performance Mock Indian Pharmaceutical Dataset Generator
Generates realistic Indian medicine master CSV datasets adhering to:
Columns: [Brand Name, Manufacturer, Composition, HSN, Packaging_Size, MRP]
Supports streaming generation for 1,000 to 250,000+ records with constant memory footprint.
"""

import os
import sys
import csv
import random
import argparse
import time

# Curated list of authentic Indian pharmaceutical brand bases
INDIAN_BRAND_SEEDS = [
    ("Crocin", "Paracetamol", [("500 mg", 24.50), ("650 mg", 33.75), ("Advance", 28.00), ("Pain Relief", 68.00)]),
    ("Dolo", "Paracetamol", [("650 mg", 34.00), ("500 mg", 22.50), ("Cold", 54.00)]),
    ("Calpol", "Paracetamol", [("500 mg", 21.00), ("650 mg", 32.50), ("250 mg Paediatric Suspension", 45.00)]),
    ("Telma", "Telmisartan", [("20 mg", 95.00), ("40 mg", 152.00), ("80 mg", 260.00), ("AM 40/5", 210.00), ("CT 40/12.5", 240.00), ("ACT", 310.00)]),
    ("Glycomet", "Metformin Hydrochloride", [("500 mg SR", 28.50), ("850 mg", 44.00), ("1000 mg SR", 62.00), ("GP 1", 115.00), ("GP 2", 158.00), ("Trio 2", 235.00)]),
    ("Augmentin", "Amoxicillin and Potassium Clavulanate", [("625 Duo", 224.00), ("375 mg", 154.00), ("1000 mg", 360.00), ("DDS Syrup", 145.00)]),
    ("Clavam", "Amoxicillin and Potassium Clavulanate", [("625 mg", 218.00), ("375 mg", 148.00), ("Bid Dry Syrup", 138.00)]),
    ("Pan", "Pantoprazole", [("40 mg", 108.00), ("20 mg", 68.00), ("-D SR", 185.00), ("-DSR Max", 220.00), ("-L", 245.00)]),
    ("Pantocid", "Pantoprazole", [("40 mg", 112.00), ("20 mg", 72.00), ("-DSR", 192.00), ("-IT", 215.00)]),
    ("Azithral", "Azithromycin", [("500 mg", 132.00), ("250 mg", 78.00), ("Stat 100", 95.00), ("XL 200 Suspension", 140.00)]),
    ("Azee", "Azithromycin", [("500 mg", 128.00), ("250 mg", 75.00), ("1000 mg", 230.00), ("Dry Syrup", 120.00)]),
    ("Lipitor", "Atorvastatin Calcium", [("10 mg", 180.00), ("20 mg", 320.00), ("40 mg", 540.00)]),
    ("Atorva", "Atorvastatin Calcium", [("10 mg", 110.00), ("20 mg", 198.00), ("40 mg", 345.00), ("TG 10", 215.00)]),
    ("Shelcal", "Calcium and Vitamin D3", [("500 mg", 138.00), ("250 mg", 85.00), ("HD", 195.00), ("XT", 245.00), ("Joint", 390.00)]),
    ("Foracort", "Budesonide and Formoterol Fumarate", [("200 Inhaler", 420.00), ("400 Inhaler", 580.00), ("100 Rotacaps", 185.00), ("200 Rotacaps", 245.00)]),
    ("Allegra", "Fexofenadine Hydrochloride", [("120 mg", 215.00), ("180 mg", 265.00), ("M", 280.00), ("Suspension", 160.00)]),
    ("Montair", "Montelukast", [("10 mg", 185.00), ("LC", 235.00), ("FX", 290.00), ("4 mg Kid", 95.00)]),
    ("Becosules", "B-Complex with Vitamin C", [("Capsules", 55.00), ("Performance", 165.00), ("Z", 62.00)]),
    ("Neurobion", "Mecobalamin and Pyridoxine", [("Forte", 42.50), ("Plus", 135.00), ("Injection 2ml", 28.00)]),
    ("Liv 52", "Herbal Liver Care Formulation", [("Tablets 100s", 160.00), ("DS Tablets 60s", 185.00), ("Syrup 200ml", 175.00)]),
    ("Thyronorm", "Thyroxine Sodium", [("25 mcg", 145.00), ("50 mcg", 162.00), ("75 mcg", 178.00), ("100 mcg", 192.00), ("125 mcg", 205.00)]),
    ("Asthalin", "Salbutamol Sulphate", [("100 mcg Inhaler", 165.00), ("4 mg Tablet", 12.00), ("2 mg Tablet", 9.50), ("Respules 2.5ml", 45.00)]),
    ("Combiflam", "Ibuprofen and Paracetamol", [("Tablet", 48.00), ("Plus", 52.00), ("Suspension 100ml", 45.00), ("Icy Hot Gel", 115.00)]),
    ("Zerodol", "Aceclofenac", [("-P", 75.00), ("-SP", 125.00), ("-TH 4", 235.00), ("-CR 200", 110.00)]),
    ("Rantac", "Ranitidine Hydrochloride", [("150 mg", 42.00), ("300 mg", 80.00), ("Injection 2ml", 12.50)]),
    ("Monocef", "Ceftriaxone Sodium", [("1g Injection", 72.00), ("500mg Injection", 55.00), ("2g Injection", 145.00), ("-O 200", 195.00)]),
    ("Oflox", "Ofloxacin", [("200 mg", 88.00), ("-OZ", 145.00), ("Eye Drops 5ml", 58.00)]),
    ("Betadine", "Povidone Iodine", [("10% Solution 100ml", 145.00), ("5% Ointment 20g", 78.00), ("Gargle 2% 100ml", 190.00)]),
    ("Volini", "Diclofenac Diethylamine", [("Gel 30g", 125.00), ("Spray 55g", 195.00), ("Maxx Gel 50g", 210.00)]),
    ("Meftal-Spas", "Mefenamic Acid and Dicyclomine", [("Tablet", 54.00), ("Suspension 60ml", 58.00), ("Drops 10ml", 45.00)]),
    ("Sinarest", "Paracetamol, Phenylephrine, Chlorpheniramine", [("Tablet", 68.00), ("New Syrup 60ml", 82.00), ("AF Drops 15ml", 72.00)]),
    ("Ascoril", "Terbutaline, Bromhexine, Guaiphenesin", [("+ Expectorant 100ml", 128.00), ("-D Plus 100ml", 138.00), ("-LS 100ml", 132.00)]),
    ("Benadryl", "Diphenhydramine, Ammonium Chloride", [("Cough Formula 100ml", 120.00), ("DR Syrup 100ml", 135.00)]),
    ("Zincovit", "Multivitamins, Multiminerals with Zinc", [("Tablets 15s", 118.00), ("Syrup 200ml", 155.00), ("Drops 15ml", 68.00)]),
    ("Electral", "Oral Rehydration Salts WHO Formula", [("Powder 21.8g Sachet", 24.50), ("Orange Ready Drink 200ml", 42.00)]),
    ("Cifran", "Ciprofloxacin", [("500 mg", 55.00), ("250 mg", 32.00), ("-CT", 120.00), ("Eye Drops", 28.00)]),
    ("Omnacortil", "Prednisolone", [("5 mg", 15.00), ("10 mg", 28.00), ("20 mg", 48.00), ("40 mg", 88.00)]),
    ("Taxim-O", "Cefixime", [("200 mg", 125.00), ("100 mg DT", 85.00), ("-CV", 245.00), ("Dry Syrup", 98.00)]),
    ("Stamlo", "Amlodipine Besylate", [("5 mg", 82.00), ("2.5 mg", 52.00), ("-Beta", 145.00), ("-T", 168.00)]),
    ("Ecosprin", "Aspirin (Acetylsalicylic Acid)", [("75 mg", 6.50), ("150 mg", 11.20), ("AV 75/20", 85.00)]),
    ("Crestor", "Rosuvastatin Calcium", [("10 mg", 295.00), ("20 mg", 540.00), ("5 mg", 165.00)]),
    ("Rosuvas", "Rosuvastatin Calcium", [("10 mg", 195.00), ("20 mg", 365.00), ("F 10", 280.00)]),
    ("Rozavel", "Rosuvastatin Calcium", [("10 mg", 185.00), ("20 mg", 350.00), ("5 mg", 110.00)]),
    ("Januvia", "Sitagliptin Phosphate", [("50 mg", 980.00), ("100 mg", 1450.00)]),
    ("Janumet", "Sitagliptin and Metformin", [("50/500 mg", 1120.00), ("50/1000 mg", 1280.00)]),
    ("Galvus", "Vildagliptin", [("50 mg", 420.00), ("Met 50/500", 490.00), ("Met 50/1000", 540.00)]),
    ("Jardiance", "Empagliflozin", [("10 mg", 780.00), ("25 mg", 980.00)]),
    ("Forxiga", "Dapagliflozin", [("10 mg", 740.00), ("5 mg", 490.00)]),
    ("Duloflex", "Duloxetine", [("20 mg", 145.00), ("30 mg", 210.00), ("60 mg", 380.00)]),
    ("Nexito", "Escitalopram Oxalate", [("10 mg", 135.00), ("5 mg", 85.00), ("Plus", 175.00), ("Forte", 225.00)]),
    ("Duphaston", "Dydrogesterone", [("10 mg", 825.00)]),
    ("Susten", "Natural Micronised Progesterone", [("200 mg Softgel", 445.00), ("300 mg SR", 620.00), ("100 mg Inj", 195.00)]),
    ("Clexane", "Enoxaparin Sodium", [("40 mg Pre-filled Syringe", 610.00), ("60 mg Pre-filled Syringe", 890.00)]),
]

# Authentic Indian Pharmaceutical Manufacturers
INDIAN_MANUFACTURERS = [
    "Sun Pharmaceutical Industries Ltd",
    "Cipla Ltd",
    "Abbott Healthcare Pvt Ltd",
    "Dr. Reddy's Laboratories Ltd",
    "Mankind Pharma Ltd",
    "Torrent Pharmaceuticals Ltd",
    "Lupin Ltd",
    "Zydus Lifesciences Ltd",
    "Alkem Laboratories Ltd",
    "Intas Pharmaceuticals Ltd",
    "Glenmark Pharmaceuticals Ltd",
    "Macleods Pharmaceuticals Pvt Ltd",
    "Aristo Pharmaceuticals Pvt Ltd",
    "Emcure Pharmaceuticals Ltd",
    "Micro Labs Ltd",
    "USV Pvt Ltd",
    "FDC Ltd",
    "Hetero Healthcare Ltd",
    "J.B. Chemicals & Pharmaceuticals Ltd",
    "Sanofi India Ltd",
    "GlaxoSmithKline Pharmaceuticals Ltd",
    "Pfizer Ltd",
]

# Standard HSN codes for Pharmaceutical Products (Chapter 3004)
INDIAN_PHARMA_HSN = [
    "30049099",  # Other medicaments consisting of mixed or unmixed products for retail sale
    "30049011",  # Ayurvedic, homeopathic or unani systems
    "30049039",  # Other antibacterial formulations
    "30042099",  # Other containing antibiotics
    "30045020",  # Vitamin formulations
    "30041010",  # Containing penicillins or derivatives
    "30043919",  # Pituitary hormone formulations
    "30049071",  # Antihistaminic formulations
    "30049089",  # Antineoplastic or immunosuppressive
    "30049060",  # Antiprotozoal drugs
]

# Standard Packaging formats in Indian Pharma Retail
PACKAGING_FORMATS = [
    ("Strip of 10 Tablets", "Strip"),
    ("Strip of 15 Tablets", "Strip"),
    ("Strip of 10 Capsules", "Strip"),
    ("Strip of 15 Capsules", "Strip"),
    ("100 ml Bottle", "Bottle"),
    ("60 ml Bottle", "Bottle"),
    ("200 ml Bottle", "Bottle"),
    ("30g Tube", "Tube"),
    ("50g Tube", "Tube"),
    ("1 Vial (10 ml)", "Vial"),
    ("1 Ampoule (2 ml)", "Ampoule"),
    ("1 Inhaler (120 MDI)", "Inhaler"),
    ("Box of 10 Strips", "Box"),
    ("Sachet of 21.8g", "Sachet"),
    ("Box of 30 Tablets", "Box"),
    ("Bottle of 60 Tablets", "Bottle"),
]

# Common pharmaceutical salt prefixes / suffixes for scalable generation
SALT_ACTIVE_AGENTS = [
    "Paracetamol", "Telmisartan", "Metformin Hydrochloride", "Amoxicillin", "Clavulanic Acid",
    "Pantoprazole", "Domperidone", "Azithromycin", "Atorvastatin Calcium", "Calcium Carbonate",
    "Vitamin D3", "Budesonide", "Formoterol Fumarate", "Fexofenadine HCl", "Montelukast Sodium",
    "Levocetirizine", "Mecobalamin", "Thyroxine Sodium", "Salbutamol Sulphate", "Aceclofenac",
    "Serratiopeptidase", "Ranitidine HCl", "Ceftriaxone Sodium", "Ofloxacin", "Ornidazole",
    "Povidone Iodine", "Diclofenac Sodium", "Dydrogesterone", "Cefixime Trihydrate", "Amlodipine Besylate",
    "Rosuvastatin Calcium", "Sitagliptin Phosphate", "Vildagliptin", "Empagliflozin", "Dapagliflozin",
    "Escitalopram Oxalate", "Pregabalin", "Gabapentin", "Cilnidipine", "Chlorthalidone",
    "Levofloxacin", "Linezolid", "Clopidogrel", "Rosuvastatin", "Spironolactone", "Torsemide"
]

SALT_DOSAGES = [
    "5 mg", "10 mg", "20 mg", "25 mg", "40 mg", "50 mg", "100 mg", "200 mg", "250 mg",
    "500 mg", "650 mg", "1000 mg", "1500 mcg", "100 mcg", "200 mcg", "500 IU", "60000 IU"
]


def generate_single_record(index: int) -> dict:
    """
    Generates an authentic Indian pharma master record.
    Uses realistic seeds for lower indices and structured procedural combinations
    for large scale datasets up to 250,000+ records.
    """
    if index < len(INDIAN_BRAND_SEEDS) * 10:
        seed_idx = index % len(INDIAN_BRAND_SEEDS)
        brand_base, salt_base, variants = INDIAN_BRAND_SEEDS[seed_idx]
        variant_idx = (index // len(INDIAN_BRAND_SEEDS)) % len(variants)
        variant_name, base_mrp = variants[variant_idx]
        
        # Pick realistic packaging
        pack_desc, pack_uom = random.choice(PACKAGING_FORMATS)
        mfg = INDIAN_MANUFACTURERS[seed_idx % len(INDIAN_MANUFACTURERS)]
        hsn = INDIAN_PHARMA_HSN[seed_idx % len(INDIAN_PHARMA_HSN)]
        
        brand_full_name = f"{brand_base} {variant_name}".strip()
        composition = f"{salt_base} {variant_name.split()[0]}".strip() if any(char.isdigit() for char in variant_name) else f"{salt_base} Standard Formulation"
        
        # Adjust MRP slightly with packaging
        mrp = round(base_mrp * (1.0 + (index % 5) * 0.05), 2)
    else:
        # Procedural generation for scalable volume (250,000+ items)
        brand_seed = INDIAN_BRAND_SEEDS[index % len(INDIAN_BRAND_SEEDS)]
        base_name = brand_seed[0]
        active_salt = SALT_ACTIVE_AGENTS[index % len(SALT_ACTIVE_AGENTS)]
        dosage = SALT_DOSAGES[(index // len(SALT_ACTIVE_AGENTS)) % len(SALT_DOSAGES)]
        
        # Distinct batch or SKU identifier for high-volume medicine masters
        sku_suffix = f"SKU-{index:06d}"
        brand_full_name = f"{base_name} {dosage} {sku_suffix}"
        
        # Secondary salt combination in 30% cases
        if index % 3 == 0:
            secondary_salt = SALT_ACTIVE_AGENTS[(index + 7) % len(SALT_ACTIVE_AGENTS)]
            composition = f"{active_salt} {dosage} + {secondary_salt} 5 mg"
        else:
            composition = f"{active_salt} {dosage}"
            
        mfg = INDIAN_MANUFACTURERS[(index // 10) % len(INDIAN_MANUFACTURERS)]
        hsn = INDIAN_PHARMA_HSN[(index // 7) % len(INDIAN_PHARMA_HSN)]
        pack_desc, pack_uom = PACKAGING_FORMATS[index % len(PACKAGING_FORMATS)]
        
        base_rate = 25.0 + ((index * 37) % 750)
        mrp = round(base_rate + ((index % 100) * 0.25), 2)
        
    return {
        "Brand Name": brand_full_name,
        "Manufacturer": mfg,
        "Composition": composition,
        "HSN": hsn,
        "Packaging_Size": pack_desc,
        "MRP": f"{mrp:.2f}"
    }


def generate_pharma_dataset(output_path: str, row_count: int = 10000, chunk_size: int = 5000, quiet: bool = False) -> str:
    """
    Streams a mock Indian pharma master dataset directly to disk in CSV format.
    Maintains constant O(1) memory usage regardless of row count.
    
    Args:
        output_path: Absolute or relative path to target CSV file.
        row_count: Number of records to generate (e.g. 1,000, 10,000, 250,000).
        chunk_size: Disk flush buffer size.
        quiet: Suppress stdout progress logs.
        
    Returns:
        Absolute path to the created CSV file.
    """
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    fieldnames = ["Brand Name", "Manufacturer", "Composition", "HSN", "Packaging_Size", "MRP"]
    
    start_time = time.time()
    if not quiet:
        print(f"[*] Starting dataset generation: {row_count:,} rows to {output_path}...")
    
    with open(output_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        buffer = []
        for i in range(1, row_count + 1):
            buffer.append(generate_single_record(i))
            
            if len(buffer) >= chunk_size:
                writer.writerows(buffer)
                buffer.clear()
                if not quiet and (i % 25000 == 0 or i == row_count):
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    print(f"    -> Generated {i:,}/{row_count:,} records ({rate:,.0f} rows/sec)")
                    
        if buffer:
            writer.writerows(buffer)
            buffer.clear()
            
    total_time = time.time() - start_time
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    if not quiet:
        rate = row_count / total_time if total_time > 0 else 0
        print(f"[+] Dataset complete: {row_count:,} records | Size: {file_size_mb:.2f} MB | Time: {total_time:.2f}s | Speed: {rate:,.0f} rows/s")
        
    return output_path


def generate_mock_csv(output_path: str, num_records: int = 10000, chunk_size: int = 5000, quiet: bool = True) -> str:
    """
    Convenience alias for generate_pharma_dataset supporting num_records argument.
    """
    return generate_pharma_dataset(output_path=output_path, row_count=num_records, chunk_size=chunk_size, quiet=quiet)


def main():
    parser = argparse.ArgumentParser(description="Generate Realistic Indian Pharma Master Dataset CSV")
    parser.add_argument("--count", "-n", type=int, default=10000, help="Number of pharmaceutical records (default: 10,000)")
    parser.add_argument("--output", "-o", type=str, default="pharma_master_records.csv", help="Target CSV file path")
    parser.add_argument("--chunk-size", "-c", type=int, default=5000, help="Buffer chunk size (default: 5,000)")
    args = parser.parse_args()
    
    generate_pharma_dataset(args.output, args.count, args.chunk_size)


if __name__ == "__main__":
    main()
