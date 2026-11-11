#Read and write researchers.tsv - the list of people the bot monitors.
#
#Columns (tab separated, one header row):
#  Status          OK (monitored) | REVIEW (candidate found, waiting for a human) | NO_MATCH | INACTIVE
#  Name            the name used in Slack and the Google Sheet
#  OpenAlexIDs     one or more OpenAlex author ids, separated by |   e.g. A5042633786|A5129961035
#  ORCID           bare ORCID, e.g. 0000-0002-8266-6513 (optional)
#  InstitutionIDs  OpenAlex institution ids the person publishes from, separated by | (optional)
#  ScholarID       old Google Scholar user id, kept for reference only (optional)
#  Notes           free text; AddResearcher.py writes runner-up candidates here
import os

rosterFile = "researchers.tsv"
rosterColumns = ["Status", "Name", "OpenAlexIDs", "ORCID", "InstitutionIDs", "ScholarID", "Notes"]
validStatuses = ["OK", "REVIEW", "NO_MATCH", "INACTIVE"]


def splitIDs(value):
    """'A1| A2 |' -> ['A1', 'A2']"""
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def joinIDs(ids):
    """Join ids with |, dropping blanks and duplicates but keeping order."""
    seen = []
    for i in ids:
        i = (i or "").strip()
        if i and i not in seen:
            seen.append(i)
    return "|".join(seen)


def loadResearchers(path=rosterFile):
    """Return a list of row dicts (all columns present, values stripped)."""
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\r\n") for line in f]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split("\t")]
    for lineNumber, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        values = line.split("\t")
        row = {column: "" for column in rosterColumns}
        for column, value in zip(header, values):
            row[column] = value.strip()
        row["Status"] = row["Status"].upper()
        if row["Status"] not in validStatuses:
            print("[WARNING] " + path + " line " + str(lineNumber) + ": unknown Status '" + row["Status"]
                  + "' for " + row["Name"] + " - treating as INACTIVE.")
            row["Status"] = "INACTIVE"
        rows.append(row)
    return rows


def saveResearchers(rows, path=rosterFile):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(rosterColumns) + "\n")
        for row in rows:
            f.write("\t".join((row.get(column) or "").replace("\t", " ").replace("\n", " ") for column in rosterColumns) + "\n")


def monitoredResearchers(path=rosterFile):
    """Rows with Status OK and at least one OpenAlex id."""
    return [row for row in loadResearchers(path) if row["Status"] == "OK" and splitIDs(row["OpenAlexIDs"])]
