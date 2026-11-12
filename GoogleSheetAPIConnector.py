import json
from datetime import datetime, timedelta
from dateutil import parser
import sys
import os

from googleapiclient.discovery import build
from google.oauth2 import service_account

# ---- Configuration ----
# Settings live in config.py (see the comments there).
# Rows go to the TEST copy unless --live is passed AND config.isLive is True (publii.sh passes --live only then).
# The production sheet must never receive test rows.
import config
from config import productionSpreadsheetID, testSpreadsheetID, sheetTabID, googleCredentialsFile, googleScopes

def getCredentials(credsPath = googleCredentialsFile, scopes = googleScopes):
    #env GOOGLE_SERVICE_ACCOUNT_JSON (the JSON content) wins, else the file in .secret
    envJson = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if envJson:
        return service_account.Credentials.from_service_account_info(json.loads(envJson), scopes=scopes)
    return service_account.Credentials.from_service_account_file(credsPath, scopes=scopes)

def InsertRowIntoGoogleSheets (data, creds, spreadsheetID):
    try:
        #connect to the spreadsheet
        service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        sheet = service.spreadsheets()

        #Insert an empty row before row 2
        InsertRowRequest = {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheetTabID,
                            "dimension": "ROWS",
                            "startIndex": 1, #insert after row 1, before row two.
                            "endIndex": 2
                        },
                        "inheritFromBefore": False
                    }
                }
            ]
        }
        sheet.batchUpdate(spreadsheetId=spreadsheetID, body=InsertRowRequest).execute()

        # Insert the data into the newly inserted empty row
        sheet.values().update(
            spreadsheetId=spreadsheetID,
            range="A2", #data begins in the first column. 
            valueInputOption="RAW",
            body={"values": [data]},
        ).execute()

        print("[INFO] Row inserted into " + ("PRODUCTION" if spreadsheetID == productionSpreadsheetID else "TEST") + " google sheet. Data: " + str(data))
        return True
    except Exception as e:
        print("[ERROR] Issue inserting row into google sheets: " + str(e))
        return False

def getNewPublications(json):
    #Participant	title	year	publisher	authors	url	firstOrLast    
    pubList = []

    for participantID, participantData in json.items():
        for pubID, pubData in participantData["publications"].items():
            try:
                row = [
                    participantData.get("Name") or "",
                    pubData.get("title") or "",
                    datetime.today().strftime("%m/%d/%Y"),
                    pubData.get("publisher") or "",
                    pubData.get("author") or "",
                    str(pubData.get("url") or ""),
                    str(bool(pubData.get("firstOrLast"))),
                    "",
                    pubData.get("year") or ""
                ]
                pubList.append(row)

            except Exception as e:
                print("[ERROR] There was an issue parsing the delta.json file: " + str(e))
                return False
    return pubList

if __name__ == "__main__":
    jsonFile = "delta.json"
    dryRun = "--dryRun" in sys.argv
    isLive = "--live" in sys.argv
    if isLive and config.isLive is not True:
        # second lock: --live alone is not enough to write to the production sheet
        print("[ERROR] --live was passed but isLive is False in config.py; refusing to write to the PRODUCTION sheet.")
        sys.exit(1)
    spreadsheetID = productionSpreadsheetID if isLive else testSpreadsheetID
    print("[INFO] Google Sheet target: " + ("PRODUCTION" if isLive else "TEST copy") + (" (dry run, nothing written)" if dryRun else ""))

    try:
        with open(jsonFile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Error reading JSON file: {e}")
        sys.exit(1)

    pubList = getNewPublications(data)

    if pubList == False:
        print("[ERROR] Failed to get publication list from delta.json")
        sys.exit(1)
    elif len(pubList) == 0:
        print("[INFO] Nothing new to insert into Google Sheets.")
    else:
        #First, lets check for duplicates. If found only keep 1 row. 
        existingTitles = {}
        for i in range(0, len(pubList)):
            if pubList[i][1] in existingTitles.keys():
                names = existingTitles[pubList[i][1]][0].split(",")
                if pubList[i][0] not in names:
                    existingTitles[pubList[i][1]][0] = existingTitles[pubList[i][1]][0] + "," + pubList[i][0]
            else:
                existingTitles[pubList[i][1]] = pubList[i]
        #convert the dict values to list and this should be it.
        cleanedPubList = list(existingTitles.values())
        if dryRun:
            for pub in cleanedPubList:
                print("[INFO] [DRY RUN] Would insert row: " + str(pub))
        else:
            try:
                creds = getCredentials()
            except Exception as e:
                print("[ERROR] Could not load google credentials: " + str(e))
                sys.exit(1)
            failures = 0
            for pub in cleanedPubList:
                if not InsertRowIntoGoogleSheets(pub, creds, spreadsheetID):
                    failures += 1
            if failures > 0:
                print("[ERROR] " + str(failures) + " row(s) failed to insert.")
                sys.exit(1)
