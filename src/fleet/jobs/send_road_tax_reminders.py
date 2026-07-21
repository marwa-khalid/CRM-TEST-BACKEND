"""Entry point for the daily Road Fund Licence reminder cron.

    PYTHONPATH=src python -m fleet.jobs.send_road_tax_reminders

Sends a reminder each day from 7 days before expiry until the expiry date.
Idempotent, so retries and overlapping runs cannot double-notify.
"""
import logging
import sys

from fleet.deps import get_session
from fleet.services.road_fund_service import run_road_tax_reminders

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    session = next(get_session())
    try:
        stats = run_road_tax_reminders(session)
        print(f"Road tax reminders: {stats}")
        return 0
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.exception("Road tax reminder job failed: %s", exc)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
