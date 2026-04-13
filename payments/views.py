
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib import messages
from users.models import Profile
from django.views.decorators.cache import never_cache
from .models import PaymentConfiguration, SubscriptionPlan

@never_cache
def upgrade(request):
    """Show Pricing Plans"""
    profile = None
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
        except Profile.DoesNotExist:
            profile = Profile.objects.create(user=request.user)
    
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    for plan in plans:
        if plan.features:
            plan.feature_list = [f.strip() for f in plan.features.split(',')]
        else:
            plan.feature_list = []
            
    return render(request, 'payments/upgrade.html', {'profile': profile, 'plans_list': plans})

from django.utils import timezone
from datetime import timedelta

@login_required
@never_cache
def payment_success(request):
    """
    Handle successful order submission.
    """
    if request.method == 'POST':
        plan_type = request.GET.get('plan')
        trx_id = request.POST.get('trx_id')
        phone_number = request.POST.get('phone_number')
        
        from .models import Order
        plan = SubscriptionPlan.objects.filter(plan_type=plan_type).first()
        
        # Create an Order
        Order.objects.create(
            user=request.user,
            plan=plan,
            transaction_id=trx_id,
            phone_number=phone_number,
            amount=plan.price if plan else 0.00,
            status='Pending'
        )
        
        # Display success message
        plan_name = plan.name if plan else plan_type
        messages.success(request, f"🎉 Your order for {plan_name} has been submitted! It is pending admin approval.")
        
        import urllib.parse
        msg = urllib.parse.quote(f"Hello, I have made a payment. Phone: {phone_number}, TrxID: {trx_id}, Plan: {plan_name}. Please approve.")
        request.session['wa_url'] = f"https://wa.me/8801805050045?text={msg}"
        return redirect('payment_success')

    wa_url = request.session.get('wa_url', None)
    return render(request, 'payments/payment_success.html', {'wa_url': wa_url})

@login_required
@never_cache
def order_history(request):
    """Show user's order history with pagination."""
    from .models import Order
    from django.core.paginator import Paginator
    
    order_list = Order.objects.filter(user=request.user).order_by('-created_at')
    paginator = Paginator(order_list, 10) # 10 orders per page
    
    page_number = request.GET.get('page')
    orders = paginator.get_page(page_number)
    
    return render(request, 'payments/order_history.html', {'orders': orders})
    

@login_required
@never_cache
def payment_cancel(request):
    """Show cancellation message"""
    messages.warning(request, "Payment was cancelled.")
    return render(request, 'payments/payment_cancel.html')

from .models import PaymentConfiguration

@login_required # Ensure user is logged in
@never_cache
def manual_payment(request):
    """
    Show manual payment instructions (Bkash/Nagad/Rocket).
    """
    plan_type = request.GET.get('plan', 'Monthly')
    
    # Get plan price from DB
    plan = SubscriptionPlan.objects.filter(plan_type=plan_type).first()
    amount = plan.price if plan else "500"
    
    # Get config from DB
    config = PaymentConfiguration.objects.filter(is_active=True).first()
    payment_number = config.bkash_number if config else "01805050045"
    
    context = {
        'plan_type': plan_type,
        'amount': amount,
        'payment_number': payment_number
    }
    return render(request, 'payments/manual_payment.html', context)
