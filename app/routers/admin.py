"""Admin portal: authentication, content management, media, settings and SEO health."""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import seo
from ..config import settings
from ..database import get_db
from ..models import (
    Article, Category, ContactMessage, Event, Level, Media, Notification, Page,
    Registration, Role, Status, Subscriber, User, utcnow,
)
from ..security import (
    authenticate, csrf_ok, current_user, hash_password, issue_csrf_token,
    make_session_token,
)
from ..site_settings import DEFAULTS, GROUPS, load_settings, save_settings
from ..templating import templates
from ..utils import (
    is_allowed_upload, parse_dt, reading_time, render_markdown, save_upload,
    summarise, unique_slug,
)

router = APIRouter(prefix="/admin")


# --------------------------------------------------------------------------- #
# Auth plumbing
# --------------------------------------------------------------------------- #

def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=307, headers={"Location": f"/admin/login?next={request.url.path}"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def admin_render(request: Request, db: Session, user: User, template: str, **extra):
    context = {
        "request": request,
        "user": user,
        "cfg": load_settings(db),
        "csrf_token": issue_csrf_token(request),
        "counts": sidebar_counts(db),
        "active": extra.pop("active", ""),
    }
    context.update(extra)
    return templates.TemplateResponse(request, template, context)


def sidebar_counts(db: Session) -> dict:
    return {
        "events": db.scalar(select(func.count()).select_from(Event)) or 0,
        "articles": db.scalar(select(func.count()).select_from(Article)) or 0,
        "notifications": db.scalar(select(func.count()).select_from(Notification)) or 0,
        "pages": db.scalar(select(func.count()).select_from(Page)) or 0,
        "media": db.scalar(select(func.count()).select_from(Media)) or 0,
        "subscribers": db.scalar(select(func.count()).select_from(Subscriber)) or 0,
        "messages_unread": db.scalar(
            select(func.count()).select_from(ContactMessage).where(ContactMessage.is_read.is_(False))
        ) or 0,
        "registrations": db.scalar(select(func.count()).select_from(Registration)) or 0,
    }


def guard_csrf(request: Request, token: str | None) -> None:
    if not csrf_ok(request, token):
        raise HTTPException(status_code=400, detail="Your session expired. Reload the page and try again.")


# --------------------------------------------------------------------------- #
# Login / logout
# --------------------------------------------------------------------------- #

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db), next: str = "/admin", error: str = ""):
    if current_user(request, db):
        return RedirectResponse(next or "/admin", status_code=303)
    return templates.TemplateResponse(
        request, "admin/login.html",
        {"request": request, "cfg": load_settings(db), "next": next, "error": error},
    )


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    user = authenticate(db, str(form.get("email", "")), str(form.get("password", "")))
    next_url = str(form.get("next") or "/admin")
    if not user:
        return RedirectResponse(f"/admin/login?error=1&next={next_url}", status_code=303)
    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        settings.SESSION_COOKIE, make_session_token(user),
        max_age=settings.SESSION_MAX_AGE, httponly=True, samesite="lax",
        secure=settings.COOKIE_SECURE, path="/",
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE, path="/")
    return response


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    now = utcnow()
    cfg = load_settings(db)

    upcoming = list(db.execute(
        select(Event).where(Event.start_at >= now, Event.status == Status.published)
        .order_by(Event.start_at).limit(5)
    ).scalars())
    drafts = list(db.execute(
        select(Article).where(Article.status == Status.draft).order_by(Article.updated_at.desc()).limit(5)
    ).scalars())
    recent_messages = list(db.execute(
        select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(5)
    ).scalars())
    recent_regs = list(db.execute(
        select(Registration).order_by(Registration.created_at.desc()).limit(6)
    ).scalars())

    health = seo_overview(db, cfg)
    week_ago = now - timedelta(days=7)
    stats = {
        "published_articles": db.scalar(
            select(func.count()).select_from(Article).where(Article.status == Status.published)) or 0,
        "upcoming_events": db.scalar(
            select(func.count()).select_from(Event).where(Event.start_at >= now, Event.status == Status.published)) or 0,
        "live_notices": db.scalar(
            select(func.count()).select_from(Notification).where(Notification.status == Status.published)) or 0,
        "subscribers": db.scalar(select(func.count()).select_from(Subscriber)) or 0,
        "new_registrations": db.scalar(
            select(func.count()).select_from(Registration).where(Registration.created_at >= week_ago)) or 0,
        "total_views": db.scalar(select(func.coalesce(func.sum(Article.views), 0))) or 0,
    }

    return admin_render(
        request, db, user, "admin/dashboard.html", active="dashboard",
        upcoming=upcoming, drafts=drafts, recent_messages=recent_messages,
        recent_regs=recent_regs, health=health, stats=stats,
        analytics_ready=bool(cfg.get("ga_measurement_id", "").strip()),
    )


# --------------------------------------------------------------------------- #
# Shared save helpers
# --------------------------------------------------------------------------- #

def _f(form, key: str, default: str = "") -> str:
    value = form.get(key)
    return (str(value).strip() if value is not None else default)


def _flag(form, key: str) -> bool:
    return _f(form, key).lower() in {"1", "on", "true", "yes"}


def _int(form, key: str) -> int | None:
    raw = _f(form, key)
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _apply_seo(obj, form) -> None:
    obj.meta_title = _f(form, "meta_title") or None
    obj.meta_description = _f(form, "meta_description") or None
    obj.focus_keyword = _f(form, "focus_keyword") or None
    obj.og_image = _f(form, "og_image") or None
    obj.canonical_url = _f(form, "canonical_url") or None
    obj.noindex = _flag(form, "noindex")


def _resolve_status(form) -> Status:
    raw = _f(form, "status", "draft")
    try:
        return Status(raw)
    except ValueError:
        return Status.draft


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #

@router.get("/events", response_class=HTMLResponse)
def events_list(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    q: str = "", status: str = "",
):
    stmt = select(Event)
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Event.status == Status(status))
    events = list(db.execute(stmt.order_by(Event.start_at.desc())).scalars())
    reg_counts = dict(
        db.execute(select(Registration.event_id, func.count()).group_by(Registration.event_id)).all()
    )
    return admin_render(
        request, db, user, "admin/events_list.html", active="events",
        events=events, q=q, status=status, statuses=[s.value for s in Status], reg_counts=reg_counts,
    )


@router.get("/events/new", response_class=HTMLResponse)
def event_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return admin_render(
        request, db, user, "admin/event_form.html", active="events",
        event=None, categories=_categories(db, "event"), issues=[], score=None,
    )


@router.get("/events/{event_id}/edit", response_class=HTMLResponse)
def event_edit(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    event = db.get(Event, event_id) or _missing()
    cfg = load_settings(db)
    issues = seo.audit_item(event, cfg)
    return admin_render(
        request, db, user, "admin/event_form.html", active="events",
        event=event, categories=_categories(db, "event"),
        issues=issues, score=seo.score_from_issues(issues),
    )


@router.post("/events/save")
async def event_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))

    event_id = _int(form, "id")
    event = db.get(Event, event_id) if event_id else Event(start_at=utcnow())
    if event is None:
        _missing()

    event.title = _f(form, "title") or "Untitled event"
    slug_input = _f(form, "slug") or event.title
    event.slug = unique_slug(db, Event, slug_input, event.id)
    event.summary = _f(form, "summary") or None
    event.body_md = _f(form, "body_md") or None
    event.body_html = render_markdown(event.body_md)
    event.cover_image = _f(form, "cover_image") or None
    event.cover_alt = _f(form, "cover_alt") or None

    event.start_at = parse_dt(_f(form, "start_at")) or event.start_at or utcnow()
    event.end_at = parse_dt(_f(form, "end_at"))
    event.timezone_name = _f(form, "timezone_name", "Asia/Kolkata")
    event.mode = _f(form, "mode", "in_person")
    event.venue_name = _f(form, "venue_name") or None
    event.address = _f(form, "address") or None
    event.city = _f(form, "city") or None
    event.country = _f(form, "country") or None
    event.online_url = _f(form, "online_url") or None
    event.registration_url = _f(form, "registration_url") or None
    event.capacity = _int(form, "capacity")
    event.is_free = _flag(form, "is_free")
    event.price = _f(form, "price") or None
    event.currency = _f(form, "currency", "INR")
    event.speakers = _f(form, "speakers") or None
    event.organizer = _f(form, "organizer") or None
    event.category_id = _int(form, "category_id")
    event.featured = _flag(form, "featured")
    event.status = _resolve_status(form)
    _apply_seo(event, form)

    if event.id is None:
        db.add(event)
    db.commit()
    return RedirectResponse(f"/admin/events/{event.id}/edit?saved=1", status_code=303)


@router.post("/events/{event_id}/delete")
async def event_delete(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    event = db.get(Event, event_id) or _missing()
    db.delete(event)
    db.commit()
    return RedirectResponse("/admin/events?deleted=1", status_code=303)


@router.get("/events/{event_id}/registrations", response_class=HTMLResponse)
def event_registrations(event_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    event = db.get(Event, event_id) or _missing()
    regs = list(db.execute(
        select(Registration).where(Registration.event_id == event_id)
        .order_by(Registration.created_at.desc())
    ).scalars())
    return admin_render(
        request, db, user, "admin/registrations.html", active="events", event=event, regs=regs,
    )


@router.get("/events/{event_id}/registrations.csv")
def event_registrations_csv(event_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    event = db.get(Event, event_id) or _missing()
    regs = db.execute(
        select(Registration).where(Registration.event_id == event_id).order_by(Registration.created_at)
    ).scalars()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Name", "Email", "Phone", "Organisation", "Notes", "Registered at"])
    for r in regs:
        writer.writerow([r.name, r.email, r.phone or "", r.organisation or "", r.notes or "",
                         r.created_at.strftime("%Y-%m-%d %H:%M")])
    return Response(
        buffer.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{event.slug}-registrations.csv"'},
    )


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #

@router.get("/articles", response_class=HTMLResponse)
def articles_list(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    q: str = "", status: str = "",
):
    stmt = select(Article)
    if q:
        stmt = stmt.where(or_(Article.title.ilike(f"%{q}%"), Article.tags.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(Article.status == Status(status))
    articles = list(db.execute(stmt.order_by(Article.updated_at.desc())).scalars())
    return admin_render(
        request, db, user, "admin/articles_list.html", active="articles",
        articles=articles, q=q, status=status, statuses=[s.value for s in Status],
    )


@router.get("/articles/new", response_class=HTMLResponse)
def article_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return admin_render(
        request, db, user, "admin/article_form.html", active="articles",
        article=None, categories=_categories(db, "article"), issues=[], score=None,
    )


@router.get("/articles/{article_id}/edit", response_class=HTMLResponse)
def article_edit(article_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    article = db.get(Article, article_id) or _missing()
    issues = seo.audit_item(article, load_settings(db))
    return admin_render(
        request, db, user, "admin/article_form.html", active="articles",
        article=article, categories=_categories(db, "article"),
        issues=issues, score=seo.score_from_issues(issues),
    )


@router.post("/articles/save")
async def article_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))

    article_id = _int(form, "id")
    article = db.get(Article, article_id) if article_id else Article()
    if article is None:
        _missing()

    article.title = _f(form, "title") or "Untitled article"
    article.slug = unique_slug(db, Article, _f(form, "slug") or article.title, article.id)
    article.body_md = _f(form, "body_md") or None
    article.body_html = render_markdown(article.body_md)
    article.excerpt = _f(form, "excerpt") or summarise(article.body_html, 200) or None
    article.cover_image = _f(form, "cover_image") or None
    article.cover_alt = _f(form, "cover_alt") or None
    article.external_url = _f(form, "external_url") or None
    article.source_name = _f(form, "source_name") or None
    article.tags = _f(form, "tags") or None
    article.category_id = _int(form, "category_id")
    article.author_id = _int(form, "author_id") or article.author_id or user.id
    article.featured = _flag(form, "featured")
    article.status = _resolve_status(form)
    article.reading_minutes = reading_time(article.body_html or article.excerpt)
    _apply_seo(article, form)

    published_at = parse_dt(_f(form, "published_at"))
    if article.status == Status.published:
        article.published_at = published_at or article.published_at or utcnow()
    else:
        article.published_at = published_at

    if article.id is None:
        db.add(article)
    db.commit()
    return RedirectResponse(f"/admin/articles/{article.id}/edit?saved=1", status_code=303)


@router.post("/articles/{article_id}/delete")
async def article_delete(article_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    db.delete(db.get(Article, article_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/articles?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #

@router.get("/notifications", response_class=HTMLResponse)
def notifications_list(
    request: Request, db: Session = Depends(get_db), user: User = Depends(require_user),
    q: str = "", status: str = "",
):
    stmt = select(Notification)
    if q:
        stmt = stmt.where(Notification.title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Notification.status == Status(status))
    notices = list(db.execute(
        stmt.order_by(Notification.pinned.desc(), Notification.created_at.desc())
    ).scalars())
    return admin_render(
        request, db, user, "admin/notifications_list.html", active="notifications",
        notices=notices, q=q, status=status, statuses=[s.value for s in Status],
    )


@router.get("/notifications/new", response_class=HTMLResponse)
def notification_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return admin_render(
        request, db, user, "admin/notification_form.html", active="notifications",
        note=None, levels=[l.value for l in Level], issues=[], score=None,
    )


@router.get("/notifications/{note_id}/edit", response_class=HTMLResponse)
def notification_edit(note_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    note = db.get(Notification, note_id) or _missing()
    issues = seo.audit_item(note, load_settings(db))
    return admin_render(
        request, db, user, "admin/notification_form.html", active="notifications",
        note=note, levels=[l.value for l in Level], issues=issues, score=seo.score_from_issues(issues),
    )


@router.post("/notifications/save")
async def notification_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))

    note_id = _int(form, "id")
    note = db.get(Notification, note_id) if note_id else Notification()
    if note is None:
        _missing()

    note.title = _f(form, "title") or "Untitled notice"
    note.slug = unique_slug(db, Notification, _f(form, "slug") or note.title, note.id)
    note.summary = _f(form, "summary") or None
    note.body_md = _f(form, "body_md") or None
    note.body_html = render_markdown(note.body_md)
    try:
        note.level = Level(_f(form, "level", "info"))
    except ValueError:
        note.level = Level.info
    note.link_url = _f(form, "link_url") or None
    note.link_label = _f(form, "link_label") or None
    note.attachment = _f(form, "attachment") or None
    note.pinned = _flag(form, "pinned")
    note.starts_at = parse_dt(_f(form, "starts_at"))
    note.expires_at = parse_dt(_f(form, "expires_at"))
    note.status = _resolve_status(form)
    _apply_seo(note, form)
    if note.status == Status.published and not note.published_at:
        note.published_at = note.starts_at or utcnow()

    if note.id is None:
        db.add(note)
    db.commit()
    return RedirectResponse(f"/admin/notifications/{note.id}/edit?saved=1", status_code=303)


@router.post("/notifications/{note_id}/delete")
async def notification_delete(note_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    db.delete(db.get(Notification, note_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/notifications?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #

@router.get("/pages", response_class=HTMLResponse)
def pages_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    pages = list(db.execute(select(Page).order_by(Page.nav_order, Page.title)).scalars())
    return admin_render(request, db, user, "admin/pages_list.html", active="pages", pages=pages)


@router.get("/pages/new", response_class=HTMLResponse)
def page_new(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return admin_render(request, db, user, "admin/page_form.html", active="pages", page=None, issues=[], score=None)


@router.get("/pages/{page_id}/edit", response_class=HTMLResponse)
def page_edit(page_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    page = db.get(Page, page_id) or _missing()
    issues = seo.audit_item(page, load_settings(db))
    return admin_render(
        request, db, user, "admin/page_form.html", active="pages",
        page=page, issues=issues, score=seo.score_from_issues(issues),
    )


@router.post("/pages/save")
async def page_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))

    page_id = _int(form, "id")
    page = db.get(Page, page_id) if page_id else Page()
    if page is None:
        _missing()

    page.title = _f(form, "title") or "Untitled page"
    page.slug = unique_slug(db, Page, _f(form, "slug") or page.title, page.id)
    page.subtitle = _f(form, "subtitle") or None
    page.body_md = _f(form, "body_md") or None
    page.body_html = render_markdown(page.body_md)
    page.hero_image = _f(form, "hero_image") or None
    page.show_in_nav = _flag(form, "show_in_nav")
    page.nav_order = _int(form, "nav_order") or 100
    page.template = _f(form, "template", "default")
    page.status = _resolve_status(form)
    _apply_seo(page, form)

    if page.id is None:
        db.add(page)
    db.commit()
    return RedirectResponse(f"/admin/pages/{page.id}/edit?saved=1", status_code=303)


@router.post("/pages/{page_id}/delete")
async def page_delete(page_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    db.delete(db.get(Page, page_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/pages?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #

def _categories(db: Session, kind: str) -> list[Category]:
    return list(db.execute(select(Category).where(Category.kind == kind).order_by(Category.name)).scalars())


@router.get("/categories", response_class=HTMLResponse)
def categories_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    cats = list(db.execute(select(Category).order_by(Category.kind, Category.name)).scalars())
    usage = {
        "article": dict(db.execute(select(Article.category_id, func.count()).group_by(Article.category_id)).all()),
        "event": dict(db.execute(select(Event.category_id, func.count()).group_by(Event.category_id)).all()),
    }
    return admin_render(request, db, user, "admin/categories.html", active="categories", cats=cats, usage=usage)


@router.post("/categories/save")
async def category_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    cat_id = _int(form, "id")
    cat = db.get(Category, cat_id) if cat_id else Category()
    cat.name = _f(form, "name") or "Untitled"
    cat.kind = _f(form, "kind", "article")
    cat.slug = unique_slug(db, Category, _f(form, "slug") or cat.name, cat.id)
    cat.description = _f(form, "description") or None
    cat.accent = _f(form, "accent", "primary")
    if cat.id is None:
        db.add(cat)
    db.commit()
    return RedirectResponse("/admin/categories?saved=1", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def category_delete(cat_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    db.delete(db.get(Category, cat_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/categories?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #
# Media library
# --------------------------------------------------------------------------- #

@router.get("/media", response_class=HTMLResponse)
def media_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user), error: str = ""):
    items = list(db.execute(select(Media).order_by(Media.created_at.desc())).scalars())
    return admin_render(
        request, db, user, "admin/media.html", active="media", items=items, error=error,
        max_mb=settings.MAX_UPLOAD_BYTES // (1024 * 1024),
        allowed=sorted(e.lstrip(".") for e in settings.ALLOWED_UPLOAD_EXT),
    )


@router.post("/media/upload")
async def media_upload(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile) and f.filename]
    alt = _f(form, "alt")
    saved = 0
    for upload in uploads:
        if not is_allowed_upload(upload.filename):
            return RedirectResponse("/admin/media?error=type", status_code=303)
        payload = await upload.read()
        if len(payload) > settings.MAX_UPLOAD_BYTES:
            return RedirectResponse("/admin/media?error=size", status_code=303)
        url, disk_name = save_upload(payload, upload.filename)
        db.add(Media(
            filename=disk_name, original_name=upload.filename, url=url,
            mime=upload.content_type, size=len(payload),
            alt=alt or None, uploaded_by_id=user.id,
        ))
        saved += 1
    db.commit()
    return RedirectResponse(f"/admin/media?uploaded={saved}", status_code=303)


@router.post("/media/{media_id}/delete")
async def media_delete(media_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    item = db.get(Media, media_id) or _missing()
    try:
        target = (settings.UPLOAD_DIR.parent.parent / item.url.lstrip("/")).resolve()
        if target.is_file() and settings.UPLOAD_DIR.resolve() in target.parents:
            target.unlink()
    except OSError:
        pass
    db.delete(item)
    db.commit()
    return RedirectResponse("/admin/media?deleted=1", status_code=303)


@router.get("/media/picker.json")
def media_picker(db: Session = Depends(get_db), user: User = Depends(require_user), q: str = ""):
    stmt = select(Media).order_by(Media.created_at.desc()).limit(100)
    if q:
        stmt = select(Media).where(Media.original_name.ilike(f"%{q}%")).order_by(Media.created_at.desc()).limit(100)
    return [
        {"id": m.id, "url": m.url, "name": m.original_name, "alt": m.alt or "",
         "is_image": m.is_image, "size": m.size_label}
        for m in db.execute(stmt).scalars()
    ]


# --------------------------------------------------------------------------- #
# Subscribers, messages, registrations
# --------------------------------------------------------------------------- #

@router.get("/subscribers", response_class=HTMLResponse)
def subscribers_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    subs = list(db.execute(select(Subscriber).order_by(Subscriber.created_at.desc())).scalars())
    return admin_render(request, db, user, "admin/subscribers.html", active="subscribers", subs=subs)


@router.get("/subscribers.csv")
def subscribers_csv(db: Session = Depends(get_db), user: User = Depends(require_user)):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Email", "Name", "Source", "Active", "Joined"])
    for s in db.execute(select(Subscriber).order_by(Subscriber.created_at)).scalars():
        writer.writerow([s.email, s.name or "", s.source or "", "yes" if s.is_active else "no",
                         s.created_at.strftime("%Y-%m-%d")])
    return Response(buffer.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="subscribers.csv"'})


@router.get("/messages", response_class=HTMLResponse)
def messages_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    msgs = list(db.execute(select(ContactMessage).order_by(ContactMessage.created_at.desc())).scalars())
    return admin_render(request, db, user, "admin/messages.html", active="messages", msgs=msgs)


@router.post("/messages/{msg_id}/read")
async def message_toggle(msg_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    msg = db.get(ContactMessage, msg_id) or _missing()
    msg.is_read = not msg.is_read
    db.commit()
    return RedirectResponse("/admin/messages", status_code=303)


@router.post("/messages/{msg_id}/delete")
async def message_delete(msg_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    db.delete(db.get(ContactMessage, msg_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/messages?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #
# SEO health
# --------------------------------------------------------------------------- #

def seo_overview(db: Session, cfg: dict) -> dict:
    rows = []
    for kind, model, url_prefix, edit_prefix in (
        ("Article", Article, "/articles", "/admin/articles"),
        ("Event", Event, "/events", "/admin/events"),
        ("Notification", Notification, "/notifications", "/admin/notifications"),
        ("Page", Page, "", "/admin/pages"),
    ):
        for obj in db.execute(select(model).where(model.status == Status.published)).scalars():
            issues = seo.audit_item(obj, cfg)
            score = seo.score_from_issues(issues)
            rows.append({
                "kind": kind, "title": obj.title, "score": score, "band": seo.score_band(score),
                "issues": issues, "public_url": f"{url_prefix}/{obj.slug}",
                "edit_url": f"{edit_prefix}/{obj.id}/edit",
            })
    rows.sort(key=lambda r: r["score"])
    average = round(sum(r["score"] for r in rows) / len(rows)) if rows else 100
    return {
        "rows": rows,
        "average": average,
        "band": seo.score_band(average),
        "errors": sum(1 for r in rows for i in r["issues"] if i["level"] == "error"),
        "warnings": sum(1 for r in rows for i in r["issues"] if i["level"] == "warn"),
        "total": len(rows),
    }


@router.get("/seo", response_class=HTMLResponse)
def seo_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    cfg = load_settings(db)
    health = seo_overview(db, cfg)
    checks = [
        {"label": "Site URL configured for canonical links", "ok": not settings.SITE_URL.startswith("http://127.0.0.1"),
         "hint": "Set SITE_URL in .env to your live domain so canonical tags and the sitemap point at production."},
        {"label": "Default meta description set", "ok": bool(cfg.get("site_description", "").strip()),
         "hint": "Settings - Identity - Default meta description."},
        {"label": "Default share image set", "ok": bool(cfg.get("seo_default_og_image", "").strip()),
         "hint": "Upload a 1200x630 image in Settings - SEO."},
        {"label": "Google Analytics connected", "ok": bool(cfg.get("ga_measurement_id", "").strip()),
         "hint": "Add your G-XXXXXXXXXX measurement ID in Settings - Analytics."},
        {"label": "Search Console verification added", "ok": bool(cfg.get("seo_google_verification", "").strip()),
         "hint": "Paste the verification token in Settings - SEO, then verify in Search Console."},
        {"label": "Indexing enabled", "ok": cfg.get("seo_indexing_enabled") in {"1", "true", "on"},
         "hint": "Turn indexing on in Settings - SEO once the site is ready to launch."},
        {"label": "Organisation contact details complete", "ok": bool(cfg.get("contact_email")) and bool(cfg.get("contact_phone")),
         "hint": "These feed the Organization structured data block."},
    ]
    return admin_render(
        request, db, user, "admin/seo.html", active="seo",
        health=health, checks=checks,
        sitemap_url=seo.absolute_url("/sitemap.xml"),
        robots_url=seo.absolute_url("/robots.txt"),
        rss_url=seo.absolute_url("/rss.xml"),
    )


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #

@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin), saved: int = 0):
    return admin_render(
        request, db, user, "admin/settings.html", active="settings",
        values=load_settings(db), groups=GROUPS, defaults=DEFAULTS, saved=bool(saved),
    )


@router.post("/settings")
async def settings_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    updates: dict[str, str] = {}
    for key, spec in DEFAULTS.items():
        if spec[3] == "bool":
            updates[key] = "1" if _flag(form, key) else "0"
        elif key in form:
            updates[key] = _f(form, key)
    save_settings(db, updates)
    return RedirectResponse("/admin/settings?saved=1", status_code=303)


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #

@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin), error: str = ""):
    users = list(db.execute(select(User).order_by(User.created_at)).scalars())
    return admin_render(request, db, user, "admin/users.html", active="users", users=users, error=error)


@router.post("/users/save")
async def user_save(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    target_id = _int(form, "id")
    target = db.get(User, target_id) if target_id else User(password_hash="")
    if target is None:
        _missing()

    email = _f(form, "email").lower()
    clash = db.execute(select(User).where(User.email == email, User.id != (target.id or 0))).scalars().first()
    if clash:
        return RedirectResponse("/admin/users?error=email", status_code=303)

    target.email = email
    target.name = _f(form, "name") or email
    target.role = Role(_f(form, "role", "editor"))
    target.is_active = _flag(form, "is_active")
    target.bio = _f(form, "bio") or None
    password = _f(form, "password")
    if password:
        if len(password) < 10:
            return RedirectResponse("/admin/users?error=weak", status_code=303)
        target.password_hash = hash_password(password)
    if not target.password_hash:
        return RedirectResponse("/admin/users?error=password", status_code=303)

    if target.id is None:
        db.add(target)
    db.commit()
    return RedirectResponse("/admin/users?saved=1", status_code=303)


@router.post("/users/{user_id}/delete")
async def user_delete(user_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    form = await request.form()
    guard_csrf(request, _f(form, "csrf_token"))
    if user_id == user.id:
        return RedirectResponse("/admin/users?error=self", status_code=303)
    db.delete(db.get(User, user_id) or _missing())
    db.commit()
    return RedirectResponse("/admin/users?deleted=1", status_code=303)


# --------------------------------------------------------------------------- #

def _missing():
    raise HTTPException(status_code=404, detail="Not found")
