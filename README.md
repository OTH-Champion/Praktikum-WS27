# Praktikum WS27

Praktika für BWLer weltweit, mit Visa- und Förder-Infos. Die Seite sammelt Praktika (Internships, Prácticas) ausgewählter Unternehmen in Europa (EU, EWR, Schweiz, UK), in südamerikanischen Wirtschaftszentren, in Australien & Neuseeland und in Asiens großen Wirtschaftszentren. Sie aktualisiert sich montags und donnerstags automatisch.

## So funktioniert es

1. Der GitHub-Workflow (`.github/workflows/update.yml`) startet zweimal pro Woche und zusätzlich, sobald sich etwas in `config/` oder `scraper/` ändert.
2. Für jede Firma aus `config/companies.yaml` wird die Stellenliste abgerufen. Bei bekannten Bewerbermanagement-Systemen (Workday, SuccessFactors, SmartRecruiters, Greenhouse, Lever, Ashby, Personio, Recruitee, Eightfold) läuft das über deren Schnittstelle: schnell und mit sauberen Orts- und Datumsangaben. Alle anderen Seiten öffnet ein echter Browser (`ats: browser`).
3. Es bleiben nur Praktika übrig (Werkstudent, Trainee, Einstiegsstellen und Abschlussarbeiten fliegen raus).
4. Ortsfilter: Länder und Städte aus `config/laender.yaml`. In Asien und Südamerika zählen nur die dort eingetragenen Städte.
5. Sprachfilter: nur Anzeigen auf Deutsch, Englisch oder Spanisch (`config/settings.yaml`).
6. Stichwort-Regeln entscheiden über den BWL-Bezug und lesen Gesamtdauer, Wochenstunden, Start und Arbeitsmodell aus der Anzeige.
7. Das Ergebnis landet in `docs/data/jobs.json`, die Länderinfos in `docs/data/laender.json`. Die Website in `docs/` zeigt beides an (GitHub Pages).

Bereits bewertete Stellen werden nicht erneut bewertet. Stellen, die auf der Karriereseite verschwinden, verschwinden auch hier.

## Einmalig einrichten

*Settings → Pages → Build and deployment*: Source „Deploy from a branch“, Branch `main`, Ordner `/docs`, „Save“. Die Seite ist danach unter `https://oth-champion.github.io/Praktikum-WS27/` erreichbar.

## Häufige Aufgaben

**Firma hinzufügen:** `config/companies.yaml` öffnen, Stift-Symbol, Eintrag ergänzen (Name, `ats`, `url`), „Commit changes“. Der Abruf startet danach automatisch.

**Visa- oder Förderinfos ändern:** `config/laender.yaml`. Dort stehen auch die Hub-Städte und deutsche Städtenamen.

**Stichwörter, Sprachen, Fachbereiche:** `config/settings.yaml`.

**Update sofort starten:** Reiter *Actions* → *Praktika aktualisieren* → *Run workflow*.

**Fehlersuche:** Beim manuellen Start „debug“ anhaken. Dann steht im Ordner `debug/` für jede Firma, welche Stelle aus welchem Grund behalten oder aussortiert wurde.

## Lokal ausprobieren

```bash
pip install -r requirements.txt
python -m tests.test_offline          # prüft alle Adapter ohne Internet
python -m scraper.run --list-only --only SAP
```
