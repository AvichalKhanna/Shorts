import subprocess
import json
import os
import sys
import tempfile
from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
OUTPUT_FILE       = "output_portrait.mp4"

OUTPUT_W          = 1080
OUTPUT_H          = 1920

VIDEO_REGION_Y    = 500
VIDEO_REGION_H    = 600

FONT_NAME         = "Bangers"
FONT_DIR          = "Bangers"                  # ← folder with Bangers-Regular.ttf
FONT_SIZE         = 164
OUTLINE_SIZE      = 5
SHADOW_SIZE       = 2
SUBTITLE_MARGIN_V = 550
# ─────────────────────────────────────────────────────────


def seconds_to_ass(t: float) -> str:
    h  = int(t // 3600)
    m  = int((t % 3600) // 60)
    s  = int(t % 60)
    cs = int(round((t % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def fix_path(p: str) -> str:
    return p.replace("\\", "/").replace("C:/", "C\\:/")


def extract_audio(video_path: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        tmp.name
    ], check=True, capture_output=True)
    print("✅ Audio extracted")
    return tmp.name


def transcribe_audio(audio_path: str) -> list:
    client = Groq(api_key=GROQ_API_KEY)
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=("audio.wav", f),
            model="whisper-large-v3",
            response_format="verbose_json",
            timestamp_granularities=["word"]
        )
    words = [{"word": w["word"], "start": w["start"], "end": w["end"]}
             for w in result.words]
    print(f"✅ Transcription done: {len(words)} words")
    return words


def build_ass(words: list) -> str:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUTPUT_W}
PlayResY: {OUTPUT_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{FONT_NAME},{FONT_SIZE},&H00FFE500,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,{OUTLINE_SIZE},{SHADOW_SIZE},2,0,0,{SUBTITLE_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for word in words:
        start = word["start"]
        end   = word["end"]
        text  = word["word"].strip()
        fade  = r"{\fad(80,80)}"
        thump = r"{\fscx130\fscy130\t(0,120,\fscx100\fscy100)}"
        events.append(
            f"Dialogue: 0,{seconds_to_ass(start)},{seconds_to_ass(end)},"
            f"Word,,0,0,0,,{fade}{thump}{text}"
        )

    return header + "\n".join(events) + "\n"


def process_video(video_path: str, audio_path: str, output_file: str = OUTPUT_FILE):
    print("🎙️ Transcribing audio...")
    extracted = extract_audio(audio_path)

    try:
        words = transcribe_audio(extracted)
    finally:
        os.unlink(extracted)

    ass_file = tempfile.NamedTemporaryFile(
        suffix=".ass", delete=False, mode="w", encoding="utf-8"
    )
    ass_file.write(build_ass(words))
    ass_file.close()
    ass_path = fix_path(ass_file.name)
    font_dir  = fix_path(os.path.abspath(FONT_DIR))

    vid_w = OUTPUT_W
    vid_h = VIDEO_REGION_H

    filter_complex = (
        f"[1:v]scale={vid_w}:-2,crop={vid_w}:{vid_h}[website];"
        f"[0:v][website]overlay=x=0:y={VIDEO_REGION_Y}[canvas];"
        f"[canvas]ass='{ass_path}':fontsdir='{font_dir}'[out];"
        f"[2:a]aresample=44100[voice_r];"
        f"[3:a]aresample=44100[music_r];"
        f"[voice_r]volume=1.0[voice];"
        f"[music_r]volume=0.07[music];"
        f"[voice][music]amix=inputs=2:duration=first[audio_out]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x0a0a0a:size={OUTPUT_W}x{OUTPUT_H}:duration=99999:rate=30",
        "-i", video_path,
        "-i", audio_path,
        "-i", "music/background.mp3",
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "[audio_out]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_file
    ]

    print("🎬 Rendering final video...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(ass_file.name)

    if result.returncode != 0:
        print("❌ FFmpeg error:")
        print(result.stderr[-4000:])
        sys.exit(1)

    print(f"✅ Done! Saved to {output_file}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python subtitles.py <video_path> <audio_path> [output_file]")
        sys.exit(1)

    video_path  = sys.argv[1]
    audio_path  = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else OUTPUT_FILE

    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    if not os.path.exists(audio_path):
        print(f"❌ Audio not found: {audio_path}")
        sys.exit(1)

    process_video(video_path, audio_path, output_file)


if __name__ == "__main__":
    main()