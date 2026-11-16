"""Diagnose: Warum liefert eine Firma keine Praktika? (läuft im Workflow "Diagnose")

1. Firmen mit Schnittstelle: alle gefundenen Titel ausgeben (zeigt, ob die Suche passt).
2. Karriereseiten im Browser öffnen: JSON-Antworten (mögliche Schnittstellen), erkannte Bewerbersysteme,
   Stellen-Links und Seitentext ausgeben.
3. Bisher aussortierte Stellen einer Firma neu bewerten und den Grund ausgeben.
Ergebnis: diag/result.txt
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import adapters  # noqa: E402
from scraper.common import Http, load_companies, load_settings, load_yaml, title_is_internship  # noqa: E402

OUT = Path(__file__).parent / "result.txt"
CFG = json.loads((Path(__file__).parent / "targets.json").read_text(encoding="utf-8"))
lines: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


def api_titles(http, settings):
    for name in CFG.get("api", []):
        p(f"\n######## API: {name}")
        comps = load_companies([name])
        if not comps:
            p("  nicht in companies.yaml (oder enabled: false)")
            continue
        comp = comps[0]
        try:
            ad = adapters.ADAPTERS[comp["ats"]]
            for term in adapters._search_terms(comp, settings):
                raw = ad.list(http, {**comp, "suchbegriffe": [term]}, settings)
                p(f"  Suchbegriff {term!r}: {len(raw)} Stellen")
                for r in raw[:40]:
                    flag = "PRAKTIKUM" if title_is_internship(r["title"], settings) else "-"
                    p(f"    [{flag}] {r['title'][:90]} | {'; '.join(r.get('locations') or [])[:50]} | {r['url'][:110]}")
        except Exception:
            p("  FEHLER " + traceback.format_exc()[-600:])


def http_probe(http):
    for url in CFG.get("http", []):
        p(f"\n######## HTTP: {url}")
        try:
            r = http.s.get(url, timeout=30, headers={"Accept": "application/json, text/html"})
            p(f"  {r.status_code} {r.headers.get('content-type', '')[:40]} {len(r.text)} Zeichen, Ende-URL {r.url[:150]}")
            p("  " + re.sub(r"\s+", " ", r.text[:1500]))
        except Exception as e:  # noqa: BLE001
            p(f"  FEHLER {e.__class__.__name__}: {str(e)[:200]}")


def browse():
    from playwright.sync_api import sync_playwright
    from scraper.common import UA
    from scraper.harvest import dismiss_cookies
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(user_agent=UA, locale="de-DE", viewport={"width": 1366, "height": 900})
        for name, url in CFG.get("browser", {}).items():
            p(f"\n######## Browser: {name}  {url}")
            page = ctx.new_page()
            reqs = []

            def on_resp(resp, reqs=reqs):
                try:
                    rt = resp.request.resource_type
                    ct = resp.headers.get("content-type", "")
                    if rt in ("xhr", "fetch") or "json" in ct:
                        body = ""
                        try:
                            body = resp.text()[:400] if ("json" in ct or "html" in ct) else ""
                        except Exception:
                            pass
                        reqs.append((resp.request.method, resp.status, resp.url, ct[:30], (resp.request.post_data or "")[:300], body))
                except Exception:
                    pass
            page.on("response", on_resp)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(6000)
                dismiss_cookies(page)
                page.wait_for_timeout(3000)
                p(f"  Ende-URL: {page.url} | Titel: {page.title()[:80]}")
                html = page.content()
                sigs = sorted({m for m in re.findall(r"(successfactors|jobs2web|rmkcdn|workday|myworkdayjobs|csod\.com|cornerstone|avature|phenom|eightfold|smartrecruiters|greenhouse|lever\.co|taleo|icims|oraclecloud|beesite|softgarden|dvinci|umantis|personio|recruitee|teamtailor|workable|join\.com|radancy|tmp\.com|talentsoft|cegid|jobvite|successfactors\.eu)", html, re.I)})
                p(f"  Signaturen im HTML: {sigs}")
                links = page.evaluate("[...document.querySelectorAll('a[href]')].map(a=>[a.href,(a.innerText||'').trim().slice(0,70)])")
                jobish = [l for l in links if re.search(r"job|stelle|karriere|career|vacanc|position|requisition", l[0], re.I)]
                p(f"  Links gesamt {len(links)}, jobähnlich {len(jobish)}:")
                for h, t in jobish[:45]:
                    p(f"    {h[:140]} | {t}")
                txt = page.evaluate("document.body.innerText")[:2500]
                p("  Seitentext: " + re.sub(r"\s+", " ", txt)[:2500])
                p(f"  XHR/JSON-Antworten ({len(reqs)}):")
                for m, st, u, ct, pd, body in reqs[:60]:
                    if re.search(r"\.(js|css|woff2?|png|svg)(\?|$)|google|facebook|doubleclick|hotjar|onetrust|cookielaw|usercentrics|analytics|adobe|bing|linkedin", u):
                        continue
                    p(f"    {m} {st} {u[:200]} [{ct}]" + (f" POST={pd!r}" if pd else ""))
                    if body:
                        p("      " + re.sub(r"\s+", " ", body)[:300])
            except Exception as e:  # noqa: BLE001
                p(f"  FEHLER {e.__class__.__name__}: {str(e)[:300]}")
            page.close()
        br.close()


def main():
    settings = load_settings()
    http = Http()
    api_titles(http, settings)
    http_probe(http)
    if CFG.get("browser"):
        browse()
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
