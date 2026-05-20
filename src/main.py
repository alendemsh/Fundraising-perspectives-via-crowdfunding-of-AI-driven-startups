"""
Kickstarter Technology category project parser.

Architecture (pipeline with parallelism):
  Level 1 вЂ“ Sequential: fetch listing pages via in-page fetch() (one CDP tab).
            Build partial records from the JSON (most fields).
  Level 2 вЂ“ Parallel:   scrape project pages, comments, updates, and creator
            profiles using multiple browser tabs via async Playwright.

Connects to a Chrome instance launched by the script itself with
--remote-debugging-port and a dedicated --user-data-dir.
"""

import asyncio
import json
import random
import re
import logging
import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.async_api import (
    async_playwright,
    Page as AsyncPage,
    BrowserContext as AsyncBrowserContext,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DISCOVER_URL = "https://www.kickstarter.com/discover/advanced"
CATEGORY_ID_TECHNOLOGY = 16
SEED_MAX = 9_999_999
DEFAULT_STATE = "successful"
DEFAULT_SORT = "magic"
DEFAULT_SEARCH = "ai"
DEFAULT_WOE_ID = 0
DEFAULT_RAISED = None  # None = no filter; 0 = raised nothing (failed projects)

NAV_TIMEOUT_MS = 60_000
REQUEST_DELAY_MS = 1_500
PARALLEL_WORKERS = 4


OUTPUT_FILE = "projects.json"

# fmt: off
AI_KEYWORDS_PATTERN = re.compile(
    r"\b("
    # ML / predictive
    r"machine\s+learning|ML|predictive\s+model|classification|clustering|trained\s+on\s+data"
    # deep learning
    r"|deep\s+learning|deep\s+neural\s+network|DNN|CNN|transformer|embeddings"
    # computer vision
    r"|computer\s+vision|machine\s+vision|object\s+detection|image\s+recognition|OCR"
    # NLP
    r"|natural\s+language\s+processing|NLP|NLU|NLG|named\s+entity\s+recognition"
    r"|summarization|sentiment\s+analysis"
    # chatbot
    r"|AI\s+chatbot|chatbot|virtual\s+assistant|question\s+answering|conversational\s+AI"
    # speech
    r"|speech\s+recognition|ASR|STT|TTS|voice\s+assistant"
    # recommendations
    r"|recommendation\s+engine|recommender\s+system|ranking\s+model"
    r"|personalized\s+recommendations|reranking"
    # predictive analytics
    r"|predictive\s+analytics|forecasting|time[- ]series\s+forecasting"
    r"|demand\s+forecasting|predictive\s+maintenance"
    # anomaly
    r"|anomaly\s+detection|outlier\s+detection|fraud\s+detection|risk\s+scoring"
    # generative AI
    r"|generative\s+AI|GenAI|LLM|large\s+language\s+model|foundation\s+model"
    r"|diffusion\s+model|GAN|VAE"
    # agents
    r"|AI\s+agent|autonomous\s+agent|tool\s+calling|agentic\s+workflow"
    # edge AI
    r"|edge\s+AI|on[- ]device\s+AI|real[- ]time\s+inference|smart\s+camera"
    # MLOps
    r"|MLOps|ModelOps|model\s+deployment|model\s+monitoring|feature\s+store"
    r"|model\s+registry|training\s+pipeline"
    # embeddings / RAG
    r"|embedding\s+model|vector\s+database|vector\s+store|vector\s+index"
    r"|RAG|retrieval[- ]augmented\s+generation|semantic\s+search"
    # XAI
    r"|explainable\s+AI|XAI|trustworthy\s+AI"
    r")\b",
    re.IGNORECASE,
)

COMPETENCE_KEYWORDS_PATTERN = re.compile(
    r"\b("
    # software engineering
    r"programming|frontend|backend|mobile\s+dev|API|version\s+control"
    r"|testing|CI/CD|architecture|microservices|open\s+source"
    # data / ML
    r"|data\s+analysis|SQL|ETL|ELT|dashboards?|A/B\s+testing"
    r"|machine\s+learning|ML|NLP|CV|recommender\s+system"
    r"|LLM|large\s+language\s+model|embeddings|fine[- ]?tuning|RAG"
    # cloud / infra
    r"|cloud\s+architecture|AWS|Azure|GCP|Kubernetes|Docker"
    r"|serverless|IaC|CI/CD\s+pipeline|observability|logging"
    r"|load\s+balancing|CDN|autoscaling|IAM|VPC|networking"
    # security
    r"|cybersecurity|secure\s+coding|threat\s+modeling"
    r"|vulnerability\s+management|pentest|encryption"
    r"|authentication|access\s+control|IR|audit|SOC\s*2"
    r"|privacy\s+by\s+design|NIST\s+alignment|zero\s+trust"
    r")\b",
    re.IGNORECASE,
)
# fmt: on
EARLY_BIRD_PATTERN = re.compile(r"early\s*bird", re.IGNORECASE)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_BASE_DEBUG_PORT = 9222
CHROME_PROFILE_BASE_DIR = Path("__chrome_profiles")
KICKSTARTER_URL = "https://www.kickstarter.com"

CF_CHALLENGE_TITLE = "Just a moment..."

SECONDS_PER_DAY = 86_400

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chrome launch (sync вЂ“ runs before the async event loop)
# ---------------------------------------------------------------------------


def _get_screen_size() -> tuple[int, int]:
    """Return (width, height) of the primary monitor."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080  # sensible fallback


def _compute_grid(total: int, screen_w: int, screen_h: int) -> list[tuple[int, int, int, int]]:
    """
    Compute grid positions for `total` windows on a screen.
    Returns list of (x, y, width, height) for each slot.
    """
    import math
    cols = math.ceil(math.sqrt(total))
    rows = math.ceil(total / cols)
    w = screen_w // cols
    h = screen_h // rows
    slots: list[tuple[int, int, int, int]] = []
    for idx in range(total):
        r, c = divmod(idx, cols)
        slots.append((c * w, r * h, w, h))
    return slots


def _launch_chrome(
    instance_id: int,
    window_rect: tuple[int, int, int, int] | None = None,
) -> subprocess.Popen:
    """Launch a Chrome instance with its own debug port and user-data-dir."""
    port = CHROME_BASE_DEBUG_PORT + instance_id
    profile_dir = Path.cwd() / CHROME_PROFILE_BASE_DIR / f"instance_{instance_id}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
    ]
    if window_rect:
        x, y, w, h = window_rect
        cmd.append(f"--window-position={x},{y}")
        cmd.append(f"--window-size={w},{h}")
    cmd.append(KICKSTARTER_URL)

    log.info("Launching Chrome #%d on port %d", instance_id, port)
    proc = subprocess.Popen(cmd)

    endpoint = f"http://127.0.0.1:{port}/json/version"
    for _ in range(30):
        try:
            requests.get(endpoint, timeout=1)
            log.info("Chrome #%d debug port ready.", instance_id)
            return proc
        except requests.ConnectionError:
            time.sleep(1)

    raise RuntimeError(
        f"Chrome #{instance_id} did not open debug port {port} within 30 s."
    )


def _launch_chrome_fleet_range(
    start_id: int,
    count: int,
    grid: list[tuple[int, int, int, int]] | None = None,
) -> list[subprocess.Popen]:
    """Launch `count` Chrome instances with ids [start_id .. start_id+count)."""
    procs: list[subprocess.Popen] = []
    for i in range(count):
        rect = grid[start_id + i] if grid and (start_id + i) < len(grid) else None
        procs.append(_launch_chrome(start_id + i, window_rect=rect))
    return procs


def _kill_chrome_proc(proc: subprocess.Popen) -> None:
    """Kill a Chrome process and all its children (Windows: taskkill /T)."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Async browser helpers
# ---------------------------------------------------------------------------


async def _wait_for_cloudflare(page: AsyncPage) -> None:
    """Poll until the Cloudflare challenge page (if any) clears."""
    for elapsed in range(0, 60_000, 2_000):
        title = await page.title()
        if CF_CHALLENGE_TITLE not in title:
            return
        log.info("Cloudflare challenge detected вЂ“ waiting вЂ¦ (%d ms)", elapsed)
        await page.wait_for_timeout(2_000)
    log.warning("Cloudflare challenge did not clear within 60 s")


async def _wait_for_kickstarter(page: AsyncPage) -> None:
    """Wait until the Kickstarter page has loaded past Cloudflare."""
    log.info("Waiting for Kickstarter to load (solve Cloudflare if prompted) вЂ¦")
    for _ in range(120):
        try:
            await page.wait_for_timeout(1_000)
            title = await page.title()
        except Exception:
            # Page/context may have been navigated away or closed temporarily
            await asyncio.sleep(1)
            continue
        if CF_CHALLENGE_TITLE not in title and "kickstarter" in page.url.lower():
            log.info("Kickstarter loaded (title: %s)", title)
            return
    log.warning("Timed out waiting for Kickstarter to load.")


async def _fetch_json_via_page(page: AsyncPage, url: str) -> dict:
    """Execute an in-page fetch() for a JSON API URL (same-origin XHR)."""
    raw = await page.evaluate(
        """async (url) => {
            const resp = await fetch(url, {
                headers: {
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.text();
        }""",
        url,
    )
    await page.wait_for_timeout(REQUEST_DELAY_MS)
    return json.loads(raw)


async def _fetch_html_via_page(page: AsyncPage, url: str) -> str:
    """Navigate a browser tab to an HTML page and return its content."""
    await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await _wait_for_cloudflare(page)
    await page.wait_for_timeout(REQUEST_DELAY_MS)
    return await page.content()


# Selectors for the campaign story container, tried in priority order.
# Kickstarter is an SPA and class names change periodically.
_STORY_SELECTORS = [
    ".story-content",
    "[class*='storyContent']",
    "[class*='campaignStory']",
    ".rte__content",
    "[data-testid='campaign-story']",
    ".full-description",
    "[class*='story']",
]
_STORY_CSS_COMBINED = ", ".join(_STORY_SELECTORS)

# Timeout (ms) for waiting for the story section to appear in the SPA.
_STORY_WAIT_TIMEOUT_MS = 10_000


async def _fetch_project_description_html(
    page: AsyncPage, project_url: str,
) -> str:
    """Navigate to the /description tab and wait for story content to render."""
    desc_url = project_url.rstrip("/") + "/description"
    await page.goto(desc_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await _wait_for_cloudflare(page)

    # Wait for the SPA to hydrate the story section (Kickstarter never goes truly network-idle).
    try:
        await page.wait_for_selector(
            _STORY_CSS_COMBINED, state="attached", timeout=_STORY_WAIT_TIMEOUT_MS,
        )
    except Exception:
        log.debug("Story selector not found on %s after %d ms, using page as-is",
                  desc_url, _STORY_WAIT_TIMEOUT_MS)

    await page.wait_for_timeout(REQUEST_DELAY_MS)
    return await page.content()


# ---------------------------------------------------------------------------
# Level 1 вЂ“ Listing API (sequential, single tab)
# ---------------------------------------------------------------------------


def _build_listing_url(
    page_num: int,
    seed: int,
    *,
    state: str = DEFAULT_STATE,
    sort: str = DEFAULT_SORT,
    term: str | None = DEFAULT_SEARCH,
    raised: int | None = DEFAULT_RAISED,
) -> str:
    url = (
        f"{BASE_DISCOVER_URL}"
        f"?google_chrome_workaround"
        f"&state={state}"
        f"&category_id={CATEGORY_ID_TECHNOLOGY}"
        f"&woe_id={DEFAULT_WOE_ID}"
        f"&sort={sort}"
        f"&seed={seed}"
        f"&page={page_num}"
    )
    if term:
        url += f"&term={term}"
    if raised is not None:
        url += f"&raised={raised}"
    return url


async def fetch_all_listing_projects(
    page: AsyncPage,
    *,
    seed: int,
    max_pages: int | None = None,
    max_projects: int | None = None,
    existing_links: set[str] | None = None,
    state: str = DEFAULT_STATE,
    sort: str = DEFAULT_SORT,
    term: str | None = DEFAULT_SEARCH,
    raised: int | None = DEFAULT_RAISED,
) -> list[dict]:
    """Fetch all project dicts from the listing API (Level 1)."""
    skip = existing_links or set()
    all_projects: list[dict] = []
    skipped = 0
    page_num = 1

    while True:
        url = _build_listing_url(
            page_num, seed,
            state=state, sort=sort, term=term, raised=raised,
        )
        log.info("[L1] Fetching listing page %d вЂ¦", page_num)
        data = await _fetch_json_via_page(page, url)
        projects = data.get("projects", [])
        if not projects:
            log.info("[L1] No projects on page %d вЂ“ stopping.", page_num)
            break

        for p in projects:
            link = p.get("urls", {}).get("web", {}).get("project", "")
            if link in skip:
                skipped += 1
            else:
                all_projects.append(p)
        log.info("[L1] Collected %d new projects (%d skipped as existing).",
                 len(all_projects), skipped)

        if max_projects and len(all_projects) >= max_projects:
            all_projects = all_projects[:max_projects]
            log.info("[L1] Reached max_projects=%d вЂ“ stopping.", max_projects)
            break

        if not data.get("has_more", False):
            log.info("[L1] No more pages after page %d.", page_num)
            break

        page_num += 1
        if max_pages and page_num > max_pages:
            log.info("[L1] Reached max_pages=%d вЂ“ stopping.", max_pages)
            break

    return all_projects


# ---------------------------------------------------------------------------
# Level 1 helpers вЂ“ build partial record from listing JSON
# ---------------------------------------------------------------------------


def _project_url(raw: dict) -> str:
    return raw["urls"]["web"]["project"]


def _unix_to_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _compute_duration_days(launched_ts: int | None, deadline_ts: int | None) -> int | None:
    if launched_ts is None or deadline_ts is None:
        return None
    return max(0, (deadline_ts - launched_ts) // SECONDS_PER_DAY)


def build_partial_record(raw: dict) -> dict:
    """Build a record from listing JSON only (Level 1)."""
    name = raw.get("name", "")
    blurb = raw.get("blurb", "")
    goal = raw.get("goal")
    pledged = raw.get("pledged")
    state = raw.get("state", "")
    launched_at = raw.get("launched_at")
    deadline = raw.get("deadline")
    category = raw.get("category", {})
    location = raw.get("location", {})
    video = raw.get("video")
    creator = raw.get("creator", {})

    title_blurb_text = f"{name} {blurb}"
    ai_kw_title_blurb = len(AI_KEYWORDS_PATTERN.findall(title_blurb_text))

    funding_ratio = None
    if goal and goal > 0 and pledged is not None:
        funding_ratio = round(pledged / goal, 6)

    # Extract creator API URL for Level 2
    creator_api_url = (creator.get("urls") or {}).get("api", {}).get("user")
    creator_web_url = (creator.get("urls") or {}).get("web", {}).get("user")
    creator_slug = creator.get("slug", "")


    return {
        "link": _project_url(raw),
        "state_success": 1 if state == "successful" else 0,
        "pledged_amount": pledged,
        "backers_count": raw.get("backers_count"),
        "funding_ratio": funding_ratio,
        "goal_amount": goal,
        "currency": raw.get("currency"),
        "launched_at": _unix_to_iso(launched_at),
        "deadline": _unix_to_iso(deadline),
        "duration_days": _compute_duration_days(launched_at, deadline),
        "category_main": category.get("parent_name") or category.get("name"),
        "category_sub": category.get("name") if category.get("parent_name") else None,
        "created_location_country": (
            location.get("expanded_country") or location.get("country")
        ),
        "title_length_chars": len(name),
        "has_video": 1 if video else 0,
        # в”Ђв”Ђ internal fields (removed before output) в”Ђв”Ђ
        "_ai_kw_title_blurb": ai_kw_title_blurb,
        "_launched_at_ts": launched_at,
        "_creator_api_url": creator_api_url,
        "_creator_web_url": creator_web_url,
        "_creator_slug": creator_slug,
        # в”Ђв”Ђ Level 2 placeholders в”Ђв”Ђ
        "story_word_count": None,
        "story_image_count": None,
        "story_external_links_count": None,
        "has_faq_section": None,
        "risks_word_count": None,
        "ai_keyword_count": None,
        "has_early_bird": None,
        "updates_count_total": None,
        "comments_count_total": None,
        "creator_created_projects": None,
        "creator_competence_count": None,
        "creator_social_links_count": None,
    }


# ---------------------------------------------------------------------------
# Level 2 вЂ“ HTML parsing helpers (pure CPU, no I/O)
# ---------------------------------------------------------------------------

# Minimum word count to consider a found element as a real story container.
_STORY_MIN_WORDS = 20


def _parse_story_section(soup: BeautifulSoup) -> dict:
    # Try each selector in priority order; pick the first with meaningful text.
    story_el = None
    for sel in _STORY_SELECTORS:
        candidate = soup.select_one(sel)
        if candidate and len(candidate.get_text(strip=True).split()) >= _STORY_MIN_WORDS:
            story_el = candidate
            log.debug("Story: matched selector %r (%d words)", sel,
                       len(candidate.get_text(strip=True).split()))
            break

    # Fallback: largest <div> with substantial text (common in redesigns).
    if story_el is None:
        best, best_len = None, 0
        for div in soup.find_all("div"):
            text = div.get_text(separator=" ", strip=True)
            wc = len(text.split())
            if wc > best_len:
                best, best_len = div, wc
        if best and best_len >= _STORY_MIN_WORDS:
            story_el = best
            log.debug("Story: used largest-div fallback (%d words)", best_len)

    if story_el is None:
        log.warning("Story section not found вЂ“ all selectors missed")

    story_text = story_el.get_text(separator=" ", strip=True) if story_el else ""
    story_words = story_text.split() if story_text else []
    images = story_el.find_all("img") if story_el else []

    external_links: set[str] = set()
    if story_el:
        for a_tag in story_el.find_all("a", href=True):
            parsed = urlparse(a_tag["href"])
            if parsed.scheme in ("http", "https") and "kickstarter.com" not in (parsed.netloc or ""):
                external_links.add(parsed.netloc)

    return {
        "story_word_count": len(story_words),
        "story_image_count": len(images),
        "story_external_links_count": len(external_links),
        "ai_keyword_count_story": len(AI_KEYWORDS_PATTERN.findall(story_text)),
    }


def _parse_risks_section(soup: BeautifulSoup) -> int:
    risks_el = soup.select_one("#risks-and-challenges")
    if not risks_el:
        for heading in soup.find_all(re.compile(r"^h\d$")):
            if "risk" in (heading.get_text() or "").lower():
                risks_el = heading.find_next_sibling()
                break
    if not risks_el:
        return 0
    return len(risks_el.get_text(separator=" ", strip=True).split())


async def _fetch_has_faq(page: AsyncPage, project_url: str) -> bool:
    """Fetch the /faqs XHR endpoint and check if any FAQ entries exist."""
    faqs_url = project_url.rstrip("/") + "/faqs"
    try:
        html = await page.evaluate(
            """async (url) => {
                const resp = await fetch(url, {
                    headers: {
                        'Accept': '*/*',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    credentials: 'same-origin'
                });
                if (!resp.ok) return '';
                return resp.text();
            }""",
            faqs_url,
        )
        if not html:
            return False
        soup = BeautifulSoup(html, "html.parser")
        faq_items = soup.select("details.kds-accordion")
        return len(faq_items) > 0
    except Exception:
        return False


def _has_early_bird(soup: BeautifulSoup) -> bool:
    rewards_section = soup.select_one("[class*='reward']")
    text = (rewards_section.get_text(separator=" ", strip=True)
            if rewards_section
            else soup.get_text(separator=" ", strip=True))
    return bool(EARLY_BIRD_PATTERN.search(text))


def _extract_tab_count(soup: BeautifulSoup, label: str) -> int | None:
    tab = soup.find("a", string=re.compile(rf"{label}\s*\d*", re.IGNORECASE))
    if tab:
        m = re.search(r"(\d+)", tab.get_text(strip=True))
        if m:
            return int(m.group(1))
    return None


def _parse_project_html(html: str) -> dict:
    """Parse project page HTML into Level-2 field dict."""
    soup = BeautifulSoup(html, "html.parser")
    story = _parse_story_section(soup)
    return {
        "story_word_count": story["story_word_count"],
        "story_image_count": story["story_image_count"],
        "story_external_links_count": story["story_external_links_count"],
        "ai_keyword_count_story": story["ai_keyword_count_story"],
        "risks_word_count": _parse_risks_section(soup),
        "has_faq_section": None,  # filled by async _fetch_has_faq
        "has_early_bird": int(_has_early_bird(soup)),
        "updates_count_total": _extract_tab_count(soup, "Updates"),
        "comments_count_total": _extract_tab_count(soup, "Comments"),
    }



# ---------------------------------------------------------------------------
# Creator profile parsing
# ---------------------------------------------------------------------------


def _parse_creator_profile(profile_json: dict) -> dict:
    """Extract creator fields from the profile API JSON."""
    created_count = profile_json.get("created_projects_count", 0)
    biography = profile_json.get("biography") or ""

    competence_count = len(COMPETENCE_KEYWORDS_PATTERN.findall(biography))

    return {
        "creator_created_projects": 1 if created_count > 1 else 0,
        "creator_competence_count": competence_count,
    }


def _parse_creator_web_page(html: str) -> dict:
    """Parse the creator's web profile page for social links."""
    soup = BeautifulSoup(html, "html.parser")
    external_links: set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and "kickstarter.com" not in (parsed.netloc or ""):
            external_links.add(parsed.netloc)

    return {
        "creator_social_links_count": len(external_links),
    }


# ---------------------------------------------------------------------------
# Level 2 вЂ“ async scraping orchestration
# ---------------------------------------------------------------------------


def _merge_level2(record: dict, page_data: dict) -> None:
    """Merge Level-2 scraped fields into a partial record (mutates in-place)."""
    for key in (
        "story_word_count", "story_image_count", "story_external_links_count",
        "risks_word_count", "has_faq_section", "has_early_bird",
        "updates_count_total", "comments_count_total",
        "creator_created_projects", "creator_competence_count",
        "creator_social_links_count",
    ):
        if key in page_data and page_data[key] is not None:
            record[key] = page_data[key]

    record["ai_keyword_count"] = (
        record.get("_ai_kw_title_blurb", 0) + page_data.get("ai_keyword_count_story", 0)
    )


async def _scrape_one_project(
    queue: asyncio.Queue,
    pw_browser,
    worker_id: int,
    total: int,
) -> None:
    """
    Async worker: owns a dedicated Chrome browser. Pulls records from
    the shared queue, scrapes each project, then moves to the next.
    """
    context = pw_browser.contexts[0]

    while True:
        try:
            index, record = queue.get_nowait()
        except asyncio.QueueEmpty:
            return

        url = record["link"]
        launched_ts = record.get("_launched_at_ts")
        creator_api_url = record.get("_creator_api_url")
        creator_web_url = record.get("_creator_web_url")
        creator_slug = record.get("_creator_slug", "")

        log.info("[L2-W%d] [%d/%d] Scraping %s", worker_id, index + 1, total, url)
        page = await context.new_page()
        try:
            all_data: dict = {}

            # в”Ђв”Ђ 1. Project description page (story, risks, early-bird) в”Ђв”Ђ
            # Navigate to /description to ensure the SPA renders the story.
            desc_html = await _fetch_project_description_html(page, url)
            project_data = _parse_project_html(desc_html)
            all_data.update(project_data)

            # If story was empty on /description, retry on the base URL.
            if project_data.get("story_word_count", 0) == 0:
                log.info("[L2-W%d] [%d/%d] Story empty on /description, retrying base URL",
                         worker_id, index + 1, total)
                base_html = await _fetch_html_via_page(page, url)
                retry_data = _parse_project_html(base_html)
                if retry_data.get("story_word_count", 0) > project_data.get("story_word_count", 0):
                    all_data.update(retry_data)

            # в”Ђв”Ђ 1b. FAQ (XHR from same page) в”Ђв”Ђ
            has_faq = await _fetch_has_faq(page, url)
            all_data["has_faq_section"] = int(has_faq)

            # в”Ђв”Ђ 4. Creator web page (social links + embedded profile data) в”Ђв”Ђ
            if creator_web_url:
                try:
                    creator_html = await _fetch_html_via_page(page, creator_web_url)
                    social_data = _parse_creator_web_page(creator_html)
                    all_data.update(social_data)
                except Exception:
                    log.warning("[L2-W%d] [%d/%d] Failed to scrape creator web page", worker_id, index + 1, total)

            # в”Ђв”Ђ 5. Creator profile API (navigate worker tab to API URL) в”Ђв”Ђ
            if creator_api_url:
                try:
                    await page.goto(creator_api_url, wait_until="domcontentloaded",
                                    timeout=NAV_TIMEOUT_MS)
                    await page.wait_for_timeout(REQUEST_DELAY_MS)
                    body = await page.inner_text("body")
                    body = body.strip()
                    if body.startswith("{"):
                        profile = json.loads(body)
                        creator_data = _parse_creator_profile(profile)
                        all_data.update(creator_data)
                    else:
                        log.warning("[L2-W%d] [%d/%d] Creator API returned non-JSON", worker_id, index + 1, total)
                except Exception:
                    log.warning("[L2-W%d] [%d/%d] Failed to fetch creator profile API", worker_id, index + 1, total)

            _merge_level2(record, all_data)

        except Exception:
            log.exception("[L2-W%d] Failed to scrape %s", worker_id, url)
        finally:
            await page.close()


async def run_level2(
    pw,
    l1_browser,
    records: list[dict],
    workers: int = PARALLEL_WORKERS,
    grid: list[tuple[int, int, int, int]] | None = None,
) -> None:
    """
    Reuse Chrome #0 (L1 browser, already warmed up) as worker 0.
    Launch `workers - 1` additional Chrome instances for workers 1..N-1.
    Each worker pulls records from a shared queue.
    """
    total = len(records)
    extra_workers = workers - 1

    queue: asyncio.Queue = asyncio.Queue()
    for i, rec in enumerate(records):
        queue.put_nowait((i, rec))

    # Worker 0 = L1 browser (already has Cloudflare cleared)
    pw_browsers = [l1_browser]
    worker_procs: list[subprocess.Popen] = []

    try:
        # Launch extra Chrome instances if needed
        if extra_workers > 0:
            log.info("[L2] Launching %d extra Chrome instances вЂ¦", extra_workers)
            worker_procs = _launch_chrome_fleet_range(1, extra_workers, grid=grid)

            for wid in range(extra_workers):
                port = CHROME_BASE_DEBUG_PORT + 1 + wid
                cdp_url = f"http://127.0.0.1:{port}"
                browser = await pw.chromium.connect_over_cdp(cdp_url)
                pw_browsers.append(browser)

            # Warm up extra workers in parallel with a timeout
            WARMUP_TIMEOUT_S = 15

            async def _warmup(wid: int) -> None:
                try:
                    ctx = pw_browsers[wid].contexts[0]
                    warmup_page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                    await asyncio.wait_for(
                        _wait_for_kickstarter(warmup_page),
                        timeout=WARMUP_TIMEOUT_S,
                    )
                    log.info("[L2-W%d] Cloudflare passed.", wid)
                except asyncio.TimeoutError:
                    log.warning("[L2-W%d] Warmup timed out after %ds вЂ“ will retry on first task.",
                                wid, WARMUP_TIMEOUT_S)
                except Exception:
                    log.warning("[L2-W%d] Warmup failed вЂ“ will retry on first task.", wid)

            log.info("[L2] Warming up %d extra workers (max %ds) вЂ¦", extra_workers, WARMUP_TIMEOUT_S)
            await asyncio.gather(*[_warmup(wid) for wid in range(1, workers)])

        log.info("[L2] Starting async scrape of %d projects (%d workers) вЂ¦", total, workers)
        tasks = [
            _scrape_one_project(queue, pw_browsers[wid], wid, total)
            for wid in range(workers)
        ]
        await asyncio.gather(*tasks)
        log.info("[L2] Async scrape complete.")
    finally:
        # Don't close l1_browser (index 0) вЂ” caller owns it
        for b in pw_browsers[1:]:
            try:
                await b.close()
            except Exception:
                pass
        for p in worker_procs:
            _kill_chrome_proc(p)
        if worker_procs:
            log.info("[L2] Extra Chrome instances terminated.")


# ---------------------------------------------------------------------------
# Internal field cleanup
# ---------------------------------------------------------------------------

INTERNAL_FIELDS = ("_ai_kw_title_blurb", "_launched_at_ts",
                   "_creator_api_url", "_creator_web_url", "_creator_slug")


def _strip_internal_fields(records: list[dict]) -> None:
    """Remove internal/helper fields before writing output."""
    for rec in records:
        for key in INTERNAL_FIELDS:
            rec.pop(key, None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main(args: argparse.Namespace) -> None:
    # Compute grid layout for all Chrome windows (security-cam style)
    total_browsers = args.workers
    screen_w, screen_h = _get_screen_size()
    grid = _compute_grid(total_browsers, screen_w, screen_h)
    log.info("Grid layout: %d windows on %dx%d screen", total_browsers, screen_w, screen_h)

    # Launch Chrome #0 for Level 1 (listing pages)
    l1_proc = _launch_chrome(0, window_rect=grid[0])

    try:
        cdp_url = f"http://127.0.0.1:{CHROME_BASE_DEBUG_PORT}"
        log.info("Connecting to Chrome #0 via CDP at %s вЂ¦", cdp_url)

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            pages = context.pages
            main_page = pages[0] if pages else await context.new_page()

            # в”Ђв”Ђ Wait for Kickstarter to load в”Ђв”Ђ
            await _wait_for_kickstarter(main_page)

            # в”Ђв”Ђ Load existing links to skip duplicates в”Ђв”Ђ
            out_path = Path(args.output)
            existing_links: set[str] = set()
            if out_path.exists():
                try:
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                    existing_links = {r["link"] for r in existing if "link" in r}
                    log.info("[L1] %d projects already in %s вЂ“ will skip them.",
                             len(existing_links), out_path)
                except (json.JSONDecodeError, OSError):
                    pass

            # в”Ђв”Ђ Level 1: collect all project JSON в”Ђв”Ђ
            seed = random.randint(1, SEED_MAX)
            log.info("Using seed=%d for this run.", seed)
            raw_projects = await fetch_all_listing_projects(
                main_page,
                seed=seed,
                max_pages=args.max_pages,
                max_projects=args.max_projects,
                existing_links=existing_links,
                state=args.state,
                sort=args.sort,
                term=args.term or None,
                raised=args.raised,
            )
            log.info("[L1] Collected %d new projects.", len(raw_projects))

            records = [build_partial_record(raw) for raw in raw_projects]
            log.info("[L1] Built %d partial records.", len(records))

            # в”Ђв”Ђ Level 2: scrape everything (Chrome #0 reused as worker 0) в”Ђв”Ђ
            await run_level2(pw, browser, records, workers=args.workers, grid=grid)

            _strip_internal_fields(records)

            await main_page.close()
    finally:
        _kill_chrome_proc(l1_proc)
        log.info("Chrome #0 terminated.")

    out_path = Path(args.output)

    # Merge with existing data, dedup by project link
    existing: list[dict] = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            log.info("Loaded %d existing records from %s", len(existing), out_path)
        except (json.JSONDecodeError, OSError):
            log.warning("Could not read existing %s вЂ“ starting fresh.", out_path)

    seen_links: set[str] = {r["link"] for r in existing if "link" in r}
    new_count = 0
    for rec in records:
        if rec.get("link") not in seen_links:
            existing.append(rec)
            seen_links.add(rec["link"])
            new_count += 1

    out_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Saved %d records (%d new) в†’ %s", len(existing), new_count, out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Kickstarter Technology parser",
        epilog=(
            "The script launches its own Chrome instance with remote debugging.\n"
            "On first run you may need to pass Cloudflare manually in the\n"
            "opened Chrome window. The script will wait for you."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-projects", type=int, default=None)
    parser.add_argument("--workers", type=int, default=PARALLEL_WORKERS,
                        help=f"Concurrent browser tabs for L2 (default: {PARALLEL_WORKERS})")
    parser.add_argument("-o", "--output", type=str, default=OUTPUT_FILE)
    parser.add_argument("--state", type=str, default=DEFAULT_STATE,
                        help=f"Project state filter (default: {DEFAULT_STATE!r}). "
                             f"Use 'failed' for unsuccessful projects.")
    parser.add_argument("--sort", type=str, default=DEFAULT_SORT,
                        help=f"Sort order (default: {DEFAULT_SORT!r}).")
    parser.add_argument("--term", type=str, default=DEFAULT_SEARCH,
                        help=f"Search term (default: {DEFAULT_SEARCH!r}). "
                             f"Pass empty string to disable.")
    parser.add_argument("--raised", type=int, default=DEFAULT_RAISED,
                        help="Raised-amount filter (e.g. 0 for projects that "
                             "raised nothing). Omitted by default.")
    args = parser.parse_args()

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
