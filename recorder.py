import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, BrowserContext

from portfolio import get_portfolio, Portfolio


RECORDINGS_DIR = Path("recordings")
RECORDINGS_DIR.mkdir(exist_ok=True)

# ── Phone profile — vertical 390×844 (iPhone 14 logical pixels) ──────────────
PHONE_PROFILE = {
    "viewport":          {"width": 390, "height": 844},
    "video_size":        {"width": 390, "height": 844},
    "user_agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "is_mobile":         True,
    "has_touch":         True,
    "device_scale_factor": 1,
}

# ── Desktop profile ────────────────────────────────────────────────────────────
DESKTOP_PROFILE = {
    "viewport":          {"width": 1440, "height": 900},
    "video_size":        {"width": 1440, "height": 900},
    "user_agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "is_mobile":         False,
    "has_touch":         False,
    "device_scale_factor": 1,
}


def _url_to_filename(url: str) -> str:
    host = urlparse(url).netloc or url
    return re.sub(r'[^a-zA-Z0-9]+', '-', host).strip('-').lower()


# ─────────────────────────────────────────────
# PAGE-READY WAIT
# ─────────────────────────────────────────────

async def _wait_for_page_ready(page, timeout: int = 25_000) -> None:
    """Block until the page has real painted content, not just DOM-ready."""
    deadline = asyncio.get_event_loop().time() + timeout / 1000

    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass

    while asyncio.get_event_loop().time() < deadline:
        painted = await page.evaluate("""() => {
            const b = document.body;
            if (!b) return false;
            return b.getBoundingClientRect().height > 100;
        }""")
        if painted:
            break
        await page.wait_for_timeout(300)

    # Extra room for CSS animations, web fonts, lazy hero images
    await page.wait_for_timeout(2500)


# ─────────────────────────────────────────────
# NATURAL SCROLL  (smoothstep ease-in-out)
# ─────────────────────────────────────────────

async def _natural_scroll(page, total_height: int) -> None:
    steps = int(((total_height / 900) * 2) + 1)
    chunk = total_height / steps
    for i in range(steps):
        # ease-in-out: slow start, fast middle, slow end
        t = i / (steps - 1)
        ease = t * t * (3 - 2 * t)  # smoothstep
        target = int(ease * total_height)
        await page.evaluate(f"window.scrollTo(0, {target})")

        # pause longer at start and end, shorter in middle
        if i < 2 or i > steps - 3:
            await page.wait_for_timeout(2500)
        else:
            await page.wait_for_timeout(2000)


# ─────────────────────────────────────────────
# MAIN RECORDER
# ─────────────────────────────────────────────

async def record_portfolio(
    portfolio: Portfolio,
    *,
    phone: bool = False,          # ← default is DESKTOP
    linger_top_ms: int = 3300,
    linger_bottom_ms: int = 4000,
    output_dir: Path = RECORDINGS_DIR,
) -> Path:
    """
    Record a portfolio website as a .webm video.
    phone=False → 1440×900 desktop layout (default)
    phone=True  → 390×844 vertical iPhone layout
    """
    profile     = PHONE_PROFILE if phone else DESKTOP_PROFILE
    suffix      = "_phone" if phone else "_desktop"
    filename    = _url_to_filename(portfolio.url) + suffix + ".webm"
    output_path = output_dir / filename

    vp = profile["viewport"]
    print(f"🎬 Recording ({'📱 phone' if phone else '🖥  desktop'}): {portfolio.url}")
    print(f"   Viewport: {vp['width']}×{vp['height']}  →  {output_path}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        context: BrowserContext = await browser.new_context(
            viewport=profile["viewport"],
            record_video_dir=str(output_dir),
            record_video_size=profile["video_size"],
            user_agent=profile["user_agent"],
            is_mobile=profile["is_mobile"],
            has_touch=profile["has_touch"],
            device_scale_factor=profile["device_scale_factor"],
        )

        page = await context.new_page()

        try:
            await page.goto(portfolio.url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            print(f"  ⚠  Navigation warning: {e} — continuing anyway")

        print("   Waiting for page to render…")
        await _wait_for_page_ready(page)
        print("   ✓ Page ready")

        # Sit at top — viewer sees the hero
        await page.wait_for_timeout(linger_top_ms)

        # ── Measure scrollable distance ──────────────────────────────────────
        total_height: int = await page.evaluate(
            "Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        viewport_height: int = profile["viewport"]["height"]
        scrollable: int = max(0, total_height - viewport_height)

        # ── Scroll only if there's something to scroll ───────────────────────
        if scrollable > 50:
            await _natural_scroll(page, scrollable)
        else:
            print("   ⚠  Page fits in viewport, no scroll needed")
            await page.wait_for_timeout(2000)

        await page.wait_for_timeout(linger_bottom_ms)

        await context.close()
        await browser.close()

    # Rename Playwright's UUID file to our readable slug
    recorded = sorted(output_dir.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    if recorded:
        latest = recorded[-1]
        if latest != output_path:
            latest.rename(output_path)

    print(f"  ✅ Saved → {output_path}")
    return output_path


# ─────────────────────────────────────────────
# CONVENIENCE WRAPPER
# ─────────────────────────────────────────────

async def record_next_portfolio(**kwargs) -> tuple[Portfolio, Path]:
    """Pop the next portfolio from the queue and record it."""
    portfolio = get_portfolio()
    path = await record_portfolio(portfolio, **kwargs)
    return portfolio, path


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    async def main():
        # python portfolio_recorder.py                          → queue, desktop
        # python portfolio_recorder.py https://example.com     → specific, desktop
        # python portfolio_recorder.py https://x.com phone     → specific, phone
        phone = len(sys.argv) > 2 and sys.argv[2] == "phone"

        if len(sys.argv) > 1:
            p = Portfolio(url=sys.argv[1], source="cli")
            await record_portfolio(p, phone=phone)
        else:
            portfolio, path = await record_next_portfolio(phone=phone)
            print(f"\n📋 Portfolio : {portfolio.name or portfolio.url}")
            print(f"   Title     : {portfolio.title}")
            print(f"   Video     : {path}")

    asyncio.run(main())