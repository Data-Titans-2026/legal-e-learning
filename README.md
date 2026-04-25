# LEGAL_E_LEARNING

A Flask legal assistant with user accounts, OTP signup, threaded chat history, and local RAG retrieval over category-wise legal knowledge files.

## Features

- Login, signup, OTP email verification, profile editing, and logout
- Threaded chat history with clickable conversations
- Continue an older conversation from the history page
- Legal chat categories such as family law, employment, consumer rights, criminal law, and more
- Local ChromaDB vector search over `knowledge_base/`
- Groq-backed LLM responses when `GROQ_API_KEY` is valid
- Local RAG fallback when the LLM provider is unavailable
- Smoother chat UX with typing indication and disabled send state while a reply is pending

## Setup

Requirements:

- Python 3.10 or newer
- Git

Clone the project and enter the folder:

```bash
git clone <repository-url>
cd legal-e-learning
```

Create and activate a virtual environment.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```bat
py -m venv .venv
.\.venv\Scripts\activate.bat
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file.

macOS / Linux:

```bash
cp data.env.example data.env
```

Windows PowerShell:

```powershell
Copy-Item data.env.example data.env
```

Windows Command Prompt:

```bat
copy data.env.example data.env
```

Initialize the database, build the RAG index, and start the app:

```bash
python init_db.py
python rag_engine.py
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Free Deployment on Render

This project is ready to deploy as a Render Web Service. Push the latest code to
GitHub, then create a new Render service from the repository in your GitHub
organization.

If Render detects `render.yaml`, it can create the service with these settings:

```text
Runtime: Python
Plan: Free
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
```

Add these environment variables in the Render dashboard:

```env
EMAIL_ADDRESS="your_email@gmail.com"
EMAIL_PASSWORD="your_gmail_app_password"
GROQ_API_KEY="your_groq_api_key"
LLM_PROVIDER="groq"
SECRET_KEY="a-long-random-secret"
```

For Gmail OTP, use a Gmail app password, not your normal Gmail password.

Render Free is fine for a hackathon demo, but its local filesystem is ephemeral.
That means `database/app.db` and generated `chroma_db/` files can be lost after a
restart, redeploy, or spin-down. For a production version, move user/chat data
from SQLite to a hosted Postgres database.

## App Flow

1. Sign up with name and email.
2. Verify the OTP sent to the configured email account.
3. Create a password and log in.
4. Choose a legal issue category from the home page.
5. Ask questions in the chatbot.
6. Open `History` to resume or delete previous conversation threads.

Each new chat creates a conversation thread. Follow-up messages stay attached to the same thread, and clicking a thread in history opens the full conversation again.

## Environment

Create `data.env` from `data.env.example` and fill in your values:

```env
EMAIL_ADDRESS=""
EMAIL_PASSWORD=""
GROQ_API_KEY=""
LLM_PROVIDER="groq"
SECRET_KEY="change-this-to-a-random-secret-key"
```

`data.env` is ignored by Git so secrets are not pushed.

## RAG Data

The source documents live in `knowledge_base/<category>/overview.txt`.

The generated vector index lives in `chroma_db/` and is ignored by Git. If `chroma_db/` is missing, the app can rebuild it from `knowledge_base/`, or you can run:

```bash
python rag_engine.py
```

## Database

The SQLite database lives at `database/app.db`.

Run the initializer whenever you set up the app or after pulling schema changes:

```bash
python init_db.py
```

Current core tables:

- `users`: registered users and password hashes
- `otp_requests`: signup OTP records and verification state
- `chat_threads`: one row per conversation thread
- `chats`: individual user messages and assistant responses linked to a thread

The initializer is migration-friendly for the current project: it creates missing tables, adds missing columns such as `thread_id` and `is_verified`, and wraps older one-message chat rows into thread records.

## Main Routes

- `/`: login page
- `/login`: login API
- `/signup`: signup page
- `/send-otp`: send signup OTP
- `/verify-otp`: verify signup OTP
- `/complete-signup`: create account after OTP verification
- `/home`: legal category selection
- `/chatbot`: chatbot page, with `?issue=<category>` or `?thread_id=<id>`
- `/ask`: chatbot API
- `/history`: threaded history page
- `/chat/thread/<id>`: load a saved thread
- `/profile`: account profile page
- `/profile/update`: update account details
- `/logout`: clear the session

## Notes

- On macOS or Linux, use `python3` instead of `python` if your system maps `python` to Python 2 or does not provide a `python` command.
- On Windows, `py` uses the Python launcher. If `py` is unavailable, try `python` instead.
- A `401 Invalid API Key` response from Groq means the key in `data.env` is invalid or revoked.
- Without a valid Groq key, the chatbot still returns the most relevant local reference material.
- Signup completion is enforced server-side: an OTP request must be verified before `/complete-signup` will create the user.
