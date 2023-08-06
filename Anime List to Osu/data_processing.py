from ossapi import Ossapi
import re
from mal import Anime, AnimeSearch
import bs4
import requests
from os import getenv
from dotenv import load_dotenv
import sqlite3
from utils import (
    get_first_non_empty,
    remove_blank_entries,
    decode_unicode,
    convert_to_string,
)

load_dotenv()

ERROR_IMG_URL = getenv("ERROR_IMG_URL")


def mal(user):
    # Find anime titles from MAL by user name sorted from highest to lowest score
    link = f"https://myanimelist.net/animelist/{user}?status=2&order=4&order2=0"
    url = requests.get(link)
    url.raise_for_status
    soup = bs4.BeautifulSoup(url.text, "html.parser")
    html_list = soup.find("table", attrs={"class": "list-table"})
    source = str(html_list)
    start_sep = "&quot;,&quot;anime_title_eng&quot;:&quot;"
    end_sep = "&quot;,&quot;anime_num_episodes&quot"
    tmp = source.split(start_sep)
    results = [par.split(end_sep)[0] for par in tmp if end_sep in par]
    return results


def get_google_results(search_term):
    # Returns the first google search results for the search term
    res = requests.get(f"https://www.google.com/search?q={search_term}")
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, "html.parser")
    linkElements = soup.select(".kCrYT > a")
    # print(linkElements)
    linkToOpen = min(2, len(linkElements))
    to_return = [
        "https://www.google.com" + linkElements[i].get("href")
        for i in range(linkToOpen)
    ]
    try:
        return to_return[0]
    except IndexError:
        return None


def extract_anime_id(url):
    # Extracts the anime ID from a google link
    match = re.search(r"/(\d+)/", url)
    if match:
        return match.group(1)
    return None


def get_anime_type(anime):
    # Getting ID from google search results instead of using the API is faster
    # and has to make half as many calls, but there is a potential for error
    try:
        MAL_id = extract_anime_id(get_google_results(f"{anime} MyAnimeList"))
    except ValueError:
        MAL_id = AnimeSearch(anime).results[0].mal_id

    anime_info = Anime(MAL_id)
    img = anime_info.image_url
    anime_type = anime_info.type
    return img, anime_type


def scrape_osu(link):
    # Returns the artist and title of the song from the osu beatmap link
    result = requests.get(link)
    soup = bs4.BeautifulSoup(result.text, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        artist_and_title = title_tag.text.strip()
        return artist_and_title.split("·")[0]
    else:
        return "Title Not Found"


def convertor(user, s, e):
    # Takes a MAL username and returns a list of lists containing anime name,
    # song name, image url, and osu! beatmap using all the previous functions
    conn = sqlite3.connect("database/anime_list.sqlite")
    c = conn.cursor()
    not_in_db = 0
    anime_list = decode_unicode(remove_blank_entries(mal(user)[s:e]))
    list_info = []
    for anime in anime_list:
        c.execute("SELECT 1 FROM anime WHERE anime_name = ? LIMIT 1", (anime,))
        result = c.fetchone()
        # print(anime)
        if not result:
            img, anime_type = get_anime_type(anime)
            song = [None]
            if anime_type == "TV":
                google_search_term = f"{anime} Osu Beatmap Anime"
                link = get_google_results(google_search_term)
                if not link.startwith("https://www.google.com/url?q=https://osu.ppy.sh/beatmapsets/") or "discussion" in link:
                    link = None
                if link is not None:
                    song = scrape_osu(link)
                else:
                    song = "No song found"
                    link = "Does not exist"

            if anime_type != "TV":
                link = [f"Some {anime_type}'s are not supported yet"]

            if song[0] is None or song[0] == "None":
                link = "Does not exist"
                song = "No song found"
            anime = convert_to_string(anime)
            list_info.append([anime, song, img, link])
            not_in_db += 1
        else:
            select_query = """
            SELECT * FROM anime
            WHERE anime_name = ?;
        """
            try:
                # Execute the select query
                c.execute(select_query, (anime,))
                row = c.fetchone()

                if row:
                    # If a row is found, you can access the columns like this
                    db_anime_name, db_anime_song, db_anime_img, db_osu_link = row
                    db_anime_name = convert_to_string(db_anime_name)
                    list_info.append(
                        [db_anime_name, db_anime_song, db_anime_img, db_osu_link]
                    )
                else:
                    anime = convert_to_string(anime)
                    list_info.append(
                        [anime, "No song", ERROR_IMG_URL, "Does not exist"]
                    )
            except Exception as e:
                list_info.append([anime, "No song", ERROR_IMG_URL, "Does not exist"])
        if not_in_db == 10:
            break

    conn.close()
    return list_info
