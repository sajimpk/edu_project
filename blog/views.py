from django.shortcuts import render, get_object_or_404
from .models import Post, Category
from django.core.paginator import Paginator
from django.views.decorators.cache import cache_page

@cache_page(60 * 15,key_prefix="blog_list_page")
def post_list(request):
    posts_all = Post.objects.filter(status='published').order_by('-created_at')
    categories = Category.objects.all()
    
    # Category filter
    category_slug = request.GET.get('category')
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        posts_all = posts_all.filter(category=category)
    
    # Pagination
    paginator = Paginator(posts_all, 6) # 6 posts per page
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    featured_posts = Post.objects.filter(status='published', is_featured=True)[:3]
    
    context = {
        'posts': posts,
        'categories': categories,
        'featured_posts': featured_posts
    }
    return render(request, 'blog/post_list.html', context)

@cache_page(60 * 15,key_prefix="blog_detail_page")
def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, status='published')
    related_posts = Post.objects.filter(status='published', category=post.category).exclude(id=post.id)[:3]
    
    context = {
        'post': post,
        'related_posts': related_posts
    }
    return render(request, 'blog/post_detail.html', context)
