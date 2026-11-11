# SOP-2: Move to GitHub Actions and go live

## Purpose
Run the bot daily on GitHub Actions, then switch it from test mode to live mode.

## Who / when
A repository admin, once, after [SOP-1](SOP-1-Setup.md) is done. The go-live part comes only after a QA period.

## Before you start
- You have the three credentials from SOP-1: OpenAlex key, Slack bot token, Google service account JSON.
- The repository is public, so logs and `allpubs.json` can be read by anyone ([Public repo](Workflow.md#public-repo)). Secrets stay masked. Do not paste secrets anywhere except the Secrets page.
- Scheduled runs happen only on the default branch, so the work must be on `main` ([GitHub scheduling](Workflow.md#github-scheduling)).

## Steps

### A. Add the secrets
1. In the repository on GitHub, click **Settings**, then **Secrets and variables**, then **Actions**.
2. Click **New repository secret**. Add these three, one at a time:
   - `SLACK_BOT_TOKEN`: the `xoxb-...` token.
   - `OPENALEX_API_KEY`: the OpenAlex key.
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: paste the full contents of the JSON key file.

### B. Allow Actions to save its state
1. **Settings**, then **Actions**, then **General**.
2. Under **Actions permissions**, choose **Allow all actions and reusable workflows**.
3. Under **Workflow permissions**, choose **Read and write permissions**. Click **Save**.

### C. Turn off the old server cron first
The old bot ran from a crontab (`0 7 * * *`) and did `git pull` and `git push`. If it stays on, it will race the new bot.
1. `ssh` to the old server.
2. Run `crontab -e`.
3. Delete the line containing `publii.sh`, or put `#` in front of it. Save and exit.
4. Run `crontab -l` and confirm the line is gone.

### D. Merge to main
1. Open a pull request from `openalex-migration` into `main` and merge it.
2. Check that `main` contains `.github/workflows/publii.yml`.

### E. First run by hand
1. Click **Actions**, then **Daily publication check** in the left list.
2. Click **Run workflow**, choose `main`, click the green **Run workflow** button.
3. Wait about a minute, then open the run.

## Check it worked
- The run has a green tick.
- The debug channel `#publication_monitor_debug` has an "[INFO] Run summary ..." message.
- The run's **Summary** page shows the same summary and message.
- A commit "Update YYYYMMDD" appears on `main`. It appears only if something changed, so on a quiet day there may be none.
- No more daily commits come from the old server.

A failed run looks like this: a red cross on the Actions page and a Slack message in the debug channel saying "The publication bot run failed." with a link to the run and `publii.log` attached. If the failure was in setup, tests or saving state, the message reads "The publication bot run failed outside the pipeline step ..." instead. You do not need to cause one to test it.

## Go-live checklist
Do this only after the bot has run in test mode for a QA period.
- [ ] The messages in the debug channel have looked right for the whole QA period.
- [ ] The review queue is under control (not a growing pile of unhandled "Needs review" items).
- [ ] The production sheet is shared with the service account as Editor.
- [ ] In `config.py`, change `isLive = False` to `isLive = True`. Commit it on `main`.
- [ ] This sends new-publication messages to `C097CKA5U4X` and adds Sheet rows to the PRODUCTION spreadsheet (`publii.sh` passes `--live`, and the Sheet script refuses `--live` unless `isLive` is True). Review items, summaries and failure alerts still go to the debug channel.
- [ ] Run **Daily publication check** once by hand and confirm: summary in debug, and (if there was news) the message in the production channel and rows in the production sheet.

## Rollback
1. Stop the schedule: **Actions**, **Daily publication check**, the **...** menu at top right, **Disable workflow**.
2. Set `isLive = False` in `config.py` and commit.
3. If a bad run saved bad state, find the "Update YYYYMMDD" commit in **Commits** and revert it: `git pull`, then `git revert <commit-id>`, then `git push`.
4. Clean up what was already posted. The bot cannot undo this. Delete the Slack message by hand (hover, **...**, **Delete message**), and delete the wrong rows from the Sheet (right-click the row number, **Delete row**).
5. When fixed, use **Enable workflow** on the same menu.

## If something goes wrong
| You see | Fix |
|---|---|
| Run fails at the commit step with a permission error | Redo step B (Read and write permissions). |
| `key_not_activated` or 429 | See [SOP-1](SOP-1-Setup.md#if-something-goes-wrong). |
| `not_in_channel` | Invite the bot to the channel. |
| Nothing runs overnight | Scheduled runs are on `main` only and can start late. See [GitHub scheduling](Workflow.md#github-scheduling). |
| Two bots posting | The old cron is still on. Redo step C. |

Next: [SOP-3: Daily operations](SOP-3-Daily-Operations.md).
