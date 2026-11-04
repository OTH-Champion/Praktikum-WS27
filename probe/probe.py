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
    "successfactors": re.compile(r"(rmkcdn\.successfactors\.com|jobs2web|career\d*\.successfactors\.(?:eu|com)[^\"'\s<>]*|sapsf\.com)"),
    "eightfold": re.compile(r"([a-z0-9.-]*eightfold\.ai[^\"'\s<>]{0,60}|/api/apply/v2/jobs[^\"'\s<>]{0,80})"),
    "phenom": re.compile(r"(phenompeople\.com|cdn\.phenompeople|/widgets\b|phApp\.)"),
    "avature": re.compile(r"([a-z0-9-]+\.avature\.net)"),
    "taleo": re.compile(r"([a-z0-9-]+\.taleo\.net)"),
    "icims": re.compile(r"([a-z0-9-]+\.icims\.com)"),
    "oracle": re.compile(r"([a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com[^\"'\s<>]{0,80})"),
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

TK = {"name", "title", "jobTitle", "job_title", "positionTitle", "postingTitle", "displayName", "Title", "RecruitPostName", "JobTitle"}
IK = {"id", "jobId", "job_id", "jobReqId", "reqId", "requisitionId", "displayJobId", "Id", "PostId", "JobId", "slug", "reference"}
UK = {"url", "jobUrl", "applyUrl", "externalUrl", "link", "href", "PostURL", "canonicalPositionUrl", "positionUrl"}
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


def patterns(links):
    from collections import Counter
    from urllib.parse import urlparse
    c = Counter(); ex = {}
    for l in links:
        u = urlparse(l)
        if not u.path or len(u.path) < 6:
            continue
        pat = re.sub(r"\d{3,}", r"\\d+", u.path)
        pat = re.sub(r"/[^/]*\\d\+[^/]*", lambda m: m.group(0), pat)
        segs = pat.split("/")
        # Slug-Segmente (lang, mit Bindestrichen) vereinheitlichen
        segs = ["[^/]+" if (s.count("-") >= 2 and "\\d+" not in s) else s for s in segs]
        pat = u.netloc + "/".join(segs)
        c[pat] += 1; ex.setdefault(pat, l)
    return [f"{n}x {p}  e.g. {ex[p]}" for p, n in c.most_common(5) if n >= 3]


async def visit_multi(browser, name, urls, sem):
    out = []
    for u in urls:
        out.append(await visit(browser, name, u, sem))
    return out


async def visit(browser, name, url, sem):
    async with sem:
        res = {"name": name, "url": url, "final": None, "title": None, "sigs": {}, "links": [], "error": None}
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = await ctx.new_page()
        reqs = []
        jsons = []
        page.on("request", lambda r: reqs.append(r.url))

        async def on_resp(resp):
            try:
                if "json" not in (resp.headers.get("content-type") or ""):
                    return
                data = await resp.json()
            except Exception:
                return
            hits = []

            def walk(o, d=0):
                if d > 8:
                    return
                if isinstance(o, dict):
                    keys = set(o)
                    if keys & TK and (keys & IK or keys & UK):
                        hits.append(o)
                    for v in o.values():
                        walk(v, d + 1)
                elif isinstance(o, list):
                    for v in o:
                        walk(v, d + 1)
            walk(data)
            if len(hits) >= 3:
                h = hits[0]
                t = next((h[k] for k in TK if k in h), "")
                jsons.append(f"{len(hits)} Treffer in {resp.url[:150]} | keys={sorted(h)[:14]} | z.B. {str(t)[:60]}")
        page.on("response", on_resp)
        try:
            await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            await page.wait_for_timeout(6000)
            for sel in ("#onetrust-reject-all-handler", "#onetrust-accept-btn-handler", "button#CybotCookiebotDialogBodyButtonDecline",
                        "[data-testid='uc-deny-all-button']", "button:has-text('Alle ablehnen')", "button:has-text('Reject all')",
                        "button:has-text('Accept all')", "button:has-text('Alle akzeptieren')"):
                try:
                    if await page.locator(sel).first.is_visible(timeout=300):
                        await page.locator(sel).first.click(timeout=1500)
                        break
                except Exception:
                    pass
            for _ in range(4):
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(1500)
            await page.wait_for_timeout(3000)
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
        res["links"] = [l for l in seen if re.search(r"\d{4,}|job|stelle|vacanc|position|offer", l, re.I)][:30]
        res["patterns"] = patterns(links)
        res["jsons"] = jsons[:4]
        res["api"] = []
        await ctx.close()
        print(f"fertig: {name} -> {list(res['sigs'])} {res['api']}", flush=True)
        return res


def extra_api():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (praktikum-ws27 probe)"
    out = []
    for line in (HERE / "workday.txt").read_text().split():
        t, w, site = line.split("/")
        url = f"https://{t}.{w}.myworkdayjobs.com/wday/cxs/{t}/{site}/jobs"
        try:
            r = s.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}, timeout=20)
            out.append(f"workday {line}: {r.status_code} total={r.json().get('total') if r.ok else ''}")
        except Exception as e:
            out.append(f"workday {line}: ERR {e}")
    for nm in ["Marriott", "Hilton", "Accor", "AccorHotel", "IHG", "Hyatt", "Vapiano", "Block House", "blockhouse", "LOsteria",
               "Hans im Glueck", "hansimglueck", "FC Bayern", "fcbayern", "FC Barcelona", "Real Madrid", "Manchester United",
               "Manchester City", "Liverpool FC", "Chelsea FC", "Greenpeace", "greenpeacede"]:
        try:
            out.append(f"slugs {nm}: {api_probe(nm)}")
        except Exception as e:
            out.append(f"slugs {nm}: ERR {e}")
    return out
    for ats, slug in [("gh", "traderepublicbank"), ("gh", "traderepublic"), ("gh", "scalablecapital"), ("gh", "byd"),
                      ("gh", "bolt"), ("gh", "dazn"), ("gh", "spotify"), ("lever", "spotify"), ("lever", "dazn"),
                      ("sr", "Sixt"), ("sr", "Continental"), ("sr", "Aumovio"), ("sr", "RedBull"), ("sr", "ContactEnergy"),
                      ("sr", "ScalableCapital"), ("sr", "DAZN"), ("sr", "airBaltic"), ("sr", "Bolt"), ("sr", "Ryanair")]:
        try:
            if ats == "gh":
                r = s.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=15)
                n = len(r.json().get("jobs", [])) if r.ok else r.status_code
                ex = [j["title"] + " @ " + j.get("location", {}).get("name", "") for j in r.json().get("jobs", [])[:3]] if r.ok else []
            elif ats == "lever":
                r = s.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=15)
                n = len(r.json()) if r.ok else r.status_code
                ex = [j["text"] for j in r.json()[:3]] if r.ok else []
            else:
                r = s.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?q=intern&limit=5", timeout=15)
                j = r.json() if r.ok else {}
                n = j.get("totalFound", r.status_code)
                ex = [p["name"] + " @ " + p.get("location", {}).get("city", "") + " / " + p.get("company", {}).get("name", "") for p in j.get("content", [])[:3]]
            out.append(f"{ats} {slug}: {n} {ex}")
        except Exception as e:
            out.append(f"{ats} {slug}: ERR {e}")
    return out


async def main():
    firms = []
    for line in (HERE / "firms.txt").read_text().splitlines():
        if "|" in line:
            n, u = line.split("|", 1)
            firms.append((n.strip(), [x.strip() for x in u.split("|")]))
    if len(sys.argv) > 1:
        firms = [f for f in firms if f[0] in sys.argv[1:]]
    sem = asyncio.Semaphore(6)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        nested = await asyncio.gather(*(visit_multi(browser, n, u, sem) for n, u in firms))
        await browser.close()
    results = [r for grp in nested for r in grp]
    results.append({"name": "_API", "url": "", "final": None, "title": None, "sigs": {}, "links": [], "error": None,
                    "patterns": [], "api": extra_api()})
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    lines = []
    for r in results:
        lines.append(f"## {r['name']}  {r['url']}")
        lines.append(f"   final: {r['final']}  title: {r['title']}  error: {r['error']}")
        for k, v in r["sigs"].items():
            lines.append(f"   {k}: {v}")
        if r["api"]:
            lines.append(f"   api: {r['api']}")
        for l in r.get("jsons", []):
            lines.append(f"   json: {l}")
        for l in r.get("patterns", []):
            lines.append(f"   pattern: {l}")
        for l in r["links"][:30]:
            lines.append(f"   link: {l}")
    TXT.write_text("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
