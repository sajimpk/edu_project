from django.db import models
from django.contrib.auth.models import User

class TopicTag(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name

class UserWeakTopic(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='weak_topics')
    tag = models.ForeignKey(TopicTag, on_delete=models.CASCADE)
    error_count = models.PositiveIntegerField(default=0)
    total_attempts = models.PositiveIntegerField(default=0)
    
    @property
    def weakness_percentage(self):
        if self.total_attempts == 0:
            return 0
        return (self.error_count / self.total_attempts) * 100

    def __str__(self):
        return f"{self.user.username} - {self.tag.name}"
