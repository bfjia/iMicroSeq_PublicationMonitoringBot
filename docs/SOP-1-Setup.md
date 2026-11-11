# SOP-1: One-time setup and local test run

## Purpose
Create the three accounts and credentials the bot needs, and prove it works on your own computer without touching anything live.

## Who / when
Whoever takes over the bot, once. Repeat only if a credential is lost or replaced.

## Before you start
- A GitHub login with access to the repository `bfjia/iMicroSeq_PublicationMonitoringBot`.
- Admin rights on the Slack workspace (to create or edit the app).
- Access to the Google Cloud project that owns the service account, and Editor rights on both Google Sheets.
- Python 3.8 or newer (3.11 or newer recommended) and `git`.

## Steps

### 1. OpenAlex API key
1. Go to openalex.org and sign in or create a free account.
2. Open **Settings** and then **API key**. Create a key and copy it.
3. Click the activation link in the email OpenAlex sends. Until you do, the key fails with `key_not_activated`.

Why it is required: a free key has a budget of $1 per day and this bot uses about $0.01 per day. Without a key the budget is $0.10 per day, shared with everyone on the same IP address. On GitHub's shared runners that is effectively unusable.

### 2. Slack bot token
1. Go to api.slack.com/apps and open the publication bot app (or create one).
2. Under **OAuth & Permissions**, add the Bot Token Scopes `chat:write` and `files:write`.
3. Click **Install to Workspace** (or **Reinstall**). Copy the **Bot User OAuth Token**. It starts with `xoxb-`.
4. In Slack, open `#publication_monitor_debug` (id `C09D86E4T5H`) and type `/invite @` followed by the bot's name. Do the same in the production channel `C097CKA5U4X`.

### 3. Google service account
1. In the Google Cloud console, open the service account whose email ends in `@imicroseqpublicationmonitor.iam.gserviceaccount.com`.
2. If you already have its JSON key (the old server kept it as `.secret/googleToken`), reuse that. Otherwise open **Keys**, then **Add key**, then **Create new key**, type **JSON**. A file downloads. Keep it safe.
3. Open the TEST copy of the Google Sheet (named `TEST_COPY_OF_iMicroSeqPubsSince20250601`), click **Share**, paste the service account's `client_email` and give it **Editor**.
4. Do the same for the production sheet (the real one the team uses; it has a tab named `iMicroSeqPubsSince20250601`).

Share **both** sheets. The bot only writes to the test copy until you go live, but going live will fail if the production sheet was not shared.

### 4. Get the code
```bash
git clone git@github.com:bfjia/iMicroSeq_PublicationMonitoringBot.git
cd iMicroSeq_PublicationMonitoringBot
git checkout openalex-migration
pip install -r requirements.txt
```

### 5. Put the credentials in place (never commit them)
Choose one way. Both are kept out of git.

Environment variables (replace the values):
```bash
export OPENALEX_API_KEY="your-openalex-key"
export SLACK_BOT_TOKEN="xoxb-your-token"
export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat /path/to/downloaded-key.json)"
```

Or files in a `.secret/` folder at the top of the repo: `.secret/pubiioauthtoken` (the Slack token on one line) and `.secret/googleToken` (the JSON file). The OpenAlex key is only read from the environment variable `OPENALEX_API_KEY`.

### 6. Run the offline tests
```bash
python tests/RunOfflineTests.py
```

### 7. Do a local test run
```bash
PYTHON=python3 ./publii.sh
```
While `isLive=false` in `publii.sh`, this posts only to the debug channel and writes only to the TEST sheet. It never touches the production channel or sheet.

## Check it worked
- The offline tests finish without errors.
- The debug channel receives an "[INFO] Run summary ..." message, plus "No new publication found." or a list.
- `git status` shows `allpubs.json` and `delta.json` possibly changed. Do not commit them from a test run: run `git checkout allpubs.json delta.json` to undo.

## If something goes wrong
| You see | Fix |
|---|---|
| `key_not_activated` | Click the activation link in the OpenAlex email. |
| `daily budget exhausted` or HTTP 429 | The key is missing or not exported in this terminal. |
| `[ERROR] Slack token not found` | Set `SLACK_BOT_TOKEN` or create `.secret/pubiioauthtoken`. |
| `not_in_channel` | Invite the bot to that channel (step 2.4). |
| `invalid_auth` | The token is wrong or from a different app. Copy it again. |
| Sheet permission error | Share that sheet with the service account email as Editor (step 3). |

Next: [SOP-2: Deploy and go live](SOP-2-Deploy.md). Overview: [Workflow](Workflow.md).
