"""Bewertet Stellen per Stichwort-Regeln: BWL-Bezug ja/nein und Fachbereich.

Reihenfolge: Titel (+ Abteilung aus dem Karrieresystem) entscheidet. Ist der Titel neutral
("Internship (m/f/d)"), entscheidet das Verhältnis kaufmännischer zu technischen Begriffen im Text.
"""
from __future__ import annotations

import re

FACH_RULES = [
    ("Vertrieb & Kundenmanagement", r"vertrieb|\bsales|key account|account manag|kundenbetreuung|customer success|customer service|"
     r"innendienst|pricing|order management|auftragsabwicklung|e-?commerce|retail|ventas|comercial|kam\b"),
    ("Einkauf & Supply Chain", r"einkauf|procurement|purchas|beschaffung|sourcing|supply|logisti|\bscm\b|materialwirtschaft|"
     r"disposition|lieferanten|zoll|customs|transport|spedition|operations|compras|cadena de suministro|log[ií]stica|aprovisionamiento"),
    ("Personal (HR)", r"\bhr\b|human resources|personal(?!is)|recruit|talent|\bpeople\b|learning (&|and) development|l&d|employer branding|"
     r"recursos humanos|rrhh|selecci[oó]n"),
    ("Marketing & Kommunikation", r"marketing|kommunikation|communication|\bpr\b|public relations|social media|brand|content|"
     r"event|storytelling|redaktion|comunicaci[oó]n|growth|crm marketing|media"),
    ("Finanzen & Controlling", r"controlling|controller|finance|finanz|accounting|buchhaltung|rechnungswesen|\bsteuer|\btax|"
     r"treasury|audit|revision|reporting|ifrs|financial|bilanz|investment|m&a|private equity|venture|banking|"
     r"finanzas|contabilidad|auditor[ií]a|fiscal|tesorer[ií]a|corporate finance|valuation|equity research|asset management"),
    ("Beratung (Consulting)", r"consult|beratung|berater|advisory|consultor[ií]a"),
    ("Produktmanagement", r"product manag|produktmanag|product owner|product marketing|category manag"),
    ("Business Development & Strategie", r"business development|strateg|corporate development|innovation|geschäftsentwicklung|"
     r"portfolio|entrepreneur|venture|desarrollo de negocio|estrategia|general management|ceo office|office of the ceo|"
     r"chief of staff|business intelligence|market research|marktforschung"),
    ("Projektmanagement", r"projekt|project|\bpmo\b|program management|koordination|coordination|proyectos"),
    ("Digitalisierung, Daten & KI", r"digital|data analy|datenanaly|datenmanag|analytics|\bbi\b|power ?bi|business analyst|\bsap\b|\bcrm\b|"
     r"ai strateg|ai product|ai business|ai transformation|ki-strateg|ki-projekt|prozessmanag|prozessanaly|prozessoptim|"
     r"process manag|process excellence|business process|process improvement|it-?consult|it project|it business|servicenow|"
     r"análisis de datos|transformaci[oó]n digital|automation consultant"),
    ("Recht & Compliance", r"legal|\brecht|compliance|contract|vertragsmanagement|export control|governance|datenschutz|"
     r"privacy|jur[ií]dico|abogad"),
]
FACH_RES = [(n, re.compile(p, re.I)) for n, p in FACH_RULES]
TECH = re.compile(
    r"engineer|ingenieur|ingeniero|(?<!personal)(?<!geschäfts)(?<!konzern)(?<!unternehmens)(?<!organisations)(?<!wirtschafts)(?<!-)entwickl(?!ungsbank|ungszusammenarbeit|ungspolit|ungshilfe)|(?<!business )(?<!product )(?<!talent )(?<!people )(?<!organizational )development(?! cooperation| (?:&|and) outreach| finance)|developer|software|firmware|hardware|embedded|elektro|electric|"
    r"mechani|mechatron|konstrukt|physik|physics|chemi|verfahrenstechn|process engineering|"
    r"halbleiter|semiconductor|verification|simulation|frontend|backend|full.?stack|devops|cyber|"
    r"robot|fertigung|manufacturing|produktion|production|montage|wartung|maintenance|\blabor\b|\blab\b|"
    r"r&d|research scientist|forschung|programmier|informatik|computer science|sensor|messtechn|material|"
    r"cad\b|machine learning|ml engineer|data scien|deep learning|biolog|pharma|clinical|medical|"
    r"architect|bauingenieur|civil|design engineer|\bux\b|ui designer|graphic design|\bgame|\bgpu|cuda|compiler|kernel|librar|\bllm|mlops|"
    r"\binfra\b|infrastructure|\bdft\b|\basic\b|\bsoc\b|\bchip|silicon|\btest\b|\bqa\b|swqa|computing|reinforcement|tensorrt|"
    r"framework|neural|algorithm|perception|autonomous|linux|networking|research intern|ai research|\bai\b|\bki\b",
    re.I,
)
# Begriffe, die trotz Technik-Wort kaufmännisch sind ("Sales Engineer" bleibt draußen, "Financial Engineering"?)
BWL_TEXT = re.compile(
    r"bwl|betriebswirtschaft|wirtschaftswissenschaft|business administration|economics|business studies|"
    r"wirtschaftsinformatik|business informatics|international management|administración de empresas|"
    r"\bmba\b|kaufmännisch|commercial|finance|marketing|controlling|vertrieb|sales|einkauf|procurement|"
    r"consulting|strategy|strategie", re.I)
TECH_TEXT = re.compile(
    r"maschinenbau|mechanical engineering|elektrotechnik|electrical engineering|informatik|computer science|"
    r"physik|physics|chemie|chemistry|verfahrenstechnik|mechatronik|ingenieur|engineering degree|"
    r"programmier|programming|python|c\+\+|java\b|embedded|cad\b|laborarbeit|computer engineering|gpu|cuda|verilog|"
    r"linux|deep learning|machine learning|pytorch|kubernetes|algorithm", re.I)


def fachbereich(title: str, department: str = "", text: str = "") -> tuple[str | None, int, int]:
    """-> (Fachbereich oder None, kaufmännische Treffer, technische Treffer) für Titel+Abteilung."""
    head = f"{title} {department}"
    found = [(m.start(), n) for n, r in FACH_RES if (m := r.search(head))]
    hits = [n for _, n in sorted(found)]  # zuerst genannter Bereich zählt
    tech = len({m.group(0).lower() for m in TECH.finditer(title)})
    return (hits[0] if hits else None), len(hits), tech


def assess(title: str, department: str, text: str) -> dict:
    fach, n_bwl, n_tech = fachbereich(title, department, text)
    if n_bwl or n_tech:
        relevant = n_bwl > n_tech
        grund = "Titel/Abteilung kaufmännisch" if relevant else "Titel technisch"
    if n_bwl and n_bwl == n_tech:  # Gleichstand ("Sales Engineer"): Text entscheidet
        n_bwl = n_tech = 0
    if n_bwl or n_tech:
        pass
    else:
        body = (text or "")[:6000]
        b = len(BWL_TEXT.findall(body))
        tt = len(TECH_TEXT.findall(body))
        relevant = (b >= 2 and tt == 0) or (b >= 3 and b > tt * 2)
        grund = f"Text: {b} kaufmännische vs. {tt} technische Begriffe"
        if relevant:
            counts = [(len(r.findall(body)), n) for n, r in FACH_RES]
            top = max(counts)
            fach = top[1] if top[0] else None
    return {"relevant": relevant, "grund": grund, "fachbereich": fach or "Sonstiges BWL"}
