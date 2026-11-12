# How the publication bot works

## Summary

Every day the bot looks up each monitored iMicroSeq researcher on OpenAlex (a free, open index of scholarly papers) and finds papers it has not seen before. Papers it is confident belong to the researcher are posted to Slack and added to a Google Sheet. Papers it is unsure about go to a "needs review" message for a person to check. GitHub Actions runs it once a day and saves its memory back to the repository. Nothing runs on a server you look after.

The bot used to read Google Scholar. It was moved to OpenAlex because Scholar blocks automated access. See [Known limits](#known-limits) for what that change costs.

## Pipeline

```
researchers.tsv  (who to watch, and their OpenAlex ids)      config.py  (all settings)
       |
       v
src/FindPublications.py  <--- OpenAlex API (works from the last 365 days)
       |
       +--> state/allpubs.json  (memory of every paper seen; committed)
       +--> state/delta.json    (confident new papers; committed)
       +--> output/msg.md       (Slack text for new papers)
       +--> output/review.md    (Slack text for papers needing review)
       +--> output/summary.md   (one-line run summary + warnings)
       |
       v
publii.sh --> Slack  (msg.md, review.md, summary.md)
          --> Google Sheet  (rows from state/delta.json)

GitHub Actions runs all of this daily and commits state/allpubs.json and state/delta.json.
```

## A daily run, step by step

1. GitHub starts the "Daily publication check" workflow at 15:20 UTC (about 07:20 Pacific time in winter). It may start late.
2. It installs the dependencies and runs the offline tests.
3. `src/FindPublications.py` reads `researchers.tsv`. It uses only rows with Status `OK` and at least one OpenAlex id.
4. For each researcher it asks OpenAlex for all works from the last 365 days.
5. It compares them with `state/allpubs.json`. Anything not already stored is "new".
6. Each new item is judged confident or needs review (see below).
7. Confident items go to `output/msg.md` and `state/delta.json`. Items needing review go to `output/review.md`.
8. `publii.sh` posts to Slack and, if there was something new, adds Google Sheet rows.
9. If `state/allpubs.json` or `state/delta.json` changed, the workflow commits "Update YYYYMMDD".

## Files

The two files people edit are at the top of the repository. Everything else is in a folder.

| File or folder | Role |
|---|---|
| `config.py` | Every setting in one place, each with a comment: the `isLive` switch, Slack channels, Sheet ids, the daily-check thresholds, `AddResearcher.py` scoring, OpenAlex retries. Edit settings here. |
| `researchers.tsv` | The list of people. Columns: Status, Name, OpenAlexIDs, ORCID, InstitutionIDs, ScholarID, Notes. Edit this to change who is watched. |
| `publii.sh` | Runs the daily steps and posts. Reads the channels and `isLive` from `config.py`. |
| `src/FindPublications.py` | The daily check. |
| `src/AddResearcher.py` | Finds the OpenAlex profile for a new person. Writes `output/addResearcherReport.md`. |
| `src/ExportPubsSince.py` | Exports every stored paper after a date to a TSV, for example to check or backfill the Sheet. |
| `src/slackConnector.py`, `src/GoogleSheetAPIConnector.py`, `src/openAlexClient.py`, `src/researcherRoster.py`, `src/paths.py` | Helpers for Slack, the Sheet, OpenAlex, reading `researchers.tsv`, and where files live. |
| `state/allpubs.json` | The bot's memory: every paper seen, per OpenAlex id. Committed by the bot. Never edit by hand. |
| `state/delta.json` | The confident new papers from the latest run. Feeds the Google Sheet step. |
| `output/` | Made fresh by each run and not committed: the three Slack messages (`msg.md`, `review.md`, `summary.md`), `publii.log`, `last_allpubs.json` (the memory before this run) and reports. |
| `.github/workflows/` | `publii.yml` (daily run) and `addResearcher.yml` (the "Add researcher candidate" button). |
| `tests/` | Offline tests. Run by the workflow before every daily run. |
| `docs/` | This page and the SOPs. |
| `legacy/` | The old Google Scholar bot and data. Reference only. |

## How researchers are matched to OpenAlex profiles

OpenAlex has its own author ids (like `A5042633786`). They are not the same as Google Scholar ids. One real person often has more than one OpenAlex profile, because OpenAlex splits profiles by mistake. So `OpenAlexIDs` can hold several ids separated by `|`, and the bot treats them as one person.

A new person is added with `AddResearcher.py`. It searches OpenAlex, ranks the candidates (name, Canadian institution, papers shared with people already monitored) and writes the best guess with Status `REVIEW`. **Nothing is watched until a human checks the guess and changes `REVIEW` to `OK`.** Status values are `OK` (watched), `REVIEW` (waiting for a human), `NO_MATCH` (nothing convincing found) and `INACTIVE` (not watched; history kept).

## Confident or "needs review"?

A new item is **confident** if any one of these is true, checked in this order:

1. The researcher's own author entry lists an institution whose id is in their `InstitutionIDs`.
2. Another monitored researcher is a co-author.
3. At least 2 of the co-authors already appear in the researcher's earlier papers.

It **needs review** if none is true, or if this applies first:

- **Re-attribution rule.** OpenAlex created the record more than 30 days ago and the paper was published more than 30 days ago, but it only now appears under this person. This usually means OpenAlex moved an old paper onto their profile. It is not a new paper.
- **Flood breaker.** If more than 40 confident items turn up in a single run, all of them are moved to review and a warning is added. This usually means OpenAlex merged profiles or re-indexed a batch.

| Outcome | Slack | Google Sheet |
|---|---|---|
| Confident | Publications message (live: production channel) | Row added |
| Needs review | "Needs review" message, always the debug channel | Not added |
| Nothing new | "No new publication found." in the debug channel | Nothing |

An item is announced or sent to review once only. After that it is stored as seen.

## Test mode and live mode

The switch is `isLive` in `config.py`. It is currently `False`.

| | `isLive = False` (test mode) | `isLive = True` (live) |
|---|---|---|
| New publications message | Debug channel `C09D86E4T5H` | Production channel `C097CKA5U4X` |
| Needs review, summary, failure alerts | Debug channel | Debug channel |
| Google Sheet rows | TEST copy of the sheet | PRODUCTION sheet |

## When a run fails

If the pipeline fails, the bot posts "The publication bot run failed." plus a link to the run and the log file to the debug channel. If another step fails (install, tests or saving state), it posts "The publication bot run failed outside the pipeline step ..." with the run link instead. Nothing is saved on a failed run, so no data is lost. The next run looks back 365 days and catches up on its own. If saving state was the step that failed, the next run may announce the same papers again. The one case with no Slack alert is when Slack itself is broken (for example a revoked token). Then you only see a red cross on the Actions page and a GitHub email. See [SOP-3](SOP-3-Daily-Operations.md#if-a-failure-alert-arrives).

## Known limits

### Missed items
In a back-test (11 Nov 2026) the old Scholar bot had posted 217 in-range items between 17 Jun and 5 Nov 2026. The new bot finds 171 of them (79%), and 95% of the ones that have a DOI. The misses were:

- 37 with no DOI: theses, university-repository deposits, conference abstracts, French-language book chapters, one patent.
- 8 from small split-off OpenAlex profiles (7 have since been added to `researchers.tsv`).
- 1 DOI that OpenAlex does not have.

In practice: roughly 1 in 5 of what Scholar showed will not appear. What you can do: add them to the Sheet by hand ([SOP-3](SOP-3-Daily-Operations.md#items-the-bot-cannot-see)).

### Extra items and noise
10 items Scholar announced as "new" were really published in 2024 or early 2025. The new bot ignores them correctly (365-day window). It also finds 64 items Scholar never showed: about 22 preprints, 15 articles, 12 datasets, 3 software, 2 peer-review reports, 5 "other", and a few chapters and conference papers. Some are noise, for example Figshare parts such as "Cell Counts" listed as datasets. What you can do: drop whole types with `ignoredTypes` ([SOP-3](SOP-3-Daily-Operations.md#changing-which-types-are-announced)).

### Duplicates
A preprint and its journal version are separate records, so both get announced. Each non-article is tagged, for example `[preprint]`. What you can do: nothing needed. Ignore the second one, or delete the extra Sheet row.

### Author matching
Matching is imperfect. About 3.5% of real papers went to review in the back-test because the affiliation was missing. Common names (for example "Ayush Kumar") can pull in another person's papers. The check caught two such cases, but it can still let one through or hold back a real one. OpenAlex also merges and splits profiles over time. The "returned no works today" warning catches a profile that suddenly empties. What you can do: handle review items ([SOP-3](SOP-3-Daily-Operations.md#handling-a-needs-review-item)) and re-run `AddResearcher.py` when you see that warning.

### Indexing lag
OpenAlex usually has a paper within days. In the back-test the median was about 3 days earlier than Scholar. Occasionally it takes weeks (the longest was about 2 months). So an announcement can arrive late. What you can do: nothing; it will appear when OpenAlex has it.

### Public repo
The repository is public. GitHub Actions logs and `state/allpubs.json` (researcher names and paper titles) can be read by anyone. Secrets stay masked in logs. What you can do: never put secrets or private notes in the repo, and keep Notes in `researchers.tsv` professional. See [SOP-2](SOP-2-Deploy.md#before-you-start).

### GitHub scheduling
Runs can start late, often 5 to 30 minutes and sometimes more. GitHub also switches off scheduled runs after 60 days with no repository activity. The workflow makes a "Keepalive" commit after 50 quiet days, but check monthly. What you can do: see [SOP-3](SOP-3-Daily-Operations.md#routine-checks) and the troubleshooting row for a disabled schedule.

### OpenAlex terms
OpenAlex changed its pricing in Feb 2026 (an API key is now standard, with a usage-based budget) and could change it again. This bot uses about 1% of the free key's daily budget. What you can do: check the usage page monthly.

### Old Scholar data
The old Google Scholar data is kept in `legacy/` for reference only. The bot does not use it.
