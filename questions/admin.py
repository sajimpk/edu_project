
from django.contrib import admin
from .models import Exam, Question, QuestionBank, AiQuestion

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    show_change_link = True
    fields = ('text', 'options', 'correct_answer', 'user_answer', 'is_correct')
    # Use readonly mostly to prevent accidental edits, but allow if needed.
    # For now, let's keep it editable but compact.

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'subject', 'level', 'difficulty', 'score', 'total_questions', 'created_at')
    list_filter = ('subject', 'level', 'difficulty', 'created_at')
    search_fields = ('user__username', 'subject', 'user__email')
    inlines = [QuestionInline]
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_text', 'exam_link', 'correct_answer', 'user_answer', 'is_correct')
    list_filter = ('is_correct', 'exam__subject', 'exam__level', 'exam__created_at')
    search_fields = ('text', 'explanation', 'exam__user__username')
    autocomplete_fields = ['exam']
    
    def short_text(self, obj):
        return obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
    short_text.short_description = "Question Text"

    def exam_link(self, obj):
        return obj.exam.subject
    exam_link.short_description = "Subject"

@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_text', 'subject', 'level', 'difficulty', 'question_type', 'created_at')
    list_filter = ('subject', 'level', 'difficulty', 'question_type', 'created_at')
    search_fields = ('text', 'explanation', 'subject', 'level', 'difficulty', 'question_type')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def short_text(self, obj):
        return obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
    short_text.short_description = "Question Text"

@admin.register(AiQuestion)
class AiQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'short_text', 'subject', 'level', 'question_type', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'subject', 'level', 'question_type', 'created_at')
    search_fields = ('text', 'explanation', 'subject')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    list_editable = ('is_approved',)
    filter_horizontal = ('tags',)

    def short_text(self, obj):
        return obj.text[:80] + "..." if len(obj.text) > 80 else obj.text
    short_text.short_description = "Question Text"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.is_approved:
            from .models import QuestionBank
            qb, created = QuestionBank.objects.get_or_create(
                text=obj.text,
                defaults={
                    'subject': obj.subject,
                    'level': obj.level,
                    'difficulty': obj.difficulty,
                    'question_type': obj.question_type,
                    'options': obj.options,
                    'correct_answer': obj.correct_answer,
                    'explanation': obj.explanation,
                }
            )
            # Add topics to QuestionBank
            if obj.tags.exists():
                qb.tags.set(obj.tags.all())
                
            # Remove from AiQuestion after successfully moving
            obj.delete()
