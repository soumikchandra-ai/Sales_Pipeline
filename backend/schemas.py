#To validate the incoming request and the outgoing response
from pydantic import BaseModel, Field ,field_validator
from typing import Optional
from datetime import date as date_type , datetime

#Auth Schemas
class UserRegisterSchema(BaseModel):
    """
    Data type required when a user tries to register
    """
    username:str = Field(
        ...,
        min_length=5,
        max_length=50,
        description="Unique username for an account: 3-50 characters"
    )
    password:str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password: 8-128 characters."
    )
    role:Optional[str] = Field(
        default="viewer",
        description="User role: admin or viewer"
    )
    
    @field_validator("username")
    @classmethod
    def username_no_spaces(cls, value: str) -> str:
        """Usernames cannot contain spaces."""
        if " " in value.strip():
            raise ValueError("Username cannot contain spaces")
        return value.strip().lower()

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        """Only allow known roles."""
        allowed = {"admin", "viewer"}
        if value not in allowed:
            return "viewer"
        return value
    
class UserLoginSchema(BaseModel):
    """
    Data expected when someone tries to login
    """
    username:str = Field(...,min_length=1,max_length=50,description="Registered Username")
    password:str = Field(...,min_length=1,max_length=128,description="Account Password")
    
class TokenResponseSchema(BaseModel):
    """
    Data sent back when someone successfully logs in the app
    """
    access_token:str         #The actual JWT token
    token_type:str = "bearer"
    
class UserResponseSchema(BaseModel):
    """
    To show who logged in the app
    """
    id :int
    username:str
    role: str
    
    class Config:
        from_attributes = True  #To read SQLAlchemy objects
        
class RawSaleCreate(BaseModel):
    """
    Schema for creating a new raw sale record.
    """
    date: date_type = Field(...,description="Date the sale happened (YYYY-MM-DD format)",example="2026-05-12")
    product:str =Field(...,min_length=1,max_length=100,description="Name of the product sold",example="Basmati Rice 5kg")
    category: str =Field(...,min_length=1,max_length=50,description="Product categoory",example="Groceries")
    qty:int =Field(...,gt=0,description="Quantity Sold(must be greater than or equal to 1)",example=3)
    price:float = Field(...,gt=0,description="Price per unit in rupees(must be >0)",example=250.00)
    
    @field_validator("product","category")
    @classmethod
    def strip_whitespace(cls,value:str)->str:
        "Custom validator: removes leading and trailing spaces."
        return value.strip()
    
    @field_validator("date")
    @classmethod
    def date_not_in_future(cls, value: date_type) -> date_type:
        "Custom validator: Sale data cannot be in future"
        if value>date_type.today():
            raise ValueError("Sale data cannot be in future")
        return value
    
    class Config:
        from_attributes=True
        
class RawSaleResponse(BaseModel):
    "Schema for returing a raw sale record from database."
    id:int
    date:date_type
    product:str
    category:str
    qty:int
    price:float
    status:str
    uploaded_by:int
    fail_reason: Optional[str] = None
    created_at:Optional[datetime]
    
    class Config:
        from_attributes = True
        
class ProcessedSaleResponse(BaseModel):
    "Schema for returning a processed sale."
    id:int
    raw_id:int
    total:float
    tax:float
    discount:float
    final_amount:float
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True
        
class CSVUploadResponse(BaseModel):
    "Schema for the response after a CSV Upload."
    
    message: str
    inserted:int
    skipped:int=0
    total_rows:int

class RoleUpdateSchema(BaseModel):
    """Request body for PATCH /admin/users/{id}/role"""
    role: str = Field(...,description="New role: 'admin' or 'viewer'")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        allowed = {"admin", "viewer"}
        if value not in allowed:
            raise ValueError(
                f"Invalid role '{value}'. Must be one of: {list(allowed)}"
            )
        return value