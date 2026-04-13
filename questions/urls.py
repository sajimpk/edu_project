
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('generate/', views.generate_test, name='generate_test'),
    path('generate/ajax/', views.ajax_generate_test, name='ajax_generate_test'),
    path('take-test/', views.take_test, name='take_test'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('exam/<int:exam_id>/take/', views.take_exam, name='take_exam'),
    path('exam/<int:exam_id>/result/', views.exam_result, name='exam_result'),
    path('exam/share/<int:exam_id>/', views.share_exam, name='share_exam'),
    path('exam/share/image/<int:exam_id>.jpg', views.share_exam_image, name='share_exam_image'),
    path('exam/<int:exam_id>/ai-feedback/', views.get_ai_feedback, name='get_ai_feedback'),
    path('about/', views.about, name='about'),
    path('privacy-policy/', views.privacy, name='privacy'),
    path('terms-of-service/', views.terms, name='terms'),
    path('test-policy/', views.test_policy, name='test_policy'),
    path('books/', views.books, name='books'),
]
