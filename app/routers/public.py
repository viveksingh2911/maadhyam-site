"""Public-facing routes."""
from __future__ import annotations

import math
import re
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import seo
from ..config import settings
from ..database import get_db
from ..models import (
    Article, Category, ContactMessage, Event, Level, Notification, Page,
    Registration, Status, Subscriber, utcnow,
)
from ..templating import render
from ..utils import summarise

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
RESERVED_SLUGS = {
    "admin", "events", "articles", "notifications", "search", "contact",
    "static", "sitemap.xml", "robots.txt", "rss.xml", "subscribe", "healthz",
}


def paginate(total: int, page: int, per_page: int) -> dict:
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "offset": (page - 1) * per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
        "window": [p for p in range(page - 2, page + 3) if 1 <= p <= pages],
    }


def published_articles(db: Session):
    return select(Article).where(
        Article.status == Status.published,
        Article.published_at <= utcnow(),
    )


def live_notifications(db: Session):
    now = utcnow()
    return select(Notification).where(
        Notification.status == Status.published,
        (Notification.starts_at.is_(None)) | (Notification.starts_at <= now),
        (Notification.expires_at.is_(None)) | (Notification.expires_at > now),
    )


# --------------------------------------------------------------------------- #
# Home
# --------------------------------------------------------------------------- #

@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    now = utcnow()

    upcoming = list(
        db.execute(
            select(Event)
            .where(Event.status == Status.published, Event.start_at >= now)
            .order_by(Event.start_at)
            .limit(3)
        ).scalars()
    )
    if not upcoming:
        upcoming = list(
            db.execute(
                select(Event)
                .where(Event.status == Status.published)
                .order_by(Event.start_at.desc())
                .limit(3)
            ).scalars()
        )

    notices = list(
        db.execute(
            live_notifications(db)
            .order_by(Notification.pinned.desc(), Notification.published_at.desc())
            .limit(4)
        ).scalars()
    )
    featured = db.execute(
        published_articles(db)
        .where(Article.featured.is_(True))
        .order_by(Article.published_at.desc())
        .limit(1)
    ).scalars().first()
    latest = list(
        db.execute(
            published_articles(db)
            .where(Article.id != (featured.id if featured else 0))
            .order_by(Article.published_at.desc())
            .limit(6)
        ).scalars()
    )

    return render(
        request, db, "public/home.html",
        upcoming=upcoming,
        notices=notices,
        featured=featured,
        latest=latest,
        breadcrumbs=[],
    )


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

@router.get("/events", response_class=HTMLResponse)
def event_index(
    request: Request,
    db: Session = Depends(get_db),
    when: str = Query("upcoming", pattern="^(upcoming|past|all)$"),
    q: str = "",
    category: str = "",
    page: int = 1,
):
    now = utcnow()
    stmt = select(Event).where(Event.status == Status.published)
    if when == "upcoming":
        stmt = stmt.where(func.coalesce(Event.end_at, Event.start_at) >= now)
    elif when == "past":
        stmt = stmt.where(func.coalesce(Event.end_at, Event.start_at) < now)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Event.title.ilike(like), Event.summary.ilike(like), Event.body_md.ilike(like)))
    if category:
        stmt = stmt.join(Category).where(Category.slug == category)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pg = paginate(total, page, settings.ITEMS_PER_PAGE)
    order = Event.start_at.asc() if when == "upcoming" else Event.start_at.desc()
    events = list(db.execute(stmt.order_by(order).offset(pg["offset"]).limit(pg["per_page"])).scalars())
    categories = list(db.execute(select(Category).where(Category.kind == "event").order_by(Category.name)).scalars())

    return render(
        request, db, "public/events.html",
        meta_spec={
            "title": {"upcoming": "Upcoming events", "past": "Past events", "all": "Events"}[when],
            "description": "Conferences, training programmes, roundtables and workshops on "
                           "mediation, arbitration and dispute resolution.",
            "path": "/events",
        },
        events=events, pg=pg, when=when, q=q, category=category, categories=categories,
        breadcrumbs=[("Home", "/"), ("Events", "/events")],
    )


@router.get("/events/{slug}", response_class=HTMLResponse)
def event_detail(slug: str, request: Request, db: Session = Depends(get_db), registered: int = 0):
    event = db.execute(select(Event).where(Event.slug == slug)).scalars().first()
    if not event or event.status != Status.published:
        raise HTTPException(status_code=404)
    related = list(
        db.execute(
            select(Event)
            .where(Event.status == Status.published, Event.id != event.id)
            .order_by(func.abs(func.julianday(Event.start_at) - func.julianday(event.start_at)))
            .limit(3)
        ).scalars()
    )
    return render(
        request, db, "public/event_detail.html",
        event=event, related=related, registered=bool(registered),
        breadcrumbs=[("Home", "/"), ("Events", "/events"), (event.title, f"/events/{event.slug}")],
    )


@router.post("/events/{slug}/register")
def event_register(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    organisation: str = Form(""),
    notes: str = Form(""),
):
    event = db.execute(select(Event).where(Event.slug == slug)).scalars().first()
    if not event or event.status != Status.published:
        raise HTTPException(status_code=404)
    if not EMAIL_RE.match(email.strip()):
        return RedirectResponse(f"/events/{slug}?error=email", status_code=303)
    db.add(Registration(
        event_id=event.id, name=name.strip(), email=email.strip().lower(),
        phone=phone.strip() or None, organisation=organisation.strip() or None,
        notes=notes.strip() or None,
    ))
    db.commit()
    return RedirectResponse(f"/events/{slug}?registered=1#register", status_code=303)


@router.get("/events/{slug}/calendar.ics")
def event_ics(slug: str, db: Session = Depends(get_db)):
    event = db.execute(select(Event).where(Event.slug == slug)).scalars().first()
    if not event or event.status != Status.published:
        raise HTTPException(status_code=404)
    end = event.end_at or (event.start_at + timedelta(hours=2))
    stamp = lambda d: d.strftime("%Y%m%dT%H%M%S")  # noqa: E731
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Maadhyam International//Events//EN",
        "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:event-{event.id}@{settings.SITE_URL.split('//')[-1]}",
        f"DTSTAMP:{stamp(utcnow())}",
        f"DTSTART:{stamp(event.start_at)}",
        f"DTEND:{stamp(end)}",
        f"SUMMARY:{event.title}",
        f"DESCRIPTION:{summarise(event.summary or event.body_html, 400)}",
        f"LOCATION:{event.online_url if event.mode == 'online' else event.location_line}",
        f"URL:{seo.absolute_url(f'/events/{event.slug}')}",
        "END:VEVENT", "END:VCALENDAR",
    ]
    return Response(
        "\r\n".join(lines),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}.ics"'},
    )


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #

@router.get("/notifications", response_class=HTMLResponse)
def notification_index(
    request: Request,
    db: Session = Depends(get_db),
    level: str = "",
    q: str = "",
    page: int = 1,
):
    stmt = live_notifications(db)
    if level in {l.value for l in Level}:
        stmt = stmt.where(Notification.level == Level(level))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Notification.title.ilike(like), Notification.summary.ilike(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pg = paginate(total, page, 12)
    notices = list(
        db.execute(
            stmt.order_by(Notification.pinned.desc(), Notification.published_at.desc())
            .offset(pg["offset"]).limit(pg["per_page"])
        ).scalars()
    )
    return render(
        request, db, "public/notifications.html",
        meta_spec={
            "title": "Notifications and notices",
            "description": "Official announcements, circulars, panel updates and notices "
                           "from Maadhyam International.",
            "path": "/notifications",
        },
        notices=notices, pg=pg, level=level, q=q, levels=[l.value for l in Level],
        breadcrumbs=[("Home", "/"), ("Notifications", "/notifications")],
    )


@router.get("/notifications/{slug}", response_class=HTMLResponse)
def notification_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    note = db.execute(select(Notification).where(Notification.slug == slug)).scalars().first()
    if not note or note.status != Status.published:
        raise HTTPException(status_code=404)
    others = list(
        db.execute(
            live_notifications(db).where(Notification.id != note.id)
            .order_by(Notification.published_at.desc()).limit(5)
        ).scalars()
    )
    return render(
        request, db, "public/notification_detail.html",
        note=note, others=others,
        breadcrumbs=[("Home", "/"), ("Notifications", "/notifications"), (note.title, f"/notifications/{note.slug}")],
    )


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #

@router.get("/articles", response_class=HTMLResponse)
def article_index(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    category: str = "",
    tag: str = "",
    page: int = 1,
):
    stmt = published_articles(db)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Article.title.ilike(like), Article.excerpt.ilike(like), Article.body_md.ilike(like)))
    if category:
        stmt = stmt.join(Category).where(Category.slug == category)
    if tag:
        stmt = stmt.where(Article.tags.ilike(f"%{tag}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pg = paginate(total, page, settings.ITEMS_PER_PAGE)
    articles = list(
        db.execute(stmt.order_by(Article.published_at.desc()).offset(pg["offset"]).limit(pg["per_page"])).scalars()
    )
    categories = list(db.execute(select(Category).where(Category.kind == "article").order_by(Category.name)).scalars())

    return render(
        request, db, "public/articles.html",
        meta_spec={
            "title": "Knowledge Lab",
            "description": "Articles, commentary and press coverage on mediation, arbitration "
                           "and alternative dispute resolution in India and beyond.",
            "path": "/articles",
        },
        articles=articles, pg=pg, q=q, category=category, tag=tag, categories=categories,
        breadcrumbs=[("Home", "/"), ("Knowledge Lab", "/articles")],
    )


@router.get("/articles/{slug}", response_class=HTMLResponse)
def article_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    article = db.execute(select(Article).where(Article.slug == slug)).scalars().first()
    if not article or article.status != Status.published:
        raise HTTPException(status_code=404)
    article.views += 1
    db.commit()

    related_stmt = published_articles(db).where(Article.id != article.id)
    if article.category_id:
        related_stmt = related_stmt.where(Article.category_id == article.category_id)
    related = list(db.execute(related_stmt.order_by(Article.published_at.desc()).limit(3)).scalars())
    if len(related) < 3:
        filler = db.execute(
            published_articles(db).where(Article.id != article.id)
            .order_by(Article.published_at.desc()).limit(3)
        ).scalars()
        seen = {a.id for a in related}
        for a in filler:
            if a.id not in seen and len(related) < 3:
                related.append(a)

    return render(
        request, db, "public/article_detail.html",
        article=article, related=related,
        breadcrumbs=[("Home", "/"), ("Knowledge Lab", "/articles"), (article.title, f"/articles/{article.slug}")],
    )


# --------------------------------------------------------------------------- #
# Search, contact, newsletter
# --------------------------------------------------------------------------- #

@router.get("/search", response_class=HTMLResponse)
def search(request: Request, db: Session = Depends(get_db), q: str = ""):
    term = q.strip()
    articles: list[Article] = []
    events: list[Event] = []
    notices: list[Notification] = []
    pages: list[Page] = []
    if term:
        like = f"%{term}%"
        articles = list(db.execute(
            published_articles(db).where(or_(Article.title.ilike(like), Article.excerpt.ilike(like), Article.body_md.ilike(like)))
            .order_by(Article.published_at.desc()).limit(10)
        ).scalars())
        events = list(db.execute(
            select(Event).where(Event.status == Status.published)
            .where(or_(Event.title.ilike(like), Event.summary.ilike(like), Event.body_md.ilike(like)))
            .order_by(Event.start_at.desc()).limit(10)
        ).scalars())
        notices = list(db.execute(
            live_notifications(db).where(or_(Notification.title.ilike(like), Notification.summary.ilike(like)))
            .order_by(Notification.published_at.desc()).limit(10)
        ).scalars())
        pages = list(db.execute(
            select(Page).where(Page.status == Status.published)
            .where(or_(Page.title.ilike(like), Page.body_md.ilike(like))).limit(5)
        ).scalars())

    total = len(articles) + len(events) + len(notices) + len(pages)
    return render(
        request, db, "public/search.html",
        meta_spec={
            "title": f'Search results for "{term}"' if term else "Search",
            "description": "Search events, notices and articles across Maadhyam International.",
            "path": "/search",
            "noindex": True,
        },
        q=term, articles=articles, events=events, notices=notices, pages=pages, total=total,
        breadcrumbs=[("Home", "/"), ("Search", "/search")],
    )


@router.get("/contact", response_class=HTMLResponse)
def contact_form(request: Request, db: Session = Depends(get_db), sent: int = 0, error: str = ""):
    page = db.execute(select(Page).where(Page.slug == "contact", Page.status == Status.published)).scalars().first()
    return render(
        request, db, "public/contact.html",
        page=page, sent=bool(sent), error=error,
        meta_spec={
            "title": "Contact us",
            "description": "Reach the Maadhyam International secretariat for mediation, "
                           "arbitration, training and speaking requests.",
            "path": "/contact",
        },
        breadcrumbs=[("Home", "/"), ("Contact", "/contact")],
    )


@router.post("/contact")
def contact_submit(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    subject: str = Form(""),
    message: str = Form(...),
    website: str = Form(""),  # honeypot
):
    if website.strip():
        return RedirectResponse("/contact?sent=1", status_code=303)
    if not EMAIL_RE.match(email.strip()) or len(message.strip()) < 10:
        return RedirectResponse("/contact?error=invalid", status_code=303)
    db.add(ContactMessage(
        name=name.strip(), email=email.strip().lower(), phone=phone.strip() or None,
        subject=subject.strip() or None, message=message.strip(),
    ))
    db.commit()
    return RedirectResponse("/contact?sent=1", status_code=303)


@router.post("/subscribe")
def subscribe(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    name: str = Form(""),
    source: str = Form("footer"),
):
    clean = email.strip().lower()
    back = _safe_return_path(request)
    if not EMAIL_RE.match(clean):
        return RedirectResponse(f"{back}?subscribe=invalid#newsletter", status_code=303)
    existing = db.execute(select(Subscriber).where(Subscriber.email == clean)).scalars().first()
    if existing:
        existing.is_active = True
    else:
        db.add(Subscriber(email=clean, name=name.strip() or None, source=source))
    db.commit()
    return RedirectResponse(f"{back}?subscribe=ok#newsletter", status_code=303)


def _safe_return_path(request: Request) -> str:
    """Same-origin path from the Referer header, falling back to the homepage.

    Never trust the header for anything but a local path, and never bounce back
    to an endpoint that only answers POST.
    """
    referer = request.headers.get("referer") or "/"
    try:
        parsed = urlparse(referer)
    except ValueError:
        return "/"
    if parsed.netloc and parsed.netloc != request.url.netloc:
        return "/"
    path = parsed.path or "/"
    if not path.startswith("/") or path in {"/subscribe", "/contact"}:
        return "/"
    return path


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# CMS pages - registered last so it never shadows a real route
# --------------------------------------------------------------------------- #

@router.get("/{slug}", response_class=HTMLResponse)
def cms_page(slug: str, request: Request, db: Session = Depends(get_db)):
    if slug in RESERVED_SLUGS:
        raise HTTPException(status_code=404)
    page = db.execute(select(Page).where(Page.slug == slug)).scalars().first()
    if not page or page.status != Status.published:
        raise HTTPException(status_code=404)
    return render(
        request, db, "public/page.html",
        page=page,
        breadcrumbs=[("Home", "/"), (page.title, f"/{page.slug}")],
    )
