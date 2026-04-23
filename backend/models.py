from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    ai_api_key = Column(String(200), default="")
    ai_base_url = Column(String(200), default="https://yunwu.ai/v1")
    ai_model = Column(String(100), default="gpt-4o")
    email_enabled = Column(Boolean, default=False)
    email_smtp_host = Column(String(100), default="smtp.qq.com")
    email_smtp_port = Column(Integer, default=465)
    email_sender = Column(String(100), default="")
    email_sender_pass = Column(String(200), default="")
    email_receiver = Column(String(200), default="")
    notify_min_confidence = Column(Float, default=0.60)
    initial_capital = Column(Float, default=100000.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="settings")


class Position(Base):
    __tablename__ = "user_positions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    symbol = Column(String(10), nullable=False)
    name = Column(String(50), default="")
    shares = Column(Float, default=0)
    avg_cost = Column(Float, default=0)
    total_cost = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="positions")


class Transaction(Base):
    __tablename__ = "user_transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    symbol = Column(String(10), nullable=False)
    name = Column(String(50), default="")
    action = Column(String(10), nullable=False)  # BUY or SELL
    price = Column(Float, nullable=False)
    shares = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    realized_pnl = Column(Float, default=0)
    realized_pnl_pct = Column(Float, default=0)
    date = Column(String(20), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class StockList(Base):
    __tablename__ = "stock_list"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False, index=True)
    market = Column(String(20), default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
