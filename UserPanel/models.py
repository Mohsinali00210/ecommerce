from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models
from django.utils.text import slugify

# Assumes BaseAuditModel (created_at/updated_at) and Tag already exist in this app,
# as used elsewhere in the project.

class BaseAuditModel(models.Model):
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_created")
    modified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="%(class)s_modified")

    class Meta:
        abstract = True
class BTag(BaseAuditModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
class BlogCategory(BaseAuditModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Blog Categories"


class BlogPost(BaseAuditModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="blog_posts"
    )
    category = models.ForeignKey(
        BlogCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts"
    )
    tags = models.ManyToManyField("BTag", blank=True, related_name="blog_posts")

    featured_image = models.ImageField(upload_to="blog/%Y/%m/")
    excerpt = models.TextField(blank=True, help_text="Short summary shown on the blog list page")
    content = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="published")
    published_at = models.DateTimeField(null=True, blank=True)
    read_time_minutes = models.PositiveIntegerField(default=3)
    views = models.PositiveIntegerField(default=0)

    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ["-published_at"]


import re

from django.core.exceptions import ValidationError
from django.db import models

# ---------------------------------------------------------------------------
# Paste this into your app's models.py  (then: makemigrations + migrate)
# ---------------------------------------------------------------------------

# A link may only point to: a page on this site ("/shop/"), an anchor ("#reviews"),
# a full URL, or a phone / email / sms link. This blocks "javascript:" and "data:" links.
_SAFE_HREF = re.compile(r"^(#|/|https?://|tel:|mailto:|sms:)", re.IGNORECASE)


def validate_href(value):
    if value and not _SAFE_HREF.match(value.strip()):
        raise ValidationError(
            "Use a page path (/shop/), an anchor (#top), a full URL (https://…), "
            "or tel: / mailto: / sms:."
        )


class TopbarItem(models.Model):
    """One entry in the strip at the very top of the site (edited at /manage/topbar/)."""

    SIDE_CHOICES = [
        ("left", "Left side"),
        ("right", "Right side"),
    ]

    KIND_CHOICES = [
        ("text", "Text (no link)"),
        ("link", "Link"),
        ("divider", "Divider  |"),
    ]

    VISIBLE_CHOICES = [
        ("always", "All screens"),
        ("sm", "Small screens and up (576px+)"),
        ("md", "Tablets and up (768px+)"),
        ("lg", "Laptops and up (992px+)"),
    ]

    side = models.CharField(max_length=5, choices=SIDE_CHOICES, default="left")
    kind = models.CharField(max_length=7, choices=KIND_CHOICES, default="text")

    label = models.CharField(max_length=120, blank=True)
    icon = models.CharField(
        max_length=60, blank=True,
        help_text="Bootstrap Icons class, e.g. bi-truck",
    )
    href = models.CharField(max_length=500, blank=True, validators=[validate_href])
    open_in_new_tab = models.BooleanField(default=False)

    visible_from = models.CharField(max_length=6, choices=VISIBLE_CHOICES, default="always")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["side", "order", "id"]

    def __str__(self):
        return f"{self.side}: {self.label or self.kind}"

    # Bootstrap classes that hide the item on small screens.
    # Spans are laid out with flex, anchors / dividers inline, hence two variants.
    @property
    def css_flex(self):
        return "" if self.visible_from == "always" else f"d-none d-{self.visible_from}-flex"

    @property
    def css_inline(self):
        return "" if self.visible_from == "always" else f"d-none d-{self.visible_from}-inline"


# What the topbar looked like before it became editable. The manager page offers
# a one-click "Add starter items" that creates exactly this.
DEFAULT_TOPBAR_ITEMS = [
    {"side": "left", "kind": "text", "icon": "bi-truck",
     "label": "Free Delivery on Orders over PKR 3,500", "visible_from": "always"},
    {"side": "left", "kind": "text", "icon": "bi-cash-coin",
     "label": "Cash on Delivery Available", "visible_from": "md"},
    {"side": "left", "kind": "text", "icon": "bi-arrow-repeat",
     "label": "Easy 7 Days Returns", "visible_from": "lg"},

    {"side": "right", "kind": "link", "icon": "bi-geo-alt", "label": "Track Order", "href": "#"},
    {"side": "right", "kind": "link", "icon": "", "label": "Help Center", "href": "#"},
    {"side": "right", "kind": "divider"},
    {"side": "right", "kind": "link", "icon": "bi-telephone",
     "label": "+92 3090900926", "href": "tel:+923090900926"},
]