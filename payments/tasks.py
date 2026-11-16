from celery import shared_task


@shared_task
def expire_unpaid_online_orders():
    from .services import expire_unpaid
    return expire_unpaid()
