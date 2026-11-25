"""Ping search engines (IndexNow / Google Indexing API) when public pages change."""
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

DEDUPE_SECONDS = 600  # the same URL is sent at most once per 10 minutes


def _engines_on():
    from .models import SeoSettings
    s = SeoSettings.get()
    return (s.indexnow_enabled or s.google_indexing_enabled) and not s.hide_from_search_engines


def _queue(url, deleted):
    if not url or not cache.add(f"indexing:sent:{deleted}:{url}", 1, DEDUPE_SECONDS):
        return
    from .tasks import notify_search_engines
    transaction.on_commit(lambda: notify_search_engines.delay([url], deleted))


@receiver(post_save, sender="products.Product", dispatch_uid="storefront_product_indexing")
def product_changed(sender, instance, raw=False, **kwargs):
    if raw or not instance.slug:
        return
    try:
        if not _engines_on():
            return
        from . import seo
        public = seo.public_products().filter(pk=instance.pk).exists()
        _queue(seo.product_url(instance), deleted=not public)
    except Exception:  # never block saving a product
        import logging
        logging.getLogger("storefront.indexing").exception("Could not queue product for indexing")


@receiver(post_save, sender="UserPanel.BlogPost", dispatch_uid="storefront_post_indexing")
def post_changed(sender, instance, raw=False, **kwargs):
    if raw or not instance.slug:
        return
    try:
        if not _engines_on():
            return
        from . import seo
        public = seo.public_posts().filter(pk=instance.pk).exists()
        _queue(seo.post_url(instance), deleted=not public)
    except Exception:
        import logging
        logging.getLogger("storefront.indexing").exception("Could not queue post for indexing")


@receiver(post_save, sender="products.Product", dispatch_uid="storefront_product_merchant")
def product_merchant_sync(sender, instance, raw=False, **kwargs):
    """Keep Google Merchant Center in step with the shop (Merchant API, when switched on)."""
    if raw:
        return
    try:
        from .models import SeoSettings
        s = SeoSettings.get()
        if not (s.merchant_api_enabled and s.merchant_auto_sync):
            return
        if not cache.add(f"merchant:queued:{instance.pk}", 1, 30):
            return  # several saves in a row (admin form + inlines) -> one sync
        from .tasks import merchant_sync_product
        pk = instance.pk
        transaction.on_commit(lambda: merchant_sync_product.apply_async(args=[pk], countdown=20))
    except Exception:
        import logging
        logging.getLogger("storefront.merchant").exception("Could not queue product for Merchant API")
