import os
from pymongo import MongoClient

from dotenv import load_dotenv

# Load .env.local file
load_dotenv(".env.local")

MONGODB_URI = os.environ.get("MONGODB_URI")

if not MONGODB_URI:
    raise Exception(
        f'Please define the MONGODB_URI environment variable inside .env.local {MONGODB_URI}'
    )

_cached_client = None

def connect_to_database():
    global _cached_client
    if _cached_client:
        return _cached_client
    _cached_client = MongoClient(MONGODB_URI)
    print("[OK] Connected to MongoDB")
    return _cached_client

# Usage:
# client = connect_to_database()
# db = client['your_database_name']
