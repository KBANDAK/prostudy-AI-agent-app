# 🎓 StudyGenius AI: Autonomous Educational Agent

An autonomous educational AI agent built with Python and Streamlit that ingests raw document context, synthesizes structured study materials, and acts as an interactive, context-aware tutor. 

By leveraging the **Google Gemini 2.5 Flash API**, StudyGenius AI transforms static, dense lecture PDFs into dynamic learning environments in under 5 seconds.

## ✨ Key Features

* **Autonomous Document Parsing:** Extracts and processes text from uploaded PDF syllabi and lectures using `PyPDF2`.
* **AI-Generated Study Kits:** Automatically synthesizes 1-paragraph summaries, Flashcards, True/False statements, and Multiple Choice Questions formatted in strict JSON.
* **Interactive "AI Professor" Agent:** An embedded chat interface that allows users to query the AI agent in real-time about specific concepts within the uploaded document context.
* **Dynamic PDF Artifacts:** Uses `ReportLab` to programmatically generate and format downloadable PDF study guides based on the AI's output.
* **Premium Monetization Tier:** Integrated with the **Stripe API** to handle secure checkout sessions and unlock premium agent capabilities (larger context limits, unlimited generations).
* **Session Management:** Implements cookie-based fingerprinting to track user sessions and subscription status securely across the web app.

## 🛠️ Tech Stack

* **Language:** Python 3.9+
* **Frontend & Framework:** Streamlit
* **LLM / AI:** Google Generative AI (Gemini 2.5 Flash)
* **Document Processing:** PyPDF2, ReportLab
* **Payments:** Stripe API
* **Database:** SQLite (Local/Development)

## 🚀 Installation & Setup

**1. Clone the repository:**
```bash
git clone [https://github.com/KBANDAK/study-app.git](https://github.com/BIGGREEK2003/study-app.git)
cd study-app
