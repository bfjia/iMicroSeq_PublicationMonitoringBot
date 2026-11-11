#Find new publications by the monitored researchers using the OpenAlex API.
#
#Reads researchers.tsv, fetches each researcher's works from the last lookbackDays, updates the
#append-only state in allpubs.json, and writes:
#  delta.json  - confident new publications (read by GoogleSheetAPIConnector.py)
#  msg.md      - the Slack announcement (same layout as the old Google Scholar bot)
#  review.md   - new publications we could not confirm belong to the researcher (empty if none)
#  summary.md  - one-line run summary plus warnings
#Nothing is written unless every researcher was fetched successfully.
import datetime
import json
import os
import re
import shutil
import unicodedata
from dateutil import parser

from openAlexClient import listWorks, shortID
from researcherRoster import monitoredResearchers, splitIDs

# ---- Configuration ----
rosterFile = 'researchers.tsv'
jsonFile = 'allpubs.json'
lastJsonFile = 'last_allpubs.json'
deltaJsonFile = 'delta.json'
msgFile = 'msg.md'
reviewFile = 'review.md'
summaryFile = 'summary.md'
# How far back to look for publications (replaces the old hardcoded year >= 2025).
lookbackDays = 365
# More confident new items than this in one run is suspicious (profile merge, mass re-index): hold them all for review.
maxNewPerRun = 40
# A new item whose OpenAlex record was created more than this many days ago was re-attributed, not newly published.
lateIndexDays = 30
# Co-authors (surname + first initial) a new item must share with the researcher's known publications to count as confident.
minSharedCoauthors = 2
workFields = 'id,doi,title,display_name,type,publication_date,created_date,primary_location,authorships'
# OpenAlex work types never stored or announced, e.g. ['dataset', 'software', 'peer-review', 'erratum'].
# Empty = announce every type (articles, reviews, preprints, chapters, datasets, software, ...).
ignoredTypes = []
# Supplementary-file deposits (e.g. Figshare "Additional file 3 of <paper>") are not publications; skip them entirely.
ignoredTitlePattern = re.compile(r'^\s*(additional file|supplementary (file|material|table|figure|data|information))\b', re.IGNORECASE)
nameSuffixes = ['jr', 'sr', 'ii', 'iii', 'iv']


#save json data
def saveJson(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


#load json data
def loadJson(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def saveText(text, filename):
    with open(filename, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def normalizeDOI(doi):
    """'https://doi.org/10.1128/MRA.0012' -> '10.1128/mra.0012'. None/'' -> None."""
    if not doi:
        return None
    doi = doi.strip().lower()
    match = re.search(r'(10\.\d{4,9}/\S+)', doi)
    return match.group(1) if match else None


def recordDOI(record):
    """DOI of a stored record. Older (Google Scholar era) records have no 'doi' field, so fall back to a doi.org url."""
    doi = normalizeDOI(record.get('doi'))
    if doi:
        return doi
    url = record.get('url') or ""
    return normalizeDOI(url) if "doi.org/" in url.lower() else None


def workTitle(work):
    return (work.get('display_name') or work.get('title') or "Untitled").strip()


def workAuthorIDs(work):
    """Short ids of every author on a work (authors without an id are skipped)."""
    return [shortID((a.get('author') or {}).get('id')) for a in (work.get('authorships') or []) if (a.get('author') or {}).get('id')]


def authorshipsFor(work, authorIDs):
    return [a for a in (work.get('authorships') or []) if shortID((a.get('author') or {}).get('id')) in authorIDs]


def mapWorkToRecord(work, authorID):
    """Convert an OpenAlex work into the publication record stored in allpubs.json, from the point of view of authorID."""
    location = work.get('primary_location') or {}
    source = location.get('source') or {}
    authorships = work.get('authorships') or []
    authors = ", ".join((a.get('author') or {}).get('display_name') or a.get('raw_author_name') or "" for a in authorships)
    doi = normalizeDOI(work.get('doi'))
    if doi:
        url = "https://doi.org/" + doi
    else:
        url = location.get('landing_page_url') or work.get('id')
    firstOrLast = any(a.get('author_position') in ('first', 'last') for a in authorshipsFor(work, [authorID]))
    return {
        "title": workTitle(work),
        "year": work.get('publication_date'),
        "publisher": source.get('display_name') or None,
        "author": authors,
        "url": url,
        "firstOrLast": firstOrLast,
        "datasource": "OpenAlex",
        "type": work.get('type'),
        "doi": doi,
        "created": (work.get('created_date') or "")[:10] or None
    }


def normalizePersonName(name):
    """'Tim Angus McAllister' / 'TA McAllister' -> 'mcallister t'. Returns '' when it can't tell (single token, non-Latin)."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"['’`]", "", text)
    text = re.sub(r"[^A-Za-z\-\s]", " ", text).lower()
    tokens = [t.strip("-") for t in text.split() if t.strip("-") and t.strip("-") not in nameSuffixes]
    if len(tokens) < 2:
        return ""
    return tokens[-1] + " " + tokens[0][0]


def authorNameKeys(authorString):
    """Set of normalized names from a comma-joined author string."""
    keys = set()
    for name in (authorString or "").split(","):
        key = normalizePersonName(name)
        if key:
            keys.add(key)
    return keys


def daysBetween(dateString, today):
    try:
        return (today - parser.parse(dateString).date()).days
    except Exception:
        return None


def isDoubtfulMatch(work, researcher, knownPublications, monitoredIDToName, today):
    """Decide whether a new work really belongs to this researcher.

    knownPublications: list of the researcher's previously stored records (any of their ids).
    monitoredIDToName: {OpenAlex author id: roster Name} for every monitored researcher.
    Returns (isDoubtful, reason). The reason explains the decision either way."""
    researcherIDs = splitIDs(researcher.get('OpenAlexIDs'))
    name = researcher.get('Name')

    # Re-attribution: an already-published paper that OpenAlex has had for a while only now shows up
    # under this person. Both dates must be old: OpenAlex often creates a record at DOI registration,
    # months before the publication date, and those are normal new papers.
    created = (work.get('created_date') or "")[:10]
    age = daysBetween(created, today) if created else None
    publishedAge = daysBetween(work.get('publication_date') or "", today)
    if age is not None and age > lateIndexDays and publishedAge is not None and publishedAge > lateIndexDays:
        return True, ("OpenAlex indexed this " + str(age) + " days ago (published " + str(work.get('publication_date'))
                      + "); it only now appears under this researcher")

    # (a) affiliation on the researcher's own authorship matches the roster InstitutionIDs.
    rosterInstitutions = set(splitIDs(researcher.get('InstitutionIDs')))
    listedInstitutions = []
    for authorship in authorshipsFor(work, researcherIDs):
        for institution in authorship.get('institutions') or []:
            ids = set([shortID(institution.get('id'))] + [shortID(i) for i in institution.get('lineage') or []])
            listedInstitutions.append(institution.get('display_name') or shortID(institution.get('id')))
            if ids & rosterInstitutions:
                return False, "affiliation match (" + (institution.get('display_name') or shortID(institution.get('id'))) + ")"

    # (b) another monitored researcher is a co-author.
    for authorID in workAuthorIDs(work):
        if authorID in researcherIDs:
            continue
        otherName = monitoredIDToName.get(authorID)
        if otherName and otherName != name:
            return False, "co-authored with monitored researcher " + otherName

    # (c) enough co-authors already appear in the researcher's earlier publications.
    ownKeys = set([normalizePersonName(name)])
    for authorship in authorshipsFor(work, researcherIDs):
        ownKeys.add(normalizePersonName((authorship.get('author') or {}).get('display_name')))
    knownCoauthors = set()
    for record in knownPublications:
        knownCoauthors |= authorNameKeys(record.get('author'))
    coauthors = set()
    for authorship in work.get('authorships') or []:
        if shortID((authorship.get('author') or {}).get('id')) in researcherIDs:
            continue
        coauthors.add(normalizePersonName((authorship.get('author') or {}).get('display_name') or authorship.get('raw_author_name')))
    shared = sorted((coauthors & knownCoauthors) - ownKeys - set([""]))
    if len(shared) >= minSharedCoauthors:
        return False, str(len(shared)) + " co-authors seen in earlier publications (" + ", ".join(shared[:3]) + ")"

    affiliationText = ("listed affiliation: " + "; ".join(sorted(set(listedInstitutions)))) if listedInstitutions else "no affiliation listed"
    if not rosterInstitutions:
        affiliationText = affiliationText + ", no InstitutionIDs on the roster row"
    return True, ("Could not confirm the author: " + affiliationText + "; no other monitored researcher is a co-author; "
                  + str(len(shared)) + " co-author(s) seen in their earlier publications")


def buildMonitoredIDMap(researchers):
    monitoredIDToName = {}
    for researcher in researchers:
        for authorID in splitIDs(researcher['OpenAlexIDs']):
            if authorID in monitoredIDToName and monitoredIDToName[authorID] != researcher['Name']:
                print("[WARNING] OpenAlex id " + authorID + " is listed for both " + monitoredIDToName[authorID]
                      + " and " + researcher['Name'] + " in " + rosterFile)
            monitoredIDToName.setdefault(authorID, researcher['Name'])
    return monitoredIDToName


def fetchWorksForResearcher(researcher, fromDate):
    """All works (any type) for the researcher's OpenAlex ids published on/after fromDate. Raises on API failure."""
    filterString = "authorships.author.id:" + "|".join(splitIDs(researcher['OpenAlexIDs'])) + ",from_publication_date:" + fromDate
    return listWorks(filterString, select=workFields, sort='publication_date:desc')


def buildStateAndFindNew(researchers, worksByResearcher, lastState, monitoredIDToName, today):
    """Merge fetched works into the append-only state and collect the new items.

    worksByResearcher is a list parallel to researchers. Returns (allPubs, newItems, zeroWorkNames)
    where each new item is {authorID, Name, pubID, record, work, doubtful, reason}."""
    allPubs = {}
    newItems = []
    zeroWorkNames = []

    for researcher, works in zip(researchers, worksByResearcher):
        name = researcher['Name']
        researcherIDs = splitIDs(researcher['OpenAlexIDs'])

        # Everything already known under any of this researcher's ids.
        knownPublications = []
        knownKeys = set()
        knownDOIs = set()
        for authorID in researcherIDs:
            for pubID, record in lastState.get(authorID, {}).get('publications', {}).items():
                knownPublications.append(record)
                knownKeys.add(pubID)
                doi = recordDOI(record)
                if doi:
                    knownDOIs.add(doi)

        # Silent-gap warning: works within the lookback window were stored before, but none came back today.
        # (Someone who simply hasn't published this year is not flagged.)
        windowStart = (today - datetime.timedelta(days=lookbackDays)).isoformat()
        if len(works) == 0 and any((record.get('year') or "") >= windowStart for record in knownPublications):
            zeroWorkNames.append(name)

        # Carry forward every stored publication (append-only).
        for authorID in researcherIDs:
            allPubs[authorID] = {
                'Name': name,
                'total_publications': "0",
                'publications': dict(lastState.get(authorID, {}).get('publications', {}))
            }

        seenKeys = set()
        seenDOIs = set()
        researcherNew = 0
        for work in works:
            pubID = shortID(work.get('id'))
            title = workTitle(work)
            if not pubID:
                continue
            if ignoredTitlePattern.search(title):
                print("[DEBUG] Skipping supplementary file " + pubID + ": " + title)
                continue
            if work.get('type') in ignoredTypes:
                print("[DEBUG] Skipping " + str(work.get('type')) + " " + pubID + " (type listed in ignoredTypes): " + title)
                continue

            presentIDs = workAuthorIDs(work)
            matchedIDs = [authorID for authorID in researcherIDs if authorID in presentIDs]
            if not matchedIDs:
                print("[WARNING] " + pubID + " was returned for " + name + " but none of their ids are in its author list "
                      + "(author list may be truncated); filing it under " + researcherIDs[0])
                matchedIDs = [researcherIDs[0]]

            for authorID in matchedIDs:
                record = mapWorkToRecord(work, authorID)
                publications = allPubs[authorID]['publications']
                if pubID not in publications:
                    publications[pubID] = record  # existing records are never rewritten

                if authorID not in lastState:
                    continue  # new to the surveillance list: recorded silently below
                if pubID in lastState[authorID].get('publications', {}):
                    continue
                doi = record['doi']
                if pubID in knownKeys or (doi and doi in knownDOIs):
                    print("[DEBUG] " + pubID + " is already known under another of " + name + "'s ids.")
                    continue
                if pubID in seenKeys or (doi and doi in seenDOIs):
                    continue
                seenKeys.add(pubID)
                if doi:
                    seenDOIs.add(doi)

                doubtful, reason = isDoubtfulMatch(work, researcher, knownPublications, monitoredIDToName, today)
                newItems.append({'authorID': authorID, 'Name': name, 'pubID': pubID, 'record': publications[pubID],
                                 'work': work, 'doubtful': doubtful, 'reason': reason})
                researcherNew = researcherNew + 1
                print("[INFO] Found new publication " + pubID + " under " + authorID + " titled: " + title
                      + (" [NEEDS REVIEW: " + reason + "]" if doubtful else " [" + reason + "]"))

        for authorID in researcherIDs:
            allPubs[authorID]['total_publications'] = str(len(allPubs[authorID]['publications']))
            if authorID not in lastState:
                print("[INFO] " + name + " (" + authorID + ") is a new author added to the surveillance list, ignoring until next time.")
        if researcherNew > 0:
            print("[INFO] " + name + " has " + str(researcherNew) + " new publication(s)!")
        else:
            print("[INFO] " + name + " has no new publications.")

    # Keep ids that are no longer monitored, so re-activating someone can never re-announce their back-catalog.
    for authorID in lastState:
        if authorID not in allPubs:
            allPubs[authorID] = lastState[authorID]

    return allPubs, newItems, zeroWorkNames


def applyFloodBreaker(newItems):
    """If too many confident items arrived at once, move all of them to review. Returns (newItems, warning or '')."""
    confident = [item for item in newItems if not item['doubtful']]
    if len(confident) <= maxNewPerRun:
        return newItems, ""
    warning = ("Flood breaker: " + str(len(confident)) + " new publications in one run is more than maxNewPerRun ("
               + str(maxNewPerRun) + "), so none were announced. This usually means OpenAlex merged profiles or re-indexed a batch.")
    for item in confident:
        item['doubtful'] = True
        item['reason'] = warning + " (otherwise: " + item['reason'] + ")"
    return newItems, warning


def buildDelta(confidentItems):
    """Legacy delta.json shape: {authorID: {Name, total_new, publications: {pubID: record}}}."""
    delta = {}
    for item in confidentItems:
        entry = delta.setdefault(item['authorID'], {'Name': item['Name'], 'total_new': "0", 'publications': {}})
        entry['publications'][item['pubID']] = item['record']
    for authorID in delta:
        delta[authorID]['total_new'] = str(len(delta[authorID]['publications']))
    return delta


def typeTag(pub):
    pubType = pub.get('type')
    if not pubType or pubType == 'article':
        return ""
    return " [" + pubType + "]"


def hasVenue(pub):
    return pub.get('publisher') not in (None, "", "Unknown")


def messageTitle(pub):
    """Title for a message line; a trailing period is dropped so the layout's own '. ' doesn't double it."""
    return pub["title"].rstrip().rstrip(".")


def formatPubLine(pub):
    line = "  * " + messageTitle(pub) + typeTag(pub) + ". "
    if hasVenue(pub):
        line = line + " Published in " + pub['publisher'] + ". "
    if pub.get('url'):
        line = line + " " + pub['url'] + "\n"
    else:
        line = line + "URL unavailable.\n"
    return line


def formatSlackMsg2(deltaJson):
    if len(deltaJson) == 0: #if theres nothing in the json file, return the appropariate msg
        return "[INFO]\nNo new publication found."

    #first we switch from author-id based index to publication title based index, combining researchers on shared titles.
    publicationTitleKVP = {}
    for authorID in deltaJson:
        for pubID in deltaJson[authorID]['publications']:
            pub = deltaJson[authorID]['publications'][pubID]
            titleKey = (pub['title'].strip().lower(), pub.get('type'))
            name = deltaJson[authorID]["Name"]
            if titleKey not in publicationTitleKVP: #new pub
                publicationTitleKVP[titleKey] = dict(pub)
                publicationTitleKVP[titleKey]["Name"] = name
            elif name not in publicationTitleKVP[titleKey]["Name"].split(", "): #existing pub, append new researcher to existing list
                publicationTitleKVP[titleKey]["Name"] = publicationTitleKVP[titleKey]["Name"] + ", " + name

    if len(publicationTitleKVP) == 0:
        return "[INFO]\nNo new publication found."

    #then reindex the publications with the Name as the index.
    publicationNameKVP = {}
    for titleKey in publicationTitleKVP:
        pub = publicationTitleKVP[titleKey]
        publicationNameKVP.setdefault(pub["Name"], []).append(pub)

    #Format the output msg
    Msg = ""
    for name in publicationNameKVP:
        if len(publicationNameKVP[name]) == 1: #only 1 publication
            Msg = Msg + name + " has a new publication: \n"
            Msg = Msg + formatPubLine(publicationNameKVP[name][0])
        else: #multiple pubs for same researcher
            Msg = Msg + name + " has new publications: \n"
            for pub in publicationNameKVP[name]:
                Msg = Msg + formatPubLine(pub)
                Msg = Msg + "\n"
        Msg = Msg + "\n"
    return Msg


def formatReviewMsg(reviewItems):
    """Slack text for doubtful items, or '' when there is nothing to review."""
    if len(reviewItems) == 0:
        return ""
    Msg = ("*Needs review* - " + str(len(reviewItems)) + " publication(s) matched a monitored researcher but could not be confirmed. "
           + "They were not added to the Google Sheet.\n\n")
    for item in reviewItems:
        pub = item['record']
        Msg = Msg + "  * " + item['Name'] + ": " + messageTitle(pub) + typeTag(pub) + ". "
        if hasVenue(pub):
            Msg = Msg + "Published in " + pub['publisher'] + ". "
        Msg = Msg + (pub.get('url') or "URL unavailable.") + "\n"
        Msg = Msg + ("    Matched OpenAlex author " + item['authorID'] + " (https://openalex.org/" + item['authorID'] + "). Reason: "
                     + item['reason'] + "\n\n")
    return Msg


def formatSummary(today, researchers, newCount, reviewCount, zeroWorkNames, floodWarning):
    profileCount = sum(len(splitIDs(r['OpenAlexIDs'])) for r in researchers)
    summary = ("[INFO] Run summary " + today.isoformat() + ": checked " + str(len(researchers)) + " researchers ("
               + str(profileCount) + " OpenAlex profiles); " + str(newCount) + " new, " + str(reviewCount) + " need review.\n")
    if zeroWorkNames:
        summary = summary + ("[WARNING] OpenAlex returned no works today for: " + ", ".join(zeroWorkNames)
                             + ", although works from the last " + str(lookbackDays) + " days were stored before."
                             + " OpenAlex may have merged or split their profile - re-run AddResearcher.py for them.\n")
    if floodWarning:
        summary = summary + "[WARNING] " + floodWarning + "\n"
    return summary


def runPipeline(today=None):
    """The whole daily run. Raises (and writes nothing) if any fetch fails or nothing at all comes back."""
    today = today or datetime.date.today()
    if os.path.exists(jsonFile):
        shutil.copy2(jsonFile, lastJsonFile)
    lastState = loadJson(lastJsonFile)

    researchers = monitoredResearchers(rosterFile)
    if len(researchers) == 0:
        raise RuntimeError("[ERROR] No monitored researchers (Status OK with an OpenAlex id) in " + rosterFile)
    monitoredIDToName = buildMonitoredIDMap(researchers)
    fromDate = (today - datetime.timedelta(days=lookbackDays)).isoformat()

    print("[INFO] Indexing publications since " + fromDate + "...")
    worksByResearcher = []
    for researcher in researchers:
        print("[INFO] Looking for publications by " + researcher['Name'] + " (" + researcher['OpenAlexIDs'] + ")")
        works = fetchWorksForResearcher(researcher, fromDate)  # any failure propagates: nothing gets written
        print("[DEBUG] " + str(len(works)) + " works returned.")
        worksByResearcher.append(works)

    if sum(len(works) for works in worksByResearcher) == 0:
        raise RuntimeError("[ERROR] OpenAlex returned zero works for all " + str(len(researchers))
                           + " researchers; refusing to write state. Check the API and " + rosterFile + ".")

    print("[INFO] Looking for anything new...")
    allPubs, newItems, zeroWorkNames = buildStateAndFindNew(researchers, worksByResearcher, lastState, monitoredIDToName, today)
    newItems, floodWarning = applyFloodBreaker(newItems)
    if floodWarning:
        print("[WARNING] " + floodWarning)
    confidentItems = [item for item in newItems if not item['doubtful']]
    reviewItems = [item for item in newItems if item['doubtful']]

    delta = buildDelta(confidentItems)
    msg = formatSlackMsg2(delta)
    reviewMsg = formatReviewMsg(reviewItems)
    summary = formatSummary(today, researchers, len(confidentItems), len(reviewItems), zeroWorkNames, floodWarning)

    saveJson(allPubs, jsonFile)
    saveJson(delta, deltaJsonFile)
    saveText(msg, msgFile)
    saveText(reviewMsg, reviewFile)
    saveText(summary, summaryFile)
    print(summary.rstrip("\n"))
    return {'allPubs': allPubs, 'delta': delta, 'msg': msg, 'review': reviewMsg, 'summary': summary,
            'confidentItems': confidentItems, 'reviewItems': reviewItems}


if __name__ == "__main__":
    runPipeline()
