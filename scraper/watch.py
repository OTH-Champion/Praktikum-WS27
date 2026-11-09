"""Beobachtung von Firmen ohne Stellenliste (ats: beobachten).

Lädt die Karriereseite (watch_url) und merkt sich alle Links, die nach Stellen aussehen.
Taucht beim nächsten Lauf ein neuer solcher Link auf (z. B. eine erste Stellenanzeige,
ein neues Stellenportal oder bei Petrobras ein neues Ausschreibungs-PDF), erscheint die
Firma auf der Website mit einem Hinweis "neue Stellenhinweise" samt Link.

Optional in companies.yaml:
  watch_url    Seite, die beobachtet wird (Pflicht)
  watch_link   eigener Regex für interessante Links (sonst WATCH_DEFAULT)
"""
from __future__ import annotations

import html as htmlmod
import re
from datetime import date
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

from .common import clean

WATCH_DEFAULT = (r"stellen|job|karriere|career|vacanc|empleo|trabaj|vaga|estagi|karijer|natje|posao|zaposl|"
                 r"oferta|praktik|intern|recruit|bewerb|apply|opening|opportunit|pasant|beca|edital|seleç|selec")
IGNORE = re.compile(r"facebook\.com|twitter\.com|x\.com/|linkedin\.com/share|whatsapp|mailto:|javascript:|"
                    r"instagram\.com|youtube\.com|tiktok\.com|cookie|privacy|datenschutz|impressum", re.I)
A_TAG = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[^\"']*[\"'][^>]*>(.*?)</a>", re.I | re.S)
HINT_DAYS = 30          # so lange bleibt ein neuer Link als Hinweis sichtbar
MAX_LINKS = 400         # Obergrenze gespeicherter Links je Firma


def _norm(url: str) -> str:
    """Link ohne Tracking-Parameter und Fragment, damit dieselbe Seite gleich bleibt."""
    u = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(u.query) if not re.match(r"utm_|sid$|_ga$|itm_|campaign|gclid|fbclid", k, re.I)]
    return urlunparse((u.scheme, u.netloc.lower(), u.path.rstrip("/") or "/", "", urlencode(q), ""))


def links_on(raw: str, base: str, pattern: str) -> dict[str, str]:
    rx = re.compile(pattern, re.I)
    out: dict[str, str] = {}
    for href, inner in A_TAG.findall(raw):
        href = htmlmod.unescape(href.strip())
        text = clean(re.sub(r"<[^>]+>", " ", htmlmod.unescape(inner)))[:120]
        full = urljoin(base, href)
        if not full.startswith("http") or IGNORE.search(full):
            continue
        if rx.search(full) or rx.search(text):
            out.setdefault(_norm(full), text)
    return out


def watch_company(comp: dict, http, state: dict) -> dict:
    """-> Status-Eintrag für company_status (ok, note, hinweise …)."""
    name = comp["name"]
    url = comp["watch_url"]
    today = date.today().isoformat()
    st = {"name": name, "ok": True, "found": 0, "note": "", "zahlen": {}, "beobachtet": True, "hinweise": []}
    w = state.setdefault("watch", {}).setdefault(name, {"links": [], "neu": {}})
    try:
        raw = http.get(url, headers={"Accept": "text/html"}).text
    except Exception as e:  # noqa: BLE001
        st["ok"] = False
        st["note"] = f"Beobachtung fehlgeschlagen ({e.__class__.__name__})"
        print(f"  ! Beobachtung fehlgeschlagen: {e}")
        st["hinweise"] = _hints(w)
        return st
    now = links_on(raw, url, comp.get("watch_link") or WATCH_DEFAULT)
    known = set(w["links"])
    first = not known and not w.get("seit")
    new = [u for u in now if u not in known]
    if first:
        print(f"  [beobachten] Ausgangslage gespeichert: {len(now)} Links")
    else:
        for u in new:
            w["neu"][u] = {"text": now[u], "seit": today}
            print(f"  [beobachten] NEU: {now[u][:60]} -> {u}")
        if not new:
            print(f"  [beobachten] keine neuen Links ({len(now)} bekannt)")
    w["seit"] = w.get("seit") or today
    w["links"] = sorted(known | set(now))[-MAX_LINKS:]
    cutoff = date.today().toordinal() - HINT_DAYS
    w["neu"] = {u: v for u, v in w["neu"].items() if date.fromisoformat(v["seit"]).toordinal() >= cutoff}
    st["found"] = len(now)
    st["zahlen"] = {"links": len(now), "neu": len(new) if not first else 0}
    st["hinweise"] = _hints(w)
    st["note"] = "wird beobachtet"
    return st


def _hints(w: dict) -> list[dict]:
    items = sorted(w.get("neu", {}).items(), key=lambda kv: kv[1]["seit"], reverse=True)
    return [{"url": u, "text": v["text"] or u, "seit": v["seit"]} for u, v in items[:5]]
