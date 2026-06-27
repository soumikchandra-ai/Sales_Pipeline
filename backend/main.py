from fastapi import FastAPI, Depends, HTTPException, status
from backend.database import engine,Base, get_db
import backend.models
from sqlalchemy.orm import Session
from datetime import timedelta
from backend.models import User
from backend.schemas import UserRegisterSchema, UserLoginSchema, TokenResponseSchema, UserResponseSchema
from backend.auth import hash_password, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user

app=FastAPI(
    title="Sales pipeline API",
    description="Backend API for Sales Data Pipeline Dashboard",
    version="1.0.0"
)

Base.metadata.create_all(bind=engine)

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
    role = user_data.role if user_data.role not in allowed_roles else "viewer"
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
            headers={"WWW-Authenticate":"Bearers"}
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
    
@app.get("auth/me",tags=["Auth"])
def get_me(current_user:User = Depends(get_current_user)):
    """
    Return info about the currently logged in User
    """
    return UserResponseSchema.model_validate(current_user)
