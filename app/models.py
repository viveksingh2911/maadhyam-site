"""Database models for the public site and the admin portal."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Status(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    published = "published"
    archived = "archived"


class Level(str, enum.Enum):
    info = "info"
    important = "important"
    urgent = "urgent"


class Role(str, enum.Enum):
    admin = "admin"
    editor = "editor"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SeoMixin:
    """Optional per-item SEO overrides. Blank fields are auto-derived at render time."""

    meta_title: Mapped[str | None] = mapped_column(String(255))
    meta_description: Mapped[str | None] = mapped_column(String(400))
    focus_keyword: Mapped[str | None] = mapped_column(String(160))
    og_image: Mapped[str | None] = mapped_column(String(500))
    canonical_url: Mapped[str | None] = mapped_column(String(500))
    noindex: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.editor, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text)
    avatar: Mapped[str | None] = mapped_column(String(500))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    articles: Mapped[list["Article"]] = relationship(back_populates="author")

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin


class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("slug", "kind", name="uq_category_slug_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="article", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    accent: Mapped[str] = mapped_column(String(30), default="primary", nullable=False)

    articles: Mapped[list["Article"]] = relationship(back_populates="category")
    events: Mapped[list["Event"]] = relationship(back_populates="category")


class Article(Base, TimestampMixin, SeoMixin):
    """Blog posts, insights, and curated external coverage."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    cover_alt: Mapped[str | None] = mapped_column(String(300))

    # Curated link posts (press coverage) point outward instead of to a body.
    external_url: Mapped[str | None] = mapped_column(String(600))
    source_name: Mapped[str | None] = mapped_column(String(160))

    tags: Mapped[str | None] = mapped_column(String(400))
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft, nullable=False, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reading_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    category: Mapped["Category | None"] = relationship(back_populates="articles")
    author: Mapped["User | None"] = relationship(back_populates="articles")

    @property
    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    @property
    def is_link_post(self) -> bool:
        return bool(self.external_url and not (self.body_md or "").strip())


class Event(Base, TimestampMixin, SeoMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    cover_alt: Mapped[str | None] = mapped_column(String(300))

    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    timezone_name: Mapped[str] = mapped_column(String(60), default="Asia/Kolkata", nullable=False)

    mode: Mapped[str] = mapped_column(String(20), default="in_person", nullable=False)
    venue_name: Mapped[str | None] = mapped_column(String(240))
    address: Mapped[str | None] = mapped_column(String(400))
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120), default="India")
    online_url: Mapped[str | None] = mapped_column(String(600))

    registration_url: Mapped[str | None] = mapped_column(String(600))
    capacity: Mapped[int | None] = mapped_column(Integer)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)

    # One speaker per line, formatted as "Name - Role".
    speakers: Mapped[str | None] = mapped_column(Text)
    organizer: Mapped[str | None] = mapped_column(String(240))

    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft, nullable=False, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))

    category: Mapped["Category | None"] = relationship(back_populates="events")
    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    @property
    def is_online(self) -> bool:
        return self.mode in {"online", "hybrid"}

    @property
    def is_past(self) -> bool:
        return (self.end_at or self.start_at) < utcnow()

    @property
    def speaker_list(self) -> list[str]:
        return [s.strip() for s in (self.speakers or "").splitlines() if s.strip()]

    @property
    def location_line(self) -> str:
        if self.mode == "online":
            return "Online"
        bits = [b for b in (self.venue_name, self.city) if b]
        return ", ".join(bits) or "Venue to be announced"


class Registration(Base, TimestampMixin):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    organisation: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    attended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    event: Mapped["Event"] = relationship(back_populates="registrations")


class Notification(Base, TimestampMixin, SeoMixin):
    """Announcements, circulars and notices shown across the site."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body_md: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    level: Mapped[Level] = mapped_column(Enum(Level), default=Level.info, nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(600))
    link_label: Mapped[str | None] = mapped_column(String(120))
    attachment: Mapped[str | None] = mapped_column(String(500))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Unused since the site-wide notice bar was removed; notices now live only
    # on the notice board. Kept so the column need not be migrated away.
    show_in_ticker: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft, nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class Page(Base, TimestampMixin, SeoMixin):
    """Editable standalone pages (About, Services, Contact and so on)."""

    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(400))
    body_md: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    hero_image: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft, nullable=False, index=True)
    show_in_nav: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nav_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    template: Mapped[str] = mapped_column(String(40), default="default", nullable=False)


class Media(Base, TimestampMixin):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    original_name: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(600), nullable=False)
    mime: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alt: Mapped[str | None] = mapped_column(String(300))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    @property
    def is_image(self) -> bool:
        return (self.mime or "").startswith("image/")

    @property
    def size_label(self) -> str:
        kb = self.size / 1024
        return f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"


class Subscriber(Base, TimestampMixin):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(160))
    source: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ContactMessage(Base, TimestampMixin):
    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    subject: Mapped[str | None] = mapped_column(String(240))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Setting(Base, TimestampMixin):
    """Key/value site configuration edited from the admin portal."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
