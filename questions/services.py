
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
import datetime
from users.models import Profile

class LimitService:
    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    @staticmethod
    def check_limits(user, request, quantity=1, question_type='MCQ', is_mock=False):
        """
        Check if user or guest can generate questions or take mock tests.
        Returns (allowed: bool, message: str)
        """
        now = timezone.now()

        # 1. Guest User Logic
        if not user.is_authenticated:
            if question_type == 'Written':
                 return False, "Written tests are for registered users only."
            
            ip = LimitService.get_client_ip(request)
            cache_key = f"guest_attempts_{ip}"
            attempts = cache.get(cache_key)
            current_attempts = int(attempts) if attempts else 0
            
            if current_attempts + quantity > 0:
                 return False, f"Please login for Free Tests."
            return True, None

        # 2. Authenticated User Logic
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            return False, "User profile error."

        # Check DB Resets
        profile.reset_monthly_if_needed()

        # Fetch Subscription Plan for Dynamic Limits (Case-insensitive lookup)
        from payments.models import SubscriptionPlan
        plan = SubscriptionPlan.objects.filter(plan_type__iexact=profile.subscription_type).first()
        
        # If no specific plan found, fallback to 'Free Core' or 'Free'
        if not plan:
            plan = SubscriptionPlan.objects.filter(plan_type__iexact="Free Core").first() or \
                   SubscriptionPlan.objects.filter(plan_type__iexact="Free").first()
        
        # --- DEBUG LOGGING (Terminal-এ দেখতে পাবেন) ---
        print(f"DEBUG: Checking limits for User: {user.username}")
        print(f"DEBUG: Profile plan_type: {profile.subscription_type}, Actual Plan found: {plan.plan_type if plan else 'None'}")
        
        if is_mock:
            # Check IELTS Mock Limit (Plan Limit or Extra Balance)
            # Default to 0 only if NO manual/fallback plan is found
            LIMIT_MOCK = plan.ielts_mock_limit if plan else 0
            
            print(f"DEBUG: MOCK Limit: {LIMIT_MOCK}, Used: {profile.ielts_mock_count}, Extra: {profile.extra_tests_balance}")
            
            # Allow if:
            # 1. Unlimited (-1)
            # 2. Used count is less than Limit (at least 1 left)
            # 3. Has extra balance
            if LIMIT_MOCK == -1 or (profile.ielts_mock_count < LIMIT_MOCK) or (profile.extra_tests_balance > 0):
                return True, None
            
            return False, f"আপনার {profile.subscription_type} প্ল্যানের মান্থলি মক টেস্ট লিমিট শেষ হয়েছে। দয়া করে এক্সাম প্যাক কিনুন অথবা প্রিমিয়াম প্ল্যানে আপগ্রেড করুন।"
        
        else:
            # Check AI Generation (Credits Limit or Extra Balance)
            # Default to 0 only if NO manual/fallback plan is found
            LIMIT_AI = plan.ai_credits_limit if plan else 0
            
            print(f"DEBUG: AI Limit: {LIMIT_AI}, Used: {profile.monthly_question_count}, Extra: {profile.extra_tests_balance}")
            
            # Allow if:
            # 1. Unlimited (-1)
            # 2. Used count is less than Limit (at least 1 left)
            # 3. Has extra balance
            if LIMIT_AI == -1 or (profile.monthly_question_count < LIMIT_AI) or (profile.extra_tests_balance > 0):
                return True, None
                
            return False, "আপনার AI ক্রেডিট লিমিট শেষ হয়েছে। দয়া করে এক্সাম প্যাক কিনুন অথবা প্রিমিয়াম প্ল্যানে আপগ্রেড করুন।"

        return True, None

    @staticmethod
    def increment_usage(user, request, count=1, question_type='MCQ', is_mock=False):
        if not user.is_authenticated:
            ip = LimitService.get_client_ip(request)
            cache_key = f"guest_attempts_{ip}"
            try:
                cache.incr(cache_key, count)
            except ValueError:
                cache.set(cache_key, count, timeout=86400)
            return

        profile = user.profile
        from payments.models import SubscriptionPlan
        plan = SubscriptionPlan.objects.filter(plan_type__iexact=profile.subscription_type).first()
        
        # Consistent fallback in increment_usage
        if not plan:
            plan = SubscriptionPlan.objects.filter(plan_type__iexact="Free Core").first() or \
                   SubscriptionPlan.objects.filter(plan_type__iexact="Free").first()
        
        if is_mock:
            # Deduct from Plan Limit first, then Extra Balance
            LIMIT_MOCK = plan.ielts_mock_limit if plan else 0
            if LIMIT_MOCK != -1 and (profile.ielts_mock_count >= LIMIT_MOCK):
                # Plan limit reached, reduce extra balance
                profile.extra_tests_balance = max(0, profile.extra_tests_balance - 1)
            else:
                # Still within plan limit
                profile.ielts_mock_count += 1
        else:
            # Deduct from AI Credits first, then Extra Balance
            LIMIT_AI = plan.ai_credits_limit if plan else 0
            if LIMIT_AI != -1 and (profile.monthly_question_count >= LIMIT_AI):
                # Plan limit reached, reduce extra balance
                profile.extra_tests_balance = max(0, profile.extra_tests_balance - 1)
            else:
                # Still within plan limit
                profile.monthly_question_count += count
            
        profile.save()

