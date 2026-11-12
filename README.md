# iMicroSeq Publication Monitoring Bot

A bot that checks OpenAlex every day for new publications by iMicroSeq network researchers.
It posts them to Slack and a Google Sheet, and flags uncertain matches for a person to review.

**Status:** Currently in test mode: posts to the debug channel and the test Google Sheet only.

## Quickstart

1. Read [Workflow](docs/Workflow.md) (about 5 minutes).
2. Follow [SOP-1](docs/SOP-1-Setup.md) to get the keys and test locally.
3. `pip install -r requirements.txt && python tests/RunOfflineTests.py`
4. Follow [SOP-2](docs/SOP-2-Deploy.md) to run it on GitHub Actions and go live.
5. Use [SOP-3](docs/SOP-3-Daily-Operations.md) for day-to-day work.

## Layout

```
config.py          every setting, with comments (incl. the isLive go-live switch)
researchers.tsv    who is monitored (edit this to add/remove people)
publii.sh          the daily pipeline, run by GitHub Actions
src/               the Python code
state/             the bot's memory (allpubs.json, delta.json); committed by the bot, never edit
output/            files generated each run (Slack messages, logs, reports); not in git
docs/              how it works and the SOPs
tests/             offline tests, run before every daily run
legacy/            the old Google Scholar bot, reference only
.github/workflows/ the daily run and the "Add researcher candidate" button
```

## Docs

- [Workflow](docs/Workflow.md): what the bot does, and its known limits
- [SOP-1: Setup](docs/SOP-1-Setup.md): accounts, credentials, local test run
- [SOP-2: Deploy](docs/SOP-2-Deploy.md): GitHub Actions, go-live, rollback
- [SOP-3: Daily operations](docs/SOP-3-Daily-Operations.md): routine use, adding researchers, troubleshooting
