import re, os, uuid, json, datetime, base64
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from anthropic import Anthropic
from google.cloud import texttospeech, firestore, secretmanager, storage
import google.auth
from googleapiclient.discovery import build

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Clients ---
db = firestore.Client(database="healthscheduleai")
tts_client = texttospeech.TextToSpeechClient()
storage_client = storage.Client()

# --- Load secrets ---
def get_secret(secret_id: str) -> str:
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "healthschedule-ai")
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    resp = client.access_secret_version(request={"name": name})
    return resp.payload.data.decode("utf-8")

claude_client = Anthropic(api_key=get_secret("claude-api-key"))

# --- System prompt ---
SYSTEM_PROMPT = """You are Sarah, a friendly and professional medical 
receptionist at HealthSchedule Medical Center. You work for 
Dr. Smith (General Practice) and Dr. Patel (Orthopedics).

Your job is to help patients schedule appointments. Follow these rules:

1. GREETING: Always start by warmly greeting the patient and asking 
   how you can help them today.

2. GATHER INFORMATION: You need four pieces of information before 
   booking. Ask for them conversationally, not all at once:
   - Patient's full name
   - Patient's email address
   - Preferred date and time (office hours are Mon-Fri 9am-5pm)
   - Reason for visit (checkup, follow-up, pain/injury, referral, other)

3. APPOINTMENT TYPES:
   - General checkup: 30 minutes with Dr. Smith
   - Follow-up visit: 20 minutes with the original doctor
   - Pain or injury: 45 minutes with Dr. Patel (orthopedics)
   - Specialist referral: 30 minutes, you will connect them

4. CONFIRM before booking: Repeat all details back to the patient 
   and ask "Shall I go ahead and book this for you?"

5. WHEN BOOKING IS CONFIRMED: Output a JSON block in this exact format:
   \x60\x60\x60json
   {"action": "book_appointment", "name": "...", "email": "...", "date": "YYYY-MM-DD", "time": "HH:MM", "reason": "..."}
   \x60\x60\x60
   Follow the JSON with a friendly confirmation message.

6. BOUNDARIES:
   - Never give medical advice, diagnoses, or medication recommendations.
   - If asked medical questions, say: "I'm not qualified to give medical advice, but I can schedule you with one of our doctors who can help."
   - If a patient describes an emergency, tell them to call 911 or go to the nearest emergency room immediately.
   - Stay within office hours (Mon-Fri 9am-5pm ET). If they request a weekend or evening, politely explain and offer alternatives.

7. TONE: Warm, professional, patient. Use short sentences suitable for voice conversation. Avoid jargon."""

# --- In-memory session store (Firestore backs it up) ---
sessions: dict[str, list] = {}

def get_calendar_service():
    scope_url = "https://" + "www.googleapis.com/auth/calendar"
    creds, _ = google.auth.default(scopes=[scope_url])
    return build("calendar", "v3", credentials=creds)


def create_calendar_and_firestore_booking(body: dict) -> dict:
    """Books the appointment on Google Calendar and logs it to Firestore."""
    patient_name = body["name"]
    patient_email = body["email"]
    date_str = body["date"]       # e.g. "2026-11-15"
    time_str = body["time"]       # e.g. "10:00"
    reason = body["reason"]

    # Build the calendar event
    start = f"{date_str}T{time_str}:00"
    end_hour = int(time_str.split(":")[0]) + 1
    end = f"{date_str}T{end_hour:02d}:{time_str.split(':')[1]}:00"

    # 'attendees' is omitted because Google Calendar blocks standalone service
    # accounts from inviting attendees without Domain-Wide Delegation.
    event = {
        "summary": f"Appointment: {patient_name} - {reason}",
        "description": (
            f"Patient: {patient_name}\n"
            f"Email: {patient_email}\n"
            f"Reason: {reason}\n"
            f"Booked via HealthSchedule AI"
        ),
        "start": {"dateTime": start, "timeZone": "America/New_York"},
        "end": {"dateTime": end, "timeZone": "America/New_York"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 30}
            ]
        }
    }

    service = get_calendar_service()
    calendar_id = "b5ce4b906d976b394efca63703071057feaa962f9b008fa3d798804390ee03a0@group.calendar.google.com"
    created = service.events().insert(
        calendarId=calendar_id, body=event, sendUpdates="none"
    ).execute()

    # Save to Firestore
    db.collection("appointments").add({
        "patient_name": patient_name,
        "patient_email": patient_email,
        "date": date_str,
        "time": time_str,
        "reason": reason,
        "calendar_event_id": created["id"],
        "created_at": datetime.datetime.now()
    })

    print(f"Successfully booked appointment {created['id']} for {patient_name}")
    return created

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_msg = body["message"]
    session_id = body.get("session_id", str(uuid.uuid4()))

    # Get or create conversation history
    if session_id not in sessions:
        sessions[session_id] = []
    sessions[session_id].append({"role": "user", "content": user_msg})

    # Call Claude
    response = claude_client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=sessions[session_id]
    )
    assistant_msg = next(block.text for block in response.content if block.type == "text")

    # Match booking JSON whether fenced with backticks or inline without newlines
    booking_result = None
    json_pattern = r"(?:\x60{3}(?:json)?\s*)?(\{\s*\"action\"\s*:\s*\"book_appointment\".*?\})(?:\s*\x60{3})?"
    json_match = re.search(json_pattern, assistant_msg, re.DOTALL)

    if json_match:
        try:
            booking_data = json.loads(json_match.group(1))
            if booking_data.get("action") == "book_appointment":
                created_event = create_calendar_and_firestore_booking(booking_data)
                booking_result = {
                    "booked": True,
                    "event_link": created_event.get("htmlLink")
                }
        except Exception as e:
            print(f"Error executing automatic booking: {e}")

    # Strip the JSON block so the patient doesn't see or hear raw code
    clean_assistant_msg = re.sub(json_pattern, "", assistant_msg, flags=re.DOTALL).strip()
    if not clean_assistant_msg:
        clean_assistant_msg = "Your appointment has been booked!"

    # Save cleaned message to session and log to Firestore
    sessions[session_id].append({"role": "assistant", "content": clean_assistant_msg})
    try:
        db.collection("conversations").document(session_id).set({
            "messages": sessions[session_id],
            "updated_at": datetime.datetime.now()
        })
    except Exception as e:
        print(f"Firestore conversation log failed: {e}")

    # Generate audio via Cloud TTS using the clean message
    audio_base64 = synthesize_speech(clean_assistant_msg, session_id)

    return JSONResponse({
        "response": clean_assistant_msg,
        "audio": audio_base64,
        "session_id": session_id,
        "booking": booking_result
    })

def synthesize_speech(text: str, session_id: str) -> str:
    """Convert text to speech and save a backup to Cloud Storage."""
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Studio-O",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    response = tts_client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    # --- Upload to Cloud Storage ---
    bucket_name = "healthschedule-ai-audio-archive" 
    try:
        bucket = storage_client.bucket(bucket_name)
        filename = f"{session_id}_{int(datetime.datetime.now().timestamp())}.mp3"
        blob = bucket.blob(filename)
        blob.upload_from_string(response.audio_content, content_type="audio/mpeg")
    except Exception as e:
        print(f"Cloud Storage upload failed: {e}")

    return base64.b64encode(response.audio_content).decode("utf-8")

@app.post("/api/book")
async def book_appointment(request: Request):
    """Fallback endpoint if the frontend explicitly calls /api/book."""
    body = await request.json()
    created = create_calendar_and_firestore_booking(body)
    return JSONResponse({
        "success": True,
        "event_link": created.get("htmlLink")
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
