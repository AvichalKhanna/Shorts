import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional
import re
import time
from playwright.sync_api import sync_playwright


# ─── CONFIG ───────────────────────────────────────────────
MIN_PAGE_HEIGHT = 3000       # minimum valid page height in pixels
REQUEST_TIMEOUT = 10         # seconds
# ──────────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    url: str
    is_valid: bool
    reachable: bool
    page_height: Optional[int]
    is_english: bool
    is_scrollable: bool
    status_code: Optional[int]
    reason: str


def _check_reachability(url: str) -> tuple[bool, Optional[int]]:
    """Check if the URL is reachable and returns a 200 status."""
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True
        )
        return r.status_code == 200, r.status_code
    except requests.exceptions.ConnectionError:
        return False, None
    except requests.exceptions.Timeout:
        return False, None
    except Exception:
        return False, None


def _check_english(url: str) -> bool:
    """Check if the page content is primarily in English."""
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        soup = BeautifulSoup(r.text, "html.parser")

        # Check html lang attribute first
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            lang = html_tag["lang"].lower()
            if lang.startswith("en"):
                return True
            elif lang and not lang.startswith("en"):
                return False

        # Check meta content-language
        meta_lang = soup.find("meta", attrs={"http-equiv": re.compile("content-language", re.I)})
        if meta_lang and meta_lang.get("content"):
            return meta_lang["content"].lower().startswith("en")

        # Fallback: count common English words in visible text
        for tag in soup(["script", "style", "meta", "link"]):
            tag.decompose()
        text = soup.get_text().lower()
        english_words = [
            "the", "and", "is", "in", "it", "of", "to", "a", "that",
            "this", "with", "for", "about", "me", "my", "i", "project",
            "work", "contact", "skills", "experience", "portfolio"
        ]
        word_count = sum(text.count(f" {w} ") for w in english_words)
        return word_count >= 10

    except Exception:
        return False


def _check_height_and_scroll(url: str) -> tuple[Optional[int], bool]:
    """Use Playwright to get actual rendered page height and check scrollability."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, timeout=15000, wait_until="networkidle")
            time.sleep(1.5)  # let any JS animations settle

            # Get full scroll height
            height = page.evaluate("document.documentElement.scrollHeight")

            # Check if page is scrollable
            is_scrollable = page.evaluate(
                "document.documentElement.scrollHeight > window.innerHeight"
            )

            browser.close()
            return height, is_scrollable

    except Exception as e:
        print(f"  ⚠ Playwright error: {e}")
        return None, False

def verify_portfolio(portfolio) -> VerificationResult:
    url = portfolio.url
    print(f"\n🔍 Verifying: {url}")

    print("  → Checking reachability...")
    reachable, status_code = _check_reachability(url)

    if not reachable:
        print(f"  ❌ Not reachable (status: {status_code})")
        return VerificationResult(
            url=url,
            is_valid=False,
            reachable=False,
            page_height=None,
            is_english=False,
            is_scrollable=False,
            status_code=status_code,
            reason=f"Site not reachable (HTTP {status_code})"
        )

    print(f"  ✅ Reachable (HTTP {status_code})")
    return VerificationResult(
        url=url,
        is_valid=True,
        reachable=True,
        page_height=None,
        is_english=True,
        is_scrollable=True,
        status_code=status_code,
        reason="Reachability check passed"
    )


# ─── QUICK TEST ───────────────────────────────────────────
if __name__ == "__main__":
    # Simulate a portfolio object for testing
    from dataclasses import dataclass
    from typing import Optional

    @dataclass
    class Portfolio:
        url: str
        name: Optional[str] = None
        title: Optional[str] = None
        source: Optional[str] = None
        description: Optional[str] = None

    test = Portfolio(url="https://brittanychiang.com")
    result = verify_portfolio(test)

    print("\n─── Result ───────────────────────────────")
    print(f"  URL        : {result.url}")
    print(f"  Valid      : {result.is_valid}")
    print(f"  Reachable  : {result.reachable}")
    print(f"  Height     : {result.page_height}px")
    print(f"  English    : {result.is_english}")
    print(f"  Scrollable : {result.is_scrollable}")
    print(f"  Reason     : {result.reason}")