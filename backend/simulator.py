import os
import random
from datetime import datetime, timezone

RESOURCE = os.getenv("RESOURCE", "oxygen_cylinders")

HOSPITALS = [
    {"id": "H01", "name": "Hospital A", "district": "Central", "lat": 13.0827, "lng": 80.2707},
    {"id": "H02", "name": "Hospital B", "district": "Central", "lat": 13.0674, "lng": 80.2376},
    {"id": "H03", "name": "Hospital C", "district": "Central", "lat": 13.0604, "lng": 80.2496},
    {"id": "H04", "name": "Hospital D", "district": "Central", "lat": 13.1067, "lng": 80.2206},
    {"id": "H05", "name": "Hospital E", "district": "Central", "lat": 13.0418, "lng": 80.2341},
    {"id": "H06", "name": "Hospital F", "district": "Central", "lat": 13.1143, "lng": 80.2930},
]

# Different depletion rates make the simulation meaningful.
BASE = {
    "H01": {"stock": 70, "rate": 5.0, "capacity": 100},
    "H02": {"stock": 115, "rate": 1.2, "capacity": 140},
    "H03": {"stock": 82, "rate": 2.0, "capacity": 120},
    "H04": {"stock": 52, "rate": 3.8, "capacity": 90},
    "H05": {"stock": 96, "rate": 0.7, "capacity": 120},
    "H06": {"stock": 65, "rate": 2.7, "capacity": 100},
}


def seed_if_empty(collection):
    if collection is None:
        return []
    if collection.count_documents({}) > 0:
        return list(collection.find().sort("timestamp", 1).limit(500))

    timestamp = datetime.now(timezone.utc)
    docs = []
    for hospital in HOSPITALS:
        b = BASE[hospital["id"]]
        docs.append({
            "timestamp": timestamp,
            "hospital_id": hospital["id"],
            "hospital_name": hospital["name"],
            "district": hospital["district"],
            "lat": hospital["lat"],
            "lng": hospital["lng"],
            "resource": RESOURCE,
            "stock": b["stock"],
            "capacity": b["capacity"],
            "consumption_rate": b["rate"],
            "units": "cylinders",
        })
    collection.insert_many(docs)
    return docs


def generate_next_snapshot(collection):
    latest = {}
    for d in collection.find().sort("timestamp", -1).limit(100):
        if d["hospital_id"] not in latest:
            latest[d["hospital_id"]] = d

    now = datetime.now(timezone.utc)
    docs = []

    for hospital in HOSPITALS:
        hid = hospital["id"]
        old = latest.get(hid)
        b = BASE[hid]

        if old:
            rate = max(0.2, float(old.get("consumption_rate", b["rate"])) + random.uniform(-0.25, 0.25))
            # Simulate a 5-minute observation interval.
            new_stock = max(0, round(float(old["stock"]) - rate * 5 / 60, 2))
        else:
            rate = b["rate"]
            new_stock = b["stock"]

        doc = {
            "timestamp": now,
            "hospital_id": hid,
            "hospital_name": hospital["name"],
            "district": hospital["district"],
            "lat": hospital["lat"],
            "lng": hospital["lng"],
            "resource": RESOURCE,
            "stock": new_stock,
            "capacity": b["capacity"],
            "consumption_rate": round(rate, 2),
            "units": "cylinders",
        }
        docs.append(doc)

    collection.insert_many(docs)
    return docs
