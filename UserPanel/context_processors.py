from django.conf import settings
from django.core.cache import cache

from .models import TOPBAR_CACHE_KEY, TopbarItem


def topbar(request):
    """Adds `topbar_left` and `topbar_right` (lists of dicts) to every template."""
    data = cache.get(TOPBAR_CACHE_KEY)
    if data is None:
        items = TopbarItem.objects.filter(is_active=True, is_deleted=False).order_by("sort_order", "id")
        data = {
            "topbar_left": [i.as_dict() for i in items if i.position == TopbarItem.Position.LEFT],
            "topbar_right": [i.as_dict() for i in items if i.position == TopbarItem.Position.RIGHT],
        }
        cache.set(TOPBAR_CACHE_KEY, data, getattr(settings, "TOPBAR_CACHE_SECONDS", 300))
    return data
