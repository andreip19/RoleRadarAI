import os

from pathlib import Path
from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[1]

load_dotenv(ROOT / ".env")

api_key = os.getenv("GEMINI_API_KEY")
model = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

if not api_key:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)

response = client.interactions.create(
    model=model,
    input=(
        "You are testing the RoleRadar AI integration. "
        "Reply with exactly: "
        "RoleRadar AI Gemini integration is working."
    ),
)

if not response.output_text:
    raise RuntimeError("Gemini returned an empty response.")

print("GEMINI API SUCCESS")
print("MODEL:", model)
print("RESPONSE:", response.output_text)
