import os
import json
import urllib
import random
import aiohttp
import asyncio
import pyoppai
import pyttanko
import requests
import datetime
import aiofiles
from bs4 import BeautifulSoup

import matplotlib as mpl
mpl.use('Agg') # for non gui
from matplotlib import ticker
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from utils.dataIO import dataIO, fileIO
from cogs.osu.osu_utils.chunks import chunks

from apiclient.discovery import build
from apiclient.errors import HttpError
from oauth2client.tools import argparser

api_keys = fileIO("config.json", "load")["API_KEYS"]

async def youtube_search(q, key, max_results=10, order="relevance"):
    youtube = build("youtube", "v3", developerKey=key)

    search_response = youtube.search().list(
        q=q, type="video",
        pageToken=None,
        order = order,
        part="id,snippet",
        maxResults=max_results,
    ).execute()

    videos = []
    for search_result in search_response.get("items", []):
        if search_result["id"]["kind"] == "youtube#video":
            videos.append(search_result)
    return videos

async def get_web(url, session=None, parser = 'html.parser'):
    if not session:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                text = await resp.read()
                try:
                    return BeautifulSoup(text.decode('utf-8'), parser)
                except:
                    return BeautifulSoup(text, parser)
    else:
        async with session.get(url) as resp:
            text = await resp.read()
            try:
                return BeautifulSoup(text.decode('utf-8'), parser)
            except:
                return BeautifulSoup(text, parser)


# asynchronously download the file
async def download_file(url, filename):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(filename, mode='wb')
                await f.write(await resp.read())
                await f.close()


async def get_REST(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def get_beatmap_listing(map_type=None):
    config_data = fileIO("config.json", "load")
    official = config_data["API_KEYS"]["OSU"]["OFFICIAL"]
    username = official["USERNAME"]
    password = official["PASSWORD"]

    payload = {"username": username,
               "password": password,
               "redirect": "index.php",
               "sid": "",
               "login": "Login"}

    async with aiohttp.ClientSession() as session:
        async with session.post('https://osu.ppy.sh/forum/ucp.php?mode=login', data = payload) as resp:
            text = await resp.read()

        query = "https://osu.ppy.sh/beatmapsets"
        if map_type and map_type!="None":
            query += f"?s={map_type}"

        async with session.get(query) as resp:
            text = await resp.read()
            soup = BeautifulSoup(text.decode('utf-8'), "lxml")
            script = soup.find("script", {"id": "json-beatmaps"}, type='application/json')
            web_data = json.loads(script.text)
            return web_data

async def get_top_cc(pages = 1):
    """Get country codes for top 50"""
    target_base = 'https://osu.ppy.sh/rankings/osu/performance?country='

    for i in range(pages):
        url = 'https://osu.ppy.sh/rankings/osu/country?page={}#jump-target'.format(i)
        soup = await get_web(url)
        a_tags = list(soup.findAll('a'))

        cc = []
        for tag in a_tags:
            try:
                if target_base in tag['href']:
                    # username tag.text.replace('\n','')
                    cc.append(tag['href'].replace(target_base, '').upper())
            except:
                pass
    return cc

async def get_map_image(mapset_id):
    # also maintains length to 1500
    folder = f"cogs/osu/resources/beatmap_images"
    filename = f"{mapset_id}.jpg"
    file_path = f"{folder}/{filename}"

    # if it exists
    if os.path.exists(file_path):
        try:
            bg = Image.open(file_path)
            return bg, True
        except:
            pass

    # if it doesn't exist
    config_data = fileIO("config.json", "load")
    official = config_data["API_KEYS"]["OSU"]["OFFICIAL"]
    username = official["USERNAME"]
    password = official["PASSWORD"]

    payload = {"username": username,
               "password": password,
               "redirect": "index.php",
               "sid": "",
               "login": "Login"}

    async with aiohttp.ClientSession() as session:
        async with session.post('https://osu.ppy.sh/forum/ucp.php?mode=login', data = payload) as resp:
            text = await resp.read()
            try:
                print("Attempting Download")
                bg, bg_success = await download_map_image_to_folder(mapset_id, session = session)
                # bg = Image.open("cogs/osu/resources/triangles_map.jpg")
                return bg, bg_success
                # return bg
            except:
                bg = Image.open("../owo_v2/cogs/osu/resources/triangles_map.jpg")
                return bg, False

async def download_map_image_to_folder(mapset_id, session=None, limit=8000):
    # get map url from site
    folder = f"cogs/osu/resources/beatmap_images"
    file_path = f"{folder}/{mapset_id}.jpg"

    bg = None
    bg_success = False
    bg_images = []

    bg_images.append("https://assets.ppy.sh/beatmaps/{}/covers/card@2x.jpg?".format(mapset_id))
    # bg_images.append("https://assets.ppy.sh/beatmaps/{}/covers/cover.jpg".format(mapset_id))

    for bg_image in bg_images:
        async with session.get(bg_image) as r:
            image = await r.content.read()
        with open(file_path,'wb') as f:
            f.write(image)
        bg = Image.open(file_path)
        bg_success = True
        break
        await asyncio.sleep(1)

    # if too many
    path, dirs, files = next(os.walk(folder))
    file_count = len(files)
    if file_count > limit:
        delete_num = file_count - limit
        for i in range(delete_num):
            file = random.choice(files)
            delete_file = f"{folder}/{file}"
            if delete_file != file_path:
                os.remove(delete_file)
    return bg, bg_success