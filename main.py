import json
import os
import requests
import time
import re
from bs4 import BeautifulSoup as bs
from groq import Groq
from supabase import create_client

TMDB_API_KEY = "0cc553ab80b66eb0e1be73756f6ec11d"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = "https://etydbhaqznqfobltkopd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0eWRiaGFxem5xZm9ibHRrb3BkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM1ODgyNjUsImV4cCI6MjA4OTE2NDI2NX0.T0T4OBcN7tShEvaNj5Tf294W1QTHA_FTxwvbQWqRULw"

client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

session = requests.Session()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.google.com/',
    'DNT': '1',
}

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"


# ---------------- FETCH ---------------- #

def get_with_retry(url, params=None, retries=5):
    for i in range(retries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=70)
            r.raise_for_status()

            if "api.themoviedb.org" in url:
                return r.json()

            return r.text

        except Exception as e:
            print("retry:", i + 1, e)
            time.sleep(2)


def get_imdb_id(movie_name):
    search = get_with_retry(
        SEARCH_URL,
        {"api_key": TMDB_API_KEY, "query": movie_name}
    )

    if not search["results"]:
        raise Exception("Movie not found")

    movie_id = search["results"][0]["id"]

    details = get_with_retry(
        f"https://api.themoviedb.org/3/movie/{movie_id}",
        {"api_key": TMDB_API_KEY}
    )

    return details["imdb_id"]


def get_imdb_page(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/parentalguide/"
    scraper_url = f"http://api.scraperapi.com?api_key={os.getenv('SCRAPERAPI_KEY')}&render=true&url={url}"
    result = get_with_retry(scraper_url)
    print("SCRAPERAPI RESPONSE CHARS:", len(result) if result else 0)
    print("SCRAPERAPI PREVIEW:", result[:500] if result else "NONE")
    return result


# ---------------- PROMPT ---------------- #

system_prompt = """
You read IMDb parental guide text and convert it into SMART content tags.

GOAL:
Understand the meaning, not just words.

RULES:
- ALWAYS include sexual content if present (SEX, KISSING, NUDITY, BREASTS, BUTTOCKS).
-  strong violence (SHOOTING, STABBING, EXPLOSION, DEATH).
- Extract substance use (DRUG USE, COCAINE, SMOKING, ALCOHOL).
- Extract strong language (FUCK, SHIT, etc).

- Ignore irrelevant things (cars, furniture, generic actions).
- Merge similar items (KILLED, KILLING → KILLING).
- Tags must be 1–3 words, ALL CAPS.

LIMIT:
- Max 20 total tags across all categories.

OUTPUT:
{
  "Visual": [],
  "Substance": [],
  "Words": []
}
"""


# ---------------- AI ---------------- #

def extract_keywords(text):
    if not text.strip():
        return {"Visual": [], "Substance": [], "Words": []}

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.3,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text[:12000]}
        ]
    )

    output = response.choices[0].message.content

    try:
        return json.loads(output)
    except:
        pass

    try:
        match = re.search(r"\{[\s\S]*\}", output)
        if match:
            return json.loads(match.group())
    except:
        pass

    return {"Visual": [], "Substance": [], "Words": []}

# ---------------- SCRAPE ---------------- #

def scrape_parental_guide(html):
    if not html:
        return ""
    soup = bs(html, "html.parser")
    text_blocks = soup.find_all("div", class_="ipc-html-content-inner-div")
    collected = [b.get_text(strip=True) for b in text_blocks]
    return "\n".join(collected)


# ---------------- MAIN ---------------- #

def analyze_movie(movie_name):
    imdb_id = get_imdb_id(movie_name)

    cached = supabase.table("movies").select("*").eq("imdb_id", imdb_id).execute()

    if cached.data:
        print("Found in cache")
        return cached.data[0]["result_json"]

    print("Processing:", imdb_id)

    html = get_imdb_page(imdb_id)
    scraped_text = scrape_parental_guide(html)

    print("scraped chars:", len(scraped_text))

    result_ai = extract_keywords(scraped_text)

    result = {
        "categories": {
            "Visual": result_ai.get("Visual", []),
            "Substance": result_ai.get("Substance", []),
            "Words": result_ai.get("Words", [])
        }
    }

    supabase.table("movies").insert({
        "imdb_id": imdb_id,
        "result_json": result
    }).execute()

    print("Saved to DB")

    return result


if __name__ == "__main__":
    movie = input("Enter movie name: ")
    print(analyze_movie(movie))
