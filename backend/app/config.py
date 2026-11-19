"""Business configuration. Everything here is meant to be edited by Prime Pupil's team,
not engineers. Values marked ASSUMED are placeholders until confirmed (see DESIGN.md §16)."""

import os

# Claude model used for candidate conversations. Switch to "claude-opus-5-5" to compare.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# ---------- Screening (ASSUMED, confirm in email 2, Q15) ----------
# Asked in this order. "field" is the ScreeningResult column the answer is stored in.
SCREENING_QUESTIONS = [
    {"field": "is_21_plus", "ask": "Are you 21 or older?"},
    {"field": "has_valid_license", "ask": "Do you have a valid driver's license?"},
    {"field": "years_licensed", "ask": "How many years have you had your driver's license?"},
    {"field": "recent_violations", "ask": "Any DUI, license suspension, or serious traffic violations in the last 5 years?"},
    {"field": "availability_ok", "ask": "Can you work a split shift (mornings and afternoons) during the school year?"},
    {"field": "has_cdl_or_permit", "ask": "Do you already have a CDL or a CDL learner's permit?"},
]

MIN_YEARS_LICENSED = 3  # ASSUMED

# Knockout rules: (field, check that returns True when the answer should be FLAGGED, label for recruiter).
# Flags never reject anyone. They create a review task for a recruiter.
KNOCKOUT_RULES = [
    ("is_21_plus", lambda v: v is False, "Under 21"),
    ("has_valid_license", lambda v: v is False, "No valid driver's license"),
    ("years_licensed", lambda v: v is not None and v < MIN_YEARS_LICENSED, f"Licensed under {MIN_YEARS_LICENSED} years"),
    ("recent_violations", lambda v: v is True, "Recent DUI / suspension / serious violation"),
    ("availability_ok", lambda v: v is False, "Can't work split shift"),
]

# How many times the agent may re-ask an unclear answer before flagging it for a recruiter.
MAX_CLARIFY_ATTEMPTS = 1

# ---------- Facts sheet (ASSUMED placeholders) ----------
# The agent may answer candidate questions ONLY from these facts. Anything else -> recruiter task.
FACTS = """
- Company: Prime Pupil Transportation, school bus operator with 12 depots.
- Role: School bus driver. Schedule is a split shift during the school year (morning and afternoon routes).
- Pay: ASSUMED $24/hour; paid CDL training at the same rate.
- Paid training: Yes. Prime Pupil pays for CDL training (held over Zoom, about 1 week) and the skills test.
- Requirements: 21+, valid driver's license for 3+ years, clean driving record, pass a background check and DOT drug test, obtain a CDL learner's permit.
- Experience: No CDL needed to apply. Prime Pupil helps you get one.
- Process: screening -> background check -> DOT drug test -> CDL permit -> paid training -> skills test -> offer.
- Benefits, start dates, specific route assignments: NOT in this sheet. Hand off to a recruiter.
""".strip()

# ---------- Follow-up engine ----------
# Days since the candidate's last activity -> action. "sms" sends a reminder template;
# "call" places an AI voice call (until voice ships in increment 5, it falls back to an SMS).
# Editable per stage; stages without an entry use DEFAULT_FOLLOW_UP.
DEFAULT_FOLLOW_UP = (
    [(1, "sms"), (2, "sms"), (4, "sms"), (5, "call"), (7, "sms"), (10, "sms"), (14, "sms"), (15, "call")]
    + [(d, "call" if i % 2 else "sms") for i, d in enumerate(range(21, 90, 7))]
)
FOLLOW_UP_SCHEDULE = {
    "screening": DEFAULT_FOLLOW_UP,
}
GIVE_UP_AFTER_DAYS = 90        # reminders stop; recruiter decides
QUIET_HOURS = (20, 8)          # no messages or calls from 8pm to 8am local time
LOCAL_TZ = "America/New_York"  # all depots are in one state

# Days in a stage before the candidate is highlighted as stuck on the dashboard.
STAGE_SLA_DAYS = {"screening": 3, "background_check": 7, "drug_test": 7, "cdl_permit": 14,
                  "training": 10, "skills_test": 5, "offer": 3}

# ---------- Deterministic templates for consequential messages ----------
# Exact wording is fixed (reviewable by legal / HR). Other languages are translated at send time.
TEMPLATES = {
    "intro": {
        "en": "Hi {first_name}! This is Prime Pupil's recruiting assistant. Thanks for applying to drive with us. Do you have 5 minutes for a few quick questions? Reply STOP to opt out.",
        "es": "¡Hola {first_name}! Soy el asistente de reclutamiento de Prime Pupil. Gracias por postularte para manejar con nosotros. ¿Tienes 5 minutos para unas preguntas rápidas? Responde STOP para cancelar.",
    },
    "screening_passed": {
        "en": "Great news, you passed screening! Next step: a background check. We'll text you a link shortly. It takes about 10 minutes.",
        "es": "¡Buenas noticias, pasaste la evaluación! Siguiente paso: una verificación de antecedentes. Te enviaremos un enlace en breve. Toma unos 10 minutos.",
    },
    "screening_review": {
        "en": "Thanks for your answers! A recruiter will review them and follow up within 1 business day.",
        "es": "¡Gracias por tus respuestas! Un reclutador las revisará y te contactará en 1 día hábil.",
    },
    "handoff": {
        "en": "Good question! I'll have a recruiter get back to you within 1 business day.",
        "es": "¡Buena pregunta! Un reclutador te responderá en 1 día hábil.",
    },
    "reminder_1": {
        "en": "Hi {first_name}, just checking in! You're almost done with your Prime Pupil application. Reply anytime to pick up where you left off.",
        "es": "¡Hola {first_name}! Solo para recordarte: ya casi terminas tu solicitud con Prime Pupil. Responde cuando puedas para continuar.",
    },
    "reminder_2": {
        "en": "Hi {first_name}, we'd love to keep your application moving. It only takes a few minutes. Reply to continue.",
        "es": "Hola {first_name}, nos encantaría avanzar con tu solicitud. Solo toma unos minutos. Responde para continuar.",
    },
    "reminder_3": {
        "en": "Hi {first_name}, we still have a school bus driver spot for you. Reply anytime and we'll pick up right where you left off.",
        "es": "Hola {first_name}, todavía tenemos un puesto de conductor para ti. Responde cuando quieras y seguimos donde lo dejaste.",
    },
    "call_fallback": {
        "en": "Hi {first_name}, we tried to reach you about your Prime Pupil application. Reply here anytime to continue.",
        "es": "Hola {first_name}, intentamos comunicarnos contigo sobre tu solicitud con Prime Pupil. Responde aquí cuando quieras para continuar.",
    },
    "rejected": {
        "en": "Hi {first_name}, thank you for your interest in driving with Prime Pupil. After review, we're unable to move forward with your application at this time. We wish you the best.",
        "es": "Hola {first_name}, gracias por tu interés en manejar con Prime Pupil. Después de revisarla, no podemos continuar con tu solicitud en este momento. Te deseamos lo mejor.",
    },
    "voice_greeting": {
        "en": "Hi {first_name}, this is Prime Pupil's automated recruiting assistant, calling about your school bus driver application. Para español, diga español. Do you have a few minutes to continue?",
        "es": "Hola {first_name}, soy el asistente automatizado de reclutamiento de Prime Pupil, llamando sobre tu solicitud para conductor de autobús escolar. For English, say English. ¿Tienes unos minutos para continuar?",
    },
    "voice_inbound_greeting": {
        "en": "Hi {first_name}, thanks for calling Prime Pupil. This is our automated recruiting assistant. Para español, diga español. Do you have a few minutes to continue your application?",
        "es": "Hola {first_name}, gracias por llamar a Prime Pupil. Soy el asistente automatizado de reclutamiento. For English, say English. ¿Tienes unos minutos para continuar tu solicitud?",
    },
    "voice_unknown_caller": {
        "en": "Thanks for calling Prime Pupil Transportation. To apply to drive with us, please visit our careers page. Goodbye!",
    },
    "voicemail": {
        "en": "Hi {first_name}, this is Prime Pupil's automated recruiting assistant about your school bus driver application. Call or text us back at this number anytime to pick up where you left off. Thanks!",
        "es": "Hola {first_name}, soy el asistente automatizado de reclutamiento de Prime Pupil, sobre tu solicitud para conductor de autobús escolar. Llámanos o escríbenos a este número cuando quieras para continuar. ¡Gracias!",
    },
    "voice_no_input": {
        "en": "Sorry, I didn't catch that. Could you say it again?",
        "es": "Perdón, no te escuché bien. ¿Puedes repetirlo?",
    },
    "voice_goodbye": {
        "en": "Thanks for your time. Goodbye!",
        "es": "Gracias por tu tiempo. ¡Adiós!",
    },
    "voice_later": {
        "en": "No problem. We'll follow up another time. You can also call or text us back anytime. Goodbye!",
        "es": "No hay problema. Te contactaremos en otro momento. También puedes llamarnos o escribirnos cuando quieras. ¡Adiós!",
    },
    "error": {
        "en": "Sorry, I had trouble with that. Could you send it again?",
        "es": "Perdón, tuve un problema. ¿Puedes enviarlo de nuevo?",
    },
}

# ---------- Voice ----------
VOICES = {"en": ("Polly.Joanna-Neural", "en-US"), "es": ("Polly.Lupe-Neural", "es-US")}
