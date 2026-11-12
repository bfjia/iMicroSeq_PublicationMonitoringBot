#One-time migration: build researchers.tsv (OpenAlex ids) from the old Google Scholar data.
#
#For every researcher in legacy/results.tsv that has a Scholar profile, take their recent papers with a
#DOI from legacy/allpubsScholar.json (papers Scholar already attributed to them), look each DOI up in
#OpenAlex, find the authorship that matches the researcher's name, and vote on the OpenAlex author id.
#DOI lookups are free on OpenAlex, so this costs almost nothing.
#
#Run from the repo root:  python legacy/MigrateScholarToOpenAlex.py
#Writes researchers.tsv and legacy/migrationReport.md. Re-running overwrites both.
import collections
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import openAlexClient
import researcherRoster

# ---- Configuration ----
resultsFile = "legacy/results.tsv"
scholarJsonFile = "legacy/allpubsScholar.json"
reportFile = "legacy/migrationReport.md"
maxPapersPerResearcher = 15
titleSimilarityCutoff = 0.75
fragmentMaxWorks = 25          # extra ids this small are treated as split-off fragments and added
minVotesForOK = 3              # fewer verified papers than this -> REVIEW
minShareForOK = 0.6            # share of resolved papers that must land on the chosen ids


def normalizeText(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def cleanName(name):
    """'Kerry E. Black, PhD' -> 'Kerry E. Black'"""
    return re.sub(r"\s+", " ", (name or "").split(",")[0]).strip()


def surnameAndInitial(name):
    tokens = normalizeText(cleanName(name)).split()
    if not tokens:
        return "", ""
    return tokens[-1], tokens[0][0]


def extractDOI(url):
    match = re.search(r"(10\.\d{4,9}/[^\s?#&]+)", url or "")
    if not match:
        return None
    doi = urllib.parse.unquote(match.group(1)).rstrip(".")
    doi = re.sub(r"/(full|abstract|pdf|epdf|meta|html|fulltext)$", "", doi, flags=re.I)
    biorxiv = re.match(r"10\.1101/(\d{4}\.\d{2}\.\d{2}\.)?\d+", doi)  # bioRxiv/medRxiv: drop v2, .full, .pdf
    if biorxiv:
        doi = biorxiv.group(0)
    doi = re.sub(r"\.(pdf|html)$", "", doi, flags=re.I)
    return doi.lower()


def lookupWorkByDOI(doi):
    """Try the DOI; on a miss, drop trailing path segments (OUP-style '/8715480' suffixes)."""
    candidate = doi
    for _ in range(3):
        work = openAlexClient.openAlexGet("/works/doi:" + urllib.parse.quote(candidate, safe="/"),
                                          {"select": "id,doi,title,authorships"})
        if work:
            return work
        if candidate.count("/") <= 1:
            return None
        candidate = candidate.rsplit("/", 1)[0]
    return None


def findMatchingAuthorship(work, names):
    """Return the authorship that best matches any of the researcher's names, or None."""
    wanted = [surnameAndInitial(n) for n in names if n]
    best, bestScore = None, 0.0
    for authorship in work.get("authorships", []):
        author = authorship.get("author") or {}
        if not author.get("id"):
            continue
        candidates = [author.get("display_name")] + [authorship.get("raw_author_name")]
        for candidateName in candidates:
            surname, initial = surnameAndInitial(candidateName)
            for wantedSurname, wantedInitial in wanted:
                if not surname or surname != wantedSurname:
                    continue
                score = 1.0 if initial == wantedInitial else 0.7
                score += max(difflib.SequenceMatcher(None, normalizeText(candidateName), normalizeText(n)).ratio()
                             for n in names if n) * 0.1
                if score > bestScore:
                    best, bestScore = authorship, score
    return best


def migrateResearcher(name, scholarID, scholarEntry):
    """Return (row dict, report lines)."""
    scholarName = cleanName(scholarEntry.get("Name", "")) if scholarEntry else ""
    names = [n for n in [cleanName(name), scholarName] if n]
    row = {"Status": "REVIEW", "Name": scholarName or cleanName(name), "OpenAlexIDs": "", "ORCID": "",
           "InstitutionIDs": "", "ScholarID": scholarID, "Notes": ""}
    if not scholarEntry:
        row["Notes"] = "Scholar profile had no stored publications; run AddResearcher.py"
        row["Status"] = "NO_MATCH"
        return row, ["- **" + row["Name"] + "**: no Scholar publications stored -> NO_MATCH"]

    pubs = sorted(scholarEntry["publications"].values(), key=lambda p: str(p.get("year")), reverse=True)
    withDOI = [(extractDOI(p.get("url")), p) for p in pubs]
    withDOI = [(doi, p) for doi, p in withDOI if doi][:maxPapersPerResearcher]

    votes = collections.Counter()
    institutions = collections.Counter()
    orcids = collections.Counter()
    resolved = 0
    for doi, pub in withDOI:
        work = lookupWorkByDOI(doi)
        if not work:
            continue
        similarity = difflib.SequenceMatcher(None, normalizeText(work.get("title")), normalizeText(pub.get("title"))).ratio()
        if similarity < titleSimilarityCutoff:
            continue
        resolved += 1
        authorship = findMatchingAuthorship(work, names)
        if not authorship:
            continue
        authorID = openAlexClient.shortID(authorship["author"]["id"])
        votes[authorID] += 1
        if authorship["author"].get("orcid"):
            orcids[openAlexClient.shortORCID(authorship["author"]["orcid"])] += 1
        for institution in authorship.get("institutions", []):
            if institution.get("id"):
                institutions[openAlexClient.shortID(institution["id"])] += 1

    if not votes:
        row["Status"] = "NO_MATCH"
        row["Notes"] = "No OpenAlex match from " + str(len(withDOI)) + " DOI papers; run AddResearcher.py"
        return row, ["- **" + row["Name"] + "**: " + str(len(withDOI)) + " DOI papers, " + str(resolved)
                     + " resolved, no matching authorship -> NO_MATCH"]

    primary, primaryVotes = votes.most_common(1)[0]
    chosen = [primary]
    possible = []
    for authorID, count in votes.most_common()[1:]:
        author = openAlexClient.openAlexGet("/authors/" + authorID, {"select": "id,display_name,works_count"}) or {}
        worksCount = author.get("works_count", 0)
        label = authorID + " (" + str(author.get("display_name", "?")) + ", " + str(worksCount) + " works, " + str(count) + " votes)"
        if count >= 2 or worksCount <= fragmentMaxWorks:
            chosen.append(authorID)
        else:
            possible.append(label)

    chosenVotes = sum(votes[i] for i in chosen)
    share = chosenVotes / float(resolved) if resolved else 0.0
    if chosenVotes >= minVotesForOK and share >= minShareForOK:
        row["Status"] = "OK"
    frequent = [i for i, c in institutions.most_common() if c >= 2][:6]
    row["InstitutionIDs"] = researcherRoster.joinIDs(frequent or [i for i, _ in institutions.most_common(3)])
    row["OpenAlexIDs"] = researcherRoster.joinIDs(chosen)
    row["ORCID"] = orcids.most_common(1)[0][0] if orcids else ""
    notes = []
    if possible:
        notes.append("possible extra ids: " + "; ".join(possible))
    if row["Status"] != "OK":
        notes.append("weak evidence: " + str(chosenVotes) + "/" + str(resolved) + " verified papers")
    row["Notes"] = " | ".join(notes)

    line = ("- **" + row["Name"] + "** -> " + row["Status"] + ": ids " + row["OpenAlexIDs"] + " (votes "
            + ", ".join(i + "=" + str(votes[i]) for i in chosen) + "; " + str(chosenVotes) + "/" + str(resolved)
            + " resolved papers, " + str(len(withDOI)) + " DOI papers tried)")
    if possible:
        line += "; possible extra: " + "; ".join(possible)
    return row, [line]


def loadResults():
    rows = []
    with open(resultsFile, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\r\n") for line in f][1:]
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2 or not parts[1].strip():
            continue
        rows.append({"Status": parts[0].strip().upper(), "Name": parts[1].strip(),
                     "UserID": parts[2].strip() if len(parts) > 2 else ""})
    return rows


if __name__ == "__main__":
    with open(scholarJsonFile, "r", encoding="utf-8") as f:
        scholarData = json.load(f)

    results = loadResults()
    # Drop duplicate names, keeping the row that has a Scholar id.
    byName = collections.OrderedDict()
    for r in results:
        key = normalizeText(r["Name"])
        if key not in byName or (r["UserID"] and not byName[key]["UserID"]):
            byName[key] = r

    rosterRows, migrated, unmatched = [], [], []
    for r in byName.values():
        if r["UserID"]:
            print("[INFO] Migrating " + r["Name"] + " (" + r["UserID"] + ")")
            row, lines = migrateResearcher(r["Name"], r["UserID"], scholarData.get(r["UserID"]))
            migrated.extend(lines)
            time.sleep(0.2)
        else:
            row = {"Status": "NO_MATCH", "Name": r["Name"], "OpenAlexIDs": "", "ORCID": "", "InstitutionIDs": "",
                   "ScholarID": "", "Notes": "No Scholar profile; not yet searched in OpenAlex"}
            unmatched.append(r["Name"])
        rosterRows.append(row)

    researcherRoster.saveResearchers(rosterRows)
    counts = collections.Counter(row["Status"] for row in rosterRows)
    with open(reportFile, "w", encoding="utf-8") as f:
        f.write("# Scholar -> OpenAlex migration report\n\n")
        f.write("Status counts: " + ", ".join(k + "=" + str(v) for k, v in sorted(counts.items())) + "\n\n")
        f.write("## Researchers with a Scholar profile\n\n" + "\n".join(migrated) + "\n\n")
        f.write("## No Scholar profile (to be searched with AddResearcher.py)\n\n" + "\n".join("- " + n for n in unmatched) + "\n")
    print("[INFO] Wrote " + researcherRoster.rosterFile + " and " + reportFile + ": " + str(dict(counts)))
