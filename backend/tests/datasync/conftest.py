import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def admin_client(db):
    c = APIClient()
    c.force_authenticate(get_user_model().objects.create_user("admin2", password="x", is_staff=True))
    return c


@pytest.fixture
def client(db):
    c = APIClient()
    c.force_authenticate(get_user_model().objects.create_user("viewer", password="x", is_staff=False))
    return c
