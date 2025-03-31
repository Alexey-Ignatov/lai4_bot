# database.py
import os
import datetime
from sqlalchemy import create_engine, Column, Integer, Boolean, Float, Date, DateTime, String
from sqlalchemy.orm import sessionmaker, declarative_base

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mydb")
DB_USER = os.getenv("DB_USER", "myuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mypassword")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    """
    Пользователи Telegram, которым будем отправлять запросы.
    """
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255), nullable=True)  # Можете хранить username
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DailyLog(Base):
    """
    Таблица для хранения ежедневных данных о привычках.
    """
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    date_of_entry = Column(Date, default=datetime.date.today)
    bedtime_before_midnight = Column(Boolean, default=False)
    no_gadgets_after_23 = Column(Boolean, default=False)
    followed_diet = Column(Boolean, default=False)
    sport_hours = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    """
    Создание таблиц, если их ещё нет.
    """
    Base.metadata.create_all(engine)

def get_session():
    return SessionLocal()