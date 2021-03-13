import os
import time
import copy
import json
import urllib
import random
import shutil
import zipfile
import hashlib
import aiohttp
import asyncio
import requests
import datetime 
import aiofiles
import operator
import pyttanko
import pickle as pkl
from PIL import Image
from string import ascii_uppercase
from utils.dataIO import dataIO, fileIO
from utils.uri_builder import URIBuilder

from cogs.osu.osu_utils.chunks import chunks
from cogs.osu.osu_utils.owoCache import owoCache
from cogs.osu.osu_utils import map_utils, web_utils, utils


class owoAPI(object):
    """
    Obtain API data from all osu servers in a semi-universal format
    """

    def __init__(self, official_api_key=None, 
        official_client_id=None, official_client_secret=None, 
        droid_api_key=None, beatconnect_api_key=None, database=None):
        # use cache?
        self.use_cache = fileIO("config.json", "load")['settings']['osu']['cache']

        # owo Cache
        self.cache = owoCache(database)

        # API list
        self.official_api = officialAPIv1(key=official_api_key)
        self.official_api_v2 = officialAPIv2(
            client_id=official_client_id, client_secret=official_client_secret)
        self.ripple_api = rippleAPI() # rippleAPIpeppy()
        self.ripplerx_api = ripplerxAPI()
        self.gatari_api = gatariAPI()
        self.akatsuki_api = akatsukiAPI() # akatsukiAPIpeppy()
        self.akatsukirx_api = akatsukirxAPI()
        self.droid_api = droidAPI(droid_api_key)
        self.kawata_api = kawataAPI() # kawataAPIpeppy()
        self.ainu_api = ainuAPI() # ainuAPIpeppy()
        self.ainurx_api = ainurxAPI()
        self.horizon_api = horizonAPI()# horizonAPIpeppy()
        self.horizonrx_api = horizonrxAPI()
        self.enjuu_api = enjuuAPI() # enjuuAPIpeppy()
        self.kurikku_api = kurikkuAPI() # kurikkuAPIpeppy()
        self.datenshi_api = datenshiAPI()# datenshiAPIpeppy()
        self.ezppfarm_api = ezppfarmAPI()# ezppfarmAPIpeppy()
        self.ezppfarmrx_api = ezppfarmrxAPI()
        self.ezppfarmap_api = ezppfarmapAPI()
        self.ezppfarmv2_api = ezppfarmv2API()

        """
        self.gatari_api = gatariAPI()
        self.akatuski_api = akatsukiAPI()
        self.ripple_api = rippleAPI()
        self.kawata_api = kawataAPI()
        self.aniu_api = aniuAPI()
        self.droid_api = droidAPI()"""

        # other services
        self.beatconnect_api = BeatConnect(beatconnect_api_key)

        # request_counter
        self.LOG_INTERVAL = 60
        self.last_log = time.time()
        self.request_counter = {}
        loop = asyncio.get_event_loop()
        loop.create_task(self.log_poller())

    # ---------------- logging ------------------
    async def log_poller(self):
        while True:
            if time.time() - self.last_log >= self.LOG_INTERVAL:
                self.request_counter = {}
                self.last_log = time.time()

            await asyncio.sleep(5)


    def log_request(self, request_name, api):
        if api not in self.request_counter:
            self.request_counter[api] = {}

        if request_name not in self.request_counter[api]:
            self.request_counter[api][request_name] = 0

        self.request_counter[api][request_name] += 1


    def get_api_usage(self):
        return self.request_counter

    # --------------- api -------------------------

    async def get_beatmap(self, beatmap_id, mods=0, 
        api='bancho', converted=0, since=None, use_cache=True):
        request_name = 'get_beatmap'

        # check cache for beatmap
        identifiers = {
            'beatmap_id': str(beatmap_id),
            'api': str(api),
            'mods': int(mods)
        }
        
        if use_cache and self.use_cache and since is None:
            beatmap_info = await self.cache.beatmap.get(identifiers)
            # print(beatmap_info)
            if beatmap_info is not None:
                if api == 'bancho':
                    await self.map_search_upsert(beatmap_info)
                # print('Using get_beatmap cache.')
                return [beatmap_info]
            # print('get_beatmap cache not found.')
        
        # otherwise get from api
        if api == "gatari":
            # print('GATARI MAP')
            beatmap_info = await self.gatari_api.get_beatmaps(
                beatmap_id=beatmap_id)
        elif api == "droid":
            # print('DROID MAP')
            beatmap_info = await self.ripple_api.get_beatmaps(
                beatmap_id=beatmap_id)
        elif since is not None:
            beatmap_info = await self.official_api.get_beatmaps(since=since)     
        elif 'bancho' not in api:
            # print(api, ' MAP')
            server_api = self.get_api(api)
            beatmap_info = await server_api.get_beatmaps(
                beatmap_id=beatmap_id)       
        else: # official
            beatmap_info = await self.official_api_v2.get_beatmaps(
                beatmap_id=beatmap_id, mods=mods)

        # then cache
        if beatmap_info:
            if api == 'bancho':
                await self.map_search_upsert(beatmap_info[0])
            await self.cache.beatmap.cache(identifiers, beatmap_info[0])

        # log request
        self.log_request(request_name, api)

        return beatmap_info


    async def get_beatmap_chunks(self, beatmap, beatmap_filepath, 
        mods=0, use_cache=True):

        identifiers = {
            'beatmap_id': beatmap['beatmap_id']
        }

        if use_cache and self.use_cache:
            bmap_chunk_cache = await self.cache.beatmap_chunks.get(identifiers)

            if bmap_chunk_cache:
                return bmap_chunk_cache['chunks']

        # download the beatmap in case
        if not os.path.exists(beatmap_filepath):
            await self.download_osu_file(beatmap)

        bmap_chunks = chunks(beatmap_filepath, mods=mods)

        # then cache
        if bmap_chunks:
            bmap_chunk_cache = {}
            bmap_chunk_cache['status'] = beatmap['status'] # needed for cache time
            bmap_chunk_cache['chunks'] = bmap_chunks

            await self.cache.beatmap_chunks.cache(
                identifiers, bmap_chunk_cache)

        return bmap_chunks


    async def get_beatmapset(self, set_id, mods=0, 
        api='bancho', converted=0, hash_id=None, use_cache=True):
        request_name = 'get_beatmapset'
        identifiers = {
            'beatmapset_id': str(set_id),
            'api': str(api),
        }

        if use_cache and self.use_cache:
            beatmapset_info = await self.cache.beatmapset.get(identifiers)

            if beatmapset_info:
                if api == 'bancho':
                    for bmp in beatmapset_info:
                        await self.map_search_upsert(bmp)
                return beatmapset_info

        beatmaps = await self.official_api_v2.get_beatmapset(set_id)

        # then cache
        if beatmaps:
            for bmp in beatmaps:
                await self.map_search_upsert(bmp)

            await self.cache.beatmapset.cache(identifiers, beatmaps)

        # log request
        self.log_request(request_name, api)

        return beatmaps


    async def get_full_beatmapset_image(self, beatmapset_id, beatmap_id=None):
        api = 'beatconnect'
        request_name = 'get_full_beatmapset_image'

        save_folder = 'cogs/osu/resources/beatmap_images_full'
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
        save_name = '{}.jpg'.format(beatmapset_id)
        full_path = os.path.join(save_folder, save_name)

        # log request
        self.log_request(request_name, api)

        resp = await self.beatconnect_api.get_full_beatmapset_image(
                beatmapset_id, beatmap_id=beatmap_id)
        
        if not resp:
            await self.download_beatmap_osz(beatmapset_id)

            if not os.path.exists(full_path): # if download was unsuccessful
                # print('BMP image not downloaded 2.')
                return 'cogs/osu/resources/triangles_map.png'

        return resp


    async def get_beatmapset_audio(self, beatmapset_id):
        api = 'beatconnect'
        request_name = 'get_beatmapset_audio'

        # log request
        self.log_request(request_name, api)

        return await self.beatconnect_api.get_beatmapset_audio(beatmapset_id)


    async def get_full_beatmap_info(self, beatmap_info, 
        mods=0, accs=[95, 99, 100], extra_info={}, use_cache=True, 
        force_osu_cache=False, api='bancho'):
        # calculations and append to response
        beatmap_data, bmp, file_path = await self._get_map_data(beatmap_info, 
            accs=accs, mods=mods, extra_info=extra_info, 
            force_osu_cache=force_osu_cache, api=api)
        beatmap_data.update(beatmap_info) # takes server info as truth
        return beatmap_data, bmp, file_path


    async def _get_map_data(self, beatmap_info, 
        accs=[95, 99, 100], mods=0, api='bancho', 
        extra_info={}, use_cache=True, force_osu_cache=False):

        # this is a helper function
        mods = int(mods)
        # print('MODE ', beatmap_info['mode']) # **
        try:
            mode = int(beatmap_info['mode'])
        except:
            mode = utils.mode_to_num(beatmap_info['mode'])

        relevant_mod_list = {'NF','EZ','HD','HR','DT','HT','NC','FL',
            '4K','5K','6K','7K','8K','9K','10K','1K','3K','2K'}
        mod_list = utils.num_to_mod(mods)

        # check cache for parsed beatmap
        identifiers = {'beatmap_id': str(beatmap_info['beatmap_id'])}
    
        bmap = None
        using_cache = False
        if mode == 0: # other modes don't work atm
            if use_cache and self.use_cache:
                bmap_file = await self.cache.beatmap_parsed.get(identifiers)
                # load file
                if bmap_file and os.path.exists(bmap_file):
                    # print("Loading cached file.")
                    with open(bmap_file, 'rb') as pickle_file:
                        bmap = pkl.load(pickle_file)
                    using_cache = True

        # get info
        # print('API ACCS', accs)
        filename = '{}.osu'.format(beatmap_info['beatmap_id'])
        file_path = os.path.join(os.getcwd(),'cogs','osu','beatmaps', filename)
        if mode == 0:
            if not bmap:
                file_path = await self.download_osu_file(beatmap_info, 
                    force_cache=force_osu_cache)
                bmap = pyttanko.parser().map(open(file_path))

            if api == 'droid':
                resp, bmap = await map_utils.get_droid_data(beatmap_info, bmap,
                    accs=accs, mods=mods, extra_info=extra_info)
            else:
                resp, bmap = await map_utils.get_std_data(beatmap_info, bmap,
                    accs=accs, mods=mods, extra_info=extra_info)
        elif mode == 1:
            resp, bmap = await map_utils.get_taiko_data(beatmap_info, 
                accs=accs, mods=mods, extra_info=extra_info)
        elif mode == 2:
            resp, bmap = await map_utils.get_ctb_data(beatmap_info, 
                accs=accs, mods=mods, extra_info=extra_info)
        elif mode == 3:
            resp, bmap = await map_utils.get_mania_data(beatmap_info, 
                accs=accs, mods=mods, extra_info=extra_info)

        if not resp:
            # if failed use gatari
            # resp = await self.gatari_api.get_pp(beatmap_info, accs[0], misses, combo, mods=mods)
            pass

        # if there's a bmp, then try to cache it
        # then cache
        if bmap is not None and not using_cache:
            await self.cache.beatmap_parsed.cache(identifiers, bmap, beatmap_info)

        return resp, bmap, file_path


    async def download_osu_file(self, beatmap_info, use_cache=True, force_cache=False, api='bancho'):
        request_name = 'download_osu_file'

        status = map_utils.handle_status(beatmap_info)
        beatmap_id = beatmap_info['beatmap_id']
        url = 'https://osu.ppy.sh/osu/{}'.format(beatmap_id)

        filename = '{}.osu'.format(beatmap_id)
        file_path = os.path.join(os.getcwd(),
            'cogs','osu','beatmaps',filename)

        identifiers = {'beatmap_id': str(beatmap_id)}

        if os.path.exists(file_path) and use_cache and self.use_cache:
            beatmap_osu_cache = await self.cache.beatmap_osu_file.get(identifiers)

            if beatmap_osu_cache or force_cache:
                return beatmap_osu_cache['filepath']

        # download the beatmap
        if status in [-2, 1, 2, 4]: # if it's ranked or graveyard, trust ripple
            viable_dl_apis = ['ripple', 'gatari', 'akatsuki', 'ezppfarm']
            beatmapset_id = beatmap_info['beatmapset_id']
            api = random.choice(viable_dl_apis)

            try:
                print('Downloading full osz for', beatmapset_id)
                await self.download_beatmap_osz(beatmapset_id, api=api)

                if not os.path.exists(file_path): # backup
                    print('Downloading osz unsuccesful, downloading .osu to', file_path)
                    await self.download_file(url, file_path)
            except:
                print('Downloading .osu to', file_path)
                await self.download_file(url, file_path)                         

        else: # if wip, graveyard, etc. use ppy's server
            print('Downloading .osu to', file_path)
            await self.download_file(url, file_path)
        
        # cache the result
        beatmap_osu_cache = {}
        beatmap_osu_cache['status'] = status # needed for cache time
        beatmap_osu_cache['filepath'] = file_path
        await self.cache.beatmap_osu_file.cache(
            identifiers, beatmap_osu_cache)

        self.log_request(request_name, api)
        return file_path


    async def download_beatmap_osz(self, set_id, api='ripple'):
        """downloads osz, unzips, and extracts all files into correct locations"""
        request_name = 'download_beatmap_osz'
        api_obj = self.get_api(api)
        if not api_obj.beatmap_download:
            api_obj = self.get_api('ripple')

        download_url = api_obj.beatmap_download.format(str(set_id))
        dest_folderpath = os.path.join(os.getcwd(), 'cogs', 'osu', 'temp')
        rand_dl_id = random.randint(0, 30)
        temp_filepath = os.path.join(dest_folderpath, 'beatmapset_{}.zip'.format(rand_dl_id))

        await self.download_file(download_url, temp_filepath)

        # check if temp_filepath exists
        if not os.path.exists(temp_filepath):
            return

        with zipfile.ZipFile(temp_filepath, 'r') as z:
            # Extract all the contents of zip file in different directory
            temp_location = os.path.join(dest_folderpath, 'beatmap_unzipped_{}'.format(rand_dl_id)) 

            # first delete original folder/content
            if os.path.exists(temp_location):
                shutil.rmtree(temp_location)
            z.extractall(temp_location)

            # ------------- attempt to extract image --------------
            background_dir = os.path.join(os.getcwd(), 'cogs', 'osu', 'resources', 'beatmap_images_full')
            background_filepath = os.path.join(background_dir, '{}.png'.format(set_id))
            valid_bg_images = []
            for f in os.listdir(temp_location):
                if os.path.splitext(f)[1].lower() in ['.jpg', '.jpeg', '.png']:
                    full_image_path = os.path.join(temp_location, f)
                    file_size = os.path.getsize(full_image_path)
                    valid_bg_images.append((full_image_path, file_size))

            # sort by size, largest is probably the background (one would hope)
            sorted_list = sorted(
                valid_bg_images, key=lambda tup: tup[1], reverse=True)
            bg_image_path = sorted_list[0][0]

            print('Downloading image to', background_filepath)

            full_image = Image.open(bg_image_path).convert('RGBA')
            full_image.save(background_filepath)

            # ------------- attempt to get .osu files --------------
            beatmap_folder = os.path.join(os.getcwd(), 'cogs', 'osu', 'beatmaps')
            valid_osu_files = []
            for f in os.listdir(temp_location):
                if os.path.splitext(f)[1].lower() in ['.osu']:
                    full_osu_filepath = os.path.join(temp_location, f)
                    
                    # process to find the beatmap id
                    beatmap_id = None
                    async with aiofiles.open(full_osu_filepath, mode='r') as f:
                        async for line in f:
                            if 'beatmapid:' in str(line).lower():
                                linesplit = str(line).split(':')
                                beatmap_id = linesplit[1].strip()
                                print('BEATMAP ID FOUND', beatmap_id)

                                # save to appropriate folder
                                new_osu_filepath = os.path.join(beatmap_folder, '{}.osu'.format(beatmap_id))
                                shutil.move(full_osu_filepath, new_osu_filepath)
                                break

        # beatmaps = await self.official_api_v2.download_beatmapset(set_id)
        self.log_request(request_name, api)


    async def get_scores(self, beatmap_id, user_id, mode, 
        relax=0, api='bancho', use_cache=True):
        request_name = 'get_scores'

        # check cache for user
        identifiers = {
            'beatmap_id': str(beatmap_id),
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }

        if use_cache and self.use_cache:
            user_score_info = await self.cache.user_score.get(identifiers)

            if user_score_info is not None:
                return user_score_info

        if api == 'bancho':
            resp = await self.official_api.get_scores(beatmap_id, user_id, mode)
        elif api == 'droid':
            resp = await self.droid_api.get_scores(user_id, beatmap_id)
        elif api == 'gatari':
            resp = await self.gatari_api.get_scores(user_id, beatmap_id)            
        elif 'ezpp' in api:
            resp = await api_obj.get_scores(beatmap_id, user_id, mode)            
        else:
            api_obj = self.get_api(api)
            resp = await api_obj.ppy_api.get_scores(beatmap_id, user_id, mode)
            # resp = await api_obj.get_scores(beatmap_id, user_id, mode)

        # resp = await api.get_scores(beatmap_id, user_id, mode)
        await self.cache.user_score.cache(identifiers, resp) # whole list

        self.log_request(request_name, api)
        return resp


    async def get_user(self, user_id, 
        mode=0, api='bancho', use_cache=True):
        request_name = 'get_user'

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }

        if use_cache and self.use_cache:
            user_info = await self.cache.user.get(identifiers)

            if user_info is not None:
                return [user_info]        

        # clean up for v2
        user_id = urllib.parse.quote(user_id.encode('utf8'))

        if api == 'bancho':
            # user_id = user_id.replace('_', ' ')
            resp = await self.official_api_v2.get_user(user_id, mode=mode)
            if not resp:
                resp = await self.official_api.get_user(user_id, mode=mode)

        else:
            try:
                api_obj = self.get_api(api)
                resp = await api_obj.get_user(user_id, mode=mode)
            except:
                resp = None

        # then cache, event if they don't exist
        try:
            await self.cache.user.cache(identifiers, resp[0])
        except:
            await self.cache.user.cache(identifiers, resp)   

        self.log_request(request_name, api)    
        return resp


    async def get_user_detailed(self, user_id, 
        mode=0, api='bancho', use_cache=True):
        # request_name = 'get_user'
        # get recent activity, achievements, most played, badges, graphs
        resp = None
        if 'bancho' in api:
            # profile, firsts, recent activity, beatmaps
            resp = await self.get_user(user_id, api=api)

        # self.log_request(request_name, api)

        return resp


    async def get_user_recent_activity(self, user_id, 
        limit=50, offset=0, api='bancho', use_cache=True):
        request_name = 'get_user_recent_activity'

        if api != 'bancho':
            return None

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api)
        }

        if use_cache and self.use_cache:
            recent_info = await self.cache.user_recent_activity.get(
                identifiers)
            if recent_info is not None:
                return recent_info 

        resp = await self.official_api_v2.get_user_recent_activity(
            user_id, limit=limit, offset=offset)
        

        # then cache
        if resp:
            await self.cache.user_recent_activity.cache(identifiers, resp)  

        self.log_request(request_name, api)    
        return resp


    async def get_user_best(self, user_id, 
        mode=0, api='bancho', limit=50, use_cache=True):
        request_name = 'get_user_best'

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }

        if use_cache and self.use_cache:
            user_best = await self.cache.user_best.get(identifiers)
            if user_best is not None and len(user_best) >= limit:
                return user_best

        api_obj = self.get_api(api)

        if 'bancho' in api:
            resp = await self.official_api_v2.get_user_best(
                user_id, mode, limit=limit)
        elif 'droid' in api:
            resp = await api_obj.get_user_best(user_id)
        else:
            resp = await api_obj.get_user_best(user_id, mode, limit=limit)

        if resp:
            await self.cache.user_best.cache(identifiers, resp)    

        self.log_request(request_name, api)
        return resp


    async def get_user_best_no_choke(self, user_id, 
        mode=0, api='bancho', use_cache=True):

        if api != 'bancho' or mode != 0:
            return None

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }
        user_nc_cache = None
        cache_time = None
        cache_valid = False
        
        if use_cache and self.use_cache:
            user_nc_cache, cache_time, cache_valid = await self.cache.user_nc_best.get(
                identifiers, force=True, include_time=True)

            # only if the cache is valid, otherwise, do other checks
            if user_nc_cache and cache_valid:
                return user_nc_cache

        top_scores = await self.get_user_best(user_id, 
            mode=mode, limit=100, api=api)

        # after you get top scores check if needs to be reprocess/recache
        if cache_time and user_nc_cache: # if there was an actual cache time
            cache_time_dt = datetime.datetime.utcfromtimestamp(
                cache_time).strftime('%Y-%m-%d %H:%M:%S')
            new_score_exists = any([score['date'] > cache_time_dt for score in top_scores])

            # if there are no new scores, no point in processing
            if not new_score_exists:
                # recache and return
                await self.cache.user_nc_best.cache(identifiers, user_nc_cache) 
                return user_nc_cache

        # otherwise, process new stats
        resp = await self._process_no_choke(
            top_scores, mode=mode, api=api)
        if resp:
            await self.cache.user_nc_best.cache(identifiers, resp) 

        return resp

    async def _process_no_choke(self, play_list, mode=0, api='bancho'):
        # will output in same format as user_best, but no choke with "original" field.
        no_choke_list = []

        for i, play_info in enumerate(play_list):

            if 'enabled_mods' in play_info:
                enabled_mods = int(play_info['enabled_mods'])
            elif 'mods' in play_info:
                enabled_mods = utils.mod_to_num(''.join(play_info['mods']))

            # ensure some info exists... because some don't have it?
            if api != 'bancho':
                map_info = await self.get_beatmap(
                    play_info['beatmap']['beatmap_id'], api=api)
                map_info = map_info[0]
                map_info['status'] = 1
                map_info['mode'] = mode
                # print(map_info)
            else:
                map_info = play_info['beatmap']

            # print('MAP INFO', map_info)
            try:
                beatmap_info, bmap, _ = await self.get_full_beatmap_info(map_info, 
                    extra_info={'play_info': play_info}, mods=enabled_mods,
                    force_osu_cache=True)
                map_max_combo = int(bmap.max_combo())
            except:
                continue
            
            # check if choke play
            no_choke_play = copy.deepcopy(play_info)
            no_choke_play['original_idx'] = i+1
            if play_info['count_miss'] > 0 or \
                (map_max_combo - int(play_info['max_combo']) > int(play_info['count_100'])) or \
                (int(play_info['max_combo']) < map_max_combo * 0.95):

                # this part is direct copy from map_utils, but still use map utils for calc
                no_choke_play['count_300'] = int(play_info['count_300']) + \
                    int(play_info['count_miss'])
                no_choke_play['count_100'] = int(play_info['count_100'])
                no_choke_play['count_50'] = int(play_info['count_50'])
                no_choke_play['count_miss'] = 0
                no_choke_play['max_combo'] = map_max_combo
                no_choke_play['accuracy'] = beatmap_info['extra_info']['fc_acc']
                no_choke_play['pp'] = beatmap_info['extra_info']['fc_pp']
                no_choke_play['original'] = copy.deepcopy(play_info)
                no_choke_play['rank'] = utils.calculate_rank(
                    no_choke_play, no_choke_play['accuracy'], ''.join(play_info['mods']))
            else:
                no_choke_play['original'] = None

            no_choke_list.append(no_choke_play)

        # sort by pp by default
        no_choke_list_sorted = sorted(no_choke_list, 
                            key=operator.itemgetter('pp'), reverse=True)
        return no_choke_list_sorted


    async def get_user_stats(self, user_id, 
        mode=0, api='bancho', use_cache=True):

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }

        user_stats_cache = None
        cache_time = None
        cache_valid = False
        if use_cache and self.use_cache:
            user_stats_cache, cache_time, cache_valid = await self.cache.user_stats.get(
                identifiers, force=True, include_time=True)

            # only if the cache is valid, otherwise, do other checks
            if user_stats_cache and cache_valid:
                return user_stats_cache

        top_scores = await self.get_user_best(user_id, 
            mode=mode, limit=100, api=api)

        # after you get top scores check if needs to be reprocess/recache
        if cache_time and user_stats_cache: # if there was an actual cache time
            cache_time_dt = datetime.datetime.utcfromtimestamp(
                cache_time).strftime('%Y-%m-%d %H:%M:%S')
            new_score_exists = any([score['date'] > cache_time_dt for score in top_scores])

            # if there are no new scores, no point in processing
            if not new_score_exists:
                # recache and return
                await self.cache.user_stats.cache(identifiers, user_stats_cache) 
                return user_stats_cache

        # otherwise, process new stats
        resp = await self._process_stats(
            top_scores, mode=mode, api=api)
        if resp:
            await self.cache.user_stats.cache(identifiers, resp) 

        return resp


    async def _process_stats(self, scores, mode=0, api='bancho'):
        stats_list = {
            "mappers": [],
            "mod_combos": [],
            "mods": [],
            "stars": [],
            "aim": [],
            "speed": [],
            "acc": [],
            "bpm": [],
            "pp": [],
            "pp_w": [],
            "rank": [],
        }

        for score_idx, score in enumerate(scores):
            # weighting score['weight']
            # https://osu.ppy.sh/wiki/en/Performance_points/Weighting_system

            if 'enabled_mods' in score:
                enabled_mods = int(score['enabled_mods'])
            elif 'mods' in score:
                enabled_mods = utils.mod_to_num(''.join(score['mods']))

            # ensure some info exists... because some don't have it?
            if api != 'bancho':
                map_info = await self.get_beatmap(
                    score['beatmap']['beatmap_id'], api=api)
                map_info = map_info[0]
                map_info['status'] = 1
                map_info['mode'] = mode
                # print(map_info)
            else:
                map_info = score['beatmap']

            # if mode == 0:
            beatmap_info, _, _ = await self.get_full_beatmap_info(map_info, 
                extra_info={'play_info': score}, mods=enabled_mods,
                force_osu_cache=True)
            # else:
                # beatmap_info = map_info

            # print(score, beatmap_info.keys())
            stats_list['rank'].append(score['rank'])
            stats_list['pp'].append(score['pp'])
            stats_list['pp_w'].append(score['pp'] * 0.95 ** score_idx)
            try:
                stats_list['mappers'].append(score['beatmapset']['creator'])
            except:
                stats_list['mappers'].append(map_info['creator'])
            mod_list = utils.num_to_mod(enabled_mods)
            if not mod_list:
                mod_list = ['NM']
            stats_list['mods'].extend(mod_list)
            mod_combo_str = utils.fix_mods(''.join(utils.num_to_mod(enabled_mods)))
            if not mod_combo_str:
                mod_combo_str = 'NM'
            stats_list['mod_combos'].append(mod_combo_str)
            try:
                stats_list['stars'].append(beatmap_info['stars_mod'])
                stats_list['aim'].append(beatmap_info['aim_stars_mod'])
                stats_list['speed'].append(beatmap_info['speed_stars_mod'])
            except:
                stats_list['stars'].append(beatmap_info['difficulty_rating'])

            # accuracy
            if 'accuracy'not in score:
                play_acc = utils.calculate_acc(score, mode)
            else:
                play_acc = score['accuracy']
            stats_list['acc'].append(play_acc)
            try:
                stats_list['bpm'].append(beatmap_info['bpm_mod'])
            except: # this is an issue lol, calc stats in get_std_data in case of fail
                stats_list['bpm'].append(beatmap_info['bpm'])

        return stats_list



    async def get_user_recent(self, user_id, 
        mode=0, limit=50, api='bancho', use_cache=True):
        request_name = 'get_user_recent'

        # check cache for user
        identifiers = {
            'user_id': str(user_id).lower(),
            'api': str(api),
            'mode': int(mode)
        }

        if use_cache and self.use_cache:
            user_recent = await self.cache.user_recent.get(identifiers)
            # print('Using recent cache', user_recent)
            if user_recent is not None:
                return user_recent

        api_obj = self.get_api(api)
        if api == 'bancho':
            # resp = await self.official_api.get_user_recent(user_id, mode=mode)
            resp = await self.official_api_v2.get_user_recent(user_id, mode=mode)
            
        elif api == 'akatsukirx' or api == 'ripplerx':
            resp = await api_obj.get_user_recent(user_id, mode)
        elif api == 'gatari':
            resp = await api_obj.get_user_recent(user_id, mode=mode, length=50)
        else:
            resp = await api_obj.get_user_recent(user_id, mode)

        # print('RESP ', resp[0:2])
        if resp is not None:
            await self.cache.user_recent.cache(identifiers, resp)  

        self.log_request(request_name, api)
        return resp


    async def get_leaderboard(self, beatmap_id, 
        mods=None, mode=0, api='bancho', use_cache=True):
        request_name = 'get_leaderboard'

        # check cache for user
        identifiers = {
            'beatmap_id': str(beatmap_id).lower(),
            'api': str(api),
            'mods': mods,
            'mode': int(mode)
        }

        if use_cache and self.use_cache:
            leaderboard = await self.cache.leaderboard.get(identifiers)
            # print('Using recent cache', user_recent)
            if leaderboard:
                return leaderboard

        if api == 'bancho': # use v1 for this for now
            resp = await self.official_api.get_leaderboard(beatmap_id, 
                mods=mods, mode=mode)
            
        else:
            api_obj = self.get_api(api)
            resp = await api_obj.get_leaderboard(beatmap_id, 
                mods=mods, mode=mode)

        if resp is not None:
            await self.cache.leaderboard.cache(identifiers, resp)  

        self.log_request(request_name, api) 
        return resp


    async def is_online(self, user, api='bancho'):
        api = self.get_api(api)
        resp = await api.is_online(user)
        return resp


    # ------------------ searching function ----------------
    async def map_search(self, search_terms, limit=50):
        headers={'content-type': 'application/json'}
        full_query = {
            "size": limit,
            "query": {
                "match": {
                    "full_name": search_terms
                }
            }
        }

        url = 'http://localhost:9200/osu/mapsearch/_search'
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.dumps(full_query), 
                headers=headers) as r:

                json_data = await r.json()

        if 'hits' not in json_data:
            return []

        cleaned_list = []
        for hit in json_data['hits']['hits']:
            
            cleaned_list.append(hit['_source'])

        return cleaned_list


    async def _map_search_beatmap_exists(self, beatmap_id):
        headers={'content-type': 'application/json'}
        full_query = {
            "query": {
                "match": {
                    "beatmap_id": beatmap_id
                }
            }
        }

        url = 'http://localhost:9200/osu/mapsearch/_search'
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.dumps(full_query),
                headers=headers) as r:
                json_data = await r.json()

        results = json_data['hits']['hits']

        # if exists
        for hit in results:
            if hit['_source']['beatmap_id'] == beatmap_id:
                return True
        return False


    async def map_search_upsert(self, data):
        headers={'content-type': 'application/json'}

        # check if something like that exists
        # if not self._map_search_beatmap_exists(data['beatmap_id']):
        url = 'http://localhost:9200/osu/mapsearch/{}/_update'.format(data['beatmap_id'])
                
        new_doc = {}
        new_doc['beatmap_id'] = data['beatmap_id']
        new_doc['status'] = data['status']
        new_doc['difficulty_rating'] = data['difficulty_rating']

        if 'version' not in data.keys():
            return
        new_doc['version'] = data['version']
        new_doc['creator'] = data['creator']

        beatmapset_str = ''
        if 'beatmapset_id' in data.keys():
            new_doc['beatmapset_id'] = data['beatmapset_id']
            beatmapset_str = data['beatmapset_id']

        if 'mode' in data.keys():
            new_doc['mode'] = int(data['mode'])

        new_doc['artist'] = data['artist']
        if 'artist_unicode' in data.keys():
            new_doc['artist_unicode'] = data['artist_unicode']
        
        new_doc['title'] = data['title']
        if 'title_unicode' in data.keys():
            new_doc['title_unicode'] = data['title_unicode']

        new_doc['full_name'] = '{} - {} [{}] {} {} {}'.format(
            data['artist'], data['title'], data['version'], data['creator'],
            data['beatmap_id'], beatmapset_str)

        # generate str for script
        script_str = ""
        for key in new_doc.keys():
            script_str += "ctx._source.{} = '{}'; ".format(key, new_doc[key])

        full_query = {
            "script": {
                "source": script_str
            },
            "upsert": new_doc
        }
        
        # resp = requests.post(url, data=json.dumps(full_query), headers=headers)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=json.dumps(full_query),
                headers=headers) as r:
                json_data = await r.json()

        return new_doc


    # ----------------- helper functions
    def url_to_server(self, url: str):
        if self.official_api.base in url:
            return "bancho"
        elif self.gatari_api.base in url:
            return "gatari"
        elif self.ripple_api.base in url:
            return "ripple"
        elif self.akatsuki_api.base in url:
            return "akatsuki"
        elif self.horizon_api.base in url:
            return "horizon"
        elif self.kawata_api.base in url:
            return "kawata"
        elif self.ainu_api.base in url:
            return "ainu"
        elif self.enjuu_api.base in url:
            return "enjuu"
        elif self.kurikku_api.base in url:
            return "kurikku"
        elif self.datenshi_api.base in url:
            return "datenshi"
        elif self.ezppfarm_api.base in url:
            return "ezppfarm"
        else:
            return "unknown"


    def get_beatmap_thumbnail(self, beatmap_info):
        url = 'https://b.ppy.sh/thumb/{}l.jpg'.format(
            beatmap_info['beatmapset_id'])
        return url


    def get_beatmap_url(self, beatmap_info):
        url = "https://osu.ppy.sh/b/{}".format(
            beatmap_info['beatmap_id'])
        return url


    def get_server_avatar(self, server_name):
        api = self.get_api(server_name)
        return api.symbol_url


    def get_server_name(self, api_name):
        api = self.get_api(api_name)
        return api.name


    async def get_user_avatar(self, user_id, api_name):
        rand_int = random.randint(0, 1000)
        api = self.get_api(api_name)
        if api_name == 'droid':
            return await api.get_avatar(user_id)

        return api.avatar_url.format(user_id) + '?{}'.format(str(rand_int))


    def get_country_flag_url(self, country_code):
        return 'https://osu.ppy.sh/images/flags/{}.png'.format(
            country_code)
    

    def get_user_url(self, user_id, api='bancho'):
        user_id = str(user_id)

        api = self.get_api(api)
        user_url = api.user_url_base.format(user_id)
        return user_url


    def get_api(self, api_name):
        # returns the api object
        if 'ripplerx' in api_name.lower():
            return self.ripplerx_api
        elif 'akatsukirx' in api_name.lower():
            return self.akatsukirx_api
        elif 'ainurx' in api_name.lower():
            return self.ainurx_api
        elif 'horizonrx' in api_name.lower():
            return self.horizonrx_api
        elif 'ezppfarmrx' in api_name.lower():
            return self.ezppfarmrx_api
        elif 'ezppfarmap' in api_name.lower():
            return self.ezppfarmap_api
        elif 'ezppfarmv2' in api_name.lower():
            return self.ezppfarmv2_api

        elif 'gatari' in api_name.lower():
            return self.gatari_api
        elif 'ripple' in api_name.lower():
            return self.ripple_api
        elif 'akatsuki' in api_name.lower():
            return self.akatsuki_api
        elif 'kawata' in api_name.lower():
            return self.kawata_api
        elif 'ainu' in api_name.lower():
            return self.ainu_api
        elif 'droid' in api_name.lower():
            return self.droid_api
        elif 'horizon' in api_name.lower():
            return self.horizon_api
        elif 'enjuu' in api_name.lower():
            return self.enjuu_api
        elif 'kurikku' in api_name.lower():
            return self.kurikku_api
        elif 'datenshi' in api_name.lower():
            return self.datenshi_api
        elif 'ezppfarm' in api_name.lower():
            return self.ezppfarm_api
        elif 'official_v2' in api_name.lower():
            return self.official_api_v2
        elif 'bancho' in api_name.lower():
            return self.official_api_v2
        else:
            return self.official_api_v2


    def get_api_list(self):
        api_list = []
        api_list.append('bancho')
        api_list.append('ripple')
        api_list.append('akatsuki')
        api_list.append('kawata')
        api_list.append('ainu')
        api_list.append('droid')
        api_list.append('horizon')
        api_list.append('enjuu')
        api_list.append('kurikku')
        api_list.append('datenshi')
        api_list.append('ezppfarm')

        api_list = sorted(api_list)

        return api_list


    async def download_file(self, uri, path):
        print(uri)

        async with aiohttp.ClientSession() as session:
            async with session.get(uri) as resp:
                # print(resp.status)
                if resp.status == 200:
                    f = await aiofiles.open(path, mode='wb')
                    await f.write(await resp.read())
                    await f.close()


class BeatConnect:
    def __init__(self, key=None):
        self.base = 'https://beatconnect.io/api/{}'
        self.api_key = key

    async def map_search(self, query=None, status=0, mode=0, page=0, diff_range=[0, 10]):   
        uri_base = 'search/?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('token', self.api_key)
        uri_builder.add_parameter('s', status)
        mode_txt = utils.mode_to_str(mode)
        uri_builder.add_parameter('m', mode_txt) # string
        uri_builder.add_parameter('p', page)
        uri_builder.add_parameter('diff_range', 
            '{diff_range[0]}-{diff_range[1]}'.format(diff_range))
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        return resp


    async def get_full_beatmapset_image(self, beatmapset_id, beatmap_id=None):
        if beatmap_id:
            end_str = beatmap_id
        else:
            end_str = ''.join(random.choice(ascii_uppercase) for i in range(8))
        uri_base = u'bg​/{}​/{}​/'.format(beatmapset_id, end_str)
        uri_builder = URIBuilder(uri_base)
        base = 'https://beatconnect.io/{}'
        uri = base.format(uri_builder.uri).encode('ascii', 'ignore').decode("utf-8")

        save_folder = 'cogs/osu/resources/beatmap_images_full'
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
        save_name = '{}.jpg'.format(beatmapset_id)
        full_path = os.path.join(save_folder, save_name)

        if not os.path.exists(full_path):
            await self.download_file(uri, full_path)

        if not os.path.exists(full_path): # if download was unsuccessful
            # print('BMP image not downloaded.')
            return None

        return full_path


    async def get_beatmapset_audio(self, beatmapset_id):
        cache_str = ''.join(random.choice(ascii_uppercase) for i in range(8)) 
        uri_base = u'audio/{}​/{}​/'.format(beatmapset_id, cache_str)
        uri_builder = URIBuilder(uri_base)
        base = 'https://beatconnect.io/{}'
        uri = base.format(uri_builder.uri).encode('ascii', 'ignore').decode("utf-8")

        save_folder = 'cogs/osu/resources/beatmap_audio'
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)
        save_name = '{}.mpg'.format(beatmapset_id)
        full_path = os.path.join(save_folder, save_name)

        if not os.path.exists(full_path):
            await self.download_file(uri, full_path)

        return full_path


    async def download_file(self, uri, path):
        print(uri)

        async with aiohttp.ClientSession() as session:
            async with session.get(uri) as resp:
                # print(resp.status)
                if resp.status == 200:
                    f = await aiofiles.open(path, mode='wb')
                    await f.write(await resp.read())
                    await f.close()


class officialAPIv1:

    def __init__(self, key=None):
        self.name = "Bancho"
        self.base = 'https://osu.ppy.sh/api/{}'
        self.symbol_url = 'https://i.imgur.com/Req9wGs.png'
        self.user_url_base = "https://osu.ppy.sh/users/{}"
        self.avatar_url = "http://s.ppy.sh/a/{}"
        self.api_key = key
        self.beatmap_download = 'https://osu.ppy.sh/beatmapsets/{}/download?noVideo=1'
        self.websocket = None


    async def get_beatmaps(self, 
        beatmapset_id=None, beatmap_id=None, user_id=None, 
        mode=0, converted=0, limit=500, mods=0, since=None):
        uri_base = 'get_beatmaps?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('s', beatmapset_id)
        if str(beatmap_id).isnumeric() or len(str(beatmap_id)) <= 8:
            uri_builder.add_parameter('b', beatmap_id)
        else:
            uri_builder.add_parameter('h', beatmap_id)
        uri_builder.add_parameter('since', since)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('a', converted)
        uri_builder.add_parameter('limit', limit)
        uri_builder.add_parameter('mods', mods)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_user(self, user_id, mode=0):
        uri_base = 'get_user?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('m', mode)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_scores(self, beatmap_id, user_id, mode=0, mods=None, limit=50):
        uri_base = 'get_scores?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('b', beatmap_id)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('m', mode)
        uri_builder.add_parameter('mods', mods)
        uri_builder.add_parameter('limit', limit)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        resp = key_cleanup(resp, self.key_mapping)  # clean up

        return resp


    async def get_user_best(self, user_id, mode=0, limit=100):
        uri_base = 'get_user_best?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('m', mode)
        uri_builder.add_parameter('limit', limit)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_user_recent(self, user_id, mode=0, limit=50):
        uri_base = 'get_user_recent?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('m', mode)
        uri_builder.add_parameter('limit', limit)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_leaderboard(self, beatmap_id, mode=0, mods=0, limit=100):
        uri_base = 'get_scores?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('k', self.api_key)
        uri_builder.add_parameter('b', beatmap_id)
        uri_builder.add_parameter('m', mode)
        uri_builder.add_parameter('mods', mods)
        uri_builder.add_parameter('limit', limit)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    def is_online(self, username):
        # doesn't follow typical structure
        self.osu_db = client['owo_database_2']
        self.online = self.osu_db['online']

        if "_" in username and username.find("_") != 0:
            test_usernames.append(username.replace("_", " "))
        if " " in username:
            test_usernames.append(username.replace(" ", "_"))

        db_data = self.online.find_one({"type": "onlinelist"})
        if db_data:
            online_list = db_data["onlinelist"]
        else:
            return False

        db_data = self.players.find_one({"osu_username": username})
        if db_data:
            if ('ingame' in db_data.keys() and db_data['ingame'] == 1) or (online_list and username in online_list):
                return True
        return False


    def key_mapping(self, key_name, command=None):
        if key_name == 'difficultyrating':
            return 'difficulty_rating'
        if key_name == 'diff_size':
            return 'cs'
        if key_name == 'diff_overall':
            return 'od'
        if key_name == 'diff_approach':
            return 'ar'
        if key_name == 'diff_drain':
            return 'hp'
        if key_name == 'count300':
            return 'count_300'
        if key_name == 'count100':
            return 'count_100'
        if key_name == 'count50':
            return 'count_50'
        if key_name == 'countmiss':
            return 'count_miss'
        if key_name == 'countkatu':
            return 'count_katu'
        if key_name == 'countgeki':
            return 'count_geki'
        if key_name == 'maxcombo':
            return 'max_combo'
        if key_name == 'approved':
            return 'status'


class officialAPIv2(object):
    def __init__(self, client_id=None, client_secret=None):
        self.name = "Bancho"
        self.base = 'https://osu.ppy.sh/api/v2/{}'
        self.symbol_url = 'https://i.imgur.com/Req9wGs.png'
        self.user_url_base = "https://osu.ppy.sh/users/{}"
        self.avatar_url = "http://s.ppy.sh/a/{}"
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expire = None
        self.beatmap_download = 'https://osu.ppy.sh/beatmapsets/{}/download?noVideo=1'
        self.websocket = None

    # ----- user ------
    async def get_user(self, user, mode=0):
        mode_text = self.mode_to_str(mode)
        uri_base = 'users/{}/{}?'.format(user, mode_text)

        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        # print(resp.keys())

        # put statistics in first level
        try:
            resp.update(resp['statistics'])
            del resp['statistics']
        except: # user not found
            return None

        # change grade_counts
        for grade_count in resp['grade_counts']:
            resp['count_rank_{}'.format(grade_count)] = resp['grade_counts'][grade_count]
        del resp['grade_counts']

        # handle ranks
        resp['pp_rank'] = None
        if 'global_rank' in resp:
            resp['pp_rank'] = resp['global_rank']# ['rank']# ['rank']['global']
        
        resp['pp_country_rank'] = None
        if 'country_rank' in resp:
            resp['pp_country_rank'] = resp['country_rank']#['rank']['country']
        elif 'rank' in resp and 'country' in resp['rank']:
            resp['pp_country_rank'] = resp['rank']['country']

        del resp['rank']

        # format level info
        resp['level'] = float(resp['level']['current']) + float(resp['level']['progress'])/100

        # fix country
        resp['country'] = resp['country']['code']

        resp = key_cleanup([resp], self._get_user_key_mapping)  # clean up

        return resp


    def _get_user_key_mapping(self, key_name, command="get_user"):
        if key_name == "id":
            return "user_id"
        if key_name == "play_count":
            return "playcount"
        if key_name == "play_time":
            return "total_seconds_played"
        if key_name == "hit_accuracy":
            return "accuracy"
        if key_name == "maximum_combo":
            return "max_combo"
        if key_name == "rankHistory":
            return "rank_history"
        if key_name == 'pp':
            return 'pp_raw'


    async def get_user_best(self, user_id, mode=0, limit=100):
        MAX_PER_PAGE = 50
        total_resp = []

        for i in range(round(limit/MAX_PER_PAGE)):
            if i == 0:
                offset = i
            else:
                offset = i*MAX_PER_PAGE

            mode_text = self.mode_to_str(mode)
            uri_base = 'users/{}/scores/best?'.format(user_id)

            uri_builder = URIBuilder(uri_base)
            uri_builder.add_parameter('mode', mode_text)
            uri_builder.add_parameter('limit', MAX_PER_PAGE)
            uri_builder.add_parameter('offset', offset)
            uri = self.base.format(uri_builder.uri)

            resp = await self.fetch(uri)

            resp = self.fix_score_keys(resp)

            total_resp.extend(resp)
        
        return total_resp


    def fix_score_keys(self, resp):
        for play in resp:
            # get mod number
            play['enabled_mods'] = utils.mod_to_num(''.join(play['mods']))

            # fix date
            play['date'] = play['created_at']
            del play['created_at']
            play = value_cleanup([play], 'date', self._fix_date)[0]

            # fix accuracy
            play = value_cleanup([play], 'accuracy', self._fix_accuracy)[0]

            # get count hits
            play.update(play['statistics'])
            del play['statistics']

            # format user section
            play['user'] = key_cleanup([play['user']], 
                self._get_user_key_mapping)[0]

            # format beatmap section
            play['beatmap'] = key_cleanup([play['beatmap']], 
                self._get_beatmap_key_mapping)[0]
            play['beatmap'] = value_cleanup([play['beatmap']], 
                'status', self._fix_ranking_status)[0]

            play['beatmap_id'] = play['beatmap']['beatmap_id']

            play['beatmapset'] = key_cleanup([play['beatmapset']], 
                self._get_beatmapset_key_mapping)[0]
            play['beatmapset'] = value_cleanup([play['beatmapset']], 
                'status', self._fix_ranking_status)[0]

        return resp


    async def get_user_recent(self, user, 
        include_fails=True, mode=0, limit=50, offset=0):
        mode_text = self.mode_to_str(mode)
        uri_base = 'users/{}/scores/recent?'.format(user)

        MAX_PER_PAGE = 50
        total_resp = []

        for i in range(round(limit/MAX_PER_PAGE)):
            if i == 0:
                offset = i
            else:
                offset = i*MAX_PER_PAGE

            uri_builder = URIBuilder(uri_base)
            uri_builder.add_parameter('include_fails', int(include_fails))
            uri_builder.add_parameter('mode', mode_text)
            uri_builder.add_parameter('limit', MAX_PER_PAGE)
            uri_builder.add_parameter('offset', offset)
            uri = self.base.format(uri_builder.uri)

            resp = await self.fetch(uri)

            resp = self.fix_score_keys(resp)

            total_resp.extend(resp)

        return total_resp


    async def get_user_firsts(self, user, mode=0, limit=50, offset=0):
        mode_text = self.mode_to_str(mode)
        uri_base = 'users/{}/scores/firsts?'.format(user)

        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('mode', mode_text)
        uri_builder.add_parameter('limit', limit)
        uri_builder.add_parameter('offset', offset)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        resp = self.fix_score_keys(resp)

        return resp


    async def get_user_beatmaps(self, user_id, 
        limit=50, offset=0, bmp_type='ranked_and_approved'):
        # types:
        # favourite, graveyard, loved, most_played, ranked_and_approved, unranked
        uri_base = 'users/{}/beatmapsets/{}?'.format(user_id, bmp_type)

        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('limit', limit)
        uri_builder.add_parameter('offset', offset)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)
        resp = key_cleanup(resp, self.key_mapping, 
            command="get_user_beatmaps")  # clean up
        return resp


    async def get_user_recent_activity(self, user_id, 
        limit=50, offset=0):

        uri_base = 'users/{}/recent_activity?'.format(user_id)
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('limit', limit)
        uri_builder.add_parameter('offset', offset)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)
        # resp = key_cleanup(resp, self._user_activity_key_mapping)  # clean up
        # resp = value_cleanup(resp, 'date', self._fix_date)

        return resp


    async def _user_activity_key_mapping(self, key_name, command="get_user_activity"):
        if key_name == "createdAt":
            return "date"


    async def get_ranking(self, country=None, mode=0):
        mode = utils.mode_to_str(mode)

        if country == 'global':
            uri = 'rankings/{}/performance?'.format(mode)
        else:
            uri = 'rankings/{}/performance?country={}'.format(mode, country)

        uri = self.base.format(uri)
        resp = await self.fetch(uri)
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    # ----- beatmaps -----
    async def get_beatmaps(self, beatmap_id, 
        mods=0, converted=True, mode=0):
        uri_base = 'beatmaps/{}?'.format(beatmap_id)
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('mods', mods)
        # uri_builder.add_parameter('mode', self.mode_to_str(mode))
        # uri_builder.add_parameter('converted', int(converted))

        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        resp = key_cleanup([resp], self._get_beatmap_key_mapping)[0]  # clean up
        resp = value_cleanup([resp], 'status', self._fix_ranking_status)[0]
        resp = value_cleanup([resp], 'mode', self._fix_gamemode)[0]

        resp['beatmapset'] = key_cleanup([resp['beatmapset']], self._get_beatmapset_key_mapping)[0]
        resp['beatmapset'] = value_cleanup([resp['beatmapset']], 'status', self._fix_ranking_status)[0]
        
        resp.update(resp['beatmapset'])

        """
        if 'max_combo' in resp:
            print('API v2 resp max combo!', resp['max_combo'])"""

        del resp['beatmapset']

        # fix times/dates
        for key in resp.keys():
            if 'date' in key and resp[key] is not None:
                resp = self._fix_date(resp, key)

        return [resp]


    def _get_beatmap_key_mapping(self, key_name, command="get_beatmap"):
        if key_name == "id":
            return "beatmap_id"
        if key_name == "accuracy":
            return "od"
        if key_name == "last_updated":
            return "last_update"
        if key_name == 'diff_drain':
            return 'hp'
        if key_name == 'drain':
            return 'hp'


    async def get_beatmapset(self, beatmapset_id):
        uri_base = 'beatmapsets/{}?'.format(beatmapset_id)
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        # clean up
        # resp = key_cleanup(resp, self._get_beatmapset_key_mapping)
        # print(resp.keys())
        bmp_info = copy.deepcopy(resp)
        bmp_info['beatmapset_id'] = bmp_info['id']
        del bmp_info['beatmaps']
        del bmp_info['id']
        del bmp_info['converts']

        # for beatmap in beatmapset
        beatmap_list = []
        for bmp_list in [resp['beatmaps'], resp['converts']]:
            for beatmap in bmp_list:
                beatmap['beatmap_id'] = beatmap['id']
                del beatmap['id']
                beatmap.update(bmp_info)
                beatmap = key_cleanup([beatmap], self._get_beatmap_key_mapping)[0]  # clean up
                beatmap = value_cleanup([beatmap], 'mode', self._fix_gamemode)[0]
                beatmap = value_cleanup([beatmap], 'status', self._fix_ranking_status)[0]

                # fix times/dates
                for key in beatmap.keys():
                    if 'date' in key and beatmap[key] is not None:
                        beatmap = self._fix_date(beatmap, key)

                beatmap_list.append(beatmap)

        return beatmap_list


    def _get_beatmapset_key_mapping(self, key_name, command="get_beatmapset"):
        if key_name == "play_count":
            return "playcount"
        if key_name == "submitted_date":
            return "submit_date"
        if key_name == 'diff_drain':
            return 'hp'
        if key_name == 'drain':
            return 'hp'


    def download_beatmapset(self, beatmapset_id):
        uri_base = 'beatmapsets/{}/download'.format(beatmapset_id)
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        

    async def get_beatmap_events(self):
        uri_base = 'beatmapsets/events'
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_leaderboard(self, beatmap_id, mods=None, mode=None):
        uri_base = 'https://osu.ppy.sh/api/v2/beatmaps/{}/scores?'.format(beatmap_id)
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        # print(resp)

        # fix scores
        resp = self.fix_score_keys(resp['scores'])

        return resp


    async def beatmap_search(self, query):
        uri_base = 'https://osu.ppy.sh/api/v2/beatmapsets/search?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('q', query)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)

        for beatmapset in resp['beatmapsets']:
            beatmapset = key_cleanup([beatmapset], self._get_beatmapset_key_mapping)[0]

        return resp['beatmapsets']


    def _fix_ranking_status(self, resp, key_name):
        if resp[key_name] == 'graveyard':
            resp[key_name] = -2
        elif resp[key_name] == 'WIP':
            resp[key_name] = -1
        elif resp[key_name] == 'pending':
            resp[key_name] = 0
        elif resp[key_name] == 'ranked':
            resp[key_name] = 1
        elif resp[key_name] == 'approved':
            resp[key_name] = 2
        elif resp[key_name] == 'qualified':
            resp[key_name] = 3
        elif resp[key_name] == 'loved':
            resp[key_name] = 4

        return resp


    def _fix_gamemode(self, resp, key_name):
        if resp[key_name] == 'osu':
            resp[key_name] = 0
        elif resp[key_name] == 'taiko':
            resp[key_name] = 1
        elif resp[key_name] == 'fruits':
            resp[key_name] = 2
        elif resp[key_name] == 'mania':
            resp[key_name] = 3

        return resp


    def _fix_date(self, resp, key_name):
        dt_obj = datetime.datetime.strptime(resp[key_name], '%Y-%m-%dT%H:%M:%S+00:00')
        resp[key_name] = dt_obj.strftime('%Y-%m-%d %H:%M:%S')

        return resp


    def _fix_accuracy(self, resp, key_name):
        resp[key_name] = resp[key_name] * 100

        return resp        

    # ----- other -----

    async def get_news(self):
        uri_base = 'news'
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await self.fetch(uri)
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp        


    # ----- requests -----
    async def get_token(self, scope='public'):
        body = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": scope
        }

        uri = 'https://osu.ppy.sh/oauth/token'

        resp = await self.post(uri, body, get_token=True)

        self.token = resp['access_token']
        self.token_expire = datetime.datetime.now().timestamp() + int(resp['expires_in'])


    async def fetch(self, uri):
        print(uri)

        current_time_sec = datetime.datetime.now().timestamp()
        if not self.token or current_time_sec > self.token_expire:
            await self.get_token()

        headers = {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
              'Authorization': 'Bearer {}'.format(self.token)
        }
        # print(headers)

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(uri) as resp:
                json_body = await resp.json()
                return json_body


    async def post(self, uri, body={}, get_token=False):
        if not get_token:
            current_time_sec = datetime.datetime.now().timestamp()
            if not self.token or current_time_sec > self.token_expire:
                await self.get_token()

            headers = {
                  'Accept': 'application/json',
                  'Content-Type': 'application/json',
                  'Authorization': 'Bearer {}'.format(self.token)
                }
        else:
            headers = {
                  'Accept': 'application/json',
                  'Content-Type': 'application/json',
            }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(uri, json=body) as resp:
                json_body = await resp.json()
                return json_body        


    def key_mapping(self, key_name, command=None):
        pass


    def mode_to_str(self, mode):
        if mode == 0:
            return "osu"
        elif mode == 1:
            return "taiko"
        elif mode == 2:
            return "fruits"
        else:
            return "mania"


class gatariAPI():
    def __init__(self):
        self.name = "Gatari"
        self.base = 'https://api.gatari.pw/{}'
        self.symbol_url = 'https://i.imgur.com/0mz9A4b.png'
        self.user_url_base = 'https://osu.gatari.pw/u/{}'
        self.avatar_url = 'https://a.gatari.pw/{}' # must be id
        self.beatmap_download = 'https://osu.gatari.pw/d/{}?novideo'


    async def get_beatmaps(self, beatmap_id=None):
        uri_base = 'beatmaps/get?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('bb', beatmap_id)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = resp['data']
        resp = key_cleanup(resp, self.key_mapping)
        resp = self.fix_beatmap_keys(resp)
        
        return resp


    def fix_beatmap_keys(self, resp):
        modes = ['std','taiko','ctb','mania']
        for beatmap in resp:
            mode_txt = modes[int(beatmap['mode'])]
            beatmap['difficulty_rating'] = beatmap[f'difficulty_{mode_txt}']

            unix_time = int(beatmap['ranking_data'])
            beatmap['approved'] = 1
            beatmap['approved_date'] = datetime.datetime.utcfromtimestamp(
                unix_time).strftime('%Y-%m-%d %H:%M:%S')

        return resp


    async def get_user(self, user_id, mode=0):
        ret_json = []
        uri_base = 'users/get?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('u', user_id)
        # uri_builder.add_parameter('mode', mode)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp_user_get = resp['users']

        for user in resp_user_get:
            # combine these two
            uri_base = 'user/stats?'
            uri_builder = URIBuilder(uri_base)
            uri_builder.add_parameter('u', user['id'])
            uri_builder.add_parameter('mode', mode)
            uri = self.base.format(uri_builder.uri)

            resp_stats = await fetch(uri)
            resp_stats = resp_stats['stats']
            resp_stats['level'] = resp_stats['level'] + \
                resp_stats['level_progress']/100

            user.update(resp_stats)

            ret_json.append(user)

        # print('Gatari USER', ret_json)

        # clean up. key_cleanup expects a list.
        ret_json = key_cleanup(ret_json, self.key_mapping,
            command="get_user")

        return ret_json


    async def get_user_recent(self, user_id, mode=0, page=None, length=None, include_fail=1, pp_filter=0):
        user_info = await self.get_user(user_id, mode=0)
        user_info = user_info[0]

        uri_base = 'user/scores/recent?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('id', user_info['user_id'])
        uri_builder.add_parameter('mode', mode)
        uri_builder.add_parameter('p', page)
        uri_builder.add_parameter('l', length)
        uri_builder.add_parameter('f', include_fail)
        uri_builder.add_parameter('ppFilter', pp_filter)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp_fixed = []
        for score in resp['scores']: # bring it into the first layer
            score['beatmap_id'] = score['beatmap']['beatmap_id']

            # deal with time
            date_time_str = str(score['time']) # removes offset 2019-07-14T12:46:41+02:00
            score['time'] = self.fix_date(date_time_str)

        resp = resp['scores']
        resp = key_cleanup(resp, self.key_mapping, 
            command="get_user_recent")  # clean up
        return resp


    async def get_user_best(self, user_id, mode=0, page=1, limit=100):
        uri_base = 'user/scores/best?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('id', user_id)
        uri_builder.add_parameter('mode', mode)
        uri_builder.add_parameter('p', page)
        uri_builder.add_parameter('l', limit)
        # uri_builder.add_parameter('mods', mods)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        for score in resp['scores']: # bring it into the first layer
            score['beatmap_id'] = score['beatmap']['beatmap_id']

            # deal with time
            date_time_str = str(score['time']) # removes offset 2019-07-14T12:46:41+02:00
            score['time'] = self.fix_date(date_time_str)

        resp = resp['scores']
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_scores(self, user_id, beatmap_id, mode=0):
        uri_base = 'beatmap/user/score?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('b', beatmap_id)
        uri_builder.add_parameter('mode', mode)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        if 'score' in resp:
            resp_score = resp['score']
            if not isinstance(resp_score, list):
                resp_score = [resp['score']]
        else:
            return []

        cleaned_list = []
        for score in resp_score:
            # deal with time
            # print(score['time'])
            date_time_str = str(score['time']) # for some reason it's unix time
            score['time'] = self.fix_date(date_time_str)

            temp_score = key_cleanup([score], self.key_mapping, 
                command="get_scores")  # clean up
            cleaned_list.append(temp_score[0])

        return cleaned_list


    async def get_leaderboard(self, beatmap_id):
        uri_base = 'beatmap/'+str(beatmap_id)+'/scores?'
        uri_builder = URIBuilder(uri_base)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_pp(self, beatmap_id, acc, misses, combo, mods=0):
        uri_base = 'api/v1/pp?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('b', beatmap_id)
        uri_builder.add_parameter('a', acc)
        uri_builder.add_parameter('x', misses)
        uri_builder.add_parameter('c', combo)
        uri_builder.add_parameter('mods', mods)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    def fix_date(self, date_time_str):
        if '+02' in date_time_str:
            dt_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%S+02:00')
        else: # unix time
            dt_obj = datetime.datetime.utcfromtimestamp(int(date_time_str))
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')        


    async def is_online(self, user_id):
        user_url = self.user_url_base + str(user_id)

        # check source code for online/offline
        soup = web_utils.get_web(user_url, parser="lxml")
        web_text = str(soup).lower()
        if "online" in web_text:
            return True
        return False


    def key_mapping(self, key_name, command=None):
        if key_name == "a_count":
            return "count_rank_a"
        if key_name == "s_count":
            return "count_rank_s"
        if key_name == "sh_count":
            return "count_rank_sh"
        if key_name == "x_count":
            return "count_rank_ss"
        if key_name == "xh_count":
            return "count_rank_ssh"
        if key_name == "count_gekis":
            return "count_geki"
        if key_name == "avg_accuracy":
            return "accuracy"
        if key_name == "id":
            return "user_id"
        if key_name == "playtime":
            return "total_seconds_played"
        if key_name == "pp" and command == "get_user":
            return "pp_raw"
        if key_name == "rank" and command not in ['get_scores']:
            return "pp_rank"
        if key_name == "country_rank":
            return "pp_country_rank"
        if key_name == "difficulty":
            return "difficulty_rating"
        if key_name == "userid":
            return "user_id"
        if key_name == "mods":
            return "enabled_mods"
        if key_name == "ranking":
            return "rank"
        if key_name == "time":
            return "date"


class rippleAPI():
    def __init__(self):
        self.name = "Ripple"
        self.base = 'https://ripple.moe/api/v1/{}'
        self.symbol_url = 'https://i.imgur.com/bpPsWWH.png'
        self.user_url_base = 'https://ripple.moe/u/{}'
        self.avatar_url = 'https://a.ripple.moe/{}' # must be id
        self.websocket = 'wss://api.ripple.moe/api/v1/ws'
        self.beatmap_download = 'http://storage.ripple.moe/d/{}?novideo'
        self.ppy_api = rippleAPIpeppy()


    async def get_user(self, user_id, mode=0, alt_uri_base=None):
        if alt_uri_base is not None:
            uri_base = alt_uri_base
        else:
            uri_base = 'users/full?'
        uri_builder = URIBuilder(uri_base)
        if str(user_id).isnumeric():
            uri_builder.add_parameter('id', user_id)
        else:
            uri_builder.add_parameter('name', user_id)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        if resp['code'] != 200:
            return None
        
        new_obj = {}
        for obj_key in resp.keys():
            if obj_key in ['std', 'taiko', 'ctb', 'mania']:
                if obj_key == utils.num_to_mode(mode):
                    mode_info = resp[obj_key]
                    new_obj.update(mode_info)
            else:
                new_obj[obj_key] = resp[obj_key]

        new_obj = [new_obj] # make into list
        new_obj = key_cleanup(new_obj, self.key_mapping,
            command="get_user")  # clean up

        return new_obj


    async def get_user_detailed(self, user_id=None, user_name=None, mode=0):
        
        return await self.get_user(self, user_id=user_id, user_name=user_name, mode=mode)


    async def get_scores(self, beatmap_id, user_id, 
        mode=0, relax=0, alt_uri_base=None):
        if alt_uri_base is not None:
            uri_base = alt_uri_base
        else:
            uri_base = 'scores?'
        # uri_base = self.peppy_base + 'get_scores?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('b', beatmap_id)
        if str(user_id).isnumeric():
            uri_builder.add_parameter('userid', user_id)
        else:
            uri_builder.add_parameter('name', user_id)
        uri_builder.add_parameter('mode', mode)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        scores = resp['scores']

        if resp is None:
            return None

        cleaned_list = []
        for score in scores:

            # deal with time
            score['time'] = self.fix_date(str(score['time']))

            temp_score = key_cleanup([score], self.key_mapping, 
                command='get_scores')  # clean up

            cleaned_list.append(temp_score[0])

        # sorted list
        mod_freq = {}
        for play in cleaned_list:
            key_name = str(play['enabled_mods'])
            if key_name not in mod_freq:
                mod_freq[key_name] = play

            if mod_freq[key_name]['score'] < play['score']:
                mod_freq[key_name] = play

        # turn values into a list
        plays_list = [mod_freq[mod] for mod in mod_freq]

        # then sort
        sorted_resp = sorted(plays_list, 
            key=lambda i: i['pp'], reverse=True) 

        return sorted_resp


    async def get_user_recent(self, user_id, mode=0, alt_uri_base=None):
        if alt_uri_base is not None:
            uri_base = alt_uri_base
        else:
            uri_base = 'users/scores/recent?'
        uri_builder = URIBuilder(uri_base)
        if str(user_id).isnumeric():
            uri_builder.add_parameter('id', user_id)
        else:
            uri_builder.add_parameter('name', user_id)
        uri_builder.add_parameter('mode', mode)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = resp['scores']

        if resp is None:
            return None

        resp = self.fix_plays(resp)
        resp = key_cleanup(resp, self.key_mapping, 
            command="get_user_recent")  # clean up

        # print(resp[0])

        return resp


    async def get_user_best(self, user_id, mode=0, limit=100, alt_uri_base=None):
        if alt_uri_base is not None:
            uri_base = alt_uri_base
        else:
            uri_base = 'users/scores/best?'
        uri_builder = URIBuilder(uri_base)
        if str(user_id).isnumeric():
            uri_builder.add_parameter('id', user_id)
        else:
            uri_builder.add_parameter('name', user_id)
        uri_builder.add_parameter('mode', mode)
        uri_builder.add_parameter('l', limit)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = resp['scores']

        if resp is None:
            return None

        resp = self.fix_plays(resp)
        resp = key_cleanup(resp, self.key_mapping,
            command="get_user_best")  # clean up
        return resp


    def fix_plays(self, all_plays):
        for play in all_plays:
            play['beatmap_id'] = play['beatmap']['beatmap_id']
            play['difficulty_rating'] = play['beatmap']['difficulty']
            play['mode'] = play['play_mode']
            if 'completed' in play and \
                (not play['completed'] or \
                    play['completed'] == 0 or play['completed'] == 1):
                play['rank'] = 'F'
            else:
                play['rank'] = self._rank_mapping(str(play['rank']))
            # del play['play_mode']

            play['time'] = self.fix_date(str(play['time']))

        return all_plays


    def fix_date(self, date_time_str):
        
        if '+03:00' in date_time_str:
            # print('API +3 Time')
            dt_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%S+03:00')
            dt_obj += datetime.timedelta(hours=3) # because of +2
        elif '+02:00' in date_time_str:
            # print('API +2 Time')
            dt_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%S+02:00')
            dt_obj += datetime.timedelta(hours=2) # because of +2
        elif '+01:00' in date_time_str:
            # print('API +1 Time')
            dt_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%S+01:00')
            dt_obj += datetime.timedelta(hours=1) # because of +1
        else:
            # print('API +0 Time (Z)')
            dt_obj = datetime.datetime.strptime(date_time_str, '%Y-%m-%dT%H:%M:%SZ')        
        
        # dt_obj = datetime.datetime.fromisoformat(date_time_str) # for python 3.7+
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')


    def _rank_mapping(self, rank):
        if rank == 'SHD':
            return 'SH'
        if rank == 'SSHD':
            return 'SSH'
        return rank


    async def get_beatmaps(self, 
        beatmapset_id=None, beatmap_id=None, user_id=None, 
        mode=0, converted=0, limit=500, relax=None):
        uri_base = 'get_beatmaps?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('s', beatmapset_id)
        if str(beatmap_id).isnumeric() or len(str(beatmap_id)) <= 8:
            uri_builder.add_parameter('b', beatmap_id)
        else:
            uri_builder.add_parameter('h', beatmap_id)
        uri_builder.add_parameter('u', user_id)
        uri_builder.add_parameter('a', converted)
        uri_builder.add_parameter('limit', limit)
        uri_builder.add_parameter('relax', relax)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)

        if not resp:
            return None

        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def get_leaderboard(self, beatmap_id, mode=None, sort='score'):
        # can sort by score or pp
        uri_base = 'scores?'
        uri_builder = URIBuilder(uri_base)
        uri_builder.add_parameter('b', beatmap_id)
        uri_builder.add_parameter('mode', mode)
        uri_builder.add_parameter('sort', sort)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        resp = resp['scores']

        if resp is None:
            return None
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def is_online(self, user_id):
        user_url = self.user_url_base.format(str(user_id))

        # check source code for online/offline
        soup = web_utils.get_web(user_url, parser="lxml")
        web_text = str(soup).lower()
        if "online" in web_text:
            return True
        return False


    def key_mapping(self, key_name, command=None):
        if key_name == "global_leaderboard_rank":
            return "pp_rank"
        if key_name == "country_leaderboard_rank":
            return "pp_country_rank"
        if key_name == "pp" and command == "get_user":
            return "pp_raw"
        if key_name == "id" and command == "get_user":
            return "user_id"
        if key_name == "mods" and (
            command in ["get_user_best", "get_user_recent", "get_scores"]):
            return "enabled_mods"
        if key_name == "time":
            return "date"
        if key_name == "play_mode":
            return "mode"
        if key_name == "difficultyrating":
            return "difficulty_rating"
        if key_name == 'diff_overall':
            return "od"
        if key_name == 'diff_approach':
            return "ar"
        if key_name == 'diff_drain':
            return "hp"
        if key_name == 'diff_size':
            return "cs"
        if key_name == "approved":
            return "status"


class rippleAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__("")
        self.name = "Ripple"
        self.base = 'https://ripple.moe/api/{}'
        self.symbol_url = 'https://i.imgur.com/bpPsWWH.png'
        self.user_url_base = 'https://ripple.moe/u/{}'
        self.avatar_url = 'https://a.ripple.moe/{}' # must be id
        self.beatmap_download = 'http://storage.ripple.moe/d/{}?novideo'
        self.websocket = 'wss://api.ripple.moe/api/v1/ws'


    async def get_user_best(self, user_id, mode=0, limit=100):
        resp = await super().get_user_best(user_id, 
            mode=mode, limit=limit)

        # sort by pp
        resp = sorted(resp, 
            key=lambda play: float(play['pp']), reverse=True)
        return resp


class ripplerxAPI(rippleAPI):
    def __init__(self):
        self.name = "Ripple RX"
        self.base = 'https://ripple.moe/api/v1/{}&relax=1'
        self.symbol_url = 'https://i.imgur.com/bpPsWWH.png'
        self.user_url_base = 'https://ripple.moe/u/{}'
        self.avatar_url = 'https://a.ripple.moe/{}' # must be id
        self.beatmap_download = 'http://storage.ripple.moe/d/{}?novideo'


class akatsukiAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Akatsuki"
        self.base = 'https://akatsuki.pw/api/v1/{}'
        self.symbol_url = 'https://i.imgur.com/NjlnjCC.png'
        self.user_url_base = 'https://osu.akatsuki.pw/u/{}'
        self.avatar_url = 'https://a.akatsuki.pw/{}' # must be id
        self.beatmap_download = 'https://akatsuki.pw/d/{}?novideo'
        self.websocket = None
        self.stat_index = 0
        self.ppy_api = akatsukiAPIpeppy()

    async def get_user(self, user_id, mode=0):
        uri_base = 'users/full?'
        uri_builder = URIBuilder(uri_base)
        if str(user_id).isnumeric():
            uri_builder.add_parameter('id', user_id)
        else:
            uri_builder.add_parameter('name', user_id)
        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        try:
            resp = {**resp['stats'][self.stat_index], **resp}
        except:
            return None

        new_obj = {}
        for obj_key in resp.keys():
            if obj_key in ['std', 'taiko', 'ctb', 'mania']:
                if obj_key == utils.num_to_mode(mode):
                    mode_info = resp[obj_key]
                    new_obj.update(mode_info)
            else:
                new_obj[obj_key] = resp[obj_key]

        new_obj = [new_obj] # make into a list
        new_obj = key_cleanup(new_obj, self.key_mapping, 
            command="get_user")  # clean up 

        return new_obj


class akatsukirxAPI(akatsukiAPI):
    def __init__(self):
        super().__init__()
        self.name = "Akatsuki RX"
        self.base = 'https://akatsuki.pw/api/v1/{}&rx=1'
        self.symbol_url = 'https://i.imgur.com/NjlnjCC.png'
        self.user_url_base = 'https://osu.akatsuki.pw/u/{}'
        self.avatar_url = 'https://a.akatsuki.pw/{}' # must be id
        self.beatmap_download = 'https://akatsuki.pw/d/{}?novideo'
        self.websocket = None
        self.stat_index = 1


class akatsukiAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Akatsuki"
        self.base = 'https://akatsuki.pw/api/{}'
        self.symbol_url = 'https://i.imgur.com/NjlnjCC.png'
        self.user_url_base = 'https://osu.akatsuki.pw/u/{}'
        self.avatar_url = 'https://a.akatsuki.pw/{}' # must be id
        self.beatmap_download = 'https://akatsuki.pw/d/{}?novideo'
        self.websocket = None


class kawataAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Kawata"
        self.base = "https://kawata.pw/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/CsEOIIu.png"
        self.user_url_base = 'https://kawata.pw/u/{}'
        self.avatar_url = 'https://a.kawata.pw/{}'
        self.websocket = 'wss://kawata.pw/api/v1/ws'
        self.beatmap_download = 'http://storage.kawata.pw/d/{}?novideo'
        self.ppy_api = kawataAPIpeppy()


class kawataAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Kawata"
        self.base = "https://kawata.pw/api/{}"
        self.symbol_url = "https://i.imgur.com/CsEOIIu.png"
        self.user_url_base = 'https://kawata.pw/u/{}'
        self.avatar_url = 'https://a.kawata.pw/{}'
        self.beatmap_download = 'http://storage.kawata.pw/d/{}?novideo'
        self.websocket = 'wss://kawata.pw/api/v1/ws'


class ainuAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Ainu"
        self.base = "https://ainu.pw/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/mGeqkfA.png"
        self.user_url_base = 'https://ainu.pw/u/{}'
        self.avatar_url = 'https://a.ainu.pw/{}'
        self.beatmap_download = None
        self.websocket = None
        self.ppy_api = ainuAPIpeppy()


class ainurxAPI(rippleAPI):
    def __init__(self):
        self.name = "Ainu RX"
        self.base = 'https://ainu.pw/api/v1/{}&rx=1'
        self.symbol_url = "https://i.imgur.com/mGeqkfA.png"
        self.user_url_base = 'https://ainu.pw/u/{}'
        self.avatar_url = 'https://a.ainu.pw/{}'
        self.beatmap_download = None
        self.websocket = None


class ainuAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Aniu"
        self.base = "https://ainu.pw/api/{}"
        self.symbol_url = "https://i.imgur.com/mGeqkfA.png"
        self.user_url_base = 'https://ainu.pw/u/{}'
        self.avatar_url = 'https://a.ainu.pw/{}'
        self.beatmap_download = None
        self.websocket = None


class horizonAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Horizon"
        self.base = "https://lemres.de/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/jW89AIe.png"
        self.user_url_base = 'https://lemres.de/u/{}'
        self.avatar_url = 'https://a.lemres.de/{}'
        self.beatmap_download = 'https://lemres.de/d/{}?novideo'
        self.websocket = None
        self.ppy_api = horizonAPIpeppy()


class horizonrxAPI(rippleAPI):
    def __init__(self):
        self.name = "Horizon RX"
        self.base = 'https://lemres.de/api/v1/{}&rx=1'
        self.symbol_url = "https://i.imgur.com/jW89AIe.png"
        self.user_url_base = 'https://lemres.de/u/{}'
        self.avatar_url = 'https://a.lemres.de/{}'
        self.beatmap_download = 'https://lemres.de/d/{}?novideo'
        self.websocket = None


class horizonAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Horizon"
        self.base = "https://lemres.de/api/{}"
        self.symbol_url = "https://i.imgur.com/jW89AIe.png"
        self.user_url_base = 'https://lemres.de/u/{}'
        self.avatar_url = 'https://a.lemres.de/{}'
        self.beatmap_download = 'https://lemres.de/d/{}?novideo'
        self.websocket = None


class enjuuAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Enjuu"
        self.base = "https://enjuu.click/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/TUS3ghr.png"
        self.user_url_base = 'https://enjuu.click/u/{}'
        self.avatar_url = 'https://a.enjuu.click/{}'
        self.beatmap_download = 'https://hentai.ninja/d/{}?novideo'
        self.websocket = 'wss://enjuu.click/api/v1/ws'
        self.ppy_api = enjuuAPIpeppy()


class enjuuAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Enjuu"
        self.base = "https://enjuu.click/api/{}"
        self.symbol_url = "https://i.imgur.com/TUS3ghr.png"
        self.user_url_base = 'https://enjuu.click/u/{}'
        self.avatar_url = 'https://a.enjuu.click/{}'
        self.beatmap_download = 'https://hentai.ninja/d/{}?novideo'
        self.websocket = 'wss://enjuu.click/api/v1/ws'


class kurikkuAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Kurikku"
        self.base = "https://kurikku.pw/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/dEIR7iz.png"
        self.user_url_base = 'https://kurikku.pw/u/{}'
        self.avatar_url = 'https://a.kurikku.pw/{}'
        self.beatmap_download = 'http://storage.kurikku.pw/d/{}?novideo'
        self.websocket = 'wss://kurikku.pw/api/v1/ws'
        self.ppy_api = kurikkuAPIpeppy()


class kurikkuAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Kurikku"
        self.base = "https://kurikku.pw/api/{}"
        self.symbol_url = "https://i.imgur.com/dEIR7iz.png"
        self.user_url_base = 'https://kurikku.pw/u/{}'
        self.avatar_url = 'https://a.kurikku.pw/{}'
        self.beatmap_download = 'http://storage.kurikku.pw/d/{}?novideo'
        self.websocket = 'wss://kurikku.pw/api/v1/ws'


class datenshiAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "Datenshi"
        self.base = "https://osu.troke.id/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/Dk8LCXw.png"
        self.user_url_base = 'https://osu.troke.id/u/{}'
        self.avatar_url = 'https://a.troke.id/{}'
        self.beatmap_download = 'https://osu.troke.id/d/{}?novideo'
        self.websocket = 'wss://osu.troke.id/api/v1/ws'
        self.ppy_api = datenshiAPIpeppy()


class datenshiAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "Datenshi"
        self.base = "https://osu.troke.id/api/{}"
        self.symbol_url = "https://i.imgur.com/Dk8LCXw.png"
        self.user_url_base = 'https://osu.troke.id/u/{}'
        self.avatar_url = 'https://a.troke.id/{}'
        self.beatmap_download = 'https://osu.troke.id/d/{}?novideo'
        self.websocket = 'wss://osu.troke.id/api/v1/ws'


class ezppfarmAPI(rippleAPI):
    def __init__(self):
        super().__init__()
        self.name = "EZ PP Farm"
        self.base = "https://ez-pp.farm/api/v1/{}"
        self.symbol_url = "https://i.imgur.com/wuWzOa2.png"
        self.user_url_base = 'https://ez-pp.farm/u/{}'
        self.avatar_url = 'https://a.ez-pp.farm/{}'
        self.beatmap_download = 'https://ez-pp.farm/d/{}?novideo'
        self.websocket = 'wss://ez-pp.farm/api/v1/ws'
        self.ppy_api = ezppfarmAPIpeppy()


class ezppfarmrxAPI(rippleAPI):
    def __init__(self):
        self.name = "EZ PP Farm RX"
        self.base = 'https://ez-pp.farm/api/v1/{}'
        self.symbol_url = "https://i.imgur.com/wuWzOa2.png"
        self.user_url_base = 'https://ez-pp.farm/u/{}'
        self.avatar_url = 'https://a.ez-pp.farm/{}'
        self.beatmap_download = 'https://ez-pp.farm/d/{}?novideo'
        self.websocket = 'wss://ez-pp.farm/api/v1/ws'
        self.score_mode = 'relax'
        self.score_mode_short = 'rx'


    async def get_user(self, user_id, mode=0):
        uri_base = 'users/{}/full?'.format(self.score_mode_short)
        resp = await super().get_user(user_id, 
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_scores(self, beatmap_id, user_id, 
        mode=0):
        uri_base = '{}/scores?'.format(self.score_mode)
        resp = await super().get_scores(beatmap_id, user_id,
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_user_recent(self, user_id, mode=0):
        uri_base = 'users/scores/{}/recent?'.format(self.score_mode)

        resp = await super().get_user_recent(user_id,
            mode=mode, alt_uri_base=uri_base)

        return resp


    async def get_user_best(self, user_id, mode=0, limit=100, alt_uri_base=None):
        uri_base = 'users/scores/{}/best?'.format(self.score_mode)

        resp = await super().get_user_best(user_id,
            mode=mode, limit=limit, alt_uri_base=uri_base)

        return resp


class ezppfarmapAPI(rippleAPI):
    def __init__(self):
        self.name = "EZ PP Farm AP"
        self.base = 'https://ez-pp.farm/api/v1/{}'
        self.symbol_url = "https://i.imgur.com/wuWzOa2.png"
        self.user_url_base = 'https://ez-pp.farm/u/{}'
        self.avatar_url = 'https://a.ez-pp.farm/{}'
        self.beatmap_download = 'https://ez-pp.farm/d/{}?novideo'
        self.websocket = 'wss://ez-pp.farm/api/v1/ws'
        self.score_mode = 'autopilot'
        self.score_mode_short = 'ap'


    async def get_user(self, user_id, mode=0):
        uri_base = 'users/{}/full?'.format(self.score_mode_short)
        resp = await super().get_user(user_id, 
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_scores(self, beatmap_id, user_id, 
        mode=0):
        uri_base = '{}/scores?'.format(self.score_mode)
        resp = await super().get_scores(beatmap_id, user_id,
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_user_recent(self, user_id, mode=0):
        uri_base = 'users/scores/{}/recent?'.format(self.score_mode_short)

        resp = await super().get_user_recent(user_id,
            mode=mode, alt_uri_base=uri_base)

        return resp


    async def get_user_best(self, user_id, mode=0, limit=100, alt_uri_base=None):
        uri_base = 'users/scores/{}/best?'.format(self.score_mode_short)

        resp = await super().get_user_best(user_id,
            mode=mode, limit=limit, alt_uri_base=uri_base)

        return resp


class ezppfarmv2API(rippleAPI):
    def __init__(self):
        self.name = "EZ PP Farm v2"
        self.base = 'https://ez-pp.farm/api/v1/{}'
        self.symbol_url = "https://i.imgur.com/wuWzOa2.png"
        self.user_url_base = 'https://ez-pp.farm/u/{}'
        self.avatar_url = 'https://a.ez-pp.farm/{}'
        self.beatmap_download = 'https://ez-pp.farm/d/{}?novideo'
        self.websocket = 'wss://ez-pp.farm/api/v1/ws'
        self.score_mode = 'v2'
        self.score_mode_short = 'v2'

    async def get_user(self, user_id, mode=0):
        uri_base = 'users/{}/full?'.format(self.score_mode_short)
        resp = await super().get_user(user_id, 
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_scores(self, beatmap_id, user_id, 
        mode=0):
        uri_base = '{}/scores?'.format(self.score_mode)
        resp = await super().get_scores(beatmap_id, user_id,
            mode=mode, alt_uri_base=uri_base)
        
        return resp


    async def get_user_recent(self, user_id, mode=0):
        uri_base = 'users/scores/{}/recent?'.format(self.score_mode)

        resp = await super().get_user_recent(user_id,
            mode=mode, alt_uri_base=uri_base)

        return resp

    async def get_user_best(self, user_id, mode=0, limit=100, alt_uri_base=None):
        uri_base = 'users/scores/{}/best?'.format(self.score_mode)

        resp = await super().get_user_best(user_id,
            mode=mode, limit=limit, alt_uri_base=uri_base)

        return resp


class ezppfarmAPIpeppy(officialAPIv1):
    def __init__(self):
        super().__init__()
        self.name = "EZ PP Farm"
        self.base = "https://ez-pp.farm/api/{}"
        self.symbol_url = "https://i.imgur.com/wuWzOa2.png"
        self.user_url_base = 'https://ez-pp.farm/u/{}'
        self.avatar_url = 'https://a.ez-pp.farm/{}'
        self.beatmap_download = 'https://ez-pp.farm/d/{}?novideo'
        self.websocket = 'wss://ez-pp.farm/api/v1/ws'


class droidAPI():
    def __init__(self, api_key):
        self.name ="Droid"
        self.base = "http://ops.dgsrz.com/api/{}.php?apiKey=" + str(api_key) + '{}'
        self.symbol_url = "https://i.imgur.com/RHDIs8S.png"
        self.user_url_base = "http://ops.dgsrz.com/profile.php?uid={}" # requires id
        self.beatmap_download = None
        self.websocket = None

    async def get_avatar(self, user_id):
        # Set your variables here
        user_info = await self.get_user(user_id)
        email = user_info[0]['email'].lower().encode('utf-8')
        # default = "https://www.example.com/default.jpg"
        size = 40
         
        # construct the url
        gravatar_url = "https://www.gravatar.com/avatar/" + hashlib.md5(email).hexdigest() + "?"
        # gravatar_url += urllib.urlencode({'d':default, 's':str(size)})
        # gravatar_url += urllib.urlencode({'s':str(size)})

        return gravatar_url


    async def get_user(self, user_id, mode=0):
        # mode is note used
        uri_base = 'getuserinfo'
        uri_builder = URIBuilder('')
        if str(user_id).isnumeric():
            uri_builder.add_parameter('uid', user_id)
        else:
            uri_builder.add_parameter('username', user_id)
        uri = self.base.format(uri_base, uri_builder.uri)

        resp = await fetch(uri)

        # parse the data
        resp_dict = {}
        data_parse = resp.split('<br>')
        top_line = data_parse[0]
        top_line_split = top_line.split(' ')
        resp_dict['user_id'] = int(top_line_split[1])
        resp_dict['username'] = str(top_line_split[2])
        resp_dict['total_score'] = int(top_line_split[3])
        resp_dict['playcount'] = int(top_line_split[4])
        resp_dict['accuracy'] = float(top_line_split[5]) * 100
        resp_dict['email'] = str(top_line_split[6])
        resp_dict['country'] = str(top_line_split[7])

        bottom_info = data_parse[1]
        bottom_json = json.loads(bottom_info)
        resp_dict['pp_rank'] = bottom_json['rank']

        resp_dict = [resp_dict]

        resp = key_cleanup(resp_dict, self.key_mapping)  # clean up
        
        return resp

    """
    async def get_user_recent(self, user_id, mode=0):
        # mode is note used
        uri_base = 'getuserinfo'
        uri_builder = URIBuilder('')
        if str(user_id).isnumeric():
            uri_builder.add_parameter('uid', user_id)
        else:
            uri_builder.add_parameter('username', user_id)
        uri = self.base.format(uri_base, uri_builder.uri)

        resp = await fetch(uri)

        # parse the data
        data_parse = resp.split('<br>')
        bottom_info = data_parse[1]
        bottom_json = json.loads(bottom_info)
        resp_dict = bottom_json['recent']

        # fix all the dates
        for play in resp_dict:
            play['date'] = datetime.datetime.utcfromtimestamp(play['date']).strftime('%Y-%m-%d %H:%M:%S')

        resp = key_cleanup(resp_dict, self.key_mapping)  # clean up
        
        return resp"""

    async def score_search_v1(self, user_id, page=0):
        uri_base = 'scoresearch'
        uri_builder = URIBuilder('')
        if str(user_id).isnumeric():
            uri_builder.add_parameter('uid', user_id)
        else:
            uri_builder.add_parameter('username', user_name)
        uri_builder.add_parameter('page', page)

        uri = self.base.format(uri_builder.uri)

        resp = await fetch(uri)
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    async def score_search_v2(self, order, user_id=None, map_hash=None, page=0):
        # order entails "sid", "date", or "score"
        uri_base = 'scoresearchv2'
        uri_builder = URIBuilder('')
        if str(user_id).isnumeric():
            uri_builder.add_parameter('uid', user_id)
        else:
            uri_builder.add_parameter('username', user_id)
        uri_builder.add_parameter('order', order)
        uri_builder.add_parameter('page', page)
        uri_builder.add_parameter('hash', map_hash)

        uri = self.base.format(uri_base, uri_builder.uri)

        resp = await fetch(uri)
        resp = self.parse_score_resp(resp)
        
        resp = key_cleanup(resp, self.key_mapping)  # clean up
        return resp


    def parse_score_resp(self, resp):
        unparsed_play_list = resp.split('<br>')
        unparsed_play_list = unparsed_play_list[1:]

        scores = []
        for score_idx, score in enumerate(unparsed_play_list):
            play_json = {}
            score_parse = score.split(' ')
            play_json['id'] = score_parse[0]
            play_json['user_id'] = score_parse[1]
            play_json['username'] = score_parse[2]
            play_json['score'] = int(score_parse[3])
            play_json['max_combo'] = int(score_parse[4])
            play_json['rank'] = score_parse[5]

            play_json['enabled_mods'] = \
                self.convert_droid_mods(str(score_parse[6]))
            # if score_idx == 0:
            # print('API DROID MODS!', score_parse[6], play_json['enabled_mods'])

            play_json['accuracy'] = int(score_parse[7])/1000
            play_json['count_300'] = int(score_parse[8])
            play_json['count_100'] = int(score_parse[9])
            play_json['count_50'] = int(score_parse[10])
            play_json['count_miss'] = int(score_parse[11])
            
            unix_time = int(score_parse[12])
            play_json['date'] = self.fix_date(unix_time)
            play_json['filename'] = score_parse[13]
            play_json['beatmap_id'] = str(score_parse[-1])
            scores.append(play_json)

        # print(scores[0])

        return scores


    def fix_date(self, unix_time):
        date_obj = datetime.datetime.utcfromtimestamp(
            unix_time) + datetime.timedelta(hours=9)
        return date_obj.strftime('%Y-%m-%d %H:%M:%S')

    
    async def get_user_recent(self, user_id, mode=0, page=0):
        user = await self.get_user(user_id)
        user = user[0]
        resp = await self.score_search_v2("date", 
            user_id=user['user_id'], page=page)

        return resp


    async def get_scores(self, user_id, map_hash, page=0):
        user = await self.get_user(user_id)
        user = user[0]
        resp = await self.score_search_v2(
            "score", user_id=user_id, map_hash=map_hash, page=page)

        # obtain max of each mod combo in list
        mod_freq = {}
        for play in resp:
            key_name = str(play['enabled_mods'])
            if key_name not in mod_freq:
                mod_freq[key_name] = play

            if mod_freq[key_name]['score'] < play['score']:
                mod_freq[key_name] = play

        # turn values into a list
        plays_list = [mod_freq[mod] for mod in mod_freq]

        # then sort
        sorted_resp = sorted(plays_list, 
            key=lambda i: i['score'], reverse=True) 

        return sorted_resp


    async def get_user_best(self, user_id, page=1):
        user = await self.get_user(user_id)
        user = user[0]
        resp = await self.score_search_v2("score", 
            user_id=user['user_id'], page=page)

        # sort by score because no pp
        resp = sorted(resp, key=operator.itemgetter('score'), reverse=True)        

        return resp


    def key_mapping(self, key_name, command=None):
        if key_name == "mark":
            return "rank"
        if key_name == "combo":
            return "max_combo"   
        return key_name


    def convert_droid_mods(self, droid_mods):
        """
        Converts droid mod string to PC mod string.

        Contributed by Rian8337.
        """

        finalMods = ""

        if "a" in droid_mods: # auto
            finalMods += "at"
        if "x" in droid_mods:
            finalMods += "rx"
        if "p" in droid_mods:
            finalMods += "ap"
        if "e" in droid_mods:
            finalMods += "ez"
        if "n" in droid_mods:
            finalMods += "nf"
        if "r" in droid_mods:
            finalMods += "hr"
        if "h" in droid_mods:
            finalMods += "hd"
        if "i" in droid_mods:
            finalMods += "fl"
        if "d" in droid_mods:
            finalMods += "dt"
        if "c" in droid_mods:
            finalMods += "nc"
        if "t" in droid_mods:
            finalMods += "ht"
        if "s" in droid_mods:
            finalMods += "pr" 
        if "m" in droid_mods:
            finalMods += "sc"
        if "b" in droid_mods:
            finalMods += "su"
        if "l" in droid_mods:
            finalMods += "re"
        if "f" in droid_mods:
            finalMods += "pf"
        if "u" in droid_mods:
            finalMods += "sd"
        if "v" in droid_mods:
            finalMods += "v2"

        mod_num = utils.mod_to_num(finalMods.upper())
        return mod_num



class URIBuilder:
    def __init__(self, base):
        self.uri = base

    def add_parameter(self, key, value):
        if value is not None:
            self.uri += '&' + str(key) + '=' + str(value)


def key_cleanup(obj_list, key_mapping, command=None):
    new_obj_list = []

    for sub_obj in obj_list:
        new_sub_obj = {}
        for obj_key in sub_obj.keys():
            new_key = key_mapping(obj_key, command=command)
            if new_key:
                new_sub_obj[new_key] = sub_obj[obj_key]
            else:
                new_sub_obj[obj_key] = sub_obj[obj_key]
        new_obj_list.append(new_sub_obj)

    return new_obj_list


def value_cleanup(obj_list, key_name, value_mapping):
    for idx, sub_obj in enumerate(obj_list):
        obj_list[idx] = value_mapping(sub_obj, key_name)

    return obj_list


async def fetch(uri, session=None, timeout=20):
    # print(uri)
    timeout = aiohttp.ClientTimeout(total=timeout)
    if not session:
        async with aiohttp.ClientSession() as session:
            async with session.get(uri, timeout=timeout) as resp:
                try:
                    api_resp = await resp.json()
                except:
                    api_resp = await resp.text()

                return api_resp
    else:
        async with session.get(uri, timeout=timeout) as resp:
            try:
                api_resp = await resp.json()
            except:
                api_resp = await resp.text()
            return api_resp
