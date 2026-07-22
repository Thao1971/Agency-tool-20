"""Newsletter email ingestion agent — IMAP reader + parser."""

import os
import imaplib
import email
import hashlib
import logging
from email.header import decode_header
from typing import Dict, List, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IMAP_HOST = os.environ.get("EDITORIAL_IMAP_HOST", "")
IMAP_PORT = int(os.environ.get("EDITORIAL_IMAP_PORT", "993"))
EMAIL_USER = os.environ.get("EDITORIAL_EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EDITORIAL_EMAIL_PASSWORD", "")


def check_connection() -> Dict:
    """Test IMAP connection."""
    if not IMAP_HOST or not EMAIL_USER or not EMAIL_PASS:
        return {"connected": False, "error": "Email credentials not configured"}
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        conn.login(EMAIL_USER, EMAIL_PASS)
        status, data = conn.select("INBOX", readonly=True)
        count = int(data[0]) if status == "OK" else 0
        conn.logout()
        return {"connected": True, "inbox_count": count, "user": EMAIL_USER}
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}


def fetch_newsletters(max_emails: int = 20, since_days: int = 7) -> List[Dict]:
    """Fetch recent unprocessed newsletters from IMAP inbox."""
    if not IMAP_HOST or not EMAIL_USER or not EMAIL_PASS:
        return []

    results = []
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        conn.login(EMAIL_USER, EMAIL_PASS)
        conn.select("INBOX", readonly=True)

        # Search recent emails
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        status, msg_ids = conn.search(None, f'(SINCE {since})')

        if status != "OK" or not msg_ids[0]:
            conn.logout()
            return []

        ids = msg_ids[0].split()[-max_emails:]  # Last N emails

        for mid in ids:
            status, msg_data = conn.fetch(mid, "(RFC822)")
            if status != "OK":
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_subject(msg.get("Subject", ""))
            sender = msg.get("From", "")
            date_str = msg.get("Date", "")
            msg_id = msg.get("Message-ID", "")

            # Parse date
            parsed_date = None
            try:
                parsed_date = email.utils.parsedate_to_datetime(date_str).isoformat()
            except Exception:
                parsed_date = datetime.now(timezone.utc).isoformat()

            # Extract body
            html_body = ""
            text_body = ""
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode("utf-8", errors="replace")
                elif ct == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        text_body = payload.decode("utf-8", errors="replace")

            # Extract links from HTML — filter out navigation/UI junk
            links = []
            if html_body:
                soup = BeautifulSoup(html_body, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)

                    # Skip short, navigation, and platform links
                    if len(text) < 15:
                        continue
                    text_lower = text.lower()
                    href_lower = href.lower()

                    # Blacklist patterns
                    skip = False
                    for junk in [
                        "unsubscribe", "leer más", "leer mas", "read more", "ver en navegador",
                        "view in browser", "marcar como", "editar esta", "edit alert",
                        "manage preferences", "update profile", "ver más resultado",
                        "see more results", "este enlace", "click here", "haga clic",
                        "página de ayuda", "portal de ayuda", "feedback", "privacy",
                        "terms of", "condiciones", "política de privacidad",
                        "dinahosting", "mailchimp", "sendgrid", "mailgun", "constantcontact",
                        "google.com/alerts", "support.google",
                        "actualizar mis datos", "update my data",
                    ]:
                        if junk in text_lower or junk in href_lower:
                            skip = True
                            break
                    if skip:
                        continue
                    if not href.startswith("http"):
                        continue

                    # Resolve Google redirect URLs to final destination
                    href = _resolve_google_redirect(href)

                    links.append({"url": href, "text": text[:200]})

            # Clean text
            clean_text = ""
            if html_body:
                clean_text = BeautifulSoup(html_body, "html.parser").get_text(separator=" ", strip=True)[:3000]
            elif text_body:
                clean_text = text_body[:3000]

            dedupe = hashlib.sha256(f"{msg_id}|{subject}".encode()).hexdigest()[:20]

            results.append({
                "message_id": msg_id,
                "subject": subject,
                "sender": sender,
                "date": parsed_date,
                "text": clean_text[:2000],
                "links": links[:30],
                "link_count": len(links),
                "dedupe_hash": dedupe,
            })

        conn.logout()

    except Exception as e:
        logger.error(f"Newsletter fetch error: {e}")

    return results


def _decode_subject(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(data))
    return " ".join(decoded)


def _resolve_google_redirect(url: str) -> str:
    """Extract real URL from Google redirect wrappers."""
    from urllib.parse import urlparse, parse_qs
    if "google.com/url" not in url:
        return url
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        # Google Alerts uses &url= parameter
        if "url" in params:
            return params["url"][0]
        # Some use &q= parameter
        if "q" in params:
            return params["q"][0]
    except Exception:
        pass
    return url
