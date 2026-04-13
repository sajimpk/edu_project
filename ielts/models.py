from django.db import models
from django.conf import settings
from ckeditor_uploader.fields import RichTextUploadingField

# ==========================================
# 📖 IELTS TEST MODEL (মূল পরীক্ষা)
# ==========================================
# এটি সম্পূর্ণ একটি Cambridge IELTS পরীক্ষার সেট কে রিপ্রেজেন্ট করে।
class Test(models.Model):
	TEST_TYPE_CHOICES = [
		('reading', 'Reading'),
		('listening', 'Listening'),
		('writing', 'Writing'),
		('speaking', 'Speaking'),
	]
	title = models.CharField(max_length=255)
	slug = models.SlugField(max_length=255, unique=True)
	test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, default='reading')
	description = models.TextField(blank=True)
	duration_minutes = models.PositiveIntegerField(default=60)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.title

# ==========================================
# 📄 PASSAGE MODEL (রিডিং প্যাসেজ বা অনুচ্ছেদ)
# ==========================================
# একটি Test-এ সাধারণত ৩টি Passage থাকে। 
# `content` ফিল্ডে [17] বা [=q1] টাইপের লোকেটর ট্যাগ থাকতে পারে।
class Passage(models.Model):
	test = models.ForeignKey(Test, related_name='passages', on_delete=models.CASCADE)
	title = models.CharField(max_length=255, blank=True)
	# content includes locator tags like [17]
	content = RichTextUploadingField()
	order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['order']

	def __str__(self):
		return f"{self.test.title} - Passage {self.order}"

	def save(self, *args, **kwargs):
		if not self.pk and self.order == 0:
			last_order = Passage.objects.filter(test=self.test).aggregate(models.Max('order'))['order__max']
			if last_order is not None:
				self.order = last_order + 1
		super().save(*args, **kwargs)


# ==========================================
# 🧩 QUESTION SECTION MODEL (প্রশ্নের গ্রুপ)
# ==========================================
# একটি প্যাসেজের অধীনে অনেকগুলো সেকশন থাকতে পারে 
# যেমন: ১-৫ নং প্রশ্ন True/False, ৬-৯ নং Matching Headings।
class QuestionSection(models.Model):
	QUESTION_TYPES = [
		('mcq', 'Multiple Choice'),
		('tfng', 'True/False/Not Given (or Yes/No/Not Given)'),
		('matching', 'Matching (Headings, Features, Info)'),
		('completion', 'Completion / Fill in the Blanks'),
		('short_answer', 'Short Answer Questions'),
	]
	passage = models.ForeignKey(Passage, related_name='sections', on_delete=models.CASCADE)
	title = models.CharField(max_length=255, blank=True)
	instruction_text = RichTextUploadingField(blank=True)
	question_type = models.CharField(max_length=32, choices=QUESTION_TYPES)
	matching_options = models.CharField(max_length=500, blank=True, help_text="For Matching: comma-separated list of options (e.g. A,B,C,D or i,ii,iii,iv)")
	start_number = models.PositiveIntegerField(default=1)
	end_number = models.PositiveIntegerField(default=1)
	order = models.PositiveIntegerField(default=0)
	tags = models.ManyToManyField('weak_topics.TopicTag', blank=True, related_name='ielts_sections')

	class Meta:
		ordering = ['order']

	def __str__(self):
		return f"Section {self.title} ({self.passage})"

	def get_matching_options_list(self):
		if self.matching_options:
			return [opt.strip() for opt in self.matching_options.split(',') if opt.strip()]
		return []

	def save(self, *args, **kwargs):
		if not self.pk and self.order == 0:
			last_order = QuestionSection.objects.filter(passage=self.passage).aggregate(models.Max('order'))['order__max']
			if last_order is not None:
				self.order = last_order + 1
		super().save(*args, **kwargs)

# ==========================================
# 🔢 QUESTION MODEL (নির্দিষ্ট প্রশ্ন)
# ==========================================
# এটি সুনির্দিষ্ট একটি প্রশ্ন (যেমন: Q1, Q2) রিপ্রেজেন্ট করে 
# এবং Sentence Completion-এর ক্ষেত্রে ব্ল্যাঙ্ক টোকেন ({[ ][=q1]}) ধারণ করে।
class Question(models.Model):
	section = models.ForeignKey(QuestionSection, related_name='questions', on_delete=models.CASCADE)
	# question text may include blank tokens like {[ ][=q1]} for sentence completion
	text = RichTextUploadingField()
	order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['order']

	def number(self):
		# auto-generate number based on section start and order
		# Ensure order starts from 0 for the first question in section to get correct sequence
		return self.section.start_number + self.order

	def __str__(self):
		return f"Q{self.number()} ({self.section.question_type})"

	def save(self, *args, **kwargs):
		if not self.pk and self.order == 0:
			last_order = Question.objects.filter(section=self.section).aggregate(models.Max('order'))['order__max']
			if last_order is not None:
				self.order = last_order + 1
		super().save(*args, **kwargs)


class Choice(models.Model):
	question = models.ForeignKey(Question, related_name='choices', on_delete=models.CASCADE)
	text = models.CharField(max_length=1024)
	is_correct = models.BooleanField(default=False)
	label = models.CharField(max_length=4, blank=True)
	order = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['order']

	def __str__(self):
		return f"{self.label} - {self.text}"

	def save(self, *args, **kwargs):
		if not self.pk and self.order == 0:
			last_order = Choice.objects.filter(question=self.question).aggregate(models.Max('order'))['order__max']
			if last_order is not None:
				self.order = last_order + 1
		
		if not self.label:
			self.label = chr(65 + self.order) # 0->A, 1->B, 2->C...
			
		super().save(*args, **kwargs)

class Answer(models.Model):
	# Used for sentence-completion blanks mapping keys (e.g., q1) to acceptable answers
	question = models.ForeignKey(Question, related_name='answers', on_delete=models.CASCADE, null=True, blank=True)
	key = models.CharField(max_length=64, help_text='e.g. q1')
	accepted = models.TextField(help_text='One accepted answer per line or comma separated')

	def accepted_list(self):
		# split by newline or comma
		parts = []
		for line in self.accepted.splitlines():
			for p in line.split(','):
				v = p.strip()
				if v:
					parts.append(v)
		return parts

	def __str__(self):
		return f"Answer {self.key} ({self.question})"


class UserAnswer(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	session_key = models.CharField(max_length=255, blank=True)
	test = models.ForeignKey(Test, on_delete=models.CASCADE)
	question = models.ForeignKey(Question, null=True, blank=True, on_delete=models.CASCADE)
	selected_choices = models.ManyToManyField(Choice, blank=True, related_name='user_answers')
	key = models.CharField(max_length=64, blank=True)
	answer_text = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"UA {self.test} {self.question or self.key}"

class Result(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
	test = models.ForeignKey(Test, on_delete=models.CASCADE)
	score = models.FloatField()
	total = models.FloatField()
	correct_count = models.PositiveIntegerField()
	submitted_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"Result {self.test.title} - {self.score}/{self.total}"

	@property
	def band_score(self):
		c = self.score
		if c >= 39: return 9.0
		elif c >= 37: return 8.5
		elif c >= 35: return 8.0
		elif c >= 33: return 7.5
		elif c >= 30: return 7.0
		elif c >= 27: return 6.5
		elif c >= 23: return 6.0
		elif c >= 19: return 5.5
		elif c >= 15: return 5.0
		elif c >= 13: return 4.5
		elif c >= 10: return 4.0
		elif c >= 8: return 3.5
		elif c >= 6: return 3.0
		elif c >= 4: return 2.5
		else: return 2.0
