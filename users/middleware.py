from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from users.models import Profile

class SubscriptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                if hasattr(request.user, 'profile'):
                    if request.user.profile.check_subscription_expiry():
                        messages.warning(request, "আপনার সাবস্ক্রিপশন মেয়াদ শেষ হয়েছে। অনুগ্রহ করে নতুন একটি প্ল্যান নির্বাচন করুন।")
            except Exception:
                pass
        
        response = self.get_response(request)
        return response

class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check for authenticated users
        if request.user.is_authenticated:
            # Skip check for OTP page, logout, and static/media files
            exempt_paths = [
                reverse('verify_signup_otp'), 
                reverse('account_logout'),
                reverse('account_signup'),
                reverse('account_login'),
                '/accounts/confirm-email/',
                '/accounts/password/reset/key/',
                '/static/', 
                '/media/'
            ]
            
            # Check if current path is exempt OR if it's an admin path
            is_exempt = any(request.path.startswith(p) for p in exempt_paths) or request.path.startswith('/admin/')
            
            if not is_exempt:
                if hasattr(request.user, 'profile') and not request.user.profile.is_email_verified:
                    return redirect('account_signup')
        
        return self.get_response(request)

class RedirectAuthenticatedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # URLs that an authenticated user should not access
            restricted_paths = [
                reverse('account_inactive'),
                reverse('account_reauthenticate'),
                reverse('account_email'),
                reverse('account_reset_password'),
            ]
            
            # Check if current path matches any of the restricted paths
            # We use startswith to handle potential trailing slashes or sub-paths
            if any(request.path.startswith(p) for p in restricted_paths):
                return redirect('index')
                
        return self.get_response(request)
