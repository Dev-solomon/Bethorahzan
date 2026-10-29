from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    email = db.Column(db.String(200), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='member', nullable=False)  # member / admin
    status = db.Column(db.String(30), default='active')
    phone = db.Column(db.String(35), default='')
    country = db.Column(db.String(90), default='')
    city = db.Column(db.String(90), default='')
    interests = db.Column(db.Text, default='')
    bio = db.Column(db.Text, default='')
    admin_notes = db.Column(db.Text, default='')
    stripe_account_id = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=utcnow)
    def set_password(self, value): self.password_hash = generate_password_hash(value)
    def check_password(self, value): return check_password_hash(self.password_hash, value)
    @property
    def is_active(self): return self.status == 'active'

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(220), nullable=False)
    slug = db.Column(db.String(240), unique=True, nullable=False)
    category = db.Column(db.String(45), default='Gathering')
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=True)
    timezone = db.Column(db.String(80), default='America/New_York')
    location = db.Column(db.String(220), default='Online')
    image_url = db.Column(db.String(500), default='')
    featured = db.Column(db.Boolean, default=False)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

class Teaching(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(220), nullable=False)
    slug = db.Column(db.String(240), unique=True, nullable=False)
    category = db.Column(db.String(70), default='Teaching')
    scripture = db.Column(db.String(160), default='')
    summary = db.Column(db.Text, nullable=False)
    youtube_url = db.Column(db.String(500), default='')
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

class RSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    event = db.relationship('Event', backref=db.backref('rsvps', cascade='all, delete-orphan'))
    user = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('event_id','user_id',name='uq_rsvp'),)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service = db.Column(db.String(65), nullable=False)
    requested_at = db.Column(db.DateTime, nullable=False)
    timezone = db.Column(db.String(80), default='America/New_York')
    notes = db.Column(db.Text, default='')
    private_response = db.Column(db.Text, default='')
    meeting_link = db.Column(db.String(500), default='')
    status = db.Column(db.String(25), default='pending')
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User', backref='appointments')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(220), nullable=False)
    slug = db.Column(db.String(250), unique=True, nullable=False)
    kind = db.Column(db.String(30), default='book')
    fulfillment_type = db.Column(db.String(20), default='digital') # digital or physical
    description = db.Column(db.Text, nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), default='')
    access_url = db.Column(db.String(500), default='')
    inventory = db.Column(db.Integer, nullable=True)  # None = unlimited
    active = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), default='pending')
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_payment_intent = db.Column(db.String(255), default='')
    shipping_details = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User', backref='purchases')
    product = db.relationship('Product')

class Cause(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    icon = db.Column(db.String(60), default='heart')
    active = db.Column(db.Boolean, default=True)

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    cause_id = db.Column(db.Integer, db.ForeignKey('cause.id'), nullable=False)
    donor_name = db.Column(db.String(140), nullable=False)
    donor_email = db.Column(db.String(200), nullable=False)
    anonymous = db.Column(db.Boolean, default=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(500), default='')
    status = db.Column(db.String(30), default='pending')
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_payment_intent = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=utcnow)
    cause = db.relationship('Cause')
    user = db.relationship('User')

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(90), default='General')
    location = db.Column(db.String(180), default='Remote')
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, default='')
    budget_cents = db.Column(db.Integer, nullable=False)  # employer pays
    worker_cents = db.Column(db.Integer, nullable=False)  # 90% displayed to applicant
    platform_cents = db.Column(db.Integer, nullable=False) # 10% retained before Stripe fees
    status = db.Column(db.String(35), default='awaiting_payment')
    approved = db.Column(db.Boolean, default=False)
    hired_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=True)
    stripe_payment_intent = db.Column(db.String(255), default='')
    stripe_transfer_id = db.Column(db.String(255), default='')
    stripe_refund_id = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=utcnow)
    owner = db.relationship('User', foreign_keys=[owner_id], backref='posted_jobs')
    hired_user = db.relationship('User', foreign_keys=[hired_user_id])
    applicants = db.relationship('JobApplication', back_populates='job', cascade='all, delete-orphan')

class JobApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pitch = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='submitted')
    created_at = db.Column(db.DateTime, default=utcnow)
    job = db.relationship('Job', back_populates='applicants')
    user = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('job_id','user_id',name='uq_job_applicant'),)

class Inquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    topic = db.Column(db.String(90), default='General')
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), default='new')
    created_at = db.Column(db.DateTime, default=utcnow)

class StripeEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(255), unique=True, nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    received_at = db.Column(db.DateTime, default=utcnow)
