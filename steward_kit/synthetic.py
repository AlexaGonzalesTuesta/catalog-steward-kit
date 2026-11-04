"""Synthetic customer and dealer-service tables.

Real catalogs mix public reference data with tables full of personal data. These two tables
play that role. Every person is fictional: emails use reserved example domains and phone
numbers use the 555-01xx range reserved for fiction. A known number of defects is injected
so the quality checks can be evaluated against ground truth (see defects.json).
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Dict, List, Sequence, Tuple

FIRST = ["Maria", "James", "Aaliyah", "Wei", "Carlos", "Emily", "Jamal", "Sofia", "Daniel", "Grace", "Luis", "Hannah",
         "Omar", "Chloe", "Ethan", "Mei", "Andre", "Olivia", "Rahul", "Zoe", "Diego", "Nora", "Tyler", "Fatima"]
LAST = ["Garcia", "Johnson", "Nguyen", "Smith", "Patel", "Brown", "Lopez", "Kim", "Williams", "Martinez", "Davis",
        "Chen", "Wilson", "Anderson", "Thomas", "Hernandez", "Moore", "Jackson", "Lee", "Walker", "Young", "Allen"]
STREETS = ["Maple", "Oak", "Washington", "Lakeview", "Woodward", "Grand River", "Jefferson", "Cedar", "Park", "Main"]
SUFFIX = ["St", "Ave", "Rd", "Dr", "Ln", "Blvd", "Ct", "Way"]
CITIES = [("Detroit", "MI", "482"), ("Warren", "MI", "480"), ("Troy", "MI", "480"), ("Lansing", "MI", "489"),
          ("Toledo", "OH", "436"), ("Columbus", "OH", "432"), ("Indianapolis", "IN", "462"), ("Fort Wayne", "IN", "468"),
          ("Chicago", "IL", "606"), ("Milwaukee", "WI", "532")]
DOMAINS = ["example.com", "example.net", "example.org"]
DEALERS = [f"D-{n}" for n in (1042, 1187, 2210, 2345, 3018, 3391, 4120, 4477)]
WMI = ["1GC", "1GN", "1GT", "1GK", "5GA", "1GY"]
YEAR_CODE = {2021: "M", 2022: "N", 2023: "P", 2024: "R", 2025: "S"}
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
_TRANSLIT = {**{str(d): d for d in range(10)},
             **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
             **dict(zip("STUVWXYZ", range(2, 10)))}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

DEFECTS = {"duplicate_customer_id": 6, "invalid_email": 12, "invalid_vin": 4,
           "orphan_recall_campaign": 7, "completed_before_appointment": 9, "invalid_status": 5}


def vin_check_digit(vin17: str) -> str:
    total = sum(_TRANSLIT[c] * w for c, w in zip(vin17, _WEIGHTS))
    r = total % 11
    return "X" if r == 10 else str(r)


def is_valid_vin(vin: str) -> bool:
    vin = vin.upper()
    if len(vin) != 17 or any(c not in VIN_CHARS for c in vin):
        return False
    return vin[8] == vin_check_digit(vin)


def make_vin(rng: random.Random) -> str:
    body = rng.choice(WMI) + "".join(rng.choice(VIN_CHARS) for _ in range(5))
    tail = rng.choice(list(YEAR_CODE.values())) + rng.choice("0123456789ABCDEFGH") + "".join(
        rng.choice("0123456789") for _ in range(6))
    draft = body + "0" + tail
    return body + vin_check_digit(draft) + tail


def _phone(rng: random.Random) -> str:
    return f"({rng.choice(['313', '586', '248', '317', '614', '312'])}) 555-01{rng.randint(0, 99):02d}"


def build_owner_contacts(rng: random.Random, n: int = 1200) -> List[Dict[str, str]]:
    rows = []
    start = date(2019, 1, 1)
    for i in range(1, n + 1):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        city, state, zip3 = rng.choice(CITIES)
        rows.append({
            "customer_id": f"C{i:06d}",
            "first_name": first,
            "last_name": last,
            "email": f"{first.lower()}.{last.lower()}{rng.randint(1, 999)}@{rng.choice(DOMAINS)}",
            "phone": _phone(rng),
            "street_address": f"{rng.randint(100, 9899)} {rng.choice(STREETS)} {rng.choice(SUFFIX)}",
            "city": city,
            "state": state,
            "zip": f"{zip3}{rng.randint(1, 99):02d}",
            "vin": make_vin(rng),
            "preferred_dealer": rng.choice(DEALERS),
            "marketing_opt_in": rng.choice(["true", "false"]),
            "created_at": (start + timedelta(days=rng.randint(0, 2400))).isoformat(),
        })
    # Injected defects
    bad_email = rng.sample(range(n), DEFECTS["invalid_email"])
    clean = [i for i in range(n) if i not in bad_email]
    bad_vin = rng.sample(clean, DEFECTS["invalid_vin"])
    clean = [i for i in clean if i not in bad_vin]
    for idx in bad_email:
        rows[idx]["email"] = rng.choice([rows[idx]["email"].replace("@", ""), rows[idx]["email"].split("@")[0] + "@"])
    for idx in bad_vin:
        rows[idx]["vin"] = rows[idx]["vin"][:16] if idx % 2 else rows[idx]["vin"][:10] + "O" + rows[idx]["vin"][11:]
    for idx in rng.sample(clean, DEFECTS["duplicate_customer_id"]):
        dup = dict(rows[idx])
        dup["created_at"] = (date.fromisoformat(dup["created_at"]) + timedelta(days=30)).isoformat()
        rows.append(dup)
    return rows


NOTE_PLAIN = ["Customer reports the issue happens on cold starts.", "Loaner vehicle requested.",
              "Waiting on part from distribution center.", "Customer will drop off the night before.",
              "Second visit for the same concern.", "Recall notice received by mail."]


def build_service_appointments(rng: random.Random, owners: Sequence[Dict[str, str]], campaigns: Sequence[str],
                               n: int = 2000) -> List[Dict[str, str]]:
    rows = []
    start = date(2025, 1, 6)
    valid_vins = [o["vin"] for o in owners if is_valid_vin(o["vin"])]
    for i in range(1, n + 1):
        appt = start + timedelta(days=rng.randint(0, 640))
        kind = rng.choices(["recall_repair", "maintenance", "warranty"], [0.45, 0.4, 0.15])[0]
        status = rng.choices(["completed", "scheduled", "cancelled", "no_show"], [0.7, 0.15, 0.1, 0.05])[0]
        note = rng.choice(NOTE_PLAIN)
        if rng.random() < 0.08:
            note = f"Customer asked to be called at {_phone(rng)} before the visit."
        elif rng.random() < 0.05:
            note = f"Send the repair summary to {rng.choice(FIRST).lower()}@{rng.choice(DOMAINS)}."
        rows.append({
            "appointment_id": f"A{i:07d}",
            "vin": rng.choice(valid_vins),
            "dealer_code": rng.choice(DEALERS),
            "appointment_date": appt.isoformat(),
            "service_type": kind,
            "recall_campaign_number": rng.choice(campaigns) if kind == "recall_repair" and campaigns else "",
            "status": status,
            "completed_at": (appt + timedelta(days=rng.randint(0, 3))).isoformat() if status == "completed" else "",
            "customer_notes": note,
        })
    recall_rows = [i for i, r in enumerate(rows) if r["recall_campaign_number"]]
    for idx in rng.sample(recall_rows, DEFECTS["orphan_recall_campaign"]):
        orphan = ""
        while not orphan or orphan in campaigns:
            orphan = f"{rng.randint(10, 19)}V{rng.randint(100, 999)}000"
        rows[idx]["recall_campaign_number"] = orphan
    done = [i for i, r in enumerate(rows) if r["status"] == "completed"]
    for idx in rng.sample(done, DEFECTS["completed_before_appointment"]):
        rows[idx]["completed_at"] = (date.fromisoformat(rows[idx]["appointment_date"]) - timedelta(days=2)).isoformat()
    others = [i for i in range(n) if rows[i]["status"] != "completed"]
    for idx in rng.sample(others, DEFECTS["invalid_status"]):
        rows[idx]["status"] = rng.choice(["Done", "resched", "CANCELED"])
    return rows


def build(campaigns: Sequence[str], seed: int = 20261104) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    rng = random.Random(seed)
    owners = build_owner_contacts(rng)
    appts = build_service_appointments(rng, owners, sorted(set(campaigns)))
    return owners, appts
