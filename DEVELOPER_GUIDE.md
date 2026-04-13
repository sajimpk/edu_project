# 🛠️ Junior Developer Guide (EduVillage LMS)

Welcome to EduVillage! This guide will explain how the project is structured, how the AI works, and how data moves between different functions.

## 📂 1. Project Architecture (অ্যাপগুলোর বিবরণ)
The platform is broken down into several modular Django applications:
- **`questions/`**: The core app. Handles AI Test Generation, the Question Bank (Saving previous AI responses), and user's Exam taking views.
- **`ielts/`**: A specialized app for Cambridge IELTS Reading. Handles reading passages, specific question types (Matching Headings, True/False/Not Given), and calculates Band Scores (2-9).
- **`users/`**: Manages authentication (Allauth), user profiles, and subscription tier upgrades (Free, Pro, Premium).
- **`payments/`**: Integrating Stripe webhooks and Manual (bKash/Nagad) verifications using a transaction ID checking system.
- **`blog/`**: A CMS built with CKEditor to let Admins publish educational posts and SEO content from `admin/`.

---

## ⚙️ 2. Key Functions & How They Work (মূল ফাংশনগুলো)

### A. The Core AI Generator: `generate_questions_ai()` (in `questions/utils.py`)
**What it does:** Contact AI Models (Gemini/Mistral/OpenRouter) to generate new questions.
**How it works:**
1. Loads API Keys from `os.getenv`.
2. Loops through a `MODELS_TO_TRY` list. If the primary key hits a rate limit (HTTP 429), it automatically switches to the fallback key.
3. Injects a highly complex **System Prompt** telling the AI to act as a 20-year experienced Senior NCTB/IELTS Examiner.
4. It receives JSON text back, strips Markdown using regex (`extract_json()`), and converts it into a Python dictionary.

### B. Smart Fetch vs Generation: `generate_test()` (in `questions/views.py`)
**What it does:** Processes the form when a student clicks "Make Test".
**How it works:**
1. **Quota Check:** Calls `LimitService.check_limits` to make sure the user hasn't asked for too many questions today based on their plan tracking.
2. **Database First (Guest):** If a user isn't logged in, it filters the `QuestionBank` model directly without hitting the AI. It returns them pseudo-exams without modifying the database.
3. **Database Look-up (Auth):** If an authenticated user runs it, it checks the `QuestionBank` first for unused questions of the exact type. This saves money and API calls.
4. **Fallback to AI:** If the database is empty for that criteria, it finally triggers `generate_questions_ai` and saves the new output into the `QuestionBank` table for the *next* student.

### C. The Exam Timer: `take_exam()` (in `questions/views.py` & `take_exam.html`)
**What it does:** Controls the actual test-taking interface.
**How it works:**
1. Loads all questions related to that specific `Exam` ID.
2. In the template (`take_exam.html`), there's JavaScript handling a strict `20-minute timer` (for FULL mock exams).
3. If the timer hits Zero, it executes `form.submit()` via JavaScript automatically.

### D. Result Calculation: `exam_result()` (in `questions/views.py`)
**What it does:** Analyzes submitted answers.
**How it works:**
1. Compares the student's selected input against `question.correct_answer`.
2. Marks `is_correct = True` and saves total percentage logic.
3. For Short Answers, it triggers `analyze_written_answer_ai()` to have the AI give a 1-10 mark based on grammatical and factual correctness.

---

## 🐞 3. Debugging Tips for Junior Devs (কোড ডিবাগিং)

- **AI Breaking (JSON Decode Errors):** If the AI returns a syntax error, it's usually because the AI added extra text around the JSON. Check `extract_json()` in `questions/utils.py`. The regex usually catches it, but if the Prompt changed recently, the AI might complain. Always test AI Prompts first!
- **Rate Limit Errors (Quota Exceeded):** Check `LimitService` in `questions/services.py`. Temporary limits are tracked in `django.core.cache` (Local memory or Redis).
- **Template Errors (Overlapping UI):** Check out `base.html` inside `templates/`. CSS variables are stored under `:root` in `<style>`. Make sure you don't use high `z-index` arbitrarily.

## 🚀 4. How to Add a New Page
1. Go to the app's `views.py`. E.g., `def my_page(request): return render(request, 'my_page.html')`
2. Define the path in the app's `urls.py`. `path('my-page/', views.my_page, name='my_page')`
3. Create `my_page.html` in the templates folder, and make sure to use `{% extends "base.html" %}` and everything goes inside `{% block content %}`.
