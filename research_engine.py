import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pathlib import Path
from playwright.sync_api import sync_playwright


def capture_public_screenshot(app_name, url):
    screenshot_dir = Path("screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-z0-9]+", "-", app_name.lower()).strip("-")
    path = screenshot_dir / f"{safe_name}.png"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.screenshot(path=str(path), full_page=False)
            browser.close()
        return str(path)
    except Exception:
        return None


AUTH_LABELS = (
    ("google_oauth", ("google", "continue with google", "sign in with google")),
    ("microsoft_oauth", ("microsoft", "azure ad", "entra id", "continue with microsoft")),
    ("github_oauth", ("github", "continue with github", "sign in with github")),
    ("apple_oauth", ("apple", "continue with apple", "sign in with apple")),
    ("magic_link", ("magic link", "email link", "sign in with email")),
    ("passwordless", ("passwordless", "passkey", "webauthn")),
    ("sso_saml", ("saml", "sso", "single sign-on", "single-sign-on")),
    ("mfa_available", ("two-factor", "2-factor", "two factor", "multi-factor", "mfa")),
)


def text_has(text, phrases):
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def url_is_official(candidate, official_url):
    try:
        candidate_host = urlparse(candidate).hostname or ""
        official_host = urlparse(official_url).hostname or ""
        return candidate_host == official_host or candidate_host.endswith("." + official_host)
    except ValueError:
        return False


def discover_public_page(app_name, official_url):
    headers = {
        "User-Agent": "AuthAtlas-Research-Agent/1.0 (+public-documentation-research)",
        "Accept": "text/html,application/xhtml+xml",
    }
    response = httpx.get(
        official_url,
        timeout=12.0,
        follow_redirects=True,
        headers=headers,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    login_url = None
    signup_url = None
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.stripped_strings).lower()
        href = urljoin(str(response.url), anchor["href"])
        href_lower = href.lower()
        if not url_is_official(href, str(response.url)):
            continue
        if login_url is None and (
            re.search(r"\b(log[ -]?in|sign[ -]?in)\b", label)
            or re.search(r"(login|sign[-]?in)", href_lower)
        ):
            login_url = href
        if signup_url is None and (
            re.search(r"\b(sign[ -]?up|start free|create account|register|get started)\b", label)
            or re.search(r"(sign[-]?up|register|create[-]?account)", href_lower)
        ):
            signup_url = href

    findings = []
    result = {
        "login_url": login_url,
        "signup_url": signup_url,
        "official_url": str(response.url),
        "http_status": response.status_code,
    }

    for field, phrases in AUTH_LABELS:
        if text_has(page_text, phrases):
            result[field] = True
            findings.append(field)
        else:
            result[field] = None

    api_phrases = ("api documentation", "developer api", "rest api", "api reference")
    result["api_available"] = True if text_has(page_text, api_phrases) else None

    if findings:
        result["findings"] = (
            f"Public official-page text for {app_name} mentions: "
            + ", ".join(findings)
            + ". These indicators require source confirmation before they are treated as verified."
        )
    elif text_has(page_text, api_phrases):
        result["findings"] = (
            f"Public official-page text for {app_name} mentions developer API access."
        )
    else:
        result["findings"] = (
            f"The official public page for {app_name} responded successfully, "
            "but authentication indicators could not be verified from extracted text."
        )

    result["evidence_url"] = str(response.url)
    result["verification_status"] = "Public documentation only"
    return result
