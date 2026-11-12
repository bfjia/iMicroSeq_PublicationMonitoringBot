#Shared helper for talking to the OpenAlex API (https://api.openalex.org).
#Used by FindPublications.py, AddResearcher.py and legacy/MigrateScholarToOpenAlex.py.
#Only needs the python standard library.
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

# ---- Configuration ----
# Settings live in config.py (see the comments there).
from config import openAlexBaseURL, userAgent, maxRetries, requestTimeout, maxRetryAfterSeconds
# Free key from https://openalex.org/settings/api-key. Works without one, but the keyless budget is
# tiny ($0.10/day) and shared with everyone on the same IP - on GitHub Actions that's other people.
openAlexApiKey = os.environ.get("OPENALEX_API_KEY", "").strip()


def shortID(openAlexID):
    """'https://openalex.org/A5042633786' -> 'A5042633786'. Leaves short ids and None alone."""
    if not openAlexID:
        return ""
    return openAlexID.rstrip("/").rsplit("/", 1)[-1]


def shortORCID(orcid):
    """'https://orcid.org/0000-0002-8266-6513' -> '0000-0002-8266-6513'."""
    if not orcid:
        return ""
    return orcid.rstrip("/").rsplit("/", 1)[-1]


def openAlexGet(path, params=None):
    """GET an OpenAlex endpoint and return the parsed JSON, or None on 404.

    Retries with exponential backoff on 429/5xx/network errors, honouring Retry-After.
    The API key is sent as a header so it never appears in a logged URL."""
    query = urllib.parse.urlencode(params or {}, safe=":,|/")
    url = openAlexBaseURL + path + ("?" + query if query else "")
    headers = {"User-Agent": userAgent, "Accept": "application/json"}
    if openAlexApiKey:
        headers["Authorization"] = "Bearer " + openAlexApiKey

    lastError = ""
    for attempt in range(1, maxRetries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=requestTimeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            lastError = "HTTP " + str(e.code) + " " + body
            if e.code == 403 and "key_not_activated" in body:
                raise RuntimeError("[ERROR] OpenAlex API key is not activated yet - click the link in the activation email.")
            if e.code == 429:
                retryAfter = e.headers.get("Retry-After")
                wait = float(retryAfter) if retryAfter and retryAfter.replace(".", "", 1).isdigit() else 5 * attempt
                if wait > maxRetryAfterSeconds:
                    raise RuntimeError("[ERROR] OpenAlex daily budget exhausted (asked to wait " + str(int(wait)) + "s). "
                                       + ("" if openAlexApiKey else "No OPENALEX_API_KEY is set - add one. ") + body)
            elif e.code in (500, 502, 503, 504):
                wait = min(5 * (2 ** (attempt - 1)), 120)
            else:
                raise RuntimeError("[ERROR] OpenAlex request failed for " + path + ": " + lastError)
        except Exception as e:  # timeouts, connection resets, bad JSON
            lastError = str(e)
            wait = min(5 * (2 ** (attempt - 1)), 120)

        if attempt < maxRetries:
            print("[WARNING] OpenAlex request to " + path + " failed (" + lastError[:120] + "), attempt "
                  + str(attempt) + "/" + str(maxRetries) + ". Retrying in " + str(int(wait)) + "s...")
            time.sleep(wait + random.uniform(0, 1))

    raise RuntimeError("[ERROR] OpenAlex request to " + path + " failed after " + str(maxRetries) + " attempts: " + lastError)


def listWorks(filterString, select=None, sort=None, maxPages=20, perPage=100):
    """Return every work matching an OpenAlex filter string, following basic page paging."""
    works = []
    for page in range(1, maxPages + 1):
        params = {"filter": filterString, "per-page": perPage, "page": page}
        if select:
            params["select"] = select
        if sort:
            params["sort"] = sort
        data = openAlexGet("/works", params)
        if data is None:
            break
        results = data.get("results", [])
        works.extend(results)
        total = data.get("meta", {}).get("count", 0)
        if len(results) < perPage or len(works) >= total:
            break
    else:
        print("[WARNING] Stopped paging after " + str(maxPages) + " pages for filter " + filterString)
    return works
