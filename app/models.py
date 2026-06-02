from __future__ import annotations

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class SuperAdmin(UserMixin, db.Model):
    __tablename__ = "super_admins"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)

    def get_id(self) -> str:
        return f"sa:{self.id}"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Society(db.Model):
    __tablename__ = "societies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    player_password_hash = db.Column(db.String(256), nullable=True)
    locked = db.Column(db.Boolean, nullable=False, default=False)

    admins = db.relationship("Admin", back_populates="society", lazy="dynamic")
    users = db.relationship("User", back_populates="society", lazy="dynamic")

    def set_player_password(self, password: str) -> None:
        self.player_password_hash = generate_password_hash(password)

    def check_player_password(self, password: str) -> bool:
        if not self.player_password_hash:
            return False
        return check_password_hash(self.player_password_hash, password)


class Admin(UserMixin, db.Model):
    """Society-scoped organiser (creates competitions; shares courses with society)."""

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False)

    society = db.relationship("Society", back_populates="admins")
    competitions = db.relationship(
        "Competition", back_populates="admin", lazy="dynamic"
    )
    created_courses = db.relationship(
        "Course",
        foreign_keys="Course.created_by_admin_id",
        back_populates="creator",
        lazy="dynamic",
    )

    def get_id(self) -> str:
        return f"a:{self.id}"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    society_id = db.Column(db.Integer, db.ForeignKey("societies.id"), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    def get_id(self) -> str:
        return f"u:{self.id}"

    society = db.relationship("Society", back_populates="users")
    competition_entries = db.relationship(
        "CompetitionPlayer", back_populates="user", lazy="dynamic"
    )
    scores = db.relationship("Score", back_populates="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Course(db.Model):
    """Shared across all societies; dropdown label uses name + postcode."""

    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    # DB column remains admin_id (legacy NOT NULL); Python name is created_by_admin_id.
    created_by_admin_id = db.Column(
        "admin_id", db.Integer, db.ForeignKey("admins.id"), nullable=False
    )
    name = db.Column(db.String(200), nullable=False)
    postcode = db.Column(db.String(32), nullable=False, default="")

    creator = db.relationship(
        "Admin", foreign_keys=[created_by_admin_id], back_populates="created_courses"
    )
    holes = db.relationship(
        "Hole",
        backref="course",
        lazy="dynamic",
        order_by="Hole.hole_number",
        cascade="all, delete-orphan",
    )
    competitions = db.relationship("Competition", backref="course", lazy="dynamic")

    @property
    def display_label(self) -> str:
        p = (self.postcode or "").strip()
        if p:
            return f"{self.name} ({p})"
        return self.name


class Hole(db.Model):
    __tablename__ = "holes"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    par = db.Column(db.Integer, nullable=False)
    stroke_index = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("course_id", "hole_number", name="uq_course_hole"),
    )


class Competition(db.Model):
    __tablename__ = "competitions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    locked = db.Column(db.Boolean, nullable=False, default=False)

    admin = db.relationship("Admin", back_populates="competitions")
    players = db.relationship(
        "CompetitionPlayer",
        back_populates="competition",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    scores = db.relationship(
        "Score",
        back_populates="competition",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class CompetitionPlayer(db.Model):
    __tablename__ = "competition_players"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competitions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    playing_handicap = db.Column(db.Integer, nullable=False, default=0)

    user = db.relationship("User", back_populates="competition_entries")
    competition = db.relationship("Competition", back_populates="players")

    __table_args__ = (
        db.UniqueConstraint("competition_id", "user_id", name="uq_comp_user"),
    )


class Score(db.Model):
    __tablename__ = "scores"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("competitions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    gross_strokes = db.Column(db.Integer, nullable=False)

    user = db.relationship("User", back_populates="scores")
    competition = db.relationship("Competition", back_populates="scores")

    __table_args__ = (
        db.UniqueConstraint(
            "competition_id", "user_id", "hole_number", name="uq_score_hole"
        ),
    )
