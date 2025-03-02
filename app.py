# app.py
import streamlit as st
import base64
import json
import re
import os
from datetime import datetime, timedelta
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pytz import timezone

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY") or st.secrets.get("OPENAI_KEY")

GEMINI_API_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={os.getenv('GEMINI_API_KEY')}"
GOOGLE_CREDENTIALS_FILE = "credentials3.json"
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/tasks"]
TOKEN_FILE = "token.json"
LOCAL_TIMEZONE = timezone('Asia/Kolkata')

def parse_input(text=None, image_bytes=None):
    current_time = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")
    
    prompt = (
        f"Current datetime: {current_time} ({LOCAL_TIMEZONE.zone})\n"
        "Analyze this input and return JSON with separate 'events' and 'tasks' lists.\n"
        "For events include: summary, start_time (ISO8601 with timezone), end_time (ISO8601 with timezone), description.\n"
        "For tasks include: title, due (ISO8601 with timezone), notes.\n"
        "Rules:\n"
        "1. Convert relative times to absolute datetimes\n"
        "2. Assume 1-hour duration for events without end_time\n"
        "3. Use timezone: Asia/Kolkata (IST)\n"
        "4. Format response as: ```json{...}```\n"
    )

    parts = [{"text": prompt}]
    
    if text:
        parts.append({"text": f"Input text: {text}"})
    if image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode()
            }
        })

    payload = {"contents": [{"parts": parts}]}

    try:
        response = requests.post(GEMINI_API_ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        output_text = result["candidates"][0]["content"]["parts"][0]["text"]
        json_match = re.search(r'```json\s*(.*?)\s*```', output_text, re.DOTALL)
        return json.loads(json_match.group(1).strip()) if json_match else {"events": [], "tasks": []}
    
    except Exception as e:
        st.error(f"Error processing Gemini response: {str(e)}")
        return {"events": [], "tasks": []}

def get_google_services():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return {
        "calendar": build("calendar", "v3", credentials=creds),
        "tasks": build("tasks", "v1", credentials=creds)
    }

# Streamlit UI
st.title("Schedule Planner 🗓️")

input_text = st.text_area("Describe your schedule/tasks:", height=150)
uploaded_file = st.file_uploader("Or upload an image:", type=["jpg", "png", "jpeg"])

if st.button("Process Schedule"):
    if not input_text and not uploaded_file:
        st.warning("Please enter text or upload an image")
        st.stop()
    
    with st.spinner("Analyzing input..."):
        image_bytes = uploaded_file.read() if uploaded_file else None
        schedule = parse_input(text=input_text, image_bytes=image_bytes)
    
    if not schedule.get("events") and not schedule.get("tasks"):
        st.error("Failed to parse any schedule items")
        st.stop()
    
    try:
        services = get_google_services()
        st.success("Connected to Google services ✅")
    except Exception as e:
        st.error(f"Google connection failed: {str(e)}")
        st.stop()
    
    results = []
    
    if schedule.get("events"):
        st.subheader("Calendar Events")
        for event in schedule["events"]:
            try:
                start = datetime.fromisoformat(event["start_time"])
                end = datetime.fromisoformat(event.get("end_time") or (start + timedelta(hours=1)))
                
                created_event = services["calendar"].events().insert(
                    calendarId="primary",
                    body={
                        "summary": event["summary"],
                        "description": event.get("description", ""),
                        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
                        "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"}
                    }
                ).execute()
                
                results.append(f"✅ Event created: {created_event['summary']}")
                st.success(f"**{created_event['summary']}**\n"
                          f"Start: {start.strftime('%d %b %Y %H:%M')}\n"
                          f"End: {end.strftime('%d %b %Y %H:%M')}")
            except Exception as e:
                results.append(f"❌ Event failed: {str(e)}")
                st.error(f"Failed to create event: {str(e)}")
    
    if schedule.get("tasks"):
        st.subheader("Google Tasks")
        for task in schedule["tasks"]:
            try:
                created_task = services["tasks"].tasks().insert(
                    tasklist="@default",
                    body={
                        "title": task["title"],
                        "notes": task.get("notes", ""),
                        "due": task.get("due")
                    }
                ).execute()
                
                results.append(f"✅ Task created: {created_task['title']}")
                st.success(f"**{created_task['title']}**\n"
                          f"Due: {datetime.fromisoformat(task['due']).strftime('%d %b %Y %H:%M') if task.get('due') else 'No due date'}")
            except Exception as e:
                results.append(f"❌ Task failed: {str(e)}")
                st.error(f"Failed to create task: {str(e)}")
    
    st.balloons()
    st.success("Processing complete!")

# Add footer
st.markdown("---")
st.markdown("_Built with Streamlit & Google Gemini_")
