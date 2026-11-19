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
    "error": {
        "en": "Sorry, I had trouble with that. Could you send it again?",
        "es": "Perdón, tuve un problema. ¿Puedes enviarlo de nuevo?",
    },
}
