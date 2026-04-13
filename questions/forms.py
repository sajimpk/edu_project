
from django import forms

SUBJECT_CHOICES = [
    ('Mathematics', 'Mathematics'),
    ('Physics', 'Physics'),
    ('Chemistry', 'Chemistry'),
    ('Biology', 'Biology'),
    ('English', 'English'),
    ('Bangla', 'Bangla'),
    ('General Knowledge', 'General Knowledge'),
    ('ICT', 'ICT'),
    ('History', 'History'),
    ('Other', 'Other'),
]


LEVEL_CHOICES = [
    ('Primary', 'Primary'),
    ('Secondary', 'Secondary'),
    ('HSC', 'HSC'),
    ('Admission', 'Admission'),
    ('Job', 'Job'),
]

DIFFICULTY_CHOICES = [
    ('Easy', 'Easy'),
    ('Medium', 'Medium'),
    ('Hard', 'Hard'),
]

TYPE_CHOICES = [
    ('MCQ', 'MCQ'),
    ('Written', 'Written'),
    ('Short Answer', 'Short Answer'),
    ('True/False', 'True/False'),
]

LANGUAGE_CHOICES = [
    ('English', 'English'),
    ('Bangla', 'Bangla'),
]

class QuestionForm(forms.Form):
    subject = forms.ChoiceField(choices=SUBJECT_CHOICES, initial='ICT', widget=forms.Select(attrs={'class': 'form-select'}))
    custom_subject = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Or enter custom subject'}))
    level = forms.ChoiceField(choices=LEVEL_CHOICES, initial='HSC', widget=forms.Select(attrs={'class': 'form-select'}))
    difficulty = forms.ChoiceField(choices=DIFFICULTY_CHOICES, initial='Medium', widget=forms.Select(attrs={'class': 'form-select'}))
    question_type = forms.ChoiceField(choices=TYPE_CHOICES, initial='MCQ', widget=forms.Select(attrs={'class': 'form-select'}))
    quantity = forms.IntegerField(min_value=1, max_value=20, initial=5, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    language = forms.ChoiceField(choices=LANGUAGE_CHOICES, initial='Bangla', widget=forms.Select(attrs={'class': 'form-select'}))

    def clean(self):
        cleaned_data = super().clean()
        custom_subject = cleaned_data.get("custom_subject")
        if custom_subject:
            cleaned_data["subject"] = custom_subject
        return cleaned_data

class TakeTestForm(forms.Form):
    subject = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    level = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    question_type = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        subject_choices = kwargs.pop('subject_choices', [])
        type_choices = kwargs.pop('type_choices', [])
        level_choices = kwargs.pop('level_choices', [])
        super().__init__(*args, **kwargs)
        
        if subject_choices:
            self.fields['subject'].choices = [('', 'Select Subject')] + subject_choices
        else:
            self.fields['subject'].choices = [('', 'No Subjects Found')]

        if level_choices:
            self.fields['level'].choices = [('Any', 'Any Level')] + level_choices
        else:
            self.fields['level'].choices = [('Any', 'Any Level')]
            
        if type_choices:
            self.fields['question_type'].choices = [('Any', 'Any Type')] + type_choices
        else:
            self.fields['question_type'].choices = [('Any', 'Any Type')]


    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


