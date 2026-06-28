#Pre-fills the Database with default users
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.database import SessionLocal, engine, Base
import backend.models
from backend.models import User
from backend.auth import hash_password

DEFAULT_USERS = [
    {
        "username":"admin1",
        "password":"admin1234",
        "role":"admin"
    },
    {
        "username":"viewer1",
        "password":"viewer1234",
        "role":"viewer"
    }
]

def seed_users(db):
    "Creates default users if they don't already exists."
    
    for user_data in DEFAULT_USERS:
        existing = db.query(User).filter(
            User.username == user_data["username"]
        ).first()
        
        if existing:
            print(f"Skipping '{user_data["username"]}' - already exists with role as '{existing.role}'")
            continue
        
        new_user = User(
            username=user_data["username"],
            password_hash=hash_password(user_data["password"]),
            role=user_data["role"]
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        print(f"Created user with '{new_user.username}' with role '{new_user.role} with id as {new_user.id}'")
        
def main():
    "Main function - runs all seed operations."
    print("Starting database seed")
    
    Base.metadata.create_all(bind=engine)
    print("Tables created/verified")
    
    db=SessionLocal()
    
    try:
        seed_users(db)
        print("Seed created! You can now log in with your username and password")
        
    except Exception as e:
        print(f"Seed failed with exception: {e}")
        db.rollback()
    
    finally:
        db.close()
        
if __name__=="__main__":
    main()