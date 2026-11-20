"""Business configuration. Everything here is meant to be edited by Prime Pupil's team,
not engineers. Values marked ASSUMED are placeholders until confirmed (see DESIGN.md §16)."""

import os

# Claude model used for candidate conversations. Switch to "claude-opus-5-5" to compare.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
# Live phone calls need fast replies; Haiku is much quicker and the code still makes every decision.
CLAUDE_MODEL_VOICE = os.getenv("CLAUDE_MODEL_VOICE", "claude-haiku-5-5")

# ---------- Screening (from John, email 2) ----------
# Asked in this order. "field" is the ScreeningResult column the answer is stored in.
SCREENING_QUESTIONS = [
    {"field": "is_21_plus", "ask": "Are you 21 or older?"},
    {"field": "years_licensed", "ask": "How many years have you had your driver's license?"},
    {"field": "dui_past_7_years", "ask": "Have you had a DUI in the past 7 years?"},
    {"field": "willing_drug_test", "ask": "Are you willing to take a DOT drug test?"},
]

MIN_YEARS_LICENSED = 3

# John: any one of these is an automatic fail. We still never reject by text: a flag creates a
# recruiter review task (John also said a recruiter reviews before anyone is rejected).
KNOCKOUT_RULES = [
    ("is_21_plus", lambda v: v is False, "Under 21"),
    ("years_licensed", lambda v: v is not None and v < MIN_YEARS_LICENSED, f"Licensed under {MIN_YEARS_LICENSED} years"),
    ("dui_past_7_years", lambda v: v is True, "DUI in the past 7 years"),
    ("willing_drug_test", lambda v: v is False, "Not willing to take a drug test"),
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
- Requirements: 21+, driver's license for 3+ years, no DUI in the past 7 years, pass a background check and DOT drug test, obtain a CDL learner's permit.
- Experience: No CDL needed to apply. Prime Pupil helps you get one.
- Process: screening -> background check -> DOT drug test -> paid CDL training (while you get your CDL learner's permit) -> skills test -> offer. Your recruiter verifies your permit before the offer.
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
    "background_check": DEFAULT_FOLLOW_UP,  # nudging to finish the vendor form (John's #1 holdup)
    "drug_test": DEFAULT_FOLLOW_UP,         # nudging to book / go to the clinic (biggest drop-off)
    "cdl_permit": DEFAULT_FOLLOW_UP,        # runs alongside training; stops when they say they have it
    "skills_test": DEFAULT_FOLLOW_UP,
    "offer": DEFAULT_FOLLOW_UP,             # nudging to sign
}

# ---------- Later stages (ASSUMED placeholders) ----------
DMV_PERMIT_LINK = "https://dmv.ny.gov/commercial-drivers/get-commercial-learner-permit-clp"  # one state; NY assumed
TRAINING_WEEKDAY, TRAINING_HOUR = 0, 10     # weekly cohort: Mondays 10am local
OFFER_TERMS = {"title": "School Bus Driver", "pay_rate": "$24.00/hour", "schedule": "Split shift, school year",
               "start": "the Monday after you sign"}
# Vendor turnaround before results are flagged as overdue (FYI to recruiter, no action required).
RESULTS_OVERDUE_DAYS = {"background_check": 5, "drug_test": 5}
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
        "en": "Great news, you passed screening!",
        "es": "¡Buenas noticias, pasaste la evaluación!",
    },
    "screening_review": {
        "en": "Thanks for your answers! A recruiter will review them and follow up soon.",
        "es": "¡Gracias por tus respuestas! Un reclutador las revisará y te contactará pronto.",
    },
    "handoff": {
        "en": "Good question! A recruiter will get back to you soon.",
        "es": "¡Buena pregunta! Un reclutador te responderá pronto.",
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
        "en": "Hi {first_name}! I'm Prime Pupil's automated recruiting assistant, calling about your bus driver application. Got a few minutes? Puedes hablarme en español.",
        "es": "¡Hola {first_name}! Soy el asistente automatizado de reclutamiento de Prime Pupil, llamando por tu solicitud de conductor. ¿Tienes unos minutos? You can also speak English.",
    },
    "voice_inbound_greeting": {
        "en": "Hi {first_name}, thanks for calling Prime Pupil. This is our automated recruiting assistant. Do you have a few minutes to continue your application? Puedes hablarme en español si prefieres.",
        "es": "Hola {first_name}, gracias por llamar a Prime Pupil. Soy el asistente automatizado de reclutamiento. ¿Tienes unos minutos para continuar tu solicitud? You can also speak to me in English.",
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
    "bg_start": {
        "en": "Next step: a background check. Please fill out this short form (about 10 minutes): {link}",
        "es": "Siguiente paso: una verificación de antecedentes. Llena este formulario corto (unos 10 minutos): {link}",
    },
    "bg_reminder": {
        "en": "Hi {first_name}, your background check form is the next step to driving with Prime Pupil. It takes about 10 minutes: {link}",
        "es": "Hola {first_name}, tu formulario de antecedentes es el siguiente paso para manejar con Prime Pupil. Toma unos 10 minutos: {link}",
    },
    "bg_form_received": {
        "en": "Thanks {first_name}, we got your background check form! Results usually take 3 to 5 days. We'll text you as soon as they're in.",
        "es": "¡Gracias {first_name}, recibimos tu formulario! Los resultados suelen tardar de 3 a 5 días. Te avisaremos en cuanto lleguen.",
    },
    "bg_clear": {
        "en": "Good news {first_name}, your background check came back clear!",
        "es": "¡Buenas noticias {first_name}, tu verificación de antecedentes salió bien!",
    },
    "under_review": {
        "en": "Thanks {first_name}. A recruiter is reviewing your results and will follow up soon.",
        "es": "Gracias {first_name}. Un reclutador está revisando tus resultados y te contactará pronto.",
    },
    "drug_start": {
        "en": "Next step: a quick DOT drug test (about 15 min). Here's your authorization: {link}\nWalk in at any of these clinics with a photo ID:\n{clinics}\nWhen are you planning to go?",
        "es": "Siguiente paso: una prueba de drogas DOT (unos 15 min). Aquí está tu autorización: {link}\nVe sin cita a cualquiera de estas clínicas con identificación con foto:\n{clinics}\n¿Cuándo piensas ir?",
    },
    "drug_reminder": {
        "en": "Hi {first_name}, your drug test is the next step. Walk in at any nearby clinic with your authorization: {link} When do you think you can go?",
        "es": "Hola {first_name}, tu prueba de drogas es el siguiente paso. Ve sin cita a una clínica cercana con tu autorización: {link} ¿Cuándo crees que puedes ir?",
    },
    "drug_booked": {
        "en": "Got it: {when} at {clinic}. Bring a photo ID and your authorization. We'll remind you the day before.",
        "es": "Perfecto: {when} en {clinic}. Lleva identificación con foto y tu autorización. Te recordaremos un día antes.",
    },
    "drug_day_before": {
        "en": "Reminder: you're planning to do your drug test tomorrow ({when}) at {clinic}. Bring a photo ID and your authorization: {link}",
        "es": "Recordatorio: planeas hacer tu prueba de drogas mañana ({when}) en {clinic}. Lleva identificación con foto y tu autorización: {link}",
    },
    "drug_morning_of": {
        "en": "Today's the day! Walk in at {clinic} for your drug test. Bring a photo ID and your authorization. It only takes about 15 minutes.",
        "es": "¡Hoy es el día! Ve a {clinic} para tu prueba de drogas. Lleva identificación con foto y tu autorización. Solo toma unos 15 minutos.",
    },
    "drug_no_show": {
        "en": "Hi {first_name}, looks like you didn't make it in for your drug test. No problem! When would work better for you?",
        "es": "Hola {first_name}, parece que no pudiste ir a tu prueba de drogas. ¡No hay problema! ¿Cuándo te funcionaría mejor?",
    },
    "drug_collected": {
        "en": "Thanks for going in, {first_name}! Results usually take 2 to 5 days. We'll text you when they're in.",
        "es": "¡Gracias por ir, {first_name}! Los resultados suelen tardar de 2 a 5 días. Te avisaremos cuando lleguen.",
    },
    "drug_negative": {
        "en": "Great news {first_name}, you passed your drug test!",
        "es": "¡Buenas noticias {first_name}, pasaste tu prueba de drogas!",
    },
    "permit_start": {
        "en": "While you train, get your CDL learner's permit: book your DMV knowledge test here: {link} Just text us when you have it.",
        "es": "Mientras entrenas, saca tu permiso de aprendiz CDL: reserva tu examen del DMV aquí: {link} Avísanos por mensaje cuando lo tengas.",
    },
    "permit_reminder": {
        "en": "Hi {first_name}, have you gotten your CDL learner's permit yet? Book your DMV test here: {link} Text us once you have it!",
        "es": "Hola {first_name}, ¿ya sacaste tu permiso de aprendiz CDL? Reserva tu examen del DMV aquí: {link} ¡Avísanos cuando lo tengas!",
    },
    "permit_photo_request": {
        "en": "Last step before your offer, {first_name}: please text us a clear photo of the front of your CDL learner's permit so your recruiter can verify it.",
        "es": "Último paso antes de tu oferta, {first_name}: mándanos una foto clara del frente de tu permiso de aprendiz CDL para que tu reclutador lo verifique.",
    },
    "permit_received": {
        "en": "Got your permit photo, thanks {first_name}! A recruiter will confirm it shortly.",
        "es": "¡Recibimos la foto de tu permiso, gracias {first_name}! Un reclutador lo confirmará en breve.",
    },
    "permit_new_photo": {
        "en": "Hi {first_name}, we couldn't confirm your permit from that photo. Could you text a clear photo of the front of your CDL learner's permit?",
        "es": "Hola {first_name}, no pudimos confirmar tu permiso con esa foto. ¿Puedes mandar una foto clara del frente de tu permiso de aprendiz CDL?",
    },
    "training_start": {
        "en": "Next step: paid CDL training on Zoom, starting {when}. Join here: {link}",
        "es": "Siguiente paso: entrenamiento CDL pagado por Zoom, empieza {when}. Únete aquí: {link}",
    },
    "training_day_before": {
        "en": "Reminder: your paid CDL training starts tomorrow, {when}. Join here: {link}",
        "es": "Recordatorio: tu entrenamiento CDL pagado empieza mañana, {when}. Únete aquí: {link}",
    },
    "training_morning_of": {
        "en": "Training starts today at {time}! Join on Zoom here: {link}",
        "es": "¡El entrenamiento empieza hoy a las {time}! Únete por Zoom aquí: {link}",
    },
    "skills_start": {
        "en": "Training complete, great work {first_name}! Last step before your offer: the CDL skills test. Start here: {link}",
        "es": "¡Terminaste el entrenamiento, buen trabajo {first_name}! Último paso antes de tu oferta: el examen de habilidades CDL. Empieza aquí: {link}",
    },
    "skills_reminder": {
        "en": "Hi {first_name}, you're one step from your offer! Take your CDL skills test here: {link}",
        "es": "Hola {first_name}, ¡estás a un paso de tu oferta! Haz tu examen de habilidades CDL aquí: {link}",
    },
    "skills_retest": {
        "en": "Hi {first_name}, you're cleared for another try at the skills test. Take it here when you're ready: {link}",
        "es": "Hola {first_name}, puedes intentar otra vez el examen de habilidades. Hazlo aquí cuando estés listo: {link}",
    },
    "offer_start": {
        "en": "Congratulations {first_name}! You passed your skills test, and we'd love to have you drive with Prime Pupil. Review and sign your offer here: {link}",
        "es": "¡Felicidades {first_name}! Pasaste tu examen de habilidades y queremos que manejes con Prime Pupil. Revisa y firma tu oferta aquí: {link}",
    },
    "offer_reminder": {
        "en": "Hi {first_name}, your Prime Pupil driver offer is waiting for you. Review and sign here: {link}",
        "es": "Hola {first_name}, tu oferta de conductor con Prime Pupil te está esperando. Revísala y fírmala aquí: {link}",
    },
    "hired": {
        "en": "Welcome to Prime Pupil, {first_name}! Your offer is signed. Your recruiter will reach out with your start details and route.",
        "es": "¡Bienvenido a Prime Pupil, {first_name}! Tu oferta está firmada. Tu reclutador te contactará con los detalles de inicio y tu ruta.",
    },
    "call_heads_up": {
        "en": "Hi {first_name}! Thanks for applying to drive with Prime Pupil. We'll call you in a moment from this number to ask a few quick questions.",
        "es": "¡Hola {first_name}! Gracias por postularte para manejar con Prime Pupil. Te llamaremos en un momento desde este número para hacerte unas preguntas rápidas.",
    },
    "call_dropped": {
        "en": "Looks like we got cut off, {first_name}! Just {left} left. Reply here to finish, or say \"call me\" and we'll call you back.",
        "es": "¡Parece que se cortó la llamada, {first_name}! Solo te queda(n) {left}. Responde aquí para terminar, o di \"llámame\" y te volvemos a llamar.",
    },
    "voice_link_texted": {
        "en": "I just texted you the link for your next step.",
        "es": "Te acabo de enviar por mensaje el enlace para tu siguiente paso.",
    },
    "voice_greeting_stage": {
        "en": "Hi {first_name}! I'm Prime Pupil's automated recruiting assistant, calling about your next step: {step}. Do you have a minute?",
        "es": "¡Hola {first_name}! Soy el asistente automatizado de reclutamiento de Prime Pupil, llamando por tu siguiente paso: {step}. ¿Tienes un minuto?",
    },
    "error": {
        "en": "Sorry, I had trouble with that. Could you send it again?",
        "es": "Perdón, tuve un problema. ¿Puedes enviarlo de nuevo?",
    },
}

# ---------- Voice ----------
# Streaming calls (Twilio ConversationRelay): ElevenLabs speaks, Deepgram listens.
# language="multi" lets Deepgram detect English/Spanish automatically.
RELAY_TTS_PROVIDER = "ElevenLabs"
# One native voice per language (ElevenLabs v4). Replies are tagged with a language, and Twilio
# uses the matching voice, so Spanish is spoken by a native Spanish voice, not an English one.
# One bilingual voice for both languages, so the same "person" speaks even when the caller switches.
# (Previous per-language defaults: en UgBBYS2sOqTuMpoF3BR0, es uDhfdG2VwEjWZ4JYzggn.)
BILINGUAL_VOICE = os.getenv("RELAY_VOICE", "9Godp7dNohUvXk6qp0gS-v4")
RELAY_VOICES = {
    "en": ("en-US", os.getenv("RELAY_VOICE_EN", BILINGUAL_VOICE)),
    "es": ("es-US", os.getenv("RELAY_VOICE_ES", BILINGUAL_VOICE)),
}
RELAY_TRANSCRIPTION_PROVIDER = "Deepgram"
RELAY_LANGUAGE = "multi"
# <Say> voices for the short non-conversational bits (voicemail, unknown caller).
VOICES = {"en": ("Polly.Joanna-Neural", "en-US"), "es": ("Polly.Lupe-Neural", "es-US")}


# ---------- Workday mapping (ASSUMED step names; IT confirms their business process) ----------
WORKDAY_STEPS = {
    "application": "Review", "screening": "Screen", "background_check": "Background Check",
    "drug_test": "Assessment: DOT Drug Test", "training": "Assessment: CDL Training",
    "skills_test": "Assessment: Skills Test", "offer": "Offer", "hired": "Ready for Hire",
}
WORKDAY_DISPOSITIONS = {
    "failed_knockout": "Does Not Meet Minimum Qualifications", "failed_background_check": "Background Check Not Cleared",
    "failed_drug_test": "Drug Screen Not Cleared", "no_response": "Candidate Unresponsive",
    "took_another_job": "Accepted Other Offer", "withdrew": "Candidate Withdrew", "other": "Other",
}

# ---------- Reminder variations (rotated so repeated reminders don't read the same) ----------
# Version 1 is the first reminder; later reminders cycle 2 -> 3 -> 4. Tone: friendly -> helpful -> encouraging -> door's open.
TEMPLATES.update({
    "reminder_4": {
        "en": "Hi {first_name}, your spot is still open with Prime Pupil. Reply anytime and we'll finish your application together.",
        "es": "Hola {first_name}, tu lugar sigue abierto en Prime Pupil. Responde cuando quieras y terminamos tu solicitud juntos.",
    },
    "bg_reminder_2": {
        "en": "Hi {first_name}, just checking in: we're still waiting on your background check form. Any questions? Just reply here. {link}",
        "es": "Hola {first_name}, solo para saber: todavía esperamos tu formulario de antecedentes. ¿Preguntas? Responde aquí. {link}",
    },
    "bg_reminder_3": {
        "en": "{first_name}, you're so close! Your background check form is the only thing holding up your next step. 10 minutes: {link}",
        "es": "¡{first_name}, ya casi! Tu formulario de antecedentes es lo único que falta para tu siguiente paso. 10 minutos: {link}",
    },
    "bg_reminder_4": {
        "en": "Hi {first_name}, we'd still love to have you drive with Prime Pupil. Your background check form is ready whenever you are: {link}",
        "es": "Hola {first_name}, nos encantaría que manejes con Prime Pupil. Tu formulario de antecedentes está listo cuando quieras: {link}",
    },
    "drug_reminder_2": {
        "en": "Hi {first_name}, we're still waiting on your drug test. It's a walk-in, about 15 minutes at a clinic near you. Questions? Just reply. {link}",
        "es": "Hola {first_name}, todavía esperamos tu prueba de drogas. Vas sin cita, unos 15 minutos en una clínica cercana. ¿Preguntas? Responde. {link}",
    },
    "drug_reminder_3": {
        "en": "{first_name}, the drug test is the last step before paid CDL training! Which day works for you to walk in? {link}",
        "es": "¡{first_name}, la prueba de drogas es el último paso antes del entrenamiento CDL pagado! ¿Qué día puedes ir? {link}",
    },
    "drug_reminder_4": {
        "en": "Hi {first_name}, your spot is still open. Walk in for your drug test whenever you're ready: {link}",
        "es": "Hola {first_name}, tu lugar sigue abierto. Ve a hacer tu prueba de drogas cuando estés listo: {link}",
    },
    "permit_reminder_2": {
        "en": "Hi {first_name}, how's the CDL permit going? The DMV knowledge test covers the CDL manual. Reply if you have questions. {link}",
        "es": "Hola {first_name}, ¿cómo va el permiso CDL? El examen del DMV cubre el manual CDL. Responde si tienes preguntas. {link}",
    },
    "permit_reminder_3": {
        "en": "{first_name}, you'll need your CDL learner's permit before your offer. Booking the DMV test now keeps you on track: {link}",
        "es": "{first_name}, necesitas tu permiso de aprendiz CDL antes de tu oferta. Reservar el examen ahora te mantiene a tiempo: {link}",
    },
    "permit_reminder_4": {
        "en": "Hi {first_name}, just text us once you have your CDL permit. Here's the DMV link again: {link}",
        "es": "Hola {first_name}, avísanos cuando tengas tu permiso CDL. Aquí está el enlace del DMV otra vez: {link}",
    },
    "skills_reminder_2": {
        "en": "Hi {first_name}, we're still waiting on your skills test. It's the last step before your offer. Questions? Just reply. {link}",
        "es": "Hola {first_name}, todavía esperamos tu examen de habilidades. Es el último paso antes de tu oferta. ¿Preguntas? Responde. {link}",
    },
    "skills_reminder_3": {
        "en": "{first_name}, you're almost there! Finish your skills test and your offer is next: {link}",
        "es": "¡{first_name}, ya casi! Termina tu examen de habilidades y sigue tu oferta: {link}",
    },
    "skills_reminder_4": {
        "en": "Hi {first_name}, your skills test is ready whenever you are: {link}",
        "es": "Hola {first_name}, tu examen de habilidades está listo cuando quieras: {link}",
    },
    "offer_reminder_2": {
        "en": "Hi {first_name}, your offer is still waiting. Any questions about pay or schedule? Just reply. {link}",
        "es": "Hola {first_name}, tu oferta sigue esperando. ¿Preguntas sobre el pago o el horario? Responde. {link}",
    },
    "offer_reminder_3": {
        "en": "{first_name}, we can't wait to have you on the road! Sign your offer here: {link}",
        "es": "¡{first_name}, queremos verte en el camino pronto! Firma tu oferta aquí: {link}",
    },
    "offer_reminder_4": {
        "en": "Hi {first_name}, your Prime Pupil offer is still open. Sign whenever you're ready: {link}",
        "es": "Hola {first_name}, tu oferta con Prime Pupil sigue abierta. Firma cuando estés listo: {link}",
    },
})

# Which template keys make up each stage's rotating reminder.
REMINDER_SETS = {
    "screening": ["reminder_1", "reminder_2", "reminder_3", "reminder_4"],
    "background_check": ["bg_reminder", "bg_reminder_2", "bg_reminder_3", "bg_reminder_4"],
    "drug_test": ["drug_reminder", "drug_reminder_2", "drug_reminder_3", "drug_reminder_4"],
    "cdl_permit": ["permit_reminder", "permit_reminder_2", "permit_reminder_3", "permit_reminder_4"],
    "skills_test": ["skills_reminder", "skills_reminder_2", "skills_reminder_3", "skills_reminder_4"],
    "offer": ["offer_reminder", "offer_reminder_2", "offer_reminder_3", "offer_reminder_4"],
}


def reminder_key(stage: str, attempt: int) -> str:
    """1st reminder uses version 1; later ones cycle 2 -> 3 -> 4."""
    keys = REMINDER_SETS[stage]
    return keys[0] if attempt <= 1 else keys[1 + (attempt - 2) % (len(keys) - 1)]


# ---------- Reminder channel policy (product decision, not configurable) ----------
# Reminders relay information people need to keep (links, clinics, what to bring), so they go by TEXT.
# The only follow-up calls are in screening, where a conversation collects answers. Candidates can also call in anytime.
SCREENING_REMINDER_CALLS = {"first": 5, "every": 14}
