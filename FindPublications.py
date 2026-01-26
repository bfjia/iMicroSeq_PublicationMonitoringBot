import json
import os
import shutil
from scholarly import scholarly
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
import time
import re
import random
from dateutil import parser
import difflib
import urllib
import requests

# ---- Configuration ----
authorID = 'PLiQF5oAAAAJ'  # e.g., '8W8gwisAAAAJ'
jsonFile = 'allpubs.json'
lastJsonFile = 'last_allpubs.json'
authorsToMonitor = "authors.txt"
deltaJsonFile = 'delta.json'
AuthorNameSimilarityFuzzyMatchingCutoff = 0.75

class publications:
    def __init__(self, title, year, publisher, author, url, firstOrLast, publicationID, datasource):
        self.title = title
        self.year = year
        self.publisher = publisher
        self.author = author
        self.url = url
        self.firstOrLast = firstOrLast
        self.publicationID = publicationID
        self.datasource = datasource

    def returnData(self):
        return [self.title, self.year, self.publisher, self.author, self.url, self.firstOrLast, self.datasource]
    
    def toDict(self):
        return {
            "title": self.title,
            "year": self.year,
            "publisher": self.publisher,
            "author": self.author,
            "url": self.url,
            "firstOrLast": self.firstOrLast,
            "datasource":self.datasource
        }
    
def extractMetadataFromCrossRef(title, profileName, pubID):
    # URL encode the title


    #NOTE:2025-11-17 WE DO NOT WANT TO PULL FROM CROSSREF BECAUSE THE PUBLISHER IS WRONG and biorxiv is stored in the "insitutition" field for some reason
    return "defer"


    query = urllib.parse.quote(title)
    url = f"https://api.crossref.org/works?query.title={query}&rows=1"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Check if there are any results
        if data['message']['items']:
            item = data['message']['items'][0]

            # Extract relevant fields
            pubDate = "/".join(str(x) for x in item.get('issued', {}).get('date-parts', [[None]])[0])
            if pubDate == 'None' or len(pubDate) < 6: #It may not have been officially published yet. Let's use the online date.
                if 'published-online' in item.keys():
                    pubDate = "/".join(str(x) for x in item.get('published-online', {}).get('date-parts', [[None]])[0])
                elif 'published-print' in item.keys():
                    pubDate = "/".join(str(x) for x in item.get('published-print', {}).get('date-parts', [[None]])[0])
                else:
                    pubDate = "/".join(str(x) for x in item.get('published', {}).get('date-parts', [[None]])[0])
                if pubDate == 'None' or len(pubDate) < 6: 
                    pubDate = "/".join(str(x) for x in item.get('indexed', {}).get('date-parts', [[None]])[0])


            journal = item.get('publisher', 'N/A')
            #journal = item.get('institution', "N/A")[0]['name']
            doi = item.get('DOI', 'N/A')
            actualPubURL = f"https://doi.org/{doi}" if doi != 'N/A' else 'N/A'

            authors = item.get('author', [])
            authorList = []
            for author in authors:
                name_parts = []
                if 'given' in author:
                    name_parts.append(author['given'])
                if 'family' in author:
                    name_parts.append(author['family'])
                authorList.append(' '.join(name_parts))
            authors = ",".join(authorList)

            profileName2 = profileName.lower()
            firstAuthor = authors.split(",")[0].strip()
            lastAuthor = authors.split(",")[-1].strip()
            similarityFirst = difflib.SequenceMatcher(None, profileName2, firstAuthor).ratio()
            similarityLast = difflib.SequenceMatcher(None, profileName2, lastAuthor).ratio()
            firstOrLastAuthor = True  if similarityFirst > 0.7 or similarityLast > 0.7 else False
            publication = publications(title, pubDate, journal, authors, actualPubURL, firstOrLastAuthor,  pubID, "CrossRef")

            #add a sanity check to ensure the crossref best hit is actually our paper of interest
            obtainedTitle = item['title'][0].lower()
            similarityTitle = difflib.SequenceMatcher(None, obtainedTitle.lower(), title.lower()).ratio()

            if similarityTitle < 0.9: #best match is NOT the same as our title
                #lets check if the author is in the author list. if it is, it's probably the right paper anyways.
                if (similarityTitle > 0.75): #add a 75% requirement for title matching. There's cases in which two similar titles from the same author impacts the fuzzy search.
                    for author in authors.split(","):
                        similarityAuthor = difflib.SequenceMatcher(None, author.lower(), profileName.lower()).ratio()
                        if (similarityAuthor > 0.7): #likely correct best match
                            print ("[INFO] Slight Mismatching of CrossRef titles but participant in Author list. Keep result. TSIMILARITY: ", str(similarityTitle), " FOUND: " + obtainedTitle, " ORIGINAL: " + title.lower() + "PSIMILARITY: ", str(similarityAuthor), " FOUND: " + author.lower(), " ORIGINAL: " + profileName.lower())
                            return publication
                    print ("[DEBUG] Slight Mismatching of CrossRef title but participant not in Author list. Defering to Google Scholars. TSIMILARITY: ", str(similarityTitle), " FOUND: " + obtainedTitle, " ORIGINAL: " + title.lower())

                print("[ERROR] CrossRef title does not meeting the threshhold and participant not in author list. Defering to Google Scholars. SIMILARITY: ", str(similarityTitle), " FOUND: " + obtainedTitle, " ORIGINAL: " + title.lower())
                return 'defer'
            elif similarityTitle != 1:
                print ("[DEBUG] None exact matching of CrossRef titles but passed threshold. SIMILARITY: ", str(similarityTitle), " FOUND: " + obtainedTitle, " ORIGINAL: " + title.lower())

            return publication
        else:
            print("[ERROR] Error or nothing found CrossRef. defer to use google scholar instead.")
            return "defer"

    except requests.RequestException as e:
        print("[ERROR] error fetching data from CrossRef" + str(e))
        return None
    
#extract publication metadata from google scholar's summary page
def extractMetadataFromScholarSummary(driver, publicationURL, profileName, title, pubID):
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

        #format the metadata. 
    pubDate = metadata['publication date'] if 'publication date' in metadata else "Unknown"
    journal = metadata['journal'] if 'journal' in metadata else (metadata['publisher'][0] if 'publisher' in metadata else "Unknown")
    authors = metadata['authors'] if 'authors' in metadata else "Unknown" 

    profileName2 = profileName.lower()
    firstAuthor = authors.split(",")[0].strip()
    lastAuthor = authors.split(",")[-1].strip()
    similarityFirst = difflib.SequenceMatcher(None, profileName2, firstAuthor).ratio()
    similarityLast = difflib.SequenceMatcher(None, profileName2, lastAuthor).ratio()
    firstOrLastAuthor = True  if similarityFirst > AuthorNameSimilarityFuzzyMatchingCutoff or similarityLast > AuthorNameSimilarityFuzzyMatchingCutoff else False
    publication = publications(title, pubDate, journal, authors, actualPubURL, firstOrLastAuthor,  pubID, "Scholars")
    return publication

#fetch the most recent 100 publications
def fetchPublicationsUsingSelenium(driver, scholarID, previousJsonData, maxYear = 2020, maxRetries = 20):
    url = f"https://scholar.google.com/citations?user={scholarID}&hl=en&cstart=0&pagesize=100&sortby=pubdate"
    
    for attempt in range(1, maxRetries + 1):
        try:
            driver.set_page_load_timeout(20)  # Set timeout in seconds
            driver.get(url)
            break  # success, break out of loop
        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            if attempt < maxRetries:
                print(f"Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("All attempts failed.")
    
    time.sleep(5)  # Let page load
    
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
                #open a new window and go to the publication url to extract it's metadata
                #publication = extractMetadataFromScholarSummary(driver, publicationURL, profileName, title)
                publicationScholar = extractMetadataFromScholarSummary(driver, publicationURL, profileName, title, pubID)

                #for cases in which only a year is reported by google scholars. use crossref to see if we can find additional information.
                #NEW: CrossRef can sometimes report wrong information. We don't really care about anything before 2025 anyways so lets just skip this if its a publication before 2025. 
                if len(publicationScholar.toDict()['year']) < 6 and parser.parse(publicationScholar.toDict()['year']).year >= 2025:
                    publicationCrossRef = extractMetadataFromCrossRef(title, profileName, pubID)

                    if publicationCrossRef == "defer":
                        publication = publicationScholar
                    elif publicationCrossRef == None: #something's wrong with teh request, lets try again for 10 times
                        for i in range(1,10):
                            print("[INFO] Trying to fetch metadata again for " + str(pubID))
                            time.sleep(2)
                            publicationCrossRef = extractMetadataFromCrossRef(title, profileName, pubID)
                            if publicationCrossRef != None:
                                publication = publicationCrossRef
                                break
                        if publicationCrossRef == None: #if the request still fails, try it again with google scholars.
                            print("[ERROR] CrossRef unaccessible or no data found.")
                            publication = publicationScholar
                    else:
                        publication = publicationCrossRef
                
                    if publication == None or publication == "defer":
                        publication = publicationScholar
                else:
                    publication = publicationScholar
                    
                if publication==None: #add acheck to make sure we found a publication. Shouldn't actually hit here if we use google scholars.
                    print("[ERROR] Absolutely Nothing found.")
                    exit(99)


                #found all publication after the max year, break the loop, dont actually add the publication
                if publication.toDict()['year'] == "Unknown":
                    publication.year = "2025"

                if (parser.parse(publication.toDict()['year']).year < maxYear):
                    print("[INFO] Found all publication after " + str(maxYear))
                    break

                publicationList[pubID] = publication.toDict()
                print("[INFO] " + "Found new publication with ID " + pubID + " Titled: " + title)
                

            else:
                print("[DEBUG] " + "Found known publication with ID " + pubID)
                publicationList[pubID] = previousJsonData[authorID]['publications'][pubID]

    # Sometimes, the publications in previousJsonData doesnt show up in the new list. 
    # sometimes it's because they are old manuscript outside the top 100 list.
    # Other times, it's actually new publications that got deindexed for some reason unknown.
    # Either way, let's brute force the known publications back into the publicationList. 
    keysInPrevButNotCur = set(previousJsonData[authorID]['publications'].keys()) - set(publicationList.keys())
    if len(keysInPrevButNotCur) > 0:
        print("[WARNING] " + "There were existing publications that were not indexed in this round " + str(keysInPrevButNotCur))
        for key in keysInPrevButNotCur:
            publicationList[key] = previousJsonData[authorID]['publications'][key]

        # except Exception as e:
        #     print("Skipping one pub due to error:", e)

    return {'Name' : profileName, 'total_publications' : str(len(publicationList)), 'publications':publicationList}

#given an google scholar ID, find all publications by that user.
def fetchPublicationsWithScholarly(authorID, previousJsonData):
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
                publication = publications(bib.get('title'), bib.get('pub_year'), bib.get('publisher'), authorList, pub_filled.get('pub_url'), True if authorList[0] == authorName or authorList[-1] == authorName else False,  pubID, "Scholarly")
                publicationList[pubID] = publication.toDict()
            except Exception as e:
                print("[ERROR] " + "Error getting publication info using ID " + pubID + ". Error: " + str(e))
                publicationList[pubID] = {
                                            "title": "Error" + str(e),
                                            "year": "Unkonwn",
                                            "publisher": "Unkonwn",
                                            "author": "Unkonwn",
                                            "url": "Unkonwn",
                                            "firstOrLast": False,
                                            "datasource": "ERROR"
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

def formatSlackMsg(deltaJson):
    Msg = ""
    if len(deltaJson) > 0:
        Msg = "[NEW!]\n\n"
        for authorID in deltaJson:
            #if len(deltaJson[authorID]['publications']) > 1:
                #Msg = Msg + deltaJson[authorID]['Name'] + " has new publications: \n"
            pubsToOutput = []
            for pubID in deltaJson[authorID]['publications']:
                pub = deltaJson[authorID]['publications'][pubID]
                if (parser.parse(pub['year']).year >= 2025):
                    pubsToOutput.append(pub)
                    #Msg = Msg + "* " + pub['title'] + ". Published in " + pub['publisher'] + ". Available at " + pub['url'] + "\n"
                else:
                    print("[WARNING] Some how picked up a old publication in delta Json: (" + 
                            pub['year'] + ") " + pub['title'] + ". Published in " + pub['publisher'] + ". Available at " + pub['url'] + "\n")
            
            if len(pubsToOutput) > 1:
                Msg = Msg + deltaJson[authorID]['Name'] + " has new publications: \n"
            elif len(pubsToOutput )== 1:
                Msg = Msg + deltaJson[authorID]['Name'] + " has a new publication: \n"
            
            for pub in pubsToOutput:
                Msg = Msg + "* "
                if pub["firstOrLast"]:
                    Msg = Msg + "[First or Senior Author] "
                Msg = Msg + pub['title'] + ". "
                if pub["publisher"] != None:
                    Msg = Msg + "Published in " + pub['publisher'] + ". "
                if pub['url'] != None:
                    Msg = Msg + ". Available at " + pub['url'] + ". "
                Msg = Msg + "\n"

        #In cases of all pubs were old ones, just output nothing new found.
        if Msg == "[NEW!]\n\n":
            Msg = "[INFO]\nNo new publication found."
    else:
        Msg = "[INFO]\nNo new publication found."

    return Msg


def formatSlackMsg2(deltaJson):
    Msg = ""
    if len(deltaJson) == 0: #if theres nothing in the json file, return the appropariate msg
        return "[INFO]\nNo new publication found."
    else:
        #first we switch from scholarID based index to publication title based index.
        publicationTitleKVP = {}
        for authorID in deltaJson:
            for pubID in deltaJson[authorID]['publications']:
                pub = deltaJson[authorID]['publications'][pubID]
                title = pub['title']
                if (parser.parse(pub['year']).year >= 2025):
                    if title not in publicationTitleKVP.keys(): #new pub
                        publicationTitleKVP[title] = pub
                        publicationTitleKVP[title]["Name"] = deltaJson[authorID]["Name"]
                    else: #existing pub, append new author to existing list
                        publicationTitleKVP[title]["Name"] = publicationTitleKVP[title]["Name"]  + ", " + deltaJson[authorID]["Name"]
                else:
                    print("[WARNING] Some how picked up a old publication in delta Json: (" + 
                            pub['year'] + ") " + pub['title'] + ". Published in " + pub['publisher'] + ". Available at " + pub['url'] + "\n")
        
        # If there's no new publications, just return the msg. Else,  we reindex the publications with the Name as the index .
        if len(publicationTitleKVP.keys()) == 0:
            return "[INFO]\nNo new publication found."
        else:
            publicationNameKVP = {}
            for title in publicationTitleKVP:
                pub = publicationTitleKVP[title]
                name = pub["Name"]
                if name not in publicationNameKVP:
                    publicationNameKVP[name] = [pub]
                else:
                    publicationNameKVP[name].append(pub)


        #Format the output msg
        for name in publicationNameKVP:
            if len(publicationNameKVP[name]) == 1: #only  1 publication:
                pub = publicationNameKVP[name][0]
                Msg = Msg + name + " has a new publication: \n"
                Msg = Msg + "  * " + pub["title"] + ". "
                if pub['publisher'] != None:
                    Msg = Msg + " Published in " + pub['publisher'] + ". "
                if pub['url'] != None:                
                    Msg = Msg + " " + pub['url'] + "\n"
            else: #multiple pubs for same author
                Msg = Msg + name + " has new publications: \n"
                for pub in publicationNameKVP[name]:
                    Msg = Msg + "  * " + pub["title"] + ". "
                    if pub['publisher'] != None:
                        Msg = Msg + " Published in " + pub['publisher'] + ". "  
                    if pub['url'] != None:                
                        Msg = Msg + " " + pub['url'] + "\n"
                    else:
                        Msg = Msg + "URL unavailable."
                    Msg = Msg + "\n"


            Msg = Msg + "\n"
        
        return Msg


if __name__ == "__main__":
    if os.path.exists(jsonFile):
        shutil.copy2(jsonFile, lastJsonFile)
    lastPublicationJson = loadJson(lastJsonFile)
    with open(authorsToMonitor, 'r') as f:
        authorIDList = [line.strip() for line in f]

    # Setup headless Firefox
    options = Options()
    options.add_argument('--headless')
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

    #As a temp fix, lets add a check to ensure that the new publications in deltaJson is actually new. 
    
    saveJson(newPublications, deltaJsonFile)

    #Lets format the message for the slack bot
    Msg = formatSlackMsg2(loadJson(deltaJsonFile))

    #write it to an md file to upload via slack bolt
    with open ("msg.md", 'w') as f:
        f.writelines(Msg)
    

    