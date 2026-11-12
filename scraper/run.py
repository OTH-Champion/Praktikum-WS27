"""Hauptprogramm: sammelt Praktika, filtert, bewertet und schreibt docs/data/jobs.json.

Aufruf:  python -m scraper.run [--debug] [--only "Firma A" "Firma B"] [--list-only] [--reclassify]
"""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
import time
import traceback
from datetime import date, datetime, timezone

from . import classify, textinfo
from .adapters import ADAPTERS, detect_ats
from .common import (DEBUG_DIR, KA, LAENDER_OUT, OUTPUT_FILE, STATE_FILE, Http, clean, companies_file,
                     load_companies, load_settings, load_yaml, slug, title_is_internship)
from .geo import Geo

MAX_DETAILS_PER_COMPANY = 800
STATE_VERSION = 1


# --------------------------------------------------------------------------- Länderdaten
def build_laender(cfg: dict, settings: dict) -> dict:
    vorlagen = cfg.get("vorlagen") or {}
    laender = {}
    for code, c in cfg["laender"].items():
        base = dict(vorlagen.get(c.get("vorlage"), {}))
        base.update({k: v for k, v in c.items() if k not in ("namen", "staedte", "vorlage")})
        laender[code] = {
            "name": base["name"], "kontinent": base["kontinent"], "visum": bool(base.get("visum")),
            "erasmus": base.get("erasmus", False), "visum_text": clean(base.get("visum_text")),
            "links": base.get("links") or [], "foerderung": base.get("foerderung") or [],
            "hubs": list((c.get("staedte") or {}).keys()),
        }
    return {
        "stand": cfg.get("stand"), "kontinente": cfg.get("kontinente"), "laender": laender,
        "foerderungen": {k: {**v, "text": clean(v.get("text"))} for k, v in (cfg.get("foerderungen") or {}).items()},
        "allgemein": [{**a, "text": clean(a.get("text"))} for a in cfg.get("allgemein") or []],
        "pflichtstunden": settings.get("pflichtstunden", 720),
    }


# --------------------------------------------------------------------------- Zustand
def load_state() -> dict:
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if s.get("version") == STATE_VERSION:
            return s
    return {"version": STATE_VERSION, "jobs": {}, "rejected": {}}


def previous_output() -> dict:
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def all_companies(company_status: list[dict], jobs_out: list[dict], prev: dict) -> list[dict]:
    status = {s["name"]: s for s in company_status}
    prev_f = {f["name"]: f for f in prev.get("firmen", [])}
    out = []
    for c in load_yaml(companies_file()) or []:
        name = c["name"]
        career = c.get("career_url") or c.get("url") or c.get("list_url")
        if name in status:
            s = status[name]
            e = {"name": name, "career_url": career, "ok": s["ok"], "note": s["note"], "aktiv": True}
            if s.get("beobachtet"):
                e["beobachtet"] = True
                e["hinweise"] = s.get("hinweise") or []
        elif c.get("enabled", True) and name in prev_f:
            e = dict(prev_f[name])
        else:
            e = {"name": name, "career_url": career, "ok": True, "aktiv": bool(c.get("enabled", True)),
                 "note": "" if c.get("enabled", True) else "derzeit nicht automatisch abrufbar"}
        e["stellen"] = sum(1 for j in jobs_out if j["firma"] == name)
        out.append(e)
        for sub in (c.get("unterfirmen") or {}):
            se = dict(e, name=sub, career_url=(c.get("unterfirmen_urls") or {}).get(sub, career))
            se["stellen"] = sum(1 for j in jobs_out if j["firma"] == sub)
            out.append(se)
    return out


# --------------------------------------------------------------------------- Bewertung einer Stelle
def evaluate(job: dict, comp: dict, geo: Geo, settings: dict) -> tuple[dict | None, str]:
    """Prüft Ort, Sprache und BWL-Bezug und liest die Eckdaten. -> (Eintrag, Grund)"""
    hints = job.get("country_hints") or ([comp["default_land"]] if comp.get("default_land") else None)
    locs = [] if comp.get("nur_land") else (job.get("locations") or [])  # Ortstext unbrauchbar: nur default_land
    orte, status = geo.resolve(locs, hints)
    if not orte and status != "fremd" and comp.get("ort_aus_titel"):  # z. B. UNICEF: Ort steht nur im Titel
        orte, status = geo.resolve([job["title"]], None)
    if not orte and status != "unbekannt":  # nur eindeutig fremde Orte schließen aus
        return None, f"Ort {status}: {'; '.join(job.get('locations') or [])[:80]}"
    # Ort nicht erkennbar: Stelle bleibt drin (orte = []), die Website zeigt "Ort unbekannt"
    text = job.get("text") or ""
    ok, lang = textinfo.language_ok(f"{job['title']}\n{text}", settings["sprachen"])
    if not ok:
        return None, f"Sprache {lang}"
    a = classify.assess(job["title"], job.get("department", ""), text, ngo=bool(comp.get("ngo")))
    if not a["relevant"]:
        return None, f"kein BWL-Bezug ({a['grund']})"
    full = f"{job['title']}\n{text}\n{job.get('extra', '')}"
    dauer, wochen = textinfo.extract_duration(full)
    stunden, h = textinfo.extract_hours(full)
    posted = job.get("posted")
    start, start_monat = textinfo.extract_start(text, posted or date.today().isoformat())
    modell = job.get("modell") or textinfo.guess_modell(text)
    return {
        "url": job["url"], "company": company_for(job, comp), "title": clean(job["title"]),
        "posted": posted, "orte": orte, "fachbereich": a["fachbereich"], "arbeitsmodell": modell,
        "start": start, "start_monat": start_monat, "dauer": dauer, "dauer_wochen": wochen,
        "stunden": stunden, "stunden_num": h, "sprache": lang, "grund": a["grund"],
    }, "ok"


# --------------------------------------------------------------------------- Abruf je Firma
def collect_http(comp: dict, http: Http, settings: dict) -> tuple[list[dict], object]:
    ats = comp.get("ats") or detect_ats(comp.get("url", "") or (comp.get("urls") or [""])[0])
    adapter = ADAPTERS[ats]
    urls = comp.get("urls") or [comp["url"]]
    out, seen = [], set()
    for u in urls:  # mehrere Stellenbörsen derselben Firma (z. B. Berufserfahrene + Nachwuchs)
        for j in adapter.list(http, {**comp, "url": u}, settings):
            if j["url"] not in seen:
                seen.add(j["url"])
                j["_src"] = u
                out.append(j)
    return out, adapter


PAGE_SIZES = {10, 12, 15, 20, 24, 25, 30, 40, 50, 100}


def search_warnings(comp: dict, ats: str, zahlen: dict, hstats: dict | None) -> list[str]:
    """Hinweise, dass eine Firma vermutlich nicht alle Praktika liefert (Suche ignoriert, nur 1 Seite gelesen)."""
    found, prakt = zahlen.get("gefunden", 0), zahlen.get("praktika", 0)
    if not found or prakt:
        return []
    out = []
    hs = hstats or {}
    paging = comp.get("pages") or comp.get("next_click") or comp.get("follow") or hs.get("auto_next_neu")
    if ats == "browser" and hs.get("extra") and not any(hs["extra"]):
        out.append("alle Such-URLs liefern dieselben Stellen, der Suchbegriff wird vermutlich ignoriert")
    if ats == "browser" and found in PAGE_SIZES and not paging:
        out.append(f"genau {found} Stellen und kein Praktikum, vermutlich nur die erste Seite gelesen")
    return out


def names_of(comp: dict) -> list[str]:
    """Firmenname plus Tochterfirmen, die auf derselben Stellenbörse ausgeschrieben werden."""
    return [comp["name"]] + list((comp.get("unterfirmen") or {}).keys())


def company_for(job: dict, comp: dict) -> str:
    """Ordnet eine Stelle einer Tochterfirma zu, wenn deren Name im Titel, Ort oder Text vorkommt."""
    hay = " ".join([job.get("title", ""), " ".join(job.get("locations") or []), (job.get("text") or "")[:1500]])
    for name, rx in (comp.get("unterfirmen") or {}).items():
        if re.search(rx or re.escape(name), hay, re.I):
            return name
    return comp["name"]


class Browser:
    """Startet Chromium erst, wenn eine Firma ohne Schnittstelle dran ist."""

    def __init__(self):
        self.pw = self.browser = self.ctx = None

    def page(self):
        if not self.ctx:
            from playwright.sync_api import sync_playwright
            from .common import UA
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH") or None,
                                                   args=["--disable-blink-features=AutomationControlled"])
            self.ctx = self.browser.new_context(user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900})
            self.ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return self.ctx.new_page()

    def close(self):
        if self.browser:
            self.browser.close()
            self.pw.stop()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="Rohdaten nach debug/ schreiben")
    ap.add_argument("--only", nargs="*", help="Nur diese Firmen")
    ap.add_argument("--list-only", action="store_true", help="Nur Stellenlisten lesen (Test), nichts speichern")
    ap.add_argument("--reclassify", action="store_true", help="Bereits bewertete Stellen neu bewerten")
    ap.add_argument("--recheck-rejected", action="store_true",
                    help="Nur bisher aussortierte Stellen neu bewerten (z. B. nach geänderten Regeln)")
    args = ap.parse_args()

    settings = load_settings()
    lcfg = load_yaml("laender.yaml")
    geo = Geo(lcfg)
    LAENDER_OUT.parent.mkdir(parents=True, exist_ok=True)
    LAENDER_OUT.write_text(json.dumps(build_laender(lcfg, settings), ensure_ascii=False, indent=1), encoding="utf-8")

    companies = load_companies(args.only)
    state = load_state()
    today = date.today().isoformat()
    http = Http()
    browser = Browser()
    print(f"Firmen ({len(companies)}): {', '.join(c['name'] for c in companies)}")

    company_status, active_urls = [], set()
    for comp in companies:
        name = comp["name"]
        st = {"name": name, "ok": True, "found": 0, "note": "", "zahlen": {}}
        dbg: dict = {"decisions": []} if args.debug else {}
        t0 = time.time()
        print(f"\n== {name} ==")
        if comp.get("ats") == "beobachten":  # Firma ohne Stellenliste: Karriereseite auf neue Stellenlinks prüfen
            from .watch import watch_company
            st = watch_company(comp, http, state)
            st["seconds"] = round(time.time() - t0)
            company_status.append(st)
            continue
        try:
            ats = comp.get("ats") or detect_ats(comp.get("url", "")) or "browser"
            if ats == "browser":
                from .detail import fetch_detail
                from .harvest import harvest
                page = browser.page()
                raw = harvest(page, comp, dbg if args.debug else None)
                for r in raw:
                    r["locations"] = [x for x in (r.get("location"), r.get("card", "")[:300]) if x]
                adapter = None
            else:
                raw, adapter = collect_http(comp, http, settings)
                page = None
            st["found"] = len(raw)
            cands = [r for r in raw if r.get("title") and (title_is_internship(r["title"], settings) or
                     (r.get("intern") and not any(p.search(r["title"]) for p in settings["_exclude"])))]
            print(f"  {len(raw)} Stellen gefunden, {len(cands)} davon Praktika (Titel)")
            # Grober Ortsfilter auf Listenebene: eindeutig fremde Orte gleich raus
            pre = []
            for c in cands:
                orte, status = geo.resolve(c.get("locations") or [], c.get("country_hints"))
                if status == "fremd" and ats != "browser":
                    continue
                pre.append(c)
            print(f"  {len(pre)} nach Ortsfilter (Liste)")
            st["zahlen"] = {"gefunden": len(raw), "praktika": len(cands), "ort_ok": len(pre)}
            hstats = None
            if ats == "browser":
                from .harvest import LAST_STATS
                hstats = dict(LAST_STATS)
            st["warnungen"] = search_warnings(comp, ats, st["zahlen"], hstats)
            for h in st["warnungen"]:
                print(f"  ⚠ {h}")
            if args.list_only:
                for c in pre[:8]:
                    print(f"    · {c['title'][:70]} | {'; '.join(c.get('locations') or [])[:60]}")
                pre = []

            n_detail, added = 0, 0
            for c in pre:
                url = c["url"]
                if url in state["jobs"] and not args.reclassify:
                    state["jobs"][url]["last_seen"] = today
                    active_urls.add(url)
                    continue
                if url in state["rejected"] and not (args.reclassify or args.recheck_rejected):
                    state["rejected"][url] = today
                    continue
                if n_detail >= MAX_DETAILS_PER_COMPANY:
                    st["note"] = "Limit für Detailseiten erreicht"
                    break
                if not c.get("text"):
                    n_detail += 1
                    try:
                        if adapter is None:
                            d = fetch_detail(page, url, fast=comp.get("detail_fast", False))
                            d["locations"] = [d.get("location")] if d.get("location") else []
                        elif hasattr(adapter, "detail"):
                            d = adapter.detail(http, {**comp, "url": c.get("_src") or comp.get("url")}, c)
                        else:
                            d = {}
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! Detailseite fehlgeschlagen: {url} ({e.__class__.__name__})")
                        continue
                    c["text"] = d.get("text", "")
                    if d.get("locations"):  # Detailseite ist genauer als die Liste
                        c["locations"] = list(d["locations"])
                    c["country_hints"] = c.get("country_hints") or d.get("country_hints") or []
                    c["posted"] = c.get("posted") or d.get("posted")
                    c["extra"] = d.get("extra", "")
                entry, why = evaluate(c, comp, geo, settings)
                if args.debug:
                    dbg["decisions"].append({"url": url, "title": c["title"], "locations": c.get("locations"),
                                             "ergebnis": why, "text_start": (c.get("text") or "")[:600]})
                if not entry:
                    state["rejected"][url] = today
                    print(f"  – {c['title'][:70]} ({why})")
                    continue
                old = state["jobs"].get(url, {})
                entry["first_seen"] = old.get("first_seen", today)
                entry["last_seen"] = today
                state["jobs"][url] = entry
                active_urls.add(url)
                added += 1
                print(f"  + {c['title'][:70]} [{', '.join(o['stadt'] + ' ' + o['land'] for o in entry['orte']) or 'Ort unbekannt'}; "
                      f"{entry['fachbereich']}; {entry['dauer']}; {entry['stunden']}; Start {entry['start']}]")
            if st["found"] == 0 and not comp.get("may_be_empty"):
                st["ok"] = False
                st["note"] = "Keine Stellen gefunden (Seite oder Schnittstelle evtl. geändert)"
        except Exception as e:  # noqa: BLE001
            st["ok"] = False
            st["note"] = f"Fehler: {e.__class__.__name__}"
            print(f"  ! Fehler bei {name}: {e}")
            if args.debug:
                dbg["error"] = traceback.format_exc()
        st["seconds"] = round(time.time() - t0)
        company_status.append(st)
        if args.debug:
            d = DEBUG_DIR / slug(name)
            d.mkdir(parents=True, exist_ok=True)
            (d / "decisions.json").write_text(json.dumps(dbg, ensure_ascii=False, indent=1, default=str)[:5_000_000],
                                              encoding="utf-8")
    browser.close()

    def print_warnings():
        flagged = [s for s in company_status if s.get("warnungen")]
        if flagged:
            print(f"\nHinweise: bei {len(flagged)} Firma(en) fehlen evtl. Praktika (Konfiguration prüfen):")
            for s in flagged:
                print(f"  ⚠ {s['name']}: {'; '.join(s['warnungen'])}")

    if args.list_only:
        for s in company_status:
            print(f"  {'OK ' if s['ok'] else 'ERR'} {s['name']}: {s['zahlen']} {s['seconds']}s {s['note']}")
        print_warnings()
        return 0

    # Firmen mit Fehler: alte Stellen einen Lauf lang behalten
    by_name = {c["name"]: c for c in companies}
    failed = {n for s in company_status if not s["ok"] for n in names_of(by_name[s["name"]])}
    for url, j in state["jobs"].items():
        if j["company"] in failed and url not in active_urls and j.get("kept_runs", 0) < 1:
            j["kept_runs"] = j.get("kept_runs", 0) + 1
            active_urls.add(url)
    queried = {n for c in companies for n in names_of(c)}
    configured = {n for c in (load_yaml(companies_file()) or []) for n in names_of(c)}
    state["jobs"] = {u: j for u, j in state["jobs"].items()
                     if j["company"] in configured and (u in active_urls or j["company"] not in queried)}
    for j in state["jobs"].values():
        if j["company"] not in failed:
            j.pop("kept_runs", None)
    cutoff = date.today().toordinal() - 60
    state["rejected"] = {u: d for u, d in state["rejected"].items() if date.fromisoformat(d).toordinal() >= cutoff}

    jobs_out = []
    for j in state["jobs"].values():
        jobs_out.append({
            "titel": j["title"], "firma": j["company"], "orte": j["orte"],
            "fachbereich": j["fachbereich"], "arbeitsmodell": j["arbeitsmodell"],
            "start": j["start"], "start_monat": j["start_monat"],
            "dauer": j["dauer"], "dauer_wochen": j["dauer_wochen"],
            "stunden": j["stunden"], "stunden_num": j["stunden_num"],
            "veroeffentlicht": j.get("posted") or j["first_seen"], "datum_geschaetzt": not j.get("posted"),
            "link": j["url"],
        })
    jobs_out.sort(key=lambda x: x["veroeffentlicht"], reverse=True)
    out = {
        "aktualisiert": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "firmen": all_companies(company_status, jobs_out, previous_output()),
        "stellen": jobs_out,
    }
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    print(f"\nFertig: {len(jobs_out)} Praktika online.")
    for s in company_status:
        print(f"  {'OK ' if s['ok'] else 'ERR'} {s['name']}: {s['zahlen']} {s['seconds']}s {s['note']}")
    print_warnings()
    return 0


if __name__ == "__main__":
    sys.exit(main())
