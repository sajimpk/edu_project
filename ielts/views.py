from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseNotFound
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.db.models import Q
from . import parser
from collections import defaultdict
from .models import Test, Passage, QuestionSection, Question, Choice, Answer, UserAnswer, Result
from payments.models import SubscriptionPlan
from django.contrib import messages
from django.views.decorators.cache import cache_page
from django.views.decorators.cache import never_cache


# ==========================================
# 🏠 IELTS READING HOME VIEW
# ==========================================
# এই ফাংশনটি IELTS এর মেইন পেজ বা টেস্ট লিস্ট দেখায়। 
# এখানে প্রতিটি টেস্টের মোট প্রশ্ন এবং ইউজার কয়টি উত্তর দিয়েছে তা হিসাব করা হয় (Resume / Restart লজিক)।
@never_cache
def reading_home(request):
	# ensure session exists (নন-লগড ইন ইউজারদের আনসার ট্র্যাক করার জন্য সেশন মাস্ট)
	if not request.session.session_key:
		request.session.save()
	session_key = request.session.session_key

	def get_info(query_set):
		from django.db.models import Count, Q
		test_ids = list(query_set.values_list('id', flat=True))
		if not test_ids: return []

		# 1. Pre-fetch Total Question Counts
		standard_types = ['mcq', 'tfng', 'ynng', 'matching_headings', 'matching_features', 'matching_info', 'matching_sentence_endings', 'short_answer']
		
		# Questions in standard types
		q_std = Question.objects.filter(section__passage__test_id__in=test_ids, section__question_type__in=standard_types)\
			.values('section__passage__test_id')\
			.annotate(total=Count('id'))
		# Questions in choose_two
		q_two = Question.objects.filter(section__passage__test_id__in=test_ids, section__question_type='choose_two')\
			.values('section__passage__test_id')\
			.annotate(total=Count('id'))
		# Answers for blanks
		blank_types = [t[0] for t in QuestionSection.QUESTION_TYPES if t[0] not in standard_types and t[0] != 'choose_two']
		a_blanks = Answer.objects.filter(question__section__passage__test_id__in=test_ids, question__section__question_type__in=blank_types)\
			.values('question__section__passage__test_id')\
			.annotate(total=Count('id'))

		# Build maps
		std_total_map = {item['section__passage__test_id']: item['total'] for item in q_std}
		two_total_map = {item['section__passage__test_id']: item['total'] for item in q_two}
		blks_total_map = {item['question__section__passage__test_id']: item['total'] for item in a_blanks}

		# 2. Pre-fetch Answered Counts
		user_filter = Q(user=request.user) if request.user.is_authenticated else Q(session_key=session_key)
		
		# Answered in standard types
		ans_std = UserAnswer.objects.filter(user_filter, test_id__in=test_ids, question__section__question_type__in=standard_types)\
			.values('test_id')\
			.annotate(answered=Count('id'))
		
		# Answered in choose_two
		ans_two_uas = UserAnswer.objects.filter(user_filter, test_id__in=test_ids, question__section__question_type='choose_two')\
			.prefetch_related('selected_choices')
		two_answered_map = defaultdict(int)
		for ua in ans_two_uas:
			two_answered_map[ua.test_id] += min(2, ua.selected_choices.count())
		
		# Answered in blanks
		ans_blks = UserAnswer.objects.filter(user_filter, test_id__in=test_ids, key__in=Answer.objects.filter(question__section__passage__test_id__in=test_ids, question__section__question_type__in=blank_types).values_list('key', flat=True))\
			.exclude(answer_text='')\
			.values('test_id')\
			.annotate(answered=Count('id'))

		std_ans_map = {item['test_id']: item['answered'] for item in ans_std}
		blks_ans_map = {item['test_id']: item['answered'] for item in ans_blks}

		# 3. Assemble results - Use prefetched data properly
		info_list = []
		test_data = query_set.prefetch_related('passages', 'passages__sections')
		
		for test in test_data:
			total_q = std_total_map.get(test.id, 0) + (two_total_map.get(test.id, 0) * 2) + blks_total_map.get(test.id, 0)
			answered = std_ans_map.get(test.id, 0) + two_answered_map.get(test.id, 0) + blks_ans_map.get(test.id, 0)
			
			pct = int((answered / total_q) * 100) if total_q else 0
			label = 'Restart' if pct == 100 else ('Resume' if pct > 0 else 'Take Test')
			url = reverse('ielts:exam', args=[test.slug])
			
			# Sort prefetched passages in Python instead of DB to save queries
			test_passages = sorted(test.passages.all(), key=lambda x: x.order)
			
			# Distinct question types for labels from prefetched sections
			all_types = set()
			for p in test_passages:
				for s in p.sections.all():
					all_types.add(s.question_type)
			
			type_map = dict(QuestionSection.QUESTION_TYPES)
			available_types = [{'id': t, 'label': type_map.get(t, t)} for t in all_types]

			info_list.append({
				'test': test, 
				'total_q': total_q, 
				'answered': answered, 
				'pct': pct, 
				'label': label, 
				'url': url,
				'passages': test_passages,
				'types': available_types
			})
		return info_list

	# Optimized: One DB hit for all tests related to reading
	all_reading_tests = Test.objects.filter(test_type='reading').order_by('-id')
	all_info = get_info(all_reading_tests)

	# Split into categories in memory (extremely fast)
	full_mocks = [item for item in all_info if item['test'].duration_minutes >= 60]
	quick_tests = [item for item in all_info if item['test'].duration_minutes < 60]

	return render(request, 'ielts/reading_home.html', {
		'full_mocks': full_mocks,
		'quick_tests': quick_tests
	})


# ==========================================
# 📊 IELTS DASHBOARD VIEW
# ==========================================
# স্টুডেন্টদের পারফরম্যান্স అనালিসিস দেখায়। 
# কোন প্যাটার্নে (True/False, MCQ) কত স্কোর পেয়েছে তা হিসাব করে।
@never_cache
def ielts_dashboard(request):
	if not request.user.is_authenticated:
		return redirect('login')
		
	test_type = request.GET.get('type')
	results = Result.objects.filter(user=request.user).order_by('-submitted_at')

	if test_type in ['reading', 'listening']:
		results = results.filter(test__test_type=test_type)
	
	# Optimize fetching for Analysis (Bulk queries instead of loop queries)
	top_results = list(results[:10])
	test_ids = [res.test_id for res in top_results]
	
	# Fetch all relevant UserAnswers in one query
	all_uas = UserAnswer.objects.filter(user=request.user, test_id__in=test_ids).prefetch_related('selected_choices')
	# Map by test_id and question/key for fast lookup
	ua_test_map = defaultdict(lambda: {'q': {}, 'key': {}})
	for ua in all_uas:
		if ua.question_id:
			ua_test_map[ua.test_id]['q'][ua.question_id] = ua
		if ua.key:
			ua_test_map[ua.test_id]['key'][ua.key] = ua

	# Fetch all sections and questions in bulk
	all_sections = QuestionSection.objects.filter(passage__test_id__in=test_ids).prefetch_related('questions__choices', 'questions__answers')
	sec_test_map = defaultdict(list)
	for sec in all_sections:
		sec_test_map[sec.passage.test_id].append(sec)

	# Analyze performance by question type
	performance = {} # {type_label: {correct: 0, total: 0}}
	type_map = dict(QuestionSection.QUESTION_TYPES)
	
	for res in top_results:
		tid = res.test_id
		ua_map = ua_test_map[tid]['q']
		ua_key_map = ua_test_map[tid]['key']
		
		sections = sec_test_map[tid]
		for sec in sections:
			q_type = sec.question_type
			type_label = type_map.get(q_type, q_type)
			if type_label not in performance:
				performance[type_label] = {'correct': 0, 'total': 0, 'id': q_type}
				
			for q in sec.questions.all():
				if q_type in ['mcq', 'tfng', 'ynng']:
					performance[type_label]['total'] += 1
					ua = ua_map.get(q.id)
					if ua and any(c.is_correct for c in ua.selected_choices.all()):
						performance[type_label]['correct'] += 1
				elif q_type == 'choose_two':
					performance[type_label]['total'] += 2
					ua = ua_map.get(q.id)
					if ua:
						performance[type_label]['correct'] += sum(1 for c in ua.selected_choices.all() if c.is_correct)
				else:
					# Blanks or standard text
					_, keys = parser.parse_blanks_to_inputs(q.text)
					if keys:
						for k in keys:
							performance[type_label]['total'] += 1
							ua = ua_key_map.get(k)
							if ua and ua.answer_text:
								# Use prefetched answers
								q_answers = q.answers.all()
								ans_obj = next((a for a in q_answers if a.key == k), None)
								if ans_obj and any(ua.answer_text.strip().lower() == a.strip().lower() for a in ans_obj.accepted_list()):
									performance[type_label]['correct'] += 1
					else:
						# Fallback
						performance[type_label]['total'] += 1
						ua = ua_map.get(q.id)
						if ua and ua.answer_text:
							accepted = [a.strip().lower() for ans in q.answers.all() for a in ans.accepted_list()]
							accepted.extend([c.text.strip().lower() for c in q.choices.all() if c.is_correct])
							if ua.answer_text.strip().lower() in accepted:
								performance[type_label]['correct'] += 1

	# Calculate Overall Stats
	avg_score = 0
	if results.exists():
		avg_score = sum(r.score for r in results) / results.count()

	# Progress Analysis: Compare last 5 vs previous 5
	last_5 = list(results[:5])
	prev_5 = list(results[5:10])
	
	last_5_avg = sum(r.score for r in last_5) / len(last_5) if last_5 else 0
	prev_5_avg = sum(r.score for r in prev_5) / len(prev_5) if prev_5 else 0
	
	improvement = last_5_avg - prev_5_avg
	trend = 'up' if improvement > 0.5 else ('down' if improvement < -0.5 else 'stable')

	# Calculate accuracy and choose areas to improve
	perf_list = []
	for label, data in performance.items():
		if data['total'] > 0:
			data['label'] = label
			data['accuracy'] = int((data['correct'] / data['total']) * 100)
			data['errors'] = data['total'] - data['correct']
			perf_list.append(data)
	
	perf_list.sort(key=lambda x: x['accuracy'], reverse=True)
	# Focus Areas: Worst accuracy
	to_improve = sorted(perf_list, key=lambda x: x['accuracy'])[:3]

	# Study Plan Logic (Daily Hours and Test Frequency)
	study_plan = {
		'hours': 2,
		'tests_per_week': 3,
		'message': 'Keep a steady pace to maintain your score.'
	}
	
	if results.exists():
		recent_avg = last_5_avg
		if recent_avg < 20: # Poor performance
			study_plan = {'hours': 4, 'tests_per_week': 7, 'message': 'Intensive practice needed. Focus on one passage daily.'}
		elif recent_avg < 30: # Average
			study_plan = {'hours': 3, 'tests_per_week': 5, 'message': 'Good progress. Increase test frequency to build stamina.'}
		elif recent_avg >= 35: # Excellent
			study_plan = {'hours': 1, 'tests_per_week': 2, 'message': 'Excellent! Just maintain your skills with occasional tests.'}
	else:
		# For new users
		study_plan = {'hours': 2, 'tests_per_week': 3, 'message': 'Start your journey. Sit for at least 3 tests this week.'}

	# Pagination for history
	from django.core.paginator import Paginator
	paginator = Paginator(results, 10)
	page_number = request.GET.get('page')
	page_obj = paginator.get_page(page_number)

	context = {
		'results': page_obj,
		'current_type': test_type,
		'performance': perf_list,
		'to_improve': to_improve,
		'avg_score': avg_score,
		'total_tests': results.count(),
		'trend': trend,
		'improvement': abs(round(improvement, 1)),
		'last_5_avg': round(last_5_avg, 1),
		'study_plan': study_plan,
	}

	# Return partial for AJAX requests
	if request.headers.get('x-requested-with') == 'XMLHttpRequest':
		return render(request, 'ielts/partial_history.html', context)

	return render(request, 'ielts/dashboard.html', context)

@never_cache
def exam_page(request, test_slug):
	# Backward compatibility for old ID-based links
	if test_slug.isdigit():
		test = get_object_or_404(Test, id=int(test_slug))
		return redirect('ielts:exam', test_slug=test.slug)
		
	test = get_object_or_404(Test, slug=test_slug)
	# ensure session
	if not request.session.session_key:
		request.session.save()
	session_key = request.session.session_key

	# --------------------------
	# --- SUBSCRIPTION CHECK ---
	if request.user.is_authenticated:
		# Check if resuming (already has answers)
		has_answers = UserAnswer.objects.filter(user=request.user, test=test).exists() or \
					 UserAnswer.objects.filter(session_key=session_key, test=test).exists()
		
		# If starting new and not on a plan with allowance
		if not has_answers:
			from questions.services import LimitService
			allowed, msg = LimitService.check_limits(request.user, request, is_mock=True)
			if not allowed:
				messages.warning(request, msg)
				return redirect('upgrade')
	# --------------------------

	# Optional filtering for section-based practice
	passage_id = request.GET.get('passage')
	q_type = request.GET.get('type')

	passages = test.passages.all().order_by('order')
	sections = QuestionSection.objects.filter(passage__test=test).select_related('passage').prefetch_related('questions__choices', 'questions__answers')

	if passage_id:
		passages = passages.filter(id=passage_id)
		sections = sections.filter(passage_id=passage_id)
	elif q_type:
		sections = sections.filter(question_type=q_type)
		passages = passages.filter(id__in=sections.values_list('passage_id', flat=True)).distinct()

	# Base question queryset for scoring should match the sections displayed
	q_base = Question.objects.filter(section__in=sections)

	if request.method == 'POST':
		# --- GUEST CHECK FOR SUBMISSION ---
		if not request.user.is_authenticated:
			messages.warning(request, "পরীক্ষা সাবমিট করার জন্য দয়া করে লগইন করুন।")
			return redirect('account_login')
		# ----------------------------------
			
		# Clear previous answers for this specific test/session
		UserAnswer.objects.filter(session_key=session_key, test=test, question__in=q_base).delete()

		# Save answers (MCQ, choose_two, and blanks)
		# 1. Collect all data from POST first
		text_answers = [] # list of (key, text)
		choice_answers_dict = defaultdict(list) # {qid: [choice_ids]}
		all_qid_involved = set()
		all_cid_involved = set()

		for k, v_list in request.POST.lists():
			if k.startswith('choice_'):
				try:
					qid = int(k.split('_', 1)[1])
					all_qid_involved.add(qid)
					for cid in v_list:
						if cid.isdigit(): all_cid_involved.add(int(cid))
					choice_answers_dict[qid].extend(v_list)
				except: continue
			elif k.startswith('ans_'):
				name_parts = k.split('_', 1)
				if len(name_parts) < 2: continue
				key = name_parts[1]
				text = v_list[0].strip() if v_list else ''
				if text: text_answers.append((key, text))

		# 2. Pre-fetch Questions and Choices in bulk
		ans_objs = {a.key: a for a in Answer.objects.filter(key__in=[t[0] for t in text_answers]).select_related('question')}
		
		# Identify all question IDs needed
		for key, _ in text_answers:
			ans = ans_objs.get(key)
			if ans and ans.question_id:
				all_qid_involved.add(ans.question_id)
			elif key.isdigit():
				all_qid_involved.add(int(key))
		
		# Now fetch all questions and choices
		questions_map = {q.id: q for q in Question.objects.filter(id__in=all_qid_involved)}
		choices_map = {c.id: c for c in Choice.objects.filter(id__in=all_cid_involved)}

		# 3. Process Text Answers
		for key, text in text_answers:
			ans = ans_objs.get(key)
			q = None
			if ans:
				q = ans.question
			elif key.isdigit():
				q = questions_map.get(int(key))
			
			if q:
				UserAnswer.objects.update_or_create(session_key=session_key, test=test, question=q, key=key, defaults={'answer_text': text})

		# 4. Process Choice Answers
		for qid, choice_ids in choice_answers_dict.items():
			q = questions_map.get(qid)
			if not q: continue
			
			ua, _ = UserAnswer.objects.update_or_create(session_key=session_key, test=test, question=q)
			
			valid_choices = []
			for cid in choice_ids:
				if cid.isdigit() and int(cid) in choices_map:
					valid_choices.append(choices_map[int(cid)])
			
			if valid_choices:
				ua.selected_choices.set(valid_choices)

		# compute basic result
		total = 0
		correct = 0

		# MCQ scoring
		# MCQ and True/False scoring
		for q in q_base.filter(section__question_type__in=['mcq', 'tfng', 'ynng']):
			total += 1
			ua = UserAnswer.objects.filter(session_key=session_key, test=test, question=q).first()
			if ua and ua.selected_choices.filter(is_correct=True).exists():
				correct += 1

		# choose_two scoring
		for q in q_base.filter(section__question_type='choose_two'):
			total += 2
			ua = UserAnswer.objects.filter(session_key=session_key, test=test, question=q).first()
			if ua:
				correct_choices = set(q.choices.filter(is_correct=True).values_list('id', flat=True))
				selected_choices = set(ua.selected_choices.values_list('id', flat=True))
				correct_selected = correct_choices & selected_choices
				correct += len(correct_selected)

		# 1. Standard one-answer per question types (matching, short answer, etc.)
		standard_text_types = ['matching_headings', 'matching_features', 'matching_info', 'matching_sentence_endings', 'short_answer']
		for q in q_base.filter(section__question_type__in=standard_text_types):
			total += 1
			ua = UserAnswer.objects.filter(session_key=session_key, test=test, question=q).first()
			if ua and ua.answer_text:
				norm = ua.answer_text.strip().lower()
				# Check against correct choices or Answer objects
				accepted = []
				# Try Answer objects first
				for ans in q.answers.all():
					accepted.extend([a.strip().lower() for a in ans.accepted_list() if a])
				# Also check choices marked as correct
				for ch in q.choices.filter(is_correct=True):
					if ch.label: accepted.append(ch.label.strip().lower())
					if ch.text: accepted.append(ch.text.strip().lower())
				
				if any(norm == a for a in accepted):
					correct += 1

		# 2. Blank-based types (summaries, sentence completion, etc.)
		# Only process types that are NOT in standard_text_types to avoid double counting
		blank_types = [t[0] for t in QuestionSection.QUESTION_TYPES if t[0] not in standard_text_types and t[0] not in ['mcq', 'tfng', 'ynng', 'choose_two']]
		for ans in Answer.objects.filter(question__in=q_base, question__section__question_type__in=blank_types):
			total += 1
			ua = UserAnswer.objects.filter(session_key=session_key, test=test, key=ans.key).first()
			if ua and ua.answer_text:
				norm = ua.answer_text.strip().lower()
				for a in ans.accepted_list():
					if norm == a.strip().lower():
						correct += 1
						break

		res = Result.objects.create(user=request.user if request.user.is_authenticated else None, test=test, score=correct, total=total, correct_count=correct)
		
		# --- DEDUCT FROM PLAN/BALANCE ---
		if request.user.is_authenticated:
			from questions.services import LimitService
			LimitService.increment_usage(request.user, request, is_mock=True)
		# ---------------------------------

		return redirect('ielts:result', test_slug=test.slug, result_id=res.id)

	passages_render = []
	
	# Pre-group sections by passage_id to avoid O(N*M) loop
	sec_by_passage = defaultdict(list)
	for sec in sections:
		sec_by_passage[sec.passage_id].append(sec)

	for p in passages:
		q_count = 0
		for sec in sec_by_passage.get(p.id, []):
			if sec.question_type in ['sent_comp', 'summary_completion', 'note_completion', 'table_completion', 'flow_chart_completion', 'diagram_label_completion', 'short_answer', 'matching_headings', 'matching_features', 'matching_info', 'matching_sentence_endings', 'pick_from_list']:
				for q in sec.questions.all():
					keys = parser.extract_blank_keys(q.text)
					# Fallback if no blanks are found but it's a type that requires answer
					q_count += len(keys) if keys else sec.questions.count()
			elif sec.question_type == 'choose_two':
				q_count += sec.questions.count() * 2
			else:
				q_count += sec.questions.count()
		passages_render.append({'passage': p, 'content': parser.show_locators_html(p.content), 'total_questions': q_count})

	# Prepare sections and for sentence completion parse blanks to inputs
	sections_render = []
	# Use sorted() to keep prefetch alive
	sorted_sections = sorted(sections, key=lambda x: x.order)
	
	for sec in sorted_sections:
		qlist = []
		for q in sec.questions.all():
			item = {'question': q, 'html': '', 'blank_keys': [], 'first_ans_key': ''}
			if sec.question_type in ['sent_comp', 'summary_completion', 'note_completion', 'table_completion', 'flow_chart_completion', 'diagram_label_completion', 'short_answer', 'matching_headings', 'matching_features', 'matching_info', 'matching_sentence_endings', 'pick_from_list', 'completion', 'matching']:
				# If there are choices, pass them as a list of labels/text for dropdowns
				q_choices = [c.label or c.text for c in q.choices.all()]
				html, keys = parser.parse_blanks_to_inputs(q.text, choices=q_choices)
				item['html'] = html
				item['blank_keys'] = keys
				# Get the first answer key if manually rendering text box
				ans = q.answers.first()
				if ans:
					item['first_ans_key'] = ans.key
			qlist.append(item)
		
		# Add question_count for dynamic selection limits
		q_count = sec.end_number - sec.start_number + 1
		sections_render.append({'section': sec, 'questions': qlist, 'question_count': q_count})

	# Split sections into 3 parts roughly evenly
	from math import ceil
	parts = []
	if sections_render:
		n = len(sections_render)
		per = ceil(n / 3)
		for i in range(3):
			chunk = sections_render[i * per:(i + 1) * per]
			qcount = sum(len(s['questions']) for s in chunk)
			parts.append({'id': i + 1, 'title': f'Part {i+1}', 'sections': chunk, 'qcount': qcount})
	else:
		parts = [{'id': 1, 'title': 'Part 1', 'sections': [], 'qcount': 0}, {'id': 2, 'title': 'Part 2', 'sections': [], 'qcount': 0}, {'id': 3, 'title': 'Part 3', 'sections': [], 'qcount': 0}]

	is_locked = not request.user.is_authenticated

	return render(request, 'ielts/exam_page.html', {
		'test': test, 
		'passages': passages_render, 
		'parts': parts, 
		'sections': sections_render,
		'is_locked': is_locked
	})

@never_cache
def result_page(request, test_slug, result_id):
	# Backward compatibility for old ID-based links
	if test_slug.isdigit():
		test = get_object_or_404(Test, id=int(test_slug))
		return redirect('ielts:result', test_slug=test.slug, result_id=result_id)
		
	test = get_object_or_404(Test, slug=test_slug)
	result = get_object_or_404(Result, pk=result_id, test=test)
	session_key = request.session.session_key or ''
	passages = test.passages.all()
	# show locators
	passages_render = []
	for p in passages:
		passages_render.append({'passage': p, 'content': parser.show_locators_html(p.content)})

	sections = QuestionSection.objects.filter(passage__test=test).select_related('passage').prefetch_related('questions__choices', 'questions__answers')
	sections_render = []
	uas = UserAnswer.objects.filter(session_key=session_key, test=test)
	ua_map = {}
	for ua in uas:
		if ua.question:
			ua_map[f'q_{ua.question.id}'] = ua
		if ua.key:
			ua_map[f'key_{ua.key}'] = ua

	correct_map = {}
	for q in Question.objects.filter(section__passage__test=test):
		correct_choices = list(q.choices.filter(is_correct=True))
		if correct_choices:
			correct_map[f'q_{q.id}'] = correct_choices
	for ans in Answer.objects.filter(question__section__passage__test=test):
		correct_map[f'key_{ans.key}'] = ans.accepted_list()

	right_count = 0
	wrong_count = 0
	for sec in sections.order_by('order'):
		qlist = []
		section_answers = []
		for q in sec.questions.all():
			item = {'question': q}
			ua = ua_map.get(f'q_{q.id}')
			if sec.question_type in ['sent_comp', 'summary_completion', 'note_completion', 'table_completion', 'flow_chart_completion', 'diagram_label_completion', 'short_answer', 'matching_headings', 'matching_features', 'matching_info', 'matching_sentence_endings', 'pick_from_list', 'completion', 'matching']:
				# Get user answers for these keys to fill into the HTML
				_, keys = parser.parse_blanks_to_inputs(q.text)
				blank_values = {}
				blank_results = {}
				for k in keys:
					ua_blank = ua_map.get(f'key_{k}')
					user_text = ua_blank.answer_text if ua_blank and ua_blank.answer_text else ''
					blank_values[k] = user_text
					
					accepted = correct_map.get(f'key_{k}', [])
					is_this_blank_correct = user_text.strip().lower() in [a.strip().lower() for a in accepted]
					blank_results[k] = is_this_blank_correct
				
				# Get question choices for dropdowns
				q_choices = [c.label or c.text for c in q.choices.all()]
				
				html, _ = parser.parse_blanks_to_inputs(q.text, values=blank_values, results=blank_results, choices=q_choices)
				item['html'] = html
				item['blank_keys'] = keys
				
				if keys:
					all_correct = True
					for key in keys:
						user_text = blank_values.get(key, '')
						accepted = correct_map.get(f'key_{key}', [])
						is_this_blank_correct = blank_results.get(key)
						
						if is_this_blank_correct:
							right_count += 1
						else:
							wrong_count += 1
							all_correct = False
						
						display_num = key.replace('q', '', 1) if key.startswith('q') else key
						section_answers.append({
							'number': display_num, 
							'answer': ' | '.join([str(a) for a in accepted]),
							'is_correct': is_this_blank_correct
						})
					item['is_correct'] = all_correct
					first_key = keys[0]
					item['user_answer'] = blank_values.get(first_key, '')
					item['correct_answer'] = ' | '.join([str(a) for a in correct_map.get(f'key_{first_key}', [])])
				else:
					# Standard question or Fallback
					user_text = ua.answer_text if ua and ua.answer_text else ''
					item['user_answer'] = user_text
					
					# Get accepted list for comparison (Choices + Answers)
					correct_choices = q.choices.filter(is_correct=True)
					accepted = [ans.accepted_list() for ans in q.answers.all()]
					flat_accepted = [item.strip().lower() for sublist in accepted for item in sublist]
					for ch in correct_choices:
						if ch.label: flat_accepted.append(ch.label.strip().lower())
						if ch.text: flat_accepted.append(ch.text.strip().lower())
					
					is_correct = user_text.strip().lower() in flat_accepted if user_text else False
					item['is_correct'] = is_correct
					
					if is_correct:
						right_count += 1
					else:
						wrong_count += 1
					
					# Build display answer string
					display_answers = [str(ch.label or ch.text) for ch in correct_choices]
					for ans in q.answers.all():
						display_answers.extend(ans.accepted_list())
					item['correct_answer'] = ' | '.join(display_answers)
					
					section_answers.append({
						'number': q.number(),
						'answer': item['correct_answer'],
						'is_correct': is_correct
					})

			elif sec.question_type in ['mcq', 'tfng', 'ynng']:
				user_choices = ua.selected_choices.all() if ua else []
				correct_choices = correct_map.get(f'q_{q.id}', [])
				# Display text only for TFNG/YNNG. For MCQ, prioritize label.
				item['user_choice_ids'] = [c.id for c in user_choices]
				item['correct_choice_ids'] = [c.id for c in correct_choices]
				
				if sec.question_type in ['tfng', 'ynng']:
					item['user_answer'] = ', '.join([str(c.text) for c in user_choices])
					item['correct_answer'] = ' | '.join([str(c.text) for c in correct_choices])
				else:
					item['user_answer'] = ', '.join([str(c.label or c.text) for c in user_choices])
					item['correct_answer'] = ' | '.join([str(c.label or c.text) for c in correct_choices])
				item['is_correct'] = any(c.id in [cc.id for cc in correct_choices] for c in user_choices) if correct_choices and user_choices else False
				if item['is_correct']:
					right_count += 1
				else:
					wrong_count += 1
				section_answers.append({
					'number': q.number(), 
					'answer': item['correct_answer'],
					'is_correct': item['is_correct']
				})
			elif sec.question_type == 'choose_two':
				user_choices = list(ua.selected_choices.all()) if ua else []
				correct_choices = correct_map.get(f'q_{q.id}', [])
				item['user_choice_ids'] = [c.id for c in user_choices]
				item['correct_choice_ids'] = [c.id for c in correct_choices]
				
				# Identify correct selections vs wrong selections
				correct_ids = set(c.id for c in correct_choices)
				right_selections = [c for c in user_choices if c.id in correct_ids]
				
				# Number of items in this block
				num_in_block = sec.end_number - sec.start_number + 1
				item['is_correct'] = len(right_selections) == num_in_block
				
				# Display answer string (all possible correct choices)
				correct_ans_display = ' | '.join([str(c.label or c.text) for c in correct_choices])
				item['correct_answer'] = correct_ans_display
				item['correct_answer_list'] = [str(c.label or c.text) for c in correct_choices]

				for i in range(num_in_block):
					q_num = sec.start_number + i
					
					# Find the correct choice designated for this slot
					# (Matches the order in correct_answer_list used in the template)
					cor_choice = correct_choices[i] if i < len(correct_choices) else None
					
					if cor_choice:
						# IMPORTANT: Number is correct ONLY if the user selected this specific choice
						is_this_pos_correct = any(uc.id == cor_choice.id for uc in user_choices)
						ans_text = str(cor_choice.label or cor_choice.text)
					else:
						# Should not normally happen if data is clean
						is_this_pos_correct = False
						ans_text = "-"
					
					if is_this_pos_correct:
						right_count += 1
					else:
						wrong_count += 1
						
					section_answers.append({
						'number': q_num,
						'answer': ans_text,
						'is_correct': is_this_pos_correct
					})
			else:
				item['user_answer'] = ua.answer_text if ua and ua.answer_text else ''
				correct_ans = correct_map.get(f'q_{q.id}', [])
				if isinstance(correct_ans, list):
					item['correct_answer'] = ' | '.join([str(a.text if hasattr(a, 'text') else a) for a in correct_ans])
				else:
					item['correct_answer'] = str(correct_ans)
				item['is_correct'] = ua and ua.answer_text and any(ua.answer_text.strip().lower() == a.strip().lower() for a in correct_ans)
				if item['is_correct']:
					right_count += 1
				else:
					wrong_count += 1
				section_answers.append({
					'number': q.number(), 
					'answer': item['correct_answer'],
					'is_correct': item['is_correct']
				})
			qlist.append(item)
		sections_render.append({'section': sec, 'questions': qlist, 'answers_summary': section_answers})

	# Calculate final total from summary logic to be 100% consistent
	final_total = right_count + wrong_count
	
	# Update the existing Result record with the correct counts calculated here
	# This ensures the summary card at the top matches the detailed list below
	result.score = right_count
	result.total = final_total
	result.correct_count = right_count
	result.save()

	# Use model property for band score
	band_score = result.band_score

	return render(request, 'ielts/result_page.html', {
		'test': test, 
		'result': result, 
		'passages': passages_render, 
		'sections': sections_render, 
		'right_count': right_count, 
		'wrong_count': wrong_count,
		'band_score': band_score
	})
# NOTE: Legacy views (reading_test, reading_result, save_answer) have been removed 
# because they referenced non-existent models and were replaced by the new 
# exam_page and result_page system.

@never_cache
def share_result(request, result_id):
	# Using select_related to fetch test and user in one query
	result = get_object_or_404(Result.objects.select_related('test', 'user'), pk=result_id)
	share_url = request.build_absolute_uri(reverse('ielts:share_result', args=[result.id]))

	# Optimize ranking queries (Adding common filters)
	# Rank calculation can be slow on large tables; using values() or count() efficiently
	higher_scores = Result.objects.filter(test=result.test, score__gt=result.score).count()
	rank_num = higher_scores + 1
	total_participants = Result.objects.filter(test=result.test).count()
	
	correct_count = int(result.score)
	wrong_count = int(result.total) - correct_count

	return render(request, 'ielts/share_result.html', {
		'result': result,
		'share_url': share_url,
		'rank_num': rank_num,
		'total_participants': total_participants,
		'correct_count': correct_count,
		'wrong_count': wrong_count,
	})


