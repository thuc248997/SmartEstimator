from celery import shared_task

from .service import run_update


@shared_task(name="datasync.run_update", time_limit=3600)
def run_update_task(run_id: int, force: bool = False):
    run_update(run_id, force=force)
    return run_id
