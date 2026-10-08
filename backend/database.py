import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI") or "mongodb://localhost:27017"
DB_NAME = os.getenv("DB_NAME", "hospital_rebalancer")

client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=2000)
db = client[DB_NAME]


def get_database():
    return db