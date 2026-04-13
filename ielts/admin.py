from django.contrib import admin
from . import models
import nested_admin

# Nested Admin setup to allow editing everything from one place

class AnswerInline(nested_admin.NestedStackedInline):
    model = models.Answer
    extra = 0
    fields = ("key", "accepted")

class ChoiceInline(nested_admin.NestedStackedInline):
    model = models.Choice
    extra = 0
    fields = ("label", "text", "is_correct", "order")
    verbose_name = "Option (MCQ/True/False)"
    verbose_name_plural = "Options (MCQ/True/False)"


class QuestionInline(nested_admin.NestedStackedInline):
    model = models.Question
    extra = 0
    show_change_link = True
    inlines = [ChoiceInline, AnswerInline]


class QuestionSectionInline(nested_admin.NestedStackedInline):
    model = models.QuestionSection
    extra = 0
    fields = (
        "title",
        "instruction_text",
        "question_type",
        "matching_options",
        "start_number",
        "end_number",
        "order",
    )
    show_change_link = True
    inlines = [QuestionInline]


class PassageInline(nested_admin.NestedStackedInline):
    model = models.Passage
    extra = 0
    show_change_link = True
    inlines = [QuestionSectionInline]


@admin.register(models.Test)
class TestAdmin(nested_admin.NestedModelAdmin):
    list_display = ('title', 'test_type', 'slug', 'duration_minutes', 'created_at')
    list_filter = ('test_type',)
    search_fields = ('title', 'description')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [PassageInline]


@admin.register(models.Passage)
class PassageAdmin(nested_admin.NestedModelAdmin):
    list_display = ('test', 'title', 'order')
    list_filter = ('test',)
    search_fields = ('title', 'content')
    inlines = [QuestionSectionInline]


@admin.register(models.QuestionSection)
class QuestionSectionAdmin(nested_admin.NestedModelAdmin):
    list_display = ('passage', 'title', 'question_type', 'start_number', 'end_number')
    list_filter = ('question_type', 'passage__test')
    search_fields = ('title', 'instruction_text')
    filter_horizontal = ("tags",)
    inlines = [QuestionInline]


@admin.register(models.Question)
class QuestionAdmin(nested_admin.NestedModelAdmin):
    list_display = ("section", "order", "get_test_name", "question_type_display")
    list_filter = ('section__question_type', 'section__passage__test')
    search_fields = ('text',)
    inlines = [ChoiceInline, AnswerInline]

    def question_type_display(self, obj):
        return obj.section.question_type if obj.section else ""
    question_type_display.short_description = "Type"
    
    def get_test_name(self, obj):
        return obj.section.passage.test.title if obj.section and obj.section.passage else ""
    get_test_name.short_description = "Test"


@admin.register(models.Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('question', 'key')
    search_fields = ('key', 'accepted')


@admin.register(models.Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ('user', 'test', 'score', 'submitted_at')
    list_filter = ('test', 'score')
    search_fields = ('user__username', 'test__title')

