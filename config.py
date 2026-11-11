#Settings for the publication bot, in one place. Edit values here, not in the scripts.
#
#Read by FindPublications.py, AddResearcher.py, openAlexClient.py, slackConnector.py,
#GoogleSheetAPIConnector.py, publii.sh and .github/workflows/publii.yml.
#Secrets never go in this file (the repo is public): they come from env vars or the gitignored .secret/ folder.
#
#Not here, because GitHub reads it from the workflow file itself: the daily run time
#(cron "20 15 * * *" = 15:20 UTC, in .github/workflows/publii.yml).
import re


# ======================================================================
# Go-live switch
# ======================================================================
# False (testing): every Slack post goes to debugChannel and Sheet rows go to the TEST copy of the sheet.
# True (live): new-publication messages go to productionChannel and rows go to the PRODUCTION sheet.
# Review items, run summaries and failure alerts always go to debugChannel.
# Do not set to True without the go-live checklist in docs/SOP-2-Deploy.md.
isLive = False


# ======================================================================
# Slack
# ======================================================================
debugChannel = "C09D86E4T5H"       # #publication_monitor_debug: test-mode posts, review items, summaries, failure alerts
productionChannel = "C097CKA5U4X"  # production channel: new-publication messages, only when isLive = True
# Fallback when the SLACK_BOT_TOKEN env var is not set (gitignored; one line holding the xoxb- token).
slackTokenFile = ".secret/pubiioauthtoken"
# Slack truncates long messages, so longer ones are split into several posts of at most this many characters.
slackMaxChunkLength = 3500


# ======================================================================
# Google Sheet
# ======================================================================
# Rows go to testSpreadsheetID unless isLive = True. The production sheet must never receive test rows.
productionSpreadsheetID = "14XeOue130U_01iplm2slQgGWtXyZAurWw1cikuDLga0"
testSpreadsheetID = "1ZUfZRNoR_WRCu7o32oJqfXaNXPPFFQUfP7UVv9vz0NQ"  # TEST_COPY_OF_iMicroSeqPubsSince20250601
# Tab 'iMicroSeqPubsSince20250601'. Same id in both spreadsheets. This is the gid in the sheet URL, not the tab's position.
sheetTabID = 1533674458
# Fallback when the GOOGLE_SERVICE_ACCOUNT_JSON env var is not set (gitignored service-account JSON key).
googleCredentialsFile = "./.secret/googleToken"
googleScopes = ["https://www.googleapis.com/auth/spreadsheets"]


# ======================================================================
# Daily check (FindPublications.py)
# ======================================================================
# How many days back to ask OpenAlex for works. Older papers are never announced.
lookbackDays = 365
# More confident new items than this in one run is suspicious (profile merge, mass re-index):
# all of them go to the review message instead and a warning is added ("flood breaker").
maxNewPerRun = 40
# A new item whose OpenAlex record was created AND published more than this many days ago was moved
# onto the researcher's profile late (re-attribution), not newly published, so it goes to review.
lateIndexDays = 30
# A new item counts as confident if at least this many of its co-authors (surname + first initial)
# appear in the researcher's earlier publications. (Matching institution or a monitored co-author also counts.)
minSharedCoauthors = 2
# OpenAlex work types that are never stored or announced, e.g. ['dataset', 'software', 'peer-review', 'erratum'].
# Empty = announce every type (articles, reviews, preprints, chapters, datasets, software, ...).
ignoredTypes = []
# Titles matching this are skipped entirely. Catches supplementary-file deposits such as
# Figshare "Additional file 3 of <paper>", which are not publications.
ignoredTitlePattern = re.compile(r'^\s*(additional file|supplementary (file|material|table|figure|data|information))\b', re.IGNORECASE)


# ======================================================================
# Adding researchers (AddResearcher.py)
# ======================================================================
maxCandidates = 8            # how many OpenAlex search hits to score per name
shownCandidates = 5          # how many of them to list in addResearcherReport.md
minNameScore = 0.8           # if the best hit's name similarity (0-1) is below this, the row becomes NO_MATCH
homeCountry = "CA"           # iMicroSeq is a Canadian network; an institution in this country is a ranking hint only
recentAffiliationYears = 6   # affiliations from the last N years count as the candidate's current institutions
# Rank = rankWeightName * name similarity + rankWeightCountry * (in homeCountry)
#        + rankWeightNetwork * min(shared works, networkOverlapCap) / networkOverlapCap.
# "Shared works" = the candidate's papers co-authored with researchers already monitored: the strongest signal.
rankWeightName = 0.45
rankWeightCountry = 0.15
rankWeightNetwork = 0.40
networkOverlapCap = 5
# A runner-up is proposed as an extra profile of the same person (OpenAlex often splits people) if its name
# similarity is at least fragmentMinNameScore, it shares an institution with the best hit, and it either
# co-authored with the network or has at most fragmentMaxWorks works.
fragmentMinNameScore = 0.85
fragmentMaxWorks = 25
# Pause between names when processing the whole roster, to be gentle on the API.
addResearcherPauseSeconds = 0.3


# ======================================================================
# OpenAlex API (openAlexClient.py)
# ======================================================================
# The API key is the OPENALEX_API_KEY env var (GitHub secret), never this file.
openAlexBaseURL = "https://api.openalex.org"
userAgent = "PublicationMonitoringBot/2.0 (python-urllib)"
maxRetries = 6           # attempts per request on 429 / 5xx / network errors, with growing waits
requestTimeout = 60      # seconds before a single request is abandoned (and retried)
# A 429 that asks us to wait longer than this means the daily budget is used up: fail instead of sleeping.
maxRetryAfterSeconds = 300


# ======================================================================
# GitHub Actions (.github/workflows/publii.yml)
# ======================================================================
# GitHub turns off scheduled runs after 60 days with no repository activity. If nothing has been
# committed for this many days, the workflow makes an empty "Keepalive" commit. Keep it below 60.
keepaliveDays = 50
