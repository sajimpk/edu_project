
from django.urls import path
from . import views

app_name = 'ielts'
urlpatterns = [
	path('', views.reading_home, name='reading_home'),
	# Legacy URLs (Removed as these used non-existent models)
	# path('<int:test_id>/start/', views.reading_test, name='reading_test'),
	# path('<int:test_id>/result/<int:result_id>/', views.reading_result, name='reading_result'),
	# path('save-answer/', views.save_answer, name='save_answer'),
	path('dashboard/', views.ielts_dashboard, name='dashboard'),
	# Cambridge-style exam endpoints
	path('test/<slug:test_slug>/exam/', views.exam_page, name='exam'),
	path('test/<slug:test_slug>/result/<int:result_id>/', views.result_page, name='result'),
	path('share/<int:result_id>/', views.share_result, name='share_result'),
]

