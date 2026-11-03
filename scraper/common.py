"""Gemeinsame Hilfsfunktionen: Konfiguration, HTTP, Text, Datum."""
from __future__ import annotations

import html as htmllib
import os
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
STATE_FILE = ROOT / "data" / "state.json"
OUTPUT_FILE = ROOT / "docs" / "data" / "jobs.json"
LAENDER_OUT = ROOT / "docs" / "data" / "laender.json"
DEBUG_DIR = ROOT / "debug"

KA = "k. A."
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def load_yaml(name: str):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_settings() -> dict:
    s = load_yaml("settings.yaml")
    s["_include"] = [re.compile(r"\b" + p, re.I) for p in s["include_title"]]
    s["_exclude"] = [re.compile(r"\b" + p, re.I) for p in s["exclude_title"]]
    return s


def companies_file() -> str:
    return os.environ.get("PRAKTIKUM_COMPANIES", "companies.yaml")  # für Tests


def load_companies(only: list[str] | None = None) -> list[dict]:
    comps = [c for c in (load_yaml(companies_file()) or []) if c.get("enabled", True)]
    if only:
        wanted = {o.lower() for o in only}
        comps = [c for c in comps if c["name"].lower() in wanted or slug(c["name"]) in wanted]
    return comps


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def fold(text: str) -> str:
    """Kleinschreibung ohne Akzente (für Vergleiche)."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def html_to_text(raw: str) -> str:
    """HTML (auch doppelt escaped) in lesbaren Text mit Zeilenumbrüchen."""
    if not raw:
        return ""
    s = str(raw)
    if "&lt;" in s and "<" not in s:
        s = htmllib.unescape(s)
    s = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr|ul|ol|section)>", "\n", s, flags=re.I)
    s = re.sub(r"<li[^>]*>", "\n• ", s, flags=re.I)
    s = htmllib.unescape(re.sub(r"<[^>]+>", " ", s))
    return "\n".join(clean(l) for l in s.splitlines() if clean(l))


def title_is_internship(title: str, settings: dict) -> bool:
    t = clean(title)
    if any(p.search(t) for p in settings["_exclude"]):
        return False
    return any(p.search(t) for p in settings["_include"])


# --------------------------------------------------------------------------- HTTP
class Http:
    """Kleiner Wrapper um requests mit Wiederholung und Pause zwischen Abrufen."""

    def __init__(self, pause: float = 0.35):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
                               "Accept": "application/json, text/html;q=0.9, */*;q=0.8"})
        self.pause = pause
        self._last = 0.0

    def _wait(self):
        dt = time.time() - self._last
        if dt < self.pause:
            time.sleep(self.pause - dt)
        self._last = time.time()

    def request(self, method: str, url: str, tries: int = 3, **kw):
        kw.setdefault("timeout", 40)
        err = None
        for i in range(tries):
            self._wait()
            try:
                r = self.s.request(method, url, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    err = RuntimeError(f"HTTP {r.status_code}")
                    time.sleep(2 * (i + 1))
                    continue
                if 400 <= r.status_code < 500:
                    r.raise_for_status()  # Client-Fehler: Wiederholen bringt nichts
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001
                err = e
                resp = getattr(e, "response", None)
                if resp is not None and 400 <= resp.status_code < 500:
                    break
                time.sleep(1.5 * (i + 1))
        raise err  # type: ignore[misc]

    def get(self, url: str, **kw):
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw):
        return self.request("POST", url, **kw)

    def json(self, url: str, method: str = "GET", **kw):
        return self.request(method, url, **kw).json()


# --------------------------------------------------------------------------- Datum
_MONTHS = {
    "jan": 1, "januar": 1, "january": 1, "enero": 1, "ene": 1,
    "feb": 2, "februar": 2, "february": 2, "febrero": 2,
    "mär": 3, "maerz": 3, "märz": 3, "mar": 3, "march": 3, "marzo": 3, "mrz": 3,
    "apr": 4, "april": 4, "abril": 4, "abr": 4,
    "mai": 5, "may": 5, "mayo": 5,
    "jun": 6, "juni": 6, "june": 6, "junio": 6,
    "jul": 7, "juli": 7, "july": 7, "julio": 7,
    "aug": 8, "august": 8, "agosto": 8, "ago": 8,
    "sep": 9, "sept": 9, "september": 9, "septiembre": 9, "setiembre": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10, "octubre": 10,
    "nov": 11, "november": 11, "noviembre": 11,
    "dez": 12, "dezember": 12, "dec": 12, "december": 12, "diciembre": 12, "dic": 12,
}
MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
               "September", "Oktober", "November", "Dezember"]


def month_number(name: str) -> int | None:
    return _MONTHS.get(name.lower().rstrip("."))


def parse_date(value) -> str | None:
    """Versucht, ein Datum in ISO (YYYY-MM-DD) umzuwandeln."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = clean(str(value))
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", s)
    if m:
        return _safe(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})[.\s-]+([A-Za-zäÄ]{3,10})\.?[\s-]+(\d{4})\b", s)
    if m and month_number(m[2]):
        return _safe(int(m[3]), month_number(m[2]), int(m[1]))
    m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s)
    if m and month_number(m[1]):
        return _safe(int(m[3]), month_number(m[1]), int(m[2]))
    m = re.search(r"posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)", s, re.I)  # Workday
    if m:
        days = 0 if m[1].lower() == "today" else 1 if m[1].lower() == "yesterday" else int(m[2])
        return date.fromordinal(date.today().toordinal() - days).isoformat()
    return None


def _safe(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None
