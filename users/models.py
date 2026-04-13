from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

class Profile(models.Model):
    SUBSCRIPTION_CHOICES = (
        ('Free', 'Free'),
        ('Monthly', 'Monthly'),
        ('Yearly', 'Yearly'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    is_paid = models.BooleanField(default=False)
    subscription_type = models.CharField(max_length=20, choices=SUBSCRIPTION_CHOICES, default='Free')
    subscription_expiry = models.DateTimeField(null=True, blank=True)
    is_email_verified = models.BooleanField(default=False)
    
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    monthly_question_count = models.IntegerField(default=0)
    ielts_mock_count = models.IntegerField(default=0)
    extra_tests_balance = models.IntegerField(default=0)
    last_month_reset = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} - {self.subscription_type}"

    def reset_monthly_if_needed(self):
        now = timezone.now()
        if now.month != self.last_month_reset.month or now.year != self.last_month_reset.year:
            self.monthly_question_count = 0
            self.ielts_mock_count = 0 
            self.last_month_reset = now
            self.save()

    def check_subscription_expiry(self):
        if self.is_paid and self.subscription_expiry:
             now = timezone.now()
             if now > self.subscription_expiry:
                self.is_paid = False
                self.subscription_type = 'Free'
                self.subscription_expiry = None
                self.save()
                from payments.models import Order
                Order.objects.filter(user=self.user, status='Approved').update(status='Expired')
                return True
        return False

class PendingRegistration(models.Model):
    username = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # hashed password
    otp = models.CharField(max_length=6)
    otp_attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return timezone.now() <= self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"{self.email} - OTP: {self.otp}"
