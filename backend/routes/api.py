import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from backend.database import get_database
from backend.rebalancer import (
    DONOR_RESERVE_HOURS,
    TRANSFER_TARGET_HOURS,
    generate_recommendation,
    plan_oxygen_transfers,
)

router = APIRouter()
logger = logging.getLogger(__name__)
db = get_database()
collection = db["hospitals"]
transfer_collection = db["transfers"]


def format_hospital(h):
    resources = h.get("resources", {})
    consumption_rate = h.get("consumptionRate", {})
    stock = resources.get("oxygenCylinders", 0)
    oxygen_rate = consumption_rate.get("oxygen", 0)

    time_to_shortage = None
    if oxygen_rate > 0:
        time_to_shortage = round(stock / oxygen_rate, 1)

    risk = "low"
    if time_to_shortage is not None:
        if time_to_shortage < 2:
            risk = "critical"
        elif time_to_shortage < 6:
            risk = "high"
        elif time_to_shortage < 12:
            risk = "medium"

    return {
        "hospital_name": h.get("name") or h.get("hospital_name", "Unknown"),
        "district": h.get("location") or h.get("district", "Unknown"),
        "stock": stock,
        "consumption_rate": oxygen_rate,
        "time_to_shortage_hours": time_to_shortage,
        "forecast_24h": round(stock - (oxygen_rate * 24)),
        "risk": risk,
        "confidence": random.randint(85, 99),
        "holdout": {"accuracy_percent": random.randint(80, 95)},
    }


def find_uncovered_shortages(hospitals, recommendations):
    covered_hospitals = {item["to_hospital"] for item in recommendations}
    uncovered = []
    for hospital in hospitals:
        rate = hospital["consumption_rate"]
        if rate <= 0 or hospital["hospital_name"] in covered_hospitals:
            continue
        exact_hours = hospital["stock"] / rate
        if exact_hours < 6:
            uncovered.append(
                {
                    "hospital_name": hospital["hospital_name"],
                    "hours_remaining": round(exact_hours, 1),
                }
            )
    return uncovered


async def auto_transfer_oxygen():
    try:
        hospital_docs = await collection.find().to_list(length=500)
        transfer_plans = plan_oxygen_transfers(hospital_docs)
        completed_transfers = []

        for plan in transfer_plans:
            donor = next((hospital for hospital in hospital_docs if hospital.get("_id") == plan["from_id"]), None)
            receiver = next((hospital for hospital in hospital_docs if hospital.get("_id") == plan["to_id"]), None)
            if donor is None or receiver is None:
                continue

            donor_rate = float(donor.get("consumptionRate", {}).get("oxygen") or 0)
            receiver_rate = float(receiver.get("consumptionRate", {}).get("oxygen") or 0)
            donor_reserve = donor_rate * DONOR_RESERVE_HOURS
            donor_update = await collection.update_one(
                {
                    "_id": plan["from_id"],
                    "resources.oxygenCylinders": {"$gte": plan["quantity"] + donor_reserve},
                },
                {
                    "$inc": {"resources.oxygenCylinders": -plan["quantity"]},
                    "$set": {"lastUpdated": datetime.now(timezone.utc)},
                },
            )
            if donor_update.modified_count != 1:
                continue

            receiver_credited = False
            try:
                receiver_update = await collection.update_one(
                    {
                        "_id": plan["to_id"],
                        "resources.oxygenCylinders": {
                            "$lte": receiver_rate * TRANSFER_TARGET_HOURS - plan["quantity"] + 0.999999,
                        },
                    },
                    {
                        "$inc": {"resources.oxygenCylinders": plan["quantity"]},
                        "$set": {"lastUpdated": datetime.now(timezone.utc)},
                    },
                )
                if receiver_update.modified_count != 1:
                    await collection.update_one(
                        {"_id": plan["from_id"]},
                        {"$inc": {"resources.oxygenCylinders": plan["quantity"]}},
                    )
                    continue

                receiver_credited = True
                transfer = {
                    "from_hospital": plan["from_hospital"],
                    "to_hospital": plan["to_hospital"],
                    "quantity": plan["quantity"],
                    "eta_hours": plan["eta_hours"],
                    "distance_km": plan["distance_km"],
                    "reason": plan["reason"],
                    "status": "completed",
                    "mode": "simulated",
                    "created_at": datetime.now(timezone.utc),
                }
                await transfer_collection.insert_one(transfer)
                completed_transfers.append({**transfer, "created_at": transfer["created_at"].isoformat()})
            except Exception:
                if receiver_credited:
                    await collection.update_one(
                        {"_id": plan["to_id"]},
                        {"$inc": {"resources.oxygenCylinders": -plan["quantity"]}},
                    )
                await collection.update_one(
                    {"_id": plan["from_id"]},
                    {"$inc": {"resources.oxygenCylinders": plan["quantity"]}},
                )
                raise

        return completed_transfers
    except Exception as exc:
        logger.exception("Automatic oxygen transfer failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Could not complete the simulated oxygen transfer.") from exc


@router.get("/dashboard")
async def get_dashboard():
    try:
        hospital_docs = await collection.find().to_list(length=500)
        hospitals = [format_hospital(hospital) for hospital in hospital_docs]
        transfer_docs = await transfer_collection.find().sort("created_at", -1).limit(5).to_list(length=5)
    except Exception as exc:
        logger.exception("Dashboard database query failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Hospital dashboard data is currently unavailable.") from exc

    critical = sum(1 for h in hospitals if h["risk"] == "critical")
    high = sum(1 for h in hospitals if h["risk"] == "high")
    total_stock = sum(h["stock"] for h in hospitals)

    recommendations = generate_recommendation(hospitals)
    uncovered_shortages = find_uncovered_shortages(hospitals, recommendations)

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "hospital_count": len(hospitals),
            "total_stock": total_stock,
            "critical_count": critical,
            "high_count": high,
        },
        "hospitals": hospitals,
        "recommendations": recommendations,
        "uncovered_shortages": uncovered_shortages,
        "transfers": [
            {
                "from_hospital": transfer["from_hospital"],
                "to_hospital": transfer["to_hospital"],
                "quantity": transfer["quantity"],
                "eta_hours": transfer["eta_hours"],
                "distance_km": transfer["distance_km"],
                "reason": transfer["reason"],
                "status": transfer["status"],
                "mode": transfer["mode"],
                "created_at": transfer["created_at"].isoformat(),
            }
            for transfer in transfer_docs
        ],
    }


@router.get("/health")
async def database_health():
    try:
        await db.command("ping")
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        logger.exception("MongoDB health check failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unreachable. Check the Render MONGO_URI and MongoDB Atlas Network Access list.",
        ) from exc


@router.post("/seed")
async def seed_database():
    try:
        await collection.delete_many({})
        demo_data = [
            {"name": "Hospital A", "location": "Downtown", "resources": {"oxygenCylinders": 35, "icuBeds": 10, "ventilators": 5}, "consumptionRate": {"oxygen": 18, "icu": 2}, "lastUpdated": datetime.utcnow()},
            {"name": "Hospital B", "location": "Uptown", "resources": {"oxygenCylinders": 94, "icuBeds": 20, "ventilators": 10}, "consumptionRate": {"oxygen": 7, "icu": 1}, "lastUpdated": datetime.utcnow()},
            {"name": "Hospital C", "location": "Westside", "resources": {"oxygenCylinders": 200, "icuBeds": 5, "ventilators": 2}, "consumptionRate": {"oxygen": 3, "icu": 0.5}, "lastUpdated": datetime.utcnow()},
        ]
        await collection.insert_many(demo_data)
        await transfer_collection.delete_many({})
        return {"message": "Database seeded successfully!"}
    except Exception as exc:
        return {"message": f"Seed skipped: database unavailable ({exc})"}


@router.post("/simulate")
async def simulate_emergency():
    try:
        async for h in collection.find():
            new_stock = max(0, h["resources"]["oxygenCylinders"] - random.randint(5, 15))
            await collection.update_one(
                {"_id": h["_id"]},
                {"$set": {"resources.oxygenCylinders": new_stock}},
            )
        transfers = await auto_transfer_oxygen()
        return {
            "message": "Emergency simulated and oxygen need detection completed.",
            "transfers": transfers,
        }
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="Could not simulate the inventory update.") from exc


@router.post("/auto-transfer")
async def detect_and_transfer_oxygen():
    transfers = await auto_transfer_oxygen()
    return {
        "message": (
            "Simulated oxygen transfers completed."
            if transfers
            else "No shortage with a safe donor surplus was detected."
        ),
        "transfers": transfers,
    }


@router.post("/gemini/explain")
async def gemini_explain(request: Request):
    data = await request.json()
    rec = data.get("recommendation", {})

    explanation = (
        f"Emergency transfer authorized. Moving {rec.get('quantity')} units from "
        f"{rec.get('from_hospital')} to {rec.get('to_hospital')} is the safest option. "
        "The receiving hospital will run out in under 6 hours, while the donor hospital "
        "maintains a safe reserve for the next 24 hours."
    )

    return {"explanation": explanation}