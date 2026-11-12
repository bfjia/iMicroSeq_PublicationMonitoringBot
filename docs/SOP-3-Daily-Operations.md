# SOP-3: Daily operations

## Purpose
Keep the bot healthy and its output trustworthy: read the daily messages, handle items needing review, change who is monitored, and respond to failures.

## Who / when
Whoever looks after the bot. A quick look each day it posts; a longer check monthly.

## Before you start
- The bot is set up ([SOP-1](SOP-1-Setup.md)) and deployed ([SOP-2](SOP-2-Deploy.md)).
- You can edit files on GitHub (click the file, then the pencil icon, then **Commit changes**).
- Background: [Workflow](Workflow.md).

## Steps

### A normal day
Most days you do nothing. The bot posts up to three kinds of message. Names, titles and links below are made up.

**1. Publications** (production channel when live, debug channel in test mode):
```
Jane Doe has a new publication: 
  * Wastewater surveillance of resistance genes.  Published in Applied and Environmental Microbiology.  https://doi.org/10.1128/aem.01234-26
```
A researcher with several papers reads "has new publications:". Types other than articles are tagged, such as `[preprint]` or `[dataset]`. If nothing is new the debug channel gets "[INFO] No new publication found."

**2. Needs review** (always the debug channel). Nothing was added to the Sheet for these:
```
*Needs review* - 1 publication(s) matched a monitored researcher but could not be confirmed. They were not added to the Google Sheet.

  * Ayush Kumar: Soil bacteria in rice paddies. Published in Soil Biology. https://doi.org/10.1016/j.soilbio.2026.000
    Matched OpenAlex author A5028360618 (https://openalex.org/A5028360618). Reason: Could not confirm the author: no affiliation listed; no other monitored researcher is a co-author; 0 co-author(s) seen in their earlier publications
```

**3. Run summary** (always the debug channel):
```
[INFO] Run summary 2026-11-12: checked 65 researchers (86 OpenAlex profiles); 1 new, 1 need review.
[WARNING] OpenAlex returned no works today for: Tim A. McAllister, although works from the last 365 days were stored before. OpenAlex may have merged or split their profile - re-run AddResearcher.py for them.
```
`[WARNING]` lines appear only when needed. There are two kinds: "returned no works today" and the flood breaker ("more than maxNewPerRun (40), so none were announced").

### Handling a "needs review" item
1. Click the link to the paper and the OpenAlex author link in the message.
2. Decide: is it really this researcher's paper?
3. **If correct:** on openalex.org open the paper, find the researcher's affiliation, and copy the institution id (the `I...` number in its URL). In `researchers.tsv`, add it to that person's `InstitutionIDs` column, separated by `|`. Future papers are then confident. Optionally add the paper to the Sheet by hand (see [Items the bot cannot see](#items-the-bot-cannot-see)). The bot will not announce this paper again.
4. **If wrong:** do nothing for a one-off. If the same OpenAlex author id keeps producing wrong items, delete that id from the person's `OpenAlexIDs` (keep the `|` between any remaining ids).

### Adding a researcher
1. On GitHub: **Actions**, **Add researcher candidate**, **Run workflow**. Enter the name. Enter the ORCID if you know it (for example `0000-0002-1234-5678`). Click **Run workflow**.
2. Or locally: `python src/AddResearcher.py "Jane Doe"` or `python src/AddResearcher.py "Jane Doe" 0000-0002-1234-5678`. Set `OPENALEX_API_KEY` first.
3. Open the run's **Summary** page (or `output/addResearcherReport.md` if local). For each person you see the proposed profile, recent works, and a table of candidates.
4. In the table, **Co-authored with network** is the number of that profile's papers shared with researchers already monitored. A number above 0 is the strongest sign it is the right person. 0 comes with a warning: check carefully. **Name score** and **Rank** are the bot's own ratings.
5. Open the candidate links. If the recent works are theirs, edit `researchers.tsv` on GitHub and change `REVIEW` to `OK` in that row. If a runner-up (listed in the Notes column) is the right one, replace the ids in `OpenAlexIDs`. A person can have several ids separated by `|`.
6. If the status is `NO_MATCH`, try again with their ORCID.
7. The first run after a person becomes `OK` records their back-catalog silently. It is announced from the next run on.

Currently waiting in `researchers.tsv`: **27 REVIEW rows** (24 candidates for people who never had a Scholar profile, and 3 with weak evidence: Marc Fiume, Ashlyn Kirk, Tyler P Cobb) and **5 NO_MATCH rows** (Mathieya Alatini, Bhavik Bhagat, Ana Maria Podadera Gonzalez, Mat Wlodarski, Sherry Wabisca). Work through these as time allows. Nobody with `REVIEW` or `NO_MATCH` is monitored.

### Removing a researcher
In `researchers.tsv`, change their Status to `INACTIVE` and commit. Their history stays in `state/allpubs.json`, so re-activating them later (back to `OK`) will not re-announce old work.

### If a failure alert arrives
1. Open the link in the Slack message (or **Actions** and the red run).
2. Open the **Run pipeline** step and read the last lines. Find the line starting `[ERROR]`.
3. Common causes: OpenAlex budget or key problem, Slack token or channel problem, a Sheet permission problem, OpenAlex briefly down. Use the troubleshooting table below.
4. Nothing was saved, so it is safe to re-run. The next daily run also catches up by itself. One exception: if the alert says it failed "outside the pipeline step" while saving state, that day's papers were already posted. The next run may post them again, and you can ignore the repeats.

### Re-running by hand
**Actions**, **Daily publication check**, **Run workflow**, choose `main`.

### Items the bot cannot see
Theses, university-repository deposits, conference abstracts and other items without a DOI are often missing ([Missed items](Workflow.md#missed-items)). To add one: open the Google Sheet, right-click row 2 and **Insert row above**, and copy the layout of the row below. Columns are: participant, title, date added, publisher, authors, url, firstOrLast (True or False), blank, year. Post it in Slack by hand if wanted.

### Exporting a list of publications
To get everything the bot has stored since a date (for example to check the Sheet against it), run locally:
```bash
python src/ExportPubsSince.py 20260101
```
It writes `output/pubsSince20260101.tsv` with one row per researcher per paper, newest first. Give a second argument to choose the file name.

### Changing which types are announced
Open `config.py` on GitHub and edit the `ignoredTypes` line, for example:
```
ignoredTypes = ['dataset', 'software', 'peer-review']
```
Commit it. Ignored types are not stored or announced. Other types: see [Extra items and noise](Workflow.md#extra-items-and-noise).

### Routine checks
- **Weekly, while in test mode:** glance at the debug channel. Is anything strange or repeated?
- **Monthly:** open your OpenAlex usage page and check the budget is far from used (about 1% is normal). Check the daily workflow is not disabled (**Actions** should show recent runs). Look for "returned no works today" warnings. For each person named, re-run `AddResearcher.py` for them and fix `OpenAlexIDs` if needed.
- The workflow adds a "Keepalive" commit after 50 quiet days to stop GitHub switching the schedule off ([GitHub scheduling](Workflow.md#github-scheduling)).

## Check it worked
- Each day: a "Run summary" appears in the debug channel and the latest Actions run is green.
- After editing `researchers.tsv`: the next run's summary shows the expected "checked N researchers" count.

## If something goes wrong
| Symptom | Likely cause | Fix |
|---|---|---|
| No message today | GitHub started the run late, the run failed before posting, or the schedule is disabled | Wait 30 minutes, then check **Actions**. Run by hand if needed. |
| Failure alert | See the `[ERROR]` line in the log | See [If a failure alert arrives](#if-a-failure-alert-arrives). |
| `429` or "daily budget exhausted" | No OpenAlex key, or the key's budget is used up | Check the `OPENALEX_API_KEY` secret ([SOP-2](SOP-2-Deploy.md)). Look at the usage page. Re-run tomorrow. |
| `key_not_activated` | OpenAlex key not activated | Click the link in the OpenAlex email. |
| Slack `not_in_channel` | Bot is not in the channel | `/invite` the bot to that channel. |
| Slack `invalid_auth` | Wrong or revoked token | Make a new token and update the `SLACK_BOT_TOKEN` secret. |
| Sheet permission error | Sheet not shared with the service account | Share it as Editor ([SOP-1](SOP-1-Setup.md)). |
| Flood-breaker warning | More than 40 confident items in one run; likely an OpenAlex merge or re-index | Check the "Needs review" list. Add genuine ones to the Sheet by hand. Nothing is repeated tomorrow. |
| A researcher's papers are missing | Wrong or incomplete `OpenAlexIDs`, no DOI, or OpenAlex lag | Search their name on openalex.org. Add extra ids with `\|`. Re-run `AddResearcher.py` for them. See [Indexing lag](Workflow.md#indexing-lag). |
| Wrong person's papers announced | A shared-name profile is in `OpenAlexIDs` | Remove that id. Delete the Sheet row. See [Author matching](Workflow.md#author-matching). |
| Schedule disabled after 60 days | No repository activity | **Actions**, **Daily publication check**, **Enable workflow**. Make any commit. |
