import json
from datetime import datetime, timedelta
from dateutil import parser
import sys

def findPubsAfterDateCutoff(json, cutoff, outputFile):
    # Convert cutoff string to datetime object
    try:
        cutoff = parser.parse(cutoff)
    except ValueError:
        print(f"Invalid cutoff date format: {cutoff}. Use YYYYMMDD.")
        sys.exit(1)

    # Open TSV output file
    with open(outputFile, 'w', encoding='utf-8') as f:
        # Write header
        f.write("Participant\ttitle\tyear\tpublisher\tauthors\turl\tfirstOrLast\n")
        
        for participantID, participantData in json.items():
            for pubID, pubData in participantData["publications"].items():
                try:
                    pubDate = parser.parse(pubData["year"])
                    if pubDate > cutoff:
                        row = [
                            participantData.get("Name",""),
                            pubData["title"] if not None else "",
                            pubData["year"] if not None else "",
                            pubData["publisher"] if not None else "",
                            pubData["author"] if not None else "",
                            str(pubData["url"]) if not None else "",
                            str(pubData["firstOrLast"])
                        ]
                        f.write("\t".join(row) + "\n")
                except ValueError:
                    print(f"Invalid date format in publication {pubID}")


if __name__ == "__main__":
    # if len(sys.argv) < 3:
    #     print("Usage: python filter_pubs.py <input_json_file> <cutoff_date: YYYYMMDD> <output_tsv_file>")
    #     sys.exit(1)

    # jsonFile = sys.argv[1]
    # cutoff = sys.argv[2]
    # outputFile = sys.argv[3]

    jsonFile = "allpubs.json"
    cutoff = "20250601"
    outputFile = "pubsSince20250601.tsv"

    try:
        with open(jsonFile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    findPubsAfterDateCutoff(data, cutoff, outputFile)
    print(f"Filtered data written to {outputFile}")