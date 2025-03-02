import streamlit as st
import json
import re
import base64
import requests
from datetime import datetime
from pytz import timezone
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# ----- Configuration -----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY") or st.secrets.get("OPENAI_KEY")

if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found. Please set it in .env or secrets.toml.")
    st.stop()

LOCAL_TIMEZONE = timezone('Asia/Kolkata')  # IST
# API Endpoints
GEMINI_TEXT_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
GEMINI_VISION_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def extract_text_from_image(image):
    """Extract text from image using Gemini Vision"""
    try:
        encoded_image = base64.b64encode(image.read()).decode("utf-8")
        prompt = "Extract all handwritten text exactly as written. Preserve line breaks."
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}}
                ]
            }]
        }
        
        response = requests.post(GEMINI_VISION_ENDPOINT, json=payload)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    
    except Exception as e:
        st.error(f"Image processing error: {str(e)}")
        return None

def parse_schedule(text):
    """Parse text into structured schedule data"""
    current_time = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M %Z")
    prompt = f"Current datetime: {current_time} (Asia/Kolkata)\nConvert this to JSON with events/tasks:\n{text}"
    
    try:
        response = requests.post(GEMINI_TEXT_ENDPOINT, json={"contents": [{"parts": [{"text": prompt}]}]})
        response.raise_for_status()
        output_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(re.search(r'```json(.*?)```', output_text, re.DOTALL).group(1))
    
    except Exception as e:
        st.error(f"Parsing error: {str(e)}")
        return {"events": [], "tasks": []}

# ----- Streamlit UI -----
st.title("Smart Schedule Creator 🗓️")

# Input Method Selection
input_method = st.radio("Choose Input Method:", ["Text", "Image Upload", "Voice"])

# Handle Input
input_text = ""
if input_method == "Text":
    input_text = st.text_area("Enter your schedule/tasks:")
    
elif input_method == "Image Upload":
    image = st.file_uploader("Upload Handwritten Notes", type=["jpg", "png", "jpeg"])
    if image:
        with st.spinner("Reading image..."):
            input_text = extract_text_from_image(image)
            if input_text:
                st.text("Extracted Text:")
                st.code(input_text)

elif input_method == "Voice":
    st.warning("Voice input requires microphone access. Click below to start recording.")
    # Using third-party component for voice (requires internet)
    try:
        from streamlit_mic import mic
        audio = mic(just_once=True)
        if audio:
            with st.spinner("Processing voice..."):
                # Convert audio to text using Whisper API
                headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
                response = requests.post("https://api.openai.com/v1/audio/transcriptions", 
                                      headers=headers,
                                      files={"file": audio["bytes"]},
                                      data={"model": "whisper-1"})
                input_text = response.json()["text"]
                st.text("Converted Text:")
                st.code(input_text)
    except:
        st.error("Voice input not available. Please install dependencies.")

# Process Input
if input_text and st.button("Create Schedule"):
    with st.spinner("Analyzing..."):
        schedule = parse_schedule(input_text)
        
        if schedule.get("events"):
            st.success("🎉 Events Created:")
            for event in schedule["events"]:
                st.write(f"- {event['summary']} ({event['start_time']})")
        
        if schedule.get("tasks"):
            st.success("✅ Tasks Added:")
            for task in schedule["tasks"]:
                st.write(f"- {task['title']} (Due: {task.get('due', 'No deadline')})")
