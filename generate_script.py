import subprocess
import json
import time
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def process_portfolio(video_path: str) -> str:
    duration = get_video_duration(video_path)
    print(f"Video duration: {duration:.1f}s")

    print("Uploading video to Gemini...")
    with open(video_path, "rb") as f:
        video_file = client.files.upload(
            file=f,
            config=types.UploadFileConfig(mime_type="video/webm")
        )

    while video_file.state.name == "PROCESSING":
        print("  Processing...")
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise ValueError("Gemini failed to process the video")

    print("Generating script...")

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=types.Content(
            role="user",
            parts=[
                types.Part.from_uri(file_uri=video_file.uri, mime_type="video/webm"),
                types.Part.from_text(text=f"""You are a famous YouTube Shorts creator who reviews developer portfolios. You have just watched this portfolio recording which is {duration:.1f} seconds long.

Write a voiceover script for a YouTube Short. Follow these rules exactly:

- Total script must be speakable in 30 to 45 seconds, roughly 80 to 120 words
- No symbols except commas, periods, and question marks
- No hashtags, no emojis, no dashes, no bullet points
- No stage directions, no timestamps, just raw spoken words
- Short punchy sentences, maximum 8 words each
- Sound like a real hype person not a robot

Structure it like this:
1. Hook, first 2 seconds, one shocking or spicy line about the portfolio
2. Quick highs, one or two things that actually impressed you, be specific to what you saw
3. Quick lows, one or two things that need work, be brutally honest
4. Rating reveal, build up then drop the score out of 10
5. CTA, tell viewers to comment their portfolio link below to get reviewed next and subscribe so they never miss a review

Output the script and nothing else.""")
            ]
        )
    )

    script = response.text.strip()

    print("\n--- SCRIPT ---")
    print(script)
    print(f"\nWord count: {len(script.split())} words")
    print("--------------")

    return script


if __name__ == "__main__":
    import sys
    video = sys.argv[1] if len(sys.argv) > 1 else "recordings/p-rism-frontend-vercel-app_desktop.webm"
    process_portfolio(video)