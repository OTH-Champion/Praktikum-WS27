"""Offline-Test: prüft alle Adapter und den Gesamtablauf mit nachgebauten Antworten.

Aufruf:  python -m tests.test_offline
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from scraper import adapters, run
from scraper.common import load_settings, load_yaml
from scraper.geo import Geo

DESC_DE = ("<p>Für unser Team in München suchen wir ab 01.03.2027 für 6 Monate eine/n Praktikant/in im Controlling. "
           "Du studierst BWL oder Wirtschaftswissenschaften und arbeitest 40 Stunden pro Woche mit uns an Reportings, "
           "Budgetplanung und Analysen. Wir bieten dir ein tolles Team und eine faire Vergütung.</p>")
DESC_EN = ("We are looking for a Marketing Intern for our team. This 6-month internship starts in September 2027 and "
           "is full-time (40 hours per week). You study business administration or economics and you will support "
           "our marketing and communication projects with the team.")
DESC_FR = ("Nous recherchons un stagiaire pour notre équipe à Paris. Vous êtes étudiant en école de commerce et vous "
           "avez une première expérience dans le marketing. Le stage est de six mois.")


def fake_http():
    def json_(url, method="GET", **kw):
        if "myworkdayjobs" in url and url.endswith("/jobs"):
            if kw["json"]["offset"] > 0 or kw["json"]["searchText"] != "intern":
                return {"jobPostings": []}
            return {"jobPostings": [
                {"title": "Intern Controlling (m/f/d)", "externalPath": "/job/Munich/Intern-Controlling_R1", "locationsText": "Munich", "postedOn": "Posted 3 Days Ago"},
                {"title": "Software Engineering Intern", "externalPath": "/job/Munich/SWE_R2", "locationsText": "Munich, Germany", "postedOn": "Posted Today"},
                {"title": "Finance Intern", "externalPath": "/job/Austin/Fin_R3", "locationsText": "Austin, Texas, United States", "postedOn": "Posted Today"},
            ]}
        if "myworkdayjobs" in url and "/job/" in url:
            return {"jobPostingInfo": {"jobDescription": DESC_DE, "location": "Munich", "country": {"descriptor": "Germany"},
                                       "startDate": "2026-10-30", "timeType": "Full time"}}
        if "greenhouse" in url:
            return {"jobs": [
                {"absolute_url": "https://boards.greenhouse.io/x/jobs/1", "title": "Marketing Intern", "location": {"name": "London, United Kingdom"},
                 "content": DESC_EN.replace("<", "&lt;"), "first_published": "2026-10-20T10:00:00Z", "departments": [{"name": "Marketing"}]},
                {"absolute_url": "https://boards.greenhouse.io/x/jobs/2", "title": "Stagiaire Marketing", "location": {"name": "Paris, France"},
                 "content": DESC_FR, "updated_at": "2026-10-20T10:00:00Z", "departments": []},
            ]}
        if "lever.co" in url:
            return [{"text": "Business Development Intern", "hostedUrl": "https://jobs.lever.co/y/abc", "country": "SG",
                     "categories": {"location": "Singapore", "team": "Growth", "commitment": "Internship"},
                     "createdAt": 1793000000000, "descriptionPlain": DESC_EN, "lists": [], "workplaceType": "hybrid"}]
        if "smartrecruiters.com" in url and "/postings/" in url:
            return {"jobAd": {"sections": {"jobDescription": {"text": DESC_EN}}}}
        if "smartrecruiters.com" in url:
            if "offset=0" not in url or "q=intern&" not in url:
                return {"content": []}
            return {"content": [{"id": "77", "name": "Intern Strategy & Consulting", "location": {"city": "Tokyo", "country": "jp"},
                                 "releasedDate": "2026-10-01T00:00:00Z", "department": {"label": "Strategy"}}]}
        if "ashbyhq" in url:
            return {"jobs": [{"title": "Finance Analyst", "employmentType": "Intern", "location": "Madrid", "jobUrl": "https://jobs.ashbyhq.com/z/1",
                              "address": {"postalAddress": {"addressLocality": "Madrid", "addressCountry": "Spain"}},
                              "publishedAt": "2026-10-11T00:00:00Z", "descriptionPlain": DESC_EN, "workplaceType": "OnSite"}]}
        if "recruitee" in url:
            return {"offers": [{"title": "Praktikum Einkauf", "careers_url": "https://r.recruitee.com/o/1", "city": "Wien", "country": "Austria",
                                "country_code": "AT", "description": DESC_DE, "published_at": "2026-10-02 10:00:00 UTC"}]}
        if "/api/jobs-proxy/search" in url:
            assert method == "POST" and "experience_level=studentisches%20Praktikum" in url
            page = int(url.split("page=")[1].split("&")[0])
            rows = [{"requisition_id": "833536", "title": "Business Development & Organizational Development Internship",
                     "job_title": "Praktikum Business Development & Organisationsentwicklung", "city": "Bonn",
                     "experience_level": "studentisches Praktikum", "category": "Zentralfunktionen"}] if page == 1 else [
                    {"requisition_id": "918443", "title": "Flexicum in Administration", "job_title": "Flexikum Verwaltung",
                     "city": "Kiel,Berlin", "experience_level": "studentisches Praktikum"}]
            return {"data": rows, "pagination_info": {"number_of_pages": 2, "page": page}}
        if "/api/apply/v2/jobs/" in url:
            return {"job_description": DESC_EN}
        if "/api/apply/v2/jobs" in url:
            if "start=0" not in url or "query=intern&" not in url:
                return {"positions": []}
            return {"positions": [{"id": 5, "name": "Internship Procurement", "locations": ["Regensburg, Bayern, Germany"],
                                   "t_create": 1793000000, "canonicalPositionUrl": "https://jobs.e.com/careers/job/5"}]}
        raise AssertionError(url)

    def get(url, **kw):
        if "personio" in url:
            xml = (f"<workzag-jobs><position><id>9</id><office>Barcelona</office><name>Intern Sales (m/f/d)</name>"
                   f"<employmentType>intern</employmentType><createdAt>2026-10-05T10:00:00+00:00</createdAt>"
                   f"<jobDescriptions><jobDescription><name>About</name><value><![CDATA[{DESC_EN}]]></value></jobDescription></jobDescriptions>"
                   f"</position></workzag-jobs>")
            return SimpleNamespace(content=xml.encode(), text=xml)
        if "/search/" in url:
            if "startrow=0" not in url or "q=intern&" not in url:
                return SimpleNamespace(text="")
            html = ('<table><tr class="data-row"><td><a href="/job/Zurich-Intern-HR/123/" class="jobTitle-link">Intern HR</a></td>'
                    '<td><span class="jobLocation">Zürich, ZH, CH, 8000</span></td><td><span class="jobDate">Oct 30, 2026</span></td></tr></table>')
            return SimpleNamespace(text=html)
        if "careers.telekom.com/de/jobs/" in url:
            body = DESC_DE.replace('"', '\\"')
            n = len(DESC_DE.encode())
            html = (f'<html><script>self.__next_f.push([1,"{hex(n)[2:]}"])</script>'
                    f'<script>self.__next_f.push([1,"2a:T{n:x},{body}"])</script></html>')
            return SimpleNamespace(text=html)
        if "/job/Zurich" in url:
            return SimpleNamespace(text=f'<html><script type="application/ld+json">{json.dumps({"@type": "JobPosting", "description": DESC_EN, "datePosted": "2026-10-30"})}</script></html>')
        raise AssertionError(url)

    return SimpleNamespace(json=json_, get=get)


def main() -> int:
    settings = load_settings()
    geo = Geo(load_yaml("laender.yaml"))
    http = fake_http()
    comps = [
        {"name": "WD", "ats": "workday", "url": "https://acme.wd3.myworkdayjobs.com/en-US/External"},
        {"name": "GH", "ats": "greenhouse", "url": "https://boards.greenhouse.io/x"},
        {"name": "LV", "ats": "lever", "url": "https://jobs.lever.co/y"},
        {"name": "SR", "ats": "smartrecruiters", "url": "https://jobs.smartrecruiters.com/ACME"},
        {"name": "AS", "ats": "ashby", "url": "https://jobs.ashbyhq.com/z"},
        {"name": "PE", "ats": "personio", "url": "https://acme.jobs.personio.de"},
        {"name": "RE", "ats": "recruitee", "url": "https://r.recruitee.com"},
        {"name": "SF", "ats": "successfactors", "url": "https://jobs.acme.com"},
        {"name": "EF", "ats": "eightfold", "url": "https://jobs.e.com/careers", "domain": "e.com"},
    ]
    # Telekom: Liste über die Schnittstelle (2 Seiten), Beschreibung aus den Next.js-Daten
    tk = adapters.ADAPTERS["telekom"].list(http, {"name": "DT", "url": "https://careers.telekom.com/de/jobs"}, settings)
    assert [j["url"] for j in tk] == [
        "https://careers.telekom.com/de/jobs/business-development-organizational-development-internship-833536",
        "https://careers.telekom.com/de/jobs/flexicum-in-administration-918443"], tk
    assert tk[1]["locations"] == ["Kiel", "Berlin"] and all(j["intern"] for j in tk)
    d = adapters.ADAPTERS["telekom"].detail(http, {}, tk[0])
    assert "Controlling" in d["text"] and "<p>" not in d["text"], d
    from scraper.common import title_is_internship as tii
    assert tii("Flexikum Social Media Content Creator", settings) and tii("Industrial Placement Finance", settings)
    assert not tii("Placement Manager", settings)
    # Warnungen bei ignorierter Suche / nur erster Seite
    w = run.search_warnings({"name": "X"}, "browser", {"gefunden": 20, "praktika": 0}, {"extra": [0, 0], "auto_next_neu": 0})
    assert len(w) == 2, w
    assert not run.search_warnings({"name": "X"}, "browser", {"gefunden": 20, "praktika": 3}, {"extra": [0]})
    print("Telekom- und Warnungs-Tests bestanden.")

    results = {}
    for comp in comps:
        ad = adapters.ADAPTERS[comp["ats"]]
        raw = ad.list(http, comp, settings)
        kept = []
        for r in raw:
            from scraper.common import title_is_internship
            if not (title_is_internship(r["title"], settings) or r.get("intern")):
                continue
            if geo.resolve(r.get("locations") or [], r.get("country_hints"))[1] == "fremd":
                kept.append((r["title"], "Ort fremd (Liste)", None, None))
                continue
            if not r.get("text") and hasattr(ad, "detail"):
                d = ad.detail(http, comp, r)
                r["text"] = d.get("text", "")
                r["locations"] = list(d.get("locations") or []) + list(r.get("locations") or [])
                r["posted"] = r.get("posted") or d.get("posted")
            entry, why = run.evaluate(r, comp, geo, settings)
            kept.append((r["title"], why, entry and entry["orte"], entry and (entry["dauer"], entry["stunden"], entry["start"])))
        results[comp["name"]] = kept
        for k in kept:
            print(comp["name"], k)
    expect = {
        "WD": ["ok", "kein BWL", "Ort"], "GH": ["ok", "Sprache"], "LV": ["ok"], "SR": ["ok"], "AS": ["ok"],
        "PE": ["ok"], "RE": ["ok"], "SF": ["ok"], "EF": ["ok"],
    }
    bad = []
    for name, exp in expect.items():
        got = [w for _, w, _, _ in results[name]]
        if len(got) != len(exp) or any(not g.startswith(e) for g, e in zip(got, exp)):
            bad.append((name, got, exp))
    print("FEHLER:" if bad else "Alle Adapter-Tests bestanden.", bad or "")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
