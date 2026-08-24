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