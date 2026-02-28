import os
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, ForeignKey, DateTime, Numeric
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# =========================
# DATABASE CONNECTION
# =========================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set!")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =========================
# USERS TABLE
# =========================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    balance = Column(Numeric(10, 2), default=0)
    total_wins = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    cards = relationship("CardPurchase", back_populates="user")

# =========================
# ROUNDS TABLE
# =========================

class Round(Base):
    __tablename__ = "rounds"

    id = Column(Integer, primary_key=True)
    round_number = Column(Integer, unique=True)
    is_active = Column(Boolean, default=True)
    total_pool = Column(Numeric(10, 2), default=0)
    winner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

# =========================
# BINGO CARDS (1000 PER ROUND)
# =========================

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True)
    card_number = Column(Integer)  # 1–1000
    round_id = Column(Integer, ForeignKey("rounds.id"))
    is_taken = Column(Boolean, default=False)

# =========================
# CARD PURCHASES
# =========================

class CardPurchase(Base):
    __tablename__ = "card_purchases"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    card_id = Column(Integer, ForeignKey("cards.id"))
    round_id = Column(Integer, ForeignKey("rounds.id"))
    purchased_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cards")

# =========================
# HOUSE COMMISSION TRACKING
# =========================

class HouseCommission(Base):
    __tablename__ = "house_commission"

    id = Column(Integer, primary_key=True)
    round_id = Column(Integer)
    amount = Column(Numeric(10, 2))
    created_at = Column(DateTime, default=datetime.utcnow)

# =========================
# CREATE TABLES
# =========================

def init_db():
    Base.metadata.create_all(bind=engine)