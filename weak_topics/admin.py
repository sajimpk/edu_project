from django.contrib import admin
from .models import TopicTag , UserWeakTopic

@admin.register(TopicTag)
class TopicTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(UserWeakTopic)
class UserWeakTopicAdmin(admin.ModelAdmin):
    list_display = ('user', 'tag', 'error_count', 'total_attempts')
    list_filter = ('tag', 'user')
    search_fields = ('user__username', 'tag__name')
