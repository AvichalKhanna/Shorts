import pyttsx3
from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────
IS_LOCAL = False
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
# ──────────────────────────────────────────────────────────

SCRIPT = """
Welcome back! Today we are covering the top 5 AI tools 
changing content creation in 2026. Let's get into it.
"""

def generate_speech(text: str, is_local: bool = IS_LOCAL, output_file: str = "output.wav"):
    if is_local:
        engine = pyttsx3.init()
        engine.setProperty('rate', 175)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        engine.setProperty('voice', voices[0].id)
        engine.save_to_file(text, output_file)
        engine.runAndWait()
        print(f"Saved to {output_file}")
    else:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.audio.speech.create(
            model="canopylabs/orpheus-v1-english",
            voice="troy",
            input=text,
            response_format="wav"
        )
        response.write_to_file(output_file)
        print(f"Saved to {output_file}")

if __name__ == "__main__":
    generate_speech(SCRIPT)