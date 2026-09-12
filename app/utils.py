"""Shared helpers: slugs, markdown rendering, text summarising, dates, uploads."""
from __future__ import annotations

import math
import re
import secrets
import unicodedata
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path

import markdown as md_lib
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings

_MD = md_lib.Markdown(
    extensions=["extra", "sane_lists", "smarty", "toc", "nl2br", "admonition"],
    output_format="html",
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SLUG_STRIP = re.compile(r"[^a-z0-9\s-]")


def _now() -> datetime:
    """Naive UTC, matching how datetimes are stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def slugify(value: str, max_length: int = 90) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    value = _SLUG_STRIP.sub("", value.lower()).strip()
    value = re.sub(r"[\s_-]+", "-", value).strip("-")
    if len(value) > max_length:
        value = value[:max_length].rsplit("-", 1)[0] or value[:max_length]
    return value or f"item-{secrets.token_hex(3)}"


def unique_slug(db: Session, model, title: str, current_id: int | None = None) -> str:
    """Slug that is unique within `model`, appending -2, -3 ... when needed."""
    base = slugify(title)
    candidate = base
    counter = 2
    while True:
        stmt = select(model).where(model.slug == candidate)
        if current_id is not None:
            stmt = stmt.where(model.id != current_id)
        if db.execute(stmt).first() is None:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def render_markdown(text: str | None) -> str:
    if not text or not text.strip():
        return ""
    _MD.reset()
    return _MD.convert(text)


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    return _WS_RE.sub(" ", unescape(_TAG_RE.sub(" ", html))).strip()


def summarise(text: str | None, limit: int = 158) -> str:
    """Trim to a whole word under `limit` characters - used for meta descriptions."""
    clean = strip_html(text)
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return f"{cut}..."


def reading_time(text: str | None) -> int:
    words = len(strip_html(text).split())
    return max(1, math.ceil(words / 220))


def parse_dt(value: str | None) -> datetime | None:
    """Parse the value produced by <input type="datetime-local"> (or a date)."""
    if not value:
        return None
    value = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def dt_local(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%dT%H:%M") if value else ""


def fmt_date(value: datetime | date | None, fmt: str = "%d %b %Y") -> str:
    return value.strftime(fmt) if value else ""


def fmt_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d %b %Y, %I:%M %p").replace(" 0", " ")


def fmt_event_range(start: datetime | None, end: datetime | None) -> str:
    if not start:
        return "Date to be announced"
    if not end:
        return start.strftime("%d %b %Y, %I:%M %p").replace(" 0", " ")
    if start.date() == end.date():
        return (
            f"{start.strftime('%d %b %Y')}, "
            f"{start.strftime('%I:%M %p').lstrip('0')} - {end.strftime('%I:%M %p').lstrip('0')}"
        )
    return f"{start.strftime('%d %b %Y')} - {end.strftime('%d %b %Y')}"


def time_ago(value: datetime | None) -> str:
    if not value:
        return ""
    delta = _now() - value
    seconds = delta.total_seconds()
    if seconds < 0:
        return "scheduled"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    if delta.days < 30:
        return f"{delta.days}d ago"
    if delta.days < 365:
        return f"{delta.days // 30}mo ago"
    return f"{delta.days // 365}y ago"


def countdown_label(start: datetime | None) -> str:
    if not start:
        return ""
    delta = start - _now()
    if delta.total_seconds() < 0:
        return "Concluded"
    if delta.days >= 1:
        return f"In {delta.days} day{'s' if delta.days != 1 else ''}"
    hours = int(delta.total_seconds() // 3600)
    return f"In {hours} hour{'s' if hours != 1 else ''}" if hours else "Starting soon"


def initials(name: str | None) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


def safe_filename(name: str) -> str:
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    return f"{slugify(stem, 60)}-{secrets.token_hex(4)}{suffix}"


def is_allowed_upload(filename: str) -> bool:
    return Path(filename).suffix.lower() in settings.ALLOWED_UPLOAD_EXT


def save_upload(file_bytes: bytes, original_name: str) -> tuple[str, str]:
    """Persist an upload under static/uploads/YYYY/MM. Returns (relative_url, disk_name)."""
    today = date.today()
    folder = settings.UPLOAD_DIR / f"{today:%Y}" / f"{today:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_filename(original_name)
    (folder / name).write_bytes(file_bytes)
    return f"/static/uploads/{today:%Y}/{today:%m}/{name}", name


