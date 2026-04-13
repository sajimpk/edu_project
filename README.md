# EduVillage LMS - Learning Management System

## Project Overview
EduVillage is Bangladesh's leading AI-powered educational platform designed to help students prepare for high-stakes exams like **NCTB (SSC/HSC)**, **IELTS**, and **BCS**. It democratizes high-quality education for rural students by using cutting-edge Generative AI to generate realistic, curriculum-aligned mock tests and study guides.

## Core Features
1. **AI Question Generator**: Generates dynamic multiple-choice, true/false, fill-in-the-blank, and short answer questions based on official curriculum data.
2. **IELTS Mock Tests & Reading Practice**: Dedicated IELTS app that provides Cambridge-style reading passages and interactive exam interfaces.
3. **Automated Exam Evaluation**: Instant grading and feedback for objective questions, with AI-powered subjective answer analysis coming soon.
4. **Question Bank**: Stores all previously generated AI questions. If an AI service fails or if a user is a guest, the system falls back to fetching questions from this database to ensure zero downtime.
5. **Role-based Authentication & Subscription**: Tracks student progress, limits usage securely via a quota system, and integrates Stripe & manual payment methods for premium access.
6. **Dynamic Blog**: Administrator-controlled content management system using CKEditor for rich text articles, tips, and guides.

## Technology Stack
- **Backend Framework**: Django 5.x (Python)
- **Database**: PostgreSQL (NeonDB used in production), SQLite (Local/Development)
- **Frontend**: HTML5, Vanilla Bootstrap 5, Custom `base.html` theming (Village Vibe, Glassmorphism, Responsive UI)
- **AI Integrations**: OpenRouter, Google Gemini, Mistral, Meta Llama. Uses multi-API key rolling to prevent rate limits.
- **Payment Gateway**: Stripe (Card) + Custom Manual payment handler (bKash/Nagad).

### Setup Instructions

1. **Clone the repository**
2. **Create a virtual environment**: `python -m venv env`
3. **Activate the virtual environment**:
   - Windows: `.\env\Scripts\activate`
   - Mac/Linux: `source env/bin/activate`
4. **Install Dependencies**: `pip install -r requirements.txt`
   *(Ensure Pillow is installed for ImageField support: `pip install Pillow`)*
5. **Setup Environment Variables**: Create a `.env` file in the root folder with the following:
   ```env
   DEBUG=True
   SECRET_KEY=your_secret_key
   OPENROUTER_API_KEY=your_openrouter_key
   ai_api1=your_fallback_key1
   ai_api2=your_fallback_key2
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_SECRET_KEY=sk_test_...
   ```
6. **Run Migrations**: `python manage.py makemigrations` and `python manage.py migrate`
7. **Create Superuser**: `python manage.py createsuperuser`
8. **Run Server**: `python manage.py runserver`

Visit `http://127.0.0.1:8000/` to test locally.

---
*Created for the students of Bangladesh 🇧🇩*
