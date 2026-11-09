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
    "gupy": re.compile(r"([a-z0-9-]+\.gupy\.io)"),
}

TK = {"name", "title", "jobTitle", "job_title", "positionTitle", "postingTitle", "displayName", "Title", "RecruitPostName", "JobTitle"}
IK = {"id", "jobId", "job_id", "jobReqId", "reqId", "requisitionId", "displayJobId", "Id", "PostId", "JobId", "slug", "reference"}
UK = {"url", "jobUrl", "applyUrl", "externalUrl", "link", "href", "PostURL", "canonicalPositionUrl", "positionUrl"}
JOBLINK = re.compile(r"(job|stelle|position|vacanc|career|karriere|opening)", re.I)
# Merkmale von Bot-Schutz/Sperrseiten (Text oder Header)
BLOCK = re.compile(r"(Access Denied|You don't have permission to access|Request unsuccessful\. Incapsula|"
                   r"Pardon Our Interruption|Just a moment\.\.\.|cf-chl|challenge-platform|captcha|"
                   r"Attention Required! \| Cloudflare|Sorry, you have been blocked|bot detection|"
                   r"Reference #\d+\.[0-9a-f]+|errors\.edgesuite\.net|The requested URL was rejected)", re.I)
# Links, denen der Prüflauf eine Ebene tiefer folgt (Stellenbörse hinter der Karriereseite)
HOP = re.compile(r"(stellenangebot|stellenbörse|jobsuche|job search|search jobs|find (a )?job|offene stellen|"
                 r"open positions|vacanc|current openings|job offers|ofertas|empleo|vagas|oportunidades|"
                 r"all jobs|alle jobs|jobbörse|career opportunities|see jobs|view jobs|explore jobs|search for jobs|"
                 r"^careers?$|^karriere$|^jobs$|work with us|join us|join our team|trabaja con nosotros|trabaje con nosotros|"
                 r"trabalhe conosco|carreiras?|karijer|zapošljavanje|posao|ljudski potencijali|apply now|working at|"
                 r"job opportunities|stellenangebote|empleos?|portal laboral)", re.I)
SHOTS = HERE / "shots"


def plain_get(url: str) -> dict:
    """Abruf ohne Browser, wie ihn die Stellen-Adapter machen."""
    try:
        r = requests.get(url, timeout=25, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml", "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})
        m = BLOCK.search(r.text[:200000])
        return {"status": r.status_code, "final": r.url, "server": r.headers.get("server", ""),
                "len": len(r.text), "block": m.group(0) if m else ""}
    except Exception as e:
        return {"status": None, "error": f"{e.__class__.__name__}: {str(e)[:120]}"}


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
                r = s.get(url, timeout=6)
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
    out, done = [], set()
    for i, u in enumerate(urls):
        if u in done:
            continue
        done.add(u)
        r = await visit(browser, name, u, sem, tag=f"{i}")
        out.append(r)
        if i == 0:  # der Karriereseite eine Ebene tiefer folgen
            for j, h in enumerate(r.get("hops", [])[:2]):
                if h not in done and h not in urls:
                    done.add(h)
                    out.append(await visit(browser, name + " (verlinkt)", h, sem, tag=f"h{j}"))
    return out


async def visit(browser, name, url, sem, tag="0"):
    async with sem:
        res = {"name": name, "url": url, "final": None, "title": None, "sigs": {}, "links": [], "error": None,
               "status": None, "block": "", "text": "", "plain": await asyncio.to_thread(plain_get, url), "hops": []}
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            locale="de-DE",
        )
        page = await ctx.new_page()
        reqs = []
        jsons = []
        bad = []
        page.on("request", lambda r: reqs.append(r.url))
        page.on("requestfailed", lambda r: bad.append(f"FEHLER {r.failure} {r.url[:140]}"))

        async def on_resp(resp):
            if resp.status >= 400:
                bad.append(f"{resp.status} {resp.url[:140]}")
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
            resp = await page.goto(url, timeout=90000, wait_until="domcontentloaded")
            res["status"] = resp.status if resp else None
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
            pairs = await page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 80)])")
            links = [h for h, _ in pairs]
            frames = [f.url for f in page.frames]
            body = await page.evaluate("document.body ? document.body.innerText : ''")
            res["text"] = re.sub(r"\s+", " ", body)[:600]
            m = BLOCK.search(html[:300000]) or BLOCK.search(res["title"] or "")
            res["block"] = m.group(0) if m else ""
            res["alllinks"] = list(dict.fromkeys(f"{t[:50]} -> {h}" for h, t in pairs if h.startswith("http")))[:120]
            res["hops"] = [h for h, t in pairs if (HOP.search(t.strip()) or HOP.search(h)) and h.startswith("http") and h.split("#")[0] != url
                           and not h.startswith("mailto")]
            res["hops"] = list(dict.fromkeys(res["hops"]))[:4]
            try:
                SHOTS.mkdir(exist_ok=True)
                fn = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") + f"-{tag}.jpg"
                await page.screenshot(path=str(SHOTS / fn), type="jpeg", quality=45)
                res["shot"] = f"probe/shots/{fn}"
            except Exception:
                pass
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
        res["bad"] = bad[:15]
        res["nreq"] = len(reqs)
        res["api"] = []
        await ctx.close()
        print(f"fertig: {name} -> {list(res['sigs'])} {res['api']}", flush=True)
        return res


def extra_api():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (praktikum-ws27 probe)"
    out = []
    for line in [l for l in (HERE / "workday.txt").read_text().split() if l.count("/") == 2]:
        t, w, site = line.split("/")
        url = f"https://{t}.{w}.myworkdayjobs.com/wday/cxs/{t}/{site}/jobs"
        try:
            r = s.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}, timeout=20)
            out.append(f"workday {line}: {r.status_code} total={r.json().get('total') if r.ok else ''}")
        except Exception as e:
            out.append(f"workday {line}: ERR {e}")
    names = [l.split("|", 1)[0].strip() for l in (HERE / "firms.txt").read_text().splitlines() if "|" in l]
    names += (HERE / "slugs.txt").read_text().split() if (HERE / "slugs.txt").exists() else []
    for slug in ((HERE / "sr.txt").read_text().split() if (HERE / "sr.txt").exists() else []):
        try:
            r = s.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?q=intern&limit=5", timeout=15)
            j = r.json() if r.ok else {}
            ex = [p["name"] + " @ " + p.get("location", {}).get("city", "") + " / " + p.get("company", {}).get("name", "") for p in j.get("content", [])[:3]]
            out.append(f"sr {slug}: {j.get('totalFound', r.status_code)} {ex}")
        except Exception as e:
            out.append(f"sr {slug}: ERR {e}")
    for nm in names:
        try:
            out.append(f"slugs {nm}: {api_probe(nm)}")
        except Exception as e:
            out.append(f"slugs {nm}: ERR {e}")
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
        browser = await p.chromium.launch()  # headless, wie der Stellen-Abruf
        nested = await asyncio.gather(*(visit_multi(browser, n, u, sem) for n, u in firms))
        await browser.close()
    results = [r for grp in nested for r in grp]
    results.append({"name": "_API", "url": "", "final": None, "title": None, "sigs": {}, "links": [], "error": None,
                    "patterns": [], "api": extra_api()})
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    lines = []
    for r in results:
        lines.append(f"## {r['name']}  {r['url']}")
        lines.append(f"   final: {r['final']}  status: {r.get('status')}  title: {r['title']}  error: {r['error']}")
        lines.append(f"   ohne Browser: {r.get('plain')}")
        if r.get("block"):
            lines.append(f"   SPERRE: {r['block']}")
        lines.append(f"   text: {r.get('text', '')[:400]}")
        for h in r.get("hops", []):
            lines.append(f"   folgt: {h}")
        for b in r.get("bad", []):
            lines.append(f"   antwort: {b}")
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
