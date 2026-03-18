from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

load_dotenv()  # reads MONGODB_URL and DATABASE_NAME from your .env file

MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "med_reconciliation")

if not MONGODB_URL:
    raise ValueError("MONGODB_URL is not set in your .env file")

# These are module-level variables.
# They start as None and get populated when connect_db() is called at startup.
client: AsyncIOMotorClient = None
db = None


async def connect_db():
    global client, db

    # ServerApi("1") pins the driver to MongoDB Server API version 1.
    # This is required by Atlas to ensure stable behaviour.
    client = AsyncIOMotorClient(
        MONGODB_URL,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=10000,  # wait up to 10s to find a server
        connectTimeoutMS=10000,          # wait up to 10s per connection attempt
        tls=True,                        # Atlas always requires TLS
        tlsAllowInvalidCertificates=True # avoids SSL cert errors locally
    )

    db = client[DATABASE_NAME]

    # Ping the database to confirm the connection actually works
    # This will raise an exception immediately if credentials are wrong
    await client.admin.command("ping")
    print(f"✓ Successfully connected to MongoDB Atlas: {DATABASE_NAME}")

    await create_indexes()


async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB Atlas connection closed")


async def create_indexes():
    """
    Indexes are like a book's index — they let MongoDB find documents
    fast without scanning every record.

    Why these specific indexes?
    - patients:  patient_id is our main lookup key → unique index
    - snapshots: we always query by patient+source+version → compound index
    - conflicts: reporting queries filter by clinic_id + status → compound index
    """

    # patients collection indexes
    await db.patients.create_indexes([
        IndexModel([("patient_id", ASCENDING)], unique=True),
        IndexModel([("clinic_id", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ])

    # snapshots collection indexes
    await db.snapshots.create_indexes([
        IndexModel([("patient_id", ASCENDING), ("version", DESCENDING)]),
        IndexModel([("patient_id", ASCENDING), ("source", ASCENDING)]),
        IndexModel([("ingested_at", DESCENDING)]),
        IndexModel([("clinic_id", ASCENDING)]),
    ])

    # conflicts collection indexes
    await db.conflicts.create_indexes([
        IndexModel([("patient_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("patient_id", ASCENDING), ("detected_at", DESCENDING)]),
        IndexModel([("clinic_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("detected_at", DESCENDING)]),
        # This compound index covers the 30-day aggregation report entirely
        # in a single index scan — no extra work needed at query time
        IndexModel([
            ("clinic_id", ASCENDING),
            ("detected_at", DESCENDING),
            ("status", ASCENDING),
        ]),
    ])

    print("✓ All MongoDB indexes created")


def get_db():
    """Called by services to get the active database handle."""
    return db


## Change 3 — `requirements.txt`