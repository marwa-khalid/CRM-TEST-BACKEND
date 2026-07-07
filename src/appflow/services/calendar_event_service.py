import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from libdata.models.tables import (
    CalendarEvent, CalendarEventAudit, Claim, ClientDetail, CaseStatus, PersonRoleEnum, User,
)
from appflow.models.calendar_event import CalendarEventIn


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day to month length
    import calendar as _cal
    day = min(d.day, _cal.monthrange(y, m)[1])
    return date(y, m, day)


def _step(d: date, rule: str) -> date:
    r = (rule or "").lower()
    if r == "daily":
        return d + timedelta(days=1)
    if r == "weekly":
        return d + timedelta(weeks=1)
    if r == "monthly":
        return _add_months(d, 1)
    if r == "yearly":
        return _add_months(d, 12)
    return d + timedelta(days=1)


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # 5 = Saturday, 6 = Sunday


def _next_weekday(d: date) -> date:
    """Push a date that lands on the weekend forward to the next Monday."""
    while d.weekday() >= 5:
        d = d + timedelta(days=1)
    return d


def _load_overrides(ev: "CalendarEvent") -> dict:
    """Parse the per-occurrence override map (date ISO -> status) off an event."""
    raw = getattr(ev, "recurrence_overrides", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


_REMINDER_OFFSET = {"15m": timedelta(minutes=15), "30m": timedelta(minutes=30),
                    "1h": timedelta(hours=1), "1d": timedelta(days=1)}


def _split(v) -> List[str]:
    if not v:
        return []
    return [s.strip() for s in str(v).split(",") if s.strip()]


def _join(v) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, (list, tuple)):
        return ", ".join([str(s).strip() for s in v if str(s).strip()]) or None
    return str(v)


def _linked_context(db: Session, ev: CalendarEvent) -> dict:
    """Claimant name + case status for the Event Details drawer (linked claim)."""
    claimant_name = None
    case_status = None
    if ev.claim_id:
        claim = db.query(Claim).filter(Claim.id == ev.claim_id).first()
        if claim:
            if claim.case_status_id:
                cs = db.query(CaseStatus).filter(CaseStatus.id == claim.case_status_id).first()
                case_status = cs.label if cs else None
            client = (
                db.query(ClientDetail)
                .filter(ClientDetail.claim_id == ev.claim_id,
                        ClientDetail.role == PersonRoleEnum.CLIENT)
                .first()
            )
            if client:
                claimant_name = f"{client.first_name or ''} {client.surname or ''}".strip() or None
    return {"claimant_name": claimant_name, "case_status": case_status}


def _to_out(db: Session, ev: CalendarEvent, with_context: bool = False) -> dict:
    data = {
        "id": ev.id,
        "title": ev.title,
        "event_type": ev.event_type,
        "status": ev.status,
        "start_date": ev.start_date,
        "start_time": ev.start_time,
        "end_date": ev.end_date,
        "end_time": ev.end_time,
        "assigned_users": _split(ev.assigned_users),
        "department": ev.department,
        "description": ev.description,
        "location": ev.location,
        "reminder": ev.reminder,
        "recurrence_rule": ev.recurrence_rule,
        "recurrence_overrides": ev.recurrence_overrides,
        "attachment_path": ev.attachment_path,
        "attachment_name": ev.attachment_name,
        "claim_id": ev.claim_id,
        "claim_reference": ev.claim_reference,
        "case_reference": ev.case_reference,
        "task_id": ev.task_id,
        "vehicle_registration": ev.vehicle_registration,
        "source": ev.source,
        "source_type": ev.source_type,
        "source_ref_id": ev.source_ref_id,
        "reminder_sent": ev.reminder_sent,
        "recurrence_rule": ev.recurrence_rule,
        "created_at": ev.created_at,
        "updated_at": ev.updated_at,
        "is_occurrence": False,
        "claimant_name": None,
        "case_status": None,
    }
    if with_context:
        data.update(_linked_context(db, ev))
    return data


def _audit(db: Session, event_id, action: str, detail: str, user_id, tenant_id):
    try:
        db.add(CalendarEventAudit(
            event_id=event_id, action=action, detail=detail,
            user_id=user_id, tenant_id=tenant_id,
        ))
        db.commit()
    except Exception:
        db.rollback()


def _expand_recurrence(ev_out: dict, win_start: Optional[date], win_end: Optional[date]) -> List[dict]:
    """Expand a recurring event into occurrences within [win_start, win_end].
    Occurrences share the base event id and are flagged is_occurrence=True.

    Weekends are treated as holidays: daily series skip Sat/Sun entirely (Mon–Fri),
    while weekly/monthly/yearly occurrences that land on a weekend shift forward to
    the next Monday. Per-occurrence overrides apply a one-off status or hide a
    deleted occurrence."""
    rule = ev_out.get("recurrence_rule")
    base_start = ev_out.get("start_date")
    if not rule or not base_start or not win_end:
        return [ev_out]
    base_end = ev_out.get("end_date") or base_start
    duration = (base_end - base_start) if base_end and base_start else timedelta(0)

    overrides = {}
    raw = ev_out.get("recurrence_overrides")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                overrides = parsed
        except Exception:
            overrides = {}

    rule_l = (rule or "").lower()
    out: List[dict] = []
    cur = base_start
    for _ in range(800):  # safety cap
        if cur > win_end:
            break
        # Resolve the date this occurrence is actually shown on (weekends are holidays).
        if rule_l == "daily":
            if _is_weekend(cur):
                cur = _step(cur, rule)
                continue
            disp = cur
        else:
            disp = _next_weekday(cur)

        if disp <= win_end and (not win_start or disp >= win_start):
            ov = overrides.get(disp.isoformat())
            if ov != "Deleted":
                occ = dict(ev_out)
                occ["start_date"] = disp
                occ["end_date"] = disp + duration
                occ["is_occurrence"] = disp != base_start
                if ov in ("Cancelled", "Completed"):
                    occ["status"] = ov
                out.append(occ)
        cur = _step(cur, rule)
    return out


class CalendarEventService:

    @staticmethod
    def _base(db: Session, tenant_id):
        q = db.query(CalendarEvent).filter(
            CalendarEvent.is_active == True,  # noqa: E712
            CalendarEvent.is_deleted == False,  # noqa: E712
        )
        if tenant_id is not None:
            q = q.filter(CalendarEvent.tenant_id == tenant_id)
        return q

    @staticmethod
    def _user_name_candidates(db: Session, user_id) -> List[str]:
        """Name strings a user's events could be tagged with in assigned_users
        (login email, its handle, and the full name) — used to scope the calendar
        to the current user."""
        if not user_id:
            return []
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            return []
        un = (u.user_name or "")
        disp = un.split("@")[0] if "@" in un else un
        full = " ".join(p for p in [getattr(u, "first_name", None), getattr(u, "last_name", None)] if p)
        return [s for s in {un, disp, full} if s]

    @staticmethod
    def list_events(
        db: Session, tenant_id,
        start: Optional[date] = None, end: Optional[date] = None,
        event_type: Optional[str] = None, assigned_user: Optional[str] = None,
        department: Optional[str] = None, claim_reference: Optional[str] = None,
        vehicle_registration: Optional[str] = None, search: Optional[str] = None,
        status_filter: Optional[str] = None, current_user=None,
    ):
        q = CalendarEventService._base(db, tenant_id)
        # User-specific: each user only sees events they created or are assigned to.
        if current_user:
            names = CalendarEventService._user_name_candidates(db, current_user)
            mine = [CalendarEvent.created_by == current_user]
            mine += [CalendarEvent.assigned_users.ilike(f"%{nm}%") for nm in names]
            q = q.filter(or_(*mine))
        if start:
            q = q.filter(or_(CalendarEvent.end_date >= start, CalendarEvent.start_date >= start))
        if end:
            q = q.filter(CalendarEvent.start_date <= end)
        if event_type:
            q = q.filter(CalendarEvent.event_type.in_([s.strip() for s in event_type.split(",") if s.strip()]))
        if department:
            q = q.filter(CalendarEvent.department.in_([s.strip() for s in department.split(",") if s.strip()]))
        if assigned_user:
            terms = [s.strip() for s in assigned_user.split(",") if s.strip()]
            if terms:
                q = q.filter(or_(*[CalendarEvent.assigned_users.ilike(f"%{t}%") for t in terms]))
        if claim_reference:
            q = q.filter(CalendarEvent.claim_reference.ilike(f"%{claim_reference}%"))
        if vehicle_registration:
            q = q.filter(CalendarEvent.vehicle_registration.ilike(f"%{vehicle_registration}%"))
        if status_filter:
            q = q.filter(CalendarEvent.status == status_filter)
        if search:
            like = f"%{search}%"
            q = q.filter(or_(
                CalendarEvent.title.ilike(like),
                CalendarEvent.description.ilike(like),
                CalendarEvent.location.ilike(like),
                CalendarEvent.assigned_users.ilike(like),
                CalendarEvent.claim_reference.ilike(like),
                CalendarEvent.vehicle_registration.ilike(like),
            ))
        events = q.order_by(CalendarEvent.start_date.asc(), CalendarEvent.start_time.asc()).all()
        out: List[dict] = []
        for e in events:
            base = _to_out(db, e)
            if e.recurrence_rule:
                out.extend(_expand_recurrence(base, start, end))
            else:
                out.append(base)
        out.sort(key=lambda d: (str(d.get("start_date") or ""), str(d.get("start_time") or "")))
        return out

    @staticmethod
    def get_event(db: Session, event_id: int, tenant_id):
        ev = CalendarEventService._base(db, tenant_id).filter(CalendarEvent.id == event_id).first()
        if not ev:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        return _to_out(db, ev, with_context=True)

    @staticmethod
    def _notify_assignees(db: Session, ev: CalendarEvent, current_user, tenant_id, title: str):
        from appflow.services.notification_service import resolve_user_by_name, safe_notify
        names = _split(ev.assigned_users)
        recipients = set()
        for n in names:
            uid = resolve_user_by_name(db, n, tenant_id)
            if uid:
                recipients.add(uid)
        if not recipients:
            recipients.add(current_user)  # fallback so it's testable before accounts exist
        when = ev.start_date.isoformat() if ev.start_date else ""
        for uid in recipients:
            safe_notify(
                db, recipient_user_id=uid, tenant_id=tenant_id, actor_user_id=current_user,
                category="Calendar", tab="Calendar", title=title,
                description=f"{ev.title}{(' on ' + when) if when else ''}.",
                claim_id=ev.claim_id, email=False,  # in-app only
            )

    @staticmethod
    def create_event(payload: CalendarEventIn, db: Session, current_user, tenant_id):
        data = payload.model_dump(exclude_unset=True)
        data["assigned_users"] = _join(data.get("assigned_users"))
        # status is passed explicitly below (with a default) — drop it from data
        # so it isn't supplied twice to the model constructor.
        data.pop("status", None)
        ev = CalendarEvent(
            **data,
            status=payload.status or "Scheduled",
            source="manual",
            tenant_id=tenant_id,
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)
        _audit(db, ev.id, "created", ev.title, current_user, tenant_id)
        CalendarEventService._notify_assignees(db, ev, current_user, tenant_id, "Event Assigned")
        return _to_out(db, ev, with_context=True)

    @staticmethod
    def update_event(event_id: int, payload: CalendarEventIn, db: Session, current_user, tenant_id):
        ev = CalendarEventService._base(db, tenant_id).filter(CalendarEvent.id == event_id).first()
        if not ev:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        data = payload.model_dump(exclude_unset=True)
        old_assignees = ev.assigned_users
        old_title = ev.title
        old_attach = _split(ev.attachment_path)
        if "assigned_users" in data:
            data["assigned_users"] = _join(data.get("assigned_users"))
        for k, v in data.items():
            setattr(ev, k, v)
        # Re-arm the reminder if the schedule changed.
        if any(k in data for k in ("start_date", "start_time", "reminder")):
            ev.reminder_sent = False
        ev.updated_by = current_user
        db.commit()
        db.refresh(ev)

        # Log attachment changes explicitly so they show in the activity log.
        new_attach = _split(ev.attachment_path)
        added = [a for a in new_attach if a not in old_attach]
        removed = [a for a in old_attach if a not in new_attach]
        if added:
            _audit(db, ev.id, "attachment added",
                   ", ".join(a.split("/")[-1] for a in added), current_user, tenant_id)
        if removed:
            _audit(db, ev.id, "attachment removed",
                   ", ".join(a.split("/")[-1] for a in removed), current_user, tenant_id)
        # Skip the generic "updated" entry when the save only touched attachments
        # (the attachment-tab sends title unchanged alongside the attachment fields).
        attach_only = set(data.keys()) <= {"title", "attachment_path", "attachment_name"} and ev.title == old_title
        if not attach_only:
            _audit(db, ev.id, "updated", ev.title, current_user, tenant_id)

        if "assigned_users" in data and (ev.assigned_users or "") != (old_assignees or ""):
            CalendarEventService._notify_assignees(db, ev, current_user, tenant_id, "Event Reassigned")
        return _to_out(db, ev, with_context=True)

    @staticmethod
    def set_status(event_id: int, new_status: str, db: Session, current_user, tenant_id,
                   occurrence_date: Optional[date] = None):
        ev = CalendarEventService._base(db, tenant_id).filter(CalendarEvent.id == event_id).first()
        if not ev:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        # Recurring series: record a one-off override for just this occurrence so the
        # rest of the series is untouched.
        if occurrence_date and ev.recurrence_rule:
            ov = _load_overrides(ev)
            ov[occurrence_date.isoformat()] = new_status
            ev.recurrence_overrides = json.dumps(ov)
            ev.updated_by = current_user
            db.commit()
            db.refresh(ev)
            _audit(db, ev.id, new_status.lower(),
                   f"{ev.title} on {occurrence_date.isoformat()}", current_user, tenant_id)
            return _to_out(db, ev, with_context=True)
        ev.status = new_status
        ev.updated_by = current_user
        db.commit()
        db.refresh(ev)
        _audit(db, ev.id, new_status.lower(), ev.title, current_user, tenant_id)
        return _to_out(db, ev, with_context=True)

    @staticmethod
    def delete_event(event_id: int, db: Session, current_user, tenant_id,
                     occurrence_date: Optional[date] = None):
        ev = CalendarEventService._base(db, tenant_id).filter(CalendarEvent.id == event_id).first()
        if not ev:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")
        # Recurring series: hide only this occurrence, keep the rest of the series.
        if occurrence_date and ev.recurrence_rule:
            ov = _load_overrides(ev)
            ov[occurrence_date.isoformat()] = "Deleted"
            ev.recurrence_overrides = json.dumps(ov)
            ev.updated_by = current_user
            db.commit()
            _audit(db, ev.id, "deleted",
                   f"{ev.title} on {occurrence_date.isoformat()}", current_user, tenant_id)
            return {"ok": True}
        ev.is_deleted = True
        ev.is_active = False
        ev.updated_by = current_user
        db.commit()
        _audit(db, ev.id, "deleted", ev.title, current_user, tenant_id)
        return {"ok": True}

    @staticmethod
    def get_audit(db: Session, event_id: int, tenant_id):
        rows = (
            db.query(CalendarEventAudit)
            .filter(CalendarEventAudit.event_id == event_id)
            .order_by(CalendarEventAudit.created_at.desc())
            .all()
        )
        return [
            {"id": r.id, "action": r.action, "detail": r.detail,
             "user_id": r.user_id, "created_at": r.created_at}
            for r in rows
        ]

    @staticmethod
    def process_due_reminders(db: Session):
        """Fire in-app notifications for events whose reminder time has passed.
        Called lazily whenever notifications are fetched (no separate scheduler)."""
        now = datetime.now(timezone.utc)
        candidates = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.is_active == True,  # noqa: E712
                CalendarEvent.is_deleted == False,  # noqa: E712
                CalendarEvent.reminder.isnot(None),
                or_(CalendarEvent.reminder_sent == False, CalendarEvent.reminder_sent.is_(None)),  # noqa: E712
                CalendarEvent.status == "Scheduled",
                CalendarEvent.start_date.isnot(None),
            )
            .all()
        )
        fired = 0
        for ev in candidates:
            # reminder may hold several offsets ("15m,1h,1d"); fire once when the
            # earliest selected reminder becomes due.
            offsets = [_REMINDER_OFFSET[o] for o in _split(ev.reminder) if o in _REMINDER_OFFSET]
            if not offsets:
                continue
            hh, mm = 9, 0
            if ev.start_time and ":" in ev.start_time:
                try:
                    hh, mm = int(ev.start_time.split(":")[0]), int(ev.start_time.split(":")[1])
                except Exception:
                    pass
            start_dt = datetime(ev.start_date.year, ev.start_date.month, ev.start_date.day,
                                hh, mm, tzinfo=timezone.utc)
            # Earliest reminder = largest offset before start.
            if any(start_dt - off <= now <= start_dt + timedelta(hours=1) for off in offsets):
                CalendarEventService._notify_assignees(db, ev, ev.created_by, ev.tenant_id, "Event Reminder")
                ev.reminder_sent = True
                db.commit()
                fired += 1
        return fired

    @staticmethod
    def sync_system_event(
        db: Session, *, tenant_id, source_type: str, source_ref_id: int,
        title: str, event_type: str, start_date, start_time=None,
        claim_id=None, claim_reference=None, vehicle_registration=None,
        task_id=None, assigned_users=None, status=None, remove=False,
    ):
        """Upsert (or remove) a system-generated calendar event tied to a source
        record. Pass start_date=None (or remove=True) to remove the event — e.g.
        when the source date is cleared, or a task is cancelled/rejected. `status`
        mirrors the source status onto the event (e.g. Completed → dim on calendar).
        Used by source screens (Phase 3) — auto create/sync/remove."""
        ev = (
            db.query(CalendarEvent)
            .filter(
                CalendarEvent.source == "system",
                CalendarEvent.source_type == source_type,
                CalendarEvent.source_ref_id == source_ref_id,
                CalendarEvent.is_deleted == False,  # noqa: E712
            )
            .first()
        )
        if remove or not start_date:
            if ev:
                ev.is_deleted = True
                ev.is_active = False
                db.commit()
            return None
        if ev:
            ev.title, ev.event_type = title, event_type
            ev.start_date = start_date
            ev.end_date = start_date
            ev.start_time = start_time
            ev.claim_id, ev.claim_reference = claim_id, claim_reference
            ev.vehicle_registration, ev.task_id = vehicle_registration, task_id
            if assigned_users is not None:
                ev.assigned_users = _join(assigned_users)
            if status is not None:
                ev.status = status
        else:
            ev = CalendarEvent(
                tenant_id=tenant_id, title=title, event_type=event_type, status=status or "Scheduled",
                start_date=start_date, end_date=start_date, start_time=start_time,
                claim_id=claim_id, claim_reference=claim_reference,
                vehicle_registration=vehicle_registration, task_id=task_id,
                assigned_users=_join(assigned_users),
                source="system", source_type=source_type, source_ref_id=source_ref_id,
            )
            db.add(ev)
        db.commit()
        return ev
