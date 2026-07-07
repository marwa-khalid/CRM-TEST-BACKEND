"""Seed dummy claims + hire/payment data so the dashboard charts have something
pretty to show. Spread across ~5 years (random years/months/weeks/days) with a
mild recency growth curve. Tenant-scoped to the dashboard's tenant.

Every seeded claim is stamped screen_completion={"_demo_seed": true} so it can be
removed later:  python scripts/seed_dashboard_demo.py --clean

Usage:
  PYTHONPATH=src .venv/bin/python scripts/seed_dashboard_demo.py [N]         # seed N claims (default 650)
  PYTHONPATH=src .venv/bin/python scripts/seed_dashboard_demo.py --clean     # delete all seeded rows
"""
import os
import sys
import random
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:demo123@localhost:5432/DBClaimCRM")

sys.path.insert(0, "src")
from sqlalchemy import text
from libdata.settings import get_session
from libdata.models.tables import (
    Claim, Referrer, HireDetail, HireVehicleProvided,
    HirePaymentDetails, Storage, Recovery, EngineerDetail, ClientDetail,
)
from libdata.enums import PersonRoleEnum

FIRST_NAMES = [
    "James", "Sarah", "Mohammed", "Emily", "David", "Aisha", "Daniel", "Priya",
    "Thomas", "Olivia", "Michael", "Fatima", "Robert", "Sophie", "John", "Amara",
    "William", "Hannah", "Ali", "Grace", "Charlie", "Zara", "George", "Chloe",
    "Harry", "Leila", "Jack", "Maya", "Oliver", "Nadia",
]
SURNAMES = [
    "Smith", "Khan", "Patel", "Jones", "Williams", "Ahmed", "Brown", "Taylor",
    "Wilson", "Begum", "Evans", "Roberts", "Hussain", "Walker", "Wright",
    "Choudhury", "Green", "Baker", "Ali", "Cooper", "Ward", "Malik", "Turner",
    "Hughes", "Shah", "Edwards", "Rana", "Collins", "Iqbal", "Murphy",
]

TENANT_ID = 36
USER_ID = 38
ON_HIRE, OFF_HIRE = 1, 2
STATUS_WEIGHTS = [  # (case_status_id, weight)
    (6, 34),  # Completed
    (1, 24),  # Accepted
    (5, 16),  # Pending
    (2, 12),  # TBC
    (3, 8),   # Rejected
    (4, 6),   # Cancelled
]
REFERRERS = [
    "Swift Accident Management", "Prime Claims Ltd", "CityWide Recovery",
    "Apex Legal Referrals", "Metro Motor Assist", "Guardian Claims",
    "Direct Hire Partners", "Nationwide Brokers", "Elite Accident Care",
    "Regional Solicitors LLP",
]
VEHICLES = [
    ("Toyota", "Prius"), ("Ford", "Focus"), ("BMW", "320d"), ("VW", "Golf"),
    ("Mercedes", "C220"), ("Audi", "A4"), ("Vauxhall", "Insignia"),
    ("Nissan", "Qashqai"), ("Hyundai", "i30"), ("Skoda", "Octavia"),
]


def _weighted_status():
    r = random.uniform(0, sum(w for _, w in STATUS_WEIGHTS))
    upto = 0
    for sid, w in STATUS_WEIGHTS:
        upto += w
        if r <= upto:
            return sid
    return 6


def _reg():
    import string
    return (
        "".join(random.choices(string.ascii_uppercase, k=2))
        + str(random.randint(10, 69))
        + " "
        + "".join(random.choices(string.ascii_uppercase, k=3))
    )


def clean(db):
    ids = [r[0] for r in db.execute(text(
        "SELECT id FROM claims WHERE screen_completion->>'_demo_seed' = 'true'"
    )).fetchall()]
    if not ids:
        print("No seeded claims found.")
        return
    for tbl in ("hire_details", "hire_vehicle_provides", "hire_payment_details",
                "referrers", "storages", "recoveries", "engineer_details",
                "client_details"):
        db.execute(text(f"DELETE FROM {tbl} WHERE claim_id = ANY(:ids)"), {"ids": ids})
    db.execute(text("DELETE FROM claims WHERE id = ANY(:ids)"), {"ids": ids})
    db.commit()
    print(f"Deleted {len(ids)} seeded claims and their related rows.")


def backfill_names(db):
    """Add a CLIENT ClientDetail (name) to any seeded claim that lacks one."""
    ids = [r[0] for r in db.execute(text(
        "SELECT c.id FROM claims c "
        "WHERE c.screen_completion->>'_demo_seed' = 'true' "
        "AND NOT EXISTS (SELECT 1 FROM client_details d "
        "               WHERE d.claim_id = c.id AND d.role = 'CLIENT' AND d.is_deleted IS NOT TRUE)"
    )).fetchall()]
    now = datetime.now(timezone.utc)
    for i, cid in enumerate(ids):
        db.add(ClientDetail(
            tenant_id=TENANT_ID, claim_id=cid, role=PersonRoleEnum.CLIENT,
            first_name=random.choice(FIRST_NAMES), surname=random.choice(SURNAMES),
            is_active=True, is_deleted=False,
            created_by=USER_ID, updated_by=USER_ID, created_at=now, updated_at=now,
        ))
        if (i + 1) % 200 == 0:
            db.commit()
    db.commit()
    print(f"Added client names to {len(ids)} seeded claims.")


def seed(db, n, max_days=5 * 365, recent=False):
    now = datetime.now(timezone.utc)
    window_days = max_days
    created = 0
    for i in range(n):
        if recent:
            # Uniform across the recent window (fills WTD / MTD cards for demos).
            offset = random.randint(0, window_days)
        else:
            # Mild recency bias so recent years have more claims (nice growth
            # trend), but the whole 5-year window is covered.
            offset = int(window_days * (random.random() ** 1.25))
        opened = now - timedelta(
            days=offset, hours=random.randint(0, 23), minutes=random.randint(0, 59)
        )
        make, model = random.choice(VEHICLES)

        claim = Claim(
            tenant_id=TENANT_ID,
            case_status_id=_weighted_status(),
            source_id=random.randint(1, 5),
            claim_type_id=random.choice([1, 2, None]),
            credit_hire_accepted=random.random() < 0.7,
            non_fault_accident=random.choice(["YES", "NO", "TBC"]),
            any_passengers=random.choice(["YES", "NO"]),
            file_opened_at=opened,
            screen_completion={"_demo_seed": True},
            is_active=True,
            is_deleted=False,
            created_by=USER_ID,
            updated_by=USER_ID,
            created_at=opened,
            updated_at=opened,
        )
        db.add(claim)
        db.flush()  # get claim.id

        # Referrer (drives the trend Referrer filter)
        db.add(Referrer(
            tenant_id=TENANT_ID, claim_id=claim.id,
            company_name=random.choice(REFERRERS), is_active=True,
            created_by=USER_ID, updated_by=USER_ID,
            created_at=opened, updated_at=opened,
        ))

        # Client (name shown on the claim listing / cards)
        db.add(ClientDetail(
            tenant_id=TENANT_ID, claim_id=claim.id,
            role=PersonRoleEnum.CLIENT,
            first_name=random.choice(FIRST_NAMES),
            surname=random.choice(SURNAMES),
            is_active=True, is_deleted=False,
            created_by=USER_ID, updated_by=USER_ID,
            created_at=opened, updated_at=opened,
        ))

        # ~78% of claims have a hire vehicle
        if random.random() < 0.78:
            abi_rate = round(random.uniform(45, 135), 2)
            admin_fee = round(random.uniform(25, 85), 2)
            # Hire starts on/after the file opens, never in the future.
            hire_out = min(opened + timedelta(days=random.randint(0, 3)), now)
            start_d = hire_out.date()
            full_days = random.randint(3, 40)
            end_dt = hire_out + timedelta(days=full_days)
            # Off-hire only if the hire would have already ended by today; a hire
            # still running past today is ON HIRE (no end date / no final days),
            # so no future dates are ever written.
            is_off = (random.random() < 0.68) and (end_dt <= now)
            days = full_days if is_off else None
            hire_back = end_dt if is_off else None
            hire_end_d = (start_d + timedelta(days=full_days)) if is_off else None

            db.add(HireVehicleProvided(
                claim_id=claim.id,
                hire_vehicle_status_id=OFF_HIRE if is_off else ON_HIRE,
                actual_vehicle_category_id=random.randint(1, 181),
                rate=abi_rate,
                hire_vehicle_registration=_reg(),
                make=make, model=model,
                hire_start_date=start_d,
                hire_end_date=hire_end_d,
                is_active=True, is_deleted=False,
                created_by=USER_ID, updated_by=USER_ID,
                created_at=opened, updated_at=opened,
            ))
            db.add(HireDetail(
                claim_id=claim.id,
                hire_out=hire_out,
                hire_back=hire_back,
                final_total_no_of_hire_days=days,
                registration_number=_reg(), make=make, model=model,
                abi_insurer=random.random() < 0.5,
                abi_hire_charge_per_day=abi_rate,
                abi_extra_charges_per_day=round(random.uniform(0, 20), 2),
                abi_administration_fee=admin_fee,
                is_active=True, is_deleted=False,
                created_by=USER_ID, updated_by=USER_ID,
                created_at=hire_out, updated_at=hire_out,
            ))

            if is_off:
                billed = round(abi_rate * days + admin_fee, 2)
                received = round(billed * random.uniform(0.25, 1.0), 2)
                outstanding = round(max(0.0, billed - received), 2)
                db.add(HirePaymentDetails(
                    claim_id=claim.id,
                    payments_received_total=received,
                    payment_outstanding_incl_vat=round(outstanding * 1.2, 2),
                    payment_outstanding_excl_vat=outstanding,
                    is_active=True, is_deleted=False,
                    created_by=USER_ID, updated_by=USER_ID,
                    created_at=opened, updated_at=opened,
                ))

        # Income-breakdown extras on a subset
        if random.random() < 0.28:
            db.add(Storage(
                claim_id=claim.id, storage_provider="Demo Storage",
                total_storage_charges=round(random.uniform(120, 900), 2),
                total_storage_days=random.randint(2, 20),
                charge_per_day=round(random.uniform(15, 45), 2),
                is_active=True, is_deleted=False,
                created_by=USER_ID, updated_by=USER_ID,
                created_at=opened, updated_at=opened,
            ))
        if random.random() < 0.24:
            db.add(Recovery(
                claim_id=claim.id, recovery_provider="Demo Recovery",
                recovery_charges=round(random.uniform(150, 550), 2),
                is_active=True, is_deleted=False,
                created_by=USER_ID, updated_by=USER_ID,
                created_at=opened, updated_at=opened,
            ))
        if random.random() < 0.30:
            db.add(EngineerDetail(
                tenant_id=TENANT_ID, claim_id=claim.id,
                company_name="Demo Engineers",
                engineer_fee=round(random.uniform(180, 650), 2),
                is_active=True, is_deleted=False,
                created_by=USER_ID, updated_by=USER_ID,
                created_at=opened, updated_at=opened,
            ))

        created += 1
        if created % 100 == 0:
            db.commit()
            print(f"  ... {created} claims committed")

    db.commit()
    print(f"Done. Seeded {created} claims (tenant {TENANT_ID}).")


if __name__ == "__main__":
    db = next(get_session())
    try:
        if "--names" in sys.argv:
            backfill_names(db)
        elif "--clean" in sys.argv:
            clean(db)
        elif "--recent" in sys.argv:
            # Concentrate claims in the last ~30 days so the WTD / MTD cards fill.
            n = 70
            for a in sys.argv[1:]:
                if a.isdigit():
                    n = int(a)
            seed(db, n, max_days=30, recent=True)
        else:
            n = 650
            for a in sys.argv[1:]:
                if a.isdigit():
                    n = int(a)
            seed(db, n)
    finally:
        db.close()
