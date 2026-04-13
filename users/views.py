from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import PendingRegistration, Profile
from django.contrib.auth.models import User
from allauth.account.utils import perform_login
from .utils_email import generate_otp, send_otp_email
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.cache import never_cache

@login_required
@never_cache
def profile_view(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    # ❗ verification required
    if not profile.is_email_verified:
        messages.warning(request, "Please verify your email first.")
        return redirect("verify_signup_otp")

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name')
        request.user.last_name = request.POST.get('last_name')
        request.user.save()

        profile.phone_number = request.POST.get('phone_number')
        profile.save()

        messages.success(request, "Profile updated successfully!")
        return redirect('profile')

    return render(request, 'users/profile.html', {'profile': profile})


@never_cache
def verify_signup_otp(request):
    email = request.session.get("pending_verification_email")

    # 🔥 fallback (important)
    if not email:
        email = request.POST.get("email") or request.GET.get("email")

    if not email:
        messages.error(request, "Session expired. Please signup again.")
        return redirect("account_signup")
    print(f'email: {email}')
    pending_user = PendingRegistration.objects.filter(email=email).first()

    if not pending_user:
        messages.error(request, "Invalid session.")
        return redirect("account_signup")

    if request.method == "POST":
        otp_entered = request.POST.get("otp")

        # 🔐 brute force protection
        if pending_user.otp_attempts >= 5:
            messages.error(request, "Too many attempts. Request new OTP.")
            from django.urls import reverse
            return redirect(f"{reverse('resend_otp')}?email={email}")

        if pending_user.otp != otp_entered:
            pending_user.otp_attempts += 1
            pending_user.save()
            messages.error(request, "Invalid OTP.")
            from django.urls import reverse
            return redirect(f"{reverse('verify_signup_otp')}?email={email}")

        if not pending_user.is_valid():
            messages.error(request, "OTP expired. Please resend.")
            from django.urls import reverse
            return redirect(f"{reverse('resend_otp')}?email={email}")

        # ✅ CREATE USER ONLY AFTER VERIFY
        user = User.objects.create(
            username=pending_user.username,
            email=pending_user.email,
            password=pending_user.password  # already hashed
        )

        # ✅ Profile is created by signal, just update it
        profile = user.profile
        profile.is_email_verified = True
        profile.save()

        # 🧹 cleanup
        pending_user.delete()
        request.session.pop("pending_verification_email", None)

        messages.success(request, "✅ Email verified successfully!")

        return perform_login(request, user, email_verification="optional")

    return render(request, "account/verify_otp.html", {"email": email})

@never_cache
def resend_otp(request):
    email = request.session.get("pending_verification_email") or request.GET.get("email")

    if not email:
        messages.error(request, "Session expired.")
        return redirect("account_signup")

    pending_user = PendingRegistration.objects.filter(email=email).first()

    if not pending_user:
        messages.error(request, "No pending registration found.")
        return redirect("account_signup")

    otp = generate_otp()

    pending_user.otp = otp
    pending_user.otp_attempts = 0
    pending_user.created_at = timezone.now()  # reset expiry
    pending_user.save()

    send_otp_email(email, otp)

    messages.success(request, "New OTP sent.")
    from django.urls import reverse
    return redirect(f"{reverse('verify_signup_otp')}?email={email}")
