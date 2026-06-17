import json
import os
import shutil
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
import time
import re
import random
from dateutil import parser
import difflib

# ---- Configuration ----
# Run Firefox without a visible window. True for the unattended cron run (a captcha then has no one
# to solve it, so isBlockedByCaptcha raises). Set False to debug with a visible browser and solve
# captchas by hand.
isHeadless = False
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


def politeSleep(lo=2.0, hi=5.0):
    """Sleep a randomized human-like interval to avoid hammering Google Scholar (throttle/captcha)."""
    time.sleep(random.uniform(lo, hi))


def isBlockedByCaptcha(driver):
    """Detect Google Scholar's throttle/captcha interstitial.

    Headless (isHeadless=True): no human can solve it, so raise and let publii.sh's ERR trap alert.
    Non-headless: warn and wait for the operator to solve it in the Firefox window, then continue."""
    try:
        currentUrl = driver.current_url.lower()
    except Exception:
        currentUrl = ""

    captchaDetected = "/sorry/" in currentUrl or "captcha" in currentUrl
    if not captchaDetected:
        try:
            captchaDetected = bool(
                driver.find_elements(By.ID, "gs_captcha_ccl")
                or driver.find_elements(By.ID, "gs_captcha_f")
                or driver.find_elements(By.CSS_SELECTOR, "form#captcha-form")
                or driver.find_elements(By.CSS_SELECTOR, "#g-recaptcha"))
        except Exception:
            captchaDetected = False

    if captchaDetected:
        if isHeadless:
            raise RuntimeError("[ERROR] Google Scholar captcha detected while running headless; cannot solve it automatically.")
        print("[WARNING] Google Scholar captcha detected. Running non-headless: solve it in the Firefox window, then press Enter here to continue...")
        try:
            input()
        except EOFError:
            pass

    return captchaDetected


def readPublicationRows(driver):
    """Read (pubID, title, detailURL, listingYear) for every row on a profile listing page.
    The year is taken from the listing itself (td.gsc_a_y), so we can filter by year WITHOUT
    opening a per-publication detail page and WITHOUT trusting Scholar's sort order."""
    rows = []
    for pub in driver.find_elements(By.CSS_SELECTOR, 'tr.gsc_a_tr'):
        try:
            titleElem = pub.find_element(By.CLASS_NAME, 'gsc_a_at')
            title = titleElem.text

            href = titleElem.get_attribute("href")
            detailURL = "https://scholar.google.com" + href if href.startswith("/citations?") else href

            match = re.search(r'citation_for_view=[^:]+:([^&]+)', detailURL)
            if not match:
                continue
            pubID = match.group(1)

            listingYear = None
            yearMatch = re.search(r'\d{4}', pub.find_element(By.CSS_SELECTOR, 'td.gsc_a_y').text)
            if yearMatch:
                listingYear = int(yearMatch.group(0))

            rows.append((pubID, title, detailURL, listingYear))
        except Exception as e:
            print("[WARNING] Could not parse a publication row: " + str(e))
    return rows


def isSortedNewestFirst(rows):
    """True if the listing years (ignoring blanks) are non-increasing, i.e. Scholar's
    sortby=pubdate actually took effect. Used to detect a silently-failed sort."""
    years = [year for _, _, _, year in rows if year is not None]
    return all(years[i] >= years[i + 1] for i in range(len(years) - 1))


#extract publication metadata from google scholar's summary page
def extractMetadataFromScholarSummary(driver, publicationURL, profileName, title, pubID, maxRetries=3):
    #open a new window and go to the publication url
    driver.execute_script("window.open('');")
    driver.switch_to.window(driver.window_handles[1])

    # Load the detail page, reloading if it didn't render. The metadata table (gsc_oci_field) is
    # our "page actually loaded" signal: a missing title link alone is fine (citation-only entries
    # genuinely have no external URL), but a missing table means a slow/partial load -> reload.
    meta_rows = []
    for attempt in range(1, maxRetries + 1):
        driver.get(publicationURL)
        politeSleep()

        isBlockedByCaptcha(driver)  # raises if headless+captcha; pauses for manual solve if not

        meta_rows = driver.find_elements(By.CLASS_NAME, 'gsc_oci_field')
        if meta_rows:
            break
        print(f"[WARNING] Detail page for {pubID} did not render (attempt {attempt}/{maxRetries}); reloading...")
        time.sleep(min(3 * attempt, 30))

    if not meta_rows:
        print(f"[ERROR] Detail page for {pubID} never rendered after {maxRetries} reloads; metadata may be incomplete.")

    # find_elements returns [] instead of raising when the title link is absent (citation-only pubs).
    linkElements = driver.find_elements(By.CLASS_NAME, 'gsc_oci_title_link')
    actualPubURL = linkElements[0].get_attribute("href") if linkElements else None

    # Extract metadata rows (zip so a field/value count mismatch can't IndexError)
    meta_values = driver.find_elements(By.CLASS_NAME, 'gsc_oci_value')
    metadata = dict()
    for field, value in zip(meta_rows, meta_values):
        metadata[field.text.lower().strip()] = value.text.strip()

    #switch back to the main window
    driver.close()
    driver.switch_to.window(driver.window_handles[0])

    #format the metadata.
    pubDate = metadata['publication date'] if 'publication date' in metadata else "Unknown"
    # Keep the WHOLE venue string. The old code used metadata['publisher'][0], which indexes the
    # first CHARACTER of the string (hence "Published in C."). Fall through the possible venue labels.
    journal = (metadata.get('journal') or metadata.get('conference') or metadata.get('source')
               or metadata.get('book') or metadata.get('publisher') or "Unknown")
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

    knownPubs = previousJsonData[scholarID]['publications'] if scholarID in previousJsonData else {}
    profileName = "Unknown"
    rows = []

    for attempt in range(1, maxRetries + 1):
        try:
            driver.set_page_load_timeout(20)  # Set timeout in seconds
            driver.get(url)
            isBlockedByCaptcha(driver)  # raises if headless+captcha; pauses for manual solve if not
            politeSleep(4, 7)  # let the page settle

            try:
                profileName = driver.find_element(By.ID, "gsc_prf_in").text.strip()
            except Exception:
                profileName = "Unknown"

            rows = readPublicationRows(driver)

            # If the listing isn't newest-first, Scholar's sort silently failed. Per-row year
            # filtering below still works, but a failed sort can hide a recent pub when an author
            # has >100 entries, so retry the load a few times before accepting the order.
            if isSortedNewestFirst(rows) or attempt >= 5:
                break
            print(f"[WARNING] Publication list for {scholarID} does not look date-sorted (attempt {attempt}). Retrying...")
            time.sleep(min(5 * attempt, 60))
        except Exception as e:
            print(f"Attempt {attempt} failed with error: {e}")
            if attempt < maxRetries:
                backoff = min(5 * (2 ** (attempt - 1)), 300)  # exponential backoff, capped at 5 min
                print(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
            else:
                raise RuntimeError(f"[ERROR] Could not load profile {scholarID} after {maxRetries} attempts (captcha or load failure).")

    print("[INFO] " + "Looking for publications by " + profileName + " with google scholar ID " + scholarID)

    publicationList = {}
    for pubID, title, publicationURL, listingYear in rows:
        # Robust to sort failures: skip anything older than maxYear by listing year alone.
        # Unknown/blank year -> keep, so genuinely-new pubs with missing dates aren't dropped.
        if listingYear is not None and listingYear < maxYear:
            continue

        # Use cached metadata for already-known pubs to avoid an unnecessary detail-page request.
        if pubID in knownPubs:
            print("[DEBUG] " + "Found known publication with ID " + pubID)
            publicationList[pubID] = knownPubs[pubID]
            continue

        # New, in-range pub -> open its detail page for full metadata.
        publication = extractMetadataFromScholarSummary(driver, publicationURL, profileName, title, pubID)
        if publication is None:
            print("[ERROR] Absolutely Nothing found.")
            continue

        # Determine the year. Prefer the detail-page date; fall back to the listing-page year.
        # If neither yields a year, this is undated cruft (posters, conference abstracts, merged
        # "cluster" citations, old PDFs that Scholar lists without a date) - skip it rather than
        # assuming it's current. The old code forced an Unknown date to "2025", which is exactly
        # why pre-2020 items leaked through and surfaced as new publications.
        try:
            pubYear = parser.parse(publication.toDict()['year']).year
        except Exception:
            pubYear = listingYear

        if pubYear is None:
            print("[INFO] Skipping publication with ID " + pubID + " ('" + title + "') - no determinable publication date.")
            continue
        if pubYear < maxYear:
            continue

        # Detail page had no parseable date but the listing did: store the real listing year so the
        # rest of the pipeline (which parses 'year') works and the pub isn't mislabelled.
        if publication.toDict()['year'] == "Unknown":
            publication.year = str(pubYear)

        publicationList[pubID] = publication.toDict()
        print("[INFO] " + "Found new publication with ID " + pubID + " Titled: " + title)

    # Sometimes publications in previousJsonData don't show up in the new list - either old
    # manuscripts outside the top 100, or recent pubs Scholar de-indexed. Brute-force the known
    # ones back in, but only if they're within range so stale pre-maxYear entries get pruned.
    if scholarID not in previousJsonData:
        print("[INFO] New author added. Not comparing to previous publication list.")
    else:
        keysInPrevButNotCur = set(knownPubs.keys()) - set(publicationList.keys())
        if len(keysInPrevButNotCur) > 0:
            print("[WARNING] " + "There were existing publications that were not indexed in this round " + str(keysInPrevButNotCur))
            for key in keysInPrevButNotCur:
                pub = knownPubs[key]
                try:
                    if parser.parse(pub['year']).year < maxYear:
                        print("[INFO] Pruning stale pre-" + str(maxYear) + " publication " + key)
                        continue
                except Exception:
                    pass
                publicationList[key] = pub

    return {'Name' : profileName, 'total_publications' : str(len(publicationList)), 'publications':publicationList}

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

    # Setup Firefox (headless when isHeadless is set; see the config flag at the top).
    options = Options()
    if isHeadless:
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
        #this is not a new person, check if new pubs exists.
        if id in lastPublicationJson.keys():
            if currentPublicationJson[id]['publications'].keys() != lastPublicationJson[id]['publications'].keys():
                diff = [item for item in currentPublicationJson[id]['publications'].keys() if item not in lastPublicationJson[id]['publications'].keys()] #holds the pubid of NEW pubs
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
        else: #we just added someone new to the list. DO NOT delta them until the next time.
            print ("[INFO] " + currentPublicationJson[id]['Name'] + " is a new author added to the surveillance list, we ignoring until next time.")

    saveJson(newPublications, deltaJsonFile)

    #Lets format the message for the slack bot
    Msg = formatSlackMsg2(loadJson(deltaJsonFile))

    #write it to an md file to upload via slack bolt
    with open ("msg.md", 'w') as f:
        f.writelines(Msg)
