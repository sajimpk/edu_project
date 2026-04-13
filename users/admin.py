from django.contrib import admin
from .models import Profile, PendingRegistration

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'subscription_type', 'is_paid','is_email_verified', 'subscription_expiry', 'monthly_question_count')
    search_fields = ('user__username', 'user__email', 'stripe_customer_id')
    list_filter = ('subscription_type', 'is_paid','is_email_verified')

@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    list_display = ('email', 'username', 'otp', 'created_at')
    search_fields = ('email', 'username', 'otp')
   