"""Entry point for the daily payment-reminder cron.

Run from the backend root:

    PYTHONPATH=src python -m fleet.jobs.send_payment_reminders

On Railway, add this as a Cron schedule (e.g. "0 9 * * *" for 09:00 daily). The
job is idempotent, so a retry or an overlapping run cannot double-send.
"""
import logging
import sys

from fleet.deps import get_session
from fleet.services.payment_reminder_service import run_payment_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    session = next(get_session())
    try:
        stats = run_payment_reminders(session)
        print(f"Payment reminders: {stats}")
        return 0
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.exception("Payment reminder job failed: %s", exc)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
