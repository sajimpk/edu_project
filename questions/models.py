
from django.db import models
from django.contrib.auth.models import User
from ckeditor_uploader.fields import RichTextUploadingField

# ==========================================
# 📝 EXAM MODEL (স্টুডেন্টের পরীক্ষার লগ)
# ==========================================
# User এর পরীক্ষা দেওয়ার ডাটা সেভ করার মডেল। 
# কতগুলো প্রশ্ন ছিল, কতটা সঠিক হয়েছে তা এখানে থাকে।
class Exam(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exams')
    subject = models.CharField(max_length=100)
    level = models.CharField(max_length=50)
    difficulty = models.CharField(max_length=50)
    question_type = models.CharField(max_length=50)
    score = models.IntegerField(null=True, blank=True)
    total_questions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ai_analysis = RichTextUploadingField(null=True, blank=True)
    share_image_url = models.URLField(max_length=500, null=True, blank=True)
    
    MODE_CHOICES = (
        ('AI_PRACTICE', 'AI Practice'),
        ('FULL_EXAM', 'Full Exam'),
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='AI_PRACTICE')
    
    @property
    def duration(self):
        if self.completed_at:
            return self.completed_at - self.created_at
        return None


    def __str__(self):
        return f"{self.subject} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

# ==========================================
# 🗄️ QUESTION BANK MODEL (প্রমাপ ডাটাবেস)
# ==========================================
# AI যত প্রশ্ন তৈরি করে, তা এখানে সেভ হয়। 
# পরবর্তীতে কেউ একই ক্যাটাগরির প্রশ্ন চাইলে এই ডাটাবেস থেকে দেওয়া হয় (AI খরচ বাঁচাতে)।
class QuestionBank(models.Model):
    subject = models.CharField(max_length=100)
    level = models.CharField(max_length=50,default='Medium',blank=True)
    difficulty = models.CharField(max_length=50,blank=True,null=True)
    question_type = models.CharField(max_length=50)
    text = RichTextUploadingField(unique=True)
    options = models.JSONField(null=True, blank=True)
    correct_answer = models.TextField()
    explanation = RichTextUploadingField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField('weak_topics.TopicTag', blank=True, related_name='question_bank_questions')

    def save(self, *args, **kwargs):
        if self.text:
            self.text = self.text.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.text[:50]

# ==========================================
# 🤖 AI QUESTION MODEL (এগুলোর রিভিউ প্রয়োজন)
# ==========================================
# AI যত প্রশ্ন তৈরি করে, তা প্রথমে এখানে সেভ হয়। 
# এডমিন রিভিউ করে টপিক (tags) দিলে তবেই Question Bank-এ যায়।
class AiQuestion(models.Model):
    subject = models.CharField(max_length=100)
    level = models.CharField(max_length=50, default='Medium', blank=True)
    difficulty = models.CharField(max_length=50, blank=True, null=True)
    question_type = models.CharField(max_length=50)
    text = RichTextUploadingField()
    options = models.JSONField(null=True, blank=True)
    correct_answer = models.TextField()
    explanation = RichTextUploadingField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    is_approved = models.BooleanField(default=False)
    tags = models.ManyToManyField('weak_topics.TopicTag', blank=True, related_name='ai_generated_questions')

    def save(self, *args, **kwargs):
        if self.text:
            self.text = self.text.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.text[:50]

# ==========================================
# ❓ QUESTION MODEL (পরীক্ষার নির্দিষ্ট প্রশ্ন)
# ==========================================
# মেইন Question Bank থেকে ডাটা কপি হয়ে এখানে আসে, যাতে 
# স্টুডেন্ট কি উত্তর দিয়েছে এবং সঠিক কি না তা ট্র্যাক করা যায়।
class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, null=True, blank=True)
    
    # Legacy/Snapshot fields (Populated from Bank)
    text = RichTextUploadingField(null=True, blank=True)
    options = models.JSONField(null=True, blank=True) 
    correct_answer = models.TextField(null=True, blank=True) 
    explanation = RichTextUploadingField(null=True, blank=True)
    
    # Store user's interaction
    user_answer = models.TextField(null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    feedback = models.TextField(null=True, blank=True) 
    tags = models.ManyToManyField('weak_topics.TopicTag', blank=True, related_name='exam_questions')

    def __str__(self):
        return self.text[:50] if self.text else "Question"
