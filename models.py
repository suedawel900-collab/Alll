from sqlalchemy import Column, Integer, BigInteger, String, Numeric, ForeignKey, JSON, DateTime
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    username = Column(String)
    balance = Column(Numeric, default=0)

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    game_code = Column(Integer)
    prize_pool = Column(Numeric, default=0)
    status = Column(String, default="waiting")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    numbers = Column(JSON)

class Draw(Base):
    __tablename__ = "draws"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    number_drawn = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    amount = Column(Numeric)
    type = Column(String)