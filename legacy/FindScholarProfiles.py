from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException
import urllib.parse
import time
import os
import re
import difflib

#clean up the html name in cause of bad characters
def sanitizeFilename(name):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

#start firefox
def initFireFox():
    options = Options()
    #options.add_argument("--headless")  # Run without GUI
    driver = webdriver.Firefox(options=options)
    return driver

def fetchScholarProfile(driver, name):
    query = urllib.parse.quote(name)
    searchURL = f"https://scholar.google.ca/scholar?q={query}"

    try:
        driver.get(searchURL)
        time.sleep(3)  # Allow page to load

        # Save search page
        # with open(f"search_{sanitizeFilename(name)}.html", "w", encoding="utf-8") as f:
        #     f.write(driver.page_source)

        # Extract first profile link
        links = driver.find_elements(By.XPATH, "//a[contains(@href, 'citations?user=')]")
        for link in links:
            href = link.get_attribute("href")
            if "user=" in href:
                # Extract user ID
                match = re.search(r"user=([a-zA-Z0-9_-]+)", href)
                if match:
                    userID = match.group(1)
                    profileURL = f"https://scholar.google.com/citations?hl=en&user={userID}"
                    return userID, profileURL
        print(f"[SKIP] No profile link found for {name}")
        return None, None

    except WebDriverException as e:
        print(f"[ERROR] Problem loading {searchURL}: {e}")
        return None, None

#calculate the different between the input name and found profile name. returns a distance score out of 1.
def verifyNameInFoundScholarProfile(driver, profileURL, name, threshold=0.8):
    try:
        driver.get(profileURL)
        time.sleep(2)

        # html = driver.page_source
        # with open(f"profile_{sanitizeFilename(name)}.html", "w", encoding="utf-8") as f:
        #     f.write(html)

        try:
            scholarNameElement = driver.find_element(By.ID, "gsc_prf_in")
            scholarName = scholarNameElement.text.strip()
        except NoSuchElementException:
            print(f"[ERROR] Scholar name not found on page: {profileURL}")
            return False, 0.0

        nameCleaned = name.split(",")[0].lower()
        scholarnameCleaned = scholarName.lower()
        similarity = difflib.SequenceMatcher(None, nameCleaned, scholarnameCleaned).ratio()

        name = name.split(",")[0]
        print(f"[DEBUG] Comparing input '{name}' to profile name '{scholarName}' (score: {similarity:.2f})")

        return similarity >= threshold, similarity

    except WebDriverException as e:
        print(f"[ERROR] Could not load profile {profileURL}: {e}")
        return False, 0.0

def main():
    inputFile = "names.txt"
    output_file = "results.tsv"

    if not os.path.exists(inputFile):
        print(f"[ERROR] File not found: {inputFile}")
        return

    with open(inputFile, "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("Status\tName\tUserID\tProfileURL\tScore\n")

    driver = initFireFox()

    try:
        for name in names:
            print(f"[INFO] Searching for: {name}")
            userID, profileURL = fetchScholarProfile(driver, name)
            with open(output_file, "a", encoding="utf-8") as out:
                if userID and profileURL:
                    matched, score = verifyNameInFoundScholarProfile(driver, profileURL, name)
                    if matched:
                        line = f"OK\t{name}\t{userID}\t{profileURL}\t{score:.2f}"
                        print(f"[OK] {userID}\t{profileURL} (score: {score:.2f})")
                    else:
                        line = f"LOW_CONFIDENCE\t{name}\t{userID}\t{profileURL}\t{score:.2f}"
                        print(f"[LOW_CONFIDENCE] Name not matched in profile: {profileURL} (score: {score:.2f})")
                else:
                    line = f"NO_MATCH\t{name}\t\t\t0.00"
                    print(f"[NO_MATCH] No profile link found for {name}")
                out.write(line + "\n")

            time.sleep(5 + 3 * (os.urandom(1)[0] % 3))  # polite delay
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
