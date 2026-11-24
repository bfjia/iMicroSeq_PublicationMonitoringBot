#Where the bot's files live. Every path is absolute, so the scripts work from any folder.
#Importing this module also puts the repo root on sys.path, so `import config` finds the root config.py.
#publii.sh and .github/workflows/ use the same layout: change them together.
import os
import sys

srcDir = os.path.dirname(os.path.abspath(__file__))
repoDir = os.path.dirname(srcDir)
if repoDir not in sys.path:
    sys.path.insert(0, repoDir)

stateDir = os.path.join(repoDir, "state")     # bot memory, committed by the workflow
outputDir = os.path.join(repoDir, "output")   # generated each run, gitignored

rosterFile = os.path.join(repoDir, "researchers.tsv")
allPubsFile = os.path.join(stateDir, "allpubs.json")
deltaFile = os.path.join(stateDir, "delta.json")
# One-time catch-up: if this file exists (one line, a date such as 2026-11-05), the next run ignores the stored state,
# re-indexes from OpenAlex and announces everything indexed or published since that date. The run deletes it.
reindexFile = os.path.join(stateDir, "reindexSince.txt")
# The old Google Scholar bot's final state (its last run was 2026-11-05). A re-index skips titles found here.
scholarStateFile = os.path.join(repoDir, "legacy", "allpubsScholar.json")
lastAllPubsFile = os.path.join(outputDir, "last_allpubs.json")
msgFile = os.path.join(outputDir, "msg.md")
reviewFile = os.path.join(outputDir, "review.md")
summaryFile = os.path.join(outputDir, "summary.md")
addResearcherReportFile = os.path.join(outputDir, "addResearcherReport.md")


def fromRepo(path):
    """A path from config.py (relative to the repo root, or absolute) as an absolute path."""
    return os.path.join(repoDir, path)


def ensureDir(filePath):
    """Create the folder a file will be written into."""
    folder = os.path.dirname(filePath)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
