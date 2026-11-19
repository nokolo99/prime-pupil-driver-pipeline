"""Sample reference data: 12 depots in one state, 6 recruiters, clinics per depot.
All names are fictional."""

from sqlmodel import Session, select

from .db import engine
from .models import Clinic, Depot, Recruiter

DEPOTS = [
    ("North Valley", "Albany"), ("Riverside", "Troy"), ("Hillcrest", "Schenectady"),
    ("Lakeview", "Saratoga Springs"), ("Eastgate", "Rensselaer"), ("Westfield", "Cohoes"),
    ("Pine Ridge", "Clifton Park"), ("Mapleton", "Glens Falls"), ("Stonebridge", "Amsterdam"),
    ("Brookside", "Hudson"), ("Cedar Point", "Kingston"), ("Oakmont", "Poughkeepsie"),
]

RECRUITERS = ["Dana Reyes", "Marcus Bell", "Priya Shah", "Tom Kowalski", "Lucia Ortega", "Jen Park"]


def seed_reference_data() -> None:
    with Session(engine) as s:
        if s.exec(select(Depot)).first():
            return  # already seeded
        depots = [Depot(name=n, city=c) for n, c in DEPOTS]
        s.add_all(depots)
        s.commit()
        for d in depots:
            s.refresh(d)

        # Each recruiter covers two depots; we record their primary one.
        for i, name in enumerate(RECRUITERS):
            s.add(Recruiter(name=name, depot_id=depots[i * 2].id))

        for d in depots:
            s.add(Clinic(name=f"{d.city} Occupational Health", address=f"120 Main St, {d.city}",
                         hours="Mon–Fri 7am–5pm, Sat 8am–12pm", depot_id=d.id))
            s.add(Clinic(name=f"{d.city} Urgent Care & DOT Testing", address=f"45 Route 9, {d.city}",
                         hours="Mon–Sun 8am–8pm", depot_id=d.id))
        s.commit()
