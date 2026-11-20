"""Data model. Mirrors DESIGN.md §10.

Each class is both a database table and the shape the API returns.
Step is the general table the stage engine works on; ScreeningResult,
BackgroundCheck and DrugTest hold step-specific details (1:1 with a Step).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    """Current time, including the demo clock offset (see clock.py). All timestamps go through here."""
    from .clock import offset
    return datetime.now(timezone.utc) + offset()


# ---------- Enums ----------

class Stage(str, Enum):
    """Strict order, per John."""
    application = "application"
    screening = "screening"
    background_check = "background_check"
    drug_test = "drug_test"
    cdl_permit = "cdl_permit"
    training = "training"
    skills_test = "skills_test"
    offer = "offer"
    hired = "hired"


STAGE_ORDER = list(Stage)


class CandidateStatus(str, Enum):
    """What's happening right now (separate from where they are)."""
    in_progress = "in_progress"              # system is acting
    waiting_on_candidate = "waiting_on_candidate"
    waiting_on_vendor = "waiting_on_vendor"
    needs_review = "needs_review"            # a recruiter must act
    dropped = "dropped"
    rejected = "rejected"
    hired = "hired"


class StepStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    waiting_on_candidate = "waiting_on_candidate"
    waiting_on_vendor = "waiting_on_vendor"
    passed = "passed"
    failed = "failed"


class StepResult(str, Enum):
    pass_ = "pass"
    fail = "fail"
    flag = "flag"  # flag -> recruiter review


class DropReason(str, Enum):
    no_response = "no_response"
    failed_knockout = "failed_knockout"
    failed_background_check = "failed_background_check"
    failed_drug_test = "failed_drug_test"
    withdrew = "withdrew"
    took_another_job = "took_another_job"
    other = "other"


class Channel(str, Enum):
    sms = "sms"
    whatsapp = "whatsapp"
    voice = "voice"
    web = "web"  # browser chat simulator


class Sender(str, Enum):
    candidate = "candidate"
    ai = "ai"
    system = "system"
    recruiter = "recruiter"


class Actor(str, Enum):
    system = "system"
    ai = "ai"
    recruiter = "recruiter"
    candidate = "candidate"
    vendor = "vendor"


class TaskStatus(str, Enum):
    open = "open"
    resolved = "resolved"


# ---------- Lookups ----------

class Depot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str


class Recruiter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    depot_id: Optional[int] = Field(default=None, foreign_key="depot.id")


class Clinic(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    address: str
    hours: str
    depot_id: int = Field(foreign_key="depot.id")


# ---------- Core ----------

class Candidate(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    first_name: str
    last_name: str = ""
    phone: str = Field(index=True)
    email: Optional[str] = None
    preferred_language: str = "en"          # en, es, ...
    preferred_channel: Channel = Channel.sms
    depot_id: Optional[int] = Field(default=None, foreign_key="depot.id")
    recruiter_id: Optional[int] = Field(default=None, foreign_key="recruiter.id")
    source: str = "career_page"

    stage: Stage = Stage.application
    status: CandidateStatus = CandidateStatus.in_progress  # convenience copy, kept in sync by the engine
    stage_entered_at: datetime = Field(default_factory=now)

    last_contacted_at: Optional[datetime] = None
    last_reply_at: Optional[datetime] = None

    drop_reason: Optional[DropReason] = None
    drop_note: Optional[str] = None

    sms_consent_at: Optional[datetime] = None
    opted_out: bool = False

    workday_id: Optional[str] = None  # set when synced to Workday
    created_at: datetime = Field(default_factory=now)


class Step(SQLModel, table=True):
    """General step record. The stage engine only looks at this table."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    stage: Stage
    status: StepStatus = StepStatus.not_started
    due_at: Optional[datetime] = None        # when the engine considers this step stuck
    nudge_count: int = 0
    last_nudged_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[StepResult] = None
    flag_note: Optional[str] = None          # FYI for recruiters, e.g. "Results overdue" (no action required)


# ---------- Step details (1:1 with Step) ----------

class ScreeningResult(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    is_21_plus: Optional[bool] = None
    has_valid_license: Optional[bool] = None
    years_licensed: Optional[float] = None
    recent_violations: Optional[bool] = None
    violations_note: Optional[str] = None
    availability_ok: Optional[bool] = None
    has_cdl_or_permit: Optional[bool] = None
    dui_past_7_years: Optional[bool] = None
    willing_drug_test: Optional[bool] = None
    knockout_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    unclear_counts: dict = Field(default_factory=dict, sa_column=Column(JSON))  # clarification attempts per field


class BackgroundCheck(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    vendor_order_id: Optional[str] = None
    form_link: Optional[str] = None
    form_completed_at: Optional[datetime] = None
    report_status: str = "ordered"   # ordered, form_pending, in_progress, clear, consider
    report_received_at: Optional[datetime] = None
    flags: Optional[str] = None


class DrugTest(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    booking_link: Optional[str] = None
    auth_sent_at: Optional[datetime] = None
    auth_signed_at: Optional[datetime] = None
    clinic_id: Optional[int] = Field(default=None, foreign_key="clinic.id")
    appointment_at: Optional[datetime] = None
    no_show_count: int = 0
    reminded_day_before: bool = False
    reminded_morning_of: bool = False
    collected_at: Optional[datetime] = None
    vendor_case_id: Optional[str] = None
    result: Optional[str] = None     # negative, non_negative, cancelled
    result_received_at: Optional[datetime] = None


# ---------- Activity ----------

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    direction: str                    # in / out
    channel: Channel
    sender: Sender
    body: str
    language: Optional[str] = None
    translation_en: Optional[str] = None  # shown to recruiters under non-English messages
    provider_id: Optional[str] = None     # Twilio message/call ID
    delivery: Optional[str] = None        # sent / failed (retried by the engine) / skipped
    attempts: int = 0
    created_at: datetime = Field(default_factory=now)


class Event(SQLModel, table=True):
    """Timeline + audit trail + 'Handled for you'."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    type: str                          # applied, stage_changed, nudge_sent, result_received, ...
    actor: Actor
    actor_id: Optional[int] = None     # which recruiter, if any
    details: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class Task(SQLModel, table=True):
    """'Needs you today'."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    type: str                          # review_knockout, review_drug_result, candidate_unresponsive, ...
    reason: str                        # human-readable, shown to the recruiter
    priority: int = 2                  # 1 = high, 3 = low
    status: TaskStatus = TaskStatus.open
    assigned_recruiter_id: Optional[int] = Field(default=None, foreign_key="recruiter.id")
    resolution: Optional[str] = None
    resolved_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


# ---------- System ----------

class Setting(SQLModel, table=True):
    """Small key/value store (e.g. the demo clock offset)."""
    key: str = Field(primary_key=True)
    value: str


class WorkdayOutbox(SQLModel, table=True):
    """Transactional outbox for Workday writes: recorded in the same save as the change, delivered right
    after (and retried) by workday.dispatch_outbox(). Workday being slow or down never blocks a candidate."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    workday_id: Optional[str] = None    # Workday Job Application ID
    action: str                         # Workday operation: Move_Candidate, Offer
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "pending"             # pending / sent / failed / skipped
    attempts: int = 0
    response: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


# ---------- Later-stage details (1:1 with Step) ----------

class PermitCheck(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    self_reported_at: Optional[datetime] = None   # candidate said they have it (stops reminders)
    photo_requested_at: Optional[datetime] = None  # asked before the offer, for recruiter verification
    image_path: Optional[str] = None
    extracted: dict = Field(default_factory=dict, sa_column=Column(JSON))  # what Claude read off the photo
    mismatches: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    received_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None


class Training(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    cohort_start: Optional[datetime] = None
    session_link: Optional[str] = None
    reminded_day_before: bool = False
    reminded_morning_of: bool = False
    completed_at: Optional[datetime] = None


class SkillsTest(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    test_id: Optional[str] = None
    test_link: Optional[str] = None
    attempts: int = 0
    result: Optional[str] = None      # pass / fail
    score: Optional[int] = None
    result_received_at: Optional[datetime] = None


class Offer(SQLModel, table=True):
    step_id: int = Field(foreign_key="step.id", primary_key=True)
    offer_id: Optional[str] = None
    sign_link: Optional[str] = None
    terms: dict = Field(default_factory=dict, sa_column=Column(JSON))
    sent_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    declined_at: Optional[datetime] = None


class TrainingSheetRow(SQLModel, table=True):
    """Stand-in for the trainer's shared spreadsheet (prod: their Google Sheet / Excel, read via API)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: int = Field(foreign_key="candidate.id", index=True)
    trainee: str
    cohort: str
    completed: bool = False
    marked_at: Optional[datetime] = None
    processed: bool = False   # our watcher has acted on the "completed" mark


# ---------- Fake Workday (stand-in for Prime Pupil's Workday tenant) ----------

class MockWorkdayApplication(SQLModel, table=True):
    """A candidate + job application as they'd exist in Workday Recruiting."""
    id: Optional[int] = Field(default=None, primary_key=True)
    candidate_id: str = Field(index=True)        # Workday Candidate ID, e.g. CAND-001234
    job_application_id: str = Field(index=True)  # Workday Job Application ID
    job_requisition_id: str                       # one open requisition per depot
    first_name: str
    last_name: str = ""
    phone: str
    email: Optional[str] = None
    preferred_language: str = "en"               # career-site application question (assumed custom question)
    sms_consent: bool = True                      # career-site application question (assumed)
    contact_channel: str = "sms"                  # demo convenience: sms / whatsapp
    first_contact: str = "text"                   # career-site question: "How should we reach you first?" text / call
    current_step: str = "Review"                  # Workday recruiting step
    disposition: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
