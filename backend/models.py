from datetime import datetime,timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey
)
from sqlalchemy.orm import relationship
from backend.database import Base

#Table 1: Stores the information of everyone who can log into the app
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="viewer")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    sales = relationship("RawSale", back_populates="uploader")
    
    def __repr__(self):
        return f"User(id={self.id}, username='{self.username}', role='{self.role}')"
    
#Table 2: Stores raw/unprocessed sales data uploaded by users
class RawSale(Base):
    __tablename__ = "raw_sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False)
    product = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    
    uploader = relationship("User", back_populates="sales")
    processed = relationship("ProcessedSale", back_populates="raw_sales", uselist=False)
    
    def __repr__(self):
        return f"RawSale(id={self.id}, product='{self.product}', status='{self.status}')"

#Table 3: Stores calculated and transformed values from RawSales
class ProcessedSale(Base):
    __tablename__ = "processed_sales"
    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_id = Column(Integer, ForeignKey("raw_sales.id"), nullable=False, unique=True)
    total = Column(Float, nullable=False)           #qty*price
    tax = Column(Float, nullable=False, default=0.0)
    discount = Column(Float, nullable=False, default=True)
    final_amount= Column(Float, nullable=False)     #total+tax-discount
    processed_at = Column(Float, default=datetime.now(timezone.utc))
    
    raw_sale = relationship("RawSale",  back_populates="processed_sales")
    
    def __repr__(self):
        return f"ProcessedSale(id={self.id}, raw_id={self.raw_id}, final_amount={self.final_amount})"