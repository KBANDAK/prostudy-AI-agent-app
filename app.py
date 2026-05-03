import streamlit as st
from openai import OpenAI
import json
import fitz 
import io
import sqlite3
import uuid
import datetime
import base64
from streamlit_cookies_controller import CookieController

OPENROUTER_API_KEY = ""

st.set_page_config(page_title="StudyGenius Pro", layout="centered")

cookie_controller = CookieController()

conn = sqlite3.connect("study_genius.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, pro_until TIMESTAMP)")
conn.commit()

st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 1.15rem; }
    .stButton>button { 
        width: 100%; border-radius: 12px; height: 3.8em; 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
        color: white; font-weight: 800; border: none;
    }
    .summary-box {
        padding: 25px; border-radius: 12px; border-left: 6px solid #667eea;
        background-color: rgba(102, 126, 234, 0.08); margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

MODEL_ID = "google/gemini-2.0-flash-001" 

client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=OPENROUTER_API_KEY,
  default_headers={ "HTTP-Referer": "http://localhost:8501", "X-Title": "StudyGenius AI" }
)

user_id = cookie_controller.get('study_genius_user_id') or str(uuid.uuid4())
if not cookie_controller.get('study_genius_user_id'):
    cookie_controller.set('study_genius_user_id', user_id, max_age=31536000)
st.session_state.user_id = user_id

cursor.execute("SELECT pro_until FROM users WHERE user_id=?", (user_id,))
row = cursor.fetchone()
st.session_state.is_pro = False
if row and row[0] and datetime.datetime.now() < datetime.datetime.fromisoformat(row[0]):
    st.session_state.is_pro = True

if 'study_data' not in st.session_state: st.session_state.study_data = None
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'is_scan' not in st.session_state: st.session_state.is_scan = False

def get_val(obj, keys, default=""):
    for k in keys:
        if k in obj and obj[k]:
            return obj[k]
    return default

st.markdown("<h1 style='text-align: center;'>StudyGenius AI</h1>", unsafe_allow_html=True)

if OPENROUTER_API_KEY == "your-sk-or-v1-key-here":
    st.info("Welcome! Please paste your OpenRouter API key into the code.")
    st.stop()

file = st.file_uploader("Upload your lecture PDF", type=["pdf"])

with st.sidebar:
    st.title("StudyGenius")
    st.info("Mode: 10 Questions" if not st.session_state.is_pro else "PRO Active")
    arabic_mode = st.toggle("Arabic Mode")

if file:
    if st.button("Generate Study Kit"):
        with st.spinner("Analyzing content..."):
            try:
                doc = fitz.open(stream=file.read(), filetype="pdf")
                text = "".join([page.get_text() for page in doc])
                
                count = 50 if st.session_state.is_pro else 10
                lang = "Translate all results to Arabic" if arabic_mode else "Use English"
                
                content_list = []
                if text.strip() and len(text.strip()) > 200:
                    st.session_state.is_scan = False
                    prompt_txt = f"Analyze this text. Create a summary, {count} flashcards, {count} T/F, and {count} MCQs. {lang}. TEXT: {text[:15000]}"
                else:
                    st.session_state.is_scan = True
                    prompt_txt = f"Analyze these images. Create a summary, {count} flashcards, {count} T/F, and {count} MCQs. {lang}."
                    for i in range(min(len(doc), 5)):
                        page = doc.load_page(i)
                        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                        b64_img = base64.b64encode(pix.tobytes("png")).decode('utf-8')
                        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}})
                
                content_list.insert(0, {"type": "text", "text": prompt_txt + "\nRETURN ONLY JSON: {'summary':'','flashcards':[{'front':'','back':''}],'true_false':[{'statement':'','answer':'','explanation':''}],'mcq':[{'question':'','options':[],'answer':'','explanation':''}]}"})

                response = client.chat.completions.create(
                    model=MODEL_ID,
                    messages=[{"role": "user", "content": content_list}],
                    response_format={ "type": "json_object" }
                )
                
                st.session_state.study_data = json.loads(response.choices[0].message.content)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

if st.session_state.study_data:
    sd = st.session_state.study_data
    st.markdown(f"<div class='summary-box'><b>Summary:</b><br>{sd.get('summary', '')}</div>", unsafe_allow_html=True)
    
    t1, t2, t3, t4 = st.tabs(["Flashcards", "True/False", "MCQs", "AI Professor"])
    
    with t1:
        for i, f in enumerate(sd.get('flashcards', [])):
            q = get_val(f, ['front', 'question', 'q', 'text'])
            a = get_val(f, ['back', 'answer', 'a'])
            with st.expander(f"Q{i+1}: {q}"):
                st.write(f"Answer: {a}")
                
    with t2:
        for i, tf in enumerate(sd.get('true_false', [])):
            s = get_val(tf, ['statement', 'question', 'text', 's'])
            a = get_val(tf, ['answer', 'a', 'correct'])
            e = get_val(tf, ['explanation', 'reason', 'e'])
            with st.container(border=True):
                st.write(f"**{i+1}.** {s}")
                user_ans = st.radio("Your Answer:", ["True", "False"], key=f"tf_{i}", horizontal=True, index=None)
                if user_ans:
                    if str(user_ans).strip().lower() == str(a).strip().lower():
                        st.success(f"Correct! | {e}")
                    else:
                        st.error(f"Incorrect. Correct answer: {a} | {e}")

    with t3:
        for i, m in enumerate(sd.get('mcq', [])):
            q = get_val(m, ['question', 'text', 'q'])
            opts = get_val(m, ['options', 'choices', 'list'], [])
            a = get_val(m, ['answer', 'a', 'correct'])
            e = get_val(m, ['explanation', 'e'])
            with st.container(border=True):
                st.write(f"**Q{i+1}:** {q}")
                user_mcq = st.radio("Select Option:", opts, key=f"mcq_{i}", index=None)
                if user_mcq:
                    u_str = str(user_mcq).strip().lower()
                    a_str = str(a).strip().lower()
                    if u_str == a_str or u_str.startswith(a_str + ".") or u_str.startswith(a_str + ")") or a_str in u_str:
                        st.success(f"Correct! | {e}")
                    else:
                        st.error(f"Incorrect. Correct answer: {a} | {e}")

    with t4:
        st.subheader("AI Professor")
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
            
        if chat_input := st.chat_input("Ask a question about the lecture..."):
            st.session_state.chat_history.append({"role": "user", "content": chat_input})
            with st.chat_message("user"): st.markdown(chat_input)
            
            with st.chat_message("assistant"):
                res = client.chat.completions.create(
                    model=MODEL_ID,
                    messages=[{"role": "user", "content": f"Context: {sd.get('summary')}. Question: {chat_input}"}]
                )
                ans = res.choices[0].message.content
                st.markdown(ans)
                st.session_state.chat_history.append({"role": "assistant", "content": ans})

    if st.button("Reset Application"):
        st.session_state.study_data = None
        st.rerun()
