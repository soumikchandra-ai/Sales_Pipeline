import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from datetime import datetime, timezone, timedelta
from backend.database import SessionLocal, engine, Base
import backend.models  # noqa: F401 — registers models with Base
from backend.models import RawSale, ProcessedSale
from backend.pipeline import run_cleaning_pipeline
import pandas as pd


def setup_test_data(db):
    """
    Inserts a controlled mix of good and bad records into raw_sales.
    Each record is designed to test a specific validation rule.
    """
    print("\n" + "=" * 60)
    print("INSERTING TEST DATA INTO raw_sales")
    print("=" * 60)

    deleted = db.query(RawSale).filter(RawSale.status == "pending").delete()
    db.commit()
    print(f"Cleared {deleted} existing pending records")
    from backend.models import User
    user = db.query(User).first()
    if not user:
        print("ERROR: No users in database. Run seed.py first!")
        print("  python seed.py")
        sys.exit(1)

    user_id = user.id
    print(f"Using user: {user.username} (id={user_id})\n")

    test_records = [
        {
            "name": "CLEAN-1 Valid sale",
            "date": datetime(2024, 1, 10),
            "product": "basmati rice 5kg",
            "category": "groceries",         
            "qty": 10,
            "price": 250.00,
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "CLEAN-2 Valid electronics sale",
            "date": datetime(2024, 1, 11),
            "product": "  Samsung TV  ",   
            "category": "  electronics  ",   
            "qty": 2,
            "price": 32000.00,
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "CLEAN-3 Price with extra decimals",
            "date": datetime(2024, 1, 12),
            "product": "Toor Dal 1kg",
            "category": "Groceries",
            "qty": 5,
            "price": 140.999,               
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "NULL-1 Missing product name",
            "date": datetime(2024, 1, 13),
            "product": None,               
            "category": "Groceries",
            "qty": 3,
            "price": 100.00,
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "NULL-2 Missing category",
            "date": datetime(2024, 1, 14),
            "product": "Rice",
            "category": None,               
            "qty": 2,
            "price": 50.00,
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "INVALID-1 Negative qty",
            "date": datetime(2024, 1, 15),
            "product": "Bad Product",
            "category": "Other",
            "qty": -5,                      
            "price": 100.00,
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "INVALID-2 Zero price",
            "date": datetime(2024, 1, 16),
            "product": "Free Product",
            "category": "Other",
            "qty": 1,
            "price": 0.0,                   
            "uploaded_by": user_id,
            "status": "pending"
        },
        {
            "name": "INVALID-3 Negative price",
            "date": datetime(2024, 1, 17),
            "product": "Refund Product",
            "category": "Other",
            "qty": 1,
            "price": -200.0,                
            "uploaded_by": user_id,
            "status": "pending"
        },
    ]

    inserted_ids = []
    for rec in test_records:
        name = rec.pop("name")
        new_record = RawSale(**rec)
        db.add(new_record)
        db.flush()
        inserted_ids.append((new_record.id, name))
        print(f"  Inserted ID {new_record.id}: {name}")

    db.commit()
    print(f"\nTotal test records inserted: {len(test_records)}")
    return inserted_ids


def print_dataframe_summary(df: pd.DataFrame, title: str):
    """
    Prints a clean summary of a DataFrame to the console.
    """
    print(f"\n{'=' * 60}")
    print(f"{title} ({len(df)} rows)")
    print("=" * 60)

    if df.empty:
        print("  (empty)")
        return

    cols_to_show = [c for c in ["id", "product", "category", "qty", "price", "fail_reason"]
                    if c in df.columns]
    print(df[cols_to_show].to_string(index=False))

def main():
    """
    Main test function — runs the full test sequence.
    """
    print("\n" * 20)
    print("PIPELINE CLEANING TEST")

    Base.metadata.create_all(bind=engine)
    print("\n Tables verified")

    db = SessionLocal()

    try:
        inserted = setup_test_data(db)

        print("\n" + "-" * 60)
        print("RUNNING CLEANING PIPELINE")
        print("-" * 60)

        results = run_cleaning_pipeline(db)

        print_dataframe_summary(results["clean_df"], "CLEAN RECORDS (passed all checks)")
        print_dataframe_summary(results["failed_df"], "FAILED RECORDS (rejected with reason)")

        print(f"\n{'=' * 60}")
        print("TEST RESULTS SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total pending processed: {results['total_pending']}")
        print(f"Passed (clean): {results['passed']}")
        print(f"Failed: {results['failed']}")

        print(f"\n{'─' * 60}")
        print("DB STATUS AFTER PIPELINE RUN:")
        pending = db.query(RawSale).filter(RawSale.status == "pending").count()
        failed = db.query(RawSale).filter(RawSale.status == "failed").count()
        processed = db.query(RawSale).filter(RawSale.status == "processed").count()
        print(f"raw_sales pending: {pending}")
        print(f"raw_sales failed: {failed}")
        print(f"raw_sales processed: {processed}")

        log_path = os.path.join(os.path.dirname(__file__), "data", "pipeline.log")
        if os.path.exists(log_path):
            log_size = os.path.getsize(log_path)
            print(f"\nLog file created: data/pipeline.log ({log_size} bytes)")
        else:
            print("\nLog file not found at data/pipeline.log")

        print(f"\n")
        print("Test complete! Check data/pipeline.log for full details.")

    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    main()