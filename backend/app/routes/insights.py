"""VP view: funnel, speed, hires vs goal, why candidates stop, by depot, and automation."""

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import (STAGE_ORDER, Actor, Candidate, CandidateStatus, Depot, Event, Message, Stage, Step, StepStatus, Task,
                      TaskStatus, now)

router = APIRouter(prefix="/api", tags=["insights"])

FUNNEL = [st for st in STAGE_ORDER if st != Stage.application]
BASELINE = {"hires_per_month": 17, "days_to_hire": 90, "goal_hires_per_month": 35}  # from John


def _aware(dt):
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


LOST = (CandidateStatus.dropped, CandidateStatus.rejected)


def _day(iso):
    from datetime import date, datetime, timezone
    return datetime.combine(date.fromisoformat(iso), datetime.min.time(), tzinfo=timezone.utc)


def filtered(s: Session, depot_id=None, recruiter_id=None, language=None, channel=None, status=None, days=None,
             applied_from=None, applied_to=None, hired_from=None, hired_to=None):
    """Shared filters (Insights + Pipeline click-through). days = applied within the last N days.
    applied_/hired_ from/to are ISO dates (to is exclusive), used by the weekly trend click-through."""
    t = now()
    cands = s.exec(select(Candidate)).all()
    if applied_from:
        cands = [c for c in cands if _day(applied_from) <= _aware(c.created_at) < _day(applied_to)]
    if hired_from:
        cands = [c for c in cands if c.stage == Stage.hired and _day(hired_from) <= _aware(c.stage_entered_at) < _day(hired_to)]
    if depot_id:
        cands = [c for c in cands if c.depot_id == depot_id]
    if recruiter_id:
        cands = [c for c in cands if c.recruiter_id == recruiter_id]
    if language:
        cands = [c for c in cands if (c.preferred_language == language) if language in ("en", "es")] if language in ("en", "es") \
            else [c for c in cands if c.preferred_language not in ("en", "es")]
    if days:
        cands = [c for c in cands if t - _aware(c.created_at) <= timedelta(days=days)]
    if status == "active":
        cands = [c for c in cands if c.status not in LOST and c.stage != Stage.hired]
    elif status == "hired":
        cands = [c for c in cands if c.stage == Stage.hired]
    elif status == "lost":
        cands = [c for c in cands if c.status in LOST]
    if channel:
        ids = {c.id for c in cands}
        called = {e.candidate_id for e in s.exec(select(Event).where(Event.type.in_(["ai_call_placed", "call_answered", "call_inbound", "nudge_sent"]))).all()
                  if e.candidate_id in ids and (e.type != "nudge_sent" or e.details.get("kind") == "call")}
        cands = [c for c in cands if (c.id in called) == (channel == "calls")]
    return cands


@router.get("/insights")
def insights(depot_id: Optional[int] = None, recruiter_id: Optional[int] = None, language: Optional[str] = None,
             channel: Optional[str] = None, status: Optional[str] = None, days: Optional[int] = None,
             applied_from: Optional[str] = None, applied_to: Optional[str] = None,
             s: Session = Depends(get_session)):
    cands = filtered(s, depot_id, recruiter_id, language, channel, status, days, applied_from, applied_to)
    ids = {c.id for c in cands}
    steps = [st for st in s.exec(select(Step)).all() if st.candidate_id in ids]
    t = now()

    # Funnel: how many candidates ever reached each stage.
    reached = defaultdict(set)
    for st in steps:
        reached[st.stage].add(st.candidate_id)
    for c in cands:
        if c.stage == Stage.hired:
            reached[Stage.hired].add(c.id)
    funnel = [{"stage": st.value, "reached": len(reached[st])} for st in FUNNEL]
    current = Counter(c.stage.value for c in cands if c.status not in (CandidateStatus.dropped, CandidateStatus.rejected))

    # Speed: median days per completed stage, and time to hire.
    per_stage = defaultdict(list)
    for st in steps:
        if st.started_at and st.completed_at and st.status == StepStatus.passed:
            per_stage[st.stage.value].append((_aware(st.completed_at) - _aware(st.started_at)).total_seconds() / 86400)
    days_per_stage = [{"stage": st.value, "median_days": round(median(per_stage[st.value]), 1) if per_stage[st.value] else None,
                       "n": len(per_stage[st.value])} for st in FUNNEL if st != Stage.hired]
    hired = [c for c in cands if c.stage == Stage.hired]
    to_hire = [(_aware(c.stage_entered_at) - _aware(c.created_at)).total_seconds() / 86400 for c in hired]
    hires_30d = sum(1 for c in hired if t - _aware(c.stage_entered_at) <= timedelta(days=30))

    # Why they stopped: drop reasons by the stage they stopped at.
    lost = [c for c in cands if c.status in (CandidateStatus.dropped, CandidateStatus.rejected)]
    drop_by_stage = defaultdict(Counter)
    for c in lost:
        drop_by_stage[c.stage.value][c.drop_reason.value if c.drop_reason else "other"] += 1
    drop_reasons = Counter(c.drop_reason.value if c.drop_reason else "other" for c in lost)

    # By depot.
    depots = {d.id: d for d in s.exec(select(Depot)).all()}
    open_tasks = Counter(tk.candidate_id for tk in s.exec(select(Task).where(Task.status == TaskStatus.open)).all())
    from ..config import STAGE_SLA_DAYS
    by_depot = defaultdict(lambda: {"applied": 0, "active": 0, "hired": 0, "hired_30d": 0, "needs_review": 0, "lost": 0, "stuck": 0, "_tth": []})
    for c in cands:
        row = by_depot[c.depot_id]
        row["applied"] += 1
        if c.status in (CandidateStatus.dropped, CandidateStatus.rejected):
            row["lost"] += 1
        elif c.stage == Stage.hired:
            row["hired"] += 1
            row["hired_30d"] += int(t - _aware(c.stage_entered_at) <= timedelta(days=30))
            row["_tth"].append((_aware(c.stage_entered_at) - _aware(c.created_at)).total_seconds() / 86400)
        else:
            row["active"] += 1
            sla = STAGE_SLA_DAYS.get(c.stage.value)
            row["stuck"] += int(bool(sla) and (t - _aware(c.stage_entered_at)).days > sla)
        row["needs_review"] += int(open_tasks.get(c.id, 0) > 0)
    depot_rows = []
    for d, v in by_depot.items():
        if d not in depots:
            continue
        tth = v.pop("_tth")
        resolved = v["hired"] + v["lost"]
        depot_rows.append({"depot_id": d, "depot": depots[d].name, "city": depots[d].city, **v,
                           "conversion": round(v["hired"] / resolved * 100, 1) if resolved else None,
                           "median_days_to_hire": round(median(tth), 1) if tth else None})
    depot_rows.sort(key=lambda r: -r["active"])

    # Automation: what the system did vs. what needed a person.
    events = [e for e in s.exec(select(Event)).all() if e.candidate_id in ids]
    auto = Counter(e.type for e in events if e.actor in (Actor.system, Actor.ai, Actor.vendor))
    touched = {e.candidate_id for e in events if e.actor == Actor.recruiter}
    advanced = {e.candidate_id for e in events if e.type == "stage_changed"}

    # Weekly trend (last 13 weeks): applications vs hires, same unit so one axis.
    weeks = []
    tomorrow = _day((t.date() + timedelta(days=1)).isoformat())  # day-aligned so click-through filters match exactly
    for w in range(12, -1, -1):
        start, end = tomorrow - timedelta(days=7 * (w + 1)), tomorrow - timedelta(days=7 * w)
        weeks.append({"week_start": start.date().isoformat(),
                      "week_end": end.date().isoformat(),
                      "applications": sum(1 for c in cands if start <= _aware(c.created_at) < end),
                      "hires": sum(1 for c in hired if start <= _aware(c.stage_entered_at) < end)})

    # Value 1: speed to first contact (measured: application -> first outbound message).
    first_out = {}
    for m in s.exec(select(Message).where(Message.direction == "out")).all():
        if m.candidate_id in ids and (m.candidate_id not in first_out or m.created_at < first_out[m.candidate_id]):
            first_out[m.candidate_id] = m.created_at
    by_id = {c.id: c for c in cands}
    gaps = [max((_aware(at) - _aware(by_id[cid].created_at)).total_seconds(), 0) for cid, at in first_out.items()]

    # Value 2: automated actions in the last 30 days (the UI multiplies by editable minutes-per-action).
    recent = [e for e in events if t - _aware(e.created_at) <= timedelta(days=30) and e.actor in (Actor.system, Actor.ai, Actor.vendor)]
    kinds = Counter()
    for e in recent:
        if e.type == "nudge_sent":
            kinds["call_follow_ups" if e.details.get("kind") == "call" else "text_follow_ups"] += 1
        elif e.type in ("bg_result_received", "drug_test_result", "skills_test_result"):
            kinds["results_processed"] += 1
        elif e.type in ("appointment_reminder", "training_reminder"):
            kinds["appointment_reminders"] += 1
        elif e.type == "screening_completed":
            kinds["screenings_completed"] += 1
        elif e.type == "stage_changed":
            kinds["stage_updates_synced"] += 1

    # Value 3: per-stage conversion among candidates who finished the stage (pass vs lost), for the what-if model.
    conv = []
    for st in FUNNEL[:-1]:
        passed = sum(1 for x in steps if x.stage == st and x.status == StepStatus.passed and x.result != None)  # noqa: E711
        lost_here = sum(drop_by_stage.get(st.value, {}).values())
        conv.append({"stage": st.value, "passed": passed, "lost": lost_here,
                     "rate": round(passed / (passed + lost_here), 3) if passed + lost_here else None})
    apps_30d = sum(1 for c in cands if t - _aware(c.created_at) <= timedelta(days=30))

    return {
        "value": {"first_contact_median_s": round(median(gaps)) if gaps else None, "first_contact_n": len(gaps),
                  "automated_30d": dict(kinds), "recruiters": len({c.recruiter_id for c in cands if c.recruiter_id}) or 6,
                  "stage_conversion": conv, "applications_30d": apps_30d},
        "trend": weeks,
        "baseline": BASELINE,
        "totals": {"candidates": len(cands), "active": sum(current.values()) - current.get("hired", 0),
                   "hired_30d": hires_30d, "lost": len(lost),
                   "median_days_to_hire": round(median(to_hire), 1) if to_hire else None},
        "funnel": funnel, "current": current, "days_per_stage": days_per_stage,
        "drop_reasons": drop_reasons.most_common(), "drop_by_stage": {k: dict(v) for k, v in drop_by_stage.items()},
        "by_depot": depot_rows,
        "automation": {"follow_ups": auto.get("nudge_sent", 0) + auto.get("ai_call_placed", 0),
                       "results_processed": auto.get("bg_result_received", 0) + auto.get("drug_test_result", 0) + auto.get("skills_test_result", 0),
                       "advanced": len(advanced), "advanced_no_recruiter": len(advanced - touched)},
    }
