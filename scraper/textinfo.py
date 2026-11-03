"""Liest Eckdaten aus dem Anzeigentext: Sprache, Dauer, Wochenstunden, Start, Arbeitsmodell."""
from __future__ import annotations

import math
import re
from datetime import date

from .common import KA, MONATSNAMEN, MONTH_RE, clean, month_number

# --------------------------------------------------------------------------- Sprache
STOP = {
    "de": "und der die das mit für wir sie ist ein eine bei von zu auf im den dem des als oder auch werden unsere deine dein ihre über sowie",
    "en": "and the with for you we our your are is a an to of in on as will be this that or who what about team",
    "es": "y el la los las con para que de en un una por tu nuestro nuestra del se es como más sus",
    "fr": "et le la les des avec pour vous nous est un une dans sur du au aux votre nos qui être ce",
    "it": "e il lo la gli le con per che di un una sono nel della del delle siamo tuo",
    "pt": "e o a os as com para que de em um uma por você nosso nossa do da são não",
    "nl": "en de het een met voor wij jij je zijn van op is als bij ons onze ook",
    "pl": "i w z na do się jest oraz dla że nie od po jak",
    "sv": "och att det som är för med på en av vi du har till",
    "da": "og at det som er for med på en af vi du har til",
    "cs": "a v se na je že s z do pro jako od",
}
STOP_SETS = {k: set(v.split()) for k, v in STOP.items()}
SCRIPTS = [
    ("ja", re.compile(r"[぀-ヿ]")),          # Hiragana/Katakana
    ("ko", re.compile(r"[가-힯]")),          # Hangul
    ("zh", re.compile(r"[一-鿿]")),          # CJK
    ("ru", re.compile(r"[Ѐ-ӿ]")),          # Kyrillisch
    ("el", re.compile(r"[Ͱ-Ͽ]")),          # Griechisch
    ("ar", re.compile(r"[؀-ۿ]")),
    ("th", re.compile(r"[฀-๿]")),
]


def detect_language(text: str) -> tuple[str, dict]:
    """Gibt (Hauptsprache, Anteile) zurück. Schrift geht vor Wortstatistik."""
    t = text or ""
    letters = max(1, len(re.findall(r"\w", t)))
    for code, pat in SCRIPTS:
        n = len(pat.findall(t))
        if n / letters > 0.15:
            return code, {code: 1.0}
    words = re.findall(r"[a-zäöüßáéíóúñàèìòùâêîôûçãõåøæ]+", t.lower())[:3000]
    counts = {k: sum(1 for w in words if w in s) for k, s in STOP_SETS.items()}
    total = sum(counts.values()) or 1
    shares = {k: v / total for k, v in counts.items() if v}
    if not shares:
        return "unbekannt", {}
    best = max(shares, key=shares.get)
    return best, shares


def language_ok(text: str, allowed: list[str]) -> tuple[bool, str]:
    lang, shares = detect_language(text)
    if lang in allowed or lang == "unbekannt":
        return True, lang
    # Mehrsprachige Anzeigen: erlaubte Sprache mit deutlichem Anteil reicht
    alt = max((shares.get(a, 0), a) for a in allowed)
    if alt[0] >= 0.3:
        return True, alt[1]
    return False, lang


# --------------------------------------------------------------------------- Zahlen
ZAHLWORT = {
    "ein": 1, "einen": 1, "one": 1, "un": 1, "uno": 1, "zwei": 2, "two": 2, "dos": 2,
    "drei": 3, "three": 3, "tres": 3, "vier": 4, "four": 4, "cuatro": 4, "fünf": 5, "fuenf": 5,
    "five": 5, "cinco": 5, "sechs": 6, "six": 6, "seis": 6, "sieben": 7, "seven": 7, "siete": 7,
    "acht": 8, "eight": 8, "ocho": 8, "neun": 9, "nine": 9, "nueve": 9, "zehn": 10, "ten": 10,
    "diez": 10, "elf": 11, "eleven": 11, "once": 11, "zwölf": 12, "twelve": 12, "doce": 12,
}
NUM = r"(\d{1,2}|" + "|".join(sorted(ZAHLWORT, key=len, reverse=True)) + r")"


def _n(x: str) -> int:
    return int(x) if x.isdigit() else ZAHLWORT.get(x.lower(), 0)


# --------------------------------------------------------------------------- Dauer
EXPERIENCE = re.compile(r"erfahrung|experience|experiencia|berufserfahrung|praxiserfahrung|years?|jahre", re.I)
DUR_CONTEXT = re.compile(
    r"praktik|intern|dauer|duration|zeitraum|period|für|for\b|minimum|mindestens|at least|"
    r"durante|duración|duracion|de\s|start|beginn|ab\b|from|laufzeit|length|befristet|"
    r"pflicht|mandatory|placement|stage", re.I)
MONTH_UNIT = r"(?:monate?n?|monats?|months?|mo\b|meses|mes)"
WEEK_UNIT = r"(?:wochen|weeks?|semanas)"


def extract_duration(text: str) -> tuple[str, float | None]:
    """-> (Anzeige, Wochen). Bevorzugt Angaben mit Praktikums-Kontext, ignoriert Berufserfahrung."""
    t = (text or "").replace("–", "-").replace("—", "-")
    patterns = [
        (rf"\b{NUM}\s*(?:-|bis|to|a|–|or|oder)\s*{NUM}[\s-]*{MONTH_UNIT}", "m2"),
        (rf"\b{NUM}[\s-]*(?:-|–)?\s*{MONTH_UNIT}(?:ig(?:es|en|e)?|s)?\b", "m1"),
        (rf"\b{NUM}[\s-]*monatig", "m1"),
        (rf"\b{NUM}[\s-]*month[\s-]", "m1"),
        (rf"\b{NUM}\s*(?:-|bis|to|a|–)\s*{NUM}[\s-]*{WEEK_UNIT}", "w2"),
        (rf"\b{NUM}[\s-]*{WEEK_UNIT}", "w1"),
        (rf"\b{NUM}[\s-]*week[\s-]", "w1"),
    ]
    best = None
    for pat, kind in patterns:
        for m in re.finditer(pat, t, re.I):
            a = _n(m.group(1))
            b = _n(m.group(2)) if kind.endswith("2") else None
            if not a or (b is not None and not b):
                continue
            unit_weeks = kind.startswith("w")
            if unit_weeks and (a > 52 or (b and b > 52)):
                continue
            if not unit_weeks and (a > 24 or (b and b > 24)):
                continue
            ctx = t[max(0, m.start() - 70): m.end() + 40]
            after = t[m.end(): m.end() + 25]
            if EXPERIENCE.search(after) or re.search(r"(stunden|hours|horas|std)\s*(pro|per|/|a la)?\s*$", t[max(0, m.start() - 30): m.start()], re.I):
                continue
            # "Wochenstunden" o. Ä. ausschließen
            if unit_weeks and re.search(r"^\s*(stunden|hours)", after, re.I):
                continue
            score = 2 if DUR_CONTEXT.search(ctx) else 0
            score += 1 if kind in ("m2", "w2") else 0
            cand = (score, -m.start(), kind, a, b)
            if best is None or cand[:2] > best[:2]:
                best = cand
    if not best or best[0] < 2:
        return KA, None
    _, _, kind, a, b = best
    if kind.startswith("m"):
        disp = f"{a}–{b} Monate" if b else f"{a} {'Monat' if a == 1 else 'Monate'}"
        weeks = round((b or a) * 4.345, 1)
    else:
        disp = f"{a}–{b} Wochen" if b else f"{a} Wochen"
        weeks = float(b or a)
    return disp, weeks


# --------------------------------------------------------------------------- Wochenstunden
def extract_hours(text: str) -> tuple[str, float | None]:
    t = (text or "").replace("–", "-")
    m = re.search(r"\b(\d{2})(?:[.,](\d))?\s*(?:-|bis|to|a)\s*(\d{2})(?:[.,]\d)?\s*"
                  r"(?:wochenstunden|std\.?|stunden|hours?|hrs?|h|horas)\b\s*(?:/|pro|per|a|je|in der|por|a la|each)?\s*"
                  r"(?:woche|week|wk|semana)?", t, re.I)
    if m and 10 <= int(m.group(1)) <= 45 and 10 <= int(m.group(3)) <= 45:
        return f"{m.group(1)}–{m.group(3)} Std.", float(m.group(3))
    pats = [
        r"\b(\d{2})(?:[.,](\d))?\s*(?:wochenstunden)",
        r"\b(\d{2})(?:[.,](\d))?\s*-?\s*(?:std\.?|stunden|hours?|hrs?|h|horas)\s*(?:/|pro|per|a|je|in der|por|a la|each|a la)\s*(?:woche|week|wk|semana)",
        r"\b(\d{2})(?:[.,](\d))?[\s-]*(?:stunden|hour)[\s-]*(?:woche|week)",
        r"(?:wochenarbeitszeit|arbeitszeit|working hours|weekly hours|jornada)[^\d\n]{0,25}(\d{2})(?:[.,](\d))?",
    ]
    for p in pats:
        m = re.search(p, t, re.I)
        if m and 10 <= int(m.group(1)) <= 45:
            h = float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
            return f"{m.group(1)}{',' + m.group(2) if m.group(2) else ''} Std.", h
    tl = t.lower()
    if re.search(r"\bvollzeit|full[\s-]?time|tiempo completo|jornada completa", tl):
        return "Vollzeit", None
    if re.search(r"\bteilzeit|part[\s-]?time|media jornada|tiempo parcial", tl):
        return "Teilzeit", None
    return KA, None


def weeks_for_hours(hours: float | None, total: int = 720) -> int | None:
    return math.ceil(total / hours) if hours else None


# --------------------------------------------------------------------------- Start
START_KW = (r"\b(?:start(?:datum|termin|ing|s)?|beginn(?:end|t)?|ab|zum|from|commencing|eintritt|einstieg|"
            r"inicio|incorporaci[oó]n|a partir de|desde|zeitraum|period|starting date|start date|available)\b")
SEASON = {"frühjahr": 3, "fruehjahr": 3, "frühling": 3, "spring": 3, "primavera": 3,
          "sommer": 6, "summer": 6, "verano": 6, "herbst": 9, "autumn": 9, "fall": 9, "otoño": 9}


def _fmt(y: int, m: int) -> tuple[str, str]:
    return f"{MONATSNAMEN[m - 1]} {y}", f"{y:04d}-{m:02d}"


def extract_start(text: str, posted: str | None = None) -> tuple[str, str | None]:
    """-> (Anzeige, 'YYYY-MM' oder None)."""
    t = text or ""
    ref = date.fromisoformat(posted) if posted else date.today()

    def infer_year(m: int) -> int:
        y = ref.year
        return y + 1 if m < ref.month else y

    # 1) Datum mit Schlüsselwort davor
    m = re.search(START_KW + r"[^\n\d]{0,25}(\d{1,2})[./](\d{1,2})[./](\d{2,4})", t, re.I)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        if 1 <= mo <= 12 and 2020 <= y <= 2035:
            return _fmt(y, mo)
    m = re.search(START_KW + r"[^\n\d]{0,25}(20\d\d)-(\d{2})-(\d{2})", t, re.I)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)))
    # 2) Monat (+ Jahr) mit Schlüsselwort davor
    m = re.search(START_KW + r"[^\n]{0,30}?\b(" + MONTH_RE + r")\.?\b(?:\s+(?:de\s+|of\s+)?(20\d\d))?", t, re.I)
    if m:
        mo = month_number(m.group(1))
        if mo and not (m.group(1).lower() in ("mar", "mai", "may", "ago", "dic", "ene") and not m.group(2)):
            y = int(m.group(2)) if m.group(2) else infer_year(mo)
            return _fmt(y, mo)
    # 3) Monat Jahr ohne Schlüsselwort, aber im Praktikums-Kontext
    for m in re.finditer(r"\b(" + MONTH_RE + r")\.?\s+(?:de\s+)?(20\d\d)\b", t, re.I):
        ctx = t[max(0, m.start() - 80): m.start()]
        if re.search(r"praktik|intern|start|beginn|ab\b|from|zeitraum|period|inicio|desde", ctx, re.I):
            mo = month_number(m.group(1))
            if mo:
                return _fmt(int(m.group(2)), mo)
    # 4) Jahreszeit
    m = re.search(r"\b(" + "|".join(SEASON) + r")\s+(?:of\s+|de\s+)?(20\d\d)\b", t, re.I)
    if m:
        mo = SEASON[m.group(1).lower()]
        return f"{m.group(1).capitalize()} {m.group(2)}", f"{m.group(2)}-{mo:02d}"
    # 5) ab sofort
    if re.search(r"ab sofort|asap|as soon as possible|immediately|immediate start|lo antes posible|"
                 r"incorporación inmediata|nächstmöglich|zum nächstmöglichen", t, re.I):
        return "ab sofort", f"{ref.year:04d}-{ref.month:02d}"
    return KA, None


# --------------------------------------------------------------------------- Arbeitsmodell
def guess_modell(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"100\s?% remote|fully remote|vollständig remote|remote-first|100\s?% teletrabajo", t):
        return "Remote"
    if re.search(r"\bhybrid|mobiles arbeiten|mobile work|teilweise remote|home ?office|work from home|teletrabajo", t):
        return "Hybrid"
    if re.search(r"\bon-?site|vor ort|presencial|in-office", t):
        return "Präsenz"
    return KA
