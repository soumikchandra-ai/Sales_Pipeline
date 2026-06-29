#To validate the incoming request and the outgoing response
from pydantic import BaseModel, Field ,field_validator
from typing import Optional
from datetime import date, datetime

#Auth Schemas
class UserRegisterSchema(BaseModel):
    """
    Data type required when a user tries to register
    """
    username:str = Field(
        ...,
        min_length=5,
        
        max_length=50,
        description="Unique username for an account"
    )
    password:str = Field(
        ...,
        min_length=6,
        description="Password of minimum 6 characters"
    )
    role:Optional[str] = Field(
        default="viewer",
        description="User role: admin or viewer"
    )
    
class UserLoginSchema(BaseModel):
    """
    Data expected when someone tries to login
    """
    username:str = Field(...,description="Registered Username")
    password:str = Field(...,description="Account Password")
    
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
    sale_date: date= Field(...,description="Date the sale happened (YYY-MM-DD format)",example="2026-05-12")
    product:str =Field(...,min_length=1,max_length=200,description="Name of the product sold",example="Basmati Rice 5kg")
    category: str =Field(...,min_length=1,max_length=100,description="Product categoory",example="Groceries")
    qty:int =Field(...,gt=0,description="Quantity Sold",example=3)
    price:float = Field(...,gt=0,description="Price per unit in rupees",example=250.00)
    
    @field_validator("product","category")
    @classmethod
    def strip_whitespace(cla,value:str)->str:
        "Custom validator: removes leading and trailing spaces."
        return value.strip()
    
    @field_validator("sale_date")
    @classmethod
    def date_not_in_future(cls, value: date) -> date:
        "Custom validator: Sale data cannot be in future"
        if value>date.today():
            raise ValueError("Sale data cannot be in future")
        return value
    
    class Config:
        from_attributes=True
        
class RawSaleResponse(BaseModel):
    "Schema for returing a raw sale record from database."
    id:int
    sale_date:date
    product:str
    category:str
    qty:int
    price:float
    status:str
    uploaded_by:int
    created_at:Optional[datetime]
    
    class Config:
        from_attributes = True
        
class ProccessedSaleResponse(BaseModel):
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