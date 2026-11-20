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
            if stage != Stage.screening or random.random() < 0.85:
                c.last_reply_at = t + timedelta(hours=random.uniform(0.2, 6))  # they replied as they started this step
            if t + timedelta(days=dur) > t_now:          # still in this stage today
                if random.random() < 0.45:  # some are engaged mid-stage (questions, booking); others have gone quiet
                    c.last_reply_at = min(t_now, t + timedelta(days=random.uniform(0, max((t_now - t).days, 0.5))))
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
            if stage in REVIEW_TASKS and random.random() < 0.025:  # a result that needed a human look, then approved
                ev("recruiter_approved", end, actor=Actor.recruiter, task_type=REVIEW_TASKS[stage][0])
            if stage == Stage.screening:
                ev("screening_completed", end, result="pass")
                s.add(ScreeningResult(step_id=step.id, is_21_plus=True, has_valid_license=True, years_licensed=random.randint(3, 25),
                                      dui_past_7_years=False, willing_drug_test=True))
            nxt = PATH[i + 1][0] if i + 1 < len(PATH) else Stage.hired
            ev("stage_changed", end, **{"from": stage.value, "to": nxt.value})
            if stage == Stage.offer:  # hired: permit was verified before the offer
                _permit(s, c, t - timedelta(days=12), verified_at=t - timedelta(days=0.3))
                ev("permit_verified", t - timedelta(days=0.3), actor=Actor.recruiter)
                ev("offer_sent", t)
            t = end
        if outcome == "hired":
            c.stage, c.stage_entered_at, c.status = Stage.hired, t, CandidateStatus.hired
        counts[outcome] += 1
    seed_showcase(s, t_now, depots, recruiters, clinics)
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
            ev("permit_verified", entered, actor=Actor.recruiter)
            ev("offer_sent", entered)
            o = vendors.offer_letter(c.id)
            s.add(Offer(step_id=step.id, offer_id=o["offer_id"], sign_link=o["link"], sent_at=entered,
                        terms={"title": "School Bus Driver", "pay_rate": "$24.00/hour"}))

    if stage in REVIEW_TASKS and random.random() < 0.07:   # a few need a human
        type_, reason = REVIEW_TASKS[stage]
        c.status = CandidateStatus.needs_review
        s.add(Task(candidate_id=c.id, type=type_, reason=reason, priority=1, assigned_recruiter_id=c.recruiter_id, created_at=entered))


# ---------- Showcase candidates: realistic conversations + recent activity for the demo ----------

def permit_png(c) -> bytes:
    """A fake CDL learner's permit with this candidate's name (demo only)."""
    import io
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (860, 540), (233, 240, 247))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 860, 90], fill=(23, 63, 115))
    d.text((30, 25), "NEW YORK STATE  ·  COMMERCIAL LEARNER PERMIT", fill="white", font_size=30)
    d.rectangle([30, 120, 250, 400], fill=(190, 200, 210))
    d.text((80, 250), "PHOTO", fill=(110, 120, 130), font_size=28)
    lines = [("CLP", "Class B   ·   Endorsements: P, S"), ("NAME", f"{c.last_name.upper()}, {c.first_name.upper()}"),
             ("ID NO", f"CLP-{c.id:03d}-{c.phone[-4:]}-77"), ("DOB", "01/01/1980"),
             ("ISSUED", now().strftime("%m/%d/%Y")), ("EXPIRES", (now() + timedelta(days=180)).strftime("%m/%d/%Y"))]
    for i, (k, v) in enumerate(lines):
        d.text((290, 125 + i * 48), k, fill=(90, 100, 110), font_size=18)
        d.text((400, 120 + i * 48), v, fill=(20, 20, 20), font_size=28)
    d.text((30, 470), "SAMPLE FOR PROTOTYPE DEMO · NOT A REAL DOCUMENT", fill=(160, 40, 40), font_size=20)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def seed_showcase(s: Session, t_now, depots, recruiters, clinics) -> None:
    """Four hand-written candidates with full conversations, so the recruiter views have real history to show.
    Fictional 203-555-01XX numbers (never texted). Removed with the rest of the demo data."""
    from zoneinfo import ZoneInfo
    from .stages import UPLOADS
    H = lambda h: timedelta(hours=h)
    depot, rec = depots[0], recruiters[0]

    def cand(first, last, n, lang, applied, stage, status, last_reply):
        c = Candidate(first_name=first, last_name=last, phone=f"+12035550{n:03d}", preferred_language=lang,
                      preferred_channel="whatsapp", depot_id=depot.id, recruiter_id=rec.id, source="demo_seed",
                      workday_id=f"WD-{random.randint(10000, 99999)}", sms_consent_at=applied, created_at=applied,
                      stage=stage, stage_entered_at=applied, status=status, last_reply_at=last_reply)
        s.add(c)
        s.flush()
        return c

    def step(c, stage, start, end=None, status=None):
        st = Step(candidate_id=c.id, stage=stage, started_at=start, completed_at=end,
                  status=status or (StepStatus.passed if end else StepStatus.waiting_on_candidate),
                  result=StepResult.pass_ if end else None)
        s.add(st)
        s.flush()
        return st

    def thread(c, items):
        """items: (time, 'in'/'out', text, english-or-None)"""
        for at, d, body, en in items:
            s.add(Message(candidate_id=c.id, direction=d, channel="whatsapp", sender="candidate" if d == "in" else "ai",
                          body=body, language=c.preferred_language, translation_en=en, created_at=at,
                          delivery="simulated" if d == "out" else None))

    def ev(c, type_, at, actor=Actor.system, **d):
        s.add(Event(candidate_id=c.id, type=type_, actor=actor, details=d, created_at=at))

    def passed_screening(c, at):
        st = step(c, Stage.screening, at, at + H(0.3))
        s.add(ScreeningResult(step_id=st.id, is_21_plus=True, has_valid_license=True, years_licensed=12,
                              dui_past_7_years=False, willing_drug_test=True))
        ev(c, "screening_completed", at + H(0.3), result="pass")

    # 1) María Hernández (Spanish): drug test, walk-in planned for Monday morning. Fully automated so far.
    a = t_now - timedelta(days=6, hours=3)
    m = cand("María", "Hernández", 101, "es", a, Stage.drug_test, CandidateStatus.waiting_on_candidate, t_now - H(3))
    ev(m, "applied", a, source="workday")
    passed_screening(m, a)
    bg = vendors.order_background_check(m.id)
    st = step(m, Stage.background_check, a + H(0.3), t_now - timedelta(days=1))
    s.add(BackgroundCheck(step_id=st.id, vendor_order_id=bg["order_id"], form_link=bg["form_link"], report_status="clear",
                          form_completed_at=a + H(20), report_received_at=t_now - timedelta(days=1)))
    ev(m, "stage_changed", a + H(0.3), **{"from": "screening", "to": "background_check"})
    ev(m, "bg_result_received", t_now - timedelta(days=1), actor=Actor.vendor, status="clear")
    ev(m, "stage_changed", t_now - timedelta(days=1), **{"from": "background_check", "to": "drug_test"})
    dt = vendors.open_drug_test_case(m.id)
    tz = ZoneInfo("America/New_York")
    local = t_now.astimezone(tz)
    monday = (local + timedelta(days=(7 - local.weekday()) % 7 or 7)).replace(hour=10, minute=0, second=0, microsecond=0)
    st = step(m, Stage.drug_test, t_now - timedelta(days=1))
    s.add(DrugTest(step_id=st.id, vendor_case_id=dt["case_id"], booking_link=dt["booking_link"],
                   auth_sent_at=t_now - timedelta(days=1), appointment_at=monday.astimezone(ZoneInfo("UTC"))))
    ev(m, "drug_visit_planned", t_now - H(3), actor=Actor.candidate, day="lunes", time_of_day="morning")
    thread(m, [
        (a, "out", "¡Hola María! Soy el asistente de reclutamiento de Prime Pupil. Gracias por postularte para manejar con nosotros. ¿Tienes unos minutos para unas preguntas rápidas?",
         "Hi María! I'm Prime Pupil's recruiting assistant. Thanks for applying to drive with us. Do you have a few minutes for some quick questions?"),
        (a + H(0.1), "in", "Sí, claro", "Yes, of course"),
        (a + H(0.11), "out", "¡Perfecto! Primera pregunta: ¿tienes 21 años o más?", "Perfect! First question: are you 21 or older?"),
        (a + H(0.13), "in", "Sí, tengo 34", "Yes, I'm 34"),
        (a + H(0.14), "out", "Gracias. ¿Cuántos años tienes con tu licencia de manejar?", "Thanks. How many years have you had your driver's license?"),
        (a + H(0.17), "in", "Como 12 años", "About 12 years"),
        (a + H(0.18), "out", "Muy bien. ¿Has tenido algún DUI en los últimos 7 años?", "Great. Have you had a DUI in the past 7 years?"),
        (a + H(0.2), "in", "No, nunca", "No, never"),
        (a + H(0.21), "out", "¿Estás dispuesta a hacerte una prueba de drogas DOT?", "Are you willing to take a DOT drug test?"),
        (a + H(0.25), "in", "Sí", "Yes"),
        (a + H(0.3), "out", f"¡Buenas noticias, pasaste la evaluación! Siguiente paso: una verificación de antecedentes. Llena este formulario corto (unos 10 minutos): {bg['form_link']}",
         "Good news, you passed screening! Next step: a background check. Fill out this short form (about 10 minutes)."),
        (a + H(20), "out", "¡Gracias María, recibimos tu formulario! Los resultados suelen tardar de 3 a 5 días. Te escribimos en cuanto lleguen.",
         "Thanks María, we got your form! Results usually take 3 to 5 days. We'll text you as soon as they're in."),
        (t_now - timedelta(days=1), "out", "¡Buenas noticias María, tu verificación de antecedentes salió limpia!", "Good news María, your background check came back clear!"),
        (t_now - timedelta(days=1) + H(0.01), "out", f"Siguiente paso: una prueba de drogas DOT rápida (unos 15 min). Firma tu autorización aquí: {dt['booking_link']} y pasa sin cita a cualquier clínica de la red. ¿Qué día te queda bien?",
         "Next step: a quick DOT drug test (about 15 min). Sign your authorization here and walk in at any clinic in the network. What day works for you?"),
        (t_now - H(3), "in", "¿Puedo ir el lunes en la mañana?", "Can I go Monday morning?"),
        (t_now - H(2.99), "out", "¡Claro! Te anoté para el lunes en la mañana. Te mando un recordatorio el día anterior.",
         "Of course! I've got you down for Monday morning. I'll send you a reminder the day before."),
    ])

    # 2) James Carter: everything passed, offer ready, only waiting on the recruiter to verify his permit photo.
    a = t_now - timedelta(days=24)
    j = cand("James", "Carter", 102, "en", a, Stage.offer, CandidateStatus.needs_review, t_now - H(2))
    ev(j, "applied", a, source="workday")
    passed_screening(j, a)
    for i, (stg, nxt, d0, d1) in enumerate([(Stage.background_check, "drug_test", 0.3, 5), (Stage.drug_test, "training", 5, 9),
                                             (Stage.training, "skills_test", 9, 20), (Stage.skills_test, "offer", 20, 23.9)]):
        step(j, stg, a + timedelta(days=d0), a + timedelta(days=d1))
        ev(j, "stage_changed", a + timedelta(days=d1), **{"from": stg.value, "to": nxt})
    step(j, Stage.offer, t_now - H(3), status=StepStatus.waiting_on_candidate)
    pst = step(j, Stage.cdl_permit, a + timedelta(days=9), status=StepStatus.in_progress)
    UPLOADS.mkdir(exist_ok=True)
    name = f"permit_demo_{j.id}.png"
    (UPLOADS / name).write_bytes(permit_png(j))
    s.add(PermitCheck(step_id=pst.id, self_reported_at=a + timedelta(days=15), photo_requested_at=t_now - H(3), image_path=name,
                      extracted={"name": "CARTER, JAMES", "class": "B", "endorsements": "P, S"}, mismatches=[], received_at=t_now - H(2)))
    ev(j, "permit_photo_received", t_now - H(2), actor=Actor.candidate, mismatches=[])
    s.add(Task(candidate_id=j.id, type="review_permit", reason="Verify CDL permit before offer (details match)", priority=2,
               assigned_recruiter_id=rec.id, created_at=t_now - H(2)))
    thread(j, [
        (a, "out", "Hi James! I'm Prime Pupil's recruiting assistant. Thanks for applying to drive with us. Got a few minutes for some quick questions?", None),
        (a + H(0.05), "in", "Sure", None),
        (a + H(0.3), "out", "Great news, you passed screening! Next step: a short background check form (about 10 minutes).", None),
        (a + timedelta(days=5), "out", "Good news James, your background check came back clear! Next: a quick DOT drug test. Walk in at any clinic in the network. What day works?", None),
        (a + timedelta(days=5, hours=1), "in", "I can go Thursday after work", None),
        (a + timedelta(days=5, hours=1.01), "out", "You're down for Thursday evening. I'll remind you the day before.", None),
        (a + timedelta(days=9), "out", "You passed your drug test! Next: paid CDL training on Zoom. While you train, get your CDL learner's permit at the DMV.", None),
        (a + timedelta(days=15), "in", "Just got my permit!", None),
        (a + timedelta(days=15, hours=0.01), "out", "Congratulations, James! Your recruiter will ask to see a photo of it before your offer.", None),
        (a + timedelta(days=20), "out", "Training complete, great work James! Last step before your offer: the CDL skills test.", None),
        (t_now - H(3), "out", "Last step before your offer, James: please text us a clear photo of the front of your CDL learner's permit.", None),
        (t_now - H(2), "in", "[photo]", None),
        (t_now - H(1.99), "out", "Got your permit photo, thanks James! A recruiter will confirm it shortly.", None),
    ])

    # 3) Tasha Williams: went quiet after the form link, follow-ups brought her back. Now waiting on the vendor.
    a = t_now - timedelta(days=5)
    w = cand("Tasha", "Williams", 103, "en", a, Stage.background_check, CandidateStatus.waiting_on_vendor, t_now - timedelta(hours=20))
    ev(w, "applied", a, source="workday")
    passed_screening(w, a)
    bg = vendors.order_background_check(w.id)
    st = step(w, Stage.background_check, a + H(0.3), status=StepStatus.waiting_on_vendor)
    st.nudge_count = 2
    s.add(BackgroundCheck(step_id=st.id, vendor_order_id=bg["order_id"], form_link=bg["form_link"], report_status="in_progress",
                          form_completed_at=t_now - H(19)))
    ev(w, "stage_changed", a + H(0.3), **{"from": "screening", "to": "background_check"})
    ev(w, "nudge_sent", a + timedelta(days=1), attempt=1, stage="background_check", kind="sms")
    ev(w, "nudge_sent", a + timedelta(days=3), attempt=2, stage="background_check", kind="sms")
    thread(w, [
        (a, "out", "Hi Tasha! I'm Prime Pupil's recruiting assistant. Thanks for applying to drive with us. Got a few minutes for some quick questions?", None),
        (a + H(0.1), "in", "yes", None),
        (a + H(0.3), "out", f"Great news, you passed screening! Next step: a background check. Fill out this short form (about 10 minutes): {bg['form_link']}", None),
        (a + timedelta(days=1), "out", f"Hi Tasha, quick reminder: your background check form is the next step (about 10 minutes): {bg['form_link']}", None),
        (a + timedelta(days=3), "out", f"Hi Tasha, just checking in! You're one form away from the next step. Here's the link again: {bg['form_link']}", None),
        (t_now - H(20), "in", "Sorry, been busy with work! Doing it now", None),
        (t_now - H(19.99), "out", "No problem, thanks Tasha!", None),
        (t_now - H(19), "out", "Thanks Tasha, we got your background check form! Results usually take 3 to 5 days. We'll text you as soon as they're in.", None),
    ])

    # 4) Luis Ramírez (Spanish): mid-screening, asked something the AI can't answer, so it's on the recruiter's list.
    a = t_now - H(5)
    l = cand("Luis", "Ramírez", 104, "es", a, Stage.screening, CandidateStatus.waiting_on_candidate, t_now - H(4.5))
    ev(l, "applied", a, source="workday")
    st = step(l, Stage.screening, a)
    s.add(ScreeningResult(step_id=st.id, is_21_plus=True, has_valid_license=True, years_licensed=4))
    s.add(Task(candidate_id=l.id, type="candidate_question", priority=2, assigned_recruiter_id=rec.id, created_at=t_now - H(4.5),
               reason="Question for recruiter: “Do you offer health insurance if I work part-time?”"))
    thread(l, [
        (a, "out", "¡Hola Luis! Soy el asistente de reclutamiento de Prime Pupil. Gracias por postularte para manejar con nosotros. ¿Tienes unos minutos para unas preguntas rápidas?",
         "Hi Luis! I'm Prime Pupil's recruiting assistant. Thanks for applying to drive with us. Do you have a few minutes for some quick questions?"),
        (a + H(0.1), "in", "Hola, sí", "Hi, yes"),
        (a + H(0.11), "out", "¡Perfecto! ¿Tienes 21 años o más?", "Perfect! Are you 21 or older?"),
        (a + H(0.15), "in", "Sí, tengo 27", "Yes, I'm 27"),
        (a + H(0.16), "out", "Gracias. ¿Cuántos años tienes con tu licencia de manejar?", "Thanks. How many years have you had your driver's license?"),
        (a + H(0.3), "in", "4 años. ¿Dan seguro médico si trabajo medio tiempo?", "4 years. Do you offer health insurance if I work part-time?"),
        (a + H(0.31), "out", "Buena pregunta. No tengo esa información, pero un reclutador te va a responder pronto. Mientras tanto: ¿has tenido algún DUI en los últimos 7 años?",
         "Good question. I don't have that information, but a recruiter will get back to you soon. In the meantime: have you had a DUI in the past 7 years?"),
    ])
