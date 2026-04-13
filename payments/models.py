
from django.db import models

# ==========================================
# 💳 STRIPE PRODUCT MODELS
# ==========================================
# স্টাইপ (Stripe) পেমেন্ট গেটওয়ের জন্য প্রোডাক্ট এবং প্রাইস আইডি সেভ রাখার মডেল
class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.IntegerField(default=0)  # In cents (paisa)
    stripe_product_id = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=100)

    def __str__(self):
        return self.name

# ==========================================
# 📑 PAYMENT TRACKING
# ==========================================
class Payment(models.Model):
     user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
     stripe_checkout_id = models.CharField(max_length=500)
     payment_status = models.CharField(max_length=50, default='pending')
     created_at = models.DateTimeField(auto_now_add=True)

class PaymentConfiguration(models.Model):
    name = models.CharField(max_length=100, default="Global Payment Number")
    bkash_number = models.CharField(max_length=15, default="018********")
    nagad_number = models.CharField(max_length=15, default="018********")
    rocket_number = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Payment Configuration"
        verbose_name_plural = "Payment Configurations"

    def __str__(self):
        return self.name

# ==========================================
# 💎 SUBSCRIPTION PLANS (প্ল্যান ম্যানেজমেন্ট)
# ==========================================
class SubscriptionPlan(models.Model):
    PLAN_CHOICES = (
        ('Free', 'Free Core'),
        ('ExamPack', 'Exam Pack (One-time)'),
        ('Monthly', 'Pro Monthly'),
        ('Yearly', 'Pro Yearly'),
    )

    name = models.CharField(max_length=100, help_text="প্ল্যানের নাম (যেমন: Pro Monthly)")
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Limits
    ai_credits_limit = models.IntegerField(default=50, help_text="প্রতি মাসে কয়টি AI প্রশ্ন জেনারেট করতে পারবে (-1 মানে আনলিমিটেড)")
    ielts_mock_limit = models.IntegerField(default=0, help_text="কয়টি ফুল IELTS মডেল টেস্ট দিতে পারবে (-1 মানে আনলিমিটেড)")
    
    features = models.TextField(blank=True, help_text="ফিচারগুলো কমা (,) দিয়ে লিখুন")
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = "Subscription Plan"
        verbose_name_plural = "Subscription Plans"

    def __str__(self):
        return f"{self.name} - {self.price} BDT"

import uuid

class Order(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Cancelled', 'Cancelled'),
        ('Expired', 'Expired'),
    )

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    plan = models.ForeignKey('SubscriptionPlan', on_delete=models.SET_NULL, null=True)
    order_number = models.CharField(max_length=50, unique=True, editable=False)
    transaction_id = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
            
        old_status = 'Pending'
        if self.pk:
            try:
                old_status = Order.objects.get(pk=self.pk).status
            except Order.DoesNotExist:
                pass
                
        super().save(*args, **kwargs)
        
        # Automatic Profile updates based on Order status changes
        if old_status != self.status:
            profile = self.user.profile
            plan = self.plan
            from django.utils import timezone
            from datetime import timedelta
            
            if self.status == 'Approved' and plan:
                if plan.plan_type == 'ExamPack':
                    profile.extra_tests_balance += plan.ielts_mock_limit
                else:
                    profile.is_paid = True
                    profile.subscription_type = plan.plan_type
                    if plan.plan_type == 'Monthly':
                        profile.subscription_expiry = timezone.now() + timedelta(days=30)
                    elif plan.plan_type == 'Yearly':
                        profile.subscription_expiry = timezone.now() + timedelta(days=365)
                profile.save()
            elif self.status in ['Cancelled', 'Expired']:
                if not plan or plan.plan_type != 'ExamPack':
                    profile.is_paid = False
                    profile.subscription_type = 'Free'
                    profile.subscription_expiry = None
                    profile.save()

    def __str__(self):
        return f"{self.order_number} - {self.user.username}"
