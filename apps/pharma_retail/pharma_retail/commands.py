"""
Frappe Bench CLI Commands for Pharma Retail
Provides high-performance streaming seeding for Indian medicine datasets.
"""

import os
import sys
import time
import inspect
import click


def get_seeder_function():
    """Dynamically resolves stream_seed_medicines from medicine_seeder or db_seeder."""
    try:
        from pharma_retail.utils.medicine_seeder import stream_seed_medicines
        return stream_seed_medicines
    except ImportError:
        pass

    try:
        from pharma_retail.utils.db_seeder import stream_seed_medicines
        return stream_seed_medicines
    except ImportError:
        pass

    # Graceful fallback to importer pipeline if medicine_seeder is not yet imported
    try:
        from pharma_retail.utils.importer import ingest_csv_pipeline
        def fallback_seeder(url=None, file_path=None, file=None, chunk_size=2000, limit=None, site=None):
            path = file or file_path
            if not path:
                from pharma_retail.utils.generate_mock_pharma_dataset import generate_pharma_dataset
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
                    path = tf.name
                generate_pharma_dataset(path, row_count=limit or 1000, quiet=True)
            return ingest_csv_pipeline(path, chunk_size=chunk_size, verbose=True)
        return fallback_seeder
    except Exception:
        raise ImportError("Could not import stream_seed_medicines from pharma_retail.utils.medicine_seeder")


def _execute_seeding(url=None, file=None, chunk_size=2000, limit=None, site=None):
    """Core execution logic shared between seed-pharma-db and seed_pharma_db."""
    start_time = time.time()

    # Resolve target site from context or environment
    if not site:
        ctx = click.get_current_context(silent=True)
        if ctx and getattr(ctx, "obj", None):
            if isinstance(ctx.obj, dict) and ctx.obj.get("sites"):
                site = ctx.obj["sites"][0]
            elif hasattr(ctx.obj, "get") and ctx.obj.get("sites"):
                site = ctx.obj.get("sites")[0]

    if not site:
        site = os.environ.get("FRAPPE_SITE") or "pharmacy.local"

    chunk_size = chunk_size or 2000

    click.echo("=" * 65)
    click.echo("🚀 PHARMA RETAIL: STREAMING MEDICINE DATABASE SEEDER")
    click.echo("=" * 65)
    click.echo(f"  • Target Site : {site}")
    click.echo(f"  • Chunk Size  : {chunk_size:,} records/transaction")
    click.echo(f"  • Limit       : {f'{limit:,}' if limit else 'None (Full Dataset)'}")
    if url:
        click.echo(f"  • Remote URL  : {url}")
    if file:
        click.echo(f"  • Local File  : {file}")
    click.echo("=" * 65 + "\n")

    stream_seed_medicines = get_seeder_function()

    # Inspect function signature for compatibility
    sig = inspect.signature(stream_seed_medicines)
    kwargs = {}
    if "url" in sig.parameters:
        kwargs["url"] = url
    if "chunk_size" in sig.parameters:
        kwargs["chunk_size"] = chunk_size
    if "limit" in sig.parameters:
        kwargs["limit"] = limit
    if "site" in sig.parameters:
        kwargs["site"] = site

    if "file_path" in sig.parameters:
        kwargs["file_path"] = file
    elif "file" in sig.parameters:
        kwargs["file"] = file
    else:
        kwargs["file_path"] = file

    # Execute seeder
    try:
        result = stream_seed_medicines(**kwargs)
    except Exception as e:
        click.secho(f"\n❌ Error during database seeding: {e}", fg="red", err=True)
        raise click.Abort()

    elapsed = time.time() - start_time
    total_inserted = 0
    if isinstance(result, dict):
        total_inserted = result.get("total_inserted") or result.get("total_records") or result.get("inserted", 0)
    elif isinstance(result, int):
        total_inserted = result

    click.echo("\n" + "=" * 65)
    click.secho("✅ SEEDING COMPLETE", fg="green", bold=True)
    if total_inserted:
        throughput = total_inserted / elapsed if elapsed > 0 else 0
        click.echo(f"  • Records Inserted : {total_inserted:,}")
        click.echo(f"  • Time Elapsed     : {elapsed:.2f}s")
        click.echo(f"  • Throughput       : {throughput:,.1f} records/second")
    click.echo("=" * 65)
    return result


@click.command('seed-pharma-db')
@click.option('--url', default=None, help='URL to streaming Indian medicine dataset CSV')
@click.option('--file', default=None, help='Path to local Indian medicine CSV file')
@click.option('--chunk-size', default=2000, type=int, help='Batch transaction chunk size (default: 2000)')
@click.option('--limit', default=None, type=int, help='Limit number of records to import (e.g., 10000 or 250000)')
@click.option('--site', default=None, help='Target Frappe site (defaults to current site or pharmacy.local)')
def seed_pharma_db(url, file, chunk_size, limit, site):
    """Stream download & batch-insert Indian medicine dataset into Frappe ERP."""
    return _execute_seeding(url=url, file=file, chunk_size=chunk_size, limit=limit, site=site)


@click.command('seed_pharma_db')
@click.option('--url', default=None, help='URL to streaming Indian medicine dataset CSV')
@click.option('--file', default=None, help='Path to local Indian medicine CSV file')
@click.option('--chunk-size', default=2000, type=int, help='Batch transaction chunk size (default: 2000)')
@click.option('--limit', default=None, type=int, help='Limit number of records to import (e.g., 10000 or 250000)')
@click.option('--site', default=None, help='Target Frappe site (defaults to current site or pharmacy.local)')
def seed_pharma_db_alias(url, file, chunk_size, limit, site):
    """Alias for seed-pharma-db using underscore notation."""
    return _execute_seeding(url=url, file=file, chunk_size=chunk_size, limit=limit, site=site)


# Exported list of commands for Frappe bench_helper (importlib.import_module(f"{app}.commands"))
commands = [seed_pharma_db, seed_pharma_db_alias]


@click.group()
def cli():
    """Pharma Retail Bench Commands"""
    pass

cli.add_command(seed_pharma_db)
cli.add_command(seed_pharma_db_alias)


if __name__ == "__main__":
    cli()
