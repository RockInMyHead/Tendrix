from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, Text, DateTime, Index
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

SQLALCHEMY_DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    telegram_id = Column(Integer, nullable=True, unique=True, index=True)
    telegram_connect_code = Column(String, nullable=True, index=True)
    is_pro = Column(Boolean, default=False)
    company_description = Column(Text, nullable=True)
    company_description_last_saved = Column(DateTime, nullable=True)
    email = Column(String, nullable=True)
    email_verified = Column(Boolean, default=False)
    email_verification_token = Column(String, nullable=True, index=True)

class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, unique=True, index=True)
    subject = Column(Text)
    price = Column(Float, nullable=True)
    currency = Column(String, nullable=True)
    update_date = Column(String, nullable=True)
    stage = Column(String, nullable=True)
    customer = Column(String, index=True)
    supplier = Column(String, nullable=True)
    region = Column(String, nullable=True)
    procurement_type = Column(String, nullable=True)
    link = Column(String)
    published_at = Column(DateTime, default=datetime.utcnow)
    
    # Store AI analysis results to avoid re-calculating
    relevance_score = Column(Integer, nullable=True)
    relevance_reason = Column(Text, nullable=True)
    pitfalls = Column(Text, nullable=True)
    tg_notified_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_tenders_region", "region"),
        Index("ix_tenders_procurement_type", "procurement_type"),
        Index("ix_tenders_stage", "stage"),
        Index("ix_tenders_price", "price"),
    )

class PromoCode(Base):
    __tablename__ = "promocodes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    description = Column(String, nullable=True)

def init_db():
    Base.metadata.create_all(bind=engine)
