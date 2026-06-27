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
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKE_EXPIRE_MINUTES","60"))

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
        expire = datetime.time(timezone.utc) + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp":expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token:str)->Optional[dict]:
    """
    Decodes and validates a JWT token
    """
    try:
        payload = jwt.encode(token, SECRET_KEY, algorithm=[ALGORITHM])
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

def current_admin(current_user:User = Depends(get_current_user))->User:
    if current_user.role!="admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user