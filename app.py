"""Bethorahzan | Flask community platform.

Payments only switch to 'paid' from Stripe's signed webhooks. Job funding is a
Stripe Connect marketplace flow, NOT a regulated escrow service. Before live
launch obtain Stripe approval, legal review, charity/tax review and a payout policy.
"""
import os
import json
import re
import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import timezone
from urllib.parse import urlparse, parse_qs

import click
import stripe
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash, abort, current_app, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import db, utcnow, User, Event, Teaching, RSVP, Appointment, Product, Purchase, Cause, Donation, Job, JobApplication, Inquiry, StripeEvent

load_dotenv()
login_manager = LoginManager()
csrf = CSRFProtect()


def price(cents):
    return f'${cents / 100:,.2f}'


def money_to_cents(raw, min_cents=100, max_cents=2_000_000):
    try:
        amount = Decimal(str(raw)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        cents = int(amount * 100)
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError('Enter a valid dollar amount.')
    if cents < min_cents or cents > max_cents:
        raise ValueError(f'Amount must be between {price(min_cents)} and {price(max_cents)}.')
    return cents


def slugify(value):
    value = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return value[:140] or 'item'


def unique_slug(model, title, instance_id=None):
    base = slugify(title)
    slug = base
    i = 2
    while True:
        found = db.session.execute(db.select(model).filter_by(slug=slug)).scalar_one_or_none()
        if found is None or found.id == instance_id:
            return slug
        slug = f'{base}-{i}'
        i += 1


def form_value(key, maximum=1000, default=''):
    return request.form.get(key, default).strip()[:maximum]


def parse_dt(value):
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M')
    except (TypeError, ValueError):
        raise ValueError('Select a valid date and time.')


def to_utc(local_dt, tzname):
    try:
        tz = ZoneInfo(tzname)
    except ZoneInfoNotFoundError:
        raise ValueError('Choose a supported timezone.')
    # Datetime-local inputs are wall-clock times for the chosen timezone.
    return local_dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def format_in_zone(when, tzname='America/New_York', fmt='%d %b %Y · %I:%M %p'):
    if not when:
        return ''
    try:
        return when.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tzname)).strftime(fmt)
    except ZoneInfoNotFoundError:
        return when.strftime(fmt) + ' UTC'


def youtube_embed(url):
    """Allow YouTube-hosted embeds only; never trust arbitrary embed markup."""
    try:
        parsed=urlparse(url)
        host=(parsed.hostname or '').lower()
        if parsed.scheme != 'https':return ''
        if host in ('www.youtube.com','youtube.com','m.youtube.com'):
            video=parse_qs(parsed.query).get('v',[''])[0]
            if not video and parsed.path.startswith('/shorts/'):
                video=parsed.path.split('/')[2]
        elif host=='youtu.be':
            video=parsed.path.lstrip('/').split('/')[0]
        else:return ''
        return 'https://www.youtube-nocookie.com/embed/'+video if re.fullmatch(r'[A-Za-z0-9_-]{11}',video) else ''
    except (TypeError,ValueError,IndexError):return ''


def safe_next(target):
    if not target:
        return None
    test = urlparse(target)
    return target if not test.scheme and not test.netloc and target.startswith('/') and not target.startswith('//') else None


def admin_required(view):
    @wraps(view)
    @login_required
    def inner(*args, **kwargs):
        if current_user.role != 'admin': abort(403)
        return view(*args, **kwargs)
    return inner


def stripe_ready():
    return bool(current_app.config['STRIPE_SECRET_KEY'] and current_app.config['STRIPE_WEBHOOK_SECRET'])


def require_stripe():
    if not stripe_ready():
        flash('Online payments are not configured yet. Please contact Bethorahzan.', 'warning')
        return False
    return True


def create_checkout(kind, id_, title, amount_cents, customer_email, success_endpoint='payment_result', needs_shipping=False):
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    extras = {'shipping_address_collection': {'allowed_countries':['US','CA','GB','NG','AU','DE','FR']}} if needs_shipping else {}
    session = stripe.checkout.Session.create(
        mode='payment', customer_email=customer_email,
        line_items=[{'price_data': {'currency': 'usd', 'unit_amount': amount_cents,
                       'product_data': {'name': title[:120]}}, 'quantity': 1}],
        # Donations, physical goods and project funding use standard Stripe Checkout,
        # not Managed Payments (which is for eligible digital products only).
        managed_payments={'enabled': False},
        payment_method_types=['card'],
        client_reference_id=f'{kind}:{id_}',
        metadata={'kind':kind, 'local_id':str(id_)},
        payment_intent_data={'metadata':{'kind':kind,'local_id':str(id_)}},
        success_url=url_for(success_endpoint, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('payment_cancel', _external=True),
        expires_at=int((datetime.now() + timedelta(minutes=45)).timestamp()),
        **extras,
    )
    return session


@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
        return user if user and user.status == 'active' else None
    except (ValueError, TypeError): return None


def normalized_database_url(value):
    """Heroku URLs use postgres://; explicitly use the installed Psycopg 3 driver."""
    if value.startswith('postgres://'):
        return 'postgresql+psycopg://' + value[len('postgres://'):]
    if value.startswith('postgresql://'):
        return 'postgresql+psycopg://' + value[len('postgresql://'):]
    return value


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY','local-development-only-change-me'),
        SQLALCHEMY_DATABASE_URI=normalized_database_url(os.getenv('DATABASE_URL','sqlite:///bethorahzan.db')),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        STRIPE_SECRET_KEY=os.getenv('STRIPE_SECRET_KEY',''),
        STRIPE_PUBLISHABLE_KEY=os.getenv('STRIPE_PUBLISHABLE_KEY',''),
        STRIPE_WEBHOOK_SECRET=os.getenv('STRIPE_WEBHOOK_SECRET',''),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0') == '1',
        MAX_CONTENT_LENGTH=1024*1024,
    )
    if config: app.config.update(config)
    if os.getenv('FLASK_ENV') == 'production' and app.config['SECRET_KEY'] == 'local-development-only-change-me':
        raise RuntimeError('Set SECRET_KEY in production.')
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Sign in to access your member portal.'
    csrf.init_app(app)
    app.jinja_env.filters['money'] = price
    app.jinja_env.filters['in_zone'] = format_in_zone
    app.jinja_env.filters['youtube_embed'] = youtube_embed
    app.jinja_env.globals['now_utc'] = utcnow
    app.jinja_env.globals['stripe_ready'] = stripe_ready
    app.jinja_env.globals['min'] = min
    register_routes(app)
    register_cli(app)
    return app


def register_routes(app):
    @app.context_processor
    def inject_globals():
        return {'site_name':'Bethorahzan', 'brand_year':datetime.now().year}

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['X-Frame-Options']='SAMEORIGIN'
        if request.is_secure:
            response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_template('message.html', title='Security check expired', message='Please go back, reload the page and try again.'), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template('message.html', title='Page not found', message='The page you were looking for is unavailable.'),404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('message.html', title='Access restricted', message='You do not have permission to access this area.'),403

    @app.get('/healthz')
    def healthz(): return {'status':'ok'}

    @app.route('/')
    def home():
        events = Event.query.filter(Event.published.is_(True), Event.date>=utcnow()).order_by(Event.featured.desc(),Event.date).limit(3).all()
        products = Product.query.filter_by(active=True).order_by(Product.featured.desc(), Product.created_at.desc()).limit(3).all()
        return render_template('home.html',events=events,products=products)

    @app.route('/about')
    def about(): return render_template('about.html')

    @app.route('/teachings')
    def teachings():
        return render_template('teachings.html', teachings=Teaching.query.filter_by(published=True).order_by(Teaching.created_at.desc()).all())

    @app.route('/teachings/<slug>')
    def teaching_detail(slug):
        teaching=Teaching.query.filter_by(slug=slug,published=True).first_or_404()
        return render_template('teaching_detail.html',teaching=teaching)

    @app.route('/impact')
    def impact():
        causes = Cause.query.filter_by(active=True).all()
        return render_template('impact.html', causes=causes)

    @app.route('/contact', methods=['GET','POST'])
    def contact():
        if request.method == 'POST':
            name,email,topic,message = [form_value(k,n) for k,n in [('name',140),('email',200),('topic',90),('message',5000)]]
            if not name or '@' not in email or len(message)<12:
                flash('Please enter your name, email and a message of at least 12 characters.','danger')
            else:
                db.session.add(Inquiry(name=name,email=email.lower(),topic=topic,message=message))
                db.session.commit()
                flash('Your message has been received. Our team will review it.','success')
                return redirect(url_for('contact'))
        return render_template('contact.html')

    @app.route('/join',methods=['GET','POST'])
    def join():
        if current_user.is_authenticated: return redirect(url_for('member_dashboard'))
        if request.method == 'POST':
            name,email,password = form_value('name',140),form_value('email',200).lower(),request.form.get('password','')
            if len(name)<2 or '@' not in email or len(password)<10:
                flash('Enter a name, valid email and a password with at least 10 characters.','danger')
            elif User.query.filter_by(email=email).first():
                flash('An account with that email already exists. Please sign in.','warning')
            else:
                user=User(name=name,email=email,phone=form_value('phone',35),country=form_value('country',90),city=form_value('city',90),interests=', '.join(request.form.getlist('interests'))[:500])
                user.set_password(password)
                db.session.add(user); db.session.commit(); login_user(user)
                flash('Welcome to the Bethorahzan community.','success')
                return redirect(url_for('member_dashboard'))
        return render_template('auth.html',mode='join')

    @app.route('/login',methods=['GET','POST'])
    def login():
        if current_user.is_authenticated: return redirect(url_for('member_dashboard'))
        if request.method == 'POST':
            user=User.query.filter_by(email=form_value('email',200).lower()).first()
            if user and user.check_password(request.form.get('password','')) and user.status=='active':
                login_user(user)
                flash('Welcome back.','success')
                return redirect(safe_next(request.args.get('next')) or url_for('member_dashboard'))
            flash('Invalid credentials or inactive account.','danger')
        return render_template('auth.html',mode='login')

    @app.post('/logout')
    @login_required
    def logout():
        logout_user(); flash('You have signed out.','info'); return redirect(url_for('home'))

    @app.route('/portal')
    @login_required
    def member_dashboard():
        return render_template('portal.html', bookings=Appointment.query.filter_by(user_id=current_user.id).order_by(Appointment.created_at.desc()).limit(6).all(),
           orders=Purchase.query.filter_by(user_id=current_user.id).order_by(Purchase.created_at.desc()).limit(6).all(),
           jobs=Job.query.filter_by(owner_id=current_user.id).order_by(Job.created_at.desc()).all(),
           applications=JobApplication.query.filter_by(user_id=current_user.id).order_by(JobApplication.created_at.desc()).all())

    @app.route('/portal/profile',methods=['GET','POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            current_user.name=form_value('name',140)
            current_user.phone=form_value('phone',35)
            current_user.country=form_value('country',90)
            current_user.city=form_value('city',90)
            current_user.bio=form_value('bio',2000)
            if not current_user.name: flash('Name is required.','danger')
            else:
                db.session.commit(); flash('Profile saved.','success'); return redirect(url_for('profile'))
        return render_template('profile.html')

    @app.route('/events')
    def events():
        category=request.args.get('category','')[:45]
        q=Event.query.filter_by(published=True)
        if category: q=q.filter_by(category=category)
        return render_template('events.html', events=q.order_by(Event.date.asc()).all(), category=category)

    @app.route('/events/<slug>')
    def event_detail(slug):
        event=Event.query.filter_by(slug=slug,published=True).first_or_404()
        rsvp=RSVP.query.filter_by(event_id=event.id,user_id=current_user.id).first() if current_user.is_authenticated else None
        return render_template('event_detail.html',event=event,rsvp=rsvp)

    @app.post('/events/<int:event_id>/rsvp')
    @login_required
    def rsvp_event(event_id):
        event=db.get_or_404(Event,event_id)
        if not event.published or event.date<utcnow(): abort(404)
        if not RSVP.query.filter_by(event_id=event_id,user_id=current_user.id).first():
            db.session.add(RSVP(event_id=event_id,user_id=current_user.id));db.session.commit()
        flash('You are on the attendee list.','success')
        return redirect(url_for('event_detail',slug=event.slug))

    @app.route('/appointments',methods=['GET','POST'])
    @login_required
    def appointments():
        services=['Meeting with the Admiral','Spiritual counseling','One-on-one prayer','Prophetic guidance','Wellness support','Community support']
        if request.method=='POST':
            try:
                service=form_value('service',65)
                zone=form_value('timezone',80,'America/New_York')
                when=to_utc(parse_dt(request.form.get('requested_at')),zone)
                if service not in services or when<utcnow()+timedelta(hours=12):
                    raise ValueError('Please select a service and a requested time at least 12 hours ahead.')
                notes=form_value('notes',3000)
                db.session.add(Appointment(user_id=current_user.id,service=service,requested_at=when,timezone=zone,notes=notes))
                db.session.commit();flash('Your appointment request was submitted. The office will confirm availability.','success')
                return redirect(url_for('member_dashboard'))
            except ValueError as exc:flash(str(exc),'danger')
        return render_template('appointments.html',services=services)

    @app.route('/shop')
    def shop():
        kind=request.args.get('kind','')
        q=Product.query.filter_by(active=True)
        if kind in ('book','course','merch'):q=q.filter_by(kind=kind)
        return render_template('shop.html',products=q.order_by(Product.featured.desc(),Product.created_at.desc()).all(),kind=kind)

    @app.route('/shop/<slug>')
    def product_detail(slug):
        item=Product.query.filter_by(slug=slug,active=True).first_or_404()
        purchased=False
        if current_user.is_authenticated:
            purchased=bool(Purchase.query.filter_by(user_id=current_user.id,product_id=item.id,status='paid').first())
        return render_template('product_detail.html',product=item,purchased=purchased)

    @app.post('/shop/<int:product_id>/checkout')
    @login_required
    def buy_product(product_id):
        product=db.get_or_404(Product,product_id)
        if not product.active or (product.inventory is not None and product.inventory<=0): abort(400)
        if not require_stripe(): return redirect(url_for('product_detail',slug=product.slug))
        purchase=Purchase(user_id=current_user.id,product_id=product.id,amount_cents=product.price_cents)
        db.session.add(purchase);db.session.commit()
        try:
            s=create_checkout('product',purchase.id,product.title,purchase.amount_cents,current_user.email,needs_shipping=(product.fulfillment_type=='physical'))
            purchase.stripe_session_id=s.id;db.session.commit()
            return redirect(s.url,code=303)
        except stripe.StripeError:
            current_app.logger.exception('Product checkout failed')
            db.session.delete(purchase);db.session.commit()
            flash('Checkout is temporarily unavailable. Please try again.','danger')
            return redirect(url_for('product_detail',slug=product.slug))

    @app.route('/giving',methods=['GET','POST'])
    def giving():
        causes=Cause.query.filter_by(active=True).order_by(Cause.id).all()
        if request.method=='POST':
            try:
                cause=db.session.get(Cause,int(request.form.get('cause_id','0')))
                if not cause or not cause.active:raise ValueError('Choose a giving purpose.')
                cents=money_to_cents(request.form.get('amount'),100,1_000_000)
                donor_name=form_value('name',140)
                donor_email=form_value('email',200).lower()
                if not donor_name or '@' not in donor_email:raise ValueError('Provide your name and a valid email.')
                if not require_stripe(): return redirect(url_for('giving'))
                donation=Donation(user_id=current_user.id if current_user.is_authenticated else None,
                    cause_id=cause.id,donor_name=donor_name,donor_email=donor_email,anonymous=bool(request.form.get('anonymous')),
                    amount_cents=cents,message=form_value('message',500))
                db.session.add(donation);db.session.commit()
                try:
                    s=create_checkout('donation',donation.id,f'Giving: {cause.name}',cents,donor_email)
                    donation.stripe_session_id=s.id;db.session.commit()
                    return redirect(s.url,code=303)
                except stripe.StripeError:
                    current_app.logger.exception('Donation checkout failed')
                    db.session.delete(donation);db.session.commit()
                    raise ValueError('Payment checkout could not start. Please try again.')
            except (ValueError,TypeError) as exc:flash(str(exc),'danger')
        return render_template('giving.html',causes=causes)

    @app.route('/opportunities')
    def opportunities():
        q=Job.query.filter(Job.approved.is_(True),Job.status=='open')
        return render_template('jobs.html',jobs=q.order_by(Job.created_at.desc()).all())

    @app.route('/opportunities/post',methods=['GET','POST'])
    @login_required
    def post_job():
        if request.method=='POST':
            try:
                amount=money_to_cents(request.form.get('budget'),1000,2_000_000)
                title=form_value('title',200);description=form_value('description',6500)
                if len(title)<6 or len(description)<40:raise ValueError('Add a title (6+ characters) and detailed job description (40+ characters).')
                fee=(amount*10+50)//100 # integer rounding 10%
                job=Job(owner_id=current_user.id,title=title,description=description,
                    requirements=form_value('requirements',4000),category=form_value('category',90,'General'),
                    location=form_value('location',180,'Remote'),budget_cents=amount,worker_cents=amount-fee,platform_cents=fee)
                db.session.add(job);db.session.commit()
                flash('Job saved. Fund the project to submit it for administrator review.','success')
                return redirect(url_for('job_detail',job_id=job.id))
            except ValueError as exc:flash(str(exc),'danger')
        return render_template('post_job.html')

    @app.route('/opportunities/<int:job_id>')
    def job_detail(job_id):
        job=db.get_or_404(Job,job_id)
        is_owner=current_user.is_authenticated and (job.owner_id==current_user.id or current_user.role=='admin')
        if not is_owner and not (job.approved and job.status in ('open','assigned','awaiting_confirmation','completed')):abort(404)
        applied=JobApplication.query.filter_by(job_id=job.id,user_id=current_user.id).first() if current_user.is_authenticated else None
        return render_template('job_detail.html',job=job,is_owner=is_owner,applied=applied)

    @app.post('/opportunities/<int:job_id>/fund')
    @login_required
    def fund_job(job_id):
        job=db.get_or_404(Job,job_id)
        if job.owner_id!=current_user.id or job.status!='awaiting_payment':abort(403)
        if not require_stripe():return redirect(url_for('job_detail',job_id=job.id))
        try:
            s=create_checkout('job',job.id,f'Project funding: {job.title}',job.budget_cents,current_user.email)
            job.stripe_session_id=s.id;db.session.commit();return redirect(s.url,code=303)
        except stripe.StripeError:
            current_app.logger.exception('Job funding checkout failed')
            flash('Checkout could not start. Try again.','danger')
            return redirect(url_for('job_detail',job_id=job.id))

    @app.post('/opportunities/<int:job_id>/apply')
    @login_required
    def apply_job(job_id):
        job=db.get_or_404(Job,job_id)
        if not job.approved or job.status!='open' or job.owner_id==current_user.id:abort(403)
        pitch=form_value('pitch',4000)
        if len(pitch)<30:
            flash('Tell us about your skills and approach in at least 30 characters.','danger')
        elif JobApplication.query.filter_by(job_id=job_id,user_id=current_user.id).first():
            flash('You have already applied.','info')
        else:
            db.session.add(JobApplication(job_id=job.id,user_id=current_user.id,pitch=pitch));db.session.commit()
            flash('Application submitted. The community team will review it.','success')
        return redirect(url_for('job_detail',job_id=job.id))

    @app.post('/opportunities/<int:job_id>/confirm-completion')
    @login_required
    def confirm_completion(job_id):
        job=db.get_or_404(Job,job_id)
        if job.owner_id!=current_user.id or job.status!='assigned':abort(403)
        job.status='awaiting_confirmation';db.session.commit()
        flash('Marked as work completed. A Bethorahzan administrator must verify and release payment.','success')
        return redirect(url_for('job_detail',job_id=job.id))

    @app.post('/portal/connect-payout')
    @login_required
    def connect_payout():
        if not require_stripe():return redirect(url_for('member_dashboard'))
        try:
            stripe.api_key=current_app.config['STRIPE_SECRET_KEY']
            if not current_user.stripe_account_id:
                account=stripe.Account.create(type='express',country='US',email=current_user.email,
                    capabilities={'transfers':{'requested':True}},metadata={'user_id':str(current_user.id)})
                current_user.stripe_account_id=account.id;db.session.commit()
            link=stripe.AccountLink.create(account=current_user.stripe_account_id,
                refresh_url=url_for('member_dashboard',_external=True),
                return_url=url_for('member_dashboard',_external=True),type='account_onboarding')
            return redirect(link.url,code=303)
        except stripe.StripeError:
            current_app.logger.exception('Connect onboarding failed')
            flash('Payout account setup is not available. Contact our team.','danger')
            return redirect(url_for('member_dashboard'))

    @app.route('/payment/result')
    def payment_result():
        return render_template('message.html',title='Thank you',message='Stripe is processing your payment. Your order, gift or project funding will update after payment is verified. View your portal for status.')

    @app.route('/payment/cancel')
    def payment_cancel():
        return render_template('message.html',title='Checkout canceled',message='No payment was confirmed. You may return to the previous page and try again.')

    @app.post('/stripe/webhook')
    @csrf.exempt
    def stripe_webhook():
        secret=current_app.config['STRIPE_WEBHOOK_SECRET']
        if not secret:return 'Not configured',503
        payload=request.get_data()
        try:
            stripe.api_key=current_app.config['STRIPE_SECRET_KEY']
            event=stripe.Webhook.construct_event(payload,request.headers.get('Stripe-Signature',''),secret)
        except (ValueError,stripe.SignatureVerificationError):return 'Bad signature',400
        if StripeEvent.query.filter_by(event_id=event['id']).first():return '',200
        etype=event['type'];obj=event['data']['object']
        if etype in ('checkout.session.completed','checkout.session.async_payment_succeeded'):
            if obj.get('payment_status')=='paid':
                kind=obj.get('metadata',{}).get('kind')
                try:pk=int(obj.get('metadata',{}).get('local_id'))
                except (ValueError,TypeError):return 'Invalid metadata',400
                model={'product':Purchase,'donation':Donation,'job':Job}.get(kind)
                record=db.session.get(model,pk) if model else None
                # Webhook must correspond to the most recent checkout and exact expected amount.
                if record is None or record.stripe_session_id!=obj['id'] or int(obj.get('amount_total',-1))!=(record.budget_cents if kind=='job' else record.amount_cents):
                    current_app.logger.error('Stripe checkout mismatch for %s id=%s',kind,pk)
                    return 'Checkout mismatch',400
                if kind=='job' and record.status=='awaiting_payment':
                    record.status='pending_review';record.stripe_payment_intent=obj.get('payment_intent') or ''
                elif kind in ('product','donation') and record.status=='pending':
                    record.status='paid';record.stripe_payment_intent=obj.get('payment_intent') or ''
                    if kind=='product' and record.product.fulfillment_type=='physical':
                        record.shipping_details=json.dumps(obj.get('shipping_details') or (obj.get('collected_information') or {}).get('shipping_details') or obj.get('customer_details',{}),ensure_ascii=False)[:3000]
                    if kind=='product' and record.product.inventory is not None and record.product.inventory>0:
                        record.product.inventory-=1
        elif etype in ('refund.updated','refund.failed'):
            job=Job.query.filter_by(stripe_refund_id=obj.get('id')).first()
            if job and job.status=='refund_pending':
                if obj.get('status')=='succeeded':job.status='refunded'
                elif obj.get('status')=='failed' or etype=='refund.failed':job.status='refund_failed'
        elif etype=='checkout.session.async_payment_failed':
            kind=obj.get('metadata',{}).get('kind')
            try:pk=int(obj.get('metadata',{}).get('local_id'))
            except (ValueError,TypeError):pk=None
            model={'product':Purchase,'donation':Donation}.get(kind)
            rec=db.session.get(model,pk) if model and pk else None
            if rec and rec.stripe_session_id==obj.get('id') and rec.status=='pending':rec.status='failed'
        db.session.add(StripeEvent(event_id=event['id'],event_type=etype))
        try:db.session.commit()
        except IntegrityError:
            db.session.rollback();return '',200
        return '',200

    # ADMIN: protected, full content lifecycle.
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        counts={'members':User.query.count(),'events':Event.query.count(),'teachings':Teaching.query.count(),'appointments':Appointment.query.filter_by(status='pending').count(),
                'jobs':Job.query.count(),'donations':Donation.query.filter_by(status='paid').count(),'inquiries':Inquiry.query.filter_by(status='new').count()}
        donations_total=db.session.query(func.coalesce(func.sum(Donation.amount_cents),0)).filter(Donation.status=='paid').scalar()
        recent=User.query.order_by(User.created_at.desc()).limit(5).all()
        review_jobs=Job.query.filter_by(status='pending_review').all()
        return render_template('admin/dashboard.html',counts=counts,donations_total=donations_total,recent=recent,review_jobs=review_jobs)

    @app.route('/admin/<section>')
    @admin_required
    def admin_list(section):
        registry={'members':(User,User.created_at),'events':(Event,Event.date),'teachings':(Teaching,Teaching.created_at),'appointments':(Appointment,Appointment.created_at),
                  'products':(Product,Product.created_at),'orders':(Purchase,Purchase.created_at),'causes':(Cause,Cause.id),
                  'donations':(Donation,Donation.created_at),'jobs':(Job,Job.created_at),'applications':(JobApplication,JobApplication.created_at),
                  'messages':(Inquiry,Inquiry.created_at)}
        if section not in registry:abort(404)
        model,sort=registry[section]
        page=max(1,request.args.get('page',1,type=int))
        items=model.query.order_by(sort.desc()).paginate(page=page,per_page=25,error_out=False)
        return render_template('admin/list.html',section=section,items=items)

    @app.route('/admin/<section>/new',methods=['GET','POST'])
    @app.route('/admin/<section>/<int:record_id>/edit',methods=['GET','POST'])
    @admin_required
    def admin_edit(section,record_id=None):
        editable={'events':Event,'teachings':Teaching,'products':Product,'causes':Cause,'members':User,'appointments':Appointment,'messages':Inquiry}
        if section not in editable:abort(404)
        model=editable[section]
        if section in ('members','appointments','messages') and record_id is None:abort(404)
        record=db.get_or_404(model,record_id) if record_id else model()
        if request.method=='POST':
            try:
                if section=='events':
                    record.title=form_value('title',220)
                    record.slug=unique_slug(Event,record.title,record.id)
                    record.category=form_value('category',45,'Gathering')
                    record.description=form_value('description',20000)
                    record.timezone=form_value('timezone',80,'America/New_York')
                    record.date=to_utc(parse_dt(request.form.get('date')),record.timezone)
                    record.end_date=to_utc(parse_dt(request.form['end_date']),record.timezone) if request.form.get('end_date') else None
                    if record.end_date and record.end_date <= record.date:raise ValueError('End date must be after start date.')
                    record.location=form_value('location',220,'Online')
                    record.image_url=form_value('image_url',500)
                    record.featured=bool(request.form.get('featured'))
                    record.published=bool(request.form.get('published'))
                    if not record.title or not record.description:raise ValueError('Title and description are required.')
                elif section=='teachings':
                    record.title=form_value('title',220)
                    record.slug=unique_slug(Teaching,record.title,record.id)
                    record.category=form_value('category',70,'Teaching')
                    record.scripture=form_value('scripture',160)
                    record.summary=form_value('summary',15000)
                    record.youtube_url=form_value('youtube_url',500)
                    record.published=bool(request.form.get('published'))
                    if not record.title or not record.summary:raise ValueError('Title and summary are required.')
                    if record.youtube_url and not youtube_embed(record.youtube_url):raise ValueError('Enter a valid HTTPS YouTube watch or youtu.be URL.')
                elif section=='products':
                    record.title=form_value('title',220)
                    record.slug=unique_slug(Product,record.title,record.id)
                    record.kind=form_value('kind',30)
                    record.fulfillment_type=form_value('fulfillment_type',20,'digital')
                    if record.fulfillment_type not in ('digital','physical'):raise ValueError('Choose digital or physical delivery.')
                    if record.kind not in ('book','course','merch'):raise ValueError('Unknown product category.')
                    record.description=form_value('description',15000)
                    record.price_cents=money_to_cents(request.form.get('price'),100,2_000_000)
                    record.image_url=form_value('image_url',500)
                    record.access_url=form_value('access_url',500)
                    record.inventory=int(request.form['inventory']) if request.form.get('inventory') else None
                    if record.inventory is not None and record.inventory<0:raise ValueError('Inventory must be nonnegative.')
                    record.active=bool(request.form.get('active'))
                    record.featured=bool(request.form.get('featured'))
                    if not record.title or not record.description:raise ValueError('Title and description are required.')
                elif section=='causes':
                    record.name=form_value('name',120)
                    record.slug=unique_slug(Cause,record.name,record.id)
                    record.description=form_value('description',3000)
                    record.icon=form_value('icon',60,'heart')
                    record.active=bool(request.form.get('active'))
                    if not record.name:raise ValueError('Name required.')
                elif section=='members':
                    record.name=form_value('name',140)
                    record.phone=form_value('phone',35);record.city=form_value('city',90);record.country=form_value('country',90)
                    record.interests=form_value('interests',500)
                    record.admin_notes=form_value('admin_notes',5000)
                    status=form_value('status',30)
                    role=form_value('role',30)
                    if status not in ('active','suspended') or role not in ('member','admin'):raise ValueError('Invalid member settings.')
                    if record.id==current_user.id and (role!='admin' or status!='active'):raise ValueError('You cannot suspend or demote your own admin account.')
                    record.status=status;record.role=role
                elif section=='appointments':
                    status=form_value('status',30)
                    if status not in ('pending','confirmed','completed','declined','canceled'):raise ValueError('Invalid appointment status.')
                    if status=='confirmed' and record.service=='Meeting with the Admiral':
                        conflict=Appointment.query.filter(Appointment.id!=record.id,Appointment.service=='Meeting with the Admiral',Appointment.status=='confirmed',Appointment.requested_at==record.requested_at).first()
                        if conflict:raise ValueError('The Admiral already has a confirmed appointment at that time.')
                    record.status=status;record.meeting_link=form_value('meeting_link',500)
                    record.private_response=form_value('private_response',2000)
                    if status=='confirmed' and not record.meeting_link:flash('Confirmed without a meeting link.','warning')
                elif section=='messages':
                    status=form_value('status',30)
                    if status not in ('new','reviewing','resolved'):raise ValueError('Invalid message status.')
                    record.status=status
                db.session.add(record);db.session.commit()
                flash(f'{section.capitalize()} saved.','success')
                return redirect(url_for('admin_list',section=section))
            except (ValueError,TypeError) as e:
                db.session.rollback();flash(str(e),'danger')
        return render_template('admin/edit.html',section=section,item=record,is_new=record_id is None)

    @app.post('/admin/<section>/<int:record_id>/delete')
    @admin_required
    def admin_delete(section,record_id):
        editable={'events':Event,'teachings':Teaching,'products':Product,'causes':Cause}
        if section not in editable:abort(403)
        item=db.get_or_404(editable[section],record_id)
        if section=='products' and Purchase.query.filter_by(product_id=record_id).first():
            item.active=False;flash('Product archived because orders reference it.','warning')
        elif section=='causes' and Donation.query.filter_by(cause_id=record_id).first():
            item.active=False;flash('Cause archived because donations reference it.','warning')
        else:
            db.session.delete(item);flash('Record deleted.','success')
        db.session.commit();return redirect(url_for('admin_list',section=section))

    @app.route('/admin/jobs/<int:job_id>')
    @admin_required
    def admin_job(job_id):
        job=db.get_or_404(Job,job_id)
        return render_template('admin/job.html',job=job)

    @app.post('/admin/jobs/<int:job_id>/action')
    @admin_required
    def admin_job_action(job_id):
        job=db.get_or_404(Job,job_id)
        action=form_value('action',35)
        if action=='approve' and job.status=='pending_review':
            job.approved=True;job.status='open';db.session.commit();flash('Funded job published.','success')
        elif action=='assign' and job.status=='open' and job.approved:
            try:app_id=int(request.form.get('application_id','0'))
            except ValueError:abort(400)
            application=JobApplication.query.filter_by(job_id=job.id,id=app_id).first_or_404()
            job.hired_user_id=application.user_id;job.status='assigned'
            for a in job.applicants:a.status='selected' if a.id==application.id else 'not_selected'
            db.session.commit();flash('Worker assigned.','success')
        elif action=='complete' and job.status in ('assigned','awaiting_confirmation'):
            job.status='awaiting_confirmation';db.session.commit();flash('Awaiting payment release verification.','info')
        elif action=='release' and job.status=='awaiting_confirmation' and job.hired_user_id and not job.stripe_transfer_id:
            if not require_stripe():return redirect(url_for('admin_job',job_id=job.id))
            worker=db.session.get(User,job.hired_user_id)
            if not worker or not worker.stripe_account_id:
                flash('Selected worker must complete Stripe Connect onboarding first.','danger')
            else:
                try:
                    stripe.api_key=current_app.config['STRIPE_SECRET_KEY']
                    account=stripe.Account.retrieve(worker.stripe_account_id)
                    if not account.get('payouts_enabled'):
                        raise ValueError('Worker payout account is not fully enabled.')
                    payment_intent=stripe.PaymentIntent.retrieve(job.stripe_payment_intent)
                    charge_id=payment_intent.get('latest_charge')
                    if not charge_id:raise ValueError('Could not verify the source charge for payout.')
                    transfer=stripe.Transfer.create(amount=job.worker_cents,currency='usd',
                        destination=worker.stripe_account_id,source_transaction=charge_id,
                        transfer_group=f'job_{job.id}',metadata={'job_id':str(job.id)},
                        idempotency_key=f'job-release-{job.id}')
                    job.stripe_transfer_id=transfer.id;job.status='completed';db.session.commit()
                    flash('Stripe transfer created for the worker.','success')
                except (stripe.StripeError,ValueError) as exc:
                    current_app.logger.exception('Stripe payout failure')
                    flash(f'Could not release transfer: {str(exc)[:180]}','danger')
        elif action=='refund' and job.status in ('pending_review','open','refund_failed') and not job.hired_user_id:
            if not require_stripe():return redirect(url_for('admin_job',job_id=job.id))
            try:
                stripe.api_key=current_app.config['STRIPE_SECRET_KEY']
                refund=stripe.Refund.create(payment_intent=job.stripe_payment_intent,reason='requested_by_customer',
                    metadata={'job_id':str(job.id)}, idempotency_key=f'job-refund-{job.id}-{job.stripe_refund_id or "initial"}')
                job.stripe_refund_id=refund.id;job.status='refund_pending' if refund.status=='pending' else 'refunded'
                job.approved=False;db.session.commit();flash('Refund requested from Stripe.','success')
            except stripe.StripeError:
                current_app.logger.exception('Stripe refund failure')
                flash('Unable to initiate refund. Check Stripe Dashboard.','danger')
        else:abort(400)
        return redirect(url_for('admin_job',job_id=job.id))

    @app.get('/admin/members/export.csv')
    @admin_required
    def export_members():
        out=io.StringIO();writer=csv.writer(out)
        writer.writerow(['id','name','email','phone','city','country','interests','status','role','joined'])
        for u in User.query.order_by(User.id).all():
            writer.writerow([u.id,u.name,u.email,u.phone,u.city,u.country,u.interests,u.status,u.role,u.created_at.isoformat()])
        return Response(out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=bethorahzan-members.csv'})

    @app.route('/privacy')
    def privacy():return render_template('legal.html',mode='privacy')
    @app.route('/terms')
    def terms():return render_template('legal.html',mode='terms')


def register_cli(app):
    @app.cli.command('init-db')
    def init_db():
        db.create_all()
        # Heroku invokes this during release. Provide default giving categories
        # only when none exist; never override administrative edits or removals.
        if db.session.query(Cause.id).first() is None:
            for name, description, icon in [
                ('Orphanages', 'Food, care and opportunities for children in vulnerable circumstances.', 'house-heart'),
                ('Widows & Families', 'Practical assistance, compassion and dignity for widows and families.', 'people'),
                ('Food Relief', 'Help communities facing severe food shortages and extreme poverty.', 'basket'),
                ('Community Outreach', 'Support local teams serving urgent needs in their communities.', 'globe')
            ]:
                db.session.add(Cause(name=name, slug=slugify(name), description=description, icon=icon))
            db.session.commit()
            click.echo('Created the four initial giving causes.')
        click.echo('Database tables initialized.')

    @app.cli.command('create-admin')
    @click.option('--email',prompt=True)
    @click.option('--name',prompt=True)
    @click.password_option()
    def create_admin(email,name,password):
        with app.app_context():
            if len(password)<10:raise click.ClickException('Password must be at least 10 characters.')
            email=email.strip().lower()
            existing=User.query.filter_by(email=email).first()
            if existing:
                existing.role='admin';existing.status='active';existing.set_password(password)
            else:
                existing=User(email=email,name=name.strip(),role='admin');existing.set_password(password);db.session.add(existing)
            db.session.commit();click.echo(f'Admin access configured for {email}')

    @app.cli.command('seed')
    def seed():
        with app.app_context():
            for name,desc,icon in [
                ('Orphanages','Supporting children with food, care and opportunities for a stronger future.','house-heart'),
                ('Widows & Families','Practical assistance, dignity and belonging for widows and households in need.','people'),
                ('Food Relief','Responding to severe food shortages and poverty in vulnerable communities.','basket'),
                ('Community Outreach','Equipping local teams to meet urgent needs and serve with compassion.','globe')]:
                slug=slugify(name)
                if not Cause.query.filter_by(slug=slug).first():db.session.add(Cause(name=name,slug=slug,description=desc,icon=icon))
            if not Event.query.first():
                for i,(title,cat,desc) in enumerate([
                    ('The Table: A Community Gathering','Gathering','A time of connection, fellowship, shared meals, and encouragement for the whole community.'),
                    ('Growth in Three Dimensions','Teaching','An intentional teaching session exploring body, soul and spirit through the principles of Christ.'),
                    ('An Evening of Prayer','Prayer','A community evening devoted to intercession, worship, and standing together in faith.')]):
                    date=(utcnow()+timedelta(days=14+21*i)).replace(hour=18,minute=30,second=0)
                    db.session.add(Event(title=title,slug=unique_slug(Event,title),category=cat,description=desc,date=date,timezone='UTC',location='Online · Details upon registration',featured=i==0))
            if not Product.query.first():
                for title,kind,desc,cents in [
                    ('The Three-Dimensional Life','book','A thoughtful introduction to whole-person growth, rooted in wisdom, community and faith.',1800),
                    ('Foundations of Purpose','course','A guided learning journey on purpose, service, character and purposeful leadership.',4900),
                    ('The Art of Stewardship','book','Principles for stewarding time, relationships, resources and responsibility.',2400)]:
                    db.session.add(Product(title=title,slug=unique_slug(Product,title),kind=kind,description=desc,price_cents=cents,featured=True))
            db.session.commit();click.echo('Starter causes, events and sample catalog created. Replace samples before launch.')


app=create_app()

if __name__=='__main__':
    app.run(debug=os.getenv('FLASK_DEBUG')=='1')
