#To validate the incoming request and the outgoing response
from pydantic import BaseModel, Field
from typing import Optional

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