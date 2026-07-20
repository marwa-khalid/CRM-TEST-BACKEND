"""Automatic weekly payment reminders.

Run once a day (Railway cron). Every hire has a Payment Day weekday; two days
before each upcoming Payment Day, any hire with an outstanding balance gets a
WhatsApp reminder. It repeats every week until the schedule is fully paid.

Idempotency: the hire stores the Payment Day it was last reminded FOR, so running
the job twice in one day — or re-running after a failure — never double-sends.
"""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from fleet.models.tables import FleetHire, FleetHirePayment
from fleet.services.whatsapp_service import send_whatsapp

logger = logging.getLogger(__name__)

# How many days before the Payment Day the reminder goes out.
DAYS_BEFORE = 2

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _num(value: Optional[str]) -> float:
    try:
        return float(str(value or "").replace(",", "").replace("£", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _outstanding(rows: List[FleetHirePayment]) -> float:
    """Total still owed across the schedule."""
    return sum(max(0.0, _num(r.due_amount) - _num(r.paid_amount)) for r in rows)


def reminder_body(driver_name: str, amount: float, due_on: date) -> str:
    """Two days' notice — deliberately not the 'pay today' wording, which only
    makes sense on the day itself."""
    name = (driver_name or "").strip().split(" ")[0] or "there"
    return (
        f"Hi {name}, a reminder from Skyline Car Hire (UK) Ltd that your weekly hire "
        f"payment of £{amount:.2f} is due on {due_on.strftime('%A %d %B')}. "
        f"Paying on time avoids late fees of £35.00 plus £2.00 per day thereafter."
    )


def run_payment_reminders(db: Session, today: Optional[date] = None) -> Dict[str, int]:
    """Send reminders for Payment Days landing DAYS_BEFORE from today."""
    today = today or date.today()
    target_day = today + timedelta(days=DAYS_BEFORE)
    target_weekday = WEEKDAYS[target_day.weekday()]

    hires = (
        db.query(FleetHire)
        .filter(FleetHire.is_deleted.isnot(True))
        .filter(FleetHire.payment_day == target_weekday)
        .all()
    )

    stats = {"checked": len(hires), "sent": 0, "skipped_paid": 0, "skipped_done": 0, "failed": 0}

    for hire in hires:
        # Already reminded for this Payment Day — the job is safe to re-run.
        if hire.payment_reminder_sent_for == target_day:
            stats["skipped_done"] += 1
            continue

        rows = db.query(FleetHirePayment).filter(FleetHirePayment.hire_id == hire.id).all()
        outstanding = _outstanding(rows)
        if outstanding <= 0:
            stats["skipped_paid"] += 1
            continue

        # Charge for one week, not the whole balance — the weekly figure is what
        # the hirer actually has to pay on the day.
        weekly = _num(hire.weekly_hire_payment) or outstanding
        amount = min(weekly, outstanding)

        result = send_whatsapp(hire.driver_mobile, reminder_body(hire.driver_name or "", amount, target_day))
        if result.get("sent"):
            # Stamp first, then commit — a send that succeeded must never be
            # repeated because a later hire in the loop blew up.
            hire.payment_reminder_sent_for = target_day
            db.commit()
            stats["sent"] += 1
        else:
            stats["failed"] += 1
            logger.warning(
                "Payment reminder failed for hire %s (%s): %s",
                hire.id, hire.fleet_reference, result.get("reason"),
            )

    logger.info("Payment reminders for %s (%s): %s", target_day, target_weekday, stats)
    return stats
