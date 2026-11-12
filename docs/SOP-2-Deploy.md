# SOP-2: Deploy to GitHub Actions and go live

## Purpose
Move the bot from the old server onto GitHub Actions so it runs every day by itself, check it works in test mode, and later switch it to live mode.

## Who / when
A repository admin, once, after [SOP-1](SOP-1-Setup.md) is done. Steps 1 to 8 take about 30 minutes. The go-live part comes only after a QA period (suggested: two weeks).

## Before you start
- [SOP-1](SOP-1-Setup.md) is done. You have:
  - the OpenAlex API key, activated;
  - the Slack bot token (`xoxb-...`), with the bot invited to both channels;
  - the Google service-account JSON key, with both sheets shared with it as Editor.
- You are an **admin** of `bfjia/iMicroSeq_PublicationMonitoringBot` on GitHub. Steps 2 and 3 need the **Settings** tab.
- You can log in to the old server (or reach whoever can) to turn off its cron job.
- Keep in mind:
  - The repository is public. Logs and `state/allpubs.json` can be read by anyone ([Public repo](Workflow.md#public-repo)). Secrets stay masked. Paste secrets only into the Secrets page.
  - Scheduled runs happen only on the default branch (`main`), so nothing runs daily until step 4 ([GitHub scheduling](Workflow.md#github-scheduling)).
  - The bot starts in test mode (`isLive = False` in `config.py`). Everything you do here posts only to `#publication_monitor_debug` and writes only to the TEST sheet.

## Steps

### 1. Turn off the old server's cron job (do this first)
The old bot runs from a crontab and pushes to `main`. If it is still on after the merge, it will pull the new code, fail or race the new bot, and push conflicting commits.
1. Log in to the old server: `ssh <user>@<server>`.
2. Run `crontab -l`. Look for a line containing `publii.sh` (it ran at `0 7 * * *`). If there is none, try the other accounts that might own it: `sudo crontab -l -u <user>`.
3. Run `crontab -e` (with `-u <user>` if needed). Put `#` at the start of the `publii.sh` line, then save and exit. Commenting the line out, rather than deleting it, keeps a record of it.
4. Run `crontab -l` again and confirm the line now starts with `#`.
5. Leave the server and its files in place for now. You may need `.secret/googleToken` from it in step 2. Decommission it after go-live.

### 2. Add the three secrets
1. On GitHub, open the repository, then **Settings**, **Secrets and variables**, **Actions**.
2. On the **Secrets** tab, click **New repository secret**. Add each of these. The name must match exactly:

   | Name | Value |
   |---|---|
   | `SLACK_BOT_TOKEN` | The `xoxb-...` token, on one line. |
   | `OPENALEX_API_KEY` | The OpenAlex key. |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | The whole contents of the JSON key file, from the first `{` to the last `}`. Open the file in a text editor, select all, copy, paste. |

3. Check the list shows all three names. You cannot view a value after saving it. If one is wrong, click it and choose **Update secret**.

### 3. Let Actions run and save its state
1. **Settings**, **Actions**, **General**.
2. Under **Actions permissions**, choose **Allow all actions and reusable workflows**. Click **Save**.
3. Under **Workflow permissions**, choose **Read and write permissions**. Click **Save**. Without this, the bot cannot commit `state/allpubs.json` and every run fails at the end.
4. **Settings**, **Branches** (and **Rules**, if shown). If `main` has a rule that blocks direct pushes or requires pull requests, the bot's daily commit will be rejected. Either remove that rule or add **GitHub Actions** to its bypass list.

### 4. Make sure the code is on main
The new code was merged into `main` in pull request #8, so normally you only check:
1. Open the **Code** tab on `main`. It should have `config.py`, `researchers.tsv`, `publii.sh`, the `src/` and `state/` folders, and `.github/workflows/publii.yml`.
2. Open the **Actions** tab. The left list should show **Daily publication check** and **Add researcher candidate**. The daily schedule is active.

If you are deploying from another branch (for example a future rewrite), merge it first: **Pull requests**, **New pull request**, **base** `main`, **compare** your branch, **Create pull request**, then **Merge pull request** and **Confirm merge**.

### 5. First run by hand
1. **Actions**, then **Daily publication check** in the left list.
2. Click **Run workflow** (top right of the run list). Leave the branch on `main`, and click the green **Run workflow** button.
3. Refresh after a few seconds. A new run appears. It takes about 1 to 3 minutes.
4. Open the run, then the **publii** job, then the **Run pipeline** step. Near the top it should print `[INFO] isLive=false`. If it says `true`, stop: disable the workflow ([Rollback](#rollback)) and set `isLive = False` in `config.py`.

### 6. Check the first run
- [ ] The run has a green tick.
- [ ] `#publication_monitor_debug` has an "[INFO] Run summary ..." message. It also has either "[INFO] No new publication found." or a list of publications.
- [ ] Nothing was posted to the production channel.
- [ ] The run's **Summary** page shows the same summary and messages.
- [ ] If there were new publications, the TEST sheet (`TEST_COPY_OF_iMicroSeqPubsSince20250601`) has new rows at the top, and the production sheet does not.
- [ ] If anything changed, `main` has a new commit "Update YYYYMMDD" from `github-actions[bot]`. On a quiet day there may be none.

### 7. Test the "Add researcher" button
This checks the OpenAlex key and the button without changing the roster.
1. **Actions**, **Add researcher candidate**, **Run workflow**.
2. Name: `Fiona Brinkman`. Leave ORCID empty. Click **Run workflow**.
3. When it is green, open the run's **Summary**. It should say she is already monitored and the roster was not changed. No new commit appears.

### 8. Check the next scheduled run
1. The next day, after about 15:20 UTC (07:20 Pacific in winter, 08:20 in summer), open **Actions**. A run marked **Scheduled** should be there. GitHub can start it up to 30 minutes or more late.
2. Check that the debug channel got that day's run summary.
3. Check there are no commits on `main` from the old server's account (it used to commit "Update YYYYMMDD" as `PaphlagonUpdater`). Commits should come only from `github-actions[bot]`.

The bot is now deployed in test mode. Use [SOP-3](SOP-3-Daily-Operations.md) for daily use during the QA period, including working through the `REVIEW` rows.

## Check it worked
- Steps 6 and 8 are all ticked.
- **Actions** shows one green run per day.
- A failed run shows a red cross on the Actions page, and the debug channel gets "The publication bot run failed." with a link to the run and `publii.log` attached. If the failure was in setup, tests or saving state, the message reads "The publication bot run failed outside the pipeline step ..." instead. You do not need to cause a failure to test this.

## Go-live checklist
Do this only after the bot has run in test mode for the QA period.
- [ ] The debug-channel messages have looked right for the whole QA period, with no repeats, wrong people or missing days.
- [ ] The review queue is under control: no growing pile of unhandled "Needs review" items.
- [ ] The production sheet is shared with the service account as Editor (SOP-1 step 3).
- [ ] The bot is a member of the production channel `C097CKA5U4X` (SOP-1 step 2).
- [ ] On GitHub, open `config.py` on `main` and click the pencil icon. Change `isLive = False` to `isLive = True`, then click **Commit changes**.
- [ ] From now on, new-publication messages go to `C097CKA5U4X`, and Sheet rows go to the PRODUCTION spreadsheet (`publii.sh` passes `--live`, and the Sheet script refuses `--live` unless `isLive` is True). Review items, summaries and failure alerts still go to the debug channel.
- [ ] Run **Daily publication check** once by hand. Confirm the log says `[INFO] isLive=true`, the summary is in the debug channel, and any new items are in the production channel and the production sheet.
- [ ] Decommission the old server (or at least delete its copy of the Slack token and Google key).

## Rollback
1. Stop the schedule: **Actions**, **Daily publication check**, the **...** menu at the top right, **Disable workflow**.
2. In `config.py`, set `isLive = False` and commit.
3. If a bad run saved bad state, find its "Update YYYYMMDD" commit under **Commits** and revert it: `git pull`, then `git revert <commit-id>`, then `git push`.
4. Clean up what was already posted. The bot cannot undo a post. Delete the Slack message by hand (hover over it, **...**, **Delete message**). Delete wrong rows from the Sheet (right-click the row number, **Delete row**).
5. When it is fixed, use **Enable workflow** on the same menu.

Do not turn the old server's cron back on. Its Google Scholar scraper no longer works, and it would conflict with the new code on `main`.

## If something goes wrong
| You see | Fix |
|---|---|
| Step 4: "Can't automatically merge" | `main` changed after the branch was made, usually the bot's own daily commit to `state/`. Bring the branch up to date: `git checkout <branch> && git merge origin/main`. If only `state/allpubs.json` or `state/delta.json` conflict, keep `main`'s versions: `git checkout --theirs state/ && git add state/ && git commit`. Push, then merge the pull request. |
| No **Run workflow** button, or the workflow is missing from the Actions list | The workflow file is not on `main` yet. Finish step 4. |
| Run fails at **Commit state** with `403` or "permission denied" | Redo step 3, item 3 (Read and write permissions). |
| Run fails at **Commit state** with "protected branch" | Redo step 3, item 4. |
| `[ERROR] Slack token not found` | The `SLACK_BOT_TOKEN` secret is missing or misnamed. Redo step 2. |
| `invalid_auth` | The Slack token is wrong. Update the secret. |
| `not_in_channel` | Invite the bot to that channel (`/invite @botname`). |
| `key_not_activated` | Click the activation link in the OpenAlex email. |
| `429` or "daily budget exhausted" | The `OPENALEX_API_KEY` secret is missing or misnamed. Redo step 2. |
| Sheet step fails with "No such file ... .secret/googleToken" | The `GOOGLE_SERVICE_ACCOUNT_JSON` secret is missing. Redo step 2. This shows up only on a day with new publications. |
| Sheet step fails with a JSON error | The secret holds only part of the key file. Update it with the whole file. |
| Sheet step fails with `403` / "The caller does not have permission" | Share that sheet with the service account's `client_email` as Editor. |
| `[ERROR] --live was passed but isLive is False` | Expected safety lock: `--live` was used by hand while in test mode. Nothing was written. |
| Nothing runs overnight | Scheduled runs are on `main` only and can start late. Wait, then run by hand. See [GitHub scheduling](Workflow.md#github-scheduling). |
| Two bots posting, or `PaphlagonUpdater` commits | The old cron is still on. Redo step 1. |

Next: [SOP-3: Daily operations](SOP-3-Daily-Operations.md).
