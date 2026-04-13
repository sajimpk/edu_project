from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings
from django.contrib.sites.models import Site
from django.urls import reverse
from .utils_email import generate_otp, send_otp_email, send_api_email
from .models import PendingRegistration
from django.shortcuts import redirect
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
class MyAccountAdapter(DefaultAccountAdapter):
    def get_email_confirmation_url(self, request, emailconfirmation):
        site = Site.objects.get(pk=settings.SITE_ID)
        protocol = 'https' 
        path = reverse("account_confirm_email", args=[emailconfirmation.key])
        return f"{protocol}://{site.domain}{path}"

    def get_password_reset_url(self, request, user, temp_key):
        site = Site.objects.get(pk=settings.SITE_ID)
        protocol = 'https'
        path = reverse("account_reset_password_from_key", kwargs={'key': temp_key})
        return f"{protocol}://{site.domain}{path}"

    def send_mail(self, template_prefix, email, context):
        """Standard allauth mails (reset, etc.) sent via Brevo API"""
        try:
            msg = self.render_mail(template_prefix, email, context)
            html_content = ""
            if hasattr(msg, 'alternatives') and msg.alternatives:
                for alt in msg.alternatives:
                    if alt[1] == "text/html":
                        html_content = alt[0]
                        break
            if not html_content:
                html_content = f"<html><body>{msg.body}</body></html>"

            send_api_email(to_email=email, subject=msg.subject, html_content=html_content)
        except Exception as e:
            print(f"❌ ADAPTER EMAIL ERROR: {e}")

    def save_user(self, request, user, form, commit=True):
        # 1. Check if this is a social login
        is_social = False
        if form and hasattr(form, 'sociallogin'):
            is_social = True
        
        # 2. If it's social, let it through normally (no OTP)
        if is_social:
            user = super().save_user(request, user, form, commit=True)
            # Ensure email is verified for social login
            if hasattr(user, 'profile'):
                user.profile.is_email_verified = True
                user.profile.save()
            return user

        # 3. Standard Registration: Cleanup expired pending ones
        PendingRegistration.objects.filter(
            created_at__lt=timezone.now() - timedelta(minutes=10)
        ).delete()

        # 4. Standard Registration: Populate user fields without saving to DB yet
        user = super().save_user(request, user, form, commit=False)
        
        # Manual password hashing because we're delaying the save
        password = form.cleaned_data.get("password1") or form.cleaned_data.get("password")
        if password:
            user.set_password(password)

        # If user with same email exists, they might be re-registering or it's a conflict
        # But for regular flow, we want to proceed to OTP
        if User.objects.filter(email=user.email).exists():
            # If for some reason we got here with an existing user, just return them
            return User.objects.get(email=user.email)

        # 5. Create Pending Registration and Send OTP
        otp = generate_otp()
        PendingRegistration.objects.filter(email=user.email).delete()
        PendingRegistration.objects.create(
            username=user.username,
            email=user.email,
            password=user.password,
            otp=otp
        )

        # Session fix for verification page
        request.session['pending_verification_email'] = user.email
        request.session.modified = True
        request.session.save()

        send_otp_email(user.email, otp)

        # Redirect to OTP verification page
        raise ImmediateHttpResponse(
            redirect(f"{reverse('verify_signup_otp')}?email={user.email}")
        )
    def respond_user_signup(self, request, user):
        """Redirect after successful (and verified) signup"""
        return redirect('dashboard')

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        """
        Mark the user as verified since they've authenticated via a social provider.
        """
        user = super().save_user(request, sociallogin, form)
        # Ensure profile verification
        if hasattr(user, 'profile'):
            user.profile.is_email_verified = True
            user.profile.save()
        return user
