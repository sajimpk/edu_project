
import os
import json
import requests
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# 🤖 AI CONFIGURATION & API KEYS
# ==========================================
# .env ফাইল থেকে সবগুলো API Key নিচ্ছি। 
# যদি প্রাইমারি Key কাজ না করে, তবে AI অটোমেটিকভাবে পরবর্তী Key ট্রাই করবে। 
API_KEYS = [
    os.getenv("ai_api"),
    os.getenv("ai_api2"),
    os.getenv("ai_api3"),
    os.getenv("ai_api4"),
    os.getenv("ai_api5"),
    os.getenv("ai_api6")
]
# Remove duplicates and None values
API_KEYS = list(filter(None, dict.fromkeys(API_KEYS)))

# OpenRouter is used as the universal API provider
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# List of models to try in order of preference
# Get primary model from .env if set
env_model = os.getenv("AI_MODEL")
env_model2 = os.getenv("AI_MODEL2")

MODELS_TO_TRY = [
    env_model,
    env_model2,
    # "google/gemini-2.0-flash-001",
    # "meta-llama/llama-3.1-70b-instruct",
    # "google/gemini-pro-1.5",
]
# Clean list: remove None and duplicates while preserving order
MODELS_TO_TRY = list(filter(None, dict.fromkeys(MODELS_TO_TRY)))


# ==========================================
# 🧠 AI PROMPT ENGINEERING
# ==========================================
# এই প্রম্পটটি AI কে বলে দিচ্ছে সে একজন সিনিয়র এক্সামিনার। 
# সে যেন কঠিন এবং যুক্তিপূর্ণ প্রশ্ন বানায় এবং JSON বাদে আর কোনো টেক্সট না দেয়।
SYSTEM_PROMPT = """
You are a highly skilled, expert question generator at Education Village.
Your task is to generate top-tier, accurate, and relevant questions for various professional and academic exams.
You are a master of MCQ, Board, and IELTS style questions.

STRICT LANGUAGE RULES:
1. Use ONLY the language requested in the input (English or Bengali).
2. DO NOT use any other languages (like Malayalam, Arabic, Hindi, etc.) under any circumstances.
3. If the requested language is Bengali, ensure the entire response (question, options, and explanation) is in clean, academic Bengali.
4. If the requested language is English, ensure the entire response is in professional, academic English.

GENERAL RULES:
1. Accuracy: All questions must be factually correct and match the specific subject and level provided.
2. Structure: Questions must be sharp, clear, and perfectly formatted.
3. Difficulty: Match the exact difficulty requested (Beginner, Intermediate, Advanced).
4. No Repetition: Ensure each question is unique.
5. Explanations: Provide masterful, clear, and logical explanations that teach the concept behind the answer.

Return the output strictly as a JSON object with the following structure:
{
  "questions": [
    {
      "question": "Masterfully crafted question text?",
      "options": ["Plausible Option A", "Plausible Option B", "Correct Answer C", "Plausible Option D"],
      "correct_answer": "Must be EXACTLY one of the strings from the options list",
      "explanation": "A professional, expert-level explanation of the logic and concept."
    }
  ]
}
No markdown. No conversational text. Only the raw JSON object. 
Your work will shape the future of talented students; maintain the highest professional standard.
"""

def extract_json(text):
    """
    Helper to extract JSON from AI response which might contain markdown.
    """
    try:
        # Try to parse directly
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for code blocks
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    # Look for plain { ... }
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
         try:
            return json.loads(match.group(0))
         except json.JSONDecodeError:
            pass
            
    return None

class AIError(Exception):
    pass

class AIQuotaExceededError(AIError):
    pass

class AIServerError(AIError):
    """Exception raised when all AI API keys fail due to external factors (balance, auth, etc.)"""
    pass

# ==========================================
# 🔄 GET AI RESPONSE (FAILOVER LOGIC)
# ==========================================
def get_ai_response(model, prompt, system_instruction=None):
    """
    Get response from the AI model using OpenRouter via requests.
    Iterates through available API keys if one fails.
    এই ফাংশনটি AI মডেলে রিকোয়েস্ট পাঠায়। যদি কোনো কারণে (যেমন: Rate Limit, Payment Required) 
    ঐ API Key ফেইল করে, তাহলে লুপের মাধ্যমে এটি পরবর্তী Key দিয়ে আবার ট্রাই করে। 
    ফলে ইউজারের কাছে সহজে এরর মেসেজ পৌঁছায় না।
    """
    if not API_KEYS:
        print("No API keys found. Please set ai_api1, ai_api2, etc. in .env")
        return None
    
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
    }

    quota_errors = 0

    # Try each API key in order
    for api_key in API_KEYS:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "village.online",
            "X-Title": "Education Question Generator",
        }

        try:
            response = requests.post(BASE_URL, headers=headers, data=json.dumps(payload), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    return data['choices'][0]['message']['content']
                else:
                    print(f"Model {model} returned empty choices with key ending in ...{api_key[-4:]}")
                    continue 

            # Handle explicit errors that warrant switching keys
            elif response.status_code in [401, 402, 429, 403]: # Unauth, Payment Required, Rate Limit, Forbidden
                print(f"Key ending ...{api_key[-4:]} failed with {response.status_code}. Trying next key.")
                quota_errors += 1
                continue 
            
            else:
                 print(f"Model {model} error {response.status_code}: {response.text}")
                 continue

        except Exception as e:
            print(f"Error calling model {model} with key ...{api_key[-4:]}: {e}")
            continue # Try next key
            
    # If we are here, all keys failed.
    # If quota_errors reached the same number as len(API_KEYS), it means all keys are exhausted/invalid.
    if quota_errors > 0:
        raise AIServerError("AI Server busy or balance exhausted (API Keys failed).")

    return None

def generate_questions_ai(subject, level, difficulty, question_type, quantity, language, exclude_topics=[], model_index=None):
    """
    Generate questions using various AI models.
    exclude_topics: List of previously asked questions/topics to avoid repetition.
    model_index: If provided, try ONLY this model from MODELS_TO_TRY.
    """
    
    avoid_instruction = ""
    if exclude_topics:
        avoid_instruction = f"\n\nCRITICAL INSTRUCTION: Do NOT generate questions similar to these recently asked ones: {', '.join(exclude_topics[:10])}..."

    user_prompt = f"""
    Subject: {subject}
    Level: {level}
    Difficulty: {difficulty}
    Question Type: {question_type}
    Quantity: {quantity}
    
    IMPORTANT - Language Requirement:
    You MUST generate everything in {language.upper()} language.
    Do NOT use any other language or script (No Malayalam, No Arabic, No Hindi, etc).
    Use only standard {language.upper()} characters.
    {avoid_instruction}
    """

    # If model_index is specifically requested
    if model_index is not None:
        try:
            m = MODELS_TO_TRY[model_index]
            print(f"Direct request for model index {model_index}: {m}...")
            response_text = get_ai_response(m, user_prompt, SYSTEM_PROMPT)
            if response_text:
                json_result = extract_json(response_text)
                if json_result: return json_result
        except IndexError:
            pass
        return None

    # Default failover logic
    max_models = 3
    for i, m in enumerate(MODELS_TO_TRY[:max_models]):
        print(f"Trying model {i+1}/{max_models}: {m}...")
        try:
            response_text = get_ai_response(m, user_prompt, SYSTEM_PROMPT)
            
            if response_text:
                json_result = extract_json(response_text)
                if json_result:
                    return json_result
                else:
                    print(f"Failed to parse JSON from model {m} response.")
        except AIQuotaExceededError:
            # Re-check limit to get the latest dynamic message from LimitService
            allowed, msg = LimitService.check_limits(request.user, request, quantity, question_type, is_mock=is_mock)
            return JsonResponse({'error': msg or "আপনার ব্যবহারের সীমা শেষ হয়ে গেছে।"}, status=429)
        except AIServerError as e:
            logger.error(f"AI Server Error (Balance/Auth): {e}")
            return JsonResponse({'error': "AI সার্ভার বর্তমানে ব্যস্ত অথবা ব্যালেন্স শেষ। দয়া করে কিছুক্ষণ পর আবার চেষ্টা করুন বা সরাসরি প্রশ্ন ব্যাংকটি ব্যবহার করুন।"}, status=503)
        except Exception as e:
            logger.error(f"AJAX Generation Error: {e}")
            return JsonResponse({'error': f'সিস্টেমে একটি ত্রুটি দেখা দিয়েছে। দয়া করে আবার চেষ্টা করুন।'}, status=500)
            
    return None

def analyze_written_answer_ai(question_text, user_answer, correct_answer):
    """
    Analyze a written answer and provide a score and feedback strictly in BENGALI.
    """
    system_prompt = """আপনি একজন দক্ষ এবং পেশাদার এক্সাম গ্রেডার। 
    আপনার কাজ হলো শিক্ষার্থীর লিখিত উত্তরটি মূল প্রশ্নের সাথে তুলনা করে মূল্যায়ন করা।
    
    গুরুত্বপূর্ণ নিয়ম:
    ১. আপনার দেওয়া "feedback" অবশ্যই শুধুমাত্র শুদ্ধ বাংলায় হতে হবে। 
    ২. কোনো ইংরেজি শব্দ বা ইংরেজি অক্ষর ব্যবহার করবেন না। 
    ৩. শিক্ষার্থীর ভুলগুলো বুঝিয়ে দিন এবং কিভাবে ভালো করা যায় তার পরামর্শ দিন।
    
    আপনার রেসপন্সটি নিচের JSON ফরম্যাটে দিন:
    {
        "is_correct": boolean,
        "score_percent": number,
        "feedback": "সম্পূর্ণ বাংলায় স্পষ্ট এবং পেশাদার ফিডব্যাক"
    }
    """
    
    user_prompt = f"""
    প্রশ্ন: {question_text}
    শিক্ষার্থীর উত্তর: {user_answer}
    সঠিক উত্তর: {correct_answer}
    
    এই উত্তরটি মূল্যায়ন করুন। ফিডব্যাক অবশ্যই ১০০% বাংলায় এবং স্বচ্ছ হতে হবে। সর্বোচ্চ ৫০ শব্দের মধ্যে শেষ করুন।
    """
    
    for m in MODELS_TO_TRY:
        response = get_ai_response(m, user_prompt, system_prompt)
        if response:
             json_result = extract_json(response)
             if json_result:
                 return json_result
    
    return None

def generate_exam_suggestion_ai(subject, level, score, total, duration_str):
    """
    Generate ultra-short, professional, and ONLY BENGALI feedback for exam results.
    """
    wrong = total - score
    system_prompt = """আপনি একজন অভিজ্ঞ মেন্টর। শিক্ষার্থীর পরীক্ষার রেজাল্ট দেখে তাকে একটি অত্যন্ত সংক্ষিপ্ত কিন্তু স্পষ্ট এবং পেশাদার ফিডব্যাক দিন। 
    
    শর্তাবলী:
    ১. উত্তরটি অবশ্যই ১০০% শুদ্ধ বাংলায় হতে হবে। কোনো ইংরেজি শব্দ ব্যবহার করবেন না।
    ২. সম্বোধন হিসেবে 'আপনি' ব্যবহার করুন।
    ৩. আপনার পরামর্শটি স্পষ্ট এবং কার্যকর হতে হবে।
    """
    
    user_prompt = f"""
    বিষয়: {subject}
    ফলাফল: {score}/{total} (সঠিক/মোট)
    ভুল: {wrong}
    সময়: {duration_str}
    
    এই তথ্যের ওপর ভিত্তি করে শিক্ষার্থীকে দ্রুত ১-২ বাক্যে একটি প্রফেশনাল ফিডব্যাক দিন শুধুমাত্র বাংলায়।
    """

    for m in MODELS_TO_TRY:
        response = get_ai_response(m, user_prompt, system_prompt)
        if response:
            return response.strip()
            
    return f"আপনি {total}টির মধ্যে {score}টি সঠিক করেছেন। ভুল হয়েছে {wrong}টি। আরও উন্নতির জন্য নিয়মিত অনুশীলন করুন।"

    for m in MODELS_TO_TRY:
        # Use a faster model if possible, or just the list
        response = get_ai_response(m, user_prompt, system_prompt)
        if response:
            return response.strip()
            
    return "Great job practicing! Keep reviewing your weak areas to improve further."

