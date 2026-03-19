import pytest
from app import app
from models import db

def test_minimal():
    assert True

def test_app_import():
    assert app is not None

def test_db_create():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        assert True
