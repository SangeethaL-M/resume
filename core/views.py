import os
import json
import re
from django.shortcuts import render, redirect
from django.conf import settings
from google import genai
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

def get_client():
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def resume_builder(request):
    if 'chat_history' not in request.session:
        request.session['chat_history'] = []
        request.session['resume_data'] = {
            "name": "", "email": "", "phone": "",
            "qualification": "", "skills": [], "experience": "",
            "suggested_roles": [], "ai_summary": "", "ai_bullets": []
        }
        # Keep track of exactly what question the AI just asked
        request.session['current_step'] = "ask_name"
    
    context = {
        "chat_history": request.session['chat_history'],
        "resume_data": request.session['resume_data']
    }

    if request.method == "POST":
        action = request.POST.get("action")
        user_input = request.POST.get("user_input", "").strip()

        if action == "reset":
            request.session.flush()
            return redirect('resume_builder')

        if not user_input:
            return render(request, "builder.html", context)

        history = request.session['chat_history']
        history.append({"sender": "user", "text": user_input})
        
        resume_data = request.session['resume_data']
        current_step = request.session.get('current_step', 'ask_name')
        lower_input = user_input.lower()
        
        # 1. CONTEXTUAL CAPTURE ENGINE (Captures anything you type based on the question asked)
        
        # Always check for email/phone in any message just in case
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_input)
        if email_match: resume_data["email"] = email_match.group(0)
        phone_match = re.search(r'\+?\d{10,12}', user_input)
        if phone_match: resume_data["phone"] = phone_match.group(0)

        # Slot filling based on what the AI last asked you
        if current_step == "ask_name":
            name_clean = re.sub(r'(?:name is|i am|myself)\s+', '', user_input, flags=re.IGNORECASE).strip()
            resume_data["name"] = name_clean.title()
            
        elif current_step == "ask_qualification":
            resume_data["qualification"] = user_input
            
        elif current_step == "ask_skills":
            # Accepts any comma-separated list or single skill you type!
            new_skills = [s.strip().title() for s in user_input.split(',') if s.strip()]
            resume_data["skills"] = list(set(resume_data["skills"] + new_skills))
            
        elif current_step == "ask_experience":
            resume_data["experience"] = user_input

        # 2. DECIDE NEXT STEP AND GENERATE THE QUESTION
        client = get_client()
        prompt = f"""
        You are an interactive AI Resume Coach. Review the data profile.
        Current Profile Data: {json.dumps(resume_data)}
        User Input: "{user_input}"
        
        Respond with a brief 2-sentence conversational reply acknowledging their input and asking for the next missing field.
        """

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            ai_text = response.text.strip()
            
            # Keep track of steps using AI state detection
            if not resume_data.get("name"): request.session['current_step'] = "ask_name"
            elif not resume_data.get("qualification"): request.session['current_step'] = "ask_qualification"
            elif not resume_data.get("skills"): request.session['current_step'] = "ask_skills"
            elif not resume_data.get("experience"): request.session['current_step'] = "ask_experience"
            else: request.session['current_step'] = "completed"
            
            history.append({"sender": "ai", "text": ai_text})
            
        except Exception:
            # Local Smart Failover Flow logic
            current_name = resume_data.get("name", "there")
            
            if not resume_data.get("name"):
                ai_msg = "Welcome! Let's get started on your resume. What is your full name?"
                request.session['current_step'] = "ask_name"
            elif not resume_data.get("qualification"):
                ai_msg = f"Got it, {current_name}! What is your educational qualification, degree, or college name?"
                request.session['current_step'] = "ask_qualification"
            elif not resume_data.get("skills"):
                ai_msg = f"Logged your education. Next, what key skills, tools, or professional expertise do you possess?"
                request.session['current_step'] = "ask_skills"
            elif not resume_data.get("experience"):
                ai_msg = f"Thanks! Do you have any prior work history, experience, internships, or academic projects?"
                request.session['current_step'] = "ask_experience"
            elif not resume_data.get("email") or not resume_data.get("phone"):
                ai_msg = f"Perfect. Finally, please share your email address and mobile number to complete your header records."
                request.session['current_step'] = "ask_contact"
            else:
                ai_msg = f"Excellent, {current_name}! Everything has been successfully gathered. Click the button below to see your customized styles!"
                request.session['current_step'] = "completed"
                
            history.append({"sender": "ai", "text": ai_msg})

        request.session['resume_data'] = resume_data
        request.session['chat_history'] = history
        request.session.modified = True
        return redirect('resume_builder')

    return render(request, "builder.html", context)


def render_preview(request):
    resume_data = request.session.get('resume_data', {})
    
    # Use exact inputs, fallback to simple strings only if completely empty
    if not resume_data.get('name'): resume_data['name'] = "Name Unspecified"
    if not resume_data.get('email'): resume_data['email'] = "no-email@provided.com"
    if not resume_data.get('phone'): resume_data['phone'] = "No Phone Provided"
    if not resume_data.get('qualification'): resume_data['qualification'] = "No Education Provided"
         
    if not resume_data.get('ai_summary'):
        qual = resume_data.get('qualification', 'Qualified Professional')
        skills_list = resume_data.get('skills', [])
        skills_str = ", ".join(skills_list) if skills_list else "Core Competencies"
        resume_data['ai_summary'] = f"Dedicated and detailed professional with clear qualifications as a {qual}. Possesses expertise in {skills_str} with a commitment to high operational quality standards."
        
        # Dynamic role matching engine based on standard fields
        q_low = qual.lower()
        if "mbbs" in q_low or "doctor" in q_low or "medical" in q_low:
            resume_data['suggested_roles'] = ["Medical Officer", "General Practitioner", "Healthcare Consultant"]
        elif "python" in q_low or "b.e" in q_low or "b.tech" in q_low or "engineering" in q_low:
            resume_data['suggested_roles'] = ["Software Engineer", "Systems Developer", "Data Associate"]
        else:
            resume_data['suggested_roles'] = ["Operations Executive", "Domain Specialist"]

    template_choice = request.GET.get('template', 'modern')
    return render(request, "preview.html", {
        "data": resume_data,
        "template": template_choice
    })