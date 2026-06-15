import requests
from bs4 import BeautifulSoup
import json
import time
import re
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path
from supabase import create_client
import os
from dotenv import load_dotenv
import random 

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

QUEUE_FILE = Path("portfolios.json")

HANDPICKED_PORTFOLIOS = [
    # Developers / Engineers
    "https://brittanychiang.com",
    "https://paco.me",
    "https://leerob.io",
    "https://joshwcomeau.com",
    "https://taniarascia.com",
    "https://cassie.codes",
    "https://robbowen.digital",
    "https://ines.io",
    "https://jacekjeznach.com",
    "https://bruno-simon.com",
    "https://memoriesofpakistan.com",
    "https://davidhellmann.com",
    "https://thblt.io",
    "https://lhbzr.com",
    "https://igorkromin.net",
    "https://manuelmoreale.com",
    "https://daviddarnes.com",
    "https://andy-bell.co.uk",
    "https://hankchizljaw.com",
    "https://piccalil.li",
    "https://zellwk.com",
    "https://css-irl.info",
    "https://stefanjudis.com",
    "https://chenhuijing.com",
    "https://sarasoueidan.com",
    "https://leaverou.me",
    "https://una.im",
    "https://adactio.com",
    "https://rachelandrew.co.uk",
    "https://chriscoyier.net",

    # Designers / Visual
    "https://naomiatkinson.com",
    "https://www.mata.as",
    "https://madebysofa.com",
    "https://www.stralo.com",
    "https://www.koalite.com",
    "https://www.pierre-io.com",
    "https://mmgrafik.de",
    "https://www.superbig.co",
    "https://www.dogstudio.co",
    "https://mmgrafik.de",
    "https://activetheory.net",
    "https://www.humaan.com",
    "https://www.locomotive.ca",
    "https://www.resn.co.nz",
    "https://www.jam3.com",
    "https://www.hellomonday.com",
    "https://www.mediamonks.com",
    "https://www.upperquad.com",
    "https://www.unfold.no",
    "https://www.toyfight.co",

    # Minimalist Personal Sites
    "https://frankchimero.com",
    "https://craigmod.com",
    "https://kottke.org",
    "https://austinkleon.com",
    "https://www.robinrendle.com",
    "https://www.simoneini.com",
    "https://nicholasreese.com",
    "https://www.alexcornell.com",
    "https://www.sebdesign.eu",
    "https://www.liamriddler.com",
    "https://mattfarley.ca",
    "https://melanierichards.com",
    "https://www.kathrynmcclintock.com",
    "https://www.calebwilliams.co",
    "https://www.charliemarcotte.com",
    "https://www.joeybanks.com",
    "https://www.ericwbailey.design",
    "https://www.daneden.me",
    "https://www.alexkaessner.de",
    "https://www.loupbrun.ca",

    # Product / UX Designers
    "https://www.nabaroa.com",
    "https://www.mikeaparicio.com",
    "https://www.kieloch.com",
    "https://www.alexhuges.com",
    "https://www.lauragaughancreative.com",
    "https://www.vanschneider.com",
    "https://www.sebastiangreger.net",
    "https://www.timothyachumba.com",
    "https://www.rauchg.com",
    "https://www.mrmrs.cc",
    "https://jxnblk.com",
    "https://rsms.me",
    "https://mds.is",
    "https://jonbellah.com",
    "https://www.kevinpowell.co",
    "https://www.sarahedo.com",
    "https://www.femke.co.nz",
    "https://www.uxfolio.com",
    "https://www.evanlintelman.com",
    "https://www.jasminmlakar.com",

    # Motion / Creative Coders
    "https://www.activetheory.net",
    "https://www.adrenalinmedia.com.au",
    "https://www.edoardodecaria.com",
    "https://www.dominikjeske.com",
    "https://www.ricardooliveira.co",
    "https://www.iamhans.com",
    "https://www.pierrelevaillant.me",
    "https://www.thibautfoussard.com",
    "https://www.benoitgirard.ca",
    "https://www.maximeheckel.com",
]

@dataclass
class Portfolio:
    url: str
    name: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None



# ─────────────────────────────────────────────
# FILE QUEUE  (read / write / pop)
# ─────────────────────────────────────────────

def _load_queue() -> list[dict]:
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE, encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def _save_queue(queue: list[dict]) -> None:
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)


def _queue_is_empty() -> bool:
    return len(_load_queue()) == 0


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def get_portfolio() -> Portfolio:
    """
    Return a single Portfolio and remove it from the queue file.
    If the queue is empty, runs the extractor first to refill it.
    """

    try:
        result = supabase_client.table("links").select("*").limit(1).execute()
        if result.data:
            row = result.data[0]
            # delete it from supabase so it's not returned again
            supabase_client.table("links").delete().eq("id", row["id"]).execute()
            print(f"📬 From Supabase: {row['url']}")
            return Portfolio(url=row["url"], source="supabase_submission")
    except Exception as e:
        print(f"⚠ Supabase check failed: {e}")

    try:
        used = supabase_client.table("handpicked_used").select("url").execute()
        used_urls = {row["url"] for row in used.data}
    except:
        used_urls = set()

    # filter out used ones
    remaining = [u for u in HANDPICKED_PORTFOLIOS if u not in used_urls]

    if remaining:
        url = random.choice(remaining)
        # mark as used in supabase
        try:
            supabase_client.table("handpicked_used").insert({"url": url}).execute()
        except Exception as e:
            print(e)
        print(f"⭐ Handpicked ({len(remaining)-1} remaining): {url}")
        return Portfolio(url=url, source="handpicked")
    
    if _queue_is_empty():
        print("⚠  Queue is empty — running extractor to refill…")
        _run_extractor()

    queue = _load_queue()
    item = queue.pop(0)          # take from the front
    _save_queue(queue)
    print(f"📦 Popped: {item['url']}  ({len(queue)} remaining in queue)")
    return Portfolio(**item)


# ─────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────

AWESOME_PORTFOLIO_READMES = [
    "https://raw.githubusercontent.com/amnashanwar/awesome-portfolios/master/README.md",
    "https://raw.githubusercontent.com/iRaul/awesome-portfolios/master/readme.md",
]


def _extract_urls_from_markdown(text: str) -> list[str]:
    return re.findall(r'https?://[^\s\)\]"\']+', text)


def _scrape_github_awesome_lists() -> list[Portfolio]:
    portfolios = []
    for raw_url in AWESOME_PORTFOLIO_READMES:
        try:
            r = requests.get(raw_url, timeout=10)
            r.raise_for_status()
            urls = _extract_urls_from_markdown(r.text)
            for url in urls:
                if any(skip in url for skip in ["github.com", "twitter.com", "npmjs", "shields.io"]):
                    continue
                portfolios.append(Portfolio(url=url.rstrip("/.,)"), source="github_awesome_list"))
            print(f"  ✓ awesome-list ({raw_url.split('/')[4]}): {len(urls)} URLs")
        except Exception as e:
            print(f"  ✗ Failed {raw_url}: {e}")
        time.sleep(0.5)
    return portfolios


def _scrape_github_user_sites(max_pages: int = 3) -> list[Portfolio]:
    portfolios = []
    headers = {"Accept": "application/vnd.github+json"}
    for page in range(1, max_pages + 1):
        url = (
            "https://api.github.com/search/repositories"
            f"?q=portfolio+in:description+language:HTML&sort=stars&per_page=30&page={page}"
        )
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            items = r.json().get("items", [])
            for repo in items:
                homepage = repo.get("homepage", "")
                owner = repo["owner"]["login"]
                site_url = (
                    homepage if (homepage and homepage.startswith("http"))
                    else f"https://{owner}.github.io/{repo['name']}"
                )
                portfolios.append(Portfolio(
                    url=site_url,
                    name=owner,
                    description=repo.get("description"),
                    source="github_search",
                ))
            print(f"  ✓ GitHub API page {page}: {len(items)} repos")
            time.sleep(1)
        except Exception as e:
            print(f"  ✗ GitHub API page {page} failed: {e}")
            break
    return portfolios


def _scrape_personalsites_es(max_pages: int = 5) -> list[Portfolio]:
    portfolios = []
    base = "https://personalsit.es"
    for page in range(1, max_pages + 1):
        url = f"{base}/?page={page}"
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href^='http']"):
                href = a["href"]
                if base in href or "github.com" in href:
                    continue
                name_el = a.select_one(".name, h2, h3, strong")
                portfolios.append(Portfolio(
                    url=href,
                    name=name_el.get_text(strip=True) if name_el else None,
                    source="personalsit.es",
                ))
            print(f"  ✓ personalsit.es page {page}: {len(portfolios)} total")
            time.sleep(0.8)
        except Exception as e:
            print(f"  ✗ personalsit.es page {page} failed: {e}")
            break
    return portfolios


# ─────────────────────────────────────────────
# ENRICHMENT
# ─────────────────────────────────────────────

def _enrich(p: Portfolio, timeout: int = 6) -> Portfolio:
    try:
        r = requests.get(p.url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        if soup.title and soup.title.string:
            p.title = soup.title.string.strip()
        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta and meta.get("content"):
            p.description = meta["content"].strip()[:200]
    except Exception:
        pass
    return p


# ─────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────

def _deduplicate(portfolios: list[Portfolio]) -> list[Portfolio]:
    seen, unique = set(), []
    for p in portfolios:
        key = re.sub(r'^https?://', '', p.url.rstrip("/")).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


# ─────────────────────────────────────────────
# EXTRACTOR  (fills the queue file)
# ─────────────────────────────────────────────

def _run_extractor(enrich_limit: int = 50) -> None:
    """Scrape all sources, deduplicate, enrich, and write to QUEUE_FILE."""
    all_portfolios: list[Portfolio] = []

    print("\n[1/3] Scraping GitHub awesome-portfolio lists…")
    all_portfolios += _scrape_github_awesome_lists()

    print("\n[2/3] Querying GitHub search API…")
    all_portfolios += _scrape_github_user_sites(max_pages=3)

    print("\n[3/3] Scraping personalsit.es gallery…")
    all_portfolios += _scrape_personalsites_es(max_pages=5)

    print(f"\n🔗 Raw total : {len(all_portfolios)}")
    portfolios = _deduplicate(all_portfolios)
    print(f"✅ After dedup: {len(portfolios)}")

    print(f"\n🌐 Enriching first {enrich_limit} entries…")
    for i, p in enumerate(portfolios[:enrich_limit]):
        portfolios[i] = _enrich(p)
        if (i + 1) % 10 == 0:
            print(f"   … {i + 1}/{enrich_limit} enriched")
        time.sleep(0.3)

    _save_queue([asdict(p) for p in portfolios])
    print(f"\n💾 Queue written → {QUEUE_FILE}  ({len(portfolios)} portfolios)\n")


# ─────────────────────────────────────────────
# QUICK DEMO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Pull three portfolios one at a time — extractor runs automatically if needed
    for _ in range(3):
        p = get_portfolio()
        print(f"  url  : {p.url}")
        print(f"  title: {p.title}")
        print(f"  src  : {p.source}")
        print()