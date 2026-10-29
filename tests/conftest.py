import pytest
from app import create_app
from models import db, User

@pytest.fixture
def app():
    app=create_app({'TESTING':True,'WTF_CSRF_ENABLED':False,
                    'SECRET_KEY':'test-secret-key',
                    'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:',
                    'STRIPE_SECRET_KEY':'','STRIPE_WEBHOOK_SECRET':''})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def member(app):
    with app.app_context():
        u=User(name='Test Member',email='member@example.com',role='member')
        u.set_password('A-long-test-password-123')
        db.session.add(u);db.session.commit()
        return u.id

@pytest.fixture
def admin(app):
    with app.app_context():
        u=User(name='Test Administrator',email='admin@example.com',role='admin')
        u.set_password('A-long-test-password-123')
        db.session.add(u);db.session.commit()
        return u.id


def authenticate(client,email):
    return client.post('/login',data={'email':email,'password':'A-long-test-password-123'},follow_redirects=True)
