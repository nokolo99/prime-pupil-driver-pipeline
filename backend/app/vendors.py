"""Mock vendors (background check + drug test).

These stand in for the real vendor APIs. The rest of the system only calls these functions and
receives the same webhook-style events a real integration would send, so swapping in a real
vendor means replacing this file, not the stage logic.
"""

import secrets

from . import telephony


def _base() -> str:
    # Links are texted to candidates, so they must be public (ngrok/deploy). Falls back to local.
    return telephony.PUBLIC_URL or "http://localhost:8000"


def order_background_check(candidate_id: int) -> dict:
    """Real vendor: POST /orders → returns an order ID and a candidate-facing form link."""
    order_id = "BG-" + secrets.token_hex(3).upper()
    return {"order_id": order_id, "form_link": f"{_base()}/vendor/bg/{order_id}"}


def open_drug_test_case(candidate_id: int) -> dict:
    """Real vendor: creates a donor case → returns case ID and an authorization + booking link."""
    case_id = "DT-" + secrets.token_hex(3).upper()
    return {"case_id": case_id, "booking_link": f"{_base()}/vendor/drug/{case_id}"}


def sample_result_email(order_id: str, first_name: str, last_name: str, clear: bool) -> dict:
    """What a background-check vendor's result email looks like (used by the demo panel)."""
    status = "CLEAR" if clear else "CONSIDER"
    detail = ("No records found. Motor vehicle record: valid license, no violations in the last 7 years."
              if clear else
              "Motor vehicle record: 1 reckless driving violation (2024-03-11). Criminal: no records found. "
              "Please review before making a decision.")
    return {
        "from": "reports@checkpoint-screening.example",
        "subject": f"Report complete: {first_name} {last_name} (Order {order_id}) - {status}",
        "body": (f"Hello,\n\nThe background report you ordered is complete.\n\nCandidate: {first_name} {last_name}\n"
                 f"Order #: {order_id}\nPackage: DOT Driver (Criminal + MVR)\nOverall status: {status}\n\n"
                 f"Summary: {detail}\n\nLog in to the portal to view the full report.\n\nCheckpoint Screening"),
    }


def training_session(candidate_id: int) -> dict:
    """Stand-in for the Zoom meeting link for the candidate's training cohort."""
    code = secrets.token_hex(3).upper()
    return {"link": f"{_base()}/vendor/training/{code}"}


def skills_test(candidate_id: int) -> dict:
    """Real platform: create an assessment invite → returns test ID + candidate link."""
    test_id = "SK-" + secrets.token_hex(3).upper()
    return {"test_id": test_id, "link": f"{_base()}/vendor/skills/{test_id}"}


def offer_letter(candidate_id: int) -> dict:
    """Real e-signature provider: create an envelope → returns ID + signing link."""
    offer_id = "OF-" + secrets.token_hex(3).upper()
    return {"offer_id": offer_id, "link": f"{_base()}/vendor/offer/{offer_id}"}
