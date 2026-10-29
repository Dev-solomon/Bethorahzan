from datetime import datetime, timedelta
from models import db,User,Event,Appointment,Job,Donation
from conftest import authenticate


def test_public_pages(client):
    for path in ['/','/about','/impact','/events','/teachings','/giving','/shop','/opportunities','/contact','/join','/privacy','/terms','/healthz']:
        response=client.get(path)
        assert response.status_code==200,(path,response.status_code)
    assert b'Growth in 3 Dimensions' in client.get('/').data


def test_registration_and_profile(client,app):
    response=client.post('/join',data={'name':'Grace Member','email':'grace@example.com','password':'good-password-123','country':'USA'},follow_redirects=True)
    assert response.status_code==200
    assert b'Welcome back' in response.data
    with app.app_context():
        u=User.query.filter_by(email='grace@example.com').first()
        assert u and u.role=='member' and u.country=='USA'


def test_member_cannot_access_admin(client,member):
    authenticate(client,'member@example.com')
    assert client.get('/admin').status_code==403


def test_admin_event_crud_and_visibility(client,app,admin):
    authenticate(client,'admin@example.com')
    dt=(datetime.utcnow()+timedelta(days=15)).strftime('%Y-%m-%dT18:00')
    response=client.post('/admin/events/new',data={'title':'Community Gathering','category':'Gathering',
        'description':'A community of fellowship and learning.','date':dt,'timezone':'UTC','location':'Online',
        'published':'on'},follow_redirects=True)
    assert response.status_code==200
    with app.app_context():
        e=Event.query.first()
        assert e and e.slug=='community-gathering'
        event_id=e.id
    assert b'Community Gathering' in client.get('/events').data
    assert client.post(f'/admin/events/{event_id}/delete',follow_redirects=True).status_code==200
    with app.app_context():assert db.session.get(Event,event_id) is None


def test_appointment_request(client,app,member):
    authenticate(client,'member@example.com')
    when=(datetime.utcnow()+timedelta(days=10)).strftime('%Y-%m-%dT13:00')
    response=client.post('/appointments',data={'service':'One-on-one prayer','requested_at':when,
        'timezone':'UTC','notes':'Prayer for direction.'},follow_redirects=True)
    assert response.status_code==200
    with app.app_context():
        appointment=Appointment.query.first()
        assert appointment and appointment.status=='pending'
        assert appointment.service=='One-on-one prayer'


def test_job_pricing_and_moderation(client,app,member):
    authenticate(client,'member@example.com')
    response=client.post('/opportunities/post',data={'title':'Build a community website',
        'category':'Software & Technology','location':'Remote','budget':'200',
        'description':'Develop a complete responsive website and deliver source code to our team.'},follow_redirects=True)
    assert response.status_code==200
    with app.app_context():
        job=Job.query.first()
        assert job and job.budget_cents==20000 and job.worker_cents==18000 and job.platform_cents==2000
        assert job.status=='awaiting_payment' and not job.approved
    assert b'Build a community website' not in client.get('/opportunities').data



def test_checkout_uses_standard_stripe_payments_for_all_payment_types(app, monkeypatch):
    """Managed Payments can't process donations or the app's physical/Connect flows."""
    from app import create_checkout
    from stripe.checkout import Session

    requests = []

    def fake_create(**kwargs):
        requests.append(kwargs)
        return object()

    monkeypatch.setattr(Session, 'create', fake_create)
    with app.test_request_context('https://bethorahzan.example/giving'):
        for kind, physical in (('donation', False), ('product', True), ('job', False)):
            create_checkout(kind, 42, f'{kind} payment', 2500, 'donor@example.com', needs_shipping=physical)

    assert len(requests) == 3
    for params in requests:
        assert params['managed_payments'] == {'enabled': False}
        assert params['payment_method_types'] == ['card']
        assert params['success_url'].startswith('https://')
    assert 'shipping_address_collection' not in requests[0]
    assert 'shipping_address_collection' in requests[1]
    assert 'shipping_address_collection' not in requests[2]


def test_stripe_unconfigured_prevents_giving(client,app):
    with app.app_context():
        from models import Cause
        c=Cause(name='Food Relief',slug='food-relief');db.session.add(c);db.session.commit();cid=c.id
    response=client.post('/giving',data={'cause_id':cid,'amount':'30','name':'Donor','email':'donor@example.com'},follow_redirects=True)
    assert response.status_code==200
    with app.app_context(): assert Donation.query.count()==0


def test_untrusted_embed_rejected():
    from app import youtube_embed
    assert youtube_embed('https://www.youtube.com/watch?v=abcdefghijk')=='https://www.youtube-nocookie.com/embed/abcdefghijk'
    assert not youtube_embed('https://evil.example/embed/abcdefghijk')
    assert not youtube_embed('javascript:alert(1)')


def test_institutional_navigation_and_official_branding(client):
    response=client.get('/')
    assert response.status_code==200
    html=response.data.decode()
    for endpoint in ['/about','/events','/teachings','/impact','/appointments','/opportunities','/shop','/giving','/contact','/join']:
        assert f'href="{endpoint}"' in html
    assert 'id="institutionSidebar"' in html
    assert 'id="sidebarToggle"' in html
    assert 'id="jumpSearch"' in html
    assert 'bethorahzan-official-emblem.png' in html
    assert 'bethorahzan-wordmark-display.png' in html
    for asset in ['/static/css/institutional-v2.css',
                  '/static/js/institutional-v2.js',
                  '/static/img/bethorahzan-official-emblem.png',
                  '/static/img/bethorahzan-official-wordmark.png']:
        assert client.get(asset).status_code == 200, asset


def test_admin_navigation_retained(client, admin):
    from conftest import authenticate
    authenticate(client, 'admin@example.com')
    response=client.get('/admin')
    assert response.status_code==200
    html=response.data.decode()
    assert 'OFFICE OF ADMINISTRATION' in html
    assert 'Sign Out' in html
    assert 'href="/admin"' in html


def test_heroku_postgres_url_uses_installed_driver():
    from app import normalized_database_url
    assert normalized_database_url('postgres://u:p@db.example:5432/bethorahzan') == 'postgresql+psycopg://u:p@db.example:5432/bethorahzan'
    assert normalized_database_url('postgresql://u:p@db.example/bethorahzan') == 'postgresql+psycopg://u:p@db.example/bethorahzan'
    assert normalized_database_url('sqlite:///bethorahzan.db') == 'sqlite:///bethorahzan.db'


def test_official_heritage_brand_and_hero_art(client):
    page=client.get('/')
    assert page.status_code == 200
    html=page.data.decode()
    assert 'Welcome to' in html
    assert 'hero-wordmark-plate' in html
    assert 'brand-refinement.css' in html
    assert 'readingProgress' in html
    for path in ('/static/img/bethorahzan-official-emblem.png',
                 '/static/img/bethorahzan-official-wordmark.png',
                 '/static/img/bethorahzan-wordmark-display.png',
                 '/static/img/hero-institution.webp',
                 '/static/css/brand-refinement.css'):
        assert client.get(path).status_code == 200, path
    css=client.get('/static/css/brand-refinement.css').data.decode()
    assert 'Times New Roman' in css
    assert '@media (max-width:700px)' in css
    assert '@media (max-width:360px)' in css
    assert b'hero-institution.webp' in page.data



def test_institutional_v4_is_loaded_on_public_and_member_pages(client, member):
    """All page templates extend the shared full-bleed, tech-inspired shell."""
    paths = ['/', '/about', '/events', '/teachings', '/impact', '/giving',
             '/shop', '/opportunities', '/contact', '/login', '/join',
             '/privacy', '/terms']
    for path in paths:
        res = client.get(path)
        assert res.status_code == 200, path
        html = res.get_data(as_text=True)
        assert 'css/institutional-v4.css' in html, path
        assert 'js/institutional-v4.js' in html, path
        assert '<main id="main-content" class="site-route-' in html, path
        assert 'id="institutionSidebar"' in html, path
        assert 'href="/events"' in html and 'href="/giving"' in html
    authenticate(client, 'member@example.com')
    html = client.get('/portal').get_data(as_text=True)
    assert 'site-route-member_dashboard' in html
    assert 'css/institutional-v4.css' in html


def test_admin_v4_sidebar_links_and_active_state(client, admin):
    authenticate(client,'admin@example.com')
    html=client.get('/admin').get_data(as_text=True)
    assert 'class="admin-shell"' in html
    assert 'css/institutional-v4.css' in html
    assert 'aria-current="page"' in html
    assert 'href="/admin/members"' in html


def test_v4_static_assets_and_responsive_spacing(app):
    from pathlib import Path
    static=Path(app.static_folder)
    css=(static/'css'/'institutional-v4.css').read_text()
    js=(static/'js'/'institutional-v4.js').read_text()
    for reference in ['.site-container', '.page-hero', '.inner-section',
                      '.admin-shell', '.admin-sidebar', '.portal-nav',
                      '@media (max-width:767.98px)', '@media (max-width:420px)']:
        assert reference in css
    assert 'doc.createElement' in js and 'prefers-reduced-motion' in js
    for asset in ['hero-institution.webp', 'impact-network.webp', 'mission-landscape.webp',
                  'bethorahzan-official-emblem.png', 'bethorahzan-wordmark-display.png']:
        assert (static/'img'/asset).is_file()


def test_mobile_header_and_giving_layout(client):
    html=client.get('/giving').data.decode()
    assert 'id="mobileSearchToggle"' in html
    assert 'id="quickJump"' in html
    assert 'id="jumpSearch" aria-label="Search website sections"' in html
    assert 'Search website sections</label>' not in html
    assert 'id="causeCollectionTitle"' in html
    assert 'id="cause_id"' in html
    for asset in ['/static/css/header-giving-fix.css', '/static/js/header-giving-fix.js']:
        assert client.get(asset).status_code == 200


def test_giving_causes_seeded_on_init_db_and_preserved(client, app):
    from models import Cause
    runner = app.test_cli_runner()
    first=runner.invoke(args=['init-db'])
    assert first.exit_code == 0, first.output
    with app.app_context():
        rows=Cause.query.order_by(Cause.id).all()
        assert {c.name for c in rows} == {'Orphanages','Widows & Families','Food Relief','Community Outreach'}
        rows[0].description='Edited by an administrator'
        db.session.commit()
    again=runner.invoke(args=['init-db'])
    assert again.exit_code == 0, again.output
    with app.app_context():
        assert Cause.query.count() == 4
        assert Cause.query.order_by(Cause.id).first().description == 'Edited by an administrator'
    html = client.get('/giving').data.decode()
    for name in ['Orphanages','Widows &amp; Families','Food Relief','Community Outreach']:
        assert name in html
    assert html.count('data-select-cause=') == 4


def test_sidebar_full_page_height_on_desktop_only(client, app):
    """A full-height sidebar rail with sticky scrolling contents and a mobile drawer."""
    from pathlib import Path
    html = client.get('/').get_data(as_text=True)
    assert '<div class="institution-sidebar-inner">' in html
    assert html.index('<aside class="institution-sidebar"') < html.index('institution-sidebar-inner')
    assert html.index('institution-sidebar-inner') < html.index('</aside>')
    css = (Path(app.static_folder) / 'css' / 'institutional-v2.css').read_text()
    rules = css.split('/* DESKTOP FULL-HEIGHT SIDEBAR')[1]
    desktop, mobile = rules.split('@media (max-width:1150px)')
    assert '@media (min-width:1151px)' in desktop
    assert 'height:auto' in desktop and 'align-self:stretch' in desktop
    assert 'position:sticky' in desktop and 'height:100dvh' in desktop
    assert 'position:fixed' in mobile and 'overflow-y:auto' in mobile


def test_verified_stripe_book_purchase_reconciles_in_member_portal(client, app, member, monkeypatch):
    """The signed webhook remains primary; the portal can recover a missed one."""
    from models import Product, Purchase
    from stripe.checkout import Session

    with app.app_context():
        book = Product(title='Blood & Water', slug='blood-and-water', kind='book',
                       fulfillment_type='digital', description='Book', price_cents=2100, inventory=3)
        db.session.add(book)
        db.session.flush()
        purchase = Purchase(user_id=member, product_id=book.id, amount_cents=2100,
                            stripe_session_id='cs_test_book_payment')
        db.session.add(purchase)
        db.session.commit()
        purchase_id = purchase.id

    app.config['STRIPE_SECRET_KEY'] = 'sk_test_local'
    calls = []

    def get_session(session_id):
        calls.append(session_id)
        return {'id': 'cs_test_book_payment', 'mode': 'payment', 'status': 'complete',
                'payment_status': 'paid', 'currency': 'usd', 'amount_total': 2100,
                'metadata': {'kind': 'product', 'local_id': str(purchase_id)},
                'client_reference_id': f'product:{purchase_id}',
                'payment_intent': 'pi_test_confirmed'}

    monkeypatch.setattr(Session, 'retrieve', get_session)
    authenticate(client, 'member@example.com')
    response = client.get('/portal')
    assert response.status_code == 200
    assert b'PAID' in response.data
    assert calls == ['cs_test_book_payment']

    # Revisiting the portal must not deduct stock or call Stripe again.
    client.get('/portal')
    with app.app_context():
        book = Product.query.filter_by(slug='blood-and-water').one()
        order = db.session.get(Purchase, purchase_id)
        assert order.status == 'paid'
        assert order.stripe_payment_intent == 'pi_test_confirmed'
        assert book.inventory == 2
    assert calls == ['cs_test_book_payment']


def test_stripe_reconciliation_rejects_mismatched_or_unpaid_sessions(client, app, member, monkeypatch):
    from models import Product, Purchase
    from stripe.checkout import Session

    with app.app_context():
        book = Product(title='Unpaid Book', slug='unpaid-book', kind='book',
                       fulfillment_type='digital', description='Book', price_cents=1500)
        db.session.add(book)
        db.session.flush()
        purchase = Purchase(user_id=member, product_id=book.id, amount_cents=1500,
                            stripe_session_id='cs_test_unconfirmed')
        db.session.add(purchase)
        db.session.commit()
        purchase_id = purchase.id

    app.config['STRIPE_SECRET_KEY'] = 'sk_test_local'
    authenticated_session = {'id': 'cs_test_unconfirmed', 'mode': 'payment',
                             'status': 'complete', 'payment_status': 'paid',
                             'currency': 'usd', 'amount_total': 1499,
                             'metadata': {'kind': 'product', 'local_id': str(purchase_id)},
                             'client_reference_id': f'product:{purchase_id}'}
    monkeypatch.setattr(Session, 'retrieve', lambda sid: authenticated_session)
    authenticate(client, 'member@example.com')
    response = client.get('/payment/result?session_id=cs_test_unconfirmed')
    assert response.status_code == 200
    assert b'Payment confirmed' not in response.data
    client.get('/portal')
    with app.app_context():
        assert db.session.get(Purchase, purchase_id).status == 'pending'

    authenticated_session['amount_total'] = 1500
    authenticated_session['payment_status'] = 'unpaid'
    client.get('/portal')
    with app.app_context():
        assert db.session.get(Purchase, purchase_id).status == 'pending'

def test_paid_digital_books_open_only_for_verified_owner(client, app, member):
    from models import Product, Purchase

    with app.app_context():
        book = Product(title='Blood & Water', slug='blood-and-water-access', kind='book',
                       fulfillment_type='digital', description='Book', price_cents=2100,
                       access_url='https://files.example.org/blood-water.pdf')
        db.session.add(book)
        db.session.flush()
        order = Purchase(user_id=member, product_id=book.id, amount_cents=2100, status='pending')
        db.session.add(order)
        db.session.commit()
        book_id, order_id = book.id, order.id

    assert client.get(f'/library/{book_id}/open').status_code in (302, 401)
    authenticate(client, 'member@example.com')
    assert client.get(f'/library/{book_id}/open').status_code == 403
    assert b'Open Book' not in client.get('/portal').data

    with app.app_context():
        db.session.get(Purchase, order_id).status = 'paid'
        db.session.commit()

    portal = client.get('/portal')
    assert b'Open Book' in portal.data
    assert f'/library/{book_id}/open'.encode() in portal.data
    opened = client.get(f'/library/{book_id}/open')
    assert opened.status_code == 302
    assert opened.headers['Location'] == 'https://files.example.org/blood-water.pdf'

    client.post('/logout')
    assert client.get(f'/library/{book_id}/open').status_code == 302


def test_book_link_waits_for_admin_and_rejects_invalid_or_physical_access(client, app, member):
    from models import Product, Purchase

    with app.app_context():
        book = Product(title='Not Yet Published', slug='book-awaiting-access', kind='book',
                       fulfillment_type='digital', description='Book', price_cents=1800)
        unsafe = Product(title='Invalid URL', slug='invalid-resource-url', kind='book',
                         fulfillment_type='digital', description='Book', price_cents=1800,
                         access_url='javascript:alert(1)')
        physical = Product(title='Printed Book', slug='physical-book', kind='book',
                           fulfillment_type='physical', description='Book', price_cents=1800,
                           access_url='https://files.example.org/printed.pdf')
        db.session.add_all([book, unsafe, physical])
        db.session.flush()
        book_id, unsafe_id, physical_id = book.id, unsafe.id, physical.id
        db.session.add_all([Purchase(user_id=member, product_id=product_id, amount_cents=1800, status='paid')
                            for product_id in (book_id, unsafe_id, physical_id)])
        db.session.commit()

    authenticate(client, 'member@example.com')
    portal = client.get('/portal')
    assert b'Your access link has not been published yet' in portal.data
    assert client.get(f'/library/{book_id}/open', follow_redirects=True).status_code == 200
    assert b'Your payment is confirmed' in client.get(f'/library/{unsafe_id}/open', follow_redirects=True).data
    assert client.get(f'/library/{physical_id}/open').status_code == 404
