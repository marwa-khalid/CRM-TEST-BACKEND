"""One-off demo data seeder for the dashboard charts (tenant 36).

Creates spread-out claims across 2025 & 2026 (varied months/weeks/quarters) plus
hire records split between On Hire / Off Hire, so the Claims Trend and Hire Trend
charts (WTD/MTD/YTD, YoY quarters, MoM weeks) have realistic variation.

Idempotent: re-running first removes the rows it previously inserted (tagged via
file_closed_reason == SEED_TAG).

Run:  PYTHONPATH=src python3 seed_demo_charts.py
"""
from datetime import datetime, timedelta

from sqlalchemy import text
from libdata.settings import get_session_ctx
from libdata.models.tables import Claim, HireDetail, HireVehicleProvided

# Demo data must never sit in the future — "to date" charts (WTD/MTD/YTD) should
# show 0 for days/months that haven't happened yet (no Thursday claims when today
# is Wednesday, no September data when September 2026 hasn't arrived).
NOW = datetime.now()

TENANT_ID = 36
SEED_TAG = "SEED_DEMO_CHARTS"
ON_HIRE_STATUS = 1   # hire_vehicle_statuses: 1 = On Hire
OFF_HIRE_STATUS = 2  # 2 = Off Hire
CASE_STATUSES = [1, 5, 6, 2, 1, 6]  # Accepted / Pending / Completed / TBC ...

# Days chosen to land in each of the four "weeks" of a month (1-7, 8-14, 15-21, 22-end).
WEEK_DAYS = [4, 11, 18, 25]


def _dt(year, month, day, hour=10):
    return datetime(year, month, day, hour, 0, 0)


# Extra 2025-side claims concentrated in two financial-year quarters so the grey
# (previous FY) line crosses above the blue (current FY) line for a pretty,
# overlapping YoY chart. (year, month, how_many)
BOOST = [
    (2024, 11, 4), (2024, 12, 4), (2025, 1, 4),   # FY24/25 Q1 (Nov–Jan): grey spikes above blue
    (2025, 5, 4), (2025, 6, 3), (2025, 7, 4),      # FY24/25 Q3 (May–Jul): grey spikes above blue
]


def build_dates():
    """(year, month, day) spread: 30 in 2025 (all 12 months), 40 in 2026 (Jan–Oct),
    plus boosters that lift two 2025 quarters above their 2026 counterparts, plus a
    couple of claims per day in the *current* week. Any date past "now" is dropped
    so the demo never shows future data (see NOW filter at the end)."""
    dates = []
    for i in range(30):                      # 2025
        dates.append((2025, (i % 12) + 1, WEEK_DAYS[i % 4]))
    for i in range(40):                      # 2026 (Jan–Oct so it stays within the current FY)
        dates.append((2026, (i % 10) + 1, WEEK_DAYS[i % 4]))
    for (y, m, cnt) in BOOST:                # crossing boosters
        for k in range(cnt):
            dates.append((y, m, WEEK_DAYS[k % 4]))

    # Current week (Mon → today): two claims per day so WTD shows real data on
    # past days and 0 on days not yet reached. Future days fall away in the filter.
    monday = NOW - timedelta(days=NOW.weekday())
    for off in range(7):
        day = monday + timedelta(days=off)
        dates.append((day.year, day.month, day.day))
        dates.append((day.year, day.month, day.day))

    # Realism guard: never seed a date in the future.
    return [(y, m, d) for (y, m, d) in dates if _dt(y, m, d) <= NOW]


def main():
    with get_session_ctx() as db:
        # ---- clean up a previous run -------------------------------------
        old = db.query(Claim).filter(
            Claim.tenant_id == TENANT_ID,
            Claim.file_closed_reason == SEED_TAG,
        ).all()
        if old:
            ids = [c.id for c in old]
            # Delete every child row referencing these claims first. Not all FKs
            # are ON DELETE CASCADE (e.g. referrers), so clear them generically by
            # querying the schema for any table that references claims.id — these
            # are all demo rows, safe to remove.
            child_fks = db.execute(text("""
                SELECT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                 AND tc.table_schema = ccu.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'claims'
            """)).fetchall()
            for table_name, column_name in child_fks:
                db.execute(
                    text(f'DELETE FROM "{table_name}" WHERE "{column_name}" = ANY(:ids)'),
                    {"ids": ids},
                )
            db.query(Claim).filter(Claim.id.in_(ids)).delete(synchronize_session=False)
            db.flush()
            print(f"Removed {len(old)} previously-seeded claims (and their child rows).")

        # ---- claims ------------------------------------------------------
        dates = build_dates()
        claims = []
        for i, (y, m, d) in enumerate(dates):
            c = Claim(
                tenant_id=TENANT_ID,
                case_status_id=CASE_STATUSES[i % len(CASE_STATUSES)],
                file_opened_at=_dt(y, m, d),
                file_closed_reason=SEED_TAG,   # marker for idempotent cleanup
                non_fault_accident="Yes",
                is_active=True,
                is_deleted=False,
            )
            db.add(c)
            claims.append((c, _dt(y, m, d)))
        db.flush()  # assign claim ids

        # ---- hires (≈ every other claim), alternating On/Off Hire --------
        hire_count = {"on": 0, "off": 0}
        for i, (claim, opened) in enumerate(claims):
            if i % 2 != 0:
                continue
            on_hire = (i % 4 == 0)
            back_date = opened + timedelta(days=14)
            # A vehicle whose return date hasn't arrived yet is still On Hire —
            # don't mark it Off Hire with a future hire-back date.
            if back_date > NOW:
                on_hire = True
            status_id = ON_HIRE_STATUS if on_hire else OFF_HIRE_STATUS
            reg = f"DM{(i % 99):02d} XYZ"
            hvp = HireVehicleProvided(
                claim_id=claim.id,
                hire_vehicle_status_id=status_id,
                hire_vehicle_registration=reg,
                make="Ford",
                model="Focus",
                hire_start_date=opened.date(),
            )
            db.add(hvp)
            db.flush()
            hd = HireDetail(
                claim_id=claim.id,
                hire_vehicle_provided_id=hvp.id,
                hire_out=opened,
                hire_back=None if on_hire else back_date,
                registration_number=reg,
                make="Ford",
                model="Focus",
            )
            db.add(hd)
            hire_count["on" if on_hire else "off"] += 1

        db.flush()
        print(f"Inserted {len(claims)} claims "
              f"({sum(1 for _, dd in claims if dd.year == 2025)} in 2025, "
              f"{sum(1 for _, dd in claims if dd.year == 2026)} in 2026).")
        print(f"Inserted hires: {hire_count['on']} On Hire, {hire_count['off']} Off Hire.")


if __name__ == "__main__":
    main()
