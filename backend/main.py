import io
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from typing import Optional, List
from backend.database import engine,Base, get_db
import backend.models
import pandas as pd
from sqlalchemy.orm import Session
from datetime import timedelta,datetime
from backend.models import User,RawSale,ProcessedSale
from backend.schemas import UserRegisterSchema, UserLoginSchema, TokenResponseSchema, UserResponseSchema, RawSaleCreate, RawSaleResponse, ProccessedSaleResponse, CSVUploadResponse
from backend.auth import hash_password, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user, require_role, require_admin, require_viewer

app=FastAPI(
    title="Sales pipeline API",
    description="Backend API for Sales Data Pipeline Dashboard",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

REQUIRED_CSV_COLUMNS = {"date","product","category","qty","price"}

@app.get("/",tags=["Health"])
def health_check():
    return {
        "status":"OK",
        "message":"Sales Data Pipeline API is running",
        "version":"1.0.0"
    }

@app.post("/auth/register",tags=["Auth"])
def register(user_data: UserRegisterSchema, db:Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username==user_data.username).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists.Please choose a differenet username."
        )
    
    allowed_roles=["admin","viewer"]
    role = user_data.role if user_data.role in allowed_roles else "viewer"
    hashed = hash_password(user_data.password)
    
    new_user = User(
        username=user_data.username,
        password_hash=hashed,
        role=role
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {
        "message":"User registered Successfully",
        "username":new_user.username,
        "role":new_user.role
    }

@app.post("/auth/login",response_model=TokenResponseSchema, tags=["Auth"])
def login(user_data: UserLoginSchema, db:Session = Depends(get_db)):
    """"
    Login with Username and coorect password.
    Returns a JWT Token.
    """
    user=db.query(User).filter(User.username==user_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate":"Bearer"}
        )
        
    if not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate":"Bearer"}
        )
        
    token_data = {
        "sub":user.username,
        "role":user.role,
        "id":user.id
    }
    
    access_token = create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return TokenResponseSchema(
        access_token=access_token,
        token_type="bearer"
    )
    
@app.get("/auth/me",tags=["Auth"])
def get_me(current_user:User = Depends(get_current_user)):
    """
    Return info about the currently logged in User
    """
    return {
        "id":current_user.id,
        "username":current_user.username,
        "role":current_user.role,
        "message":f"Hello, {current_user.username}! You are logged in as {current_user.role}"
    }

#Admin-Only Routes
@app.get("/admin/dashboard",tags=["Admin"])
def admin_dashboard(current_user: User= require_admin):
    """
    Admin only routes. Users whose role is admin can only access this.
    """
    return{
        "message":f"Welcome to the Admin Dashboard, {current_user.username}!",
        "role":current_user.role,
        "access_level":"full",
        "available_actions":[
            "View all Users",
            "Process sales Data",
            "Delete records",
            "View all reports"
        ]
    }

@app.get("/admin/users",tags=["Admin"])
def list_all_users(current_user: User = require_admin, db: Session = Depends(get_db)):
    "Admin route only to list all the Users"
    users= db.query(User).all() #Returns a list of all User objects from the database
    
    return{
        "total_users":len(users),
        "users":[
            {
                "id":u.id,
                "username":u.username,
                "role":u.role,
                "created_at":u.created_at
            }
            for u in users
        ]
    }
    
#Viewer Routes
@app.get("/viewer/data",tags=["Viewer"])
def viewer_data(current_user: User= require_viewer):
    "Viewer route: Both viewer and admin can access this."
    return {
        "message":f"Welcome to the data view {current_user.username}",
        "role":current_user.role,
        "access_level":"read_only",
        "note":"You can view sales data here. Upload and processing requires admin access."
    }
    
@app.get("/viewer/summary",tags=["Viewer"])
def viewer_summary(current_user: User= require_viewer):
    "Shows a placeholder summary. Connected to the real sales data."
    return {
        "message":"Sales summary appear here",
        "accessed_by":current_user.username,
        "role":current_user.role,
        "placeholder_stats":{
            "total_sales":0,
            "total_revenue":0.0,
            "pending_records":0,
            "processed_records":0
        }
    }
    
@app.post("/sales/upload-manual",response_model=RawSaleResponse,tags=["Sales"],status_code=status.HTTP_201_CREATED)
def upload_manual_sale(sale_data:RawSaleCreate,current_user:User=require_admin,db:Session=Depends(get_db)):
    """
    Uplaod a single sale record manually via JSON.
    Admin ONLY.
    """
    try:
        new_sale = RawSale(
            date=datetime.combine(sale_data.date,datetime.min.time()),
            product=sale_data.product,
            category=sale_data.category,
            qty=sale_data.qty,
            price=sale_data.price,
            uploaded_by=current_user.id,
            status="pending"
        )
        db.add(new_sale)
        db.commit()
        db.refresh(new_sale)
        
        return new_sale
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save the sale record. Error: {str(e)}"
        )
        
@app.post("/sales/upload-csv",response_model=CSVUploadResponse,tags=["Sales"],status_code=status.HTTP_201_CREATED)
async def upload_csv(file:UploadFile=File(...),current_user:User=require_admin,db:Session=Depends(get_db)):
    """
    Upload multiple Sales records via CSV Files.
    Admin ONLY.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV Files are supported."
        )
        
    try:
        contents=await file.read()
        if len(contents)==0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty."
            )
        df=pd.read_csv(io.BytesIO(contents))
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read the CSV File. Error: {str(e)}"
        )
    
    df.columns = df.columns.str.strip().str.lower()
    actual_columns = set(df.columns)
    missing_columns = REQUIRED_CSV_COLUMNS - actual_columns
    
    if missing_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"CSV is missing required columns: {sorted(missing_columns)}. "
                f"Required columns are: {sorted(REQUIRED_CSV_COLUMNS)}. "
                f"Found columns: {sorted(actual_columns)}."
            )
        )
    
    if len(df)==0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV File has no data rows(only headers found)."
        )
        
    inserted = 0
    skipped = 0
    total_rows = len(df)
    
    for index,row in df.iterrows():
        try:
            raw_date_value = str(row["date"]).strip()
            try:
                parsed_date = pd.to_datetime(raw_date_value)
                sale_datetime = parsed_date.to_pydatetime()
            except Exception:
                print(f"Row {index+1}: Invalid Date '{raw_date_value}' -skipping")
                skipped+=1
                continue
            
            product = str(row["product"]).strip()
            if not product or product.lower()=="nan":
                print(f"Row {index+1} has no product- skipping.")
                skipped+=1
                continue
            
            category = str(row["category"])
            if not category or category.lower() == "nan":
                print(f"  Row {index + 1}: Empty category — skipping")
                skipped += 1
                continue
            
            try:
                qty = int(float(str(row["qty"]).strip()))
                if qty <= 0:
                    raise ValueError("qty must be > 0")
            except Exception:
                print(f"  Row {index + 1}: Invalid qty '{row['qty']}' — skipping")
                skipped += 1
                continue

            try:
                price = float(str(row["price"]).strip())
                if price <= 0:
                    raise ValueError("price must be > 0")
            except Exception:
                print(f"  Row {index + 1}: Invalid price '{row['price']}' — skipping")
                skipped += 1
                continue
            
            new_sale = RawSale(
                date=sale_datetime,
                product=product,
                category=category,
                qty=qty,
                price=price,
                uploaded_by=current_user.id,
                status="pending"
            )
            db.add(new_sale)
            inserted+=1
        except Exception as e:
            print(f"Row {index+1}: Unexpected Error- {str(e)} -skipping")
            skipped+=1
            continue
    
    if inserted>0:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save records to database. Error: {str(e)}"
            )
            
    return CSVUploadResponse(
        message=f"CSV upload Complete. {inserted} rows inserted, {skipped} rows skipped",
        inserted=inserted,
        skipped=skipped,
        total_rows=total_rows
    )
    
@app.get("/sales/raw",response_model=List[RawSaleResponse],tags=["Sales"])
def get_raw_sales(status_filter: Optional[str]=Query(
    default=None,
    alias="status",
    description="Filter by status: pending,processed or failed"
    ),
    current_user:User=require_viewer,
    db:Session=Depends(get_db)):
    """
    Get all raw sales record.
    """
    try:
        query=db.query(RawSale)
        valid_statuses = ["pending","processed","failed"]
        if status_filter:
            if status_filter.lower() not in valid_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status '{status_filter}'. Must be one of: {valid_statuses}"
                )
            query = query.filter(RawSale.status==status_filter.lower())
        sales = query.order_by(RawSale.created_at.desc()).all()
        return sales
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch raw sales. Error: {str(e)}"
        )
        
@app.get("/sales/raw/{sale_id}",response_model=RawSaleResponse,tags=["Sales"])
def get_raw_sale_by_id(sale_id:int, current_user:User=require_viewer,db:Session=Depends(get_db)):
    "Get a single record by sale_id"
    try:
        sale = db.query(RawSale).filter(RawSale.id==sale_id).first()
        if sale is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Raw Sale with ID {sale_id} not found."
            )
        return sale
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sale with ID {sale_id}. Error: {str(e)}"
        )
        
@app.get("/sales/processed",response_model=List[ProccessedSaleResponse],tags=["Sales"])
def get_processed_sales(current_user:User=require_viewer,db:Session=Depends(get_db)):
    "Get all processed sales record"
    try:
        sales = db.query(ProcessedSale).order_by(ProcessedSale.processed_at.desc()).all()
        return sales
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch processed sales. Error: {str(e)}"
        )
        
@app.post("/pipeline/run",tags=["Pipeline"])
def run_pipeline(current_user: User=require_admin):
    "Triggers the ETL Pipelinne to proocess all pending raw sales."
    from backend.database import SessionLocal
    db = SessionLocal()
    
    try:
        pending_count = db.query(RawSale).filter(RawSale.status=="pending").count()
        return {
            "message":"Pipeline triggered successfully.",
            "status":"stub",
            "pending_records_found":pending_count,
            "processed":0,
            "triggered_by":current_user.username
        }
    finally:
        db.close()