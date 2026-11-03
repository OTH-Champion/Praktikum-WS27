"""Einmaliges Hilfsskript: erkennt das Bewerbersystem hinter Karriereseiten.

Lädt jede Seite in einem echten Browser, sammelt alle Netzwerkanfragen und das HTML
und sucht darin nach bekannten ATS-Signaturen. Zusätzlich werden öffentliche
ATS-APIs mit naheliegenden Firmenkürzeln abgefragt.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

import requests
from playwright.async_api import async_playwright

HERE = Path(__file__).parent
OUT = HERE / "result.json"
TXT = HERE / "result.txt"

SIGS = {
    "workday": re.compile(r"([a-z0-9-]+)\.(wd\d+)\.myworkday(?:jobs|site)\.com/(?:[a-z]{2}-[A-Z]{2}/)?(?:wday/cxs/[a-z0-9-]+/)?([A-Za-z0-9_-]+)"),
    "greenhouse": re.compile(r"(?:boards|job-boards)(?:-api)?\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([A-Za-z0-9_-]+)"),
    "lever": re.compile(r"(?:jobs|api)\.lever\.co/(?:v0/postings/)?([A-Za-z0-9_.-]+)"),
    "smartrecruiters": re.compile(r"(?:jobs|careers|api)\.smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.-]+)"),
    "personio": re.compile(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
    "recruitee": re.compile(r"([a-z0-9-]+)\.recruitee\.com"),
    "successfactors": re.compile(r"(rmkcdn\.successfactors\.com|jobs2web|career\d*\.successfactors\.(?:eu|com)[^\"' ]*|sapsf\.com)"),
    "eightfold": re.compile(r"([a-z0-9.-]*eightfold\.ai[^\"' ]{0,60}|/api/apply/v2/jobs[^\"' ]{0,80})"),
    "phenom": re.compile(r"(phenompeople\.com|cdn\.phenompeople|/widgets\b|phApp\.)"),
    "avature": re.compile(r"([a-z0-9-]+\.avature\.net)"),
    "taleo": re.compile(r"([a-z0-9-]+\.taleo\.net)"),
    "icims": re.compile(r"([a-z0-9-]+\.icims\.com)"),
    "oracle": re.compile(r"([a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com[^\"' ]{0,80})"),
    "teamtailor": re.compile(r"([a-z0-9-]+\.teamtailor\.com)"),
    "workable": re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
    "softgarden": re.compile(r"([a-z0-9-]+\.softgarden\.io)"),
    "dvinci": re.compile(r"([a-z0-9-]+\.dvinci(?:-easy)?\.(?:de|com))"),
    "umantis": re.compile(r"(recruitingapp-\d+\.umantis\.com|[a-z0-9-]+\.umantis\.com)"),
    "beesite": re.compile(r"(beesite|milchundzucker)"),
    "jobvite": re.compile(r"jobs\.jobvite\.com/([A-Za-z0-9_-]+)"),
    "csod": re.compile(r"([a-z0-9-]+\.csod\.com)"),
    "radancy": re.compile(r"(tbcdn\.talentbrew\.com|radancy)"),
    "join": re.compile(r"join\.com/companies/([A-Za-z0-9_-]+)"),
}

JOBLINK = re.compile(r"(job|stelle|position|vacanc|career|karriere|opening)", re.I)


def slugs(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9 ]", "", name.lower().replace("&", "and"))
    parts = base.split()
    c = {"".join(parts), "-".join(parts), parts[0]}
    return [s for s in c if s]


def api_probe(name: str) -> list[str]:
    hits = []
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (praktikum-ws27 probe)"
    for slug in slugs(name):
        tests = {
            "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
            "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1",
            "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
            "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
            "personio": f"https://{slug}.jobs.personio.de/xml",
            "recruitee": f"https://{slug}.recruitee.com/api/offers/",
        }
        for ats, url in tests.items():
            try:
                r = s.get(url, timeout=10)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            t = r.text
            n = None
            try:
                j = r.json()
                if ats == "greenhouse":
                    n = len(j.get("jobs", []))
                elif ats == "lever":
                    n = len(j) if isinstance(j, list) else None
                elif ats == "smartrecruiters":
                    n = j.get("totalFound")
                elif ats == "ashby":
                    n = len(j.get("jobs", []))
                elif ats == "recruitee":
                    n = len(j.get("offers", []))
            except Exception:
                if ats == "personio" and "<position" in t:
                    n = t.count("<position>")
            if n:
                hits.append(f"{ats}:{slug} ({n} Stellen)")
    return hits


async def visit(browser, name, url, sem):
    async with sem:
        res = {"name": name, "url": url, "final": None, "title": None, "sigs": {}, "links": [], "error": None}
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = await ctx.new_page()
        reqs = []
        page.on("request", lambda r: reqs.append(r.url))
        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_timeout(9000)
            res["final"] = page.url
            res["title"] = await page.title()
            html = await page.content()
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            frames = [f.url for f in page.frames]
        except Exception as e:
            res["error"] = str(e)[:200]
            html, links, frames = "", [], []
        blob = "\n".join(reqs + frames + links) + "\n" + html
        for k, rx in SIGS.items():
            found = sorted({m if isinstance(m, str) else "/".join(m) for m in rx.findall(blob)})
            if found:
                res["sigs"][k] = found[:6]
        seen = []
        for l in links:
            if JOBLINK.search(l) and l not in seen and not l.startswith("mailto"):
                seen.append(l)
        res["links"] = seen[:25]
        res["api"] = await asyncio.to_thread(api_probe, name)
        await ctx.close()
        print(f"fertig: {name} -> {list(res['sigs'])} {res['api']}", flush=True)
        return res


async def main():
    firms = []
    for line in (HERE / "firms.txt").read_text().splitlines():
        if "|" in line:
            n, u = line.split("|", 1)
            firms.append((n.strip(), u.strip()))
    if len(sys.argv) > 1:
        firms = [f for f in firms if f[0] in sys.argv[1:]]
    sem = asyncio.Semaphore(5)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        results = await asyncio.gather(*(visit(browser, n, u, sem) for n, u in firms))
        await browser.close()
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    lines = []
    for r in results:
        lines.append(f"## {r['name']}  {r['url']}")
        lines.append(f"   final: {r['final']}  title: {r['title']}  error: {r['error']}")
        for k, v in r["sigs"].items():
            lines.append(f"   {k}: {v}")
        if r["api"]:
            lines.append(f"   api: {r['api']}")
        for l in r["links"][:12]:
            lines.append(f"   link: {l}")
    TXT.write_text("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
