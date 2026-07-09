import io
import time
import logging
import logging.handlers
import os
from datetime import timedelta, datetime, timezone
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException,status, UploadFile, File, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from typing import Optional, List
from backend.database import engine, Base, get_db
import backend.models
from backend.models import User, RawSale, ProcessedSale, PipelineRun, PipelineStatus
from backend.schemas import UserRegisterSchema, UserLoginSchema,TokenResponseSchema, UserResponseSchema,RawSaleCreate, RawSaleResponse,ProcessedSaleResponse, CSVUploadResponse,RoleUpdateSchema
from backend.auth import hash_password, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user, require_role, require_admin, require_viewer
from backend.pipeline import run_pipeline

def setup_api_logger() -> logging.Logger:
    """
    Sets up a dedicated logger for API requests.
    Writes to data/api.log (separate from pipeline.log).
    """
    api_logger = logging.getLogger("api")
    api_logger.setLevel(logging.INFO)

    if not api_logger.handlers:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "api.log"),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8"
        )
        
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        api_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        api_logger.addHandler(console_handler)

    return api_logger

api_logger  = setup_api_logger()
pipe_logger = logging.getLogger("pipeline")

app = FastAPI(
    title="Sales Pipeline API",
    description="Backend API for Sales Data Pipeline Dashboard",
    version="1.0.0"
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    FastAPI middleware that runs for EVERY incoming HTTP request.
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"

    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 1)
        log_level = (
            logging.WARNING if response.status_code >= 400
            else logging.INFO
        )
        api_logger.log(
            log_level,
            f"{request.method} {request.url.path} | "
            f"{response.status_code} | "
            f"{duration_ms}ms | "
            f"client={client_ip}"
        )

        return response

    except Exception as e:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        api_logger.error(
            f"{request.method} {request.url.path} | "
            f"EXCEPTION | {duration_ms}ms | {str(e)}"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": "An unexpected error occurred. Please try again.",
            }
        )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches ANY unhandled exception in ANY route.
    Returns a safe JSON response instead of a Python traceback.
    """
    api_logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: "
        f"{type(exc).__name__}: {str(exc)}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "Something went wrong on the server. Please try again later."
        }
    )

Base.metadata.create_all(bind=engine)

def _ensure_pipeline_status(db):
    """Creates the initial PipelineStatus row if it doesn't exist."""
    existing = db.query(PipelineStatus).filter(PipelineStatus.id == 1).first()
    if not existing:
        db.add(PipelineStatus(id=1, is_running=0))
        db.commit()

PIPELINE_LOCK_TIMEOUT_MINUTES = 30

def _acquire_pipeline_lock(db: Session, username: str) -> bool:
    """
    Tries to acquire the pipeline lock.
    Returns True if lock was acquired, False if already locked.
    """
    _ensure_pipeline_status(db)

    status_row = db.query(PipelineStatus).filter(
        PipelineStatus.id == 1
    ).first()

    if status_row.is_running:
        if status_row.started_at:
            elapsed = datetime.now(timezone.utc) - status_row.started_at
            if elapsed.total_seconds() > PIPELINE_LOCK_TIMEOUT_MINUTES * 60:
                pipe_logger.warning(
                    f"Stale pipeline lock detected "
                    f"(started {elapsed.total_seconds()/60:.1f} minutes ago). "
                    f"Resetting lock."
                )
            else:
                return False

    status_row.is_running  = 1
    status_row.started_at  = datetime.now(timezone.utc)
    status_row.locked_by   = username
    db.commit()
    return True


def _release_pipeline_lock(db: Session):
    """Releases the pipeline lock after a run completes or fails."""
    try:
        status_row = db.query(PipelineStatus).filter(
            PipelineStatus.id == 1
        ).first()
        if status_row:
            status_row.is_running = 0
            status_row.started_at = None
            status_row.locked_by = None
            db.commit()
    except Exception as e:
        pipe_logger.error(f"Failed to release pipeline lock: {e}")
        
@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "message": "Sales Pipeline API is running",
        "version": "1.0.0"
    }

@app.post("/auth/register", tags=["Auth"])
def register(user_data: UserRegisterSchema, db: Session = Depends(get_db)):
    """
    Registers a new user.
    Pydantic validates length limits before this function runs.
    """
    try:
        existing = db.query(User).filter(
            User.username == user_data.username
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists. Please choose a different username."
            )

        allowed_roles = ["admin", "viewer"]
        role = user_data.role if user_data.role in allowed_roles else "viewer"

        new_user = User(
            username = user_data.username,
            password_hash = hash_password(user_data.password),
            role = role
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        api_logger.info(f"New user registered: {new_user.username} (role: {role})")

        return {
            "message": "User registered successfully",
            "username": new_user.username,
            "role": new_user.role
        }

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register user. Please try again."
        )


@app.post("/auth/login", response_model=TokenResponseSchema, tags=["Auth"])
def login(user_data: UserLoginSchema, db: Session = Depends(get_db)):
    """
    Authenticates a user and returns a JWT token.
    """
    user = db.query(User).filter(User.username == user_data.username).first()

    if not user:
        api_logger.warning(
            f"Failed login attempt: username='{user_data.username}' "
            f"(user not found)"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(user_data.password, user.password_hash):
        api_logger.warning(
            f"Failed login attempt: username='{user_data.username}' "
            f"(wrong password)"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    api_logger.info(f"Successful login: username='{user.username}' role='{user.role}'")

    return TokenResponseSchema(access_token=access_token, token_type="bearer")


@app.get("/auth/me", tags=["Auth"])
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id" : current_user.id,
        "username": current_user.username,
        "role" : current_user.role,
        "message" : f"Hello, {current_user.username}!"
    }

@app.get("/admin/dashboard", tags=["Admin"])
def admin_dashboard(current_user: User = require_admin):
    return {
        "message" : f"Welcome, {current_user.username}!",
        "role" : current_user.role,
        "access_level" : "full",
        "available_actions": [
            "View all Users", "Process sales Data",
            "Delete records", "View all reports"
        ]
    }


@app.get("/admin/users", tags=["Admin"])
def list_all_users(
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """Returns all users. Never includes password_hash."""
    try:
        users = db.query(User).all()
        return {
            "total_users": len(users),
            "users": [
                {
                    "id": u.id,
                    "username": u.username,
                    "role": u.role,
                    "created_at": u.created_at.isoformat() if u.created_at else None
                }
                for u in users
            ]
        }
    except Exception as e:
        api_logger.error(f"Failed to list users: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve users."
        )

@app.patch("/admin/users/{user_id}/role", tags=["Admin"])
def update_user_role(
    user_id: int,
    role_data: RoleUpdateSchema,
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """Changes a user's role. Admins cannot change their own role."""
    try:
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot change your own role. Ask another admin."
            )

        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found."
            )

        old_role = target.role
        target.role = role_data.role
        db.commit()
        db.refresh(target)

        api_logger.info(
            f"Role change: admin='{current_user.username}' "
            f"changed '{target.username}' from '{old_role}' to '{role_data.role}'"
        )

        return {
            "message": (
                f"Changed '{target.username}' from '{old_role}' to '{role_data.role}'"
            ),
            "user": {
                "id": target.id,
                "username": target.username,
                "role": target.role,
                "created_at": target.created_at.isoformat() if target.created_at else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Role update error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update role.")

@app.patch("/admin/promote/{username}", tags=["Admin"])
def promote_to_admin(
    username: str,
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """Promotes a user to admin by username."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    if user.role == "admin":
        return {"message": f"'{username}' is already an admin."}
    user.role = "admin"
    db.commit()
    db.refresh(user)
    return {"message": f"Promoted '{username}' to admin.", "role": user.role}

@app.get("/viewer/data", tags=["Viewer"])
def viewer_data(current_user: User = require_viewer):
    return {
        "message": f"Welcome, {current_user.username}!",
        "role": current_user.role,
        "access_level": "read_only"
    }

@app.get("/viewer/summary", tags=["Viewer"])
def viewer_summary(current_user: User = require_viewer):
    return {
        "message": "Sales summary",
        "accessed_by": current_user.username,
        "placeholder_stats": {
            "total_sales": 0,
            "total_revenue": 0.0,
            "pending_records": 0,
            "processed_records": 0
        }
    }

@app.get("/me", tags=["User"])
def get_me_route(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role
    }

REQUIRED_CSV_COLUMNS = {"date", "product", "category", "qty", "price"}


@app.post(
    "/sales/upload-manual",
    response_model=RawSaleResponse,
    tags=["Sales"],
    status_code=status.HTTP_201_CREATED
)
def upload_manual_sale(
    sale_data: RawSaleCreate,
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """Adds a single sale record manually. Admin only."""
    try:
        new_sale = RawSale(
            date = datetime.combine(sale_data.date, datetime.min.time()),
            product = sale_data.product,
            category = sale_data.category,
            qty = sale_data.qty,
            price = sale_data.price,
            uploaded_by = current_user.id,
            status= "pending"
        )
        db.add(new_sale)
        db.commit()
        db.refresh(new_sale)
        return new_sale

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        api_logger.error(f"Manual upload error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save sale record. Please try again."
        )


@app.post(
    "/sales/upload-csv",
    response_model=CSVUploadResponse,
    tags=["Sales"],
    status_code=status.HTTP_201_CREATED
)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """Uploads multiple sale records via CSV. Admin only."""

    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only .csv files are accepted."
        )

    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if not contents or len(contents) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty."
        )

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse CSV. Make sure it is a valid CSV file. Error: {str(e)}"
        )

    df.columns = df.columns.str.strip().str.lower()
    missing_cols = REQUIRED_CSV_COLUMNS - set(df.columns)
    if missing_cols:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing required columns: {sorted(missing_cols)}. "
                f"Required: {sorted(REQUIRED_CSV_COLUMNS)}. "
                f"Found: {sorted(df.columns.tolist())}."
            )
        )

    if len(df) == 0:
        raise HTTPException(
            status_code=400,
            detail="CSV has headers but no data rows."
        )

    inserted = 0
    skipped  = 0
    total = len(df)

    for idx, row in df.iterrows():
        try:
            raw_date = str(row["date"]).strip()
            try:
                parsed_date = pd.to_datetime(raw_date)
                sale_dt     = parsed_date.to_pydatetime()
            except Exception:
                skipped += 1
                continue

            product = str(row["product"]).strip()
            if not product or product.lower() == "nan":
                skipped += 1
                continue

            category = str(row["category"]).strip()
            if not category or category.lower() == "nan":
                skipped += 1
                continue

            product  = product[:100]
            category = category[:50]

            try:
                qty = int(float(str(row["qty"]).strip()))
                if qty <= 0:
                    raise ValueError("qty <= 0")
            except Exception:
                skipped += 1
                continue

            try:
                price = float(str(row["price"]).strip())
                if price <= 0:
                    raise ValueError("price <= 0")
            except Exception:
                skipped += 1
                continue

            db.add(RawSale(
                date = sale_dt,
                product = product,
                category = category,
                qty = qty,
                price = price,
                uploaded_by = current_user.id,
                status = "pending"
            ))
            inserted += 1

        except Exception:
            skipped += 1
            continue

    if inserted > 0:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            api_logger.error(f"CSV bulk insert failed: {e}")
            raise HTTPException(
                status_code=500,
                detail="Failed to save records to database."
            )

    api_logger.info(
        f"CSV upload by '{current_user.username}': "
        f"{inserted} inserted, {skipped} skipped, {total} total"
    )

    return CSVUploadResponse(
        message = f"Upload complete: {inserted} inserted, {skipped} skipped.",
        inserted = inserted,
        skipped = skipped,
        total_rows = total
    )


@app.get("/sales/raw", response_model=List[RawSaleResponse], tags=["Sales"])
def get_raw_sales(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns raw sales with optional status filter."""
    try:
        query = db.query(RawSale)
        valid_statuses = ["pending", "processed", "failed"]
        if status_filter:
            if status_filter.lower() not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status '{status_filter}'. Must be one of {valid_statuses}."
                )
            query = query.filter(RawSale.status == status_filter.lower())
        return query.order_by(RawSale.created_at.desc()).all()

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"get_raw_sales error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch raw sales.")


@app.get(
    "/sales/raw/{sale_id}",
    response_model=RawSaleResponse,
    tags=["Sales"]
)
def get_raw_sale_by_id(
    sale_id: int,
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns a single raw sale by ID. 404 if not found."""
    sale = db.query(RawSale).filter(RawSale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail=f"Sale ID {sale_id} not found.")
    return sale


@app.get(
    "/sales/processed",
    response_model=List[ProcessedSaleResponse],
    tags=["Sales"]
)
def get_processed_sales(
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns all processed sales ordered by most recent first."""
    try:
        return db.query(ProcessedSale).order_by(
            ProcessedSale.processed_at.desc()
        ).all()
    except Exception as e:
        api_logger.error(f"get_processed_sales error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch processed sales.")

@app.post("/pipeline/run", tags=["Pipeline"])
def trigger_pipeline(
    current_user: User = require_admin,
    db: Session = Depends(get_db)
):
    """
    Triggers the full ETL pipeline.
    Returns 409 if pipeline is already running.
    Admin only.
    """
    lock_acquired = _acquire_pipeline_lock(db, current_user.username)
    if not lock_acquired:
        status_row = db.query(PipelineStatus).filter(
            PipelineStatus.id == 1
        ).first()
        locked_by = status_row.locked_by if status_row else "unknown"
        started = status_row.started_at if status_row else None
        started_str = started.strftime("%H:%M:%S") if started else "unknown time"

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pipeline is already running "
                f"(triggered by '{locked_by}' at {started_str}). "
                "Please wait for it to complete."
            )
        )

    try:
        pipe_logger.info(f"Pipeline triggered by: {current_user.username}")
        summary = run_pipeline(db)

        # Save run to history
        db.add(PipelineRun(
            total_loaded = summary.get("total_loaded", 0),
            processed = summary.get("processed", 0),
            failed = summary.get("failed", 0),
            skipped_duplicates = summary.get("skipped_duplicates", 0),
            total_revenue= summary.get("total_revenue", 0.0),
            tax_collected= summary.get("tax_collected", 0.0),
            triggered_by= current_user.username
        ))
        db.commit()

        return {
            "triggered_by": current_user.username,
            "total_loaded": summary.get("total_loaded", 0),
            "processed": summary.get("processed", 0),
            "failed": summary.get("failed", 0),
            "skipped_duplicates": summary.get("skipped_duplicates", 0),
            "tax_collected": summary.get("tax_collected", 0.0),
            "total_revenue": summary.get("total_revenue", 0.0),
            "message": summary.get("message", "Pipeline complete.")
        }

    except HTTPException:
        raise
    except Exception as e:
        pipe_logger.error(f"Pipeline crashed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Pipeline failed. Check pipeline.log for details."
        )
    finally:
        _release_pipeline_lock(db)
        
@app.get("/pipeline/history", tags=["Pipeline"])
def get_pipeline_history(
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns the last N pipeline run records."""
    try:
        runs = (
            db.query(PipelineRun)
            .order_by(PipelineRun.run_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "run_at": r.run_at.isoformat() if r.run_at else None,
                "total_loaded": r.total_loaded,
                "processed": r.processed,
                "failed": r.failed,
                "skipped_duplicates": r.skipped_duplicates,
                "total_revenue": r.total_revenue,
                "tax_collected": r.tax_collected,
                "triggered_by": r.triggered_by
            }
            for r in runs
        ]
    except Exception as e:
        api_logger.error(f"pipeline history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pipeline history.")


@app.get("/pipeline/status", tags=["Pipeline"])
def get_pipeline_status(
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """
    Returns whether the pipeline is currently running.
    Useful for frontend to poll and show a "pipeline busy" state.
    """
    _ensure_pipeline_status(db)
    status_row = db.query(PipelineStatus).filter(
        PipelineStatus.id == 1
    ).first()

    return {
        "is_running": bool(status_row.is_running),
        "locked_by": status_row.locked_by,
        "started_at": (
            status_row.started_at.isoformat()
            if status_row.started_at else None
        )
    }

@app.get("/dashboard/summary", tags=["Dashboard"])
def get_dashboard_summary(
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns KPI summary metrics from processed_sales."""
    try:
        result = db.query(
            func.sum(ProcessedSale.final_amount).label("total_revenue"),
            func.sum(ProcessedSale.tax).label("total_tax"),
            func.count(ProcessedSale.id).label("total_orders"),
            func.avg(ProcessedSale.final_amount).label("avg_order_value"),
            func.max(ProcessedSale.processed_at).label("last_updated")
        ).first()

        return {
            "total_revenue": round(float(result.total_revenue or 0), 2),
            "total_tax": round(float(result.total_tax or 0), 2),
            "total_orders": int(result.total_orders or 0),
            "avg_order_value": round(float(result.avg_order_value or 0), 2),
            "last_updated": (
                result.last_updated.isoformat() if result.last_updated else None
            )
        }
    except Exception as e:
        api_logger.error(f"dashboard summary error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard summary.")


@app.get("/dashboard/revenue-trend", tags=["Dashboard"])
def get_revenue_trend(
    start_date: str | None = Query(default=None, alias="start_date"),
    end_date: str | None   = Query(default=None, alias="end_date"),
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns daily revenue grouped by date with optional date filters."""
    try:
        from datetime import timedelta

        query = db.query(
            cast(RawSale.date, Date).label("sale_date"),
            func.sum(ProcessedSale.final_amount).label("revenue"),
            func.count(ProcessedSale.id).label("order_count")
        ).join(
            RawSale, ProcessedSale.raw_id == RawSale.id
        ).group_by(
            cast(RawSale.date, Date)
        )

        if start_date:
            try:
                clean = start_date.strip().split("T")[0].split(" ")[0]
                start_dt = datetime.strptime(clean, "%Y-%m-%d")
                query = query.filter(RawSale.date >= start_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid start_date '{start_date}'. Use YYYY-MM-DD."
                )

        if end_date:
            try:
                clean = end_date.strip().split("T")[0].split(" ")[0]
                end_dt = datetime.strptime(clean, "%Y-%m-%d") + timedelta(days=1)
                query = query.filter(RawSale.date < end_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid end_date '{end_date}'. Use YYYY-MM-DD."
                )

        results = query.order_by("sale_date").all()
        trend_data = []
        for row in results:
            val = row.sale_date
            if val is None:
                continue
            date_str = (
                val.strftime("%Y-%m-%d") if hasattr(val, "strftime")
                else str(val).split("T")[0].split(" ")[0]
            )
            trend_data.append({
                "date": date_str,
                "revenue": round(float(row.revenue or 0), 2),
                "order_count": int(row.order_count or 0)
            })

        return trend_data

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"revenue trend error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch revenue trend: {str(e)}"
        )

@app.get("/dashboard/top-products", tags=["Dashboard"])
def get_top_products(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns top N products by revenue."""
    try:
        results = db.query(
            RawSale.product.label("product"),
            RawSale.category.label("category"),
            func.sum(ProcessedSale.final_amount).label("revenue"),
            func.sum(RawSale.qty).label("units_sold")
        ).join(
            RawSale, ProcessedSale.raw_id == RawSale.id
        ).group_by(
            RawSale.product, RawSale.category
        ).order_by(
            func.sum(ProcessedSale.final_amount).desc()
        ).limit(limit).all()

        return [
            {
                "product": row.product or "Unknown",
                "category": row.category or "Uncategorized",
                "revenue": round(float(row.revenue or 0), 2),
                "units_sold": int(row.units_sold or 0)
            }
            for row in results
        ]
    except Exception as e:
        api_logger.error(f"top products error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch top products.")


@app.get("/dashboard/category-breakdown", tags=["Dashboard"])
def get_category_breakdown(
    current_user: User = require_viewer,
    db: Session = Depends(get_db)
):
    """Returns revenue per category with percentage of total."""
    try:
        results = db.query(
            RawSale.category.label("category"),
            func.sum(ProcessedSale.final_amount).label("revenue"),
            func.count(ProcessedSale.id).label("order_count")
        ).join(
            RawSale, ProcessedSale.raw_id == RawSale.id
        ).group_by(
            RawSale.category
        ).order_by(
            func.sum(ProcessedSale.final_amount).desc()
        ).all()

        if not results:
            return []

        total_revenue = sum(float(r.revenue or 0) for r in results)
        return [
            {
                "category": row.category or "Uncategorized",
                "revenue": round(float(row.revenue or 0), 2),
                "order_count": int(row.order_count or 0),
                "percentage": (
                    round((float(row.revenue or 0) / total_revenue) * 100, 2)
                    if total_revenue > 0 else 0.0
                )
            }
            for row in results
        ]
    except Exception as e:
        api_logger.error(f"category breakdown error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch category breakdown.")