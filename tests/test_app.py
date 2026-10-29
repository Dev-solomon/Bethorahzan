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
