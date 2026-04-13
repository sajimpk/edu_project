
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from .forms import QuestionForm, TakeTestForm
from .utils import generate_questions_ai, analyze_written_answer_ai, generate_exam_suggestion_ai, AIQuotaExceededError, AIServerError
import logging
from django.views.decorators.cache import never_cache
from django.views.decorators.cache import cache_page

logger = logging.getLogger(__name__)
from django.utils import timezone

from .services import LimitService
from .models import Exam, Question, QuestionBank, AiQuestion
from users.models import Profile

# ==========================================
# 🏠 HOME PAGE VIEW
# ==========================================
@never_cache
def index(request):
    """
    Landing Page View.
    (হোম পেজ বা ল্যান্ডিং পেজ লোড করার জন্য এই ফাংশন কাজ করে)
    """
    from ielts.models import Test
    from payments.models import SubscriptionPlan
    
    full_mocks = Test.objects.filter(duration_minutes__gte=60).order_by('-id').select_related('passages__sections')[:3]
    recent_practice = Test.objects.filter(duration_minutes__lt=60).order_by('-id').select_related('passages__sections')[:3]
    
    # Fetch Subscription Plans from DB
    plans = SubscriptionPlan.objects.all().order_by('price')
    for plan in plans:
        if plan.features:
            plan.feature_list = [f.strip() for f in plan.features.split(',')]
        else:
            plan.feature_list = []
            
    return render(request, 'index.html', {
        'full_mocks': full_mocks,
        'recent_practice': recent_practice,
        'plans': plans
    })

# ==========================================
# 🧠 AI TEST GENERATION VIEW (The Core Engine)
# ==========================================
@never_cache
def generate_test(request):
    """
    Generate Exam View (Form & Processing).
    এই ফাংশনটি 'Make Test' ফর্ম থেকে ডাটা নিয়ে AI বা Database থেকে প্রশ্ন তৈরি করে।
    """
    result = None
    error = None
    form = QuestionForm()

    if request.method == 'POST':
        try:
            form = QuestionForm(request.POST) 
            
            if form.is_valid():
                subject = form.cleaned_data['subject']
                level = form.cleaned_data['level']
                difficulty = form.cleaned_data['difficulty']
                question_type = form.cleaned_data['question_type']
                quantity = form.cleaned_data['quantity']
                language = form.cleaned_data['language']
                
                # --- [ STEP 1: GUEST RESTRICTIONS ] ---
                if not request.user.is_authenticated and quantity > 5:
                     quantity = 5
                     messages.warning(request, "Guests limited to 5 questions per request.")

                # --- [ STEP 2: SUBSCRIPTION LIMIT CHECK ] ---
                allowed, msg = LimitService.check_limits(request.user, request, quantity, question_type)
                if not allowed:
                    return render(request, 'exams/generate_test.html', {'form': form, 'result': None, 'error': msg, 'allowed': False})

                # --- [ STEP 3: DATABASE LOOKUP (Deduplication) ] ---
                seen_qb_ids = []
                if request.user.is_authenticated:
                    seen_qb_ids = Question.objects.filter(
                        exam__user=request.user,
                        question_bank__isnull=False
                    ).values_list('question_bank_id', flat=True).order_by('-id')[:200]
                
                candidate_questions = QuestionBank.objects.filter(
                    subject__iexact=subject,
                    level__iexact=level,
                    difficulty__iexact=difficulty,
                    question_type__iexact=question_type
                ).exclude(
                    id__in=seen_qb_ids
                ).order_by('?')[:quantity]
                
                if candidate_questions.count() >= quantity:
                    if request.user.is_authenticated:
                        exam = Exam.objects.create(
                            user=request.user,
                            subject=subject,
                            level=level,
                            difficulty=difficulty,
                            question_type=question_type,
                            total_questions=quantity
                        )
                        for qb in candidate_questions:
                            Question.objects.create(
                                exam=exam,
                                question_bank=qb,
                                text=qb.text,
                                options=qb.options,
                                correct_answer=qb.correct_answer,
                                explanation=qb.explanation
                            )
                        LimitService.increment_usage(request.user, request, quantity, question_type)
                        return redirect('take_exam', exam_id=exam.id)
                    else:
                        result = {
                            'subject': subject,
                            'level': level,
                            'difficulty': difficulty,
                            'questions': [{'question': qb.text, 'options': qb.options, 'correct_answer': qb.correct_answer, 'explanation': qb.explanation} for qb in candidate_questions]
                        }
                        LimitService.increment_usage(request.user, request, quantity, question_type)
                        return render(request, 'exams/practice_exam.html', {'result': result})

                # --- [ STEP 4: AI GENERATION ] ---
                exclude_topics = list(QuestionBank.objects.filter(id__in=seen_qb_ids).values_list('text', flat=True)[:20])
                start_time = timezone.now()
                try:
                    # Get model retry index if provided by frontend
                    model_idx_raw = request.POST.get('model_retry_count')
                    model_idx = int(model_idx_raw) if (model_idx_raw and model_idx_raw.isdigit()) else 0
                    
                    # Track execution time to prevent 524
                    if model_idx == 0:
                        messages.info(request, "আপনার পছন্দের প্রশ্নগুলো AI দিয়ে জেনারেট করা শুরু হয়েছে...")
                    
                    # Stop if we already tried 3 times
                    if model_idx >= 3:
                        messages.error(request, "AI সার্ভার বর্তমানে অনেক ব্যস্ত। অনুগ্রহ করে আমাদের প্রশ্ন ব্যাংক থেকে এখনই পরীক্ষা দিন।")
                        return redirect('take_test')

                    result_json = generate_questions_ai(
                        subject, level, difficulty, question_type, quantity, language, 
                        exclude_topics=exclude_topics, model_index=model_idx
                    )
                    
                    # Check if we took too long (Near 50s)
                    if (timezone.now() - start_time).total_seconds() > 50 and not result_json:
                        messages.warning(request, "AI সার্ভার থেকে রেসপন্স পেতে দেরি হচ্ছে। আমরা উন্নত কোনো মডেল দিয়ে ২য় বার চেষ্টা করছি...")
                        return render(request, 'exams/generate_test.html', {'form': form, 'retry_auto': True, 'model_idx': model_idx + 1})
                    
                    if result_json and isinstance(result_json, dict):
                         LimitService.increment_usage(request.user, request, quantity, question_type)
                         questions_list = result_json.get('questions', [])[:quantity]
                         
                         if request.user.is_authenticated:
                             exam = Exam.objects.create(
                                 user=request.user,
                                 subject=result_json.get('subject', subject),
                                 level=result_json.get('level', level),
                                 difficulty=result_json.get('difficulty', difficulty),
                                 question_type=question_type,
                                 total_questions=len(questions_list)
                             )
                             for q_data in questions_list:
                                 q_text = q_data.get('question', '').strip()
                                 if not q_text: continue
                                 ai_qb, _ = AiQuestion.objects.get_or_create(
                                     text=q_text,
                                     defaults={
                                         'subject': subject, 'level': level, 'difficulty': difficulty,
                                         'question_type': question_type, 'options': q_data.get('options'),
                                         'correct_answer': q_data.get('correct_answer'), 'explanation': q_data.get('explanation')
                                     }
                                 )
                                 Question.objects.create(exam=exam, question_bank=None, text=ai_qb.text, options=ai_qb.options, correct_answer=ai_qb.correct_answer, explanation=ai_qb.explanation)
                             return redirect('take_exam', exam_id=exam.id)
                         else:
                             return render(request, 'exams/practice_exam.html', {'result': result_json})
                    else:
                        # Fallback
                        fallback = QuestionBank.objects.filter(subject__icontains=subject).order_by('?')[:quantity]
                        if fallback.exists():
                            result = {'subject': subject, 'level': level, 'difficulty': difficulty, 'questions': [{'question': qb.text, 'options': qb.options, 'correct_answer': qb.correct_answer, 'explanation': qb.explanation} for qb in fallback]}
                            return render(request, 'exams/practice_exam.html', {'result': result})
                        error = "AI temporarily unavailable and no fallback questions found in DB."
                except AIQuotaExceededError as e:
                    error = str(e)
                except Exception as e:
                    error = f"AI Error: {str(e)}"

        except Exception as e:
            error = f"Internal App Error: {str(e)}"

    return render(request, 'exams/generate_test.html', {'form': form, 'error': error})

# ==========================================
# ️ AJAX AI TEST GENERATION (SMOOTH UI)
# ==========================================
@login_required
@never_cache
def ajax_generate_test(request):
    """
    Handle test generation via AJAX to avoid 524 timeouts and provide smooth UI updates.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    form = QuestionForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'error': 'প্রদত্ত তথ্যগুলো সঠিক নয়। দয়া করে আবার যাচাই করুন।'}, status=400)

    subject = form.cleaned_data['subject']
    level = form.cleaned_data['level']
    difficulty = form.cleaned_data['difficulty']
    question_type = form.cleaned_data['question_type']
    quantity = form.cleaned_data['quantity']
    language = form.cleaned_data['language']
    
    # Get retry index
    model_idx_raw = request.POST.get('model_retry_count')
    model_idx = int(model_idx_raw) if (model_idx_raw and model_idx_raw.isdigit()) else 0

    if model_idx >= 3:
        messages.error(request, "AI সার্ভার বর্তমানে অনেক ব্যস্ত। অনুগ্রহ করে আমাদের প্রশ্ন ব্যাংক থেকে এখনই পরীক্ষা দিন।")
        return JsonResponse({
            'error': 'AI সার্ভার ব্যস্ত', 
            'redirect_url': reverse('take_test')
        }, status=429)

    # Determine if it should count as an IELTS Mock
    is_mock = 'ielts' in subject.lower() or quantity >= 30
    
    # Limit check
    allowed, msg = LimitService.check_limits(request.user, request, quantity, question_type, is_mock=is_mock)
    if not allowed:
        return JsonResponse({'error': msg}, status=403)

    # Prep topics to exclude
    seen_qb_ids = request.session.get('seen_questions', [])
    exclude_topics = list(QuestionBank.objects.filter(id__in=seen_qb_ids).values_list('text', flat=True)[:20])
    
    start_time = timezone.now()
    try:
        result_json = generate_questions_ai(
            subject, level, difficulty, question_type, quantity, language, 
            exclude_topics=exclude_topics, model_index=model_idx
        )
        
        # Backend timeout check (Stop at 50s to avoid Cloudflare 524)
        if (timezone.now() - start_time).total_seconds() > 50 and not result_json:
            return JsonResponse({
                'error': 'TIMEOUT_RETRY', 
                'message': 'AI সার্ভার থেকে রেসপন্স পেতে দেরি হচ্ছে। আমরা উন্নত কোনো মডেল দিয়ে আবার চেষ্টা করছি...',
                'next_idx': model_idx + 1
            }, status=408)

        if result_json and isinstance(result_json, dict):
            # SUCCESS
            # Only deduct immediately if it's NOT a mock. Mocks are deducted on submit.
            if not is_mock:
                LimitService.increment_usage(request.user, request, quantity, question_type, is_mock=False)
            
            questions_list = result_json.get('questions', [])[:quantity]
            
            exam = Exam.objects.create(
                user=request.user,
                subject=result_json.get('subject', subject),
                level=result_json.get('level', level),
                difficulty=result_json.get('difficulty', difficulty),
                question_type=question_type,
                total_questions=len(questions_list),
                mode='FULL_EXAM' if is_mock else 'AI_PRACTICE'
            )
            for q_data in questions_list:
                q_text = q_data.get('question', '').strip()
                if not q_text: continue
                ai_qb, _ = AiQuestion.objects.get_or_create(
                    text=q_text,
                    defaults={
                        'subject': subject, 'level': level, 'difficulty': difficulty,
                        'question_type': question_type, 'options': q_data.get('options'),
                        'correct_answer': q_data.get('correct_answer'), 'explanation': q_data.get('explanation')
                    }
                )
                Question.objects.create(exam=exam, question_bank=None, text=ai_qb.text, options=ai_qb.options, correct_answer=ai_qb.correct_answer, explanation=ai_qb.explanation)
            
            return JsonResponse({'success': True, 'redirect_url': reverse('take_exam', args=[exam.id])})
        else:
            messages.error(request, "AI কোনো প্রশ্ন তৈরি করতে পারেনি। দয়া করে আমাদের প্রশ্ন ব্যাংক থেকে এখনই পরীক্ষা দিন।")
            return JsonResponse({'error': 'AI জেনারেশন ব্যর্থ', 'redirect_url': reverse('take_test')}, status=500)

    except AIQuotaExceededError:
        # Re-check limit to get the latest dynamic message from LimitService
        allowed, msg = LimitService.check_limits(request.user, request, quantity, question_type, is_mock=is_mock)
        return JsonResponse({'error': msg or "আপনার ব্যবহারের সীমা শেষ হয়ে গেছে।"}, status=429)
    except Exception as e:
        logger.error(f"AJAX Generation Error: {e}")
        return JsonResponse({'error': f'সিস্টেমে একটি ত্রুটি দেখা দিয়েছে। দয়া করে আবার চেষ্টা করুন।'}, status=500)

# ==========================================
# 📚 TAKE TEST VIEW (Question Bank Browser)
# ==========================================
@never_cache
def take_test(request):
    """
    Take Test View (DB Only) with Pagination (Test 1, Test 2...).
    Uses QuestionBank for sources.
    """
    error = None
    # 1. Fetch dynamic choices from DB
    all_subjects_qs = QuestionBank.objects.values('subject').annotate(
        count=Count('id')
    ).filter(count__gt=0).order_by('-count')
    
    subject_choices = [(s['subject'], f"{s['subject']} ({s['count']})") for s in all_subjects_qs]
    
    all_types_qs = QuestionBank.objects.values('question_type').annotate(
        count=Count('id')
    ).order_by('question_type')
    type_choices = [(t['question_type'], t['question_type']) for t in all_types_qs]

    all_levels_qs = QuestionBank.objects.values('level').annotate(
        count=Count('id')
    ).order_by('level')
    level_choices = [(l['level'], l['level']) for l in all_levels_qs if l['level']]

    # Initialize form with dynamic choices
    form_kwargs = {
        'subject_choices': subject_choices, 
        'type_choices': type_choices,
        'level_choices': level_choices
    }

    
    # AJAX Handling for Dynamic Dropdowns
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or (request.GET.get('ajax') == 'true'):
        target_subject = request.GET.get('subject')
        if target_subject:
            levels = QuestionBank.objects.filter(subject__iexact=target_subject).values_list('level', flat=True).distinct()
            types = QuestionBank.objects.filter(subject__iexact=target_subject).values_list('question_type', flat=True).distinct()
            return JsonResponse({
                'levels': sorted(list(set(l for l in levels if l))),
                'types': sorted(list(set(t for t in types if t)))
            })

    # Check if we have a subject from POST or GET
    subject = request.POST.get('subject') or request.GET.get('subject')

    level = request.POST.get('level') or request.GET.get('level') or 'Any'
    question_type = request.POST.get('question_type') or request.GET.get('question_type') or 'Any'
    page_str = request.POST.get('page') or request.GET.get('page')

    if request.method == 'POST':
        form = TakeTestForm(request.POST, **form_kwargs)
        if form.is_valid():
            subject = form.cleaned_data['subject']
            level = form.cleaned_data['level']
            question_type = form.cleaned_data['question_type']
    else:
        form = TakeTestForm(initial={
            'subject': subject,
            'level': level,
            'question_type': question_type
        }, **form_kwargs)

    if subject:
        # Build Filter
        filters = {'subject__iexact': subject}
        if level and level != 'Any':
            filters['level__iexact'] = level
        if question_type and question_type != 'Any':
            filters['question_type__iexact'] = question_type

        qs = QuestionBank.objects.filter(**filters).values(
            'text', 'options', 'correct_answer', 'explanation', 'id'
        ).distinct()

        # Fallback if specific filters too strict
        if not qs.exists():
            qs = QuestionBank.objects.filter(subject__icontains=subject).values(
                'text', 'options', 'correct_answer', 'explanation', 'id'
            ).distinct()

        total_questions = qs.count()

        if total_questions == 0:
            error = f"No questions found for '{subject}'."
        else:
            if page_str and page_str.isdigit():
                # START SPECIFIC TEST
                page = int(page_str)
                start_index = (page - 1) * 20
                end_index = page * 20
                questions_data = list(qs[start_index:end_index])

                if questions_data:
                    count = len(questions_data)
                    if request.user.is_authenticated:
                        from .services import LimitService
                        allowed, msg = LimitService.check_limits(request.user, request, is_mock=True)
                        if not allowed:
                            messages.error(request, msg)
                            return redirect('upgrade')
                        
                        exam = Exam.objects.create(
                            user=request.user,
                            subject=f"{subject} (Test {page})",
                            level=level,
                            difficulty='Medium',
                            question_type=question_type,
                            total_questions=count,
                            mode='FULL_EXAM'
                        )
                        
                        for q_dict in questions_data:
                            Question.objects.create(
                                exam=exam,
                                question_bank_id=q_dict.get('id'),
                                text=q_dict['text'],
                                options=q_dict['options'],
                                correct_answer=q_dict['correct_answer'],
                                explanation=q_dict.get('explanation')
                            )
                        return redirect('take_exam', exam_id=exam.id)
                    else:
                        if page == 1:
                            result = {
                                'subject': f"{subject} (Test {page})",
                                'level': level,
                                'questions': []
                            }
                            for q_dict in questions_data:
                                result['questions'].append({
                                    'question': q_dict['text'],
                                    'options': q_dict['options'],
                                    'correct_answer': q_dict['correct_answer'],
                                    'explanation': q_dict.get('explanation')
                                })
                            return render(request, 'exams/practice_exam.html', {
                                'result': result,
                                'read_only': True
                            })
                        else:
                            return redirect('account_login')
            else:
                # SEARCH MODE: Show available tests
                num_pages = (total_questions + 19) // 20
                tests_range = range(1, num_pages + 1)
                
                context = {
                    'form': form,
                    'tests_range': tests_range,
                    'total_questions': total_questions,
                    'selected_subject': subject,
                    'all_subjects': all_subjects_qs
                }
                if request.user.is_authenticated:
                    from .services import LimitService
                    allowed, msg = LimitService.check_limits(request.user, request, is_mock=True)
                    context['tests_dite_parbe'] = allowed
                    context['limit_msg'] = msg if not allowed else None
                
                return render(request, 'exams/take_test.html', context)

    return render(request, 'exams/take_test.html', {
        'form': form, 
        'error': error, 
        'all_subjects': all_subjects_qs
    })




# ==========================================
# ⏱️ TAKE EXAM VIEW (Main Mock Test UI)
# ==========================================
@login_required
@never_cache
def take_exam(request, exam_id):
    """
    User takes the exam.
    এই ফাংশনটি ইউজারের তৈরি করা প্রশ্নগুলো লোড করে এবং ইউজারকে পরীক্ষা দেওয়ার স্ক্রিন দেখায়। 
    (HTML পেজ থেকে ২০ মিনিটের টাইমার শুরু হয়। সাবমিট করলে এই ফাংশনটিই POST রিকোয়েস্ট রিসিভ করে 
     এবং উত্তরগুলো চেক করে score হিসাব করে)
    """
    exam = get_object_or_404(Exam, id=exam_id, user=request.user)
    
    if request.method == 'POST':
        score = 0
        total = exam.questions.count()
        
        all_exam_questions = list(exam.questions.all())
        for question in all_exam_questions:
            user_ans = request.POST.get(f'question_{question.id}')
            question.user_answer = user_ans
            
            # Check answer correctness
            if user_ans:
                # WRITTEN ANSWER LOGIC
                if exam.question_type == 'Written':
                    # Call AI to grade
                    analysis = analyze_written_answer_ai(
                        question.text, 
                        user_ans, 
                        question.correct_answer
                    )
                    
                    if analysis:
                        question.is_correct = analysis.get('is_correct', False)
                        question.feedback = analysis.get('feedback', '')
                        # You might want to use score_percent for more granular scoring
                        if question.is_correct:
                            score += 1
                    else:
                        # Fallback if AI fails
                        question.feedback = "AI Analysis failed to connect. Please review manually."
                        question.is_correct = False
                
                # MCQ / SHORT ANSWER LOGIC
                else:
                    # Normalize and Compare
                    import re
                    
                    def clean_opt(text):
                        if not text: return ""
                        # Remove leading A., A), 1., etc (e.g. "A. Answer" -> "Answer")
                        text = re.sub(r'^[a-zA-Z0-9][\.\)]\s*', '', str(text))
                        return text.strip().lower()

                    u_clean = clean_opt(user_ans)
                    c_clean = clean_opt(question.correct_answer)
                    
                    # 1. Exact match after cleaning
                    if u_clean == c_clean:
                        question.is_correct = True
                        score += 1
                        
                    # 2. Fuzzy match (containment) - e.g. "Paris" vs "Paris France"
                    elif len(u_clean) > 2 and (u_clean in c_clean or c_clean in u_clean):
                        question.is_correct = True
                        score += 1
                        
                    # 3. Fallback: Check original raw strings logic just in case
                    elif user_ans.strip().lower() == question.correct_answer.strip().lower():
                         question.is_correct = True
                         score += 1
 
                    else:
                        question.is_correct = False
            else:
                 question.is_correct = False
            
            # No individual save here, we will bulk_update after the loop
        
        # Save all questions at once
        fields_to_update = ['user_answer', 'is_correct', 'feedback']
        exam.questions.bulk_update(all_exam_questions, fields_to_update)



        # --- DEDUCT ON SUBMIT ---
        if exam.mode == 'FULL_EXAM' and exam.score is None:
            from .services import LimitService
            LimitService.increment_usage(request.user, request, is_mock=True)
        # ------------------------

        exam.score = score
        exam.completed_at = timezone.now()
        exam.save()

        # Trigger Background Image Generation for Social Sharing
        try:
            import threading
            from django.urls import reverse
            share_page_url = request.build_absolute_uri(reverse('share_exam', args=[exam.id])) + "?render=1"
            
            # Start background thread to generate the image
            thread = threading.Thread(target=generate_share_image_worker, args=(exam.id,))
            thread.daemon = True
            thread.start()
        except Exception as e:
            logger.error(f"Failed to start background image generation: {e}")

        return redirect('exam_result', exam_id=exam.id)


    return render(request, 'exams/take_exam.html', {'exam': exam})

@login_required
@never_cache
def exam_result(request, exam_id):
    """
    Show exam results with explanations.
    """
    exam = get_object_or_404(Exam, id=exam_id, user=request.user)
    return render(request, 'exams/exam_result.html', {'exam': exam})

@login_required
@never_cache
def get_ai_feedback(request, exam_id):
    """
    Generate AI analysis on-demand via AJAX.
    """
    exam = get_object_or_404(Exam, id=exam_id, user=request.user)
    
    # Security/Subscription Check
    if not hasattr(request.user, 'profile') or not request.user.profile.is_paid:
        return JsonResponse({'error': 'Upgrade to Premium to get personalized AI analysis and detailed feedback!'}, status=403)

    if exam.ai_analysis:
        return JsonResponse({'analysis': exam.ai_analysis})

    try:
        start_time = timezone.now()
        duration_delta = exam.completed_at - exam.created_at
        total_seconds = int(duration_delta.total_seconds())
        duration_str = f"{total_seconds // 60}m {total_seconds % 60}s"

        analysis = generate_exam_suggestion_ai(
            exam.subject, 
            exam.level, 
            exam.score, 
            exam.total_questions, 
            duration_str
        )
        
        # Abort if it took too long (close to Cloudflare 60s limit)
        if (timezone.now() - start_time).total_seconds() > 50:
             return JsonResponse({'error': 'TIMEOUT_RETRY', 'message': 'Server is busy. Switching AI model...'}, status=408)

        exam.ai_analysis = analysis
        exam.save()
        
        # Regenerate share image with the new AI feedback
        try:
            import threading
            thread = threading.Thread(target=generate_share_image_worker, args=(exam.id,))
            thread.daemon = True
            thread.start()
        except Exception as e:
            logger.error(f"Failed to trigger image update thread: {e}")

        return JsonResponse({'analysis': analysis})
    except Exception as e:
        return JsonResponse({'error': f"AI Error: {str(e)}"}, status=500)

@login_required
@never_cache
def dashboard(request):
    """User Dashboard View"""
    try:
        profile = request.user.profile
        profile.reset_monthly_if_needed()
    except Profile.DoesNotExist:
        profile = Profile.objects.create(user=request.user)
    
    # Get all user's past exams (base query)
    all_exams = Exam.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate FULL EXAM ONLY for limit (across all history)
    full_exams_count = all_exams.filter(mode='FULL_EXAM').count()

    # Filter for display (Date Filter)
    filter_date = request.GET.get('date')
    if filter_date:
        exams_list = all_exams.filter(created_at__date=filter_date)
    else:
        exams_list = all_exams

    # Pagination for AI Tests (10 per page)
    from django.core.paginator import Paginator
    paginator_ai = Paginator(exams_list, 10)
    page_ai = request.GET.get('page_ai')
    exams = paginator_ai.get_page(page_ai)

    # Fetch IELTS Results
    from ielts.models import Result as IeltsResult
    ielts_results = IeltsResult.objects.filter(user=request.user).select_related('test').order_by('-submitted_at')
    if filter_date:
        ielts_results = ielts_results.filter(submitted_at__date=filter_date)
    else:
        ielts_results = ielts_results[:6]

    extra_balance = profile.extra_tests_balance
    remaining_free = max(0, 5 - full_exams_count) if not profile.is_paid else "Unlimited"

    # Fetch Subscription Plan from DB
    from payments.models import SubscriptionPlan
    current_plan = SubscriptionPlan.objects.filter(plan_type=profile.subscription_type).first()
    
    if current_plan and current_plan.features:
        current_plan.feature_list = [f.strip() for f in current_plan.features.split(',')]
    elif current_plan:
        current_plan.feature_list = []

    limit_monthly = current_plan.ai_credits_limit if current_plan else 50
    if limit_monthly == -1:
        remaining_monthly = "Unlimited"
    else:
        remaining_monthly = max(0, limit_monthly - profile.monthly_question_count)

    context = {
        'profile': profile,
        'remaining_monthly': remaining_monthly,
        'is_paid': profile.is_paid,
        'exams': exams,
        'ielts_results': ielts_results,
        'exam_count': full_exams_count, # Usage for limit display
        'remaining_free': remaining_free,
        'extra_balance': extra_balance,
        'filter_date': filter_date,
        'current_plan': current_plan,
        'limit_monthly': limit_monthly,
        'ielts_limit': current_plan.ielts_mock_limit if current_plan else 0,
    }
    return render(request, 'users/dashboard.html', context)
@cache_page(60 * 10,key_prefix="about_page")
def about(request):
    return render(request, 'pages/about.html')
@cache_page(60 * 10,key_prefix="privacy_page")
def privacy(request):
    return render(request, 'pages/privacy_policy.html')
@cache_page(60 * 10,key_prefix="terms_page")
def terms(request):
    return render(request, 'pages/terms_of_service.html')
@cache_page(60 * 10,key_prefix="test_policy_page")
def test_policy(request):
    """
    Render Subscriptions and Test Policy Page in Bengali.
    """
    return render(request, 'pages/test_policy.html')
@cache_page(60 * 10,key_prefix="cookies_page")
def cookies(request):
    return render(request, 'pages/cookie_policy.html')
@cache_page(60 * 10,key_prefix="books_page")
def books(request):
    book_list = [
        {"id": 1, "title": "Cambridge IELTS 1", "link": "https://drive.google.com/file/d/13Os4N_B0Xmv0aAzPN-SWDt-qyHrsgzIs/view?usp=sharing"},
        {"id": 2, "title": "Cambridge IELTS 2", "link": "https://drive.google.com/file/d/1GTJ1A0nIeHVkBntb6944SMoTKs0GcMFW/view?usp=sharing"},
        {"id": 3, "title": "Cambridge IELTS 3", "link": "https://drive.google.com/file/d/1cwHOnDOFUCXyYtqdt6-SHdHFOY0oaDn7/view?usp=drive_link"},
        {"id": 4, "title": "Cambridge IELTS 4", "link": "https://drive.google.com/file/d/10-GHKr6awS3QRp5BkbnR8ET-BC7KW_mR/view?usp=drive_link"},
        {"id": 5, "title": "Cambridge IELTS 5", "link": "https://drive.google.com/file/d/1RSIzb7sfUy7AFzOvMMeqgbIpm-XqYugq/view?usp=drive_link"},
        {"id": 6, "title": "Cambridge IELTS 6", "link": "https://drive.google.com/file/d/1tDGBUP0ciKfNt6-yEAJvb4zZ8q7CE_qM/view?usp=drive_link"},
        {"id": 7, "title": "Cambridge IELTS 7", "link": "https://drive.google.com/file/d/12W5qpoSMmLrbP7V25F5pJTMl5priQiQT/view?usp=drive_link"},
        {"id": 8, "title": "Cambridge IELTS 8", "link": "https://drive.google.com/file/d/1G0r0yZidaDQC3hAP4g5vjkSdG7LOF779/view?usp=drive_link"},
        {"id": 9, "title": "Cambridge IELTS 9", "link": "https://drive.google.com/file/d/1tzH1jzQwockWY8aNmghixZ9hS5y9r2xX/view?usp=drive_link"},
        {"id": 10, "title": "Cambridge IELTS 10", "link": "https://drive.google.com/file/d/1iXUJ8OrunmXB1zDbYjjfINkk04Gk02-5/view?usp=drive_link"},
        {"id": 11, "title": "Cambridge IELTS 11", "link": "https://drive.google.com/file/d/1QqCF61FR468wuBGDOXtQ6A9PfgC8vd08/view?usp=drive_link"},
        {"id": 12, "title": "Cambridge IELTS 12", "link": "https://drive.google.com/file/d/188SAwgf7LRS_5yX5MBlVy-5dy56owirT/view?usp=drive_link"},
        {"id": 13, "title": "Cambridge IELTS 13", "link": "https://drive.google.com/file/d/1TdfCoayYMQNuLHyT3vfPBGZUViFOTzp_/view?usp=drive_link"},
        {"id": 14, "title": "Cambridge IELTS 14", "link": "https://drive.google.com/file/d/1DgGceY3wlGP9y7GeYRF6L13nCMlNqvn7/view?usp=drive_link"},
        {"id": 15, "title": "Cambridge IELTS 15", "link": "https://drive.google.com/file/d/1zFh8Fk1KevI26R6tKuEr_H9WxX3B3l-N/view?usp=drive_link"},
        {"id": 16, "title": "Cambridge IELTS 16", "link": "https://drive.google.com/file/d/1DifSBbkfr0KpzEgHdnQr9qt6GJ5SbGHp/view?usp=sharing"},
        {"id": 17, "title": "Cambridge IELTS 17", "link": "https://drive.google.com/file/d/13EftEm4m9e-PFlrFHwUFsGMyqA_Fe_CA/view?usp=drive_link"},
        {"id": 18, "title": "Cambridge IELTS 18", "link": "https://drive.google.com/file/d/1fhDmRFH2virXUtUxD188ECiKKDXJ10Hs/view?usp=drive_link"},
        {"id": 19, "title": "Cambridge IELTS 19", "link": "https://drive.google.com/file/d/1HQEIiDaUx1oxeKjJYxdUSAvnnRin8gZA/view?usp=sharing"},
        {"id": 20, "title": "Cambridge IELTS 20", "link": "https://drive.google.com/file/d/108v2gfhFEri1CExTw1PnE_RJaM6oEar1/view?usp=sharing"},
    ]
    return render(request, 'pages/books.html', {'books': book_list})


from django.http import HttpResponse, FileResponse
@never_cache
def share_exam(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    # Use local media URL for the share image
    image_url = request.build_absolute_uri(reverse('share_exam_image', args=[exam.id]))
    share_url = request.build_absolute_uri(reverse('share_exam', args=[exam.id]))

    return render(request, 'exams/share_exam.html', {
        'exam': exam,
        'image_url': image_url,
        'share_url': share_url
    })

def generate_share_image_worker(exam_id, target_url=None):
    """
    Background worker to generate and cache a DASHBOARD-STYLE screenshot of the exam result card using Pillow.
    Saves to media/<username>/exam_<exam_id>.png (local storage).
    """
    import os
    import logging
    from PIL import Image, ImageDraw, ImageFont
    from django.conf import settings
    from django.utils import timezone
    from .models import Exam
    from math import sin, cos, radians
    
    worker_logger = logging.getLogger(__name__)

    try:
        exam = Exam.objects.get(pk=exam_id)
        username = exam.user.username if exam.user else "guest"
        image_name = f"exam_{exam.id}.png"
        
        user_dir = os.path.join(settings.MEDIA_ROOT, username)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir, exist_ok=True)
            
        image_path = os.path.join(user_dir, image_name)
        
        # --- PREMIUM DASHBOARD DESIGN ---
        width, height = 1200, 630
        primary_bg = "#020617" # Deep Navy
        border_clr = "#1e293b" # Lighter Navy Border
        accent_clr = "#fbbf24" # Yellow/Gold
        safe_accent = "#22d3ee" # Cyan for secondary accents
        
        # 1. Create Canvas with Background
        img = Image.new('RGB', (width, height), color=primary_bg)
        draw = ImageDraw.Draw(img)
        
        # Subtle Grid Background
        grid_spacer = 40
        for x in range(0, width, grid_spacer):
            draw.line([(x, 0), (x, height)], fill="#0f172a", width=1)
        for y in range(0, height, grid_spacer):
            draw.line([(0, y), (width, y)], fill="#0f172a", width=1)

        # 2. Font Loading
        font_paths = [
            "C:/Windows/Fonts/arialbd.ttf", 
            "C:/Windows/Fonts/Segoe UI/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "arial.ttf"
        ]
        font_path = next((p for p in font_paths if os.path.exists(p)), None)
        
        def get_font(size):
            try:
                return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
            except:
                return ImageFont.load_default()

        f_xxl = get_font(80)
        f_logo = get_font(70)
        f_xl = get_font(50)
        f_lg = get_font(32)
        f_md = get_font(24)
        f_sm = get_font(18)
        f_xs = get_font(14)

        # 3. Drawing Header
        draw.text((50, 35), "Edu", font=f_logo, fill="#ffffff")
        try:
            edu_width = draw.textlength("Edu", font=f_logo)
        except AttributeError:
            edu_width = 120  # Fallback for old Pillow versions
        draw.text((50 + edu_width, 35), "Village", font=f_logo, fill="#2d9cdb")
        
        # Header Badge (Right side) - Dynamic Width
        header_date = timezone.now().strftime('%b %d, %Y').upper()
        subject_badge = f"QUIZ: {exam.subject[:20].upper()} | {header_date}"
        
        # Calculate badge size based on text
        try:
            tw = draw.textlength(subject_badge, font=f_md)
        except:
            tw = len(subject_badge) * 16 # rough estimate
            
        badge_w = tw + 60
        header_badge_x = 1160 - badge_w
        draw.rectangle([header_badge_x, 35, 1160, 95], fill="#0f172a", outline=accent_clr, width=2)
        draw.text((header_badge_x + 30, 52), subject_badge, font=f_md, fill="#ffffff")

        # 4. Left Sidebar: Profile & Gauge
        # Profile Box
        p_box = [40, 130, 360, 240]
        draw.rounded_rectangle(p_box, radius=20, fill="#0f172a", outline="#1e293b", width=1)
        # Profile Circle (Placeholder Avatar)
        draw.ellipse([65, 150, 135, 220], fill="#334155")
        draw.text((88, 160), username[0].upper(), font=f_xl, fill="#ffffff")
        draw.text((155, 160), "USERNAME:", font=f_xs, fill="#94a3b8")
        draw.text((155, 185), username, font=f_md, fill="#ffffff")

        # Accuracy Gauge
        g_center = (200, 450)
        g_radius = 125
        # Shadow/Background Circle
        draw.arc([g_center[0]-g_radius, g_center[1]-g_radius, g_center[0]+g_radius, g_center[1]+g_radius], 
                 start=135, end=405, fill="#1e293b", width=35)
        # Active Progress
        percentage = (exam.score / exam.total_questions) if exam.total_questions > 0 else 0
        end_angle = 135 + (percentage * 270)
        draw.arc([g_center[0]-g_radius, g_center[1]-g_radius, g_center[0]+g_radius, g_center[1]+g_radius], 
                 start=135, end=end_angle, fill=accent_clr, width=35)
        
        # Gauge Text (Centered)
        score_val = str(exam.score)
        total_val = f"/{exam.total_questions}"
        # Calculate full width of both strings together
        try:
            full_tw = draw.textlength(score_val, font=f_xxl) + draw.textlength(total_val, font=f_lg)
        except:
            full_tw = (len(score_val) * 50) + (len(total_val) * 20)

        # Baseline text positioning
        tx_start = g_center[0] - (full_tw / 2)
        draw.text((tx_start, g_center[1]-50), score_val, font=f_xxl, fill="#ffffff")
        try:
            sw = draw.textlength(score_val, font=f_xxl)
        except:
            sw = len(score_val) * 50
        draw.text((tx_start + sw + 5, g_center[1]-10), total_val, font=f_lg, fill="#94a3b8")
        draw.text((g_center[0], g_center[1]+55), "SCORE ACCURACY", font=f_sm, fill=accent_clr, anchor="mm")

        # 5. Middle Section: Detailed Stats
        mid_x = 400
        box_w = 420
        box_h = 75
        gap = 15
        
        stats = [
            ("TOTAL ATTEMPTS:", "1/1", "#ffffff"),
            ("CORRECT ANSWERS:", f"{exam.score}", safe_accent),
            ("INCORRECT ANSWERS:", f"{exam.total_questions - exam.score}", "#f43f5e"),
            ("TIME TAKEN:", f"{int(exam.duration.total_seconds()) if exam.duration else 0}s", accent_clr),
        ]

        for i, (label, value, val_clr) in enumerate(stats):
            y_pos = 130 + (i * (box_h + gap))
            draw.rounded_rectangle([mid_x, y_pos, mid_x + box_w, y_pos + box_h], radius=12, fill="#0f172a", outline="#1e293b")
            draw.text((mid_x + 25, y_pos + 25), label, font=f_md, fill="#ffffff")
            # Pull values further from edge to avoid cut-off
            draw.text((mid_x + box_w - 25, y_pos + 25), value, font=f_md, fill=val_clr, anchor="ra")

        # Final Score Box
        y_final = 130 + (4 * (box_h + gap))
        draw.rounded_rectangle([mid_x, y_final, mid_x + box_w, y_final + box_h + 10], radius=12, fill="#0f172a", outline=accent_clr, width=2)
        draw.text((mid_x + 25, y_final + 30), "FINAL SCORE:", font=f_md, fill=accent_clr)
        score_pct = f"{int(percentage * 100)}%"
        draw.text((mid_x + box_w - 25, y_final + 30), score_pct, font=f_xl, fill="#ffffff", anchor="ra")

        # 6. Right Sidebar: Performance & Skills
        right_x = 850
        box_right_w = 310
        # Performance Status Box
        draw.rounded_rectangle([right_x, 130, right_x + box_right_w, 350], radius=20, fill="#0f172a", outline="#1e293b")
        draw.text((right_x + 25, 150), "PERFORMANCE STATUS", font=f_md, fill=accent_clr)
        
        grade = "A+" if percentage >= 0.9 else "A" if percentage >= 0.8 else "B" if percentage >= 0.7 else "C" if percentage >= 0.6 else "D" if percentage >= 0.5 else "F"
        draw.text((right_x + 25, 210), "Grade:", font=f_md, fill="#94a3b8")
        draw.text((right_x + box_right_w - 25, 210), grade, font=f_xl, fill="#ffffff", anchor="ra")
        
        draw.text((right_x + 25, 280), "Global Rank:", font=f_md, fill="#94a3b8")
        draw.text((right_x + box_right_w - 25, 280), f"#{73 - exam.score}", font=f_xl, fill="#ffffff", anchor="ra")

        # Skill Matrix Box
        draw.rounded_rectangle([right_x, 370, right_x + box_right_w, 520], radius=20, fill="#0f172a", outline="#1e293b")
        draw.text((right_x + 25, 390), "SKILL MATRIX", font=f_md, fill=accent_clr)
        draw.text((right_x + 25, 435), "Knowledge:", font=f_md, fill="#94a3b8")
        draw.text((right_x + box_right_w - 25, 435), f"{exam.score}/{exam.total_questions}", font=f_md, fill="#ffffff", anchor="ra")
        draw.text((right_x + 25, 475), "Logic Sync:", font=f_md, fill="#94a3b8")
        draw.text((right_x + box_right_w - 25, 475), "Active", font=f_md, fill="#ffffff", anchor="ra")

        # 7. AI Summary Section
        draw.rounded_rectangle([right_x, 540, right_x + box_right_w, 610], radius=15, fill="#0f172a", outline=accent_clr, width=1)
        draw.text((right_x + 20, 553), "AI SUMMARY", font=f_sm, fill=accent_clr)
        
        # Make the summary dynamic
        summary_text = str(exam.ai_analysis) if exam.ai_analysis else "Complete exam to receive AI feedback..."
        # Truncate text to fit the box cleanly (around 45 characters)
        if len(summary_text) > 42:
            summary_text = summary_text[:40] + "..."
        # Remove any HTML tags safely just in case
        import re
        summary_text = re.sub(r'<[^>]+>', '', summary_text).strip()
        
        draw.text((right_x + 20, 580), summary_text, font=f_xs, fill="#94a3b8")

        # Brand Footer
        draw.text((40, 595), "EDUCATION VILLAGE - SMART LEARNING ECOSYSTEM", font=f_sm, fill="#475569")
        
        # Save image locally
        img.save(image_path, "PNG")

        # Store local media URL
        exam.share_image_url = f"/media/{username}/{image_name}"
        exam.save()
        
        worker_logger.info(f"Share image saved locally for exam {exam_id}: {image_path}")
        return image_path

    except Exception as e:
        worker_logger.error(f"Error in share image worker (Enhanced Pillow) for exam {exam_id}: {e}")
        return None




def share_exam_image(request, exam_id):
    import os
    from django.conf import settings
    from django.urls import reverse

    exam = get_object_or_404(Exam, pk=exam_id)
    
    # If local file URL exists, serve from local storage
    if exam.share_image_url and exam.share_image_url.startswith('/media/'):
        local_path = os.path.join(settings.BASE_DIR, exam.share_image_url.lstrip('/'))
        if os.path.exists(local_path):
            return FileResponse(open(local_path, 'rb'), content_type="image/png")

    username = exam.user.username if exam.user else "guest"
    image_name = f"exam_{exam.id}.png"
    user_dir = os.path.join(settings.MEDIA_ROOT, username)
    image_path = os.path.join(user_dir, image_name)

    # Generate if not exists
    if not os.path.exists(image_path):
        from django.urls import reverse
        target_url = request.build_absolute_uri(reverse('share_exam', args=[exam.id])) + "?render=1"
        generate_share_image_worker(exam.id)

    if os.path.exists(image_path):
        return FileResponse(open(image_path, 'rb'), content_type="image/png")
    
    return HttpResponse("Generation failed or in progress.", status=503)
