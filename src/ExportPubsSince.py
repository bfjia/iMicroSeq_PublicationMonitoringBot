#Export every stored publication dated after a cutoff to a TSV (e.g. to backfill or audit the Google Sheet).
#
#  python src/ExportPubsSince.py 20250601                  -> output/pubsSince20250601.tsv
#  python src/ExportPubsSince.py 20250601 myExport.tsv     -> myExport.tsv
#
#Reads state/allpubs.json. One row per researcher per publication, newest first.
import json
import os
import sys
from dateutil import parser

import paths


def findPubsAfterDateCutoff(allPubs, cutoff):
    rows = []
    for authorID, authorData in allPubs.items():
        for pubID, pub in authorData.get("publications", {}).items():
            try:
                pubDate = parser.parse(pub.get("year") or "")
            except (ValueError, OverflowError):
                print("[WARNING] Invalid date in publication " + pubID + ": " + str(pub.get("year")))
                continue
            if pubDate > cutoff:
                rows.append([authorData.get("Name") or "", pub.get("title") or "", pub.get("year") or "",
                             pub.get("publisher") or "", pub.get("author") or "", str(pub.get("url") or ""),
                             str(pub.get("firstOrLast"))])
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python src/ExportPubsSince.py <cutoff YYYYMMDD> [output.tsv]")
        sys.exit(1)
    cutoffText = sys.argv[1]
    try:
        cutoff = parser.parse(cutoffText)
    except (ValueError, OverflowError):
        print("[ERROR] Invalid cutoff date: " + cutoffText + ". Use YYYYMMDD.")
        sys.exit(1)
    outputFile = sys.argv[2] if len(sys.argv) > 2 else os.path.join(paths.outputDir, "pubsSince" + cutoffText + ".tsv")

    with open(paths.allPubsFile, "r", encoding="utf-8") as f:
        allPubs = json.load(f)
    rows = findPubsAfterDateCutoff(allPubs, cutoff)

    paths.ensureDir(outputFile)
    with open(outputFile, "w", encoding="utf-8", newline="\n") as f:
        f.write("Participant\ttitle\tyear\tpublisher\tauthors\turl\tfirstOrLast\n")
        for row in rows:
            f.write("\t".join(cell.replace("\t", " ").replace("\n", " ") for cell in row) + "\n")
    print("[INFO] " + str(len(rows)) + " publications written to " + outputFile)
