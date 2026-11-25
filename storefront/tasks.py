from celery import shared_task


@shared_task(ignore_result=True)
def notify_search_engines(urls, deleted=False):
    from .indexing import notify
    notify(urls, deleted=deleted)


@shared_task(ignore_result=True)
def submit_all_urls(user_id=None):
    """Send every public product, category and post URL to IndexNow (admin button)."""
    from django.contrib.auth import get_user_model

    from . import seo
    from .indexing import indexnow_submit
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    urls = [seo.absolute("/")]
    urls += [seo.product_url(p) for p in seo.public_products().only("slug")]
    urls += [seo.category_url(c) for c in seo.public_categories().only("pk")]
    urls += [seo.post_url(p) for p in seo.public_posts().only("slug")]
    for i in range(0, len(urls), 10000):
        indexnow_submit(urls[i:i + 10000], user=user, force=True)


@shared_task(ignore_result=True)
def merchant_sync_product(product_id):
    from .merchant import sync_product
    sync_product(product_id)


@shared_task(ignore_result=True)
def merchant_sync_all(user_id=None):
    from django.contrib.auth import get_user_model

    from .merchant import sync_all
    user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
    sync_all(user=user)
