from celery import shared_task


@shared_task(name="calculation.execute_run")
def execute_run(run_id: int) -> int:
    from .services import execute_run_now

    execute_run_now(run_id)
    return run_id
