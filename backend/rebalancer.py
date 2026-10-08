import math
import os
import random


SHORTAGE_THRESHOLD_HOURS = float(os.getenv("SHORTAGE_THRESHOLD_HOURS", "6"))
DONOR_RESERVE_HOURS = float(os.getenv("SAFETY_HOURS", "12"))
TRANSFER_TARGET_HOURS = float(os.getenv("TRANSFER_TARGET_HOURS", "6"))


def _get_name(hospital):
    return hospital.get("hospital_name") or hospital.get("name") or "Unknown"


def _get_stock(hospital):
    if "stock" in hospital:
        return float(hospital.get("stock") or 0)

    resources = hospital.get("resources", {})
    return float(resources.get("oxygenCylinders") or 0)


def _get_consumption_rate(hospital):
    if "consumption_rate" in hospital:
        return float(hospital.get("consumption_rate") or 0)

    consumption_rate = hospital.get("consumptionRate", {})
    return float(consumption_rate.get("oxygen") or 0)


def calculate_time_to_shortage(current_stock, consumption_rate_per_hour):
    if consumption_rate_per_hour <= 0:
        return None
    return round(current_stock / consumption_rate_per_hour, 1)


def _exact_time_to_shortage(current_stock, consumption_rate_per_hour):
    if consumption_rate_per_hour <= 0:
        return None
    return current_stock / consumption_rate_per_hour


def plan_oxygen_transfers(
    hospitals,
    shortage_threshold_hours=SHORTAGE_THRESHOLD_HOURS,
    donor_reserve_hours=DONOR_RESERVE_HOURS,
    transfer_target_hours=TRANSFER_TARGET_HOURS,
):
    """Plan whole-cylinder transfers while preserving each donor's safety reserve."""
    stock_by_id = {}
    id_by_object = {}
    for index, hospital in enumerate(hospitals):
        hospital_id = hospital.get("_id", index)
        id_by_object[id(hospital)] = hospital_id
        stock_by_id[hospital_id] = max(0, _get_stock(hospital))

    receivers = sorted(
        hospitals,
        key=lambda hospital: (
            _exact_time_to_shortage(
                stock_by_id[id_by_object[id(hospital)]],
                _get_consumption_rate(hospital),
            )
            if _get_consumption_rate(hospital) > 0
            else float("inf")
        ),
    )
    plans = []

    for receiver in receivers:
        receiver_id = id_by_object[id(receiver)]
        receiver_rate = _get_consumption_rate(receiver)
        receiver_stock = stock_by_id[receiver_id]
        shortage_hours = _exact_time_to_shortage(receiver_stock, receiver_rate)
        if shortage_hours is None or shortage_hours >= shortage_threshold_hours:
            continue

        eligible_donors = []
        for donor in hospitals:
            donor_id = id_by_object[id(donor)]
            if donor_id == receiver_id:
                continue

            donor_rate = _get_consumption_rate(donor)
            donor_stock = stock_by_id[donor_id]
            safe_reserve = donor_rate * donor_reserve_hours
            surplus = donor_stock - safe_reserve
            if surplus >= 1:
                eligible_donors.append((surplus, donor))

        eligible_donors.sort(key=lambda item: item[0], reverse=True)
        for surplus, donor in eligible_donors:
            donor_id = id_by_object[id(donor)]
            target_stock = receiver_rate * transfer_target_hours
            deficit = max(0, target_stock - receiver_stock)
            quantity = min(int(surplus), math.ceil(deficit))
            if quantity <= 0:
                break

            donor_stock = stock_by_id[donor_id]
            donor_name = _get_name(donor)
            receiver_name = _get_name(receiver)
            plans.append(
                {
                    "priority": len(plans) + 1,
                    "from_hospital": donor_name,
                    "to_hospital": receiver_name,
                    "quantity": quantity,
                    "from_id": donor_id,
                    "to_id": receiver_id,
                    "distance_km": round(random.uniform(2.0, 15.0), 1),
                    "eta_hours": round(random.uniform(0.5, 1.5), 1),
                    "reason": (
                        f"{receiver_name} has about {shortage_hours:.1f} hours of oxygen "
                        f"remaining; {donor_name} can spare {quantity} cylinders while "
                        f"keeping a {donor_reserve_hours}-hour reserve."
                    ),
                }
            )
            stock_by_id[donor_id] = donor_stock - quantity
            stock_by_id[receiver_id] = receiver_stock + quantity
            break

    return plans


def generate_recommendation(hospitals):
    return [
        {key: value for key, value in plan.items() if key not in {"from_id", "to_id"}}
        for plan in plan_oxygen_transfers(hospitals)
    ]