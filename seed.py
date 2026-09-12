"""Populate the database with demonstration content.

Run once after installing:  python seed.py
Pass --reset to wipe existing content first.
"""
from __future__ import annotations

import sys
from datetime import timedelta

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import (
    Article, Category, Event, Level, Notification, Page, Role, Status, User, utcnow,
)
from app.security import hash_password
from app.site_settings import save_settings
from app.utils import reading_time, render_markdown, slugify

NOW = utcnow()


def days(n: int):
    return NOW + timedelta(days=n)


def make_page(title, subtitle, body, order, nav=True, **kw):
    return Page(
        title=title, slug=slugify(title), subtitle=subtitle,
        body_md=body, body_html=render_markdown(body),
        status=Status.published, show_in_nav=nav, nav_order=order, **kw,
    )


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if reset:
            for model in (Article, Event, Notification, Page, Category):
                for row in db.execute(select(model)).scalars():
                    db.delete(row)
            db.commit()

        if db.execute(select(Article).limit(1)).first():
            print("Content already present. Re-run with --reset to replace it.")
            return

        admin = db.execute(select(User).where(User.role == Role.admin)).scalars().first()
        if admin is None:
            admin = User(
                email="admin@maadhyam.local", name="Site Administrator",
                password_hash=hash_password("ChangeMe!2026"), role=Role.admin,
            )
            db.add(admin)
            db.flush()

        editor = db.execute(select(User).where(User.email == "editor@maadhyam.local")).scalars().first()
        if editor is None:
            editor = User(
                email="editor@maadhyam.local", name="Ananya Rao",
                password_hash=hash_password("EditorPass!2026"), role=Role.editor,
                bio="Mediator and trainer. Writes on commercial dispute resolution.",
            )
            db.add(editor)
            db.flush()

        # ---- Categories ---------------------------------------------------
        cats = {}
        for name, kind in [
            ("Mediation", "article"), ("Arbitration", "article"),
            ("Policy & Reform", "article"), ("Press coverage", "article"),
            ("Conference", "event"), ("Training", "event"),
            ("Roundtable", "event"), ("Webinar", "event"),
        ]:
            cat = Category(name=name, slug=slugify(name), kind=kind)
            db.add(cat)
            cats[(kind, name)] = cat
        db.flush()

        # ---- Pages --------------------------------------------------------
        db.add_all([
            make_page(
                "About us",
                "An independent institution for mediation, arbitration and everything in between.",
                """
We were founded on a simple conviction: most disputes do not need a winner. They need a
resolution that both sides can live with, reached quickly enough that the relationship survives it.

## What we do

We convene and train neutrals, administer mediation and arbitration proceedings, and work with
courts, companies and community bodies to make alternative dispute resolution a first resort
rather than a last one.

## How we work

* **Institutional rigour.** Panels are accredited, proceedings are administered, and timelines
  are enforced.
* **Practical training.** Programmes for lawyers, in-house counsel, students and community
  mediators, taught by people who sit in the chair.
* **Open knowledge.** Case notes, commentary and research published for anyone to read.

## Governance

The institution is governed by a council of practitioners, retired judges and academics.
Panels are reviewed annually, and every proceeding is administered under published rules.
""".strip(),
                10,
            ),
            make_page(
                "Services",
                "Mediation, arbitration, training and institutional support.",
                """
## Mediation

A structured, voluntary process in which a neutral third party helps disputing parties reach
their own settlement. The mediator does not decide the outcome. The parties do - which is why
mediated settlements are honoured far more often than imposed ones.

Suited to: commercial contracts, family and succession matters, employment disputes,
community and neighbourhood conflict, and court-referred matters.

## Arbitration

A formal process in which one or more arbitrators hear both sides and issue a binding, legally
enforceable award. Our panel includes senior counsel, retired judges and domain specialists.

Suited to: complex commercial disputes, construction and infrastructure claims, shareholder
disagreements, and cross-border contracts.

## Training and accreditation

Foundation and advanced programmes in mediation and arbitration practice, including a
40-hour accreditation course, advocacy workshops and continuing-education sessions.

## Institutional support

Rules drafting, panel administration, hearing facilities and secretariat services for
organisations building their own dispute resolution capability.
""".strip(),
                20,
            ),
            make_page(
                "Contact",
                "Enquiries about mediation, arbitration, training and collaborations.",
                "The secretariat responds to enquiries within two working days. "
                "For urgent matters concerning a live proceeding, call the number listed here.",
                90, nav=False,
            ),
        ])

        # ---- Events -------------------------------------------------------
        events = [
            Event(
                title="National Conference on Commercial Mediation",
                summary="Two days on what actually moves commercial disputes to settlement, "
                        "with judges, in-house counsel and practising mediators.",
                body_md="""
The conference brings together the people who decide whether mediation works in practice:
judges who refer matters, in-house counsel who authorise settlements, and the mediators who
sit between them.

### Programme

* **Day one** - Referral practice, confidentiality, and what courts expect from a mediation report.
* **Day two** - Settlement architecture in multi-party commercial disputes; enforcement of
  mediated settlement agreements.

Delegate places are limited, and priority goes to practitioners handling live matters.
""".strip(),
                start_at=days(24).replace(hour=9, minute=30, second=0, microsecond=0),
                end_at=days(25).replace(hour=17, minute=0, second=0, microsecond=0),
                mode="in_person", venue_name="India Habitat Centre", city="New Delhi",
                address="Lodhi Road, New Delhi 110003",
                organizer="Maadhyam International", capacity=180, is_free=False, price="4,500",
                category_id=cats[("event", "Conference")].id,
                speakers="Justice (Retd.) Meera Krishnan - Chair, Advisory Council\n"
                         "Rohan Mehta - General Counsel, Suryan Infrastructure\n"
                         "Ananya Rao - Accredited Mediator and Trainer",
                status=Status.published, featured=True,
            ),
            Event(
                title="40-Hour Mediation Accreditation Programme",
                summary="The full accreditation course: theory, role-plays and assessed practice, "
                        "delivered over five days.",
                body_md="""
An intensive, assessed programme covering the mediation process end to end. Participants who
complete the assessment join the Maadhyam panel of accredited mediators.

### What is covered

1. The mediation process and the mediator's role
2. Interest-based negotiation and reframing
3. Managing power imbalance and impasse
4. Drafting enforceable settlement agreements
5. Assessed role-play with feedback from two assessors

Bring a live matter (anonymised) if you have one - the final day works best with real material.
""".strip(),
                start_at=days(52).replace(hour=9, minute=0, second=0, microsecond=0),
                end_at=days(56).replace(hour=18, minute=0, second=0, microsecond=0),
                mode="in_person", venue_name="Maadhyam Training Centre", city="Mumbai",
                organizer="Maadhyam International", capacity=24, is_free=False, price="32,000",
                category_id=cats[("event", "Training")].id,
                status=Status.published,
            ),
            Event(
                title="Roundtable: Emergency Arbitration After the Amendment",
                summary="A closed-door discussion on interim relief, enforceability and what "
                        "practitioners are seeing in practice.",
                body_md="An invitation-only roundtable under the Chatham House rule. "
                        "Twenty seats, three short provocations, and two hours of argument.",
                start_at=days(11).replace(hour=17, minute=0, second=0, microsecond=0),
                end_at=days(11).replace(hour=19, minute=30, second=0, microsecond=0),
                mode="hybrid", venue_name="Maadhyam Chambers", city="New Delhi",
                online_url="https://meet.example.org/emergency-arbitration",
                organizer="Maadhyam International", capacity=20, is_free=True,
                category_id=cats[("event", "Roundtable")].id,
                status=Status.published,
            ),
            Event(
                title="Webinar: Mediation for In-House Legal Teams",
                summary="A practical hour on when to propose mediation, how to prepare the "
                        "business, and what authority the room needs.",
                body_md="Open to all. The recording is circulated to registrants afterwards.",
                start_at=days(6).replace(hour=16, minute=0, second=0, microsecond=0),
                end_at=days(6).replace(hour=17, minute=0, second=0, microsecond=0),
                mode="online", online_url="https://meet.example.org/inhouse-mediation",
                organizer="Maadhyam International", is_free=True,
                category_id=cats[("event", "Webinar")].id,
                status=Status.published,
            ),
            Event(
                title="Community Mediation Summit 2026",
                summary="Practitioners from eighteen cities on what community mediation "
                        "achieves when it is properly resourced.",
                body_md="The summit closed with a commitment to a shared training curriculum "
                        "for community mediators across participating states.",
                start_at=days(-38).replace(hour=10, minute=0, second=0, microsecond=0),
                end_at=days(-37).replace(hour=17, minute=0, second=0, microsecond=0),
                mode="in_person", venue_name="Bengaluru International Centre", city="Bengaluru",
                organizer="Maadhyam International", is_free=True,
                category_id=cats[("event", "Conference")].id,
                status=Status.published,
            ),
        ]
        for e in events:
            e.slug = slugify(e.title)
            e.body_html = render_markdown(e.body_md)
        db.add_all(events)

        # ---- Notifications -------------------------------------------------
        notices = [
            Notification(
                title="Panel applications open for the 2026-27 cycle",
                summary="Accredited mediators and arbitrators may apply to join the institutional "
                        "panel. Applications close at the end of next month.",
                body_md="Applicants must hold a recognised accreditation and demonstrate at least "
                        "ten completed proceedings. The application form, fee schedule and review "
                        "criteria are published on the panel page.\n\n"
                        "Incomplete applications will not be carried forward to the next cycle.",
                level=Level.important, pinned=True,
                link_url="/contact", link_label="Request the application pack",
                published_at=days(-3), expires_at=days(34), status=Status.published,
            ),
            Notification(
                title="Revised schedule of fees effective from the next quarter",
                summary="Administrative fees for arbitration proceedings have been revised. "
                        "Matters already registered continue on the existing schedule.",
                body_md="The revised schedule applies to matters registered on or after the first "
                        "day of the next quarter. Parties in existing proceedings are unaffected.",
                level=Level.info, published_at=days(-9), status=Status.published,
            ),
            Notification(
                title="Hearing rooms unavailable on the 14th and 15th",
                summary="Scheduled maintenance at the Delhi chambers. Listed matters have been "
                        "moved to the annexe; parties have been notified individually.",
                body_md="If you have a matter listed on either day and have not heard from the "
                        "secretariat, please contact us before the hearing date.",
                level=Level.urgent, published_at=days(-1), expires_at=days(16),
                status=Status.published,
            ),
            Notification(
                title="Annual report for 2025-26 published",
                summary="Case statistics, settlement rates, panel composition and audited accounts.",
                body_md="The report covers 512 matters administered during the year, with a "
                        "settlement rate of 94 per cent in mediated proceedings.",
                level=Level.info, published_at=days(-21), status=Status.published,
                show_in_ticker=False,
            ),
        ]
        for n in notices:
            n.slug = slugify(n.title)
            n.body_html = render_markdown(n.body_md)
        db.add_all(notices)

        # ---- Articles -------------------------------------------------------
        articles = [
            Article(
                title="Why mediated settlements hold, and imposed ones do not",
                excerpt="Compliance data tells a consistent story: people honour agreements they "
                        "helped write. That has consequences for how disputes should be routed.",
                body_md="""
There is a finding in dispute resolution research that is unusually consistent across
jurisdictions and dispute types: parties comply with settlements they negotiated at a
materially higher rate than with outcomes imposed on them.

## The mechanism is not mysterious

A mediated settlement is drafted by the people who have to live with it. They know which
clauses are workable, which deadlines are realistic, and which obligations quietly cannot be
met. An imposed award has none of that information built in.

## What follows for practice

If compliance is the objective - and for most commercial parties it is, since a paper victory
that requires two more years of enforcement is not a victory - then the routing decision
matters more than the advocacy.

> The question is not "can we win this?" but "what will actually be performed?"

### Three practical consequences

1. **Route early.** The value of mediation falls sharply once positions have been filed and
   publicly defended.
2. **Send authority into the room.** A mediation without settlement authority present is a
   scheduling exercise.
3. **Draft for performance.** Settlement terms should specify who does what, by when, and what
   happens if they do not.

None of this is an argument against arbitration. It is an argument for choosing deliberately
rather than by default.
""".strip(),
                tags="mediation, settlement, practice",
                category_id=cats[("article", "Mediation")].id,
                status=Status.published, featured=True, published_at=days(-4),
                author_id=editor.id,
            ),
            Article(
                title="Interim relief in arbitration: a practitioner's checklist",
                excerpt="Emergency arbitration is only as useful as the enforcement route behind "
                        "it. A short checklist for deciding whether to seek it.",
                body_md="""
Emergency arbitration promises speed. Whether it delivers depends almost entirely on where
you will need to enforce the resulting order.

## Before you apply

* Is the seat's law clear on the enforceability of emergency relief?
* Does the institutional rule set provide for it, and did the parties opt out?
* Would a court application at the seat be faster and more certain?

## What tribunals actually look for

Urgency has to be real and documented. A tribunal asked to grant relief on the basis of an
apprehension that has been live for six months will ask why the application waited.

## After the order

An emergency order is not self-executing. Plan the enforcement step before you apply, not
after the order issues.
""".strip(),
                tags="arbitration, interim relief, procedure",
                category_id=cats[("article", "Arbitration")].id,
                status=Status.published, published_at=days(-12), author_id=editor.id,
            ),
            Article(
                title="Pre-institution mediation is not working as intended",
                excerpt="The statutory requirement exists. Compliance is widespread. Meaningful "
                        "engagement is not. The gap between the two is the whole problem.",
                body_md="""
Mandatory pre-institution mediation was meant to divert disputes before they reached a
courtroom. In practice a substantial share of referrals are completed as a formality: a
notice issued, a date fixed, an attendance recorded, a non-starter certificate obtained.

## Where the process leaks

The referral often reaches a party who has no authority to settle, at a stage where counsel
have already drafted the plaint. Nothing about that sequence is designed to produce agreement.

## What would change the outcome

Three things, in order of impact: authority in the room, a mediator who has read the file,
and a realistic time allocation. Ninety minutes with an unprepared mediator and a junior
representative is not a mediation.
""".strip(),
                tags="policy, mediation, courts",
                category_id=cats[("article", "Policy & Reform")].id,
                status=Status.published, published_at=days(-19), author_id=editor.id,
            ),
            Article(
                title="Notes from the Community Mediation Summit",
                excerpt="Eighteen cities, one recurring theme: community mediation works when it "
                        "is resourced like an institution rather than run like a favour.",
                body_md="""
The clearest message from practitioners across eighteen cities was structural rather than
technical. Community mediation programmes do not fail because the mediators are unskilled.
They fail because nobody funds the coordination.

## What the successful programmes had in common

* A paid coordinator, not a volunteer rota
* A referral relationship with a specific institution - a court, a police station, a housing body
* Case records good enough to show outcomes to a funder

The curriculum commitment made at the close of the summit is a start. Funding the coordination
role is the harder ask.
""".strip(),
                tags="community, training, summit",
                category_id=cats[("article", "Mediation")].id,
                status=Status.published, published_at=days(-33), author_id=editor.id,
            ),
            Article(
                title="Institution publishes 2025-26 case statistics",
                excerpt="Coverage of the annual report, including settlement rates and the "
                        "composition of the arbitration panel.",
                external_url="https://example.org/coverage/annual-report-2026",
                source_name="Legal Practice Review",
                tags="press, annual report",
                category_id=cats[("article", "Press coverage")].id,
                status=Status.published, published_at=days(-26),
            ),
            Article(
                title="Draft: institutional rules review 2027",
                excerpt="Working notes on the rules review. Not for publication.",
                body_md="Internal working draft.",
                status=Status.draft, author_id=admin.id,
            ),
        ]
        for a in articles:
            a.slug = slugify(a.title)
            a.body_html = render_markdown(a.body_md)
            a.reading_minutes = reading_time(a.body_html or a.excerpt)
        db.add_all(articles)

        save_settings(db, {
            "home_hero_eyebrow": "Alternative Dispute Resolution",
            "home_hero_title": "Resolve disputes without losing the relationship.",
            "seo_default_og_image": "/static/img/og-default.svg",
        })

        db.commit()
        print("Seeded:")
        print(f"  {len(events)} events, {len(notices)} notices, {len(articles)} articles, 3 pages")
        print("  admin@maadhyam.local / ChangeMe!2026   (administrator)")
        print("  editor@maadhyam.local / EditorPass!2026 (editor)")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
