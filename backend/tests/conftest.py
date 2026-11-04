import pytest


@pytest.fixture(autouse=True)
def _celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.MEDIA_ROOT = str(settings.BASE_DIR / "media" / "test")
