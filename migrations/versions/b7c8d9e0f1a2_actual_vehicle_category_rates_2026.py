"""add fifty_fifty_rate to actual_vehicle_categories and load 2026 GTA rates

Adds the 50/50 rate column to actual_vehicle_categories and refreshes the
ABI / 50-50 / BHR rates for each GTA group from the 2026 "Updated Car and
Private Hire Taxi" schedule (the purple columns):

  * abi_rate        = 2026 GTA Rate (adjusted per section)
  * fifty_fifty_rate = 50/50 column
  * bhr_rate        = BHR (35% top of New GTA) column

Updates are keyed by `label`, so any group whose label differs in this
deployment is simply skipped (no rows changed) rather than corrupted.

client_vehicle_categories intentionally has no rate columns — it holds
labels only.

Revision ID: b7c8d9e0f1a2
Revises: b1c2d3e4f5a6
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

# label -> (abi_rate, fifty_fifty_rate, bhr_rate)
# Source: 2026 "Updated Car and Private Hire Taxi" schedule.
RATES = {
    # Standard (S)
    "S1": ("42.32", "21.16", "57.14"),
    "S2": ("47.99", "23.99", "64.78"),
    "S3": ("51.18", "25.59", "69.10"),
    "S4": ("54.87", "27.44", "74.08"),
    "S5": ("58.06", "29.03", "78.38"),
    "S6": ("61.86", "30.93", "83.51"),
    "S7": ("86.74", "43.37", "117.10"),
    # MPV (M)
    "M":  ("56.66", "28.33", "76.49"),
    "M1": ("65.49", "32.75", "88.41"),
    "M2": ("74.68", "37.34", "100.82"),
    "M3": ("87.68", "43.84", "118.37"),
    "M4": ("103.59", "51.79", "139.84"),
    "M5": ("155.37", "77.69", "209.75"),
    "M6": ("196.80", "98.40", "265.69"),
    # 4x4 / SUV (F)
    "F1": ("112.10", "56.05", "151.34"),
    "F2": ("111.74", "55.87", "150.84"),
    "F3": ("129.46", "64.73", "174.77"),
    "F4": ("158.83", "79.41", "214.42"),
    "F5": ("198.64", "99.32", "268.16"),
    "F6": ("223.47", "111.74", "301.69"),
    "F7": ("260.72", "130.36", "351.97"),
    "F8": ("279.34", "139.67", "377.11"),
    "F9": ("341.41", "170.71", "460.91"),
    # Prestige (P)
    "P1":  ("84.61", "42.30", "114.22"),
    "P2":  ("101.36", "50.68", "136.83"),
    "P3":  ("107.84", "53.92", "145.58"),
    "P4":  ("131.22", "65.61", "177.15"),
    "P5":  ("152.30", "76.15", "205.60"),
    "P6":  ("172.25", "86.13", "232.54"),
    "P7":  ("200.93", "100.47", "271.26"),
    "P8":  ("229.63", "114.81", "309.99"),
    "P9":  ("264.09", "132.05", "356.52"),
    "P10": ("324.96", "162.48", "438.69"),
    "P11": ("456.42", "228.21", "616.17"),
    "P12": ("683.21", "341.60", "922.33"),
    "P13": ("990.65", "495.32", "1337.37"),
    # Sports / Prestige Sports (SP)
    "SP1":  ("69.28", "34.64", "93.53"),
    "SP2":  ("75.32", "37.66", "101.69"),
    "SP3":  ("90.48", "45.24", "122.15"),
    "SP4":  ("103.30", "51.65", "139.46"),
    "SP5":  ("112.86", "56.43", "152.36"),
    "SP6":  ("149.92", "74.96", "202.39"),
    "SP7":  ("168.10", "84.05", "226.93"),
    "SP8":  ("186.27", "93.14", "251.47"),
    "SP9":  ("204.44", "102.22", "276.00"),
    "SP10": ("233.96", "116.98", "315.85"),
    "SP11": ("281.67", "140.83", "380.25"),
    "SP12": ("370.28", "185.14", "499.87"),
    "SP13": ("540.63", "270.31", "729.85"),
    # Taxi / trade age bands (T) — 2026 column of the T-group schedule.
    # Pre 31/03/11, hire car < 3 yrs
    "T1 < 3Y": ("85.18", "42.59", "114.99"),
    "T2 < 3Y": ("113.56", "56.78", "153.31"),
    "T3 < 3Y": ("106.46", "53.23", "143.72"),
    "T4 < 3Y": ("134.87", "67.44", "182.08"),
    # Pre 31/03/11, hire car >= 3 yrs
    "T1 ≥ 3Y": ("57.98", "28.99", "78.27"),
    "T2 ≥ 3Y": ("79.49", "39.74", "107.31"),
    "T3 ≥ 3Y": ("70.97", "35.49", "95.82"),
    "T4 ≥ 3Y": ("93.68", "46.84", "126.47"),
    # After 31/03/11 (NT), hire car < 3 yrs
    "NT3 < 3Y": ("106.46", "53.23", "143.72"),
    "NT4 < 3Y": ("141.45", "70.72", "190.96"),
    # After 31/03/11 (NT), hire car >= 3 yrs
    "NT3 ≥ 3Y": ("70.97", "35.49", "95.82"),
    "NT4 ≥ 3Y": ("98.25", "49.13", "132.64"),
    # All, hire car < 4 yrs
    "T5 < 4Y": ("96.53", "48.27", "130.32"),
    "T6 < 4Y": ("130.59", "65.30", "176.30"),
    "T7 < 4Y": ("110.74", "55.37", "149.49"),
    "T8 < 4Y": ("144.78", "72.39", "195.45"),
    # All, hire car >= 4 yrs
    "T5 ≥ 4Y": ("68.12", "34.06", "91.97"),
    "T6 ≥ 4Y": ("96.53", "48.27", "130.32"),
    "T7 ≥ 4Y": ("78.20", "39.10", "105.57"),
    "T8 ≥ 4Y": ("106.11", "53.06", "143.25"),
    # All, < 3 yrs (PT9/T10/T12/PT13 = hire car; T14 = hire bike)
    "PT9 < 3Y": ("265.07", "132.54", "357.85"),
    "T10 < 3Y": ("175.03", "87.52", "236.30"),
    "T12 < 3Y": ("187.60", "93.80", "253.26"),
    "PT13 < 3Y": ("318.15", "159.08", "429.51"),
    "T14 < 3Y": ("102.20", "51.10", "137.97"),
    # All, >= 3 yrs
    "PT9 ≥ 3Y": ("198.84", "99.42", "268.43"),
    "T10 ≥ 3Y": ("128.34", "64.17", "173.26"),
    "T12 ≥ 3Y": ("134.03", "67.01", "180.93"),
    "PT13 ≥ 3Y": ("234.44", "117.22", "316.50"),
    "T14 ≥ 3Y": ("73.81", "36.91", "99.65"),
}

# label -> (abi_rate, bhr_rate)
# Commercial schedule has NO 50/50 column, so fifty_fifty_rate stays NULL.
# abi_rate = "2026 New GTA Rate - Variable Increase/Decrease"; bhr_rate = BHR 35%.
COMMERCIAL = {
    # Minibuses (CM)
    "CM1": ("85.72", "115.72"),
    "CM2": ("99.20", "133.92"),
    "CM3": ("112.35", "151.67"),
    # Pickups (CP)
    "CP1": ("69.81", "94.25"),
    "CP2": ("79.20", "106.92"),
    "CP3": ("90.18", "121.75"),
    # Refrigerated vans (RV)
    "RV1": ("93.64", "126.41"),
    "RV2": ("129.52", "174.85"),
    # Commercial vans / tippers / luton (CV)
    "CV1": ("70.09", "94.62"),
    "CV2": ("71.91", "97.08"),
    "CV3": ("75.60", "102.06"),
    "CV4": ("107.70", "145.39"),
    # Panel vans (PV)
    "PV1": ("48.45", "65.41"),
    "PV2": ("56.23", "75.91"),
    "PV3": ("56.23", "75.91"),
    "PV4": ("62.36", "84.19"),
    "PV5": ("65.50", "88.43"),
    "PV6": ("68.66", "92.69"),
    # Commercial 4x4 / station wagons (CS)
    "CS1": ("81.94", "110.62"),
    "CS2": ("87.63", "118.31"),
    "CS3": ("94.11", "127.05"),
    "CS4": ("99.78", "134.71"),
    "CS5": ("106.26", "143.45"),
}


def upgrade() -> None:
    op.add_column(
        "actual_vehicle_categories",
        sa.Column("fifty_fifty_rate", sa.DECIMAL(), nullable=True),
    )

    bind = op.get_bind()
    stmt = sa.text(
        "UPDATE actual_vehicle_categories "
        "SET abi_rate = :abi, fifty_fifty_rate = :fifty, bhr_rate = :bhr "
        "WHERE label = :label"
    )
    for label, (abi, fifty, bhr) in RATES.items():
        bind.execute(stmt, {"label": label, "abi": abi, "fifty": fifty, "bhr": bhr})

    # Commercial groups are brand-new categories — INSERT them (ABI + BHR only,
    # no 50/50). Guarded by NOT EXISTS so the migration is safe to re-run and
    # won't duplicate a label that already exists. tenant_id stays NULL (listing
    # is not tenant-scoped); created_at/updated_at use the column server defaults.
    stmt_comm = sa.text(
        "INSERT INTO actual_vehicle_categories "
        "(label, abi_rate, bhr_rate, fifty_fifty_rate, valet_rate, sort_order, is_active, is_deleted) "
        "SELECT :label, :abi, :bhr, NULL, 30, :sort, TRUE, FALSE "
        "WHERE NOT EXISTS "
        "(SELECT 1 FROM actual_vehicle_categories WHERE label = :label)"
    )
    for i, (label, (abi, bhr)) in enumerate(COMMERCIAL.items()):
        bind.execute(stmt_comm, {"label": label, "abi": abi, "bhr": bhr, "sort": 1000 + i})


def downgrade() -> None:
    # Remove the commercial categories inserted by this migration.
    bind = op.get_bind()
    del_stmt = sa.text("DELETE FROM actual_vehicle_categories WHERE label = :label")
    for label in COMMERCIAL:
        bind.execute(del_stmt, {"label": label})

    op.drop_column("actual_vehicle_categories", "fifty_fifty_rate")
