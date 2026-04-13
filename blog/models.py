from django.db import models
from django.contrib.auth.models import User
from ckeditor_uploader.fields import RichTextUploadingField
from django.utils.text import slugify

# ==========================================
# 🏷️ CATEGORY MODEL (ব্লগের ক্যাটাগরি)
# ==========================================
# ব্লগের বিভিন্ন টপিক আলাদা করার জন্য এই মডেল (যেমন: IELTS Tips, SSC Suggestion)।
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Categories"

# ==========================================
# ✍️ POST MODEL (মূল ব্লগ পোস্ট)
# ==========================================
# অ্যাডমিন প্যানেল থেকে লেখা প্রতিটি আর্টিকেল এই মডেলে সেভ হয়। 
# CKEditor ব্যবহার করে rich-text কন্টেন্ট রাখা হয়।
class Post(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('published', 'Published'),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_posts')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
    featured_image = models.ImageField(upload_to='blog/images/', blank=True, null=True)
    featured_image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Direct link to the featured image (YouTube/External).")
    content = RichTextUploadingField()
    excerpt = models.TextField(max_length=500, blank=True, help_text="Short summary for the blog card.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)

    @property
    def get_featured_image_url(self):
        if self.featured_image:
            return self.featured_image.url
        elif self.featured_image_url:
            return self.featured_image_url
        return None

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
