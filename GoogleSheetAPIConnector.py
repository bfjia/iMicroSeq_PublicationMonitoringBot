import json
from datetime import datetime, timedelta
from dateutil import parser
import sys

from googleapiclient.discovery import build
from google.oauth2 import service_account

def InsertRowIntoGoogleSheets (data, credsPath = "./.secret/googleToken", scopes = ["https://www.googleapis.com/auth/spreadsheets"]):
    try:
        # Authenticate with service account using json file in .secrets

        creds = service_account.Credentials.from_service_account_file(
            credsPath, scopes=scopes
        )

        #connect to the spreadsheet
        spreadsheetID = "14XeOue130U_01iplm2slQgGWtXyZAurWw1cikuDLga0"
        #spreadsheetID = "1IcAkjCkkf7XbLUex8kbSHe47ZM9lYJpg1qTysQb_KA0" #TESTING SPREADSHEET
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Get spreadsheet metadata and find the correct sheet to update
        #spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        #for sheet in spreadsheet["sheets"]:
        #    print(sheet["properties"]["title"], sheet["properties"]["sheetId"])

        #Insert an empty row before row 2
        InsertRowRequest = {
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": 1533674458,  #not 0-based index. have to manually obtain
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

        # Insert in the data into the newly inserted empty row
        range_ = "A2"  # top-left cell of the inserted row

        sheet.values().update(
            spreadsheetId=spreadsheetID,
            range="A2", #data begins in the first column. 
            valueInputOption="RAW",
            body={"values": [data]},
        ).execute()

        print("[INFO] Row inserted successfully into google sheets. Data: " + str(data))
    except Exception as e:
       print("[ERROR] Issue inserting row into google sheets: " + str(e))

def getNewPublications(json):
    #Participant	title	year	publisher	authors	url	firstOrLast    
    pubList = []

    for participantID, participantData in json.items():
        for pubID, pubData in participantData["publications"].items():
            try:
                #assuming everything here 
                if (parser.parse(pubData['year']).year >= 2025):
                    row = [
                        participantData.get("Name",""),
                        pubData["title"] if not None else "",
                        datetime.today().strftime("%m/%d/%Y") if not None else "",
                        pubData["publisher"] if not None else "",
                        pubData["author"] if not None else "",
                        str(pubData["url"]) if not None else "",
                        str(pubData["firstOrLast"]),
                        "",
                        pubData['year']
                    ]
                    pubList.append(row)
                else:
                    print("[INFO] Nothing new to insert.")

            except Exception as e:
                print("[ERROR] There was an issue parsing the delta.json file: " + str(e))
                return False
    return pubList

if __name__ == "__main__":
    jsonFile = "delta.json"

    try:
        with open(jsonFile, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    pubList = getNewPublications(data)

    if pubList == False:
        print("[ERROR] Failed to get publication list from delta.json")
    elif len(pubList) == 0:
        print("[INFO] Nothing new to insert into Google Sheets.")
    else:
        #First, lets check for duplicates. If found only keep 1 row. 
        existingTitles = {}
        for i in range(0, len(pubList)):
            if pubList[i][1] in existingTitles.keys():
                existingTitles[pubList[i][1]][0] =  existingTitles[pubList[i][1]][0] + "," + pubList[i][0]
            else:
                existingTitles[pubList[i][1]] = pubList[i]
        #convert the dict values to list and this should be it.
        cleanedPubList = list(existingTitles.values())
        for pub in cleanedPubList:
            InsertRowIntoGoogleSheets(pub)
