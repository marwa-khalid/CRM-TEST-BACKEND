import re
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from libdata.models.tables import Task, VehicleDetail, Claim, User, HireVehicleProvided
from appflow.models.task import TaskCreate, TaskUpdate

# Statuses that take a task out of the "overdue" running
_TERMINAL_STATUSES = ("Completed", "Rejected")


def _is_overdue(task: Task) -> bool:
    if not task.due_date:
        return False
    if (task.status or "") in _TERMINAL_STATUSES:
        return False
    return task.due_date < date.today()


def _to_out(task: Task) -> dict:
    """Return the ORM task plus a derived is_overdue flag (Pydantic reads attrs)."""
    setattr(task, "is_overdue", _is_overdue(task))
    return task


def _user_display(db: Session, user_id) -> str:
    if not user_id:
        return "Someone"
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return "Someone"
    if user.user_name:
        return user.user_name.split("@")[0]
    full_name = " ".join(p for p in [user.first_name, user.last_name] if p)
    return full_name or "Someone"


def _assignee_recipient(db: Session, assigned_user, tenant_id, fallback_user):
    from appflow.services.notification_service import resolve_user_by_name

    return resolve_user_by_name(db, assigned_user, tenant_id) or fallback_user


def _notify_task_assigned(db: Session, task: Task, current_user, title: str = "New Task Assigned",
                          reason: Optional[str] = None) -> None:
    if not task.assigned_user:
        return

    from appflow.services.notification_service import safe_notify

    tenant_id = task.tenant_id
    recipient_user_id = _assignee_recipient(db, task.assigned_user, tenant_id, current_user)
    actor_name = _user_display(db, current_user)
    is_high = (task.priority or "").strip().lower() == "high"
    ref = f" ({task.claim_reference})" if task.claim_reference else ""
    suffix = f" Reason: {reason}" if reason else ""
    safe_notify(
        db,
        recipient_user_id=recipient_user_id,
        tenant_id=tenant_id,
        actor_user_id=current_user,
        category="High Priority" if is_high else "Task",
        tab="High Priority" if is_high else "Tasks",
        title=title,
        description=f"{actor_name} assigned you a task: {task.title}{ref}.{suffix}",
        claim_id=task.claim_id,
        email=False,  # in-app notification only — no email for (re)assignment
    )


def _sync_task_due_event(db: Session, task: Task) -> None:
    """Keep a system-generated 'Task Deadline' calendar event in sync with the
    task's due date — auto create / update / remove (Calendar Phase 3, AC11).

    Cancelled tasks are removed from the calendar. Rejected tasks stay but show as
    "Rejected" (grey + strikethrough). Completed tasks stay with a Completed status
    so the calendar shows them dimmed. They all remain on Task Management."""
    try:
        from appflow.services.calendar_event_service import CalendarEventService
        st = (task.status or "").strip().lower()
        remove = st == "cancelled"
        cal_status = (
            "Completed" if st == "completed"
            else "Rejected" if st == "rejected"
            else "Scheduled"
        )
        CalendarEventService.sync_system_event(
            db, tenant_id=task.tenant_id, source_type="task_due", source_ref_id=task.id,
            title=f"Task Due: {task.title}", event_type="Task Deadline",
            start_date=task.due_date, start_time=task.due_time,
            claim_id=task.claim_id, claim_reference=task.claim_reference,
            vehicle_registration=task.vehicle_registration, task_id=task.id,
            assigned_users=[task.assigned_user] if task.assigned_user else None,
            status=cal_status, remove=remove,
        )
    except Exception:
        db.rollback()


class TaskService:
    @staticmethod
    def _base_query(db: Session, tenant_id: Optional[int]):
        q = db.query(Task).filter(Task.is_deleted == False)
        if tenant_id is not None:
            q = q.filter(or_(Task.tenant_id == tenant_id, Task.tenant_id.is_(None)))
        return q

    # ----- CREATE -----
    @staticmethod
    def create_task(payload: TaskCreate, db: Session, current_user, tenant_id):
        task = Task(
            **payload.dict(),
            tenant_id=tenant_id,
            created_by=current_user,
            updated_by=current_user,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        _sync_task_due_event(db, task)
        _notify_task_assigned(db, task, current_user)
        from appflow.services.task_note_service import log_history
        log_history(db, task.id, current_user, "created", "Task created", task.title, tenant_id)
        if task.assigned_user:
            log_history(db, task.id, current_user, "assigned", "Task assigned", f"Assigned to {task.assigned_user}", tenant_id)
        return _to_out(task)

    # ----- READ -----
    @staticmethod
    def get_task(task_id: int, db: Session):
        task = db.query(Task).filter(Task.id == task_id, Task.is_deleted == False).first()
        if not task:
            raise HTTPException(404, "Task not found")
        return _to_out(task)

    @staticmethod
    def list_tasks(
        db: Session,
        tenant_id: Optional[int] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        department: Optional[str] = None,
        assigned_user: Optional[str] = None,
        claim_reference: Optional[str] = None,
        vehicle_registration: Optional[str] = None,
        due_from: Optional[date] = None,
        due_to: Optional[date] = None,
        page: int = 1,
        page_size: int = 10,
        exclude_overdue: bool = False,
        current_user_id: Optional[int] = None,
    ):
        q = TaskService._base_query(db, tenant_id)

        # Tasks are user-specific: a user only sees the tasks assigned to them.
        # Assignees are stored as display strings, so match the logged-in user's
        # email prefix to the assignee after normalising (lowercase, strip
        # non-alphanumerics) — e.g. "hinasadaf@…" ↔ "Hina Sadaf".
        if current_user_id is not None:
            me = db.query(User).filter(User.id == current_user_id).first()
            handle = (me.user_name.split("@")[0] if me and me.user_name else "")
            norm_me = re.sub(r"[^a-z0-9]", "", handle.lower())
            norm_assignee = func.regexp_replace(
                func.lower(func.coalesce(Task.assigned_user, "")), "[^a-z0-9]", "", "g"
            )
            q = q.filter(norm_assignee == norm_me)

        # Filters accept a single value or a comma-separated list (multi-select)
        def _split(v):
            return [s.strip() for s in str(v).split(",") if s.strip()] if v else []

        if search:
            like = f"%{search}%"
            q = q.filter(
                or_(
                    Task.title.ilike(like),
                    Task.description.ilike(like),
                    Task.assigned_user.ilike(like),
                    Task.department.ilike(like),
                    Task.status.ilike(like),
                    Task.priority.ilike(like),
                    Task.claim_reference.ilike(like),
                    Task.vehicle_registration.ilike(like),
                    Task.notes.ilike(like),
                )
            )
        if status:
            statuses = _split(status)
            normal = [s for s in statuses if s.lower() != "overdue"]
            has_overdue = any(s.lower() == "overdue" for s in statuses)
            conds = []
            if normal:
                conds.append(Task.status.in_(normal))
            if has_overdue:
                conds.append(
                    and_(
                        Task.due_date.isnot(None),
                        Task.due_date < date.today(),
                        Task.status.notin_(_TERMINAL_STATUSES),
                    )
                )
            if conds:
                q = q.filter(or_(*conds))
        # A task past its due date reads as "Overdue" (it overrides the status
        # badge). exclude_overdue keeps the Pending / Awaiting Response cards
        # mutually exclusive with the Overdue card.
        if exclude_overdue:
            q = q.filter(or_(Task.due_date.is_(None), Task.due_date >= date.today()))
        if priority:
            q = q.filter(Task.priority.in_(_split(priority)))
        if department:
            q = q.filter(Task.department.in_(_split(department)))
        if assigned_user:
            q = q.filter(Task.assigned_user.in_(_split(assigned_user)))
        if claim_reference:
            refs = _split(claim_reference)
            q = q.filter(or_(*[Task.claim_reference.ilike(f"%{r}%") for r in refs]))
        if vehicle_registration:
            regs = _split(vehicle_registration)
            q = q.filter(or_(*[Task.vehicle_registration.ilike(f"%{r}%") for r in regs]))
        if due_from:
            q = q.filter(Task.due_date >= due_from)
        if due_to:
            q = q.filter(Task.due_date <= due_to)

        total = q.count()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        rows = (
            q.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [_to_out(t) for t in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def vehicle_options(db: Session, tenant_id: Optional[int] = None):
        """Distinct vehicle registrations across the tenant — from client
        vehicles, hire-provided vehicles AND from tasks (so a reg typed into a
        task becomes reusable)."""
        regs = set()

        vq = (
            db.query(VehicleDetail.registration)
            .join(Claim, VehicleDetail.claim_id == Claim.id)
            .filter(
                Claim.tenant_id == tenant_id,
                VehicleDetail.is_deleted == False,
                VehicleDetail.registration.isnot(None),
            )
        )
        for (r,) in vq.all():
            if r and r.strip():
                regs.add(r.strip())

        # Hire-provided (replacement) vehicles — scoped to the tenant via the claim.
        hq = (
            db.query(HireVehicleProvided.hire_vehicle_registration)
            .join(Claim, HireVehicleProvided.claim_id == Claim.id)
            .filter(
                Claim.tenant_id == tenant_id,
                HireVehicleProvided.hire_vehicle_registration.isnot(None),
            )
        )
        for (r,) in hq.all():
            if r and r.strip():
                regs.add(r.strip())

        tq = (
            TaskService._base_query(db, tenant_id)
            .with_entities(Task.vehicle_registration)
            .filter(Task.vehicle_registration.isnot(None))
        )
        for (r,) in tq.all():
            if r and r.strip():
                regs.add(r.strip())

        return sorted(regs)

    @staticmethod
    def get_stats(db: Session, tenant_id: Optional[int] = None, current_user_id: Optional[int] = None):
        # Widgets show only the current user's tasks. Assignees are stored as
        # display strings, so match the logged-in user's email prefix to the
        # assignee after normalising (same logic as list_tasks).
        def _scoped():
            q = TaskService._base_query(db, tenant_id)
            if current_user_id is not None:
                me = db.query(User).filter(User.id == current_user_id).first()
                handle = (me.user_name.split("@")[0] if me and me.user_name else "")
                norm_me = re.sub(r"[^a-z0-9]", "", handle.lower())
                norm_assignee = func.regexp_replace(
                    func.lower(func.coalesce(Task.assigned_user, "")), "[^a-z0-9]", "", "g"
                )
                q = q.filter(norm_assignee == norm_me)
            return q

        # A task past its due date shows as "Overdue" (it overrides the status
        # badge), so the Pending / In progress cards must exclude overdue tasks
        # to stay mutually exclusive with the Overdue card.
        not_overdue = or_(Task.due_date.is_(None), Task.due_date >= date.today())
        total = _scoped().count()
        pending = _scoped().filter(Task.status == "Pending", not_overdue).count()
        in_progress = _scoped().filter(Task.status == "In Progress", not_overdue).count()
        completed = _scoped().filter(Task.status == "Completed").count()
        overdue = (
            _scoped()
            .filter(
                Task.due_date.isnot(None),
                Task.due_date < date.today(),
                Task.status.notin_(_TERMINAL_STATUSES),
            )
            .count()
        )
        return {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "overdue": overdue,
            "completed": completed,
        }

    # ----- UPDATE -----
    @staticmethod
    def update_task(task_id: int, payload: TaskUpdate, db: Session, current_user):
        task = db.query(Task).filter(Task.id == task_id, Task.is_deleted == False).first()
        if not task:
            raise HTTPException(404, "Task not found")
        old_status = task.status
        old_assignee = task.assigned_user
        data = payload.dict(exclude_unset=True)
        for key, value in data.items():
            setattr(task, key, value)
        task.updated_by = current_user
        db.commit()
        db.refresh(task)

        _sync_task_due_event(db, task)

        # Assignment notifications resolve a real user account when the assignee
        # label matches one; status notifications still stay with the actor.
        from appflow.services.notification_service import safe_notify
        tenant_id = task.tenant_id
        is_high = (task.priority or "").strip().lower() == "high"
        tab = "High Priority" if is_high else "Tasks"
        category = "High Priority" if is_high else "Task"
        ref = f" ({task.claim_reference})" if task.claim_reference else ""

        from appflow.services.task_note_service import log_history

        # Reassigned.
        if "assigned_user" in data and (task.assigned_user or "") != (old_assignee or ""):
            if task.assigned_user:
                _notify_task_assigned(db, task, current_user, title="Task Reassigned")
            # Also notify + log history when the previous assignee is removed.
            if old_assignee:
                safe_notify(
                    db, recipient_user_id=current_user, tenant_id=tenant_id, actor_user_id=current_user,
                    category=category, tab=tab, title="Task Unassigned",
                    description=f"{task.title}{ref} removed from {old_assignee}.", claim_id=task.claim_id,
                    email=False,  # in-app notification only
                )
                log_history(db, task.id, current_user, "assigned", "Assignee removed", f"Removed from {old_assignee}", tenant_id)
            log_history(db, task.id, current_user, "assigned", "Task reassigned", f"Assigned to {task.assigned_user}", tenant_id)

        # Status change.
        if "status" in data and (task.status or "") != (old_status or ""):
            title = "Task Completed" if (task.status or "").strip().lower() == "completed" else "Task Status Updated"
            safe_notify(
                db, recipient_user_id=current_user, tenant_id=tenant_id, actor_user_id=current_user,
                category=category, tab=tab, title=title,
                description=f"{task.title}{ref} status changed to {task.status}.", claim_id=task.claim_id,
                email=False,  # in-app notification only — no email for task updates
            )
            log_history(db, task.id, current_user, "status", "Status changed", task.status, tenant_id)

        # Attachment changed.
        if "attachment_path" in data:
            log_history(db, task.id, current_user, "attachment", "Attachment updated", "", tenant_id)
        return _to_out(task)

    # ----- REASSIGN -----
    @staticmethod
    def reassign_task(task_id: int, payload, db: Session, current_user):
        task = db.query(Task).filter(Task.id == task_id, Task.is_deleted == False).first()
        if not task:
            raise HTTPException(404, "Task not found")
        old_assignee = task.assigned_user
        task.assigned_user = payload.new_assignee
        if payload.reason:
            prefix = (task.notes + "\n") if task.notes else ""
            task.notes = f"{prefix}Reassigned: {payload.reason}".strip()
        task.updated_by = current_user
        db.commit()
        db.refresh(task)

        # Reassign notifications resolve a real user account when the new
        # assignee label matches one.
        from appflow.services.notification_service import safe_notify
        tenant_id = task.tenant_id
        is_high = (task.priority or "").strip().lower() == "high"
        cat = "High Priority" if is_high else "Task"
        tab = "High Priority" if is_high else "Tasks"
        ref = f" ({task.claim_reference})" if task.claim_reference else ""

        if payload.notify_new:
            _notify_task_assigned(
                db,
                task,
                current_user,
                title="Task Reassigned",
                reason=payload.reason,
            )
        if payload.notify_previous and old_assignee:
            safe_notify(
                db, recipient_user_id=current_user, tenant_id=tenant_id, actor_user_id=current_user,
                category=cat, tab=tab, title="Task Reassigned",
                description=f"{task.title}{ref} reassigned from {old_assignee} to {payload.new_assignee}.",
                claim_id=task.claim_id,
            )
        from appflow.services.task_note_service import log_history
        if old_assignee:
            log_history(db, task.id, current_user, "assigned", "Assignee removed", f"Removed from {old_assignee}", tenant_id)
        log_history(db, task.id, current_user, "assigned", "Task reassigned", f"Assigned to {payload.new_assignee}", tenant_id)
        return _to_out(task)

    # ----- DELETE (soft) -----
    @staticmethod
    def delete_task(task_id: int, db: Session, current_user):
        task = db.query(Task).filter(Task.id == task_id, Task.is_deleted == False).first()
        if not task:
            raise HTTPException(404, "Task not found")
        task.is_deleted = True
        task.is_active = False
        task.updated_by = current_user
        db.commit()
        # Remove the linked system calendar event.
        try:
            from appflow.services.calendar_event_service import CalendarEventService
            CalendarEventService.sync_system_event(
                db, tenant_id=task.tenant_id, source_type="task_due", source_ref_id=task.id,
                title="", event_type="", start_date=None,
            )
        except Exception:
            db.rollback()
        return {"detail": "Task deleted"}
