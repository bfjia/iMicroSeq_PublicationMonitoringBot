import json
import os
import shutil
from scholarly import scholarly
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import time
import re
import random
from dateutil import parser
import difflib

# ---- Configuration ----
authorID = 'PLiQF5oAAAAJ'  # e.g., '8W8gwisAAAAJ'
jsonFile = 'allpubs.json'
lastJsonFile = 'last_allpubs.json'
authorsToMonitor = "authors.txt"
deltaJsonFile = 'delta.json'

class publications:
    def __init__(self, title, year, publisher, author, url, firstOrLast, publicationID):
        self.title = title
        self.year = year
        self.publisher = publisher
        self.author = author
        self.url = url
        self.firstOrLast = firstOrLast
        self.publicationID = publicationID

    def returnData(self):
        return [self.title, self.year, self.publisher, self.author, self.url, self.firstOrLast]
    
    def toDict(self):
        return {
            "title": self.title,
            "year": self.year,
            "publisher": self.publisher,
            "author": self.author,
            "url": self.url,
            "firstOrLast": self.firstOrLast
        }

#fetch the most recent 100 publications
def fetchPublicationsUsingSelenium(driver, scholarID, previousJsonData, maxYear = 2020):
    url = f"https://scholar.google.com/citations?user={scholarID}&hl=en&cstart=0&pagesize=100&sortby=pubdate"
    driver.get(url)
    time.sleep(2)  # Let page load
    
    try:
        name_elem = driver.find_element(By.ID, "gsc_prf_in")
        profileName = name_elem.text.strip()
        print("[INFO] " + "Looking for publications by " + profileName + " with google scholar ID " + scholarID)
    except Exception as e:
        profileName = "Unknown"
        print("[ERROR] " + "Cannot fetch author name for ID " + scholarID + " Error: " + str(e))

    publicationList = {}

    pubs = driver.find_elements(By.CSS_SELECTOR, 'tr.gsc_a_tr')
    for pub in pubs:
        # try:
            title_elem = pub.find_element(By.CLASS_NAME, 'gsc_a_at')
            title = title_elem.text


            publicationURLElement = title_elem.get_attribute("href")
            publicationURL = "https://scholar.google.com" + publicationURLElement if publicationURLElement.startswith("/citations?") else publicationURLElement
            
            match = re.search(r'citation_for_view=[^:]+:([^&]+)', publicationURL)
            pubID = match.group(1)

            #check to see if this is a new author or if the paper is new. if not, then dont bother querying and use existing data to save time.
            if scholarID not in previousJsonData.keys() or pubID not in previousJsonData[authorID]['publications'].keys():
                #open a new window and go to the publication url
                driver.execute_script("window.open('');")
                driver.switch_to.window(driver.window_handles[1])
                driver.get(publicationURL)
                time.sleep(2)
                try:
                    external_link = driver.find_element(By.CLASS_NAME, 'gsc_oci_title_link')
                    actualPubURL = external_link.get_attribute("href")
                except Exception as e:
                    actualPubURL = None
                    print(e)

                # Extract metadata rows
                meta_rows = driver.find_elements(By.CLASS_NAME, 'gsc_oci_field')
                meta_values = driver.find_elements(By.CLASS_NAME, 'gsc_oci_value')
                metadata = dict()
                for i in range(len(meta_rows)):
                    key = meta_rows[i].text.lower().strip()
                    val = meta_values[i].text.strip()
                    metadata[key] = val
                
                #switch back to the main window
                driver.close()
                driver.switch_to.window(driver.window_handles[0])

                pubDate = metadata['publication date'] if 'publication date' in metadata else "Unknown"
                journal = metadata['journal'] if 'journal' in metadata else (metadata['publisher'][0] if 'publisher' in metadata else "Unknown")
                authors = metadata['authors'] if 'authors' in metadata else "Unknown" 

                profileName2 = profileName.lower()
                firstAuthor = authors.split(",")[0].strip()
                lastAuthor = authors.split(",")[-1].strip()
                similarityFirst = difflib.SequenceMatcher(None, profileName2, firstAuthor).ratio()
                similarityLast = difflib.SequenceMatcher(None, profileName2, lastAuthor).ratio()
                firstOrLastAuthor = True  if similarityFirst > 0.7 or similarityLast > 0.7 else False
                publication = publications(title, pubDate, journal, authors, actualPubURL, firstOrLastAuthor,  pubID)

                #found all publication after the max year, break the loop, dont actually add the publication
                if (parser.parse(pubDate).year < maxYear):
                    print("[INFO] Found all publication after " + str(maxYear))
                    break

                publicationList[pubID] = publication.toDict()
                print("[INFO] " + "Found new publication with ID " + pubID + " Titled: " + title)
                

            else:
                print("[DEBUG] " + "Found known publication with ID " + pubID)
                publicationList[pubID] = previousJsonData[authorID]['publications'][pubID]
        # except Exception as e:
        #     print("Skipping one pub due to error:", e)

    return {'Name' : profileName, 'total_publications' : str(len(publicationList)), 'publications':publicationList}

#given an google scholar ID, find all publications by that user.
def fetchPublications(authorID, previousJsonData):
    # Retrieve author by Google Scholar ID
    author = scholarly.fill(scholarly.search_author_id(authorID))
    authorName = author['name']
    print("[INFO] " + "Looking for publications by " + authorName + " with google scholar ID " + authorID)
    publicationList = {}
    for pub in author['publications']:
        pubID = pub['author_pub_id'].split(":")[1]

        #add a check to skip indexing papers older than 2020. Else we have a very big database.
        if ('pub_year' in pub['bib']):
            if (int(pub['bib']['pub_year']) < 2020):
                print("[INFO] Skipping publication with id " + pubID + " because it's older than 2020")
                continue
        else:
            print("[INFO] No date information")

        #check to see if this is a new author or if the paper is new. if not, then dont bother querying and use existing data to save time.
        if authorID not in previousJsonData.keys() or pubID not in previousJsonData[authorID]['publications'].keys():
            print("[INFO] " + "Found new publication with ID " + pubID)
            try:
                pub_filled = scholarly.fill(pub)
                bib = pub_filled.get('bib', {})
                authorList = bib.get('author').split(" and ")
                publication = publications(bib.get('title'), bib.get('pub_year'), bib.get('publisher'), authorList, pub_filled.get('pub_url'), True if authorList[0] == authorName or authorList[-1] == authorName else False,  pubID)
                publicationList[pubID] = publication.toDict()
            except Exception as e:
                print("[ERROR] " + "Error getting publication info using ID " + pubID + ". Error: " + str(e))
                publicationList[pubID] = {
                                            "title": "Error" + str(e),
                                            "year": "Unkonwn",
                                            "publisher": "Unkonwn",
                                            "author": "Unkonwn",
                                            "url": "Unkonwn",
                                            "firstOrLast": False
                                        }
        else:
            print("[DEBUG] " + "Found known publication with ID " + pubID)
            publicationList[pubID] = previousJsonData[authorID]['publications'][pubID]
    return {'Name' : authorName, 'total_publications' : str(len(publicationList)), 'publications':publicationList}

#save json data
def saveJson(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

#load json data
def loadJson(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

if __name__ == "__main__":
    if os.path.exists(jsonFile):
        shutil.copy2(jsonFile, lastJsonFile)
    lastPublicationJson = loadJson(lastJsonFile)
    with open(authorsToMonitor, 'r') as f:
        authorIDList = [line.strip() for line in f]


    # Setup headless Firefox
    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)


    print("[INFO] " + "Indexing publications...")
    allPubs = {}
    for authorID in authorIDList:
        allPubs[authorID] = fetchPublicationsUsingSelenium(driver, authorID, lastPublicationJson)

    saveJson(allPubs, jsonFile)

    currentPublicationJson = loadJson(jsonFile)
    driver.quit()


    #look for differences
    print("[INFO] " + "Looking for anything new...")
    newPublications = {}
    for authorID in authorIDList:
        id = authorID
        #we just added someone new to the list. DO NOT delta them until the next time.
        if id in lastPublicationJson.keys():
            if currentPublicationJson[id]['publications'].keys() != lastPublicationJson[id]['publications'].keys():
                diff = [item for item in currentPublicationJson[id]['publications'].keys() if item not in lastPublicationJson[id]['publications'].keys()]
                if len(diff) > 0:
                    print(currentPublicationJson[id]['Name'] + " have " + str(len(diff)) + " new publications!")
                    for pubid in diff:
                        if (authorID not in newPublications.keys()):
                            newPublications[authorID] = {
                                'Name' : currentPublicationJson[id]['Name'],
                                'total_new' : str(len(diff)),
                                'publications' : {pubid : currentPublicationJson[id]['publications'][pubid]}
                            }
                        else:
                            newPublications[authorID]['publications'][pubid] = currentPublicationJson[id]['publications'][pubid]
            else:
                print("[INFO] " + currentPublicationJson[id]['Name'] + " have no new publications.")
        else:
            print ("[INFO] " + currentPublicationJson[id]['Name'] + " is a new author added to the surveillance list, we ignoring until next time.")
    saveJson(newPublications, deltaJsonFile)

    #Lets format the message for the slack bot
    deltaJson = loadJson(deltaJsonFile)

    Msg = ""
    if len(deltaJson) > 0:
        for authorID in deltaJson:
            if len(deltaJson[authorID]['publications']) > 1:
                Msg = Msg + deltaJson[authorID]['Name'] + " have new publications: \n"
                for pubID in deltaJson[authorID]['publications']:
                    pub = deltaJson[authorID]['publications'][pubID]
                    Msg = Msg + "* " + pub['title'] + ". Published in " + pub['publisher'] + ". Available at " + pub['url'] + "\n"
                Msg = Msg + "Congratulations!\n\n"
            else:
                for pubID in deltaJson[authorID]['publications']:
                    pub = deltaJson[authorID]['publications'][pubID]
                    Msg = Msg + deltaJson[authorID]['Name'] + " have a new publication titled: \"" + pub['title'] + ".\" Published in " + pub['publisher'] + ". Available at " + pub['url'] + " \nCongratulations!\n\n" 

    with open ("msg.md", 'w') as f:
        f.writelines(Msg)

    