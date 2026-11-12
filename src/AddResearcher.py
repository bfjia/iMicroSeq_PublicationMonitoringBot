#Find the OpenAlex profile(s) for a researcher by name and propose the best match for human review.
#
#  python AddResearcher.py "Jane Doe"                       search by name
#  python AddResearcher.py "Jane Doe" 0000-0002-1234-5678   exact lookup by ORCID
#  python AddResearcher.py                                  search every roster row that has no OpenAlex id yet
#
#The researcher is written to researchers.tsv with Status REVIEW (or NO_MATCH). NOTHING is monitored
#until a person checks the candidates in addResearcherReport.md and changes REVIEW to OK.
import difflib
import re
import sys
import time
import unicodedata

import paths
import openAlexClient
import researcherRoster

# ---- Configuration ----
reportFile = paths.addResearcherReportFile
# Tunable settings live in config.py (see the comments there).
from config import (maxCandidates, shownCandidates, minNameScore, homeCountry, recentAffiliationYears,
                    rankWeightName, rankWeightCountry, rankWeightNetwork, networkOverlapCap,
                    fragmentMinNameScore, fragmentMaxWorks, addResearcherPauseSeconds)


def normalizeText(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def nameScore(queryName, candidate):
    """Best similarity between the query and the candidate's display name or alternative names.
    A different surname caps the score, so 'Ranjit Kumar' can't outrank 'Ayush Kumar' on shape alone."""
    query = normalizeText(queryName.split(",")[0])
    querySurname = query.split()[-1] if query else ""
    names = [candidate.get("display_name")] + (candidate.get("display_name_alternatives") or [])
    best = 0.0
    for name in names:
        name = normalizeText(name)
        if not name:
            continue
        score = difflib.SequenceMatcher(None, query, name).ratio()
        if name.split()[-1] != querySurname:
            score = min(score, 0.5)
        elif name.split()[0][:1] == query.split()[0][:1]:
            score = max(score, 0.85)  # same surname + same first initial: 'J. Doe', 'Jane A. Doe'
        best = max(best, score)
    return round(best, 2)


def recentInstitutions(candidate):
    """[(institution id, name, country)] from last-known institutions and recent affiliations."""
    found = []
    for institution in candidate.get("last_known_institutions") or []:
        found.append((openAlexClient.shortID(institution.get("id")), institution.get("display_name"), institution.get("country_code")))
    thisYear = time.gmtime().tm_year
    for affiliation in candidate.get("affiliations") or []:
        institution = affiliation.get("institution") or {}
        if any(year >= thisYear - recentAffiliationYears for year in affiliation.get("years") or []):
            found.append((openAlexClient.shortID(institution.get("id")), institution.get("display_name"), institution.get("country_code")))
    unique = []
    for item in found:
        if item[0] and item[0] not in [u[0] for u in unique]:
            unique.append(item)
    return unique[:6]


def networkOverlap(candidateID, monitoredIDs):
    """(count, sample titles) of the candidate's works co-authored with researchers already monitored."""
    others = [i for i in monitoredIDs if i != candidateID][:99]  # OpenAlex allows up to 100 OR values
    if not others:
        return 0, []
    data = openAlexClient.openAlexGet("/works", {
        "filter": "authorships.author.id:" + candidateID + ",authorships.author.id:" + "|".join(others),
        "sort": "publication_date:desc", "per-page": 3, "select": "title,publication_date"})
    if not data:
        return 0, []
    return data.get("meta", {}).get("count", 0), [w.get("title") for w in data.get("results", [])]


def recentTitles(candidateID):
    data = openAlexClient.openAlexGet("/works", {"filter": "authorships.author.id:" + candidateID,
                                                 "sort": "publication_date:desc", "per-page": 3,
                                                 "select": "title,publication_date"})
    return [(w.get("publication_date") or "")[:4] + " " + (w.get("title") or "") for w in (data or {}).get("results", [])]


def searchCandidates(name, orcid=None):
    select = "id,display_name,display_name_alternatives,orcid,works_count,last_known_institutions,affiliations"
    if orcid:
        data = openAlexClient.openAlexGet("/authors", {"filter": "orcid:" + openAlexClient.shortORCID(orcid), "select": select})
    else:
        data = openAlexClient.openAlexGet("/authors", {"search": name, "per-page": maxCandidates, "select": select})
    return (data or {}).get("results", [])


def scoreCandidates(name, candidates, monitoredIDs):
    scored = []
    for candidate in candidates[:maxCandidates]:
        candidateID = openAlexClient.shortID(candidate["id"])
        institutions = recentInstitutions(candidate)
        score = nameScore(name, candidate)
        overlap, overlapTitles = networkOverlap(candidateID, monitoredIDs) if score >= 0.5 else (0, [])
        inHomeCountry = any(country == homeCountry for _, _, country in institutions)
        # Co-authoring with people already monitored is the strongest signal that this is the right person.
        rank = (rankWeightName * score + rankWeightCountry * (1 if inHomeCountry else 0)
                + rankWeightNetwork * min(overlap, networkOverlapCap) / float(networkOverlapCap))
        scored.append({"id": candidateID, "candidate": candidate, "nameScore": score, "institutions": institutions,
                       "inHomeCountry": inHomeCountry, "overlap": overlap, "overlapTitles": overlapTitles, "rank": round(rank, 2)})
    scored.sort(key=lambda s: (s["rank"], s["candidate"].get("works_count", 0)), reverse=True)
    return scored


def proposeIDs(scored):
    """Best candidate plus same-person fragments: same name, and they share an institution or co-author with the network."""
    best = scored[0]
    bestInstitutions = set(i for i, _, _ in best["institutions"])
    proposed = [best]
    for other in scored[1:]:
        if other["nameScore"] < fragmentMinNameScore:
            continue
        sharesInstitution = bool(bestInstitutions & set(i for i, _, _ in other["institutions"]))
        if sharesInstitution and (other["overlap"] > 0 or other["candidate"].get("works_count", 0) <= fragmentMaxWorks):
            proposed.append(other)
    return proposed


def describe(s):
    c = s["candidate"]
    institutions = "; ".join((n or "?") + (" (" + country + ")" if country else "") for _, n, country in s["institutions"][:3]) or "unknown"
    return ("[" + s["id"] + "](https://openalex.org/" + s["id"] + ") | " + str(c.get("display_name")) + " | "
            + (openAlexClient.shortORCID(c.get("orcid")) or "-") + " | " + institutions + " | "
            + str(c.get("works_count", 0)) + " | " + str(s["overlap"]) + " | " + str(s["nameScore"]) + " | " + str(s["rank"]))


def findRow(rows, name):
    key = normalizeText(name)
    for row in rows:
        if normalizeText(row["Name"]) == key:
            return row
    return None


def addResearcher(name, orcid, rows, monitoredIDs, report):
    print("[INFO] Searching OpenAlex for " + name + (" (ORCID " + orcid + ")" if orcid else ""))
    scored = scoreCandidates(name, searchCandidates(name, orcid), monitoredIDs)

    row = findRow(rows, name)
    if row is None:
        row = {column: "" for column in researcherRoster.rosterColumns}
        row["Name"] = name
        rows.append(row)
    if row["Status"] == "OK":
        print("[WARNING] " + name + " is already monitored (Status OK); leaving the roster row unchanged.")
        report.append("## " + name + "\n\nAlready monitored with ids `" + row["OpenAlexIDs"] + "`; roster not changed.\n")
        return

    report.append("## " + name + "\n")
    if not scored or scored[0]["nameScore"] < minNameScore:
        row["Status"] = "NO_MATCH"
        row["Notes"] = "AddResearcher " + time.strftime("%Y-%m-%d") + ": no convincing OpenAlex match"
        report.append("**No convincing match.** Status set to NO_MATCH. Try again with their ORCID: "
                      "`python AddResearcher.py \"" + name + "\" 0000-0000-0000-0000`.\n")
    else:
        proposed = proposeIDs(scored)
        best = proposed[0]
        row["Status"] = "REVIEW"
        row["OpenAlexIDs"] = researcherRoster.joinIDs([p["id"] for p in proposed])
        row["ORCID"] = openAlexClient.shortORCID(best["candidate"].get("orcid")) or (openAlexClient.shortORCID(orcid) if orcid else "")
        row["InstitutionIDs"] = researcherRoster.joinIDs([i for p in proposed for i, _, _ in p["institutions"]][:6])
        runnerUps = [s["id"] + " " + str(s["candidate"].get("display_name")) for s in scored[1:shownCandidates] if s not in proposed]
        row["Notes"] = ("AddResearcher " + time.strftime("%Y-%m-%d") + ": check before setting OK"
                        + ("; runner-ups: " + ", ".join(runnerUps) if runnerUps else ""))
        report.append("**Proposed:** `" + row["OpenAlexIDs"] + "` (" + str(best["candidate"].get("display_name")) + "). Status set to REVIEW.\n")
        if best["overlap"] == 0:
            report.append("> Warning: the proposed profile has no co-authored papers with anyone already monitored. Check carefully.\n")
        report.append("Recent works of the proposed profile:\n")
        for title in recentTitles(best["id"]):
            report.append("- " + title)
        if best["overlapTitles"]:
            report.append("\nCo-authored with monitored researchers (" + str(best["overlap"]) + " total), e.g.:\n")
            for title in best["overlapTitles"]:
                report.append("- " + str(title))
        report.append("")

    if scored:
        report.append("| OpenAlex id | Name | ORCID | Recent institutions | Works | Co-authored with network | Name score | Rank |")
        report.append("|---|---|---|---|---|---|---|---|")
        for s in scored[:shownCandidates]:
            report.append("| " + describe(s) + " |")
    report.append("")
    print("[INFO] " + name + " -> " + row["Status"] + (" " + row["OpenAlexIDs"] if row["OpenAlexIDs"] else ""))


if __name__ == "__main__":
    rows = researcherRoster.loadResearchers()
    monitoredIDs = [i for row in rows if row["Status"] == "OK" for i in researcherRoster.splitIDs(row["OpenAlexIDs"])]

    if len(sys.argv) > 1:
        targets = [(sys.argv[1].strip(), sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2].strip() else None)]
    else:
        targets = [(row["Name"], row["ORCID"] or None) for row in rows
                   if row["Status"] != "INACTIVE" and not researcherRoster.splitIDs(row["OpenAlexIDs"])]
        print("[INFO] " + str(len(targets)) + " roster rows have no OpenAlex id yet.")

    report = ["# AddResearcher report (" + time.strftime("%Y-%m-%d") + ")\n",
              "Nothing below is monitored yet. For each person: open the proposed profile link, check the recent works "
              "are theirs, then in `researchers.tsv` change `REVIEW` to `OK` (and fix `OpenAlexIDs` if a runner-up is "
              "the right one). Columns: *Co-authored with network* = papers shared with researchers already monitored "
              "(the strongest sign it is the right person).\n"]
    for name, orcid in targets:
        if not name:
            continue
        addResearcher(name, orcid, rows, monitoredIDs, report)
        time.sleep(addResearcherPauseSeconds)

    researcherRoster.saveResearchers(rows)
    paths.ensureDir(reportFile)
    with open(reportFile, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report))
    print("[INFO] Updated " + researcherRoster.rosterFile + "; report written to " + reportFile)
