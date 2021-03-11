import os
import re
import ssl
import json
import time
import math
import numpy
import string
import urllib
import random
import discord
import aiohttp
import asyncio
import logging
import datetime
import operator
import websockets
import collections
import numpy as np
import motor.motor_asyncio
from bs4 import BeautifulSoup
from utils.dataIO import fileIO

from discord.ext import commands

from cogs.osu.osu import Osu
from cogs.osu.osu_utils.owoAPI import owoAPI
from cogs.osu.osu_utils import map_utils, utils, web_utils

from concurrent.futures import ProcessPoolExecutor

# global_client = MongoClient('mongodb://162.243.20.39/', 27017)

# ----------------------- Tracking Section -------------------------------
class Updater(commands.Cog):
    def __init__(self, bot):
        # super().__init__()
        # Osu cog for helper function covenience
        self.bot = bot
        self.osu = Osu(self.bot)

        # tasks to run for the updater
        self.run_tasks = [] #

        # for each tracking api
        # self.api_list = self.osu.owoAPI.get_api_list()
        self.api_list = ['bancho'] # ['ripple']

        # create conccurent tasks
        executor = ProcessPoolExecutor(len(self.api_list))
        self.loop = asyncio.get_event_loop()

        # add map feed
        self.loop.create_task(MapTracker(bot).map_feed())

        
        # add tracking loops
        """
        for api in self.api_list:
            server_api = self.osu.owoAPI.get_api(api)
            if server_api.websocket:
                tracker = TopPlayTrackerWebsocket(bot, server_api)
                self.loop.create_task(tracker.web_socket())
            else:
                tracker = TopPlayTrackerPoll(bot, server_api)
                self.loop.create_task(tracker.poll_tracker())
                """


class TopPlayTrackerPoll(Osu):
    def __init__(self, bot, api, max_requests=30):
        self.bot = bot
        self.max_requests = max_requests # per minute
        self.cycle_time = 0
        self.sleep_time = 0.01 # initial
        self.num_track = 100 # track all of them
        self.api = api

        self.MODES = ["osu", "taiko", "ctb", "mania"]

        # databases
        client = motor.motor_asyncio.AsyncIOMotorClient(
            port=self.bot.config['database']['primary'],
            connectTimeoutMS=5000, 
            socketTimeoutMS=5000, 
            serverSelectionTimeoutMS=5000)
        
        self.server_settings = self.bot.db["osu"] # global osu server settings
        self.osu_db = client['owo_database']
        self.track = self.osu_db['track']
        self.track_settings = self.osu_db['track_settings']
        self.track_latency = self.osu_db['track_latency']
        self.online = self.osu_db['online']
        # self.new_plays = self.osu_db['new_plays']
        self.rec_osu = self.osu_db['suggest_osu']

    # ------- tracker ----------
    async def poll_tracker(self):
        await asyncio.sleep(10)
        # await self.check_integrity()

        while True:
            await asyncio.sleep(1)
            current_time = datetime.datetime.now()
            # determine if anyone new was added and then add to node database

            loop = asyncio.get_event_loop()
            relevant_players = await self._get_online_ids() #  list of osu ids that are relevant for the server alone!
            total_tracking = len(relevant_players) # counts total number of players
            self.sleep_time = self.max_requests/60 # in seconds hardcoded
            self.cycle_time = total_tracking/self.max_requests

            print("INFO Total players: {} | Cycle Estimate: {} min | Sleep Time: {}".format(
                len(relevant_players), str(self.cycle_time), str(self.sleep_time)))

            for osu_id in relevant_players:

                player = self.track.find_one({"osu_id":osu_id})
                if not player:
                    player = self.track.find_one({"username":osu_id})

                loop.create_task(self.check_plays(player)) # *** needs to be uncommented!

                print('Finished tracking', osu_id)
                await asyncio.sleep(self.sleep_time)

            if self.cycle_time * 60 < 60:
                await asyncio.sleep(60 - self.cycle_time*60)
            else:
                pass

            loop_time = datetime.datetime.now()
            elapsed_time = loop_time - current_time
            print("INFO Tracking Time Ended. Cycle Time: {}".format(str(elapsed_time)))


    async def _get_online_ids(self):
        online_list = await self.online.find_one({'type': 'userlist'})
        online_list = online_list['userlist']
        osu_id_list = []
        for username in online_list:
            try:
                db_user = await self.track.find_one({"username":username})
                if db_user:
                    osu_id_list.append(db_user["osu_id"])
            except:
                pass
        return osu_id_list


    async def check_plays(self, player, api='bancho'):
        if player and 'osu_id' in player:
            osu_id = player['osu_id']
        else:
            return

        # gets new data
        plays, required_modes = await self._fetch_new(osu_id, player["servers"]) # contains data for player

        # gets existing data
        data = await self.track.find_one({'osu_id':osu_id})

        current_time = datetime.datetime.now()
        for mode in required_modes:
            gamemode_number = utils.get_gamemode_number(mode)
            score_gamemode = utils.get_gamemode_display(mode)

            # try:
            best_plays = plays["best"][mode] # single mode

            # print(best_plays)
            best_timestamps = []
            for best_play in best_plays:
                best_timestamps.append(best_play['date'])
            # except:
                # continue

            for i in range(len(best_timestamps)): # max 100
                last_top = player["last_check"]
                last_top_datetime = datetime.datetime.strptime(last_top, '%Y-%m-%d %H:%M:%S')
                best_datetime = datetime.datetime.strptime(best_timestamps[i], '%Y-%m-%d %H:%M:%S')

                if best_datetime > last_top_datetime:
                    # print(best_datetime, last_top_datetime)
                    # calculate latency
                    besttime = datetime.datetime.strptime(best_timestamps[i], '%Y-%m-%d %H:%M:%S')
                    oldlastcheck = datetime.datetime.strptime(last_top, '%Y-%m-%d %H:%M:%S')
                    delta = besttime - oldlastcheck

                    top_play_num = i+1
                    play = best_plays[i]

                    play_map = await self.owoAPI.get_beatmap(play['beatmap_id'])
                    await asyncio.sleep(1)
                    new_user_info = await self.owoAPI.get_user(osu_id, 
                        mode=gamemode_number, api='bancho') # disable cache necessary? **
                    new_user_info = new_user_info[0]

                    # send appropriate message to channel
                    if mode in player["userinfo"]:
                        old_user_info = player["userinfo"][mode]
                    else:
                        old_user_info = None
                    player["userinfo"][mode] = new_user_info

                    timeago = utils.time_ago(
                        datetime.datetime.utcnow(),
                        datetime.datetime.strptime(play['date'], '%Y-%m-%d %H:%M:%S'))
                    # display if it hasn't been too long
                    new_play_obj = None
                    if not ("Hours" in timeago or "Day" in timeago or "Month" in timeago):
                        # check if there's actual servers
                        try:
                            all_servers = list(set(data['servers'].keys()))
                        except:
                            continue

                        # build new play object
                        play_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                        # map_rank = self.get_map_rank(old_user_info["osu_id"])
                        new_play_obj = {
                            "i": i,
                            "api": api,
                            "play_id": play_id,
                            # "map_rank_num": map_rank,
                            "top_play_num": top_play_num,
                            "play":play,
                            "play_map": play_map,
                            "old_user_info":old_user_info,
                            "new_user_info":new_user_info,
                            "score_gamemode":score_gamemode,
                            "gamemode_num":gamemode_number,
                            "mode": mode,
                            "servers": data['servers'],
                            "shard_ids_sent": [],
                            "timestamp": time.time()
                        }


                    if gamemode_number == 0:
                        await self._append_suggestion_database(play)

                    # print("Created top {} {} play for {}({}): {}".format(top_play_num, mode, new_user_info['username'], osu_id, str(delta)))
                    player['last_check'] = best_timestamps[i] # set the actual variable + update
                    await self.track.update_one({"osu_id":player['osu_id']}, {
                        '$set':{
                            "username":player["userinfo"][mode]['username'],
                            "userinfo":player['userinfo'],
                            "last_check":best_timestamps[i]
                        }})

                    # send out the info to the relevant servers
                    if new_play_obj:
                        await self.send_play(new_play_obj)

                    await asyncio.sleep(1)


    async def _fetch_new(self, osu_id, player_servers):
        new_data = {"best":{}, "recent":{}}

        required_modes = await self._get_required_modes(player_servers)

        for mode in required_modes:
            # new_data["best"][mode] = {}
            new_data["best"][mode] = await self.owoAPI.get_user_best(osu_id, mode=gamemode, use_cache=False)
            await asyncio.sleep(1)

        return new_data, required_modes


    async def _get_required_modes(self, player_servers):
        required_modes = []
        for server_id in player_servers.keys():
            server_player_info = player_servers[server_id]
            if 'options' in server_player_info:
                required_modes.extend(server_player_info['options']['gamemodes'])
            else: # if no option exists
                required_modes.extend([0])

        required_modes = list(set(required_modes))
        required_modes_list = []
        for mode_num in required_modes:
            required_modes_list.append(int(self.MODES[mode_num]))
        return required_modes_list


    async def check_integrity(self):
        print("CHECKING database integrity...")
        await self.remove_duplicates()
        # just several things i would like to check on the database.
        async for player in self.track.find({}, no_cursor_timeout=True):
            # make sure the username has an underscore f
            if "osu_id" not in player:
                for mode in modes:
                    try:
                        player["osu_id"] = player["userinfo"][mode]
                    except:
                        pass
                await self.track.update_one({"username":player["username"]},
                    {'$set':{"osu_id":player["osu_id"]}})
                print("Osu id added for {}".format(player["username"]))
        print("FINISHED checking integrity")


    async def remove_duplicates(self):
        print("CHECKING for duplicates...")
        async for player in self.track.find({}, no_cursor_timeout=True):
            player_find_count = await self.track.find({"osu_id":player['osu_id']}).count()
            if player_find_count == 2:
                await self.track.delete_one({"osu_id":player['osu_id']})
                print("DELETED One Instance of {}".format(player['username']))
            elif player_find_count > 2:
                await self.track.delete_many({"osu_id":player['osu_id']})
                print("DELETED All Instances of {}".format(player['username']))
        print("FINISHED checking for duplicates.")


    async def send_play(self, play):
        sent_servers = []
        em = await self.create_new_play_embed(play)

        all_servers = list(set(play['servers'].keys()))
        # print(play['new_user_info']["username"], all_servers, self.bot.shard_id)
        for server_id in all_servers:
            # print(play['new_user_info']["username"], sent_servers, self.bot.shard_id)
            server = await self.bot.fetch_guild(int(server_id))
            server_settings = await self.server_settings.find_one(
                {"server_id": str(server_id)})

            if self._display_criteria_met(play, server, server_settings):
                # print("New mode play detected...")
                i = int(play["i"])
                mode = play['mode']
                channel = await self.bot.fetch_channel(
                    int(play['servers'][server_id]["top"][mode]["channel_id"]))

                try: # blehhh
                    await channel.send(embed=em)
                    print("Sent play {} for {} to {}".format(i + 1,
                        play['new_user_info']["username"], server.id))
                except:
                    print("No perms to send play for {} to {}.".format(
                        play['new_user_info']["username"], server.id))

        # handle the per server tracks
        pass

    def _display_criteria_met(self, play, server, server_settings):
        criteria_met = False
        server_id = str(server.id)
        mode = play['mode']
        i = int(play["i"])
        if server and (not server_settings or "tracking" not in server_settings or server_settings["tracking"]):
            server_player_info = play['servers'][server_id]
            if "top" in play['servers'][server_id] and \
                mode in play['servers'][server_id]["top"] and \
                "channel_id" in play['servers'][server_id]["top"][mode]:
                if "plays" in play['servers'][server_id]["top"][mode] and \
                    i < int(play['servers'][server_id]["top"][mode]["plays"]):
                        criteria_met = True
        return criteria_met

    # gets user map rank if less than 1000
    async def get_map_rank(self, osu_userid, title):
        pass
        """
        try:
            ret = None
            url = 'https://osu.ppy.sh/users/{}'.format(osu_userid)
            # soup = await web_utils.get_web(url, parser = "lxml")
            soup = None
            find = soup.find('script',{"id": "json-user"})
            user = json.loads(find.get_text())

            for recent_play in user['recentActivity']:
                if title in recent_play['beatmap']['title']:
                    ret = int(recent_play['rank'])
                    break
            return ret
        except Exception as e:
            print(e)
            return None
            """


    async def _remove_bad_servers(self):
        if self.server_send_fail != [] and len(self.server_send_fail) <= 15: # arbitrary threshold in case discord api fails
            async for player in self.track.find({}, no_cursor_timeout=True).batch_size(self.batch_size):
                all_servers = player['servers'].keys()
                for failed_server_id in self.server_send_fail:
                    if failed_server_id in all_servers:
                        del player['servers'][failed_server_id]
                        await self.track.update_one({"username":player['username']}, {'$set':{"servers":player['servers']}})
                        find_test = await self.track.find_one({"username":player['username']})
                        if failed_server_id in find_test['servers'].keys():
                            print("FAILED to delete Server {} from {}".format(failed_server_id, player['username']))
                        else:
                            print("Deleted Server {} from {}".format(failed_server_id, player['username']))
            self.server_send_fail = []


    async def create_new_play_embed(self, play_info):
        top_play_num = play_info['top_play_num']
        play = play_info['play']
        beatmap = play_info['play_map']
        old_user_info = play_info['old_user_info']
        new_user_info = play_info['new_user_info']
        gamemode = play_info['score_gamemode']
        gamemode_num = play_info['gamemode_num']
        api = play_info['api']


        beatmap_url = self.owoAPI.get_beatmap_url(play)
        #print("TYPE AND USER ID: {} {}".format(self.osu_settings["type"]["default"], new_user_info['user_id'] ))
        user_url = 'https://{}/u/{}'.format(api.replace('/api',''), new_user_info['user_id'])
        profile_url = 'https://a.ppy.sh/{}'.format(new_user_info['user_id'])
        beatmap = beatmap[0]

        # get infomation
        m0, s0 = divmod(int(beatmap['total_length']), 60)
        mods = utils.num_to_mod(play['enabled_mods'])
        em = discord.Embed(description='', colour=0xffa500)
        acc = utils.calculate_acc(play, int(beatmap['mode']))

        # determine mods
        if not mods:
            mods = []
            mods.append('No Mod')
            bmp_output = None
        else:
            bmp_mods = "+{}".format("".join(mods))
            bmp_output = await map_utils.get_map_data(beatmap['beatmap_id'],
                accs=[int(acc)], mods = int(play['enabled_mods']))

        # grab beatmap image
        map_image_url = 'https://b.ppy.sh/thumb/{}l.jpg'.format(beatmap['beatmapset_id'])
        em.set_thumbnail(url=map_image_url)
        em.set_author(name="New #{} for {} in {}".format(
            top_play_num, new_user_info['username'], gamemode),
            icon_url = profile_url, url = user_url)

        info = ""
        map_title = "{} [{}]".format(beatmap['title'], beatmap['version'])
        map_rank = None
        map_rank = await self.get_map_rank(new_user_info['user_id'], map_title)
        # print(map_rank) # just for debugging
        map_rank_str = ''
        if map_rank:
            map_rank_str = '▸ #{}'.format(str(map_rank))

        info += "▸ [**__{}__**]({}) {}                            \n".format(map_title, beatmap_url, map_rank_str)
        # calculate bpm and time... MUST clean up.
        if bmp_output and ('DT' in str(mods).upper() or 'HT' in str(mods).upper()):
            if 'DT' in str(mods):
                m1,s1,bpm1 = utils.calc_time(beatmap['total_length'], beatmap['bpm'], 1.5)
            elif 'HT' in str(mods):
                m1,s1,bpm1 = utils.calc_time(beatmap['total_length'], beatmap['bpm'], 2/3)

            star_str, _ = utils.compare_val(beatmap['difficultyrating'], bmp_output, 'stars', dec_places = 2)
            info += "▸ **{}★** ▸ {}:{}({}:{}) ▸ {}({})bpm ▸ +{}\n".format(
                star_str,
                m0, str(s0).zfill(2),
                m1, str(s1).zfill(2),
                beatmap['bpm'], bpm1 , utils.fix_mods(''.join(mods)))

        elif 'DT' in str(mods).upper() or 'HT' in str(mods).upper():
            if 'DT' in str(mods):
                m1,s1,bpm1 = utils.calc_time(beatmap['total_length'], beatmap['bpm'], 1.5)
            elif 'HT' in str(mods):
                m1,s1,bpm1 = utils.calc_time(beatmap['total_length'], beatmap['bpm'], 2/3)

            star_str, _ = utils.compare_val(beatmap['difficultyrating'], bmp_output, 'stars', dec_places = 2)
            info += "▸ **{}★** ▸ {}:{}({}:{}) ▸ {}({})bpm ▸ +{}\n".format(
                star_str,
                m0, str(s0).zfill(2),
                m1, str(s1).zfill(2),
                beatmap['bpm'], bpm1, utils.fix_mods(''.join(mods)))
        else:
            stars_str, _ = utils.compare_val(beatmap['difficultyrating'], bmp_output, 'stars', dec_places = 2)
            info += "▸ **{}★** ▸ {}:{} ▸ {}bpm ▸ +{}\n".format(
                stars_str, m0, str(s0).zfill(2), beatmap['bpm'], utils.fix_mods(''.join(mods)))

        #try:
        if old_user_info != None:
            dpp = float(new_user_info['pp_raw']) - float(old_user_info['pp_raw'])
            if dpp == 0:
                pp_gain = ""
            else:
                pp_gain = "({:+.2f})".format(dpp)
            info += "▸ {} ▸ **{:.2f}%** ▸ **{:.2f} {}pp**\n".format(self.RANK_EMOTES[play['rank']],
                float(acc), float(play['pp']), pp_gain)
            info += "▸ {} ▸ x{}/{} ▸ {}\n".format(
                play['score'], play['maxcombo'], beatmap['max_combo'],
                self._get_score_breakdown(play, gamemode_num))
            info += "▸ #{} → #{} ({}#{} → #{})".format(
                old_user_info['pp_rank'], new_user_info['pp_rank'],
                new_user_info['country'],
                old_user_info['pp_country_rank'], new_user_info['pp_country_rank'])
        else: # if first time playing
            info += "▸ {} ▸ **{:.2f}%** ▸ **{:.2f}pp**\n".format(
                self.RANK_EMOTES[play['rank']], float(acc), float(play['pp']))
            info += "▸ {} ▸ x{}/{} ▸ {}\n".format(
                play['score'], play['maxcombo'], beatmap['max_combo'],
                self._get_score_breakdown(play, gamemode_num))
            info += "▸ #{} ({}#{})".format(
                new_user_info['pp_rank'],
                new_user_info['country'],
                new_user_info['pp_country_rank'])
        #except:
            #info += "Error"
        em.description = info

        time_ago_datetime = datetime.datetime.utcnow() - datetime.datetime.strptime(play['date'], '%Y-%m-%d %H:%M:%S')

        if int(time_ago_datetime.total_seconds()) < 300:
            latency_info = await self.track_latency.find_one({'shard_id': '{}'.format(str(self.bot.shard_id))})
            if not latency_info:
                await self.track_latency.insert_one({
                    'shard_id': '{}'.format(str(self.bot.shard_id)),
                    'latency': []
                })
                latency_info = await self.track_latency.find_one({'shard_id':'global'})

            latencies = deque(latency_info['latency'], maxlen = 300)
            latencies.append(int(time_ago_datetime.total_seconds()))
            latencies = list(latencies)
            await self.track_latency.update_one(
                {'shard_id':'{}'.format(str(self.bot.shard_id))}, {'$set': {
                    'latency': latencies,
                    }})

        shift = 0
        timeago = utils.time_ago(
            datetime.datetime.utcnow(),
            datetime.datetime.strptime(play['date'], '%Y-%m-%d %H:%M:%S'), shift=shift)
        em.set_footer(text = "{}Ago On osu! Official Server".format(timeago))
        return em


class TopPlayTrackerWebsocket(TopPlayTrackerPoll):
    def __init__(self, bot, api):
        self.bot = bot
        self.api = api
        self.uri = self.api.websocket
        self.prev_time = None
        self.poll_interval = 10 # seconds

    async def web_socket(self):
        # try:
        self.prev_time = datetime.datetime.utcnow()

        async with websockets.connect(self.uri) as websocket:
            # name = input("What's your name? ")

            message = await websocket.recv()
            print(f"< {self.api.name}: {message}")

            stream_query = {"type":"subscribe_scores", "data": []}
            stream_query = json.dumps(stream_query)
            await websocket.send(stream_query)

            while True:
                try:
                    message = await websocket.recv()
                    json_parsed = json.loads(message)
                    data = json_parsed['data']

                    # print(data.keys())

                    if data['completed']:
                        print(f"> {self.api.name}: {message}")
                except:
                    pass

        #except:
            #print(f"< {self.api.name}: FAILED TO CONNECT!")
            #await asyncio.sleep(60)
            #await self.web_socket()

    async def poll_tasks(self):
        pass


class MapTracker(Osu):
    def __init__(self, bot):
        super().__init__(bot)

    async def map_feed(self, api='official'):
        await asyncio.sleep(30) # sleep for 30 just in case
        MAP_FEED_INTERVAL = 120 # seconds

        print("RUNNING Map Feed")
        # use a json file instead of database
        filepath = os.path.join(os.getcwd(), "cogs/osu/temp/map_feed.json")
        if not os.path.exists(filepath):
            map_feed_last = datetime.datetime.utcnow()
            sql_date = datetime.datetime.strftime(map_feed_last, '%Y-%m-%d %H:%M:%S')
            map_json = {"last_check": sql_date}

            fileIO(filepath, "save", data=map_json)
        else:
            map_feed_last_str = fileIO(filepath, "load")['last_check']
            map_feed_last = datetime.datetime.strptime(map_feed_last_str, '%Y-%m-%d %H:%M:%S')

        while True:
            await asyncio.sleep(MAP_FEED_INTERVAL) # at beginning in case of crash

            # get new beatmaps
            sql_date = datetime.datetime.strftime(map_feed_last, '%Y-%m-%d %H:%M:%S')
            try:
                beatmaps = await self.owoAPI.get_beatmap(None, since=sql_date)
            except:
                await self.map_feed()
            print('QUERY TIME', sql_date)

            # save and update
            map_feed_last = datetime.datetime.utcnow()
            sql_date_new = datetime.datetime.strftime(map_feed_last, '%Y-%m-%d %H:%M:%S')
            map_json = {"last_check": sql_date_new}
            fileIO(filepath, "save", data=map_json)
            print('UPDATED TIME', sql_date_new)

            # display beatmaps
            new_beatmapsets = self._group_beatmaps(beatmaps)
            for beatmapset_id in new_beatmapsets:
                # new_beatmapset = new_beatmapsets[beatmapset_id]
                new_beatmapset = await self.owoAPI.get_beatmapset(beatmapset_id)

                # filter out the converts
                new_filtered = []
                for new_bmp in new_beatmapset:
                    if new_bmp['convert']:
                        continue
                    new_filtered.append(new_bmp)

                new_bmpset_embed = await self._create_new_bmp_embed(new_filtered)
                bmpset_summary = self._get_bmpset_summary(new_filtered)

                # download just to have the files cached
                try:
                    if int(bmpset_summary['status']) in [1, 2, 4]: # ranked/approved/loved
                        await self.owoAPI.download_osu_file(new_beatmapset[0])
                except:
                    pass

                # send to appropriate channels
                async for server_options in self.map_track.find({}, no_cursor_timeout=True):
                    guild_id = int(server_options["server_id"])
                    for channel_id in server_options['channels']:
                        channel_options = server_options['channels'][channel_id]
                        channel = self.bot.get_channel(int(channel_id))

                        # if pass the filters
                        if 'mappers' in channel_options and channel_options['mappers'] != [] and \
                            bmpset_summary['creator'] not in channel_options['mappers'] and \
                            bmpset_summary['creator_id'] not in channel_options['mappers']:
                            continue
                        if 'xmappers' in channel_options and channel_options['xmappers'] != [] and \
                            (bmpset_summary['creator'] in channel_options['xmappers'] or \
                            bmpset_summary['creator_id'] in channel_options['xmappers']):
                            continue
                        if channel_options['min_length'] is not None and \
                            float(channel_options['min_length']) > float(bmpset_summary['total_length']):
                            continue
                        if channel_options['max_length'] is not None and \
                            float(channel_options['max_length']) < float(bmpset_summary['total_length']):
                            continue
                        if channel_options['min_stars'] is not None and \
                            all([float(channel_options['min_stars']) > float(bmp_diff) for bmp_diff in bmpset_summary['stars']]):
                            continue
                        if channel_options['max_stars'] is not None and \
                            all([float(channel_options['max_stars']) < float(bmp_diff) for bmp_diff in bmpset_summary['stars']]):
                            continue
                        if channel_options['max_stars'] is not None and \
                            all([float(channel_options['max_stars']) < float(bmp_diff) for bmp_diff in bmpset_summary['stars']]):
                            continue
                        if not set(channel_options['modes']).intersection(set(bmpset_summary['modes'])):
                            continue
                        if str(bmpset_summary['status']) not in channel_options['status']:
                            continue                              

                        if channel:
                            try:
                                await channel.send(embed=new_bmpset_embed)
                            except:
                                print('Unable to send to', channel.id)
                                
                await asyncio.sleep(5)


def setup(bot):
    osu = Updater(bot)
    bot.add_cog(osu)

    # bot.loop.create_task(osu.map_feed()) !!!!!!!!!!!!!
