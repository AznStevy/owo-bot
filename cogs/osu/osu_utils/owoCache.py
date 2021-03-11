import os
import time
import copy
import pickle as pkl
import motor.motor_asyncio
from cogs.osu.osu_utils import map_utils

class owoCache(object):

    def __init__(self, database):
        # cache basepath
        self.cache_folderpath = os.path.join('cogs', 'osu', 'cache')
        self.beatmap_parsed_folderpath = os.path.join(
            self.cache_folderpath, 'beatmap_parsed')
        self.create_folders()

        # initialize different cache databases
        self.beatmap_parsed = CacheBeatmapFile(
            database, 'cached_beatmap_parsed', 
            self.beatmap_parsed_folderpath)

        self.beatmap = CacheBeatmap(database, 'cached_beatmap')
        self.beatmapset = CacheBeatmap(database, 'cached_beatmapset')
        self.beatmap_chunks = CacheBeatmap(database, 'cached_beatmap_chunks')
        self.beatmap_osu_file = CacheBeatmap(database, 'cached_beatmap_osu_file')

        self.leaderboard = Cache(database, 'cached_beatmap_leaderboard', 5*60)
        self.user = Cache(database, 'cached_user', 5*60) # 2*60
        self.user_best = Cache(database, 'cached_user_best', 2*60) # 2 * 60
        self.user_nc_best = Cache(database, 'cached_user_nc_best', 2*60) # 2 * 60
        self.user_recent = Cache(database, 'cached_user_recent', 60) # 1 * 60
        self.user_recent_activity = Cache(database, 'cached_user_recent_activity', 3*60) # 1 * 60
        self.user_stats = Cache(database, 'cached_user_stats', 7*24*60) # 1 * 60
        self.user_score = Cache(database, 'cached_user_score', 5*60) # 5 * 60


    def create_folders(self):
        folders = [
            self.cache_folderpath,
            self.beatmap_parsed_folderpath
        ]

        for folder in folders:
            if not os.path.exists(folder):
                os.makedirs(folder)


class Cache:
    def __init__(self, database, name, time):
        self.database = database
        self.name = name
        self.entries = self.database[self.name]
        self.time = time # in sections to expire

    async def get(self, query, force=False, include_time=False):
        # await self.entries.delete_many({}) # testing
        # db_query = self._get_db_query(query)
        # print(db_query)
        data = await self.entries.find_one(query)

        if data is None:
            return self._get_none_response(force, include_time)

        cache_valid = True
        elapsed_time = time.time() - float(data['cached_date']) # seconds
        if elapsed_time > self.time:
            cache_valid = False

        if force:
            if include_time:
                return data['data'], data['cached_date'], cache_valid
            else:
                return data['data'], cache_valid

        if not cache_valid:
            return self._get_none_response(force, include_time)

        # print('Using Cache')

        if include_time:
            return data['data'], data['cached_date']
        else:
            return data['data']

    def _get_none_response(self, force, include_time):
        if force:
            if include_time:
                return None, None, False
            else:
                return None, False
        else:
            if include_time:
                return None, None
            else:
                return None

    async def cache(self, identifiers, data):
        # print('Caching at time', time.time())
        cache_obj = copy.deepcopy(identifiers)
        cache_obj['cached_date'] = time.time()
        cache_obj['data'] = data

        # print('To cache', cache_obj)
        db_query = self._get_db_query(identifiers)

        # print("Cached")
        """
        await self.entries.replace_one(
            db_query, cache_obj, upsert=True)"""
        await self.entries.update_many(
            db_query, {"$set": cache_obj}, upsert=True)

    def _get_db_query(self, query):
        db_query = {}
        for key in query:
            db_query[key] = {"$eq": query[key]}

        return db_query


class CacheBeatmap(Cache):
    def __init__(self, database, name):
        super().__init__(database, name, None)

    async def get(self, query, force=False, include_time=False):

        data = await self.entries.find_one(query)

        if data is None:
            return self._get_none_response(force, include_time)

        cache_valid = True
        elapsed_time = time.time() - float(data['cached_date']) # seconds
        if isinstance(data['data'], list):
            if 'approved' in data['data'][0]:
                if elapsed_time > self._beatmap_cache_timeout(data['data'][0]['approved']):
                    cache_valid = False
            else:
                if elapsed_time > self._beatmap_cache_timeout(data['data'][0]['status']):
                    cache_valid = False
        else:
            if 'approved' in data['data']:
                if elapsed_time > self._beatmap_cache_timeout(data['data']['approved']):
                    cache_valid = False     
            else:
                if elapsed_time > self._beatmap_cache_timeout(data['data']['status']):
                    cache_valid = False            

        if force:
            if include_time:
                return data['data'], data['cached_date'], cache_valid
            else:
                return data['data'], cache_valid

        if not cache_valid:
            return self._get_none_response(force, include_time) 

        # print('Using Cache (Beatmap)')
        if include_time:
            return data['data'], data['cached_date']
        else:
            return data['data']

    def _beatmap_cache_timeout(self, status):
        status = int(self.handle_status(status))
        # return 10 # 1 second for testing
        
        if status in [1, 2, 4]:
            return 6 * 30 * 24 * 3600   # 6 month for ranked
        elif status in [3]:
            return 24 * 3600            # 1 day for qualified
        elif status in [-2]:          
            return 6 * 30 * 24 * 3600   # 6 month for graveyard
        else:
            return 5*60                 # 5 minutes for WIP/Pending

    def handle_status(self, status):
        is_int = False
        try:
            status = int(status)
            is_int = True
        except ValueError:
            status = status.lower()

        if is_int:
            return status
        elif status == 'graveyard': # graveyard, red
            return -2
        elif status == 'work in progress' or status == 'wip': # WIP, purple
            return -1
        elif status == 'pending': # pending, blue
            return 0
        elif status == 'ranked': # ranked, bright green
            return 1
        elif status == 'approved': # approved, dark green
            return 2
        elif status == 'qualified': # qualified, turqoise
            return 3
        elif status == 'loved': # loved, pink
            return 4


class CacheBeatmapFile(CacheBeatmap):
    def __init__(self, database, name, folderpath):
        super().__init__(database, name)
        self.folderpath = folderpath

    async def get(self, query, force=False, include_time=False):

        data = await self.entries.find_one(query)

        if data is None:
            return self._get_none_response(force, include_time)

        cache_valid = True
        elapsed_time = time.time() - float(data['cached_date']) # seconds
        if elapsed_time > self._beatmap_cache_timeout(data['data']['status']):
            cache_valid = False

        if force:
            if include_time:
                return data['data']['filepath'], data['cached_date'], cache_valid
            else:
                return data['data']['filepath'], cache_valid

        if not cache_valid:
            return self._get_none_response(force, include_time)

        # print('Using Cache (Beatmap)')
        if include_time:
            return data['data']['filepath'], data['cached_date']
        else:
            return data['data']['filepath']

    async def cache(self, identifiers, data, beatmap_info):
        # print('Caching Beatmap File')
        beatmap_id = str(beatmap_info['beatmap_id'])
        cache_obj = copy.deepcopy(identifiers)
        cache_obj['cached_date'] = float(time.time())
        cache_obj['data'] = {}
        try:
            cache_obj['data']['status'] = int(beatmap_info['status'])
        except:
            cache_obj['data']['status'] = 1 # default to 1 cause i don't care
        cache_obj['data']['filepath'] = os.path.join(
            self.folderpath, '{}.pkl'.format(beatmap_id))

        # print('Caching Time', time.time())

        with open(cache_obj['data']['filepath'], 'wb') as pickle_file:
            pkl.dump(data, pickle_file)

        # print('To cache', cache_obj)
        db_query = self._get_db_query(identifiers)
        """
        await self.entries.replace_one(
            db_query, cache_obj, upsert=True)"""
        await self.entries.update_many(
            db_query, {"$set": cache_obj}, upsert=True)