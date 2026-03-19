import json
import os
import requests
import time
import re
from bs4 import BeautifulSoup as bs
from groq import Groq
from supabase import create_client

TMDB_API_KEY = "0cc553ab80b66eb0e1be73756f6ec11d"
GROQ_API_KEY = "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"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = "https://etydbhaqznqfobltkopd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV0eWRiaGFxem5xZm9ibHRrb3BkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM1ODgyNjUsImV4cCI6MjA4OTE2NDI2NX0.T0T4OBcN7tShEvaNj5Tf294W1QTHA_FTxwvbQWqRULw"


client = Groq(api_key=GROQ_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

session = requests.Session()

headers = {'User-Agent': 'Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'}

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"


def get_with_retry(url, params=None, retries=5):

    for i in range(retries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=15)
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

    return get_with_retry(url)


system_prompt = """
You extract concrete content warnings from IMDb parental guide text.

RULES:
- Extract concrete physical actions. Include SEXUAL ACTS, KISSING, NUDITY, BREAST NUDITY, PUBIC HAIR, EXPLICIT TOUCH, BLOOD, INJURIES. 
- Do NOT include themes, character names, emotions, or story topics.
- Keywords must be 1-3 words.
- Use ALL CAPS.
- Be specific (examples: KISSING, BREAST NUDITY, BLOODLESS EXPLOSION, WINE DRINKING, F-BOMBS).
- Return ONLY valid JSON.

FORMAT:
{"keywords":[]}
"""


def extract_keywords(text):

    if not text.strip():
        return {"keywords": []}

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ]
    )

    output = response.choices[0].message.content

    try:
        return json.loads(output)

    except:
        match = re.search(r"\{.*\}", output, re.DOTALL)

        if match:
            return json.loads(match.group())

    return {"keywords": []}


def scrape_parental_guide(html):

    soup = bs(html, "html.parser")

    text_blocks = soup.find_all("div", class_="ipc-html-content-inner-div")

    collected = [b.get_text(strip=True) for b in text_blocks]

    full_text = "\n".join(collected)

    return full_text


def split_categories(text):

    visual = []
    substance = []
    words = []

    for line in text.split("\n"):

        l = line.lower()

        if any(x in l for x in [
            "sex", "nudity", "violence", "blood", "fight", "kill", "frightening"
        ]):
            visual.append(line)

        elif any(x in l for x in [
            "drink", "alcohol", "smoke", "cigarette", "drug"
        ]):
            substance.append(line)

        elif any(x in l for x in [
            "fuck", "shit", "bitch", "asshole"
        ]):
            words.append(line)

    return "\n".join(visual), "\n".join(substance), "\n".join(words)


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

    visual_text, substance_text, words_text = split_categories(scraped_text)

    print("visual:", len(visual_text))
    print("substance:", len(substance_text))
    print("words:", len(words_text))

    visual = extract_keywords(visual_text)
    substance = extract_keywords(substance_text)
    words = extract_keywords(words_text)

    result = {
        "categories": {
            "Visual": visual["keywords"],
            "Substance": substance["keywords"],
            "Words": words["keywords"]
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
