"""Realistic demo data: ~150 days of history (so the 13-week trend shows a steady state, not a warm-up) across 12 depots, generated through the real data model.

Volume and drop-off shape follow John's numbers (~300 applicants/month, drug test is the
biggest drop-off). Phone numbers use the reserved fictional 555-01XX range, which
telephony.py never texts or calls. Everything here is labeled demo data (source="demo_seed").
"""

import random
from datetime import timedelta

from sqlmodel import Session, select

from . import vendors
from .config import DEFAULT_FOLLOW_UP
from .models import (Actor, BackgroundCheck, Candidate, CandidateStatus, Clinic, Depot, DrugTest, DropReason, Event,
                     Message, Offer, PermitCheck, Recruiter, ScreeningResult, SkillsTest, Stage, Step, StepResult,
                     StepStatus, Task, Training, TrainingSheetRow, now)

FIRST = ["James", "Maria", "Robert", "Linda", "Michael", "Patricia", "David", "Barbara", "William", "Susan", "Richard",
         "Karen", "Joseph", "Nancy", "Thomas", "Lisa", "Charles", "Betty", "Daniel", "Sandra", "Kevin", "Donna", "Brian",
         "Carol", "Gary", "Sharon", "Tyrone", "Keisha", "Andre", "Tamika", "Wei", "Priya", "Omar", "Fatima", "Dmitri"]
FIRST_ES = ["José", "María", "Luis", "Ana", "Carlos", "Rosa", "Juan", "Carmen", "Miguel", "Lucía", "Jorge", "Elena",
            "Pedro", "Isabel", "Ricardo", "Gabriela", "Fernando", "Sofía", "Héctor", "Marisol", "Raúl", "Yolanda"]
LAST = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Anderson", "Taylor", "Thomas",
        "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Clark", "Lewis", "Walker", "Hall", "Young",
        "Allen", "King", "Wright", "Scott", "Green", "Baker", "Nguyen", "Patel", "Kim", "Okafor", "Ivanova", "Haddad"]
LAST_ES = ["García", "Rodríguez", "Martínez", "Hernández", "López", "González", "Pérez", "Sánchez", "Ramírez", "Torres",
           "Flores", "Rivera", "Gómez", "Díaz", "Reyes", "Morales", "Cruz", "Ortiz", "Gutiérrez", "Chávez"]
AREA_CODES = ["518", "315", "607", "716", "845", "914", "585", "631", "347", "929", "680", "838", "212", "646", "718", "516"]

# (stage, duration days (min, mode, max), drop probability, drop reasons)
PATH = [
    (Stage.screening, (0.1, 0.6, 4), 0.45, [DropReason.failed_knockout, DropReason.no_response, DropReason.took_another_job]),
    (Stage.background_check, (3, 6, 15), 0.30, [DropReason.no_response, DropReason.failed_background_check, DropReason.took_another_job]),
    (Stage.drug_test, (3, 7, 18), 0.55, [DropReason.no_response, DropReason.failed_drug_test, DropReason.took_another_job, DropReason.withdrew]),
    (Stage.training, (6, 8, 14), 0.42, [DropReason.withdrew, DropReason.no_response]),  # incl. never getting the permit (parallel track)
    (Stage.skills_test, (1, 3, 6), 0.10, [DropReason.other, DropReason.withdrew]),
    (Stage.offer, (0.5, 1.5, 5), 0.06, [DropReason.withdrew, DropReason.took_another_job]),
]
REVIEW_TASKS = {Stage.screening: ("review_knockout", "Screening flags: Licensed under 3 years"),
                Stage.background_check: ("review_background_flag", "Background check needs review: 1 speeding violation (2023)"),
                Stage.drug_test: ("review_drug_result", "Drug test result: non-negative"),
                Stage.offer: ("review_permit", "Verify CDL permit before offer (details match)"),
                Stage.skills_test: ("review_skills_test", "Skills test failed (score 64): allow a retest?")}


def _phones():
    nums = [f"+1{ac}55501{n:02d}" for ac in AREA_CODES for n in range(100)]
    random.shuffle(nums)
    return iter(nums)


def seed_demo(s: Session, n: int = 1500, days: int = 150, seed: int = 7) -> dict:
    random.seed(seed)
    t_now = now()
    depots = s.exec(select(Depot)).all()
    recruiters = s.exec(select(Recruiter)).all()
    clinics = {d.id: s.exec(select(Clinic).where(Clinic.depot_id == d.id)).all() for d in depots}
    phones = _phones()
    counts = {"hired": 0, "active": 0, "dropped": 0}

    for _ in range(n):
        spanish = random.random() < 0.33
        depot = random.choice(depots)
        rec = recruiters[(depot.id - 1) // 2 % len(recruiters)]
        t = t_now - timedelta(days=random.uniform(0, days))
        c = Candidate(first_name=random.choice(FIRST_ES if spanish else FIRST), last_name=random.choice(LAST_ES if spanish else LAST),
                      phone=next(phones), preferred_language="es" if spanish else "en", depot_id=depot.id,
                      recruiter_id=rec.id, source="demo_seed", workday_id=f"WD-{random.randint(10000, 99999)}",
                      sms_consent_at=t, created_at=t, stage=Stage.screening, stage_entered_at=t)
        s.add(c)
        s.flush()
        ev = lambda type_, at, actor=Actor.system, **d: s.add(Event(candidate_id=c.id, type=type_, actor=actor, details=d, created_at=at))
        ev("applied", t, source="workday")
        s.add(Message(candidate_id=c.id, direction="out", channel="sms", sender="system", created_at=t,
                      body=f"Hi {c.first_name}! This is Prime Pupil's recruiting assistant. Thanks for applying to drive with us."))

        outcome = "hired"
        for i, (stage, (lo, mode, hi), p_drop, reasons) in enumerate(PATH):
            dur = random.triangular(lo, hi, mode)
            step = Step(candidate_id=c.id, stage=stage, started_at=t, status=StepStatus.not_started)
            s.add(step)
            s.flush()
            c.stage, c.stage_entered_at = stage, t
            if t + timedelta(days=dur) > t_now:          # still in this stage today
                outcome = "active"
                _make_current(s, c, step, stage, t, t_now, clinics.get(depot.id, []), ev)
                break
            end = t + timedelta(days=dur)
            for k, (d, kind) in enumerate([x for x in DEFAULT_FOLLOW_UP if x[0] < dur][:6]):  # follow-ups that kept them moving
                ev("nudge_sent", t + timedelta(days=d), attempt=k + 1, stage=stage.value, kind=kind)
            if random.random() < p_drop:                    # lost at this stage
                outcome = "dropped"
                reason = random.choice(reasons)
                step.status, step.result, step.completed_at = StepStatus.failed, StepResult.fail, end
                c.status = CandidateStatus.rejected if reason.value.startswith("failed") else CandidateStatus.dropped
                c.drop_reason = reason
                ev("recruiter_rejected" if c.status == CandidateStatus.rejected else "recruiter_marked_dropped", end,
                   actor=Actor.recruiter, reason=reason.value)
                break
            step.status, step.result, step.completed_at = StepStatus.passed, StepResult.pass_, end
            result_event = {Stage.background_check: ("bg_result_received", {"status": "clear"}),
                            Stage.drug_test: ("drug_test_result", {"result": "negative"}),
                            Stage.skills_test: ("skills_test_result", {"result": "pass"})}.get(stage)
            if result_event:
                ev(result_event[0], end, actor=Actor.vendor, **result_event[1])
            if stage == Stage.screening:
                ev("screening_completed", end, result="pass")
                s.add(ScreeningResult(step_id=step.id, is_21_plus=True, has_valid_license=True, years_licensed=random.randint(3, 25),
                                      dui_past_7_years=False, willing_drug_test=True))
            nxt = PATH[i + 1][0] if i + 1 < len(PATH) else Stage.hired
            ev("stage_changed", end, **{"from": stage.value, "to": nxt.value})
            if stage == Stage.offer:  # hired: permit was verified before the offer
                _permit(s, c, t - timedelta(days=12), verified_at=t - timedelta(days=0.3))
            t = end
        if outcome == "hired":
            c.stage, c.stage_entered_at, c.status = Stage.hired, t, CandidateStatus.hired
        counts[outcome] += 1
    s.commit()
    return counts


def _permit(s, c, started, verified_at=None, self_reported=False, photo_requested=False):
    """The CDL permit is a parallel track that starts with training."""
    st = Step(candidate_id=c.id, stage=Stage.cdl_permit, started_at=started,
              status=StepStatus.passed if verified_at else StepStatus.in_progress if self_reported else StepStatus.waiting_on_candidate,
              result=StepResult.pass_ if verified_at else None, completed_at=verified_at)
    s.add(st)
    s.flush()
    s.add(PermitCheck(step_id=st.id, verified_at=verified_at, self_reported_at=started + timedelta(days=5) if (self_reported or verified_at) else None,
                      photo_requested_at=now() - timedelta(hours=6) if photo_requested else None))
    return st


def _make_current(s, c, step, stage, entered, t_now, clinics, ev):
    """Candidate is in this stage right now: create the detail rows the live system expects."""
    idle = (t_now - entered).total_seconds() / 86400
    step.status, c.status = StepStatus.waiting_on_candidate, CandidateStatus.waiting_on_candidate
    # Pretend the follow-ups that would have fired already did (no backlog when the engine starts).
    sent = [(d, kind) for d, kind in DEFAULT_FOLLOW_UP if d <= idle]
    step.nudge_count = len(sent)
    if sent:
        step.last_nudged_at = entered + timedelta(days=sent[-1][0])
    for k, (d, kind) in enumerate(sent):
        ev("nudge_sent", entered + timedelta(days=d), attempt=k + 1, stage=stage.value, kind=kind)

    if stage == Stage.screening:
        s.add(ScreeningResult(step_id=step.id))
    elif stage == Stage.background_check:
        o = vendors.order_background_check(c.id)
        done = random.random() < 0.45
        s.add(BackgroundCheck(step_id=step.id, vendor_order_id=o["order_id"], form_link=o["form_link"],
                              report_status="in_progress" if done else "form_pending",
                              form_completed_at=entered + timedelta(days=min(idle, random.uniform(0.5, 4))) if done else None))
        if done:
            step.status, c.status = StepStatus.waiting_on_vendor, CandidateStatus.waiting_on_vendor
    elif stage == Stage.drug_test:
        o = vendors.open_drug_test_case(c.id)
        booked = random.random() < 0.5 and clinics
        s.add(DrugTest(step_id=step.id, vendor_case_id=o["case_id"], booking_link=o["booking_link"], auth_sent_at=entered,
                       clinic_id=random.choice(clinics).id if booked else None,
                       appointment_at=(t_now + timedelta(days=random.randint(1, 4), hours=random.choice([1, 3, 5]))) if booked else None))
    elif stage == Stage.training:
        step.status, c.status = StepStatus.in_progress, CandidateStatus.in_progress
        start = entered + timedelta(days=2)
        s.add(Training(step_id=step.id, cohort_start=start, session_link=vendors.training_session(c.id)["link"]))
        s.add(TrainingSheetRow(candidate_id=c.id, trainee=f"{c.first_name} {c.last_name}", cohort=start.strftime("Week of %b %-d"),
                               completed=False, processed=False))
        _permit(s, c, entered, self_reported=random.random() < 0.4)
    elif stage == Stage.skills_test:
        tst = vendors.skills_test(c.id)
        s.add(SkillsTest(step_id=step.id, test_id=tst["test_id"], test_link=tst["link"], attempts=1))
        _permit(s, c, entered - timedelta(days=8), self_reported=random.random() < 0.7)
    elif stage == Stage.offer:
        if random.random() < 0.5:  # still waiting on the permit photo / recruiter verification
            _permit(s, c, entered - timedelta(days=12), self_reported=True, photo_requested=True)
        else:
            _permit(s, c, entered - timedelta(days=12), verified_at=entered)
            o = vendors.offer_letter(c.id)
            s.add(Offer(step_id=step.id, offer_id=o["offer_id"], sign_link=o["link"], sent_at=entered,
                        terms={"title": "School Bus Driver", "pay_rate": "$24.00/hour"}))

    if stage in REVIEW_TASKS and random.random() < 0.07:   # a few need a human
        type_, reason = REVIEW_TASKS[stage]
        c.status = CandidateStatus.needs_review
        s.add(Task(candidate_id=c.id, type=type_, reason=reason, priority=1, assigned_recruiter_id=c.recruiter_id, created_at=entered))
