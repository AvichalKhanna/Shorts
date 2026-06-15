import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES           = ["https://www.googleapis.com/auth/youtube.upload",
                    "https://www.googleapis.com/auth/youtube.readonly"]
CLIENT_SECRETS   = "client_secrets.json"
TOKEN_FILE       = "yt_token.json"

DISCLAIMER = """
⚠️ Disclaimer: I do not own this portfolio. All rights belong to the original creator. This video is purely for educational and review purposes. If you are the owner and would like this video removed, please contact me at karansethi@email.com and I will take it down promptly.

👇 Submit your portfolio for a free review in the comments!
🔔 Subscribe so you never miss a review.

#portfolio #uidesign #uxdesign #webdesign #webdev #shorts #design #portfolioreview
"""


def get_youtube_client():
    creds = None

    # try env var first (for Render)
    if os.getenv("GOOGLE_TOKEN"):
        creds = Credentials.from_authorized_user_info(
            json.loads(os.getenv("GOOGLE_TOKEN")), SCOPES
        )
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # save refreshed token back to env isn't possible, so save to file
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            # this only works locally
            if os.getenv("GOOGLE_CLIENT_SECRETS"):
                with open(CLIENT_SECRETS, "w") as f:
                    f.write(os.getenv("GOOGLE_CLIENT_SECRETS"))
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str       = "Portfolio Review",
    description: str = "",
    tags: list       = ["portfolio", "webdev", "uidesign", "uxdesign", "webdesign", "shorts", "design", "portfolioreview"],
    category_id: str = "28",
) -> dict:
    youtube = get_youtube_client()

    full_description = description + DISCLAIMER if description else DISCLAIMER.strip()

    body = {
        "snippet": {
            "title":       title,
            "description": full_description,
            "tags":        tags,
            "categoryId":  category_id,
        },
        "status": {
            "privacyStatus":           "public",    # ← public now
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    print(f"📤 Uploading {video_path}...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")

    video_id  = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"✅ Uploaded: {video_url}")
    return {"id": video_id, "url": video_url}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "output_portrait.mp4"
    upload_video(path)