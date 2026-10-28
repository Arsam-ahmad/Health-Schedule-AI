# 🏥 HealthSchedule AI

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Google Cloud Run](https://img.shields.io/badge/Google_Cloud_Run-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/run)
[![Anthropic Claude](https://img.shields.io/badge/Claude_Sonnet_5.5-D97757?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![Firestore](https://img.shields.io/badge/Cloud_Firestore-FFCA28?logo=firebase&logoColor=black)](https://cloud.google.com/firestore)

**HealthSchedule AI** is a serverless, voice-enabled AI medical receptionist ("Sarah") built with **FastAPI**, **Anthropic Claude**, and **Google Cloud Platform (GCP)**. Designed for HealthSchedule Medical Center (supporting General Practice and Orthopedics), the application converses naturally with patients to gather scheduling details, books appointments directly onto **Google Calendar**, persists chat histories and appointment records in **Cloud Firestore**, synthesizes spoken responses via **Cloud Text-to-Speech**, and archives voice audio to **Cloud Storage**.

---

## ✨ Key Features

- **Conversational AI Receptionist:** Powered by Anthropic's Claude (`claude-sonnet-5-5`), following strict clinical scheduling rules and safety guardrails (never providing medical advice and directing emergencies to 911).
- **Automated Google Calendar Booking:** Extracts structured booking JSON directly from the LLM response stream and creates calendar events with custom reminders via the Google Calendar API.
- **Natural Voice Synthesis & Archiving:** Converts assistant responses into lifelike speech (`en-US-Studio-O`) using Google Cloud Text-to-Speech and archives `.mp3` recordings per session in Google Cloud Storage.
- **Real-Time Persistence:** Logs multi-turn conversation histories (`conversations` collection) and confirmed appointment metadata (`appointments` collection) in Cloud Firestore.
- **Zero-Trust Secret & Identity Management:** Uses Google Cloud Secret Manager for API credentials and a dedicated least-privilege IAM Service Account on Cloud Run.

---

## 🏗️ Architecture & Tech Stack

```text
┌────────────────────┐
│  Patient Browser   │  (Web UI: Chat + Audio Playback)
└─────────┬──────────┘
          │ HTTPS (POST /api/chat)
          ▼
┌──────────────────────────────────────────────────────────────┐
│                Google Cloud Run (FastAPI)                    │
│  Service Account: healthschedule-sa                          │
└─┬────────────┬──────────────┬───────────────┬──────────────┬─┘
  │            │              │               │              │
  ▼            ▼              ▼               ▼              ▼
┌──────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────────┐
│  Secret  │ │ Anthropic  │ │   Google     │ │   Cloud    │ │ Cloud TTS &  │
│ Manager  │ │ Claude API │ │ Calendar API │ │ Firestore  │ │Cloud Storage │
└──────────┘ └────────────┘ └──────────────┘ └────────────┘ └──────────────┘
```

### GCP Services Utilized
* **Compute & CI/CD:** Cloud Run, Cloud Build, Artifact Registry
* **Storage & Databases:** Cloud Firestore (Native mode), Cloud Storage
* **AI & Machine Learning:** Cloud Text-to-Speech, Anthropic Claude API
* **Security & Observability:** Identity and Access Management (IAM), Secret Manager, Cloud Logging, Cloud Monitoring

---

## 📂 Project Structure

```text
.
├── main.py              # FastAPI application, Claude agent, Calendar, Firestore, TTS & GCS logic
├── requirements.txt     # Python package dependencies
├── Dockerfile           # Container image definition for Cloud Run
├── templates/
│   └── index.html       # Frontend chat and audio interface
├── static/              # Static CSS/JS assets
└── README.md            # Repository documentation
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Google Cloud SDK (`gcloud`)
- A Google Cloud Project (`healthschedule-ai`) with billing enabled
- An Anthropic API Key
- A Google Calendar shared with your Cloud Run service account

---

## ☁️ Google Cloud Setup & Deployment

Run the following commands to provision the cloud infrastructure and deploy the service from scratch.

### 1. Authenticate & Configure GCP Project

```bash
# Install Google Cloud CLI (macOS)
brew install --cask google-cloud-sdk

# Authenticate and set project defaults
gcloud auth login
gcloud config set project healthschedule-ai
gcloud config set run/region us-east4
```

### 2. Enable Required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  texttospeech.googleapis.com \
  secretmanager.googleapis.com \
  calendar-json.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project=healthschedule-ai
```

### 3. Configure Service Account & IAM Permissions

Create a dedicated service account and bind least-privilege IAM roles:

```bash
# Create service account
gcloud iam service-accounts create healthschedule-sa \
  --display-name="HealthSchedule AI Service Account" \
  --project=healthschedule-ai

# Grant Firestore access
gcloud projects add-iam-policy-binding healthschedule-ai \
  --member="serviceAccount:healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Grant Cloud Storage access
gcloud projects add-iam-policy-binding healthschedule-ai \
  --member="serviceAccount:healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com" \
  --role="roles/storage.objectUser"

# Grant Secret Manager access
gcloud projects add-iam-policy-binding healthschedule-ai \
  --member="serviceAccount:healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Grant Artifact Registry writer access
gcloud projects add-iam-policy-binding healthschedule-ai \
  --member="serviceAccount:healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

### 4. Store Anthropic API Key in Secret Manager

```bash
echo -n "YOUR_ANTHROPIC_API_KEY" | gcloud secrets create claude-api-key \
  --data-file=- \
  --replication-policy="automatic" \
  --project=healthschedule-ai
```

### 5. Provision Firestore & Cloud Storage

```bash
# Create Firestore Native database
gcloud firestore databases create \
  --database=healthscheduleai \
  --location=us-east4 \
  --type=firestore-native \
  --project=healthschedule-ai

# Create Cloud Storage bucket for audio archives
gcloud storage buckets create gs://healthschedule-ai-audio-archive \
  --location=us-east4 \
  --project=healthschedule-ai
```

### 6. Authorize Google Calendar Access

1. Open Google Calendar and navigate to your target clinic calendar's **Settings and sharing**.
2. Under **Share with specific people or groups**, add `healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com` with **Make changes to events** permissions.
3. Copy the **Calendar ID** from the **Integrate calendar** section and set `calendar_id` in `main.py`.

### 7. Deploy to Cloud Run

```bash
gcloud run deploy healthschedule-ai \
  --source . \
  --region=us-east4 \
  --allow-unauthenticated \
  --service-account=healthschedule-sa@healthschedule-ai.iam.gserviceaccount.com \
  --set-env-vars=GOOGLE_CLOUD_PROJECT=healthschedule-ai \
  --memory=512Mi \
  --timeout=60 \
  --project=healthschedule-ai
```

---

## 💻 Local Development

To run the application locally for testing:

```bash
# 1. Authenticate Application Default Credentials (with Calendar scope)
gcloud auth application-default login \
  --scopes=[https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/calendar](https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/calendar)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Export project environment variable and start server
export GOOGLE_CLOUD_PROJECT=healthschedule-ai
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` in your browser.

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Renders the patient web interface (`index.html`). |
| `POST` | `/api/chat` | Processes patient messages, invokes Claude, triggers automated calendar/Firestore booking on confirmation, synthesizes TTS audio, and archives `.mp3` to Cloud Storage. |
| `POST` | `/api/book` | Direct booking endpoint for creating a Google Calendar event and `appointments` document in Firestore. |

---

## 🧠 Engineering Takeaways & Troubleshooting

- **Least-Privilege IAM Bindings:** Cloud Run service accounts require explicit IAM role bindings (`roles/datastore.user`, `roles/storage.objectUser`, `roles/secretmanager.secretAccessor`) for every downstream GCP dependency to prevent runtime `403 PermissionDenied` errors.
- **Cloud IAM vs. Google Workspace Permissions:** Project-level IAM roles do not grant access to Google Calendar. The target calendar must be explicitly shared with the service account email address to avoid `404 Not Found` errors.
- **Service Account Domain-Wide Delegation Constraints:** Standalone service accounts cannot send email invitations (`sendUpdates="all"`) or include the `attendees` property without Workspace Domain-Wide Delegation. Setting `sendUpdates="none"` and recording patient emails in the event description and Firestore bypasses `403 forbiddenForServiceAccounts` restrictions.
- **Resilient LLM Output Parsing:** Extracting structured JSON via flexible regular expressions and stripping code blocks prior to Text-to-Speech synthesis prevents formatting variations from breaking automated bookings or being read aloud to patients.

---

## 🔮 Roadmap & Future Improvements

- [ ] **Chat Agent Input & Output Validation:** Implement validation of the input and the output of the chat agent using Pydantic schemas and guardrails to prevent prompt injection and verify dates, times, and email formats prior to API execution.
- [ ] **Load Balancer Integration:** Deploy a Google Cloud External Application Load Balancer with Cloud Armor in front of Cloud Run for custom domains, managed SSL certificates, DDoS protection, and multi-region high availability.
- [ ] **Live Calendar Availability (`freebusy`):** Query the Google Calendar `freebusy` endpoint before confirming slots to prevent double-booking Dr. Smith or Dr. Patel.
- [ ] **Automated Email/SMS Notifications:** Integrate SendGrid or Twilio to send external booking confirmations and reminders to patients.
- [ ] **Stateless Session Hydration:** Read and write active conversation context directly from Firestore rather than an in-memory dictionary so sessions persist seamlessly across container scaling events.

---

## 👤 Author

**Arsam Ahmad**  
*Advanced Cloud Computing — Fall 2026*
