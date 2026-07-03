import os
from datetime import datetime,time,timedelta,timezone
from typing import Optional
from dotenv import load_dotenv
import bcrypt
from jose import jwt,JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY","fallback-secret-key-not-for-production")
ALGORITHM = os.getenv("ALGORITHM","HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES","60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(password:str)->str:
    """
    Takes a plain text password and return a bcrypt hash.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes,salt)
    
    #Store the hashed password in the Databse
    return hashed.decode("utf-8")

def verify_password(plain_password:str, hashed_password:str)->bool:
    """
    Checks if the hashed password exists in the Database or not
    """
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    
    return bcrypt.checkpw(plain_bytes,hashed_bytes)

def create_access_token(data:dict, expires_delta:Optional[timedelta]=None)->str:
    """
    Creates the JWT token containing the provided data
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp":expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token:str)->Optional[dict]:
    """
    Decodes and validates a JWT token
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
    
def get_current_user(token:str= Depends(oauth2_scheme), db: Session = Depends(get_db))->User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate":"Bearer"}
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.username==username).first()
    if user is None:
        raise credentials_exception
    
    return user

def require_role(required_role:str):
    """
    Dependency Factory : A function that returns another function.
    How it works:
        require_role("admin")-> returns a function that only lets admins through
        require_role("viewer")-> returns a function that only lets viewers through
    """
    
    def role_checker(current_user:User = Depends(get_current_user))->User:
        """
        The dependency function returned by require_role
        """
        ROLE_HIERARCHY ={
            "viewer":["viewer","admin"], #viewer route allows both viewer and admin users
            "admin":["admin"]            #admin route allows only admin users
        }
        
        allowed_roles = ROLE_HIERARCHY.get(required_role,[required_role])
        
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Access Denied. This role requires role: '{required_role}'. Your role is '{current_user.role}'")
            )
        
        return current_user
    return role_checker

require_admin = Depends(require_role("admin"))
require_viewer = Depends(require_role("viewer"))