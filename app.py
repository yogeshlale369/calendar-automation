import streamlit as st
import base64
import json
import re
import os
from datetime import datetime, timedelta
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from pytz import timezone
from urllib.parse import urlparse

# Configuration
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GEMINI_API_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
LOCAL_TIMEZONE = timezone('Asia/Kolkata')

# Google OAuth Configuration
CLIENT_CONFIG = {
    "web": {
        "client_id": st.secrets["GOOGLE_CLIENT_ID"],
        "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
        "project_id": st.secrets["GOOGLE_PROJECT_ID"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": [st.secrets["REDIRECT_URI"]]
    }
}

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks"
]

def get_google_services():
    """Secure OAuth flow for both local and cloud environments"""
    creds = None
    if 'google_creds' in st.session_state:
        creds = Credentials.from_authorized_user_info(st.session_state.google_creds)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = Flow.from_client_config(
                CLIENT_CONFIG,
                scopes=SCOPES,
                redirect_uri=CLIENT_CONFIG['web']['redirect_uris'][0]
            )
            
            # Handle cloud environment
            if os.getenv('STREAMLIT_SERVER'):
                authorization_url, _ = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )
                st.session_state['auth_flow'] = flow  # Save flow in session state
                st.markdown(f"[Click here to authenticate]({authorization_url})")
                return None
                
            # Handle local environment
            else:
                authorization_url, _ = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true'
                )
                print(f"Please go to this URL: {authorization_url}")
                code = input("Enter the authorization code: ")
                flow.fetch_token(code=code)
                creds = flow.credentials

        # Store credentials in session state (encrypted in Streamlit Sharing)
        st.session_state.google_creds = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes
        }

    return {
        "calendar": build("calendar", "v3", credentials=creds),
        "tasks": build("tasks", "v1", credentials=creds)
    }

def handle_oauth_callback():
    """Handle OAuth redirect in cloud environment"""
    if 'code' in st.experimental_get_query_params():
        code = st.experimental_get_query_params()['code'][0]
        if 'auth_flow' in st.session_state:
            flow = st.session_state.auth_flow
            flow.fetch_token(code=code)
            st.session_state.google_creds = {
                'token': flow.credentials.token,
                'refresh_token': flow.credentials.refresh_token,
                'token_uri': flow.credentials.token_uri,
                'client_id': flow.credentials.client_id,
                'client_secret': flow.credentials.client_secret,
                'scopes': flow.credentials.scopes
            }
            # Clear query parameters
            st.experimental_set_query_params()


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
