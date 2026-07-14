"""
FAQ Knowledge base.
Each entry: (keywords_that_trigger_it, spoken_answer)
Add/edit these freely -- this is your "business logic" layer.
"""

FAQS = {
    "company": [
        (["interview", "schedule interview", "interview process", "recruitment"],
         "Our interview process includes a screening call, a technical interview, and a final HR discussion. Our team will contact you with the next steps."),
        (["careers", "jobs", "openings", "positions", "hiring"],
         "We are hiring for software development, product management, and customer success roles. Please send your resume to careers@abccompany.com."),
        (["documents", "resume", "cv", "portfolio"],
         "Please keep your resume, CV, and any relevant portfolio or certifications ready for the interview."),
        (["salary", "compensation", "pay", "package"],
         "Compensation details are shared during the offer stage and vary by role and experience."),
        (["location", "office", "address", "where"],
         "Our headquarters is located at MG Road, Hyderabad, and we also support remote team members."),
        (["contact", "hr", "human resources", "recruiter"],
         "You can contact our HR team at hr@abccompany.com for interview scheduling and hiring questions."),
        (["culture", "policy", "work culture", "benefits", "perks"],
         "We offer a flexible work culture, employee benefits, and a collaborative team environment. More details are shared during the interview."),
        (["questions", "about company", "company info", "information"],
         "Welcome to ABC Company. We're a growing team focused on delivering excellent products and support for our clients."),
    ],
}

GREETING = "Hello! Thank you for calling ABC Company. How may I help you today?"
FAREWELL = "Thank you for calling. Have a great day! Goodbye."
NOT_UNDERSTOOD = "I'm sorry, I didn't quite understand that. Could you please rephrase your question?"

# Phrases that should always trigger a transfer to a human agent
TRANSFER_KEYWORDS = [
    "manager", "human", "real person", "speak to someone", "representative",
    "angry", "frustrated", "complaint", "complain", "lawsuit", "legal",
    "emergency", "urgent help", "not working at all", "sue you",
]
