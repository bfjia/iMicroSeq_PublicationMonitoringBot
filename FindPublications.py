import json
import os
import shutil
from scholarly import scholarly

# ---- Configuration ----
authorID = 'PLiQF5oAAAAJ'  # e.g., '8W8gwisAAAAJ'
jsonFile = 'allpubs.json'
lastJsonFile = 'last_allpubs.json'
authorsToMonitor = "authorsToMonitor.txt"
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

#given an google scholar ID, find all publications by that user.
def fetchPublications(authorID, previousJsonData):
    # Retrieve author by Google Scholar ID
    author = scholarly.fill(scholarly.search_author_id(authorID))
    authorName = author['name']
    print("Looking for publications by " + authorName + " with google scholar ID " + authorID)
    publicationList = {}
    for pub in author['publications']:
        pubID = pub['author_pub_id'].split(":")[1]
        #check to see if this is a new author or if the paper is new. if not, then dont bother querying and use existing data to save time.
        if authorID not in previousJsonData.keys() or pubID not in previousJsonData[authorID]['publications'].keys():
            print("Found new publication with ID " + pubID)
            pub_filled = scholarly.fill(pub)
            bib = pub_filled.get('bib', {})
            authorList = bib.get('author').split(" and ")
            publication = publications(bib.get('title'), bib.get('pub_year'), bib.get('publisher'), authorList, pub_filled.get('pub_url'), True if authorList[0] == authorName or authorList[-1] == authorName else False,  pubID)
            publicationList[pubID] = publication.toDict()
        else:
            print("Found known publication with ID " + pubID)
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

    print("Indexing publications...")
    allPubs = {}
    for authorID in authorIDList:
        allPubs[authorID] = fetchPublications(authorID, lastPublicationJson)

    saveJson(allPubs, jsonFile)

    currentPublicationJson = loadJson(jsonFile)

    #look for differences
    print("Looking for anything new...")
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
                print(currentPublicationJson[id]['Name'] + " have no new publications.")
        else:
            print (currentPublicationJson[id]['Name'] + " is a new author added to the surveillance list, we ignoring until next time.")
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