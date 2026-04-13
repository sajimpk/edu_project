
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView
from edu_project.sitemaps import StaticViewSitemap, BlogSitemap, IeltsTestSitemap

sitemaps = {
    'static': StaticViewSitemap,
    'blog': BlogSitemap,
    'ielts': IeltsTestSitemap,
}

from users.views import verify_signup_otp, resend_otp, profile_view

urlpatterns = [
    path('accounts/verify-otp/', verify_signup_otp, name='verify_signup_otp'),
    path('accounts/resend-otp/', resend_otp, name='resend_otp'),
    path('accounts/profile/', profile_view, name='profile'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('questions.urls')),
    path('billing/', include('payments.urls')), # Proper prefix
    path('ielts/', include('ielts.urls')), # Proper prefix
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('_nested_admin/', include('nested_admin.urls')),
    path('blog/', include('blog.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Always serve media files locally (no Cloudinary)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)