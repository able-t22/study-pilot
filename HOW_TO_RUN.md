# How to run StudyPilot on Windows

## 1. Start the existing installation

Open PowerShell and run:

```powershell
cd D:\PROJECTS\studypilot
.\.venv\Scripts\python.exe run.py
```

Your browser should open automatically. If it does not, visit:

**http://127.0.0.1:8000**

Keep the PowerShell window open while using StudyPilot. Press **Ctrl+C** in that window to stop the server.

The existing virtual environment has been repaired using an installed Python 3.12 interpreter. If that interpreter is later removed, follow the fresh setup instructions below.

## 2. Configure OpenRouter

StudyPilot uses **OpenRouter only** for online AI features.

Open the configuration file:

```powershell
notepad .env
```

If you are setting up the project for the first time and do not have an .env file, create it without overwriting an existing one:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set the following values, replacing the placeholder with your own key:

```dotenv
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=google/gemma-4-31b-it:free
OPENROUTER_FALLBACK_MODELS=inclusionai/ling-3.1-flash,openrouter/free
LLM_TIMEOUT=30
LLM_ATTEMPT_TIMEOUT=12
QUIZ_AI_SECONDS=25
OPENROUTER_VISION=0
DATABASE_URL=
```

Use your OpenRouter account to obtain a key and select a model available to your account. You can replace the primary and fallback model IDs with models available to your account. Availability, limits and credits depend on your account and the model.

Leave DATABASE_URL empty to use the built-in local SQLite database. Supabase is optional.

Save the file and restart the server after changing any settings. Keep .env private: it contains your API key and may contain database credentials.

Without an API key, local source search, extractive tutoring, source-based concept questions and learner tracking still work. AI-generated answers and other online AI features require a working OpenRouter key.

## 3. Fresh setup, if needed

Install **Python 3.10–3.12**, enabling **Add Python to PATH** during installation. Open a new PowerShell window afterward.

```powershell
cd D:\PROJECTS\studypilot
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Add your OpenRouter settings as described above, then start:

```powershell
.\.venv\Scripts\python.exe run.py
```

If python is not recognised but the Windows Python launcher is installed, use py -3.12 instead of python for the version check and environment creation.

You do not need Node.js, a GPU, or a separate FFmpeg installation. The first dependency installation may take several minutes.

### Recreate a broken virtual environment

Stop the server first. Rename the old environment so it can be restored if needed:

```powershell
cd D:\PROJECTS\studypilot
$backupName = ".venv-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
Rename-Item -LiteralPath .venv -NewName $backupName
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

This preserves your .env file and your uploaded material in data/.

## 4. Use the app

1. Create a learner profile.
2. Open **Library** and upload your course material: PDF, PPTX, text, Markdown, audio, video, or VTT/SRT transcripts.
3. Leave **Fast upload** enabled for quicker processing. It extracts text, performs scanned-page OCR, and builds topics locally. Disable it before uploading when you need figure descriptions, video frames and slide rendering.
4. Wait for ingestion and analysis to finish.
5. Open **Tutor** for cited answers or **Practice** for questions.
6. **Revise** automatically builds a local source-based pack, with your weakest topics first. Formulas render locally without a CDN.
7. Use the arrow beside the connection status to open **OpenRouter diagnostics**, then click **Test connection**. The status distinguishes a configured key from a successful connection, rate limits, invalid keys and network errors.
8. Use **Study cockpit** for daily study actions and mistake retries. Use **Revise** for spaced review and other revision tools.

**Upload your course material before starting practice. Adding material or re-analysing rebuilds topics and resets quiz history and mastery.**

For faster video/audio processing, upload a matching transcript in the same batch, for example lecture.mp4 and lecture.vtt. Without a transcript, local speech recognition is required; its first run may download the Whisper model. Set WHISPER_MODEL=tiny in .env for faster transcription.

Re-analyse updates topic structure; it does not extract figures skipped during a fast upload.

## 5. Run checks

From the project folder:

```powershell
.\.venv\Scripts\python.exe scripts/selftest.py
.\.venv\Scripts\python.exe scripts/test_llm_fallback.py
.\.venv\Scripts\python.exe scripts/test_features.py
.\.venv\Scripts\python.exe scripts/test_repairs.py
.\.venv\Scripts\python.exe scripts/test_study_flow.py
```

These checks use temporary data and mocked provider responses. They do not confirm live OpenRouter availability or API latency.

## 6. Troubleshooting

| Problem | What to do |
| --- | --- |
| Python is not recognised | Install Python 3.10–3.12 with Add Python to PATH, then reopen PowerShell. |
| No Python at a particular path | Recreate the virtual environment using the instructions above. |
| ModuleNotFoundError | Run .\.venv\Scripts\python.exe -m pip install -r requirements.txt. |
| Browser did not open | Open http://127.0.0.1:8000 manually. |
| Port 8000 is already in use | Stop the existing StudyPilot server with Ctrl+C, or use the alternate-port command below. |
| Backend unavailable | Start run.py and open the local URL; do not open static/index.html directly. |
| AI answers are unavailable | Check OPENROUTER_API_KEY, model availability, credits and rate limits. Restart after editing .env. |
| Questions cannot be generated | Wait for upload analysis to finish and use readable material or a broader topic scope. If AI is unavailable, the app can return labelled source-based concept questions. |
| Video upload is slow | Upload a matching VTT/SRT transcript, enable Fast upload, or set WHISPER_MODEL=tiny. |
| PowerShell blocks Activate.ps1 | Use the direct .\.venv\Scripts\python.exe commands in this guide; activation is unnecessary. |

To use a different port:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Then open **http://127.0.0.1:8001** manually.

## 7. Your files

- **.env**: private API and database settings.
- **data/**: local learner data, uploads and generated material; back this up if needed.
- **requirements.txt**: required Python packages.
- **run.py**: starts the local server and opens the browser.

For more details, see [README.md](README.md).
