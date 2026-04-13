from django.contrib import admin

from .models import PaymentConfiguration, SubscriptionPlan, Order

@admin.register(PaymentConfiguration)
class PaymentConfigurationAdmin(admin.ModelAdmin):
    list_display = ('name', 'bkash_number', 'nagad_number', 'is_active')

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'plan_type', 'price', 'ai_credits_limit', 'ielts_mock_limit', 'is_active')
    list_editable = ('price', 'is_active')

@admin.action(description="Approve selected orders and activate plan")
def approve_orders(modeladmin, request, queryset):
    for order in queryset.filter(status='Pending'):
        order.status = 'Approved'
        # Calling save() automatically updates the user's Profile
        order.save()

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'user', 'plan', 'amount', 'transaction_id', 'phone_number', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'transaction_id', 'phone_number', 'user__username')
    actions = [approve_orders]
