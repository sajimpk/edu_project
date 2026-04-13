
from django.urls import path
from . import views

urlpatterns = [
    path('upgrade/', views.upgrade, name='upgrade'),
    path('success/', views.payment_success, name='payment_success'),
    path('cancel/', views.payment_cancel, name='payment_cancel'),
    path('checkout/manual/', views.manual_payment, name='manual_payment'),
    path('order-history/', views.order_history, name='order_history'),
]

