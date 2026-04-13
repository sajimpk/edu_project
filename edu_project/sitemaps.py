from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from blog.models import Post
from ielts.models import Test

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return [
            'index', 
            'about', 
            'privacy', 
            'terms', 
            'test_policy', 
            'books', 
            'generate_test', 
            'take_test', 
            'ielts:reading_home', 
            'blog:post_list'
        ]

    def location(self, item):
        return reverse(item)

class BlogSitemap(Sitemap):
    priority = 0.6
    changefreq = 'weekly'
    protocol = 'https'

    def items(self):
        return Post.objects.filter(status='published').order_by('-created_at')

    def location(self, obj):
        return reverse('blog:post_detail', args=[obj.slug])

class IeltsTestSitemap(Sitemap):
    priority = 0.7
    changefreq = 'monthly'
    protocol = 'https'

    def items(self):
        return Test.objects.all().order_by('-id')

    def location(self, obj):
        return reverse('ielts:exam', args=[obj.slug])
