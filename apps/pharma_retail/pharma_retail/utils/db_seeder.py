"""
Alias and export module for medicine_seeder.
Provides backwards and alternative import compatibility for db_seeder.
"""

try:
    from pharma_retail.utils.medicine_seeder import (
        DEFAULT_MEDICINE_DATASET_URL,
        FALLBACK_DATASET_URLS,
        DEFAULT_BATCH_SIZE,
        DEFAULT_PROGRESS_INTERVAL,
        DEFAULT_HSN,
        DEFAULT_ITEM_GROUP,
        DEFAULT_UOM,
        clean_text,
        normalize_uom,
        parse_price,
        map_medicine_row,
        stream_simulated_lines,
        stream_lines_from_url,
        stream_lines_from_file,
        stream_csv_records,
        BaseSeederEngine,
        SQLiteEngine,
        FrappeEngine,
        create_engine,
        stream_seed_medicines,
        main,
    )
except ImportError:
    from medicine_seeder import (
        DEFAULT_MEDICINE_DATASET_URL,
        FALLBACK_DATASET_URLS,
        DEFAULT_BATCH_SIZE,
        DEFAULT_PROGRESS_INTERVAL,
        DEFAULT_HSN,
        DEFAULT_ITEM_GROUP,
        DEFAULT_UOM,
        clean_text,
        normalize_uom,
        parse_price,
        map_medicine_row,
        stream_simulated_lines,
        stream_lines_from_url,
        stream_lines_from_file,
        stream_csv_records,
        BaseSeederEngine,
        SQLiteEngine,
        FrappeEngine,
        create_engine,
        stream_seed_medicines,
        main,
    )

__all__ = [
    "DEFAULT_MEDICINE_DATASET_URL",
    "FALLBACK_DATASET_URLS",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_PROGRESS_INTERVAL",
    "DEFAULT_HSN",
    "DEFAULT_ITEM_GROUP",
    "DEFAULT_UOM",
    "clean_text",
    "normalize_uom",
    "parse_price",
    "map_medicine_row",
    "stream_simulated_lines",
    "stream_lines_from_url",
    "stream_lines_from_file",
    "stream_csv_records",
    "BaseSeederEngine",
    "SQLiteEngine",
    "FrappeEngine",
    "create_engine",
    "stream_seed_medicines",
    "main",
]

if __name__ == "__main__":
    main()
