import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import declarative_base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/sales.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread":False}    #Uses multiple threads to work with SQLite
)

SessionLocal = sessionmaker(
    autocommit=False,   #Manually control when data is saved
    autoflush=False,    #Manually control when changes are sent to DB
    bind=engine         #Link the session to the engine
)

Base = declarative_base()   #Parent class from which all database models inherit from

def get_db():
    """
    This is a fastapi dependency function.
    It creates a new session for each incoming request,
    give it to the route handler and closes it when it's done.
    """
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()