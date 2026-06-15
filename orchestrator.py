import asyncio
import subprocess
import sys
import os
import re
import time
import random
from pathlib import Path

from portfolio import get_portfolio, Portfolio
from recorder import record_portfolio
from generate_script import process_portfolio as generate_script
from generate_speech import generate_speech
from subtitles import process_video
from verify_portfolio import verify_portfolio

OUTPUT_DIR  = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
MAX_RETRIES = 5


def clean_script(script: str) -> str:
    script = re.sub(r'[-–—*#\[\]()]', '', script)
    script = re.sub(r'\*\*.*?\*\*', '', script)
    script = re.sub(r' +', ' ', script)
    script = re.sub(r'\n+', '\n', script)
    return script.strip()


async def get_valid_portfolio(portfolio_url: str = None) -> Portfolio:
    """Keep pulling portfolios until one passes verification."""
    if portfolio_url:
        portfolio = Portfolio(url=portfolio_url, source="cli")
        result = verify_portfolio(portfolio)
        if not result.is_valid:
            print(f"❌ Provided URL failed verification: {result.reason}")
            print("⚠️  Continuing anyway since URL was manually provided...")
        return portfolio

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n📦 Fetching portfolio from queue (attempt {attempt}/{MAX_RETRIES})...")
        portfolio = get_portfolio()
        print(f"🌐 Got: {portfolio.url}")

        result = verify_portfolio(portfolio)
        if result.is_valid:
            print(f"✅ Portfolio passed verification")
            return portfolio

        print(f"❌ Failed verification: {result.reason} — trying next...")

    raise RuntimeError(f"Could not find a valid portfolio after {MAX_RETRIES} attempts")


async def run(portfolio_url: str = None):

    # ── Step 1: Get a verified portfolio ─────────────────────────────────────
    portfolio = await get_valid_portfolio(portfolio_url)
    print(f"\n🌐 Portfolio: {portfolio.url}")
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', portfolio.url.split("//")[-1]).strip('-').lower()
    import time
    time.sleep(10000000)
    # ── Step 2: Record the website ────────────────────────────────────────────
    print("\n🎬 Recording website...")
    video_path = await record_portfolio(portfolio, phone=False)
    print(f"✅ Video: {video_path}")

    # ── Step 3: Generate script via Gemini ───────────────────────────────────
    print("\n✍️  Generating script...")
    raw_script = generate_script(str(video_path))
    script     = clean_script(raw_script)
    print(f"\n📝 Cleaned script:\n{script}\n")

    script_path = OUTPUT_DIR / f"{slug}_script.txt"
    script_path.write_text(script, encoding="utf-8")
    print(f"✅ Script saved: {script_path}")

    # ── Step 4: Generate speech ───────────────────────────────────────────────
    print("\n🔊 Generating voiceover...")
    audio_path = str(OUTPUT_DIR / f"{slug}_audio.mp3")
    generate_speech(script, output_file=audio_path)
    print(f"✅ Audio saved: {audio_path}")

    # ── Step 5: Burn subtitles + merge into final video ───────────────────────
    print("\n🎞️  Rendering final video with subtitles...")
    final_path = str(OUTPUT_DIR / f"{slug}_final.mp4")
    process_video(str(video_path), audio_path, output_file=final_path)
    print(f"\n✅ Final video: {final_path}")

    return final_path

if __name__ == "__main__":
    async def main():
        while True:
            await run()
            
            wait = (4 * 60 * 60) + random.randint(0, 30 * 60)
            mins = wait // 60
            print(f"⏳ Next run in {mins} minutes...")
            await asyncio.sleep(wait)
    
    asyncio.run(main())