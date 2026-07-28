"""Fleet Map — vehicle GPS positions.

Self-contained and self-seeding: the ``fleet_vehicle_location`` table is created
on demand and, if empty, seeded with a realistic UK fleet so the Fleet Map is
never blank in a demo or a fresh environment. No Claims imports and no hard
Alembic dependency, so it is safe to call on any DB state.
"""
import logging
import random
from datetime import date, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from fleet.models.tables import FleetVehicleLocation
from libdata.settings import engine

logger = logging.getLogger(__name__)

# Depots (home bases) and repair garages, spread across the UK.
_DEPOTS = [
    ("Birmingham Depot", 52.4862, -1.8904),
    ("Manchester Depot", 53.4808, -2.2426),
    ("London Depot", 51.5074, -0.1278),
    ("Leeds Depot", 53.8008, -1.5491),
    ("Bristol Depot", 51.4545, -2.5879),
    ("Glasgow Depot", 55.8642, -4.2518),
]
_GARAGES = [
    ("AutoFix Birmingham", 52.470, -1.870),
    ("QuickService Manchester", 53.470, -2.250),
    ("PitStop London", 51.500, -0.120),
]
_ROADS = ["M42 Southbound", "M6 Junction 7", "A38 Bristol Road", "M62 Eastbound", "M1 Junction 23", "A34 Bypass"]
_MODELS = [
    ("BMW", "3 Series"), ("Audi", "A4"), ("Mercedes-Benz", "C-Class"), ("Vauxhall", "Astra"),
    ("Tesla", "Model 3"), ("Ford", "Focus"), ("Volkswagen", "Golf"), ("Toyota", "Corolla"),
    ("Nissan", "Qashqai"), ("Kia", "Sportage"), ("Ford", "Transit Custom"), ("Mercedes-Benz", "Vito"),
]
_DRIVERS = [
    "John Smith", "Aisha Khan", "Michael O'Connor", "Fiona Campbell", "Daniel Evans", "Grace Robinson",
    "Harun Ali", "Priya Sharma", "Thomas Baker", "Sarah Lewis", "David Wright", "Chloe Murphy",
]
_LETTERS = "ABCDEFGHJKLMNOPRSTUVWXYZ"


def _reg(rnd: random.Random) -> str:
    a = "".join(rnd.choice(_LETTERS) for _ in range(2))
    n = rnd.randint(10, 74)
    b = "".join(rnd.choice(_LETTERS) for _ in range(3))
    return f"{a}{n} {b}"


def _generate_fleet() -> List[dict]:
    """Deterministic demo fleet (~32 vehicles) across depots + statuses."""
    rnd = random.Random(42)
    # Totals mirror the demo mockup: 28 + 45 + 16 + 4 + 4 + 2 = 99 vehicles.
    statuses = (
        ["Available"] * 28 + ["On Hire"] * 45 + ["In Repair"] * 16
        + ["Breakdown"] * 4 + ["Reserved"] * 4 + ["Off Fleet"] * 2
    )
    rnd.shuffle(statuses)
    today = date.today()
    rows: List[dict] = []
    for i, status in enumerate(statuses):
        depot_name, dlat, dlng = _DEPOTS[i % len(_DEPOTS)]
        make, model = _MODELS[i % len(_MODELS)]
        on_hire = status == "On Hire"

        if status == "In Repair":
            loc_name, blat, blng = _GARAGES[i % len(_GARAGES)]
        elif status == "Breakdown":
            loc_name, blat, blng = rnd.choice(_ROADS), dlat, dlng
        elif on_hire:
            loc_name, blat, blng = depot_name.replace(" Depot", "") + " area", dlat, dlng
        else:
            loc_name, blat, blng = depot_name, dlat, dlng

        rows.append({
            "registration": _reg(rnd),
            "make": make,
            "model": model,
            "status": status,
            "driver_name": rnd.choice(_DRIVERS) if on_hire else None,
            "latitude": round(blat + rnd.uniform(-0.16, 0.16), 4),
            "longitude": round(blng + rnd.uniform(-0.22, 0.22), 4),
            "speed_mph": rnd.choice([24, 28, 32, 36, 41, 46, 52]) if on_hire else 0,
            "heading": rnd.randrange(0, 360) if on_hire else 0,
            "location_label": loc_name,
            "depot": depot_name,
            "mileage": rnd.randint(8, 120) * 1000 + rnd.randint(0, 999),
            "plate_expiry": today + timedelta(days=rnd.randint(-30, 720)),
            "mot_expiry": today + timedelta(days=rnd.randint(-20, 640)),
        })
    return rows


def _ensure_table() -> None:
    """Create the table if it does not exist yet (safe / idempotent)."""
    FleetVehicleLocation.__table__.create(bind=engine, checkfirst=True)


def _seed_demo(db: Session, tenant_id: Optional[int]) -> None:
    """Seed (or re-seed) the demo fleet. This table is demo data only, so if the
    row count doesn't match the current demo set we replace it — that way tweaks
    to the seed (e.g. growing the fleet) take effect on the next load."""
    rows = _generate_fleet()
    if db.query(FleetVehicleLocation).count() == len(rows):
        return
    db.query(FleetVehicleLocation).delete()
    for row in rows:
        db.add(FleetVehicleLocation(tenant_id=tenant_id, **row))
    db.commit()
    logger.info("Seeded %s fleet map vehicle locations.", len(rows))


def list_vehicle_locations(db: Session, tenant_id: Optional[int] = None) -> List[FleetVehicleLocation]:
    """All vehicle positions for the Fleet Map (seeds demo data on first call)."""
    _ensure_table()
    _seed_demo(db, tenant_id)
    return (
        db.query(FleetVehicleLocation)
        .order_by(FleetVehicleLocation.registration)
        .all()
    )
