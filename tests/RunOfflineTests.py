#Offline tests for FindPublications.py. No network, no framework: plain asserts.
#Run from the repo root:  python tests/RunOfflineTests.py
#Fixtures in tests/fixtures/ were captured from the real OpenAlex API (Nov 2026) and trimmed.
import copy
import datetime
import json
import os
import shutil
import sys
import tempfile
import traceback

testsDir = os.path.dirname(os.path.abspath(__file__))
repoDir = os.path.dirname(testsDir)
sys.path.insert(0, repoDir)

import FindPublications as fp
import researcherRoster

# ---- Fixtures ----
fixtureRoster = os.path.join(testsDir, "fixtures", "researchers.tsv")
fixtureWorks = os.path.join(testsDir, "fixtures", "openAlexWorks.json")
today = datetime.date(2026, 11, 11)

with open(fixtureWorks, "r", encoding="utf-8") as f:
    worksByID = dict((fp.shortID(w["id"]), w) for w in json.load(f))

researchers = researcherRoster.monitoredResearchers(fixtureRoster)
mcallister, parkins, hubert = researchers
monitoredIDToName = fp.buildMonitoredIDMap(researchers)


def work(workID, createdDaysAgo=1, **changes):
    """A deep copy of a fixture work, created recently by default so the late-index check doesn't fire."""
    w = copy.deepcopy(worksByID[workID])
    if createdDaysAgo is not None:
        w["created_date"] = (today - datetime.timedelta(days=createdDaysAgo)).isoformat() + "T00:00:00"
    w.update(changes)
    return w


def stateFor(authorID, name, publications=None):
    return {authorID: {"Name": name, "total_publications": str(len(publications or {})), "publications": dict(publications or {})}}


def record(title="Old paper", author="", doi=None, url=None, year="2026-01-01"):
    return {"title": title, "year": year, "publisher": "Old Journal", "author": author, "url": url,
            "firstOrLast": False, "datasource": "OpenAlex", "type": "article", "doi": doi, "created": year}


def findNew(researcherList, worksList, lastState):
    return fp.buildStateAndFindNew(researcherList, worksList, lastState, fp.buildMonitoredIDMap(researcherList), today)


# ---- Mapping ----
def testMapWorkToRecord():
    rec = fp.mapWorkToRecord(worksByID["W7221010631"], "A5042633786")
    assert rec["title"].startswith("Draft genome sequences of Bibersteinia trehalosi"), rec["title"]
    assert rec["year"] == "2026-10-08", rec["year"]
    assert rec["publisher"] == "Microbiology Resource Announcements", rec["publisher"]
    assert "Tim Angus McAllister" in rec["author"] and rec["author"].startswith("Sara Andrés-Lasheras, "), rec["author"]
    assert rec["doi"] is not None and rec["doi"] == rec["doi"].lower() and rec["doi"].startswith("10."), rec["doi"]
    assert rec["url"] == "https://doi.org/" + rec["doi"], rec["url"]
    assert rec["firstOrLast"] is False  # middle author
    assert rec["datasource"] == "OpenAlex" and rec["type"] == "article"
    assert rec["created"] == "2026-10-09", rec["created"]
    assert set(rec.keys()) == set(["title", "year", "publisher", "author", "url", "firstOrLast", "datasource", "type", "doi", "created"])


def testMapWorkFirstOrLastAndType():
    rec = fp.mapWorkToRecord(worksByID["W7154060862"], "A5042633786")
    assert rec["firstOrLast"] is True  # last author on the erratum
    assert rec["type"] == "erratum"
    # same work from the point of view of a different author (first author)
    assert fp.mapWorkToRecord(worksByID["W7154060862"], "A5062116564")["firstOrLast"] is True


def testMapWorkMissingSourceAndDOI():
    rec = fp.mapWorkToRecord(worksByID["W7204137749"], "A5063583896")
    assert rec["publisher"] is None, rec["publisher"]
    w = work("W7204137749", doi=None)
    w["primary_location"]["landing_page_url"] = "https://example.org/landing"
    rec = fp.mapWorkToRecord(w, "A5063583896")
    assert rec["doi"] is None and rec["url"] == "https://example.org/landing", rec
    w["primary_location"] = None
    rec = fp.mapWorkToRecord(w, "A5063583896")
    assert rec["url"] == "https://openalex.org/W7204137749" and rec["publisher"] is None, rec
    assert fp.mapWorkToRecord({"id": "https://openalex.org/W1", "title": None, "display_name": None}, "A1")["title"] == "Untitled"


def testNormalizeHelpers():
    assert fp.normalizeDOI("https://doi.org/10.1128/MRA.00123-26") == "10.1128/mra.00123-26"
    assert fp.normalizeDOI(None) is None and fp.normalizeDOI("") is None
    assert fp.recordDOI({"url": "https://doi.org/10.1234/ABC"}) == "10.1234/abc"  # Scholar-era record without a doi field
    assert fp.recordDOI({"url": "https://example.org/x"}) is None
    assert fp.normalizePersonName("Tim Angus McAllister") == "mcallister t"
    assert fp.normalizePersonName("TA McAllister") == "mcallister t"
    assert fp.normalizePersonName("Christine O’Grady") == "ogrady c"
    assert fp.normalizePersonName("Sara Andrés-Lasheras") == "andres-lasheras s"
    assert fp.normalizePersonName("John Smith Jr.") == "smith j"
    assert fp.normalizePersonName("이장우") == "" and fp.normalizePersonName("Madonna") == ""


# ---- Diff ----
def testNewAuthorIsSilent():
    allPubs, newItems, zero = findNew([mcallister], [[work("W7221010631"), work("W7154060862")]], {})
    assert newItems == [], newItems
    assert set(allPubs["A5042633786"]["publications"].keys()) == set(["W7221010631", "W7154060862"])
    assert allPubs["A5042633786"]["Name"] == "Tim McAllister" and allPubs["A5042633786"]["total_publications"] == "2"
    # next run with the same works: nothing new
    allPubs2, newItems2, _ = findNew([mcallister], [[work("W7221010631"), work("W7154060862")]], allPubs)
    assert newItems2 == [] and allPubs2["A5042633786"] == allPubs["A5042633786"]


def testNewWorkIsDetected():
    last = stateFor("A5042633786", "Tim McAllister", {"W7154060862": fp.mapWorkToRecord(worksByID["W7154060862"], "A5042633786")})
    allPubs, newItems, _ = findNew([mcallister], [[work("W7221010631"), work("W7154060862")]], last)
    assert [i["pubID"] for i in newItems] == ["W7221010631"], newItems
    assert newItems[0]["authorID"] == "A5042633786" and newItems[0]["Name"] == "Tim McAllister"


def testSplitProfileNewIDIsSilent():
    # Hubert's second id was just added: works under it are recorded but not announced.
    last = stateFor("A5029134801", "Casey Hubert")
    allPubs, newItems, _ = findNew([hubert], [[work("W7204137749")]], last)  # this work lists A5128958200
    assert newItems == [], newItems
    assert "W7204137749" in allPubs["A5128958200"]["publications"]
    assert "W7204137749" not in allPubs["A5029134801"]["publications"]


def testDedupeAcrossResearcherIDs():
    # Known under one id, now returned under the other id: not new.
    last = {}
    last.update(stateFor("A5029134801", "Casey Hubert", {"W7204137749": record("One Panel")}))
    last.update(stateFor("A5128958200", "Casey Hubert"))
    allPubs, newItems, _ = findNew([hubert], [[work("W7204137749")]], last)
    assert newItems == [], newItems
    # Same DOI known under the other id with a different work id: not new.
    doi = fp.normalizeDOI(worksByID["W7204137749"]["doi"])
    last = {}
    last.update(stateFor("A5029134801", "Casey Hubert", {"W999": record("Duplicate record", doi=doi)}))
    last.update(stateFor("A5128958200", "Casey Hubert"))
    allPubs, newItems, _ = findNew([hubert], [[work("W7204137749")]], last)
    assert newItems == [], newItems
    # Scholar-era record with the DOI only in its url also counts.
    last["A5029134801"]["publications"] = {"scholarPubID": record("Scholar record", url="https://doi.org/" + doi.upper())}
    allPubs, newItems, _ = findNew([hubert], [[work("W7204137749")]], last)
    assert newItems == [], newItems


def testDedupeWithinRun():
    # One work listing both of Hubert's ids is announced once.
    w = work("W7221344554")  # lists A5029134801
    w["authorships"].append({"author_position": "middle", "author": {"id": "https://openalex.org/A5128958200", "display_name": "Casey Hubert"},
                             "institutions": [], "raw_author_name": "Casey Hubert"})
    last = {}
    last.update(stateFor("A5029134801", "Casey Hubert"))
    last.update(stateFor("A5128958200", "Casey Hubert"))
    allPubs, newItems, _ = findNew([hubert], [[w]], last)
    assert len(newItems) == 1 and newItems[0]["authorID"] == "A5029134801", newItems
    assert "W7221344554" in allPubs["A5029134801"]["publications"] and "W7221344554" in allPubs["A5128958200"]["publications"]
    # Two OpenAlex records with the same DOI in one run: announced once, both stored.
    twin = work("W7221344554", id="https://openalex.org/W1234")
    allPubs, newItems, _ = findNew([hubert], [[work("W7221344554"), twin]], stateFor("A5029134801", "Casey Hubert"))
    assert len(newItems) == 1, newItems
    assert set(allPubs["A5029134801"]["publications"].keys()) == set(["W7221344554", "W1234"])


def testAppendOnlyCarryForward():
    oldRecord = record("A 2025 paper OpenAlex no longer returns")
    tamperedTitle = record("Stored title must not be rewritten")
    last = stateFor("A5042633786", "Old Scholar Name", {"W_OLD": oldRecord, "W7221010631": tamperedTitle})
    last.update(stateFor("A5999999999", "Removed Researcher", {"W_GONE": record("Kept forever")}))
    allPubs, newItems, _ = findNew([mcallister], [[work("W7221010631")]], last)
    pubs = allPubs["A5042633786"]["publications"]
    assert pubs["W_OLD"] == oldRecord
    assert pubs["W7221010631"]["title"] == "Stored title must not be rewritten"
    assert allPubs["A5042633786"]["Name"] == "Tim McAllister"  # roster name wins
    assert allPubs["A5042633786"]["total_publications"] == "2"
    assert allPubs["A5999999999"]["publications"]["W_GONE"]["title"] == "Kept forever"  # unmonitored ids carried forward
    assert newItems == []


def testSupplementaryFilesSkipped():
    allPubs, newItems, zero = findNew([parkins], [[work("W7172243868")]], stateFor("A5063583896", "Michael Parkins"))
    assert newItems == [] and "W7172243868" not in allPubs["A5063583896"]["publications"]
    assert zero == []  # a researcher with only skipped works still "had works"


def testZeroWorkNames():
    # Nothing stored and nothing returned: someone who simply hasn't published this year is not flagged.
    allPubs, newItems, zero = findNew([mcallister, parkins], [[work("W7221010631")], []], {})
    assert zero == [], zero
    assert allPubs["A5063583896"]["publications"] == {}  # id recorded even with no works, so it is diffed next run
    # Recent works were stored before, but none came back today: flagged (profile probably merged/split).
    last = stateFor("A5063583896", "Michael Parkins", {"W1": record(year="2026-09-01")})
    allPubs, newItems, zero = findNew([parkins], [[]], last)
    assert zero == ["Michael Parkins"], zero
    # Only old works were stored: not flagged.
    last = stateFor("A5063583896", "Michael Parkins", {"W1": record(year="2024-01-01")})
    allPubs, newItems, zero = findNew([parkins], [[]], last)
    assert zero == [], zero


# ---- Doubt check ----
def testDoubtAffiliation():
    doubtful, reason = fp.isDoubtfulMatch(work("W7221010631"), mcallister, [], monitoredIDToName, today)
    assert doubtful is False and "affiliation" in reason, reason


def testDoubtAffiliationLineage():
    w = work("W7221010631")
    for a in w["authorships"]:
        for inst in a["institutions"]:
            inst["id"] = "https://openalex.org/I111"
            inst["lineage"] = ["https://openalex.org/I111", "https://openalex.org/I1331897569"]
    doubtful, reason = fp.isDoubtfulMatch(w, mcallister, [], monitoredIDToName, today)
    assert doubtful is False and "affiliation" in reason, reason
    for a in w["authorships"]:
        for inst in a["institutions"]:
            inst["lineage"] = ["https://openalex.org/I111"]
    doubtful, reason = fp.isDoubtfulMatch(w, mcallister, [], monitoredIDToName, today)
    assert doubtful is True, reason


def testDoubtCoMonitoredResearcher():
    # Parkins has no InstitutionIDs; Hubert (monitored) is a co-author.
    doubtful, reason = fp.isDoubtfulMatch(work("W7221344554"), parkins, [], monitoredIDToName, today)
    assert doubtful is False and "Casey Hubert" in reason, reason
    # ...also via Hubert's second id
    doubtful, reason = fp.isDoubtfulMatch(work("W7204137749"), parkins, [], monitoredIDToName, today)
    assert doubtful is False and "Casey Hubert" in reason, reason


def testDoubtSharedCoauthors():
    onlyParkins = {"A5063583896": "Michael Parkins"}
    known = [record(author="N Acosta, Michael D. Parkins"), record(author="Rhonda G. Clark, M Parkins, Someone Else")]
    doubtful, reason = fp.isDoubtfulMatch(work("W4406508397"), parkins, known, onlyParkins, today)
    assert doubtful is False and "2 co-authors" in reason, reason
    # one shared co-author (plus the researcher himself) is not enough
    doubtful, reason = fp.isDoubtfulMatch(work("W4406508397"), parkins, known[:1], onlyParkins, today)
    assert doubtful is True and "1 co-author(s)" in reason, reason


def testDoubtNoEvidence():
    onlyParkins = {"A5063583896": "Michael Parkins"}
    doubtful, reason = fp.isDoubtfulMatch(work("W7204137749"), parkins, [], onlyParkins, today)
    assert doubtful is True and reason.startswith("Could not confirm the author"), reason
    assert "no affiliation listed" in reason and "no InstitutionIDs on the roster row" in reason, reason


def testDoubtLateIndex():
    # Real fixture: created 2025-01-18, published 2026-05-30. Late index wins even with an affiliation/co-author match.
    doubtful, reason = fp.isDoubtfulMatch(work("W4406508397", createdDaysAgo=None), parkins, [], monitoredIDToName, today)
    assert doubtful is True and "OpenAlex indexed this 662 days ago (published 2026-05-30)" in reason, reason
    # W7221010631 was published 2026-10-08 (34 days before the test date), so only the created date varies here.
    doubtful, reason = fp.isDoubtfulMatch(work("W7221010631", createdDaysAgo=fp.lateIndexDays), mcallister, [], monitoredIDToName, today)
    assert doubtful is False, reason  # exactly lateIndexDays is still fine
    doubtful, reason = fp.isDoubtfulMatch(work("W7221010631", createdDaysAgo=fp.lateIndexDays + 1), mcallister, [], monitoredIDToName, today)
    assert doubtful is True and "indexed this 31 days ago" in reason, reason
    # Created long ago (e.g. at DOI registration) but only just published: a normal new paper, not late.
    recent = work("W7221010631", createdDaysAgo=200)
    recent["publication_date"] = (today - datetime.timedelta(days=3)).isoformat()
    doubtful, reason = fp.isDoubtfulMatch(recent, mcallister, [], monitoredIDToName, today)
    assert doubtful is False, reason


def testDoubtfulItemsGoToReviewNotDelta():
    last = stateFor("A5063583896", "Michael Parkins")
    allPubs, newItems, _ = fp.buildStateAndFindNew([parkins], [[work("W4406508397", createdDaysAgo=None), work("W7221344554")]],
                                                   last, monitoredIDToName, today)
    byID = dict((i["pubID"], i) for i in newItems)
    assert byID["W4406508397"]["doubtful"] is True and byID["W7221344554"]["doubtful"] is False
    delta = fp.buildDelta([i for i in newItems if not i["doubtful"]])
    assert list(delta["A5063583896"]["publications"].keys()) == ["W7221344554"] and delta["A5063583896"]["total_new"] == "1"
    assert "W4406508397" in allPubs["A5063583896"]["publications"]  # stored, so it is not re-flagged tomorrow


# ---- Flood breaker ----
def testFloodBreaker():
    saved = fp.maxNewPerRun
    try:
        fp.maxNewPerRun = 1
        items = [{"doubtful": False, "reason": "affiliation match (X)"}, {"doubtful": False, "reason": "affiliation match (Y)"},
                 {"doubtful": True, "reason": "late"}]
        items, warning = fp.applyFloodBreaker(items)
        assert warning.startswith("Flood breaker: 2 new publications") and "maxNewPerRun (1)" in warning, warning
        assert all(i["doubtful"] for i in items)
        assert items[0]["reason"].startswith("Flood breaker") and items[2]["reason"] == "late"
        items, warning = fp.applyFloodBreaker([{"doubtful": False, "reason": "ok"}])
        assert warning == "" and items[0]["doubtful"] is False
    finally:
        fp.maxNewPerRun = saved


# ---- Slack message ----
def pub(title, publisher="Journal A", url="https://doi.org/10.1/a", pubType="article"):
    return {"title": title, "year": "2026-10-01", "publisher": publisher, "author": "", "url": url, "firstOrLast": False,
            "datasource": "OpenAlex", "type": pubType, "doi": None, "created": "2026-10-01"}


def testMsgNone():
    assert fp.formatSlackMsg2({}) == "[INFO]\nNo new publication found."


def testMsgSingle():
    delta = {"A1": {"Name": "Tim McAllister", "total_new": "1", "publications": {"W1": pub("Paper one")}}}
    assert fp.formatSlackMsg2(delta) == ("Tim McAllister has a new publication: \n"
                                         "  * Paper one.  Published in Journal A.  https://doi.org/10.1/a\n\n")


def testMsgMultiple():
    delta = {"A1": {"Name": "Tim McAllister", "total_new": "2", "publications": {"W1": pub("Paper one"), "W2": pub("Paper two", publisher="Journal B")}}}
    assert fp.formatSlackMsg2(delta) == ("Tim McAllister has new publications: \n"
                                         "  * Paper one.  Published in Journal A.  https://doi.org/10.1/a\n\n"
                                         "  * Paper two.  Published in Journal B.  https://doi.org/10.1/a\n\n\n")


def testMsgSharedTitle():
    shared = pub("Shared paper")
    delta = {"A1": {"Name": "Michael Parkins", "total_new": "1", "publications": {"W1": shared}},
             "A2": {"Name": "Casey Hubert", "total_new": "2", "publications": {"W1": dict(shared), "W2": pub("Solo paper")}}}
    msg = fp.formatSlackMsg2(delta)
    assert msg == ("Michael Parkins, Casey Hubert has a new publication: \n"
                   "  * Shared paper.  Published in Journal A.  https://doi.org/10.1/a\n\n"
                   "Casey Hubert has a new publication: \n"
                   "  * Solo paper.  Published in Journal A.  https://doi.org/10.1/a\n\n"), repr(msg)
    assert "Name" not in delta["A1"]["publications"]["W1"]  # delta records are not mutated


def testMsgTypeTagNoVenueNoURL():
    delta = {"A1": {"Name": "Michael Parkins", "total_new": "1",
                    "publications": {"W1": pub("A preprint", publisher="bioRxiv", pubType="preprint")}},
             "A2": {"Name": "Casey Hubert", "total_new": "1", "publications": {"W2": pub("No venue", publisher=None, url=None, pubType="dataset")}},
             "A3": {"Name": "Tim McAllister", "total_new": "2",
                    "publications": {"W3": pub("Unknown venue", publisher="Unknown", url=None), "W4": pub("Untyped", pubType=None)}}}
    msg = fp.formatSlackMsg2(delta)
    assert msg == ("Michael Parkins has a new publication: \n"
                   "  * A preprint [preprint].  Published in bioRxiv.  https://doi.org/10.1/a\n\n"
                   "Casey Hubert has a new publication: \n"
                   "  * No venue [dataset]. URL unavailable.\n\n"
                   "Tim McAllister has new publications: \n"
                   "  * Unknown venue. URL unavailable.\n\n"
                   "  * Untyped.  Published in Journal A.  https://doi.org/10.1/a\n\n\n"), repr(msg)


def testMsgTitleTrailingPeriod():
    delta = {"A1": {"Name": "Tim McAllister", "total_new": "1", "publications": {"W1": pub("PS2-18. Ends with a period.")}}}
    assert fp.formatSlackMsg2(delta).startswith("Tim McAllister has a new publication: \n  * PS2-18. Ends with a period.  Published in")
    assert delta["A1"]["publications"]["W1"]["title"] == "PS2-18. Ends with a period."  # stored title untouched


def testReviewAndSummaryFormat():
    assert fp.formatReviewMsg([]) == ""
    item = {"Name": "Michael Parkins", "authorID": "A5063583896", "reason": "late", "record": pub("A preprint", publisher="bioRxiv", pubType="preprint")}
    review = fp.formatReviewMsg([item])
    assert review == ("*Needs review* - 1 publication(s) matched a monitored researcher but could not be confirmed. "
                      "They were not added to the Google Sheet.\n\n"
                      "  * Michael Parkins: A preprint [preprint]. Published in bioRxiv. https://doi.org/10.1/a\n"
                      "    Matched OpenAlex author A5063583896 (https://openalex.org/A5063583896). Reason: late\n\n"), repr(review)
    summary = fp.formatSummary(today, researchers, 2, 1, ["Michael Parkins"], "")
    assert summary == ("[INFO] Run summary 2026-11-11: checked 3 researchers (4 OpenAlex profiles); 2 new, 1 need review.\n"
                       "[WARNING] OpenAlex returned no works today for: Michael Parkins, although works from the last 365 days "
                       "were stored before. OpenAlex may have merged or split their profile - re-run AddResearcher.py for them.\n"), repr(summary)
    assert fp.formatSummary(today, researchers, 0, 0, [], "Flood breaker: x").endswith("[WARNING] Flood breaker: x\n")


# ---- Whole pipeline in a temp dir ----
outputFiles = ["allpubs.json", "delta.json", "msg.md", "review.md", "summary.md"]


class pipelineSandbox:
    """chdir into a temp dir, point the roster at the fixture and replace the fetcher; undo everything on exit."""
    def __init__(self, fakeFetch):
        self.fakeFetch = fakeFetch

    def __enter__(self):
        self.oldDir = os.getcwd()
        self.oldFetch = fp.fetchWorksForResearcher
        self.oldRoster = fp.rosterFile
        self.tempDir = tempfile.mkdtemp(prefix="publiiTest")
        os.chdir(self.tempDir)
        fp.rosterFile = fixtureRoster
        fp.fetchWorksForResearcher = self.fakeFetch
        return self.tempDir

    def __exit__(self, *args):
        os.chdir(self.oldDir)
        fp.fetchWorksForResearcher = self.oldFetch
        fp.rosterFile = self.oldRoster
        shutil.rmtree(self.tempDir, ignore_errors=True)
        return False


def fetchFrom(worksByName):
    def fakeFetch(researcher, fromDate):
        assert fromDate == "2025-11-11", fromDate
        return [copy.deepcopy(w) for w in worksByName.get(researcher["Name"], [])]
    return fakeFetch


def readText(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def testPipelineTwoRuns():
    available = {"Tim McAllister": [work("W7154060862")], "Michael Parkins": [work("W7221344554")], "Casey Hubert": [work("W7221344554")]}
    with pipelineSandbox(fetchFrom(available)) as tempDir:
        # run 1: everyone is new to the surveillance list -> silent
        fp.runPipeline(today)
        assert readText("msg.md") == "[INFO]\nNo new publication found."
        assert fp.loadJson("delta.json") == {} and readText("review.md") == ""
        assert set(fp.loadJson("allpubs.json").keys()) == set(["A5042633786", "A5063583896", "A5029134801", "A5128958200"])
        assert readText("summary.md").startswith("[INFO] Run summary 2026-11-11: checked 3 researchers (4 OpenAlex profiles); 0 new, 0 need review.\n")
        assert "returned no works" not in readText("summary.md")
        # run 2: new confident works, one doubtful, one supplementary file; Hubert's id returns nothing
        available["Tim McAllister"] = [work("W7221010631"), work("W7155628488", createdDaysAgo=None)]
        available["Michael Parkins"] = [work("W7204137749"), work("W7172243868"), work("W7221344554")]
        available["Casey Hubert"] = []
        result = fp.runPipeline(today)
        assert os.path.exists("last_allpubs.json")
        delta = fp.loadJson("delta.json")
        assert set(delta.keys()) == set(["A5042633786", "A5063583896"]), delta.keys()
        assert list(delta["A5042633786"]["publications"].keys()) == ["W7221010631"]
        assert list(delta["A5063583896"]["publications"].keys()) == ["W7204137749"]
        for entry in delta.values():
            for rec in entry["publications"].values():
                for field in ["title", "publisher", "author", "url", "firstOrLast", "year"]:
                    assert field in rec  # what GoogleSheetAPIConnector.py reads
        msg = readText("msg.md")
        assert msg.startswith("Tim McAllister has a new publication: \n  * Draft genome sequences"), msg
        assert "Michael Parkins has a new publication: \n  * One Panel, Many Pathogens" in msg and "Published in None" not in msg, msg
        review = readText("review.md")
        assert review.startswith("*Needs review* - 1 publication(s)") and "W7155628488" not in review, review
        assert "Tim McAllister: Optimizing a culture-enriched hybrid metagenomics" in review and "Matched OpenAlex author A5042633786" in review
        assert "Reason: OpenAlex indexed this 199 days ago" in review, review
        summary = readText("summary.md")
        assert "; 2 new, 1 need review." in summary and "returned no works today for: Casey Hubert," in summary, summary
        # append-only: run-1 works are still there even though they were not returned again
        state = fp.loadJson("allpubs.json")
        assert "W7221344554" in state["A5029134801"]["publications"] and "W7154060862" in state["A5042633786"]["publications"]
        # run 3: same data -> nothing new
        fp.runPipeline(today)
        assert readText("msg.md") == "[INFO]\nNo new publication found." and readText("review.md") == ""


def testZeroWorksRaises():
    with pipelineSandbox(fetchFrom({})):
        try:
            fp.runPipeline(today)
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "zero works" in str(e), str(e)
        for name in outputFiles:
            assert not os.path.exists(name), name + " should not be written"


def testFetchFailureWritesNothing():
    def failingFetch(researcher, fromDate):
        if researcher["Name"] == "Michael Parkins":
            raise RuntimeError("[ERROR] OpenAlex request to /works failed after 6 attempts: HTTP 503")
        return [work("W7221010631")]
    with pipelineSandbox(failingFetch):
        fp.saveJson({"A5042633786": {"Name": "Tim McAllister", "total_publications": "0", "publications": {}}}, "allpubs.json")
        before = readText("allpubs.json")
        try:
            fp.runPipeline(today)
            assert False, "expected the fetch error to propagate"
        except RuntimeError as e:
            assert "HTTP 503" in str(e)
        assert readText("allpubs.json") == before
        for name in ["delta.json", "msg.md", "review.md", "summary.md"]:
            assert not os.path.exists(name), name + " should not be written"


def testFetchWorksForResearcherFilter():
    calls = []
    saved = fp.listWorks
    try:
        fp.listWorks = lambda filterString, select=None, sort=None: calls.append((filterString, select, sort)) or []
        fp.fetchWorksForResearcher(hubert, "2025-11-11")
    finally:
        fp.listWorks = saved
    assert calls == [("authorships.author.id:A5029134801|A5128958200,from_publication_date:2025-11-11", fp.workFields, "publication_date:desc")], calls


if __name__ == "__main__":
    tests = [(name, obj) for name, obj in list(globals().items()) if name.startswith("test") and callable(obj)]
    failures = []
    for name, test in tests:
        try:
            test()
            print("[INFO] PASS " + name)
        except Exception:
            failures.append(name)
            print("[ERROR] FAIL " + name)
            traceback.print_exc()
    if failures:
        print("[ERROR] " + str(len(failures)) + " of " + str(len(tests)) + " tests failed: " + ", ".join(failures))
        sys.exit(1)
    print("[INFO] All " + str(len(tests)) + " tests passed")
