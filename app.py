import streamlit as st
import google.generativeai as genai
import json
import PyPDF2
import io
import sqlite3
import uuid
import stripe
import datetime
from streamlit_cookies_controller import CookieController
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# --- 1. PAGE CONFIGURATION (Must be first) ---
st.set_page_config(page_title="StudyGenius Pro", page_icon="🎓", layout="centered")

# --- 2. COOKIE CONTROLLER (Remembers the user) ---
cookie_controller = CookieController()

# --- 3. DATABASE SETUP (Monthly Subscription Tracking Only) ---
conn = sqlite3.connect("study_genius.db", check_same_thread=False)
cursor = conn.cursor()

# We use pro_until to track the exact date their month expires
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    pro_until TIMESTAMP
)
""")
conn.commit()

# --- 4. THE "MAGIC" CSS ---
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 1.15rem; }
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    p, li { font-size: 1.2rem !important; line-height: 1.7 !important; }
    
    .stButton>button { 
        width: 100%; border-radius: 12px; height: 3.8em; 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
        color: white; font-weight: 800; font-size: 1.2rem; 
        border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
        transition: all 0.3s ease;
    }
    .stButton>button:hover { 
        transform: translateY(-2px); box-shadow: 0 6px 12px rgba(0,0,0,0.3); 
    }
    
    .streamlit-expanderHeader { font-size: 1.3rem !important; font-weight: 700 !important; color: #1f2937; }
    div[data-testid="stExpander"] { 
        border-radius: 12px !important; border: 2px solid rgba(100, 100, 100, 0.2) !important; 
        margin-bottom: 15px !important; background-color: rgba(255, 255, 255, 0.02);
    }
    
    div[role="radiogroup"] label { font-size: 1.2rem !important; font-weight: 600 !important; cursor: pointer; }
    
    .summary-box {
        padding: 25px; border-radius: 12px; border-left: 6px solid #667eea;
        background-color: rgba(102, 126, 234, 0.08); font-size: 1.25rem; 
        line-height: 1.7; margin-bottom: 2.5rem;
    }
    
    .premium-pitch-box {
        background-color: rgba(255, 215, 0, 0.08); border: 2px solid #FFD700;
        border-radius: 15px; padding: 20px; margin-bottom: 20px;
    }
    .premium-pitch-box h3 { margin-top: 0; color: #B8860B; text-align: center; font-weight: 900; font-size: 1.6rem; }
    .premium-pitch-box ul { list-style-type: '✨ '; padding-left: 15px; }
    .premium-pitch-box li { font-weight: 600; margin-bottom: 12px; font-size: 1.1rem !important; }
    
    button[data-baseweb="tab"] { font-size: 1.2rem !important; font-weight: 700 !important; padding-bottom: 10px; }
    
    .score-box {
        background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
        color: white; padding: 20px; border-radius: 12px; text-align: center;
        font-size: 1.8rem; font-weight: bold; margin-top: 20px;
        box-shadow: 0 4px 10px rgba(40, 167, 69, 0.3);
    }
    
    .pay-link {
        display: block; width: 100%; text-align: center; padding: 12px; margin-bottom: 10px;
        border-radius: 8px; text-decoration: none !important; font-weight: bold;
        transition: 0.3s;
    }
    .pay-global { background-color: #635bff; color: white !important; }
    .pay-global:hover { background-color: #4b45c6; }
    </style>
""", unsafe_allow_html=True)

# --- 5. ENTERPRISE CONFIG & SECURITY ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    stripe.api_key = st.secrets["STRIPE_SECRET_KEY"]
except:
    API_KEY = "AIzaSyAh6IgG2XH4l_3-2KNdCKkF2i8MNlerp5w"
    stripe.api_key = "sk_test_..." 
    
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- 6. SESSION STATE & USER FINGERPRINT (COOKIES) ---
user_cookie = cookie_controller.get('study_genius_user_id')

if user_cookie:
    st.session_state.user_id = user_cookie
else:
    new_id = str(uuid.uuid4())
    st.session_state.user_id = new_id
    cookie_controller.set('study_genius_user_id', new_id, max_age=31536000) # Remembers for 1 year

cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (st.session_state.user_id,))
conn.commit()

# --- 7. CHECK MONTHLY PRO STATUS ---
cursor.execute("SELECT pro_until FROM users WHERE user_id=?", (st.session_state.user_id,))
row = cursor.fetchone()
db_pro_until = row[0] if row else None

st.session_state.is_pro = False
st.session_state.days_left = 0

if db_pro_until:
    expire_date = datetime.datetime.fromisoformat(db_pro_until)
    if datetime.datetime.now() < expire_date:
        st.session_state.is_pro = True
        st.session_state.days_left = (expire_date - datetime.datetime.now()).days

# Initialize session states
if 'first_try_used' not in st.session_state:
    st.session_state.first_try_used = False
if 'study_data' not in st.session_state:
    st.session_state.study_data = None
if 'current_filename' not in st.session_state:
    st.session_state.current_filename = None
if 'pdf_text' not in st.session_state:
    st.session_state.pdf_text = ""
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# --- 8. AUTOMATIC STRIPE PAYMENT VERIFICATION ---
query_params = st.query_params
if "session_id" in query_params and not st.session_state.is_pro:
    session_id = query_params["session_id"]
    try:
        checkout_session = stripe.checkout.Session.retrieve(session_id)
        if checkout_session.payment_status == "paid":
            # Add 30 days to their account upon successful card charge
            new_expiry = (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
            cursor.execute("UPDATE users SET pro_until=? WHERE user_id=?", (new_expiry, st.session_state.user_id))
            conn.commit()
            st.session_state.is_pro = True
            st.success("🎉 Payment verified! You now have 30 days of PRO access.")
            st.query_params.clear()
            st.rerun()
    except Exception as e:
        st.error("Could not verify payment. Please contact support.")

# --- 9. PDF EXPORT HELPER FUNCTIONS ---
def convert_flashcards_to_pdf(flashcards):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph("StudyGenius Flashcards", styles['Title']))
    elements.append(Spacer(1, 20))
    
    for i, card in enumerate(flashcards):
        elements.append(Paragraph(f"<b>Q{i+1}:</b> {card['front']}", styles['Heading3']))
        elements.append(Paragraph(f"<b>Answer:</b> {card['back']}", styles['Normal']))
        elements.append(Spacer(1, 15))
        
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def convert_tf_to_pdf(true_false_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph("StudyGenius True/False Quiz", styles['Title']))
    elements.append(Spacer(1, 20))
    
    for i, tf in enumerate(true_false_data):
        elements.append(Paragraph(f"<b>Statement {i+1}:</b> {tf['statement']}", styles['Heading3']))
        elements.append(Paragraph(f"<b>Answer:</b> {tf['answer']}", styles['Normal']))
        elements.append(Paragraph(f"<b>Explanation:</b> {tf['explanation']}", styles['Normal']))
        elements.append(Spacer(1, 15))
        
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def convert_mcq_to_pdf(mcq_data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    elements.append(Paragraph("StudyGenius Multiple Choice Quiz", styles['Title']))
    elements.append(Spacer(1, 20))
    
    for i, mcq in enumerate(mcq_data):
        elements.append(Paragraph(f"<b>Q{i+1}:</b> {mcq['question']}", styles['Heading3']))
        for option in mcq['options']:
            elements.append(Paragraph(option, styles['Normal']))
        elements.append(Paragraph(f"<b>Answer:</b> {mcq['answer']}", styles['Normal']))
        elements.append(Paragraph(f"<b>Explanation:</b> {mcq['explanation']}", styles['Normal']))
        elements.append(Spacer(1, 15))
        
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

# --- 10. SIDEBAR ---
with st.sidebar:
    st.markdown("""
        <div class="premium-pitch-box">
            <h3>👑 StudyGenius PRO</h3>
            <ul>
                <li><b>Unlimited</b> PDF Uploads</li>
                <li><b>50+</b> Flashcards & MCQs</li>
                <li><b>AI Professor</b> Chat Access</li>
                <li><b>Zero</b> Wait Times</li>
            </ul>
        </div>
    """, unsafe_allow_html=True)
    
    if not st.session_state.is_pro:
        st.markdown("### 🌍 Pro Subscription ($1.99 / mo)")
        st.info("Pay securely with Visa, Mastercard, Apple Pay, or Google Pay.")
        
        # INSERT YOUR STRIPE LINK HERE.
        stripe_link = "https://buy.stripe.com/test_your_link_here" 
        st.markdown(f"<a href='{stripe_link}' class='pay-link pay-global'>💳 Upgrade to PRO</a>", unsafe_allow_html=True)

    else:
        st.success(f"👑 You are an Active PRO User! ({st.session_state.days_left} days left)")
        
    st.divider()
    st.markdown("### ⚙️ Settings")
    arabic_mode = st.toggle("🇸🇦 Translate Kit to Arabic", value=False)
    st.caption("Note: PDF downloads currently only support English characters.")

# --- 11. MAIN APP UI ---
st.markdown("<h1 style='text-align: center; font-weight: 900; margin-bottom: 0; font-size: 3rem; background: -webkit-linear-gradient(#667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>🎓 StudyGenius AI</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; font-size: 1.3rem !important; color: gray; margin-bottom: 2rem;'>Turn any long lecture into an interactive study kit in 5 seconds.</p>", unsafe_allow_html=True)

file = st.file_uploader("📂 Drop your PDF syllabus or lecture here", type=["pdf"])

if file:
    if file.name != st.session_state.current_filename:
        st.session_state.study_data = None
        st.session_state.current_filename = file.name
        st.session_state.pdf_text = ""
        st.session_state.chat_history = [] 

    can_proceed = not st.session_state.first_try_used or st.session_state.is_pro
    btn_label = "✨ Generate My Free Study Kit" if not st.session_state.first_try_used else "💎 Generate Premium Kit"
    
    if not st.session_state.study_data:
        if st.button(btn_label):
            if can_proceed:
                with st.spinner("🧠 Reading your document and generating interactive quizzes..."):
                    try:
                        reader = PyPDF2.PdfReader(file)
                        text = " ".join([p.extract_text() for p in reader.pages if p.extract_text()])
                        st.session_state.pdf_text = text 
                        
                        if len(text.strip()) < 50:
                            st.warning("Oops! This PDF looks empty or unreadable. Try saving it as a standard text PDF.")
                            st.stop()
                        
                        card_count = 50 if st.session_state.is_pro else 10
                        lang_instruction = "IMPORTANT: Translate ALL output (summary, flashcards, true/false, mcq) into Arabic." if arabic_mode else "Output everything in English."
                        
                        prompt = f"""
                        You are an expert university tutor. Summarize this text clearly in 1 paragraph.
                        Then create {card_count} flashcards (Question/Answer), {card_count} True/False statements, and {card_count} Multiple Choice Questions (4 options A, B, C, D) to test the student's knowledge.
                        {lang_instruction}
                        Return ONLY valid JSON: 
                        {{
                            "summary": "...", 
                            "flashcards": [{{"front": "...", "back": "..."}}], 
                            "true_false": [{{"statement": "...", "answer": "True", "explanation": "..."}}],
                            "mcq": [{{"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "A", "explanation": "..."}}]
                        }}
                        TEXT: {text[:80000]}
                        """
                        
                        response = model.generate_content(prompt)
                        
                        raw_text = response.text.strip()
                        if raw_text.startswith("```json"): 
                            raw_text = raw_text[7:]
                        elif raw_text.startswith("```"):
                            raw_text = raw_text[3:]
                        if raw_text.endswith("```"): 
                            raw_text = raw_text[:-3]
                            
                        st.session_state.study_data = json.loads(raw_text.strip())
                        
                        if not st.session_state.is_pro:
                            st.session_state.first_try_used = True
                        
                        st.balloons()
                        st.rerun()
                                
                    except Exception as e:
                        st.error(f"We hit a small bump while reading your file. Please ensure it is a valid PDF and try again. Error: {e}")
            else:
                st.error("🔒 You've used your free try! Upgrade via the sidebar to unlock Premium interactive features.")

    # --- 12. RENDER THE INTERACTIVE STUDY KIT ---
    if st.session_state.study_data:
        data = st.session_state.study_data
        
        st.markdown("## 📝 Complete Lecture Summary")
        st.markdown(f"<div class='summary-box'>{data['summary']}</div>", unsafe_allow_html=True)
        
        st.markdown("## 🧠 Interactive Study Modes")
        
        tab1, tab2, tab3, tab4 = st.tabs(["🃏 Flashcards", "✅ True/False", "📝 Multiple Choice", "👨‍🏫 AI Professor"])
        
        # --- TAB 1: FLASHCARDS ---
        with tab1:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown("<p style='color: gray;'>Click on a question to reveal the answer.</p>", unsafe_allow_html=True)
            with col2:
                fc_pdf = convert_flashcards_to_pdf(data['flashcards'])
                st.download_button(
                    label="📥 Download PDF",
                    data=fc_pdf,
                    file_name="StudyGenius_Flashcards.pdf",
                    mime="application/pdf",
                    key="fc_dl_btn",
                    use_container_width=True
                )
                
            for i, card in enumerate(data['flashcards']):
                with st.expander(f"📌 **Q{i+1}:** {card['front']}"):
                    st.success(f"**Answer:** {card['back']}")
                    
        # --- TAB 2: TRUE / FALSE ---
        with tab2:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown("<p style='color: gray;'>Test your knowledge. Select True or False.</p>", unsafe_allow_html=True)
            with col2:
                if 'true_false' in data:
                    tf_pdf = convert_tf_to_pdf(data['true_false'])
                    st.download_button(
                        label="📥 Download PDF",
                        data=tf_pdf,
                        file_name="StudyGenius_TrueFalse.pdf",
                        mime="application/pdf",
                        key="tf_dl_btn",
                        use_container_width=True
                    )
            
            st.write("")

            if 'true_false' in data:
                tf_correct = 0
                tf_answered = 0
                
                for i, tf in enumerate(data['true_false']):
                    with st.container(border=True):
                        st.markdown(f"**Statement {i+1}:** {tf['statement']}")
                        
                        user_choice = st.radio(
                            "Your Answer:", 
                            ["Select...", "True", "False"], 
                            key=f"tf_{i}_{st.session_state.current_filename}", 
                            horizontal=True
                        )
                        
                        if user_choice != "Select...":
                            tf_answered += 1
                            correct_answer = "True" if "true" in tf['answer'].lower() else "False"
                            if user_choice == correct_answer:
                                st.success("🎯 **Correct!**")
                                tf_correct += 1
                            else:
                                st.error(f"❌ **Incorrect.** The correct answer is {correct_answer}.")
                            st.info(f"**Explanation:** {tf['explanation']}")
                            
                if tf_answered == len(data['true_false']) and len(data['true_false']) > 0:
                    st.markdown(f"<div class='score-box'>🏆 Final Score: {tf_correct} / {len(data['true_false'])}</div>", unsafe_allow_html=True)
            else:
                st.warning("No True/False questions were generated.")

        # --- TAB 3: MULTIPLE CHOICE ---
        with tab3:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown("<p style='color: gray; margin-bottom: 20px;'>Select the best answer for each question.</p>", unsafe_allow_html=True)
            with col2:
                if 'mcq' in data:
                    mcq_pdf = convert_mcq_to_pdf(data['mcq'])
                    st.download_button(
                        label="📥 Download PDF",
                        data=mcq_pdf,
                        file_name="StudyGenius_MCQ.pdf",
                        mime="application/pdf",
                        key="mcq_dl_btn",
                        use_container_width=True
                    )
            
            st.write("")

            if 'mcq' in data:
                mcq_correct = 0
                mcq_answered = 0
                
                for i, mcq in enumerate(data['mcq']):
                    with st.container(border=True):
                        st.markdown(f"**Q{i+1}:** {mcq['question']}")
                        
                        options_display = ["Select..."] + mcq['options']
                        user_choice = st.radio(
                            "Choose an option:", 
                            options_display, 
                            key=f"mcq_{i}_{st.session_state.current_filename}"
                        )
                        
                        if user_choice != "Select...":
                            mcq_answered += 1
                            user_letter = user_choice.split(".")[0].strip() if "." in user_choice else user_choice.strip()
                            correct_letter = mcq['answer'].strip()
                            
                            if user_letter.upper() == correct_letter.upper():
                                st.success("🎯 **Correct!**")
                                mcq_correct += 1
                            else:
                                st.error(f"❌ **Incorrect.** The correct answer is {correct_letter}.")
                            st.info(f"**Explanation:** {mcq['explanation']}")
                
                if mcq_answered == len(data['mcq']) and len(data['mcq']) > 0:
                    st.markdown(f"<div class='score-box'>🏆 Final Score: {mcq_correct} / {len(data['mcq'])}</div>", unsafe_allow_html=True)
            else:
                st.warning("No MCQ questions were generated.")

        # --- TAB 4: AI PROFESSOR CHAT ---
        with tab4:
            st.markdown("### 👨‍🏫 Ask the AI Professor")
            st.markdown("<p style='color: gray;'>Stuck on a question? Ask me to explain it to you like you're 5!</p>", unsafe_allow_html=True)
            
            if not st.session_state.is_pro:
                st.warning("🔒 AI Professor is a Premium feature. Upgrade to ask unlimited questions about your materials!")
            else:
                for message in st.session_state.chat_history:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                
                if prompt := st.chat_input("Ask a question about the lecture..."):
                    with st.chat_message("user"):
                        st.markdown(prompt)
                    st.session_state.chat_history.append({"role": "user", "content": prompt})
                    
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking..."):
                            chat_context = f"You are a helpful university professor. Use this lecture text to answer the student's question clearly and concisely. Lecture Text: {st.session_state.pdf_text[:50000]} \n\n Student Question: {prompt}"
                            
                            try:
                                response = model.generate_content(chat_context)
                                st.markdown(response.text)
                                st.session_state.chat_history.append({"role": "assistant", "content": response.text})
                            except Exception as e:
                                st.error("I'm having trouble connecting right now. Please try again.")

        st.write("---")
        if st.button("🔄 Start Over with a New Kit", use_container_width=True):
            st.session_state.study_data = None
            st.session_state.pdf_text = ""
            st.session_state.chat_history = []
            st.rerun()