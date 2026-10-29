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


def test_heroku_postgres_url_uses_installed_driver():
    from app import normalized_database_url
    assert normalized_database_url('postgres://u:p@db.example:5432/bethorahzan') == 'postgresql+psycopg://u:p@db.example:5432/bethorahzan'
    assert normalized_database_url('postgresql://u:p@db.example/bethorahzan') == 'postgresql+psycopg://u:p@db.example/bethorahzan'
    assert normalized_database_url('sqlite:///bethorahzan.db') == 'sqlite:///bethorahzan.db'
