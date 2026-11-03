"""Adapter für Bewerbermanagement-Systeme mit öffentlicher Schnittstelle.

Jeder Adapter liefert eine Liste "roher" Stellen:
    url, title, locations (Liste), country_hints (ISO-Codes), posted (YYYY-MM-DD),
    department, text (falls schon vorhanden), modell, intern (System sagt "Praktikum")
und kann bei Bedarf die Detailseite nachladen (detail()).

Konfiguration je Firma in companies.yaml, z. B.:
    - name: Beispiel AG
      ats: workday
      url: https://beispiel.wd3.myworkdayjobs.com/External
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urljoin, urlparse

from .common import clean, html_to_text, parse_date


def _uniq(items: list[dict]) -> list[dict]:
    out, seen = [], set()
    for j in items:
        if j["url"] not in seen:
            seen.add(j["url"])
            out.append(j)
    return out


def _search_terms(comp: dict, settings: dict) -> list[str]:
    return comp.get("suchbegriffe") or settings.get("suchbegriffe") or ["intern", "praktikum"]


# --------------------------------------------------------------------------- Workday
class Workday:
    """https://<tenant>.wd<N>.myworkdayjobs.com/<site>  (auch mit /de-DE/ o. Ä. davor)"""

    def _parts(self, comp):
        u = urlparse(comp["url"])
        tenant = comp.get("tenant") or u.netloc.split(".")[0]
        segs = [s for s in u.path.split("/") if s and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", s)]
        site = comp.get("site") or segs[0]
        base = f"{u.scheme}://{u.netloc}"
        return base, tenant, site

    def list(self, http, comp, settings):
        base, tenant, site = self._parts(comp)
        api = f"{base}/wday/cxs/{tenant}/{site}/jobs"
        out = []
        for term in _search_terms(comp, settings):
            offset = 0
            while offset < 2000:
                body = {"appliedFacets": comp.get("facets", {}), "limit": 20, "offset": offset, "searchText": term}
                data = http.json(api, method="POST", json=body, headers={"Content-Type": "application/json"})
                posts = data.get("jobPostings") or []
                for p in posts:
                    if not p.get("externalPath"):
                        continue
                    out.append({
                        "url": f"{base}/{site}{p['externalPath']}",
                        "title": clean(p.get("title")),
                        "locations": [p.get("locationsText") or ""],
                        "posted": parse_date(p.get("postedOn")),
                        "ref": p["externalPath"],
                    })
                if len(posts) < 20:
                    break
                offset += 20
        return _uniq(out)

    def detail(self, http, comp, job):
        base, tenant, site = self._parts(comp)
        d = http.json(f"{base}/wday/cxs/{tenant}/{site}{job['ref']}").get("jobPostingInfo", {})
        locs = [d.get("location") or ""] + list(d.get("additionalLocations") or [])
        country = (d.get("country") or {}).get("descriptor")
        return {
            "text": html_to_text(d.get("jobDescription")),
            "locations": [l for l in locs if l] + ([country] if country and len(locs) <= 1 else []),
            "posted": parse_date(d.get("startDate")) or job.get("posted"),
            "extra": clean(d.get("timeType")),
        }


# --------------------------------------------------------------------------- Greenhouse
class Greenhouse:
    """boards.greenhouse.io/<token> oder job-boards.greenhouse.io/<token>"""

    def list(self, http, comp, settings):
        token = comp.get("token") or urlparse(comp["url"]).path.strip("/").split("/")[0]
        data = http.json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
        out = []
        for j in data.get("jobs", []):
            locs = [(j.get("location") or {}).get("name") or ""]
            locs += [o.get("location") or o.get("name") or "" for o in j.get("offices") or []]
            out.append({
                "url": j.get("absolute_url"),
                "title": clean(j.get("title")),
                "locations": [l for l in locs if l],
                "posted": parse_date(j.get("first_published") or j.get("updated_at")),
                "department": ", ".join(d.get("name", "") for d in j.get("departments") or []),
                "text": html_to_text(j.get("content")),
            })
        return out


# --------------------------------------------------------------------------- Lever
class Lever:
    """jobs.lever.co/<site> oder jobs.eu.lever.co/<site>"""

    def list(self, http, comp, settings):
        u = urlparse(comp["url"])
        site = comp.get("site") or u.path.strip("/").split("/")[0]
        api = "https://api.eu.lever.co" if ".eu." in u.netloc else "https://api.lever.co"
        data = http.json(f"{api}/v0/postings/{site}?mode=json")
        out = []
        for j in data:
            cat = j.get("categories") or {}
            locs = list(cat.get("allLocations") or []) or [cat.get("location") or ""]
            lists = "\n".join(f"{l.get('text', '')}\n{html_to_text(l.get('content'))}" for l in j.get("lists") or [])
            out.append({
                "url": j.get("hostedUrl"),
                "title": clean(j.get("text")),
                "locations": locs,
                "country_hints": [j["country"]] if j.get("country") else [],
                "posted": parse_date(j.get("createdAt")),
                "department": ", ".join(x for x in (cat.get("department"), cat.get("team")) if x),
                "text": "\n".join([j.get("descriptionPlain") or "", lists, j.get("additionalPlain") or "",
                                   cat.get("commitment") or ""]),
                "modell": {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Präsenz"}.get(j.get("workplaceType") or ""),
                "intern": "intern" in (cat.get("commitment") or "").lower(),
            })
        return out


# --------------------------------------------------------------------------- SmartRecruiters
class SmartRecruiters:
    """jobs.smartrecruiters.com/<CompanyId>"""

    def _cid(self, comp):
        return comp.get("company_id") or urlparse(comp["url"]).path.strip("/").split("/")[0]

    def list(self, http, comp, settings):
        cid = self._cid(comp)
        out = []
        for term in _search_terms(comp, settings):
            offset = 0
            while offset < 1000:
                q = urlencode({"q": term, "limit": 100, "offset": offset})
                data = http.json(f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?{q}")
                items = data.get("content") or []
                for p in items:
                    loc = p.get("location") or {}
                    out.append({
                        "url": f"https://jobs.smartrecruiters.com/{cid}/{p['id']}",
                        "title": clean(p.get("name")),
                        "locations": [loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)],
                        "country_hints": [loc["country"].upper()] if loc.get("country") else [],
                        "posted": parse_date(p.get("releasedDate")),
                        "department": (p.get("department") or {}).get("label") or "",
                        "modell": "Remote" if loc.get("remote") else ("Hybrid" if loc.get("hybrid") else None),
                        "intern": "intern" in json.dumps(p.get("typeOfEmployment") or {}).lower(),
                        "ref": p["id"],
                    })
                if len(items) < 100:
                    break
                offset += 100
        return _uniq(out)

    def detail(self, http, comp, job):
        d = http.json(f"https://api.smartrecruiters.com/v1/companies/{self._cid(comp)}/postings/{job['ref']}")
        sec = (d.get("jobAd") or {}).get("sections") or {}
        text = "\n".join(html_to_text((sec.get(k) or {}).get("text")) for k in
                         ("companyDescription", "jobDescription", "qualifications", "additionalInformation"))
        return {"text": text}


# --------------------------------------------------------------------------- Ashby
class Ashby:
    """jobs.ashbyhq.com/<org>"""

    def list(self, http, comp, settings):
        org = comp.get("org") or urlparse(comp["url"]).path.strip("/").split("/")[0]
        data = http.json(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=false")
        out = []
        for j in data.get("jobs", []):
            if j.get("isListed") is False:
                continue
            locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
            addr = ((j.get("address") or {}).get("postalAddress") or {})
            hints = [addr["addressCountry"]] if addr.get("addressCountry") else []
            out.append({
                "url": j.get("jobUrl"),
                "title": clean(j.get("title")),
                "locations": [l for l in locs if l] + ([f"{addr.get('addressLocality', '')}, {addr['addressCountry']}"] if addr.get("addressCountry") else []),
                "country_hints": hints if len(hints) == 1 and len(hints[0]) == 2 else [],
                "posted": parse_date(j.get("publishedAt")),
                "department": ", ".join(x for x in (j.get("department"), j.get("team")) if x),
                "text": j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
                "modell": {"Remote": "Remote", "Hybrid": "Hybrid", "OnSite": "Präsenz"}.get(j.get("workplaceType") or "")
                or ("Remote" if j.get("isRemote") else None),
                "intern": (j.get("employmentType") or "").lower() == "intern",
            })
        return out


# --------------------------------------------------------------------------- Personio
class Personio:
    """<firma>.jobs.personio.de (oder .com)"""

    def list(self, http, comp, settings):
        u = urlparse(comp["url"] if "://" in comp["url"] else "https://" + comp["url"])
        base = f"https://{u.netloc}"
        r = http.get(f"{base}/xml?language={comp.get('language', 'en')}")
        root = ET.fromstring(r.content)
        out = []
        for p in root.iter("position"):
            g = lambda tag: clean(p.findtext(tag))  # noqa: E731
            offices = [g("office")] + [clean(o.text) for o in p.findall("./additionalOffices/office")]
            text = "\n".join(f"{clean(d.findtext('name'))}\n{html_to_text(d.findtext('value'))}"
                             for d in p.findall("./jobDescriptions/jobDescription"))
            out.append({
                "url": f"{base}/job/{g('id')}",
                "title": g("name"),
                "locations": [o for o in offices if o],
                "posted": parse_date(g("createdAt")),
                "department": g("department"),
                "text": text + "\n" + g("schedule"),
                "intern": g("employmentType").lower() == "intern",
            })
        return out


# --------------------------------------------------------------------------- Recruitee
class Recruitee:
    """<firma>.recruitee.com"""

    def list(self, http, comp, settings):
        u = urlparse(comp["url"] if "://" in comp["url"] else "https://" + comp["url"])
        data = http.json(f"https://{u.netloc}/api/offers/")
        out = []
        for j in data.get("offers", []):
            locs = [", ".join(x for x in (l.get("city"), l.get("country")) if x) for l in j.get("locations") or []]
            locs = locs or [", ".join(x for x in (j.get("city"), j.get("country")) if x)]
            hints = list({(l.get("country_code") or "").upper() for l in j.get("locations") or [] if l.get("country_code")})
            if not hints and j.get("country_code"):
                hints = [j["country_code"].upper()]
            out.append({
                "url": j.get("careers_url"),
                "title": clean(j.get("title")),
                "locations": locs,
                "country_hints": hints,
                "posted": parse_date(j.get("published_at") or j.get("created_at")),
                "department": j.get("department") or "",
                "text": html_to_text(j.get("description")) + "\n" + html_to_text(j.get("requirements")),
                "modell": "Remote" if j.get("remote") else ("Hybrid" if j.get("hybrid") else None),
                "intern": "intern" in (j.get("employment_type_code") or "").lower(),
            })
        return out


# --------------------------------------------------------------------------- SAP SuccessFactors (Career Site Builder)
class SuccessFactors:
    """Karriereseiten im Stil jobs.<firma>.com/search/?q=  (SAP SuccessFactors RMK/CSB)"""

    ROW = re.compile(r'<tr[^>]*class="[^"]*data-row[^"]*"[^>]*>(.*?)</tr>', re.S | re.I)
    LINK = re.compile(r'<a[^>]+href="([^"]*/job/[^"]+)"[^>]*class="[^"]*jobTitle-link[^"]*"[^>]*>(.*?)</a>|'
                      r'<a[^>]+class="[^"]*jobTitle-link[^"]*"[^>]+href="([^"]*/job/[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
    LOC = re.compile(r'class="[^"]*jobLocation[^"]*"[^>]*>(.*?)</span>', re.S | re.I)
    DATE = re.compile(r'class="[^"]*jobDate[^"]*"[^>]*>(.*?)</span>', re.S | re.I)

    def list(self, http, comp, settings):
        u = urlparse(comp["url"])
        base = f"{u.scheme}://{u.netloc}"
        locale = comp.get("locale", "en_US")
        out = []
        for term in _search_terms(comp, settings):
            for start in range(0, comp.get("max_rows", 500), 25):
                q = urlencode({"q": term, "locale": locale, "startrow": start,
                               "sortColumn": "referencedate", "sortDirection": "desc"})
                raw = http.get(f"{base}/search/?{q}", headers={"Accept": "text/html"}).text
                rows = self.ROW.findall(raw)
                if not rows:  # anderes Layout: alle Links auf /job/... nehmen
                    rows = [m.group(0) for m in re.finditer(r'<a[^>]+href="[^"]*/job/[^"]+"[^>]*>.*?</a>', raw, re.S | re.I)]
                    rows = [r if "jobTitle-link" in r else r.replace("<a ", '<a class="jobTitle-link" ', 1) for r in rows]
                    if start == 0 and term == _search_terms(comp, settings)[0]:
                        print(f"    [successfactors] keine Tabellenzeilen; {len(rows)} /job/-Links; "
                              f"Seite {len(raw)} Zeichen, Anfang: {clean(html_to_text(raw))[:160]!r}")
                for row in rows:
                    m = self.LINK.search(row)
                    if not m:
                        continue
                    href, title = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
                    loc = self.LOC.search(row)
                    dt = self.DATE.search(row)
                    out.append({
                        "url": urljoin(base, href.split("?")[0]),
                        "title": clean(html_to_text(title)),
                        "locations": [clean(html_to_text(loc.group(1)))] if loc else [],
                        "posted": parse_date(html_to_text(dt.group(1))) if dt else None,
                    })
                if len(rows) < 25:
                    break
        return _uniq(out)

    def detail(self, http, comp, job):
        return fetch_html_detail(http, job["url"])


# --------------------------------------------------------------------------- Eightfold
class Eightfold:
    """Karriereseiten von Eightfold (z. B. jobs.<firma>.com/careers), braucht 'domain'"""

    def list(self, http, comp, settings):
        u = urlparse(comp["url"])
        base = f"{u.scheme}://{u.netloc}"
        domain = comp.get("domain") or ".".join(u.netloc.split(".")[-2:])
        out = []
        for term in _search_terms(comp, settings):
            for start in range(0, comp.get("max_rows", 500), 10):
                q = urlencode({"domain": domain, "start": start, "num": 10, "query": term, "sort_by": "timestamp"})
                data = http.json(f"{base}/api/apply/v2/jobs?{q}")
                pos = data.get("positions") or []
                for p in pos:
                    out.append({
                        "url": p.get("canonicalPositionUrl") or f"{base}/careers/job/{p['id']}",
                        "title": clean(p.get("name")),
                        "locations": list(p.get("locations") or []) or [p.get("location") or ""],
                        "posted": parse_date(p.get("t_create")),
                        "department": p.get("department") or "",
                        "ref": p["id"],
                    })
                if len(pos) < 10:
                    break
        return _uniq(out)

    def detail(self, http, comp, job):
        u = urlparse(comp["url"])
        domain = comp.get("domain") or ".".join(u.netloc.split(".")[-2:])
        d = http.json(f"{u.scheme}://{u.netloc}/api/apply/v2/jobs/{job['ref']}?domain={domain}")
        return {"text": html_to_text(d.get("job_description"))}


# --------------------------------------------------------------------------- Detailseite per HTML (ohne Browser)
def _jsonld(raw: str) -> dict:
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', raw, re.S | re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:  # noqa: BLE001
            continue
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
                    return x
                if "@graph" in x:
                    stack.append(x["@graph"])
    return {}


def jsonld_locations(jp: dict) -> tuple[list[str], list[str]]:
    locs, hints = [], []
    jl = jp.get("jobLocation") or []
    for l in (jl if isinstance(jl, list) else [jl]):
        a = (l or {}).get("address") or {}
        if isinstance(a, str):
            locs.append(a)
            continue
        country = a.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        locs.append(", ".join(str(x) for x in (a.get("addressLocality"), a.get("addressRegion"), country) if x))
        if isinstance(country, str) and len(country) == 2:
            hints.append(country.upper())
    return [l for l in locs if l], hints


def fetch_html_detail(http, url: str) -> dict:
    raw = http.get(url, headers={"Accept": "text/html"}).text
    jp = _jsonld(raw)
    locs, hints = jsonld_locations(jp) if jp else ([], [])
    m = re.search(r'<(?:span|div)[^>]+(?:itemprop="description"|class="[^"]*jobdescription[^"]*")[^>]*>(.*)', raw, re.S | re.I)
    text = html_to_text(jp.get("description")) if jp.get("description") else ""
    if len(text) < 300:
        alt = html_to_text(m.group(1)[:200_000]) if m else html_to_text(raw)
        text = alt if len(alt) > len(text) else text
    return {"text": text[:12000], "locations": locs, "country_hints": hints,
            "posted": parse_date(jp.get("datePosted")) if jp else None}


ADAPTERS = {
    "workday": Workday(), "greenhouse": Greenhouse(), "lever": Lever(), "smartrecruiters": SmartRecruiters(),
    "ashby": Ashby(), "personio": Personio(), "recruitee": Recruitee(), "successfactors": SuccessFactors(),
    "eightfold": Eightfold(),
}


def detect_ats(url: str) -> str | None:
    """Erkennt das System an der Adresse der Karriereseite."""
    h = urlparse(url).netloc.lower()
    if "myworkdayjobs.com" in h or "myworkdaysite.com" in h:
        return "workday"
    if "greenhouse.io" in h:
        return "greenhouse"
    if "lever.co" in h:
        return "lever"
    if "smartrecruiters.com" in h:
        return "smartrecruiters"
    if "ashbyhq.com" in h:
        return "ashby"
    if "personio." in h:
        return "personio"
    if "recruitee.com" in h:
        return "recruitee"
    return None
