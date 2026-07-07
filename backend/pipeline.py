import os
import logging
from datetime import datetime, timezone
from typing import Tuple
import pandas as pd
from sqlalchemy.orm import Session
from backend.models import RawSale, ProcessedSale

TAX_RATE = float(os.getenv("TAX_RATE","0.18"))
DISCOUNT_RATE = float(os.getenv("DISCOUNT_RATE","0.05"))

logger = logging.getLogger("pipeline")
logger.setLevel(logging.DEBUG)

if not logger.handlers:

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(log_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, "pipeline.log")
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

def load_pending_records(db: Session) -> pd.DataFrame:
    """
    Fetches all raw_sales records with status='pending' from the DB
    and loads them into a pandas DataFrame.
    """
    logger.info("=" * 60)
    logger.info("PIPELINE RUN STARTED")
    logger.info(f"TAX_RATE = {TAX_RATE*100:.1f}")
    logger.info(f"DISCOUNT_RATE = {DISCOUNT_RATE*100:.1f}")
    logger.info("=" * 60)
    logger.info("Loading pending records from database...")

    pending_records = db.query(RawSale).filter(
        RawSale.status == "pending"
    ).all()

    if not pending_records:
        logger.info("No pending records found. Pipeline has nothing to do.")
        return pd.DataFrame()

    records_as_dicts = []
    for record in pending_records:
        records_as_dicts.append({
            "id": record.id,
            "date": record.date,
            "product": record.product,
            "category": record.category,
            "qty": record.qty,
            "price": record.price,
            "uploaded_by": record.uploaded_by,
            "status": record.status,
            "created_at": record.created_at
        })

    df = pd.DataFrame(records_as_dicts)

    logger.info(f"Loaded {len(df)} pending records from DB")
    logger.debug(f"Columns: {list(df.columns)}")

    return df



def check_nulls(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Identifies rows with null/missing values in critical columns.
    """
    logger.info("Checking for null values...")

    CRITICAL_COLUMNS = ["date", "product", "category", "qty", "price"]

    null_mask = df[CRITICAL_COLUMNS].isnull().any(axis=1)
    failed_df = df[null_mask].copy()
    clean_df = df[~null_mask].copy()

    if len(failed_df) > 0:
        def build_null_reason(row):
            null_cols = [col for col in CRITICAL_COLUMNS if pd.isnull(row[col])]
            return f"null_value: [{', '.join(null_cols)}] is null/missing"

        failed_df["fail_reason"] = failed_df.apply(build_null_reason, axis=1)

        logger.warning(f"Found {len(failed_df)} rows with null values:")
        for _, row in failed_df.iterrows():
            logger.warning(f"  Row ID {row['id']}: {row['fail_reason']}")
    else:
        logger.info("No null values found")

    logger.info(f"After null check → clean: {len(clean_df)}, failed: {len(failed_df)}")
    return clean_df, failed_df



def validate_types(
    df: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validates and coerces data types for all required columns.
    """
    logger.info("Validating and coercing data types...")

    if df.empty:
        return df.copy(), pd.DataFrame()

    failed_indices = []
    fail_reasons = {}

    df = df.copy()
    logger.debug("Parsing date column...")
    for idx, val in df["date"].items():

        try:
            if pd.isnull(val):
                raise ValueError("date is null")

            parsed = pd.to_datetime(val)

            df.at[idx, "date"] = parsed

        except Exception as e:
            failed_indices.append(idx)
            fail_reasons[idx] = f"type_error: date='{val}' is not a valid date ({str(e)})"

    logger.debug("Validating qty column...")
    for idx, val in df["qty"].items():
        if idx in failed_indices:
            continue

        try:
            qty_val = int(float(str(val)))

            if qty_val <= 0:
                raise ValueError(f"qty must be positive, got {qty_val}")

            df.at[idx, "qty"] = qty_val

        except Exception as e:
            failed_indices.append(idx)
            fail_reasons[idx] = f"type_error: qty='{val}' is invalid ({str(e)})"

    logger.debug("Validating price column...")
    for idx, val in df["price"].items():
        if idx in failed_indices:
            continue

        try:
            price_val = float(str(val))

            if price_val <= 0:
                raise ValueError(f"price must be positive, got {price_val}")

            df.at[idx, "price"] = price_val

        except Exception as e:
            failed_indices.append(idx)
            fail_reasons[idx] = f"type_error: price='{val}' is invalid ({str(e)})"

    logger.debug("Stripping whitespace from product and category...")
    for col in ["product", "category"]:
        df[col] = df[col].astype(str).str.strip()

    failed_indices = list(set(failed_indices))

    if failed_indices:
        type_failed_df = df.loc[failed_indices].copy()
        type_failed_df["fail_reason"] = [
            fail_reasons.get(idx, "unknown_type_error") for idx in failed_indices
        ]

        clean_df = df.drop(index=failed_indices).copy()

        logger.warning(f"Found {len(type_failed_df)} rows with type errors:")
        for _, row in type_failed_df.iterrows():
            logger.warning(f"Row ID {row['id']}: {row['fail_reason']}")
    else:
        type_failed_df = pd.DataFrame()
        clean_df = df

    logger.info(f"After type check → clean: {len(clean_df)}, failed: {len(type_failed_df)}")
    return clean_df, type_failed_df



def check_duplicates(
    df: pd.DataFrame,
    db: Session
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Detects duplicate records by checking if a combination of
    date + product + qty + price already exists in processed_sales.
    """
    logger.info("Checking for duplicates against processed_sales...")

    if df.empty:
        return df.copy(), pd.DataFrame()

    existing_processed = db.query(ProcessedSale).all()

    if not existing_processed:
        logger.info("No existing processed records — no duplicates possible")
        return df.copy(), pd.DataFrame()

    existing_fingerprints = set()
    for ps in existing_processed:
        raw = ps.raw_sale

        if raw:
            fingerprint = (
                str(raw.date.date()) if raw.date else "",
                str(raw.product or "").strip().lower(),
                int(raw.qty or 0),
                round(float(raw.price or 0), 2)
            )
            existing_fingerprints.add(fingerprint)

    logger.debug(f"Built {len(existing_fingerprints)} fingerprints from existing processed records")

    duplicate_indices = []

    for idx, row in df.iterrows():
        try:
            date_val = row["date"]
            if hasattr(date_val, "date"):
                date_str = str(date_val.date())
            else:
                date_str = str(pd.to_datetime(date_val).date())

            fingerprint = (
                date_str,
                str(row["product"]).strip().lower(),
                int(float(str(row["qty"]))),
                round(float(str(row["price"])), 2)
            )

            if fingerprint in existing_fingerprints:
                duplicate_indices.append(idx)
                logger.warning(
                    f"Duplicate found — Row ID {row['id']}: "
                    f"{row['product']} on {date_str}"
                )

        except Exception as e:
            logger.warning(f"Error checking duplicate for row ID {row['id']}: {e}")

    if duplicate_indices:
        dup_failed_df = df.loc[duplicate_indices].copy()
        dup_failed_df["fail_reason"] = (
            "duplicate: record with same date+product+qty+price "
            "already exists in processed_sales"
        )
        clean_df = df.drop(index=duplicate_indices).copy()
        logger.warning(f"Found {len(dup_failed_df)} duplicate records")
    else:
        dup_failed_df = pd.DataFrame()
        clean_df = df.copy()
        logger.info("No duplicates found")

    logger.info(f"After duplicate check -> clean: {len(clean_df)}, failed: {len(dup_failed_df)}")
    return clean_df, dup_failed_df



def standardize_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies formatting and standardization to clean records.
    """
    logger.info("Standardizing data formatting...")

    if df.empty:
        logger.info("No records to standardize")
        return df

    df = df.copy()

    df["category"] = df["category"].str.title()

    df["product"] = df["product"].str.title()

    df["price"] = df["price"].round(2)

    df["qty"] = df["qty"].astype(int)

    df["date"] = pd.to_datetime(df["date"])

    logger.info(f"Standardized {len(df)} records")
    logger.debug(f"Sample after standardization:\n{df[['product', 'category', 'price']].head(3)}")

    return df

def validate_dataframe(
    df: pd.DataFrame,
    db: Session
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Runs all cleaning and validation steps in sequence.
    """
    logger.info("Starting validation pipeline...")

    if df.empty:
        logger.info("Empty DataFrame — nothing to validate")
        return pd.DataFrame(), pd.DataFrame()

    total_input = len(df)
    all_failed_parts = []

    clean_df, null_failed = check_nulls(df)
    if not null_failed.empty:
        all_failed_parts.append(null_failed)

    clean_df, type_failed = validate_types(clean_df)
    if not type_failed.empty:
        all_failed_parts.append(type_failed)

    clean_df, dup_failed = check_duplicates(clean_df, db)
    if not dup_failed.empty:
        all_failed_parts.append(dup_failed)

    clean_df = standardize_data(clean_df)

    if all_failed_parts:
        all_failed_df = pd.concat(all_failed_parts, ignore_index=True)
    else:
        all_failed_df = pd.DataFrame()

    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info(f"Total input records: {total_input}")
    logger.info(f"Passed (clean): {len(clean_df)}")
    logger.info(f"Failed: {len(all_failed_df)}")

    if not all_failed_df.empty and "fail_reason" in all_failed_df.columns:
        reasons = all_failed_df["fail_reason"].str.split(":").str[0]
        reason_counts = reasons.value_counts()
        logger.info("Failure breakdown:")
        for reason, count in reason_counts.items():
            logger.info(f"    {reason}: {count} record(s)")

    logger.info("=" * 60)

    return clean_df, all_failed_df



def update_failed_records(failed_df: pd.DataFrame, db: Session) -> int:
    """
    Updates the status of failed records in the DB.
    """
    if failed_df.empty:
        logger.info("No failed records to update in DB")
        return 0

    logger.info(f"Writing {len(failed_df)} failed records back to DB...")

    updated_count = 0

    for _, row in failed_df.iterrows():

        try:
            record_id = int(row["id"])
            fail_reason = str(row.get("fail_reason", "unknown error"))

            db_record = db.query(RawSale).filter(RawSale.id == record_id).first()

            if db_record:
                db_record.status = "failed"
                db_record.fail_reason = fail_reason

                updated_count += 1
                logger.debug(f"Marked ID {record_id} as failed: {fail_reason}")

            else:
                logger.warning(f"Record ID {record_id} not found in DB — skipping")

        except Exception as e:
            logger.error(f"Failed to update record {row.get('id', '?')}: {e}")

    try:
        db.commit()
        logger.info(f"Successfully marked {updated_count} records as failed in DB")
    except Exception as e:
        db.rollback()
        logger.error(f"DB commit failed when updating failed records: {e}")
        raise

    return updated_count



def calculate_financials(clean_df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies financial calculations to every clean row.
    """
    logger.info("Calculating financials...")
    logger.info(f"Applying TAX_RATE={TAX_RATE*100:.1f}%, "
                f"DISCOUNT_RATE={DISCOUNT_RATE*100:.1f}%")

    if clean_df.empty:
        logger.info("No records to calculate")
        return clean_df

    df = clean_df.copy()
    df["total"] = df["qty"] * df["price"]
    df["tax"] = df["total"] * TAX_RATE
    df["discount"] = df["total"] * DISCOUNT_RATE
    df["final_amount"] = df["total"] + df["tax"] - df["discount"]
    
    for col in ["total", "tax", "discount", "final_amount"]:
        df[col] = df[col].round(2)
    
    logger.debug(
        f"Sample calculation:\n"
        f"{df[['product', 'qty', 'price', 'total', 'tax', 'discount', 'final_amount']].head(3)}"
    )

    total_revenue = df["final_amount"].sum().round(2)
    total_tax = df["tax"].sum().round(2)
    total_discount= df["discount"].sum().round(2)

    logger.info(f"Records calculated : {len(df)}")
    logger.info(f"Total revenue : Rs.{total_revenue:,.2f}")
    logger.info(f"Total tax collected: Rs.{total_tax:,.2f}")
    logger.info(f"Total discount : Rs.{total_discount:,.2f}")

    return df

def write_to_processed(
    clean_df: pd.DataFrame,
    db: Session
) -> Tuple[int, int]:
    """
    Bulk inserts calculated records into processed_sales and
    updates the corresponding raw_sales status to 'processed'.
    """
    logger.info("Writing to processed_sales...")

    if clean_df.empty:
        logger.info("No records to write")
        return 0, 0

    processed_objects = []
    now = datetime.now(timezone.utc)
    
    for _, row in clean_df.iterrows():
        try:
            ps = ProcessedSale(
                raw_id = int(row["id"]),
                total = float(row["total"]),
                tax = float(row["tax"]),
                discount = float(row["discount"]),
                final_amount = float(row["final_amount"]),
                processed_at = now
            )
            processed_objects.append(ps)

        except Exception as e:
            logger.error(
                f"Failed to build ProcessedSale for raw_id={row.get('id')}: {e}"
            )

    if not processed_objects:
        logger.error("No ProcessedSale objects built — nothing to insert")
        return 0, len(clean_df)

    raw_ids_to_update = [ps.raw_id for ps in processed_objects]
    
    try:
        db.add_all(processed_objects)

        db.flush()

        updated_count = 0
        for raw_id in raw_ids_to_update:
            raw_record = db.query(RawSale).filter(
                RawSale.id == raw_id
            ).first()

            if raw_record:
                raw_record.status = "processed"
                updated_count += 1

        db.commit()

        logger.info(
            f"Successfully wrote {len(processed_objects)} records "
            f"to processed_sales"
        )
        logger.info(
            f"Updated {updated_count} raw_sales records "
            f"to status='processed'"
        )

        return len(processed_objects), 0

    except Exception as e:
        db.rollback()

        logger.error(f"TRANSACTION FAILED — rolling back: {e}")
        logger.error(
            f"{len(processed_objects)} records were NOT written. "
            f"raw_sales status NOT updated."
        )

        try:
            for raw_id in raw_ids_to_update:
                raw_record = db.query(RawSale).filter(
                    RawSale.id == raw_id
                ).first()
                if raw_record:
                    raw_record.status = "failed"
                    raw_record.fail_reason = (
                        f"load_error: DB transaction failed — {str(e)}"
                    )
            db.commit()
            logger.info(
                f"Marked {len(raw_ids_to_update)} records "
                f"as 'failed' due to transaction error"
            )
        except Exception as inner_e:
            db.rollback()
            logger.error(
                f"Could not even mark records as failed: {inner_e}"
            )

        return 0, len(processed_objects)


def run_pipeline(db: Session) -> dict:
    """
    The single entry point for the full ETL pipeline.
    Called by the FastAPI endpoint POST /pipeline/run.
    """
    pipeline_start = datetime.now(timezone.utc)

    raw_df = load_pending_records(db)

    if raw_df.empty:
        logger.info("Pipeline complete — no pending records found")
        logger.info("=" * 60)
        return {
            "total_loaded": 0,
            "processed": 0,
            "failed": 0,
            "skipped_duplicates": 0,
            "tax_collected": 0.0,
            "total_revenue": 0.0,
            "message": "No pending records found. Nothing to process."
        }

    total_loaded = len(raw_df)

    clean_df, failed_df = validate_dataframe(raw_df, db)

    skipped_duplicates = 0
    if not failed_df.empty and "fail_reason" in failed_df.columns:
        skipped_duplicates = int(
            failed_df["fail_reason"].str.startswith("duplicate").sum()
        )

    update_failed_records(failed_df, db)

    if clean_df.empty:
        logger.info("No clean records to transform — pipeline stopping")
        logger.info("=" * 60)
        return {
            "total_loaded": total_loaded,
            "processed": 0,
            "failed": len(failed_df),
            "skipped_duplicates": skipped_duplicates,
            "tax_collected": 0.0,
            "total_revenue": 0.0,
            "message": "All records failed validation. Check fail reasons."
        }

    calculated_df = calculate_financials(clean_df)

    tax_collected = round(float(calculated_df["tax"].sum()), 2)
    total_revenue = round(float(calculated_df["final_amount"].sum()), 2)

    written, write_failed = write_to_processed(calculated_df, db)

    total_failed = len(failed_df) + write_failed

    pipeline_end = datetime.now(timezone.utc)
    duration_seconds = (pipeline_end - pipeline_start).total_seconds()

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE — FINAL SUMMARY")
    logger.info(f"Duration : {duration_seconds:.2f} seconds")
    logger.info(f"Total loaded : {total_loaded}")
    logger.info(f"Successfully processed: {written}")
    logger.info(f"Failed : {total_failed}")
    logger.info(f"of which duplicates: {skipped_duplicates}")
    logger.info(f"Total revenue : Rs.{total_revenue:,.2f}")
    logger.info(f"Tax collected : Rs.{tax_collected:,.2f}")
    logger.info(
        f"Discount given : Rs. {round(float(calculated_df['discount'].sum()), 2):,.2f}"
    )
    logger.info("=" * 60)

    return {
        "total_loaded": total_loaded,
        "processed": written,
        "failed": total_failed,
        "skipped_duplicates": skipped_duplicates,
        "tax_collected": tax_collected,
        "total_revenue": total_revenue,
        "message": (
            f"Pipeline complete. {written} records processed, "
            f"{total_failed} failed."
        )
    }