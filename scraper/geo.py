"""Erkennt Stadt und Land aus Ortsangaben wie "Munich, Bavaria, Germany", "DE-Munich",
"Singapore", "London, United Kingdom" oder "Tokyo, JP" und prüft, ob der Ort erlaubt ist."""
from __future__ import annotations

import re

from .common import clean, fold

# Land der Städte aus "stadtnamen" (laender.yaml), damit auch reine Stadtangaben zugeordnet werden
STADT_LAND = {
    "München": "DE", "Köln": "DE", "Nürnberg": "DE", "Düsseldorf": "DE", "Frankfurt am Main": "DE",
    "Hannover": "DE", "Berlin": "DE", "Hamburg": "DE", "Stuttgart": "DE", "Regensburg": "DE",
    "Wien": "AT", "Zürich": "CH", "Genf": "CH", "Basel": "CH", "Bern": "CH",
    "Mailand": "IT", "Rom": "IT", "Turin": "IT", "Florenz": "IT", "Neapel": "IT", "Venedig": "IT",
    "Prag": "CZ", "Warschau": "PL", "Krakau": "PL", "Breslau": "PL", "Danzig": "PL",
    "Lissabon": "PT", "Brüssel": "BE", "Antwerpen": "BE", "Kopenhagen": "DK", "Athen": "GR",
    "Bukarest": "RO", "Sofia": "BG", "Budapest": "HU", "Den Haag": "NL", "Göteborg": "SE",
    "Luxemburg": "LU", "Barcelona": "ES", "Madrid": "ES", "Sevilla": "ES", "Valencia": "ES",
    "Paris": "FR", "Lyon": "FR", "Marseille": "FR", "London": "GB", "Edinburgh": "GB",
    "Dublin": "IE", "Stockholm": "SE", "Helsinki": "FI", "Oslo": "NO", "Amsterdam": "NL",
    "Rotterdam": "NL", "Tallinn": "EE", "Riga": "LV", "Vilnius": "LT", "Sydney": "AU",
    "Melbourne": "AU", "Auckland": "NZ",
}

# Häufige Länder außerhalb des Suchgebiets (eindeutige Ablehnung statt "unbekannt")
FREMD = [
    "united states", "united states of america", "usa", "u.s.", "u.s.a.", "us", "america",
    "canada", "kanada", "mexico", "mexiko", "méxico", "india", "indien", "israel", "turkey", "türkiye",
    "turkei", "türkei", "united arab emirates", "uae", "saudi arabia", "qatar", "egypt", "south africa",
    "malaysia", "thailand", "vietnam", "viet nam", "indonesia", "philippines", "ukraine", "russia",
    "serbia", "serbien", "bosnia", "north macedonia", "albania", "moldova", "belarus", "georgia",
    "armenia", "morocco", "tunisia", "nigeria", "kenya", "pakistan", "bangladesh", "sri lanka",
    "costa rica", "panama", "ecuador", "bolivia", "paraguay", "venezuela", "guatemala",
    "dominican republic", "puerto rico", "kazakhstan", "macau", "macao",
]
MEHRERE = re.compile(r"\b(multiple|various|several|mehrere|verschiedene|varias|diversas|v[áa]rias)\b", re.I)
REMOTE = re.compile(r"\b(remote|home ?office|work from home|fully remote|teletrabajo|remoto)\b", re.I)
NOISE = re.compile(r"\b(hybrid|on-?site|office|headquarters|hq|campus|metropolitan area|area|region|"
                   r"greater|city of|stadt|provincia de|province|state|county|district)\b", re.I)


class Geo:
    def __init__(self, cfg: dict):
        self.laender = cfg["laender"]
        self.country_alias: dict[str, str] = {}      # gefaltete Schreibweise -> Code
        self.multi_word: list[tuple[re.Pattern, str]] = []
        self.hubs: dict[str, list[tuple[str, list[str]]]] = {}
        self.city_alias: dict[str, str] = {}         # gefaltet -> Anzeigename
        self.city_country: dict[str, str] = {}       # Anzeigename -> Code
        for code, c in self.laender.items():
            names = set(c.get("namen") or []) | {c["name"]}
            for n in names:
                f = fold(n)
                self.country_alias[f] = code
                if " " in f or "." in f:
                    self.multi_word.append((re.compile(r"(?<![a-z])" + re.escape(f) + r"(?![a-z])"), code))
            if c.get("staedte"):
                lst = []
                for disp, aliases in c["staedte"].items():
                    al = sorted({fold(a) for a in (aliases or [])} | {fold(disp)}, key=len, reverse=True)
                    lst.append((disp, al))
                    for a in al:
                        self.city_alias[a] = disp
                    self.city_country[disp] = code
                self.hubs[code] = lst
        for disp, aliases in (cfg.get("stadtnamen") or {}).items():
            for a in set(aliases or []) | {disp}:
                self.city_alias.setdefault(fold(a), disp)
        for disp, code in STADT_LAND.items():
            self.city_country.setdefault(disp, code)
            self.city_alias.setdefault(fold(disp), disp)
        self.fremd = {fold(x) for x in FREMD}
        self.multi_word.sort(key=lambda x: -len(x[0].pattern))
        self.iso3 = {fold(n): code for code, c in self.laender.items() for n in (c.get("namen") or [])
                     if len(n) == 3 and n.isupper()}

    # ------------------------------------------------------------------ Hilfen
    def name(self, code: str) -> str:
        return self.laender[code]["name"]

    def kontinent(self, code: str) -> str:
        return self.laender[code]["kontinent"]

    def _country_from_parts(self, parts: list[str], raw_parts: list[str]) -> str | None:
        """Gibt Code (erlaubt), 'XX' (bekannt, aber nicht erlaubt) oder None zurück."""
        found = None
        has_us = False
        for p, raw in zip(parts, raw_parts):
            if p in self.fremd:
                has_us = has_us or p in ("usa", "us", "u.s.", "united states", "united states of america")
                found = found or "XX"
                continue
            if p in self.country_alias and not (len(raw) == 2 and raw.isupper()):
                return self.country_alias[p]
        # ISO-Codes (z. B. "Munich, BY, DE" oder "DE-Munich"): letzter 2-/3-Buchstaben-Teil zählt
        for p, raw in reversed(list(zip(parts, raw_parts))):
            if len(raw) == 2 and raw.isupper():
                code = raw if raw != "UK" else "GB"
                if code == "US":
                    return "XX"
                if code in self.laender and not has_us:
                    return code
                return None if not found else found
            if len(raw) == 3 and raw.isupper() and fold(raw) in self.iso3:
                return self.iso3[fold(raw)]
        return found

    def _token_fallback(self, whole: str) -> tuple[str | None, str | None]:
        """Sucht bekannte Städte/Länder als einzelne Wörter (mind. 4 Buchstaben, Wortpaare zuerst)."""
        toks = [t for t in re.split(r"[^a-z\u00c0-\u024f]+", whole) if t]
        grams = [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)] + toks
        city = code = None
        for g in grams:
            if len(g) < 4:
                continue
            if not city and g in self.city_alias and self.city_alias[g] in self.city_country:
                city = self.city_alias[g]
            if not code and g in self.fremd:
                code = "XX"
            if not code and g in self.country_alias:
                code = self.country_alias[g]
        if city and not code:
            code = self.city_country[city]
        if city and code and self.city_country.get(city) != code:
            city = None
        if code and code != "XX" and not city:
            names = {fold(n) for n in (self.laender[code].get("namen") or [])} | {fold(self.name(code))}
            rest = whole
            for n in sorted(names, key=len, reverse=True):
                rest = re.sub(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", " ", rest)
            rest = clean(NOISE.sub(" ", rest)).strip(" .-,")
            city = rest.title() if 2 <= len(rest) <= 40 and not MEHRERE.search(rest) else None
        return code, city

    def _display_city(self, part: str) -> str:
        f = fold(part)
        if f in self.city_alias:
            return self.city_alias[f]
        return clean(part).strip(" .")

    # ------------------------------------------------------------------ Hauptfunktion
    def resolve_one(self, text: str, hint: str | None = None) -> dict | None:
        """Ein Ort -> {stadt, land} | {land: 'XX'} (nicht erlaubt) | None (unbekannt)."""
        s = clean(text)
        if not s:
            return None
        remote = bool(REMOTE.search(s))
        s = re.sub(r"\b\d{4,6}(-\d{3,4})?\b", " ", s)            # PLZ
        s = REMOTE.sub(" ", s)
        s = re.sub(r"\+\s*\d+\s*(more|weitere|más|mais)\b\W*", " ", s, flags=re.I)  # "+1 more…"
        m = re.match(r"^\s*([A-Z]{2})\s*-\s*(.+)$", s)              # "DE-Munich"
        if m:
            s = f"{m.group(2)}, {m.group(1)}"
        raw_parts = [clean(p).strip(" .") for p in re.split(r",|\s[-–|/]\s|\(|\)|;", s)]
        raw_parts = [p for p in raw_parts if p]
        parts = [fold(p) for p in raw_parts]
        whole = fold(s)
        code = None
        for pat, c in self.multi_word:                              # "United Kingdom", "Hong Kong"
            if pat.search(whole):
                code = c
                break
        if not code:
            code = self._country_from_parts(parts, raw_parts)
        if not code and hint:
            code = hint
        # Stadt ohne Land: über bekannte Städte zuordnen
        if not code:
            for p in parts:
                disp = self.city_alias.get(p)
                if disp and disp in self.city_country:
                    code = self.city_country[disp]
                    break
        forced_city = None
        if not code and len(s) <= 80:
            # Letzter Versuch: einzelne Wörter (z. B. "Campus Repsol-Madrid", "zagreb croatia")
            code, forced_city = self._token_fallback(whole)
        if not code:
            return None
        if code == "XX":
            return {"land": "XX"}
        if forced_city and (code not in self.hubs or self.city_country.get(forced_city) == code):
            return {"stadt": forced_city, "land": code}

        # Stadt bestimmen
        if code in self.hubs:
            for disp, aliases in self.hubs[code]:
                if any(re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", whole) for a in aliases):
                    return {"stadt": disp, "land": code}
            if code in ("SG", "HK"):
                return {"stadt": self.name(code), "land": code}
            return {"land": "XX", "grund": f"außerhalb der Hubs in {self.name(code)}"}
        if code in ("SG", "HK"):
            return {"stadt": self.name(code), "land": code}
        city = None
        country_names = {fold(n) for n in (self.laender[code].get("namen") or [])} | {fold(self.name(code)), fold(code)}
        for p, raw in zip(parts, raw_parts):
            if p in country_names or p in self.fremd or (len(raw) <= 3 and raw.isupper()):
                continue
            cand = clean(NOISE.sub(" ", raw)).strip(" .-")
            cand = re.sub(r"\s+[A-Z]{2,3}$", "", cand)          # "Sydney NSW" -> "Sydney"
            if len(cand) < 2 or cand.isdigit() or MEHRERE.search(cand):
                continue
            city = self._display_city(cand)
            break
        if not city:
            city = "Remote" if remote else "k. A."
        return {"stadt": city, "land": code}

    def resolve(self, locations: list[str], hints: list[str] | None = None) -> tuple[list[dict], str]:
        """Mehrere Ortsangaben -> (erlaubte Orte, Status). Status: ok | fremd | unbekannt."""
        hints = [h.upper() for h in (hints or []) if h]
        hint = hints[0] if len(set(hints)) == 1 else None
        hint = "GB" if hint == "UK" else hint
        if hint and hint not in self.laender:
            hint = "XX"
        pieces: list[str] = []
        for loc in locations or []:
            for p in re.split(r"\s*(?:;|\||\n| or | und | and |\s/\s|\s&\s)\s*", str(loc or "")):
                if clean(p):
                    pieces.append(p)
        ok, seen, fremd, unknown = [], set(), 0, 0
        for p in pieces:
            r = self.resolve_one(p, hint if hint != "XX" else None)
            if r is None:
                if hint == "XX":
                    fremd += 1
                else:
                    unknown += 1
                continue
            if r["land"] == "XX":
                fremd += 1
                continue
            key = (r["stadt"], r["land"])
            if key not in seen:
                seen.add(key)
                ok.append(r)
        if not pieces and hint and hint != "XX":
            ok.append({"stadt": "k. A.", "land": hint})
        if ok:
            # "k. A." nur behalten, wenn es für das Land keine konkrete Stadt gibt
            konkret = {o["land"] for o in ok if o["stadt"] != "k. A."}
            ok = [o for o in ok if o["stadt"] != "k. A." or o["land"] not in konkret]
            return ok, "ok"
        return [], "fremd" if fremd and not unknown else "unbekannt"
