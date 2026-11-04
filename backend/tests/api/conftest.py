from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.catalog.loader import load_catalog
from apps.regulations.loader import load_rule_pack

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture
def seeded(db):
    pack = load_rule_pack(FIXTURES / "rule_pack_tt36_2026.json")
    norm_rel, price_rel = load_catalog(FIXTURES / "sample_catalog.json")
    return {"pack": pack, "norm": norm_rel, "price": price_rel}


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("ks", password="x", is_staff=True)


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c
