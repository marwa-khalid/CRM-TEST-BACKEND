"""fix 2026 GTA rates that migration b7c8d9e0f1a2 failed to apply

Two bugs in b7c8d9e0f1a2 left the DB holding pre-2026 (wrong) rates:

  1. The T / NT / PT taxi groups are stored with *space-less* labels
     ("T1<3Y", "NT3≥3Y", "PT9<3Y"), but b7c8 keyed its UPDATE on spaced
     labels ("T1 < 3Y", …). Those 30 main rows matched nothing and kept the
     old values (the yellow "Variable Increase/Decrease New GTA" column and a
     BHR of 35% on top of it) instead of the "2026 - Variable Increase/Decrease
     New GTA" column the business wants.

  2. 50/50 rates are modelled as *separate category rows* suffixed "-50/50"
     (their own abi_rate holds the 50/50 value), NOT the fifty_fifty_rate
     column b7c8 populated. So every "-50/50" row (all groups) was never
     corrected and still carried a value derived from the wrong base.

This migration re-applies the same authoritative RATES table (verified against
the 2026 schedule) but against the real labels:

  * main row  <LABEL>        -> abi_rate = ABI(2026 col), bhr_rate = BHR
  * fifty row <LABEL>-50/50  -> abi_rate = 50/50 col,     bhr_rate = BHR

Updates are keyed by exact label, so a group whose label differs in this
deployment is skipped (no rows changed) rather than corrupted.

Revision ID: d5e6f7a8b9c0
Revises: f4a5b6c7d8e9
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

# label -> (abi_rate, fifty_fifty_rate, bhr_rate) — identical source of truth
# as b7c8d9e0f1a2. The T/NT/PT keys are written with spaces here purely for
# readability; upgrade() strips them to match the space-less DB labels.
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
    "T1 < 3Y": ("85.18", "42.59", "114.99"),
    "T2 < 3Y": ("113.56", "56.78", "153.31"),
    "T3 < 3Y": ("106.46", "53.23", "143.72"),
    "T4 < 3Y": ("134.87", "67.44", "182.08"),
    "T1 ≥ 3Y": ("57.98", "28.99", "78.27"),
    "T2 ≥ 3Y": ("79.49", "39.74", "107.31"),
    "T3 ≥ 3Y": ("70.97", "35.49", "95.82"),
    "T4 ≥ 3Y": ("93.68", "46.84", "126.47"),
    "NT3 < 3Y": ("106.46", "53.23", "143.72"),
    "NT4 < 3Y": ("141.45", "70.72", "190.96"),
    "NT3 ≥ 3Y": ("70.97", "35.49", "95.82"),
    "NT4 ≥ 3Y": ("98.25", "49.13", "132.64"),
    "T5 < 4Y": ("96.53", "48.27", "130.32"),
    "T6 < 4Y": ("130.59", "65.30", "176.30"),
    "T7 < 4Y": ("110.74", "55.37", "149.49"),
    "T8 < 4Y": ("144.78", "72.39", "195.45"),
    "T5 ≥ 4Y": ("68.12", "34.06", "91.97"),
    "T6 ≥ 4Y": ("96.53", "48.27", "130.32"),
    "T7 ≥ 4Y": ("78.20", "39.10", "105.57"),
    "T8 ≥ 4Y": ("106.11", "53.06", "143.25"),
    "PT9 < 3Y": ("265.07", "132.54", "357.85"),
    "T10 < 3Y": ("175.03", "87.52", "236.30"),
    "T12 < 3Y": ("187.60", "93.80", "253.26"),
    "PT13 < 3Y": ("318.15", "159.08", "429.51"),
    "T14 < 3Y": ("102.20", "51.10", "137.97"),
    "PT9 ≥ 3Y": ("198.84", "99.42", "268.43"),
    "T10 ≥ 3Y": ("128.34", "64.17", "173.26"),
    "T12 ≥ 3Y": ("134.03", "67.01", "180.93"),
    "PT13 ≥ 3Y": ("234.44", "117.22", "316.50"),
    "T14 ≥ 3Y": ("73.81", "36.91", "99.65"),
}


def upgrade() -> None:
    bind = op.get_bind()

    main_stmt = sa.text(
        "UPDATE actual_vehicle_categories "
        "SET abi_rate = :abi, bhr_rate = :bhr WHERE label = :label"
    )
    # 50/50 lives on its own category row; its abi_rate carries the 50/50 value,
    # and it shares the parent group's BHR (matching the existing data shape).
    fifty_stmt = sa.text(
        "UPDATE actual_vehicle_categories "
        "SET abi_rate = :fifty, bhr_rate = :bhr WHERE label = :label"
    )

    for spaced_label, (abi, fifty, bhr) in RATES.items():
        label = spaced_label.replace(" ", "")  # "T1 < 3Y" -> "T1<3Y"
        bind.execute(main_stmt, {"label": label, "abi": abi, "bhr": bhr})
        bind.execute(
            fifty_stmt,
            {"label": f"{label}-50/50", "fifty": fifty, "bhr": bhr},
        )


def downgrade() -> None:
    # Data-only correction of previously-wrong values; there is nothing safe to
    # restore to, so downgrade is a no-op.
    pass
