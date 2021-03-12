import os
import re
import sys
import copy
import json
import time
import math
import urllib
import random
import discord
import aiohttp
import asyncio
import logging
import pyttanko
import datetime
import operator
import requests
import importlib
import pytesseract
import collections
import numpy as np
from PIL import Image
from threading import Thread
from collections import deque
from iso3166 import countries

import motor.motor_asyncio

from discord.utils import find
from discord.ext import commands

from utils import checks
from utils.dataIO import dataIO, fileIO
from utils.option_parser import OptionParser
from cogs.osu.beatmap_parser import beatmap_parser
from cogs.osu.replay_parser.replay import parse_replay_file
from cogs.osu.osu_utils.owoAPI import owoAPI
from cogs.osu.osu_utils import map_utils, utils, web_utils, drawing
# import https://xkcd.com/353/

class Osu(commands.Cog):
    """Cog to give osu! stats for all gamemodes."""
    def __init__(self, bot):
        self.bot = bot

        # cog settings for the server
        self.server_settings = self.bot.db["osu"]
        # separate database for osu
        client = motor.motor_asyncio.AsyncIOMotorClient(
            port=self.bot.config['database']['primary'],
            connectTimeoutMS=30000, 
            socketTimeoutMS=360000, 
            serverSelectionTimeoutMS=30000)
        self.osu_db = client['owo_database'] # overall database
        self.players = self.osu_db['players']   # user settings
        self.map_track = self.osu_db['map_track'] # map feed settings
        self.irc_commands = self.osu_db['irc_commands'] # broadcast to irc

        # tracking db
        self.track = self.osu_db['track'] # tracked users
        self.track_country = self.osu_db['track_settings'] # tracking server settings

        # recommendation db
        self.rec_std    = self.osu_db['suggest_std']
        self.rec_taiko  = self.osu_db['suggest_taiko']
        self.rec_ctb    = self.osu_db['suggest_ctb']
        self.rec_mania  = self.osu_db['suggest_mania']

        # API Keys
        api_keys = self.bot.config["API_KEYS"]
        official_key = api_keys['OSU']['OFFICIAL']['KEY']
        client_id = api_keys['OSU']['OFFICIAL']['CLIENT_ID']
        client_secret = api_keys['OSU']['OFFICIAL']['CLIENT_SECRET']
        droid_key = api_keys['OSU']['DROID']['KEY']
        beatconnect_key = api_keys['OSU']['BEATCONNECT']['KEY']
        self.owoAPI = owoAPI(
            official_api_key=official_key,
            droid_api_key=droid_key,
            beatconnect_api_key=beatconnect_key,
            official_client_id=client_id,
            official_client_secret=client_secret,
            database=self.osu_db)

        # constants
        self.MODES = ["osu", "taiko", "ctb", "mania"]
        self.RANK_EMOTES = fileIO("cogs/osu/resources/rank_emotes.json", "load")
        self.DIFF_EMOTES = fileIO("cogs/osu/resources/diff_emotes.json", "load")
        self.TRACK_LIMIT = 200
        self.NUM_MAX_PROF = 8
        self.MAX_USER_DISP = 5
        self.LIST_MAX = 5
        self.MAX_MAP_DISP = 3
        self.SLEEP_TIME = 0.1 # so we don't get ratelimited
        self.LB_MAX = 15
        self.LINK_COOLDOWN = 5 # seconds

        # tools
        self.replay_parser = parse_replay_file
        self.beatmap_parser = beatmap_parser.BeatmapParser()

        # misc variables
        self.server_link_cooldown = {}


    def reimport(self):
        import_list = []
        beatmap_parser = importlib.import_module('cogs.osu.beatmap_parser.beatmap_parser')
        importlib.reload(beatmap_parser)
        map_utils = importlib.import_module('cogs.osu.osu_utils.map_utils')
        importlib.reload(map_utils)
        utils = importlib.import_module('cogs.osu.osu_utils.utils')
        importlib.reload(utils)
        web_utils = importlib.import_module('cogs.osu.osu_utils.web_utils')
        importlib.reload(web_utils)
        drawing = importlib.import_module('cogs.osu.osu_utils.drawing')
        importlib.reload(drawing)
        owoapi_module = importlib.import_module('cogs.osu.osu_utils.owoAPI')
        importlib.reload(owoapi_module)
        owoAPI = getattr(owoapi_module, 'owoAPI')

        print("Dependencies imported.")


    # define servers
    def server_option_parser(self, inputs):
        # define option parser
        option_parser = OptionParser()
        option_parser.add_option('bancho',      'bancho',       opt_type=None, default=False)
        option_parser.add_option('ripple',      'ripple',       opt_type=None, default=False)
        option_parser.add_option('ripplerx',    'ripplerx',     opt_type=None, default=False)
        option_parser.add_option('gatari',      'gatari',       opt_type=None, default=False)
        option_parser.add_option('akatsuki',    'akatsuki',     opt_type=None, default=False)
        option_parser.add_option('akatsukirx',  'akatsukirx',   opt_type=None, default=False)
        option_parser.add_option('droid',       'droid',        opt_type=None, default=False)
        option_parser.add_option('kawata',      'kawata',       opt_type=None, default=False)
        option_parser.add_option('ainu',        'ainu',         opt_type=None, default=False)
        option_parser.add_option('ainurx',      'ainurx',       opt_type=None, default=False)
        option_parser.add_option('horizon',     'horizon',      opt_type=None, default=False)
        option_parser.add_option('horizonrx',   'horizonrx',    opt_type=None, default=False)
        option_parser.add_option('enjuu',       'enjuu',        opt_type=None, default=False)
        option_parser.add_option('kurikku',     'kurikku',      opt_type=None, default=False)
        option_parser.add_option('datenshi',    'datenshi',     opt_type=None, default=False)
        option_parser.add_option('ezpp',        'ezppfarm',     opt_type=None, default=False)
        option_parser.add_option('ezpprx',      'ezppfarmrx',   opt_type=None, default=False)
        option_parser.add_option('ezppap',      'ezppfarmap',   opt_type=None, default=False)
        option_parser.add_option('ezppv2',      'ezppfarmv2',   opt_type=None, default=False)
        outputs, options = option_parser.parse(inputs)
        return outputs, options


    # ---------------------------------- osuset ----------------------------------------
    @commands.group(pass_context=True)
    async def osuset(self, ctx):
        """Define some user settings."""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return


    @commands.cooldown(1, 5, commands.BucketType.user)
    @osuset.command(name = "user", no_pm=True)
    async def set_user(self, ctx, *inputs):
        """Set your osu username. Supports other servers.

        [Options]
        username: Your in game username. Use quotes if there's a space.
        Server (-{server name}): <osu_servers> 

        [Example]
        +osuset <COMMAND> Cookiezi
        """

        if not inputs:
            await self.bot.send_cmd_help(ctx)
            return

        # include option parser
        # print('SET USER', inputs)
        username, options = self.server_option_parser(inputs)
        await self.process_set_user(ctx, username[0], options)


    def determine_api(self, api_options, db_user=None):
        # takes in a dictionary of option flags. will return
        api = None
        for api in api_options.keys():
            if api != "page" and api_options[api] == True:
                return api

        # print('DETERMINE API', db_user)
        if db_user is not None and 'default_api' in db_user:
            return db_user['default_api']

        # otherwise, assume it's bancho
        return "bancho"

    def remove_api_suffix(self, api_name):
        cleaned_api = api_name.replace('rx', '').replace('ap', '').replace('v2', '')
        return cleaned_api


    async def process_set_user(self, ctx, username, options):
        user = ctx.message.author
        channel = ctx.message.channel
        server = ctx.message.guild

        # update server info
        await self.update_user_servers_list(user, server)

        api = self.determine_api(options)
        api = self.remove_api_suffix(api) # remove the rx from any api names

        if username == 'NONE':
            # update information with new
            await self.players.update_one({'user_id': str(user.id)}, {
                '$set':{
                    "{}_user_id".format(api): None,
                    "{}_username".format(api): None
                }})

            # give confirmation
            return await ctx.send(":white_check_mark: **{}, your `{}` username has been removed.**".format(
                user.name, self.owoAPI.get_server_name(api)))

        gamemodes = [0, 1, 2, 3] # ensure that the user can link his/her account
        osu_user = None
        for gamemode in gamemodes:
            osu_user = await self.owoAPI.get_user(username, mode=gamemode, api=api)
            if osu_user:
                break
            await asyncio.sleep(.5)

        if not osu_user:
            return await ctx.send("**`{}` doesn't exist in the `{}` database.**".format(
                username, self.owoAPI.get_server_name(api)))

        # check if the user exists at all in the database
        if not await self.check_user_exists(user):
            await self.create_new_user(user, osu_user[0], api=api)
            # give confirmation
            await ctx.send(":white_check_mark: **{}, your account has been linked to `{}` on the `{}` server.**".format(
                user.name, osu_user[0]["username"], self.owoAPI.get_server_name(api)))
        else:
            # update information with new
            try:
                updated_json = {
                        "{}_user_id".format(api): osu_user[0]["user_id"],
                        "{}_username".format(api): username
                    }
            except:
                return await ctx.send("**`{}` doesn't exist in the `{}` database.**".format(
                    username, self.owoAPI.get_server_name(api)))                

            if api == 'bancho':
                if 'discord' in osu_user[0].keys():
                    user_discrim_str = "{0.name}#{0.discriminator}".format(user)
                    if osu_user[0]['discord'] == user_discrim_str:
                        updated_json['{}_verified'.format(api)] = True
                    else:
                        updated_json['{}_verified'.format(api)] = False
                else:
                    updated_json['{}_verified'.format(api)] = False

            await self.players.update_one({'user_id': str(user.id)}, 
                {'$set':updated_json})

            # give confirmation
            await ctx.send(":white_check_mark: **{}, your `{}` username has been edited to `{}`**".format(
                user.name, self.owoAPI.get_server_name(api), osu_user[0]["username"]))


    # Checks if user exists
    async def check_user_exists(self, user):
        find_user = await self.players.find_one({"user_id":str(user.id)})
        
        if not find_user:
            return False
        return True


    async def create_new_user(self, user, osu_user, api='bancho'):
        newuser = {
            "discord_username": user.name,
            "default_gamemode": 0,
            "default_api": 'bancho',
            "user_id": str(user.id),
            "farm": 8,
            "skin": None,
            "servers": []
        }
        api = self.remove_api_suffix(api)

        # insert new user
        newuser["{}_user_id".format(api)] = str(osu_user["user_id"])
        newuser["{}_username".format(api)] = str(osu_user["username"])

        if api == 'bancho':
            if 'discord' in osu_user.keys():
                user_discrim_str = "{0.name}#{0.discriminator}".format(user)
                if osu_user['discord'] == user_discrim_str:
                    newuser['{}_verifed'.format(api)] = True
                else:
                    newuser['{}_verifed'.format(api)] = True
            else:
                newuser['{}_verifed'.format(api)] = False

        await self.players.insert_one(newuser)

    @commands.cooldown(1, 5, commands.BucketType.user)    
    @osuset.command(name = "farm", no_pm=True)
    async def set_farm(self, ctx, farm_rating:int):
        """Set the default farm rating of your recommendations.

        [Options]
        farm_rating: The farm rating. (0-10)

        [Example]
        +osuset <COMMAND> 7
        """
        user = ctx.message.author
        user_set = await self.players.find_one({'user_id':str(user.id)})

        try:
            farm_rating = int(farm_rating)
            if farm_rating > 10:
                farm_rating = 10
            elif farm_rating < 0:
                farm_rating = 0
        except:
            return await ctx.send("**Please enter a valid farm rating!**")

        if user_set:
            await self.players.update_one({'user_id':str(user.id)},
                {'$set':{"farm": farm_rating}})
            await ctx.send(
                ":white_check_mark: **`{}`'s farm rating has been set to `{}`.**".format(user.name, farm_rating))
        else:
            await ctx.send('**To set a farm rating, please first link your account using `>osuset user "your username"`.**')


    @commands.cooldown(1, 5, commands.BucketType.user)
    @osuset.command(name = "skin", no_pm=True)
    async def set_skin(self, ctx, link:str):
        """Set the skin that you're currently playing with.

        [Options]
        link: Link to your skin.
        Find (-f): Attempts to find your skin from your user profile.

        [Example]
        +<COMMAND> https://ndb.moe/cxr
        """
        user = ctx.message.author
        user_set = await self.players.find_one({'user_id':str(user.id)})
        if user_set:
            await self.players.update_one({'user_id':str(user.id)},
                {'$set':{"skin": link}})
            await ctx.send(
                ":white_check_mark: **`{}`'s skin has been set to `{}`.**".format(user.name, link))
        else:
            await ctx.send('**To set a skin, please first link your account using `>osuset user "your username"`.**')


    @commands.cooldown(1, 5, commands.BucketType.user)
    @osuset.command(name="gamemode", no_pm=True)
    async def set_gamemode(self, ctx, mode:str):
        """Set your default gamemode.

        [Options]
        mode: 0 = std, 1 = taiko, 2 = ctb, 3 = mania

        [Example]
        +osuset <COMMAND> taiko
        """
        user = ctx.message.author
        server = ctx.message.guild

        try:
            if mode.lower() in self.MODES:
                gamemode = self.MODES.index(mode.lower())
            elif int(mode) >= 0 and int(mode) <= 3:
                gamemode = int(mode)
            else:
                return await ctx.send(
                    "**Please view `>h osuset gamemode` for valid modes.**")
        except:
            return await ctx.send(
                "**Please view `>h osuset gamemode` for valid modes.**")
            

        user_set = await self.players.find_one({'user_id':str(user.id)})
        if user_set:
            await self.players.update_one({'user_id':str(user.id)},
                {'$set':{"default_gamemode": int(gamemode)}})
            await ctx.send(":white_check_mark: **`{}`'s default gamemode has been set to `{}`.**".format(
                user.name, self.MODES[gamemode]))
        else:
            await ctx.send('**To set a gamemode, please first link your account using `>osuset user "your username"`.**')


    @commands.cooldown(1, 5, commands.BucketType.user)
    @osuset.command(name="server", no_pm=True)
    async def set_server(self, ctx, *, server_name):
        """Set your default game server.

        [Options]
        Server:  <osu_servers> 

        [Example]
        +osuset <COMMAND> taiko
        """
        user = ctx.message.author
        server = ctx.message.guild

        # print('SERVER NAME 1', server_name)
        if not server_name.startswith('-'):
            server_name = '-{}'.format(server_name)
        # print('SERVER NAME 2', server_name)

        _, server_options = self.server_option_parser(('', server_name))
        # print(server_options)
        api = self.determine_api(server_options)
        # print(api)

        user_set = await self.players.find_one({'user_id':str(user.id)})
        if user_set:
            await self.players.update_one({'user_id':str(user.id)},
                {'$set':{"default_api": api}})
            await ctx.send(":white_check_mark: **`{}`'s default server has been set to `{}`.**".format(
                user.name, self.owoAPI.get_server_name(api)))
        else:
            await ctx.send('**To set a server, please first link your account using `>osuset user "your username"`.**')


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, aliases=['std'])
    async def osu(self, ctx, *username):

        """
        Get an osu profile.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Image (-im): Generates a image signature for the player. (no param)
        Detailed (-d): Get more information about the user. (no param)
        Statistics (-s): Calculate statistics on the user. (no param)
        User (-u): Ignore discord users with same username. (no param)

        [Example]
        +<COMMAND> <USER> -d
        """
        await self.process_user_info(ctx, username, 0)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, alises = ["ot","st"])
    async def osutop(self, ctx, *username):
        """
        Get user's top osu standard plays.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Accuracy (-acc): Sort by accuracy.
        Combo (-c): Sort by max combo.
        Greater than (-g): Check how many plays are greater than a certain pp. (float)
        Play index (-i): Get specific play number from recents. (1-100)
        Image (-im): Generates score image of play. Must include index -i #. (no param)
        No-Choke (-nc): Calculates no-choke pp for a player's top 100. (no param)
        Mods (-m): Filter by plays with included mods. (str)
        Exclusive Mods (-mx): Filter by plays with exact mods. (str)
        Page (-p): Get another page of the list. (int)
        Reverse (-rev): Reverse the order of the list. (no param)
        Rank (-rk): Sort by rank achieved on map. (no param)
        Recent Plays (-r): Gets 5 most recent plays in top 100. (no param)
        Score (-sc): Sort by score achieved on map. (no param)
        Search (-?): Search for title in top scores. Must be in quotes. (str)
        Ten (-10): Display top 10 in a condensed list. (no param)
        User (-u): Ignore discord users with same username. (no param)
        What If (-wif): Calculate pp totals with a hypothetical play. (float)

        [Example]
        +<COMMAND> <USER>
        """

        await self.process_user_top(ctx, username, 0)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def taiko(self, ctx, *username):
        """
        Get an taiko profile.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Image (-im): Generates a image signature for the player. (no param)
        Detailed (-d): Get more information about the user. (no param)
        Statistics (-s): Calculate statistics on the user. (no param)
        User (-u): Ignore discord users with same username. (no param)

        [Example]
        +<COMMAND> <USER> -d
        """
        await self.process_user_info(ctx, username, 1)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, alises = ["tt"])
    async def taikotop(self, ctx, *username):
        """
        Get user's top taiko plays.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Accuracy (-acc): Sort by accuracy.
        Combo (-c): Sort by max combo.
        Greater than (-g): Check how many plays are greater than a certain pp. (float)
        Play index (-i): Get specific play number from recents. (1-100)
        Image (-im): Generates score image of play. Must include index -i #. (no param)
        Mods (-m): Filter by plays with included mods. (str)
        Exclusive Mods (-mx): Filter by plays with exact mods. (str)
        Page (-p): Get another page of the list. (int)
        Reverse (-rev): Reverse the order of the list. (no param)
        Rank (-rk): Sort by rank achieved on map. (no param)
        Recent Plays (-r): Gets 5 most recent plays in top 100. (no param)
        Score (-sc): Sort by score achieved on map. (no param)
        Search (-?): Search for title in top scores. Must be in quotes. (str)
        Ten (-10): Display top 10 in a condensed list. (no param)
        User (-u): Ignore discord users with same username. (no param)
        What If (-wif): Calculate pp totals with a hypothetical play. (float)

        [Example]
        +<COMMAND> <USER>
        """
        await self.process_user_top(ctx, username, 1)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, alises = ["catch"])
    async def ctb(self, ctx, *username):
        """
        Get a ctb profile.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers>
        Image (-im): Generates a image signature for the player. (no param)
        Detailed (-d): Get more information about the user. (no param)
        Statistics (-s): Calculate statistics on the user. (no param)
        User (-u): Ignore discord users with same username. (no param)

        [Example]
        +<COMMAND> <USER> -d
        """
        await self.process_user_info(ctx, username, 2)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, alises = ["ct"])
    async def ctbtop(self, ctx, *username):
        """
        Get user's top ctb plays.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Accuracy (-acc): Sort by accuracy.
        Combo (-c): Sort by max combo.
        Greater than (-g): Check how many plays are greater than a certain pp. (float)
        Play index (-i): Get specific play number from recents. (1-100)
        Image (-im): Generates score image of play. Must include index -i #. (no param)
        Mods (-m): Filter by plays with included mods. (str)
        Exclusive Mods (-mx): Filter by plays with exact mods. (str)
        Page (-p): Get another page of the list. (int)
        Reverse (-rev): Reverse the order of the list. (no param)
        Rank (-rk): Sort by rank achieved on map. (no param)
        Recent Plays (-r): Gets 5 most recent plays in top 100. (no param)
        Score (-sc): Sort by score achieved on map. (no param)
        Search (-?): Search for title in top scores. Must be in quotes. (str)
        Ten (-10): Display top 10 in a condensed list. (no param)
        User (-u): Ignore discord users with same username. (no param)
        What If (-wif): Calculate pp totals with a hypothetical play. (float)

        [Example]
        +<COMMAND> <USER>
        """
        await self.process_user_top(ctx, username, 2)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def mania(self, ctx, *username):

        """
        Get a mania profile.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Image (-im): Generates a image signature for the player. (no param)
        Detailed (-d): Get more information about the user. (no param)
        Statistics (-s): Calculate statistics on the user. (no param)
        User (-u): Ignore discord users with same username. (no param)

        [Example]
        +<COMMAND> <USER> -d
        """

        await self.process_user_info(ctx, username, 3)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, alises = ["mt","mtop"])
    async def maniatop(self, ctx, *username):
        """
        Get user's top mania plays.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Accuracy (-acc): Sort by accuracy.
        Combo (-c): Sort by max combo.
        Greater than (-g): Check how many plays are greater than a certain pp. (float)
        Play index (-i): Get specific play number from recents. (1-100)
        Image (-im): Generates score image of play. Must include index -i #. (no param)
        Mods (-m): Filter by plays with included mods. (str)
        Exclusive Mods (-mx): Filter by plays with exact mods. (str)
        Page (-p): Get another page of the list. (int)
        Reverse (-rev): Reverse the order of the list. (no param)
        Rank (-rk): Sort by rank achieved on map. (no param)
        Recent Plays (-r): Gets 5 most recent plays in top 100. (no param)
        Score (-sc): Sort by score achieved on map. (no param)
        Search (-?): Search for title in top scores. Must be in quotes. (str)
        Ten (-10): Display top 10 in a condensed list. (no param)
        User (-u): Ignore discord users with same username. (no param)
        What If (-wif): Calculate pp totals with a hypothetical play. (float)

        [Example]
        +<COMMAND> <USER>
        """
        await self.process_user_top(ctx, username, 3)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, aliases = ["rs", "newplay"])
    async def recent(self, ctx, *username):
        """
        Get user's most recent plays. Mode defaults to set default gamemode.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Recent best (-b): Gets most recent score in top 100. (no param)
        Graph (-g): Get a completion graph of your play. Only if failed. (no param)
        Play index (-i): Get specific play number from recents. (1-50)
        Image (-im): Generates score image of play. (no param)
        List (-l): List 5 most recent plays. (no param)
        Mode (-m) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania (int or tag)
        Now Playing (-np): Get currently playing. Must have discord presence enabled. (no param)
        Page (-p): Get another page of the list. (int)
        Pass only (-ps): Filter pass-only scores. (no param)
        Search (-?): Search by map name. Will grab first match. (str)
        User (-u): Ignore discord users with same username. (no param)

        [Example]
        +<COMMAND> <USER> -b -ripple
        """

        await self.process_user_recent(ctx, username)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(pass_context=True, aliases = ["sc", "score"])
    async def scores(self, ctx, *inputs):
        """
        Get a user's score, given a map link. Defaults to linked username.

        [Options]
        Map link: Supports old or new link + converts. Must be from official site.
        Username: username of the player.
        Server (-{server name}):  <osu_servers> 
        Play index (-i): Get specific play number from all scores on map. (int)
        Image (-im): Generates score image of play. (no param)
        Mode (-m) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania. For converts. (int or tag)
        Exclusive Mods (-mx): Filter by plays with exact mods. (str)
        Search (-?): Search score by map name. Will grab first match. Quotes required. (str)

        [Example]
        +<COMMAND> https://osu.ppy.sh/beatmapsets/346591/#osu/765017 <USER>
        """

        input_str_username = str('!'.join(inputs)) # for ! usernames only

        input_str = str(' '.join(inputs)) # for maps
        osu_urls = [url for url, mods in self.find_osu_urls(input_str)]
        osu_urls_str = ' '.join(osu_urls)

        # clean up inputs
        for url in osu_urls:
            input_str_username = input_str_username.replace(url, '')
        input_str_username = input_str_username.strip()

        if not input_str_username:
            username = []
        else:
            username = input_str_username.split('!')
            username = [uname for uname in username if uname] # remove things with nothing

        beatmapset_id, beatmap_id, map_gamemode = self._url_to_bmapid(osu_urls_str)
        score_id = self._url_to_score_id(osu_urls_str)

        if not (beatmap_id or beatmapset_id or score_id) and '-?' not in inputs:
            return await ctx.send("There needs to be a proper beatmap link")

        # print(username, osu_urls, beatmapset_id, beatmap_id, score_id, map_gamemode)

        await self.process_user_score(ctx, username, 
            beatmapset_id=beatmapset_id,
            beatmap_id=beatmap_id,
            score_id=score_id,
            map_gamemode=map_gamemode)

    
    def _url_to_score_id(self, url:str):
        score_id = None
        if url.find('https://osu.ppy.sh/scores/') != -1:
            is_score = True
            score_id = url.replace('https://osu.ppy.sh/scores/','')
        return score_id


    def _url_to_bmapid(self, url:str):
        map_gamemode = None
        beatmapset_id = None
        beatmap_id = None

        if url.find('https://osu.ppy.sh/s/') != -1:
            beatmapset_id = url.replace('https://osu.ppy.sh/s/','')
        elif url.find('https://osu.ppy.sh/b/') != -1:
            beatmap_id = url.replace('https://osu.ppy.sh/b/','')
        elif url.find('https://osu.ppy.sh/beatmapsets/') != -1:
            # https://osu.ppy.sh/beatmapsets/332952#osu/737025
            # for sake of consistency
            if not url.endswith('/'):
                url += '/'
            if "#" in url and "/#" not in url:
                url = url.replace("#","/#")

            after_beatmapset = url[int(url.rfind('beatmapsets')):]
            link_elements = after_beatmapset.split('/')
            # print(link_elements)
            if len(link_elements) == 3 or len(link_elements) == 4:
                beatmapset_id = link_elements[1]
                map_gamemode = utils.mode_to_num(link_elements[2])
            elif len(link_elements) == 5:
                beatmapset_id = link_elements[1]
                map_gamemode = utils.mode_to_num(link_elements[2])
                beatmap_id = link_elements[3]

        return beatmapset_id, beatmap_id, map_gamemode

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases = ['comp','cmp','c'])
    async def compare(self, ctx, *inputs:str):
        """
        Compare your score to a recent map/score card.

        [Options]
        Username: username of the player.
        Server (-{server name}): <osu_servers> 
        Play index (-i): Get specific play number from all scores on map. (int)
        Image (-im): Generates score image of play. (no param)
        Mode (-m #) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania. (int or tag)
        Search (-?): Search discord chat for recently referenced beatmap. Quotes required. (str)

        [Example]
        +<COMMAND> <USER>
        """
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        db_user = await self.get_user(user)

        # og_inputs = copy.deepcopy(inputs)
        inputs, cmd_gamemode = self._gamemode_option_parser(inputs) # map gamemode might not be the same
        # print('GAMEMODE 1', cmd_gamemode)
        outputs, server_options = self.server_option_parser(inputs)
        api = self.determine_api(server_options, db_user=db_user)

        option_parser = OptionParser()
        option_parser.add_option('i',   'index',        opt_type=range,     default=None)
        option_parser.add_option('m',   'mode',         opt_type=int,       default=None)
        option_parser.add_option('?',   'search',       opt_type=str,       default=None)
        option_parser.add_option('im',  'image',        opt_type=None,      default=False)
        usernames, options = option_parser.parse(outputs)

        if not usernames:
            userinfo = await self.get_user(user)
            if not userinfo:
                return await ctx.send(":red_circle: **`{}` does not have an account linked.**".format(user.name))
            else:
                base_api = self.remove_api_suffix(api)
                username = [userinfo["{}_username".format(base_api)]]
        else:
            username = usernames

        # find beatmap
        beatmap_urls = await self.find_recent_bmp_urls(channel, ['/b/','beatmap'], search=options['search'])
        if not beatmap_urls:
            return await ctx.send(":red_circle: **{}, no maps found in conversation.**".format(user.mention))

        bmp_idx = 0
        if options['index']: # choose which one in the list, if there's a list (top cmd)
            bmp_idx = min(int(options['index']) - 1, len(beatmap_urls))
            options['index'] = None # because it messes with _process_user_score

        # print('BEATMAP URLS', beatmap_urls)
        beatmapset_id, beatmap_id, map_gamemode = self._url_to_bmapid(beatmap_urls[bmp_idx])

        forced_gamemode = None
        if map_gamemode is None:
            if options['mode'] is not None:
                forced_gamemode = int(options['mode'])
            elif cmd_gamemode is not None:
                forced_gamemode = int(cmd_gamemode)

        # print('FINAL MAP MODE', map_gamemode)
        #try:
        await self.process_user_score(ctx, username, 
            beatmapset_id=beatmapset_id,
            beatmap_id=beatmap_id,
            map_gamemode=map_gamemode,
            forced_gamemode=forced_gamemode,
            api=api)
        # except:
            # return await ctx.send(":red_circle: **{}, Error, try again later.**".format(user.mention))


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(aliases = ['m'])
    async def map(self, ctx, *inputs):
        """
        Get map from a link, recent score card, or search. Works same way passively.

        [Options]
        Accuracy (-a): Calculate pp at a certain accuracy. (float)
        Breakdown (-b): Calculate pp for a certain score breakdown. (e.g. #/#/#/#)
        Combo (-c): Calculate pp for a certain max combo on play. (int)
        Converts (-cv): Include converts in display. (no param)
        Graph (-g): Include strain graph. (no param)
        Index (-i): Get index in a beatmapset. Starts from 1. (int)
        Leaderboard (-lb): Display leaderboard for certain map.
        Mode (-m #) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania. (int or tag)
        Mods: Calculate pp for a mod combination applied to map or recently referenced map. (e.g. HD)
        Page (-p): Changes page if more than 3 maps in a beatmapset. (int)
        Set (-s): Displays full beatmap set instead of single beatmap. (no param)
        Version (-v): Looks for a specific version based on a query. (str)
        Search (-?): Search query for a specific beatmap. Pair with -i, -s, -v. Quotes required. (str)
        

        [Example]
        +<COMMAND> HD -g -a 97.5
        """

        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        inputs, gamemode = self._gamemode_option_parser(inputs) # map gamemode might not be the same
        option_parser = OptionParser()
        option_parser.add_option('i',   'index',         opt_type=int,      default=None)
        option_parser.add_option('v',   'version',       opt_type=str,      default=None)
        option_parser.add_option('s',   'set',           opt_type=None,     default=False)
        option_parser.add_option('g',   'graph',         opt_type=None,     default=False)
        option_parser.add_option('a',   'acc',           opt_type=float,    default=None)
        option_parser.add_option('c',   'combo',         opt_type=int,      default=None)
        option_parser.add_option('b',   'breakdown',     opt_type=str,      default=None)
        option_parser.add_option('m',   'mode',          opt_type=int,      default=None)
        option_parser.add_option('?',   'search',        opt_type=int,      default=None)
        option_parser.add_option('cv',  'convert',       opt_type=None,     default=False)
        option_parser.add_option('lb',  'leaderboard',   opt_type=None,     default=None)
        option_parser.add_option('p',   'page',          opt_type=int,      default=1)
        output, options = option_parser.parse(inputs)

        if gamemode is not None and options['mode'] is None:
            options['mode'] = gamemode

        # print(options)

        ## find beatmap in outputs
        command_urls = self.find_osu_urls(" ".join(output))
        # if there are mods but no output, then find beatmap url
        mods = []
        if options['search'] is None:
            if not command_urls:
                beatmap_urls = await self.find_recent_bmp_urls(channel, ['/s/','/b/','beatmap'])
                mods = utils.str_to_mod(" ".join(output)) 
            else:
                beatmap_urls = [command_urls[0][0]] # url, mod pair   
                if not command_urls[0][1]:
                    mods = []
                else:
                    mods = utils.str_to_mod(command_urls[0][1])

            if not beatmap_urls:
                return await ctx.send(":red_circle: **{}, no maps found.**".format(user.mention))
        else:
            mods = utils.str_to_mod(" ".join(output)) 
                
        # check if search
        if options['search']:
            search_results = await self.owoAPI.map_search(options['search'])
            if not search_results:
                return await ctx.send(":red_circle: **{}, no maps found.**".format(user.mention))

            result = search_results[0]
            is_set = False
            map_id = result['beatmap_id']
        else:
            # print(beatmap_urls)
            beatmap_url = beatmap_urls[0]
            beatmapset_id, beatmap_id, _ = self._url_to_bmapid(beatmap_url)

            if beatmapset_id and not beatmap_id:
                is_set = True
                map_id = beatmapset_id
            else:
                is_set = False
                map_id = beatmap_id

        if is_set:
            beatmap = await self.owoAPI.get_beatmapset(map_id)
        else:
            beatmap = await self.owoAPI.get_beatmap(map_id)

        # print('MAP CMD', beatmap)

        if options['version']:
            if not is_set:
                beatmap_set = await self.owoAPI.get_beatmapset(
                    beatmap[0]['beatmapset_id'])
            else:
                beatmap_set = beatmap

            similar_sig = []
            for i in range(len(beatmap_set)):
                full_query = '{}'.format(beatmap_set[i]['version'])
                similar_sig.append(utils.get_similarity(
                    full_query.lower(), options['version'].lower()))
            similar_idx = np.argmax(similar_sig)
            beatmap = [beatmap_set[similar_idx]]
        elif options['set'] or options['index'] is not None:
            if not is_set:
                beatmap = await self.owoAPI.get_beatmapset(
                    beatmap[0]['beatmapset_id'])

        # print('beatmap check 2 ', beatmap)

        # handle other filtering options
        indices = []
        for idx, bmp in enumerate(beatmap): # beatmap is a list until this point
            # print(options['convert'], bmp['convert'], options['mode'], bmp['mode'])
            try:
                if not options['convert'] and options['mode'] is None:
                    if not bool(bmp['convert']): # default
                        indices.append(idx)
                        continue
            except:
                pass

            is_valid_map = False
            if options['mode'] and int(bmp['mode']) != int(options['mode']):
                continue
            elif options['mode'] and int(bmp['mode']) == int(options['mode']):
                is_valid_map = True

            if not bool(options['convert']) and bool(bmp['convert']):
                is_valid_map = False
            elif bool(options['convert']) and bool(bmp['convert']):
                is_valid_map = True

            if is_valid_map:
                indices.append(idx)

        if not indices:
            return await ctx.send(
                "**No beatmaps found with those options.**")

        elif options['index'] is not None:
            i = min(max(0, int(options['index']) - 1), len(beatmap_urls))
            indices = [indices[i]]

        beatmap = [beatmap[idx] for idx in indices] # filtered

        if options['leaderboard'] and len(beatmap) == 1:
            gamemode = str(beatmap[0]['mode'])
            leaderboard_info = await self.owoAPI.get_leaderboard(
                beatmap[0]['beatmap_id'], mods=None, mode=gamemode)
            return await self.disp_leaderboard(ctx.message, beatmap, leaderboard_info, 
                options=options)
        elif options['leaderboard']:
            return await ctx.send(
                "**Please specify the map in the mapset by using `-v version_name`.**")

        extra_info = {}
        if options["acc"]:
            extra_info['extra_acc'] = float(str(options["acc"]).replace("%",''))
        elif options["breakdown"] or options['combo']:
            if len(beatmap) == 1:
                breakdown_txt = options["breakdown"]
                if not breakdown_txt:
                    hypothetical_play_info = self.parse_breakdown(breakdown_txt)
                    hypothetical_play_info['count_300'] = beatmap[0]['max_combo']
                else:
                    hypothetical_play_info = self.parse_breakdown(breakdown_txt)
                hypothetical_play_info['hit_total'] = \
                    sum([hypothetical_play_info[hit_type] for hit_type in hypothetical_play_info])
                
                if hypothetical_play_info['hit_total'] > beatmap[0]['max_combo']:
                    return await ctx.send("**Your breakdown hit total does not add up! Max: `{}`**".format(
                        beatmap[0]['max_combo']))

                if options['combo'] is not None and int(options['combo']) > beatmap[0]['max_combo']:
                    return await ctx.send("**Your combo is greater than number of hits! Max: `{}`**".format(
                        beatmap[0]['max_combo']))

                hypothetical_play_info['accuracy'] = utils.calculate_acc(
                    hypothetical_play_info, beatmap[0]['mode'])
                hypothetical_play_info['max_combo'] = options['combo']
                hypothetical_play_info['mode'] = beatmap[0]['mode']
                hypothetical_play_info['enabled_mods'] = utils.mod_to_num(''.join(mods))

                msg, em = await self.create_hypothetical_play_embed(ctx, beatmap[0], hypothetical_play_info)
                return await ctx.send(msg, embed=em)
            else:
                return await ctx.send(
                    "**Please specify the map in the mapset by using `-v version_name`.**")

        include_graph = len(beatmap) == 1

        # print(beatmap)
        await self.disp_beatmap(ctx.message, beatmap,
            mods=''.join(mods), include_graph=options['graph'], extra_info=extra_info)


    def parse_breakdown(self, breakdown_txt, delimiter='/'):
        breakdown_txt = breakdown_txt.replace('[','').replace(']','')
        breakdown_parse = breakdown_txt.split(delimiter)
        # print(breakdown_txt, breakdown_parse)
        breakdown_dict = {}
        if breakdown_txt:
            if len(breakdown_parse) == 6:
                breakdown_dict['count_geki'] = int(breakdown_parse[0])
                breakdown_dict['count_300'] = int(breakdown_parse[1])
                breakdown_dict['count_katu'] = int(breakdown_parse[2])
                breakdown_dict['count_100'] = int(breakdown_parse[3])
                breakdown_dict['count_50'] = int(breakdown_parse[4])
                breakdown_dict['count_miss'] = int(breakdown_parse[5])
            elif len(breakdown_parse) == 4:
                breakdown_dict['count_300'] = int(breakdown_parse[0])
                breakdown_dict['count_100'] = int(breakdown_parse[1])
                breakdown_dict['count_50'] = int(breakdown_parse[2])
                breakdown_dict['count_miss'] = int(breakdown_parse[3])
            elif len(breakdown_parse) == 3:
                breakdown_dict['count_300'] = int(breakdown_parse[0])
                breakdown_dict['count_100'] = int(breakdown_parse[1])
                breakdown_dict['count_miss'] = int(breakdown_parse[2])
        else:
            if len(breakdown_parse) == 6:
                breakdown_dict['count_geki'] = 0
                breakdown_dict['count_300'] = 0
                breakdown_dict['count_katu'] = 0
                breakdown_dict['count_100'] = 0
                breakdown_dict['count_50'] = 0
                breakdown_dict['count_miss'] = 0
            elif len(breakdown_parse) == 4:
                breakdown_dict['count_300'] = 0
                breakdown_dict['count_100'] = 0
                breakdown_dict['count_50'] = 0
                breakdown_dict['count_miss'] = 0
            elif len(breakdown_parse) == 3:
                breakdown_dict['count_300'] = 0
                breakdown_dict['count_100'] = 0
                breakdown_dict['count_miss'] = 0          

        return breakdown_dict


    async def create_hypothetical_play_embed(self, ctx, beatmap, hyp_play):
        # it's a lot like the create_recent_embeds method, but i didn't want to screw with it..
        server_user = ctx.message.author
        server = ctx.message.guild

        beatmap_url = self.owoAPI.get_beatmap_url(beatmap)
        beatmap_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap)

        acc = utils.calculate_acc(hyp_play, hyp_play['mode'])
        enabled_mods = int(hyp_play['enabled_mods'])

        # determine mods
        mods = utils.num_to_mod(enabled_mods)
        if not mods:
            mods.append('No Mod')

        # do some input protection/implied calculations for the hyp play
        if 'max_combo' not in hyp_play and 'max_combo' in beatmap:
            if hyp_play['count_miss'] == 0:
                hyp_play['max_combo'] = beatmap['max_combo']
        elif 'max_combo' in hyp_play and hyp_play['max_combo'] is not None:
            hyp_play['max_combo'] = int(hyp_play['max_combo'])
        else:
            hyp_play['max_combo'] = hyp_play['hit_total']
        hyp_play['rank'] = utils.calculate_rank(
            hyp_play, hyp_play['accuracy'], mods)
        gamemode = hyp_play['mode']

        # display the embed
        beatmap_info, _, _ = await self.owoAPI.get_full_beatmap_info(beatmap, 
                mods=enabled_mods, extra_info={'play_info': hyp_play})

        msg = "**Hypothetical Play for {}:**".format(server_user.name)

        play_pp = 0
        if beatmap_info is not None and 'extra_info' in beatmap_info:
            # print('using calc pp')
            play_pp = float(beatmap_info['extra_info']['play_pp'])

        pot_txt = ''
        if 'extra_info' in beatmap_info and \
            abs(float(beatmap_info['extra_info']['play_pp']) - \
            float(beatmap_info['extra_info']['fc_pp'])) > 2 and \
            gamemode == 0 and 'S' not in hyp_play['rank']:

            pot_txt = '**{:.2f}PP** ({:.2f}PP for {:.2f}% FC)'.format(play_pp, 
                float(beatmap_info['extra_info']['fc_pp']), 
                float(beatmap_info['extra_info']['fc_acc']))
        else:
            pot_txt = '**{:.2f}PP** (_Unofficial_)'.format(play_pp)

        # define acc text
        if gamemode == 3:
            if float(hyp_play['count_300']) != 0:
                ratio_300 = float(hyp_play['count_geki'])/float(hyp_play['count_300'])
                acc_txt = '{:.2f}% ▸ {:.2f}:1'.format(round(acc, 2), ratio_300)
            else:
                acc_txt = '{:.2f}% ▸ ∞:1'.format(round(acc, 2))
        else:
            acc_txt = '{:.2f}%'.format(round(acc, 2))

        info = ""
        info += "▸ **{}** ▸ {} ▸ {}\n".format(
            self.RANK_EMOTES[hyp_play['rank']], pot_txt, acc_txt)
        max_combo_den_str = '/{}'.format(str(beatmap['max_combo']))
        if 'none' in str(beatmap['max_combo']).lower() or \
            str(beatmap['max_combo']) == '0':
            max_combo_den_str = ''
        info += "▸ x{}{} ▸ {}\n".format(
            hyp_play['max_combo'], max_combo_den_str,
            self._get_score_breakdown(hyp_play, gamemode))

        # form map completion
        if 'extra_info' in beatmap_info and \
            'map_completion' in beatmap_info['extra_info'] and \
            beatmap_info['extra_info']['map_completion'] != 100 and not graph:
            info += "▸ **Map Completion:** {:.2f}%".format(
                beatmap_info['extra_info']['map_completion'])

        # print(calc_info)
        star_str, _ = self.compare_val_params(
            beatmap_info, 'difficulty_rating', 'stars_mod', 
            precision=2, single=True)

        em = discord.Embed(description=info, colour=server_user.colour)
        em.set_author(name="{} [{}]{} +{} [{}★]".format(
            beatmap['title'], beatmap['version'],
            self._get_keys(beatmap, gamemode, beatmap['version']), 
            utils.fix_mods(''.join(mods)), star_str), 
            url=beatmap_url, icon_url=server_user.avatar_url)

        em.set_thumbnail(url=beatmap_image_url)

        return msg, em

    async def find_recent_bmp_urls(self, channel, look_for_bmp, 
        search=None):

        beatmap_urls = []
        found_map = False
        async for msg in channel.history(limit=100):
            if msg.author.bot and msg.embeds:
                try:
                    embed = msg.embeds[0]

                    # print(search, str(search).lower() in embed.author.name.lower())
                    if search and str(search).lower() not in embed.author.name.lower() and \
                        search not in str(embed.description):
                        continue
                    
                    # check the author line
                    embed_url = embed.author.url.replace(')', '')
                    if any([check in embed_url for check in look_for_bmp]) and \
                        embed_url not in beatmap_urls:
                        beatmap_urls.append(embed_url)
                        found_map = True

                    # check the description section
                    if hasattr(embed, 'description') and embed.description:
                        description = str(embed.description)
                        all_urls = self.find_osu_urls(description)
                        if all_urls:
                            for url, mods in all_urls:
                                map_url = url.replace(')', '')
                                if any([x in map_url for x in look_for_bmp]) and \
                                    map_url not in beatmap_urls:
                                    beatmap_urls.append(map_url)
                                    found_map = True
                    if found_map:
                        break
                except:
                    pass

        return beatmap_urls

    # ------------------------- leaderboard display -----------------------
    @commands.command(pass_context = True, name = 'leaderboard', 
        aliases = ['ol','osul','lb','osulb'])
    async def leaderboard(self, ctx, *inputs):
        """
        Server leaderboard for osu!.

        [Options]
        Country (-c): 2-char country code. Reference https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2
        Mode (-m) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania
        Page (-p): Changes page in leaderboard. (int)
        Server (-{server name}): <osu_servers>
        Stat (-s): Sort by a specific user stat. Available: id, playcount (pc), ranked score (rs), total score (ts), pp, level (lvl), accuracy (acc). Delimiter: ,

        [Example]
        +<COMMAND> -c US
        """

        user = ctx.message.author
        server = ctx.message.guild

        db_user = await self.get_user(user)

        # get options
        outputs, gamemode = self._gamemode_option_parser(inputs)
        outputs, server_options = self.server_option_parser(outputs)
        api = self.determine_api(server_options, db_user=db_user)
        option_parser = OptionParser()
        option_parser.add_option('s',   'stat',         opt_type=str,     default=None)
        option_parser.add_option('c',   'country',      opt_type=str,     default=None)
        option_parser.add_option('m',   'mode',         opt_type=int,     default=None)
        option_parser.add_option('p',   'page',         opt_type=int,     default=1)
        _, options = option_parser.parse(outputs)

        skip_num = self.LB_MAX * (int(options['page'])-1)

        # need mode for leaderboard
        if gamemode is not None:
            mode = int(gamemode)
        elif options['mode'] is not None:
            mode = int(options['mode'])
        else:
            mode = 0

        # print('DATABASE USER', db_user)

        # get verified members of the server
        cleaned_api = self.remove_api_suffix(api)
        server_query = {"servers" : {"$in": [str(server.id)]}}
        
        if api == 'bancho':
            server_query["{}_verified".format(cleaned_api)] = {
                "$exists": True, 
                "$eq": True
            }
        
        # print('SERVER QUERY', server_query)
        server_user_osu_ids = []
        discord_to_osu_mapping = {}
        async for server_user in self.players.find(server_query):
            try:
                discord_to_osu_mapping[server_user['{}_user_id'.format(api)]] = {
                    'discord_username': server_user['discord_username']
                }
                server_user_osu_ids.append(server_user['{}_user_id'.format(api)])
            except:
                pass

        # print('LEADERBOARD SERVER USERS', server_user_osu_ids)

        # query database cache for players
        valid_types = ['id','pc','rs','ts','pp','lvl','acc','pt']
        if not options['stat']: # default sort by pp
            options['stat'] = 'pp'
        if options['stat'] not in valid_types:
            return await ctx.send("**Invalid Stat! Available: `{}`**".format(', '.join(valid_types)))

        cache_query = {
            'data.user_id': {"$in": server_user_osu_ids},
            'api': api,
            'mode': mode
            }

        if options['country'] is not None:
            cache_query['data.country'] = countries.get(options['country']).alpha2

        # print('CACHE QUERY', cache_query)

        options_list = [self._lb_stats_query(stat) for stat in options['stat'].split(',')]
        sort_criteria = [("data.{}".format(opt["type"]), opt["order"]) for opt in options_list]
        sort_criteria_dict = {sort_criteria[i][0]: sort_criteria[i][1] for i in range(len(sort_criteria))}
        # print('SORT CRITERIA', sort_criteria_dict)

        sorted_user_list = []
        found_osu_ids = [] # get rid of dups cause cache has dups
        base_pipeline = [
            {"$group": { # 0
                "_id" : {
                    "data.user_id": "$data.user_id",
                    "api": "$api",
                    "mode": "$mode"
                },
                "data": {"$first": "$data"},
                "api": {"$first": "$api"},
                "mode": {"$first": "$mode"},
                }
            },
            {"$match": cache_query}, # 1
            {"$sort": sort_criteria_dict}, # 2
        ]

        # find total documents
        count_total_pipeline = copy.deepcopy(base_pipeline)
        # count_total_pipeline.extend([{"$count": "counts"}])
        total = 0
        async for temp in self.owoAPI.cache.user.entries.aggregate(
            count_total_pipeline, allowDiskUse=True):
            total += 1

        # find user position
        try:
            user_query = {
                'data.user_id': db_user['{}_user_id'.format(cleaned_api)],
                'api': api,
                'mode': mode
            }
            user_info = await self.owoAPI.cache.user.entries.find_one(user_query)
        except:
            user_info = None
        
        if not user_info:
            show_rank = False
        else:
            rank_pipeline = copy.deepcopy(base_pipeline)
            rank_query = {}
            for opt in options_list:

                if opt["order"] == 1:
                    order_type = "$lte"
                else:
                    order_type = "$gte"

                rank_query['data.{}'.format(opt["type"])] = \
                    {order_type: user_info['data'][opt["type"]]}

            rank_pipeline.append({"$match": rank_query}) # 'rep': {'$gt': userinfo['rep']}
            show_rank = False
            user_rank = 0

            if api == 'bancho' and 'bancho_verified' in db_user \
                and db_user['bancho_verified']:
                show_rank = True

            async for temp in self.owoAPI.cache.user.entries.aggregate(
                rank_pipeline, allowDiskUse=True):
                # print(temp['data']['user_id'], db_user['{}_user_id'.format(api)])
                if temp['data']['user_id'] == db_user['{}_user_id'.format(api)]:
                    show_rank = True
                user_rank += 1 # their would-be rank
        

        # print('USER RANK', user_rank)

        # add the extra two to the pipeline
        full_query_pipeline = copy.deepcopy(base_pipeline)
        full_query_pipeline.extend([
            {"$skip": skip_num}, # 3
            {"$limit": 15} # 4
            ])

        count_mode = 0
        sorted_user_list = []
        async for player in self.owoAPI.cache.user.entries.aggregate(
            full_query_pipeline, allowDiskUse=True):
            sorted_user_list.append(player['data'])

        # drawing leaderboard
        sorted_list = sorted_user_list
        msg = ""
        start_index = self.LB_MAX*(int(options['page'])-1)

        default_label = "  "
        special_labels = ["♔", "♕", "♖", "♗", "♘", "♙"]

        # define variable defaults
        indicator = 'Acc'
        variable_stat = 'accuracy'
        disp_fmt = "{:.2f}%"
        if options_list:
            if options_list[0]['indicator'] not in ['PP', 'Acc']:
                indicator = options_list[0]['indicator']
                variable_stat = options_list[0]['type']
                disp_fmt = options_list[0]['display']

        header = u'`{:<7}{:<12}{:<12}{:<6}{:<12}{:<12}{:<12}`\n'.format(
            'Rank','Dis. Name','Username', 'CC', 'PP Rank', indicator, 'PP')
        msg += header
        for rank_idx, single_user in enumerate(sorted_list):
            try:
                current_rank = start_index+rank_idx+1
                # print(current_rank)
                if current_rank-1 < len(special_labels):
                    label = special_labels[current_rank-1]
                else:
                    label = default_label

                # get text
                global_rank = '-'
                if 'global_rank' in single_user:
                    global_rank = single_user['global_rank']
                pp_raw = '-'
                if 'pp_raw' in single_user:
                    pp_raw = single_user['pp_raw']

                # handle time a bit differently
                if variable_stat == 'total_seconds_played':
                    days, r = divmod(int(single_user['total_seconds_played']), 86400)
                    hours, r = divmod(r, 3600)
                    # minutes, seconds = divmod(r, 60)

                    variable_stat_val = '{}d {}hr'.format(days, hours)
                else:
                    variable_stat_val = single_user[variable_stat]

                # print(single_user.keys())
                msg += u'`{:<3}{:<4}{:<12}{:<12}{:<6}{:<12}{:<12}{:<12}`\n'.format(
                    current_rank, label, 
                    self._truncate_text(
                        discord_to_osu_mapping[single_user['user_id']]['discord_username'].replace(
                            '`', '\`'), 10),
                    self._truncate_text(single_user['username'],10),
                    "{}".format(single_user['country']),
                    "#{}".format(global_rank), 
                    disp_fmt.format(variable_stat_val),
                    "{:.2f}pp".format(pp_raw))
            except:
                pass

        country_txt = ''
        if options['country']:
            country_txt = '({} Only)'.format(countries.get(options['country']).alpha2.upper())
        user_rank_txt = '-'
        if show_rank:
            user_rank_txt = '{}'.format(user_rank)

        gamemode_text = utils.get_gamemode_display(self.MODES[mode])
        em = discord.Embed(description='', colour=user.colour)
        title = '{} {} Leaderboard for {} {}'.format(
            gamemode_text, options_list[0]['description'], server.name, country_txt)

        total_pages = math.ceil(total/self.LB_MAX)
        em.set_author(name=title, icon_url=server.icon_url)
        api_icon_url = self.owoAPI.get_server_avatar(api)
        server_name = self.owoAPI.get_server_name(api)
        em.set_footer(text="Your Rank: {} | On osu! {} Server | Page {} of {} ".format(
            user_rank_txt, server_name, options['page'], total_pages), icon_url=api_icon_url)
        em.description = msg

        await ctx.send(embed = em)


    def _format_lb_number(self, number, num_type):
        if float(number).is_integer():
            return round(number)
        else:
            return round(float(number),2)


    def _lb_stats_query(self, rank_type):
        rank_type = str(rank_type).strip().lower()
        options = {}
        if rank_type == "id":
            options["type"] = "user_id"
            options["description"] = "User ID"
            options["indicator"] = "ID"
            options["order"] = 1
            options["display"] = "{}"
        elif rank_type == "pc":
            options["type"] = "playcount"
            options["description"] = "Playcount"
            options["indicator"] = "PC"
            options["order"] = -1
            options["display"] = "{}"
        elif rank_type == "rs":
            options["type"] = "ranked_score"
            options["description"] = "Ranked Score"
            options["indicator"] = "Score"
            options["order"] = -1
            options["display"] = "{}"
        elif rank_type == "ts":
            options["type"] = "total_score"
            options["description"] = "Total Score"
            options["indicator"] = "Score"
            options["order"] = -1
            options["display"] = "{}"
        elif rank_type == "pp":
            options["type"] = "pp_raw"
            options["description"] = "PP"
            options["indicator"] = "PP"
            options["order"] = -1
            options["display"] = "{:.2f}pp"
        elif rank_type == "lvl":
            options["type"] = "level"
            options["description"] = "Level"
            options["indicator"] = "Level"
            options["order"] = -1
            options["display"] = "{:.2f}"
        elif rank_type == "acc":
            options["type"] = "accuracy"
            options["description"] = "Accuracy"
            options["indicator"] = "Acc"
            options["order"] = -1
            options["display"] = "{:.2f}%"
        elif rank_type == "pt":
            options["type"] = "total_seconds_played"
            options["description"] = "Play Time"
            options["indicator"] = "Time"
            options["order"] = -1
            options["display"] = "{}"

        return options


    def _truncate_text(self, text, max_length):
        if len(text) > max_length:
            if text.strip('$').isdigit():
                text = int(text.strip('$'))
                return "${:.2E}".format(text)
            return text[:max_length-3] + "..."
        return text


    def _name(self, discord_name, osu_name, max_length=20):
        if discord_name == osu_name:
            return osu_name
        else:
            return "{} ({})".format(discord_name,
                self._truncate_text(osu_name, max_length - len(discord_name) - 3), max_length)


    @commands.command(no_pm=True)
    async def skin(self, ctx, user:discord.Member = None):
        """
        Get skin of a user.

        [Options]
        user = user in the server.

        [Example]
        +<COMMAND> <USER>
        """
        if user == None:
            user = ctx.message.author

        userinfo = await self.players.find_one({'user_id':str(user.id)})

        if userinfo != None:
            try:
                if 'skin' in userinfo:
                    await ctx.send("**`{}`'s Skin: <{}>.**".format(user.name,
                        self.bot.escape_mass_mentions(userinfo['skin']).replace('\n', '').replace('@', '')))
                else:
                    await ctx.send("**`{}` has not set a skin.**".format(user.name))
            except:
                await ctx.send("**`{}` has not set a skin.**".format(user.name))
        else:
            await ctx.send("**`{}` does not have an account linked. Use `>osuset user \"your username\"`.**".format(user.name))


    # Gets json information to proccess the small version of the image
    async def process_user_info(self, ctx, inputs, gamemode:int):

        channel = ctx.message.channel
        discord_user = ctx.message.author
        server = discord_user.guild

        # update server info
        await self.update_user_servers_list(discord_user, server)

        db_user = await self.get_user(discord_user)

        try:
            outputs, server_options = self.server_option_parser(inputs)
            api = self.determine_api(server_options, db_user=db_user)
            option_parser = OptionParser()
            option_parser.add_option('im', 'image',         opt_type=None, default=False)
            option_parser.add_option('d',  'detailed',      opt_type=None, default=False)
            option_parser.add_option('s',  'stats',         opt_type=None, default=False)
            option_parser.add_option('u',  'user',          opt_type=None, default=False)
            usernames, info_options = option_parser.parse(outputs)
        except:
            await ctx.send("**Please check your inputs for errors!**")

        # pings bancho server
        if api == 'bancho':
            commands = await self.irc_commands.find_one({"type":"commands"})
            if not commands:
                await self.irc_commands.insert_one({
                    "type":"commands", "commands": []})
                commands = []
            else:
                commands = commands["commands"]

        # get rid of duplicates initially
        usernames = list(set(usernames))
        if not usernames: # if still empty, then use self + account
            usernames = [None]

        # gives the final input for osu username
        final_usernames = []
        for username in usernames:
            test_username = await self.process_username(ctx, username, 
                api=api, force_username=info_options['user'])
            if test_username is not None:
                final_usernames.append(test_username)
        if not final_usernames:
            return await ctx.send("**No players found.**")

        # get rid of duplicates initially
        final_usernames = list(set(final_usernames))

        # only display signature if it's requested
        if info_options['image']:
            return await ctx.send("**Currently unavailable.**") # remove later!!!!
            return await self.draw_profile_image()

        # check if it's asking for details. Only do one user in that case
        if info_options['detailed']:
            if 'bancho' not in api:
                return await ctx.send("**Only currently supported for `Bancho`.**")

            user = await self.owoAPI.get_user(final_usernames[0], mode=gamemode, api=api)
            if not user:
                return await ctx.send(":red_circle: **`{}` not found.**".format(username))
            
            user = user[0] # get only first entry

            em, graph = await self.create_user_detailed_embed(ctx, user, 
                gamemode=gamemode, api=api)

            try:
                if graph:
                    return await ctx.send(embed=em, files=[graph])
                else:
                    return await ctx.send(embed=em)
            except:
                return await ctx.send(":red_circle: **`{}` not found.**".format(username))

        elif info_options['stats']:

            if 'bancho' not in api:
                return await ctx.send("**Only currently supported for `Bancho`.**")

            user = await self.owoAPI.get_user(final_usernames[0], 
                mode=gamemode, api=api)
            if not user:
                return await ctx.send(":red_circle: **`{}` not found.**".format(username)) 

            em = await self.create_user_stats_embed(ctx, user[0], 
                gamemode=gamemode, api=api)

            return await ctx.send(embed=em)

        else: # if the embed isn't special, then just display the regular profile
            all_players = []
            for username in final_usernames[0:self.MAX_USER_DISP]:
                user = await self.owoAPI.get_user(username, mode=gamemode, api=api)

                if not user:
                    await ctx.send(":red_circle: **`{}` not found.**".format(username))
                    continue

                try:
                    user = user[0]
                    all_players.append(
                        await self.create_user_embed(ctx, user, gamemode, api=api))
                except:
                    await ctx.send(":red_circle: **`{}` not found.**".format(username))
                    continue

            disp_num = min(self.NUM_MAX_PROF, len(all_players))
            if disp_num < len(all_players):
                await ctx.send("Found {} users, but displaying top {}.".format(
                    len(all_players), disp_num))

            for player in all_players[0:self.MAX_USER_DISP]:
                await ctx.send(embed=player)

            # BANCHO COMMAND, must refractor/reorganize
            """
            commands.append("WHOIS {}\r\n".format(username))
            await self.irc_commands.update_one({"type":"commands"}, {'$set':{
                'commands': commands}})"""


    async def create_user_embed(self, ctx, user, gamemode, 
        old_userinfo=None, api='bancho'):
        try: # if ctx is actually a message object like for link detection
            server = ctx.message.guild
            server_user = ctx.message.author
        except:
            server = ctx.guild
            server_user = ctx.author

        gamemode_text = utils.get_gamemode_text(gamemode)

        profile_avatar = await self.owoAPI.get_user_avatar(user['user_id'], api)
        profile_url = self.owoAPI.get_user_url(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        online_status = self.owoAPI.is_online(user['user_id'], api)
        api_display = self.owoAPI.get_server_name(api)

        # generate rank brakedown
        is_all_zero = True
        rank_text = ""
        rank_order = ['SSH', 'SS', 'SH', 'S', 'A']
        for rank in rank_order:
            try:
                rank_num = int(user['count_rank_{}'.format(rank.lower())])

                if rank_num != 0:
                    is_all_zero = False

                rank_text += '{}`{:,}`'.format(self.RANK_EMOTES[rank], rank_num)
            except:
                pass
        if is_all_zero:
            rank_text = ""

        # see if pp country rank exists
        if 'pp_country_rank' in user.keys() and user['pp_country_rank'] is not None:
            pp_country_rank = " ({}#{:,})".format(
                user['country'].upper(), int(user['pp_country_rank']))
        else:
            pp_country_rank = " ({})".format(user['country'])

        # calculate playtime from seconds
        hours_played_str = ""
        if 'total_seconds_played' in user.keys() and user['total_seconds_played']:
            hours_played = round(float(user['total_seconds_played'])/3600)
            hours_played_str = ' ({:,} hrs)'.format(int(hours_played))

        # see if there's available pp or accuracy
        pp_text = ""
        if 'pp_raw' in user.keys():
            pp_text = '**PP:** {:,.2f}'.format(
                round(float(user['pp_raw']), 3))

        acc_text = ""
        if 'accuracy' in user.keys():
            acc_text = "**Acc:** {}%".format(
                round(float(user['accuracy']), 2))

        pp_rank_text = "-"
        if 'pp_rank' in user.keys() and user['pp_rank'] is not None:
            pp_rank_text = "#{:,}".format(int(user['pp_rank']))

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="{} Profile for {}".format(gamemode_text, user['username']),
            icon_url = flag_url, url=profile_url)
        em.set_thumbnail(url=profile_avatar)

        # describe the actual info section of the embed
        info = ""
        info += "▸ **{} Rank:** {} {}\n".format(
            api_display, pp_rank_text, pp_country_rank)
        if 'level' in user.keys():
            level_int = int(float(user['level']))
            level_percent = float(user['level']) - level_int
            info += "▸ **Level:** {} + {:.2f}%\n".format(
                level_int, round(level_percent*100, 4))
        if pp_text or acc_text:
            info += "▸ {} {}\n".format(pp_text, acc_text)
        info += "▸ **Playcount:** {:,}{}\n".format(
            int(user['playcount']), hours_played_str)
        if rank_text:
            info += "▸ **Ranks:** {}".format(rank_text)
        em.description = info

        # get online/offline status
        if 'is_online' in user.keys():
            icon_url = self._get_online_icon(user['is_online'])
        else:
            icon_url = self.owoAPI.get_server_avatar(api)

        # check if verified
        verified = ""
        if 'discord' in user.keys():
            user_discrim_str = "{0.name}#{0.discriminator}".format(server_user)

            if user['discord'] == user_discrim_str:
                verified = " | Verified"
            
        em.set_footer(text = "On osu! {} Server{}".format(api_display, verified), icon_url=icon_url)

        return em


    def _get_online_icon(self, is_online):
        if is_online:
            online_status = "https://i.imgur.com/DKLGecZ.png"
        else:
            online_status = "https://i.imgur.com/sOtDO3u.png" # offline
        return online_status


    async def create_user_detailed_embed(self, ctx, user, gamemode, api='bancho'):
        try: # if ctx is actually a message object like for link detection
            server = ctx.message.guild
            server_user = ctx.message.author
        except:
            server = ctx.guild
            server_user = ctx.author

        gamemode_text = utils.get_gamemode_text(gamemode)

        profile_avatar = await self.owoAPI.get_user_avatar(user['user_id'], api)
        profile_url = self.owoAPI.get_user_url(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        online_status = self.owoAPI.is_online(user['user_id'], api)
        api_display = self.owoAPI.get_server_name(api)

        # generate rank brakedown
        is_all_zero = True
        rank_text = ""
        rank_order = ['SSH', 'SS', 'SH', 'S', 'A']
        for rank in rank_order:
            try:
                rank_num = int(user['count_rank_{}'.format(rank.lower())])

                if rank_num != 0:
                    is_all_zero = False

                rank_text += '{}`{:,}`'.format(self.RANK_EMOTES[rank], rank_num)
            except:
                pass
        if is_all_zero:
            rank_text = ""

        # see if pp country rank exists
        if 'pp_country_rank' in user.keys() and user['pp_country_rank'] is not None:
            pp_country_rank = " ({}#{:,})".format(
                user['country'].upper(), int(user['pp_country_rank']))
        else:
            pp_country_rank = " ({})".format(user['country'])

        # get total hits
        if 'total_hits' in user.keys():
            total_hits = int(user['total_hits'])
        else:
            total_hits = int(user['count_50']) + int(user['count_100']) + int(user['count_300'])
        hits_per_play = round(total_hits / int(user['playcount']), 2)

        # see if there's available pp or accuracy
        pp_text = "-"
        if 'pp_raw' in user.keys():
            pp_text = '**PP:** {:,.2f}'.format(
                round(float(user['pp_raw']), 3))

        acc_text = "-"
        if 'accuracy' in user.keys():
            acc_text = "**Acc:** {}%".format(
                round(float(user['accuracy']), 2))

        pp_rank_text = "-"
        if 'pp_rank' in user.keys() and user['pp_rank'] is not None:
            pp_rank_text = "#{:,}".format(int(user['pp_rank']))

        # play time
        play_time = "Unknown"
        if 'total_seconds_played' in user.keys():
            m, s = divmod(int(user['total_seconds_played']), 60)
            h, m = divmod(m, 60)
            play_time = ' ({:,}h {}m {}s)'.format(h, m, s)

        # play style
        play_style = "Unknown"
        if 'playstyle' in user.keys():
            if user['playstyle']:
                play_style = ', '.join(user['playstyle'])
            else:
                play_style = "Unknown"

        # get ranked score
        if 'ranked_score' in user.keys():
            ranked_score = int(user['ranked_score'])
            rs_per_play = round(int(user['ranked_score']) / int(user['playcount']), 2)
        else:
            ranked_score = 0
            rs_per_play = 0

        # get total score
        total_score = int(user['total_score'])
        ts_per_play = round(int(user['total_score']) / int(user['playcount']), 2)

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="{} Profile for {}".format(gamemode_text, user['username']),
            icon_url = flag_url, url=profile_url)
        em.set_thumbnail(url=profile_avatar)

        # describe the actual info section of the embed
        info = ""
          
        info += "▸ **{} Rank:** {} {}\n".format(
            api_display, pp_rank_text, pp_country_rank)
        if 'level' in user.keys():
            level_int = int(float(user['level']))
            level_percent = float(user['level']) - level_int
            info += "▸ **Level:** {} + {:.2f}%\n".format(
                level_int, round(level_percent*100, 4))
        if pp_text or acc_text:
            info += "▸ {} {}\n".format(pp_text, acc_text)
        info += "▸ **Playcount:** {:,}{}\n".format(
            int(user['playcount']), play_time)
        if rank_text:
            info += "▸ **Ranks:** {}\n".format(rank_text)
        if 'ranked_score' in user:
            info += "▸ **Ranked Score:** {:,} ({:,}/play)\n".format(
                ranked_score, rs_per_play)
        if 'total_score' in user:
            info += "▸ **Total Score:** {:,} ({:,}/play)\n".format(
                total_score, ts_per_play)            
        if 'total_hits' in user:
            info += "▸ **Total Hits:** {:,}  ({:,}/play)\n".format(
                total_hits, hits_per_play)
        if 'max_combo' in user:
            info += "▸ **Max Combo:** {:,}\n".format(int(user['max_combo']))

        em.description = info

        # recent events
        recent_events = ''
        recent_activity = await self.owoAPI.get_user_recent_activity(
            user['user_id'])

        # print('USER RECENT ACTIVITY', recent_activity)

        if not isinstance(recent_activity, list):
            recent_activity = [recent_activity]

        if recent_activity:
            for event in recent_activity[0:3]:
                # there will always be a time
                time = datetime.datetime.strptime(
                    event['createdAt'], '%Y-%m-%dT%H:%M:%S+00:00')
                time_ago = utils.time_ago(datetime.datetime.utcnow(), time, shift=0, abbr=True).lower()
                # print(event)
                if event['type'] == 'rank':
                    beatmap_url = 'https://osu.ppy.sh{}'.format(event['beatmap']['url'])
                    recent_events += "▸ {} Achieved `#{}` on [{}]({}) {} ago (`{}`)\n".format(
                        self.RANK_EMOTES[event['scoreRank']], event['rank'], 
                        event['beatmap']['title'], beatmap_url, time_ago, event['mode'])
                elif event['type'] == 'beatmapsetUpdate':
                    beatmapset_url = 'https://osu.ppy.sh{}'.format(event['beatmapset']['url'])
                    recent_events += "▸ Updated beatmapset [{}]({}) {}\n".format(
                        event['beatmapset']['title'], beatmapset_url, time_ago)
                elif event['type'] == 'beatmapsetRevive':
                    beatmapset_url = 'https://osu.ppy.sh{}'.format(event['beatmapset']['url'])
                    recent_events += "▸ Revived beatmapset [{}]({}) {}\n".format(
                        event['beatmapset']['title'], beatmapset_url, time_ago)
                elif event['type'] == 'rankLost':
                    beatmap_url = 'https://osu.ppy.sh{}'.format(event['beatmap']['url'])
                    recent_events += "▸ Lost first on [{}]({}) {} ago\n".format(
                        event['beatmap']['title'], beatmap_url, time_ago)
                elif event['type'] == 'achievement':
                    recent_events += "▸ Unlocked the `{}` medal {} ago\n".format(
                        event['achievement']['name'], time_ago)

            # print(recent_events)
            em.add_field(name='Recent Events', value=recent_events, inline=False)

            # print('RECENT EVENTS', recent_events)
        # draw useful user plots
        # try:
        colour = (server_user.colour.r/255, 
            server_user.colour.g/255, 
            server_user.colour.b/255)
        try:
            discord_file, url = await drawing.plot_profile(user, 
                color = colour)
            em.set_image(url=url)
        except:
            discord_file = None

        # extra info
        extra_info = ''
        if 'previous_usernames' in user and user['previous_usernames']:
            extra_info += "▸ **Previously known as: ** {}\n".format(
                ', '.join(user['previous_usernames']))
        if 'playstyle' in user and user['playstyle']:
            extra_info += "▸ **Playstyle:** {}\n".format(
                ', '.join(user['playstyle']))
        if 'follower_count' in user and user['follower_count']:
            extra_info += "▸ **Followers:** {:,}\n".format(
                int(user['follower_count']))
        if 'ranked_and_approved_beatmapset_count' in user:
            extra_info += "▸ **Ranked/Approved Beatmaps:** {:,}\n".format(
                int(user['ranked_and_approved_beatmapset_count']))
        if 'replays_watched_by_others' in user:
            extra_info += "▸ **Replays Watched By Others:** {:,}\n".format(
                int(user['replays_watched_by_others']))
        if extra_info:    
            em.add_field(name='Extra Info', value=extra_info, inline=False)
            # print('EXTRA INFO', extra_info)

        # get online/offline status
        if 'is_online' in user.keys():
            icon_url = self._get_online_icon(user['is_online'])
        else:
            icon_url = self.owoAPI.get_server_avatar(api)

        # check if verified
        verified = ""
        if 'discord' in user.keys():
            user_discrim_str = "{0.name}#{0.discriminator}".format(server_user)

            if user['discord'] == user_discrim_str:
                verified = " | Verified"
            
        em.set_footer(text = "On osu! {} Server{}".format(api_display, verified), icon_url=icon_url)

        return em, discord_file


    async def create_user_stats_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author
        gamemode_text = utils.get_gamemode_text(gamemode)

        # get proper api
        profile_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        user_url = self.owoAPI.get_user_url(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        colour = (server_user.colour.r/255, 
            server_user.colour.g/255, 
            server_user.colour.b/255)

        # do some necessary calculations -----------------

        # get stats
        # await self.owoAPI.cache.user_stats.entries.drop() # drop for test
        stats = await self.owoAPI.get_user_stats(
            user['user_id'], mode=gamemode, api=api)

        # draw simplified box-whisker
        stats_str = ''
        stats_ignore = ['pp_w']
        comp_list = ['pp', 'stars', 'aim', 'speed', 'acc', 'bpm', 'pp_w']
        for attr in comp_list:
            if attr not in stats or attr in stats_ignore or not stats[attr]:
                continue
            name = attr
            if name == 'pp':
                name = 'PP'
            elif name == 'bpm':
                name = 'BPM'
            else:
                name = attr.capitalize()

            stats_str += self._draw_box_whisker(stats[attr], name=name) + '\n'
        
        pp_total = np.sum(stats['pp'])
        pp_w_total = np.sum(stats['pp_w'])

        freq_list = {}
        for attr in stats:
            if attr not in stats or attr in comp_list or not stats[attr]:
                continue
            freq_list[str(attr)] = self._count_freq(stats[attr])

        # print(freq_list)

        # favorite mod combos -------------------------------
        sorted_mod_combos = dict(sorted(freq_list['mod_combos'].items(), 
            key=lambda item: item[1], reverse=True))
        mod_combos_str = ''
        counter = 0
        for mod_combo in sorted_mod_combos: # start with 5
            # mod combo (count, pp, % of total)
            # find idx from stats['mod_combos']
            top_idx = [i for i, x in enumerate(stats['mod_combos']) if x == mod_combo]
            pp_mod_combo = np.array(stats['pp'])[top_idx]
            pp_w_mod_combo = np.array(stats['pp_w'])[top_idx]

            mod_combos_str += \
                '`{:<6}:` `{:<2}` [`{:<8}` (`{:<5}%`)|`{:<8}` (`{:<5}%`)]\n'.format(
                mod_combo, sorted_mod_combos[mod_combo], 
                round(np.sum(pp_w_mod_combo), 1),
                round(np.sum(pp_w_mod_combo)/pp_w_total * 100, 1),
                round(np.sum(pp_mod_combo), 1), 
                round(np.sum(pp_mod_combo)/pp_total * 100, 1))

            counter += 1
            if counter > 5:
                break

        # favorite mods -------------------------------------
        sorted_mods = dict(sorted(freq_list['mods'].items(), 
            key=lambda item: item[1], reverse=True))
        mod_str = ''
        counter = 0
        for mod in sorted_mods: # start with 5
            # mod combo (count, pp, % of total)
            mod_str += '`{:<6}` (`{:<3}`)\n'.format(
                mod, sorted_mods[mod])
            counter += 1
            if counter > 5:
                break

        # pp dependencies, calculate with lists
        if gamemode == 0:
            dep_str = ''
            y_comp = 'pp_w'
            compare_attrs = [('aim', y_comp), 
                ('speed', y_comp), ('acc', y_comp)] 
            total_corr = 0
            dep = {}
            for var_1, var_2 in compare_attrs:
                var_1_norm = np.array(stats[var_1]) / np.max(stats[var_1])
                var_2_norm = np.array(stats[var_2]) / np.max(stats[var_2])

                # length adjustment
                min_length = min(var_1_norm.shape[0], var_2_norm.shape[0])
                var_1_norm = var_1_norm[:min_length]
                var_2_norm = var_2_norm[:min_length]

                # try:
                corr_mat = np.corrcoef(var_1_norm, var_2_norm)
                corr = abs(corr_mat[0, 1])
                total_corr += corr
                dep[var_1] = corr
                # except:
                    # print(var_1_norm, var_2_norm)

            dep_per = {}
            for var in dep:
                dep_per[var] = dep[var] / total_corr * 100

            sorted_deps = dict(sorted(dep_per.items(), 
                key=lambda item: item[1], reverse=True))
            for dep in sorted_deps:
                name = dep
                if name == 'bpm':
                    name = 'BPM'
                else:
                    name = name.capitalize()

                dep_str += '`{:<6}:` `{:<6}%`\n'.format(name, round(sorted_deps[dep], 2))
        else:
            dep_str = ''

        # favorite mappers
        sorted_mappers = dict(sorted(freq_list['mappers'].items(), 
            key=lambda item: item[1], reverse=True))
        mappers_str = ''
        counter = 0
        for mapper in sorted_mappers: # start with 5
            # mod combo (count, pp, % of total)

            top_idx = [i for i, x in enumerate(stats['mappers']) if x == mapper]
            pp_mod_combo = np.array(stats['pp'])[top_idx]
            pp_w_mod_combo = np.array(stats['pp_w'])[top_idx]

            mappers_str += '`{:<15}:` `{:<2}` [`{:<8}`(`{:<5}%`)|`{:<8}`(`{:<5}%`)]\n'.format(
                mapper, sorted_mappers[mapper], 
                round(np.sum(pp_w_mod_combo), 1),
                round(np.sum(pp_w_mod_combo)/pp_w_total * 100, 1),
                round(np.sum(pp_mod_combo), 1), 
                round(np.sum(pp_mod_combo)/pp_total * 100, 1))

            counter += 1
            if counter > 5:
                break

        # footer----------------
        # get online/offline status
        if 'is_online' in user.keys():
            icon_url = self._get_online_icon(user['is_online'])
        else:
            icon_url = self.owoAPI.get_server_avatar(api)

        # check if verified
        verified = ""
        if 'discord' in user.keys():
            user_discrim_str = "{0.name}#{0.discriminator}".format(server_user)

            if user['discord'] == user_discrim_str:
                verified = " | Verified"
            
        # embed -----------
        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="Top {} Stats in {} for {}".format(
            len(stats['pp']), gamemode_text, user['username']), 
            icon_url = flag_url, url = user_url)
        em.add_field(name='Performance Spread (┃= avg):', 
            value=stats_str, inline=False)
        if dep_str:
            em.add_field(name='PP Attr. Dependencies (/100):', value=dep_str, inline=True)
        em.add_field(name='Favourite Mods:', value=mod_str, inline=True)
        em.add_field(name='Favourite Mod Combos (#, Weighted|Unweighted PP):', value=mod_combos_str, inline=False)
        em.add_field(name='Favourite Mappers (#, Weighted|Unweighted PP):', value=mappers_str, inline=False)
        em.set_thumbnail(url=profile_url)

        """
        if 'cover' in user.keys():
            em.set_image(url=user['cover']['url'])
            """
        em.set_footer(text = "On osu! {} Server{}".format(
            self.owoAPI.get_server_name(api), verified), icon_url=icon_url)

        return em


    def _count_freq(self, data_list):
        freq_dict = {}
        for el in data_list:
            if el not in freq_dict:
                freq_dict[str(el)] = 0
            freq_dict[str(el)] += 1
        return freq_dict


    def _draw_box_whisker(self, data_list, name='None', total_length=20):
        start_char = '╠'
        end_char = '╣'
        fill_char = '═'
        mean_char = '┃'
        med_char = '┋'

        d_mean = np.mean(data_list)
        d_min = np.min(data_list)
        d_max = np.max(data_list)
        d_median = np.median(data_list)

        bx_whisker = fill_char * total_length
        bx_whisker = list(bx_whisker)
        med_idx = int(round((d_median - d_min) /(d_max - d_min) * total_length))
        # bx_whisker[med_idx] = med_char
        mean_idx = int(round((d_mean - d_min) /(d_max - d_min) * total_length))
        bx_whisker[mean_idx] = mean_char
        # replace the letters with parameter
        mean_str = '{:.2f}'.format(d_mean)
        if mean_idx/total_length > 0.5:
            bx_whisker[mean_idx-len(mean_str):mean_idx] = '{:.2f}'.format(d_mean)
        else:
            bx_whisker[mean_idx+1:mean_idx+len(mean_str)+1] = '{:.2f}'.format(d_mean)
        bx_whisker = ''.join(bx_whisker)

        # print(bx_whisker)

        # make pretty
        bx_whisker_full = '`{:<6}:` `{:<6.2f}` `{}{}{}` `{:<6.2f}`'.format(
            name, float(d_min), start_char, bx_whisker, end_char, float(d_max))
        """
        bx_whisker_full = '`{:<6}: {}{}{}`\n'.format(
            name, start_char, bx_whisker, end_char)
        labels = '`{}{:<6.2f}{}{:<6.2f}{}{:<6.2f}`'.format(
            8*' ', float(d_min), (mean_idx-len('{:<6.2f}'.format(float(d_min))))*' ', 
            d_mean, 6*' ', float(d_max))

        bx_whisker_full += labels"""

        return bx_whisker_full



    async def _create_graph_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author

        # info
        profile_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        user_url = self.owoAPI.get_user_url(user['user_id'], api)
        gamemode_text = utils.get_gamemode_text(gamemode)

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="{} Rank graph for {}".format(gamemode_text, user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)

        #try:
        replays_watched = user["replays_watched_counts"]
        monthly_playcounts = user["monthly_playcounts"]
        discord_file, url = await drawing.plot_profile(user['rank_history']["data"], 
            replays_watched, monthly_playcounts, color = colour)
        em.set_image(url=url)

        return em, discord_file


    async def _create_recent_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author

        recent = await self.owoAPI.get_user_activity(user['user_id'], api=api)

        # info
        profile_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        user_url = self.owoAPI.get_user_url(user['user_id'], api)

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="Recent activity for {}".format(user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)
        msg = ''
        for activity in recent:
            act_time = datetime.datetime.strptime(activity['date'], '%Y-%m-%d %H:%M:%S')
            try:
                timeago = utils.time_ago(datetime.datetime.now(), act_time, shift = 4, abbr=True)
            except:
                try:
                    timeago = utils.time_ago(datetime.datetime.now(), act_time, shift = 0, abbr=True)
                except:
                    timeago = utils.time_ago(datetime.datetime.now(), act_time, shift = 0, abbr=True)

            if activity['type'] == 'rank':
                beatmap_id = activity['beatmap']['url']
                beatmap_id = beatmap_id[int(beatmap_id.rfind('/'))+1:]
                beatmap_id = beatmap_id.replace('/','')
                url = 'https://osu.ppy.sh/b/' + beatmap_id
                msg += "▸ Achieved {} (`#{}`) on [{}]({}) ({})\n".format(
                    self.RANK_EMOTES[activity['scoreRank']],
                    activity['rank'],activity['beatmap']['title'], url, timeago)
            elif activity['type'] == 'rankLost':
                beatmap_id = activity['beatmap']['url']
                beatmap_id = beatmap_id[int(beatmap_id.rfind('/'))+1:]
                beatmap_id = beatmap_id.replace('/','')
                url = 'https://osu.ppy.sh/b/' + beatmap_id
                msg += "▸ Lost first place on [{}]({}) ({})\n".format(
                    activity['beatmap']['title'], url, timeago)
            elif activity['type'] == 'nameChange':
                pass
            elif activity['type'] == 'beatmapsetUpload':
                beatmapset_id = activity['beatmapset']['url']
                beatmapset_id = beatmapset_id[int(beatmapset_id.rfind('/'))+1:]
                beatmapset_id = beatmapset_id.replace('/','')
                url = 'https://osu.ppy.sh/s/' + beatmapset_id
                msg += "▸ Updated beatmap set [{}]({}) ({})\n".format(
                    activity['beatmapset']['title'], url, timeago)

        if msg == '':
            msg = "No recent activity."

        em.description = msg
        return em


    async def _create_most_played_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author
        info = soup.find("script", {"id": "json-extras"}, type='application/json')
        web_data = json.loads(info.text)
        most_played = web_data['beatmapPlaycounts']
        gamemode_text = utils.get_gamemode_text(gamemode)
        # info
        user_url = 'https://osu.ppy.sh/u/{}'.format(user['user_id'])
        profile_url ='https://a.ppy.sh/{}'.format(user['user_id'])

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="Most played maps for {}".format(user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)

        msg = ''
        count = 1
        for ct_beatmap in most_played:
            beatmap = ct_beatmap['beatmap']
            beatmapset = ct_beatmap['beatmapset']
            url = 'https://osu.ppy.sh/s/' + str(beatmapset['id'])
            dl_links = self._get_dl_links(beatmapset['id'], beatmap['id'])
            msg += "{}. [{} - {} [{}]]({}) ({} times) [[download]({})]\n".format(count,
                beatmapset['artist'], beatmapset['title'], beatmap['version'], url,
                ct_beatmap['count'], dl_links[0])
            count += 1
        em.description = msg
        return em


    async def _create_first_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author
        info = soup.find("script", {"id": "json-extras"}, type='application/json')
        web_data = json.loads(info.text)
        firsts = web_data['scoresFirsts']

        # info
        user_url = 'https://osu.ppy.sh/u/{}'.format(user['user_id'])
        profile_url ='https://a.ppy.sh/{}'.format(user['user_id'])

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="First Place Maps for {}".format(user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)

        msg = ''
        for ft_info in firsts:
            beatmap = ft_info['beatmap']
            beatmapset = ft_info['beatmapset']
            dl_links = self._get_dl_links(beatmapset['id'], beatmap['id'])
            url = 'https://osu.ppy.sh/b/' + str(beatmap['id'])
            if ft_info['pp']:
                pp = float(ft_info['pp'])
                pp = "{:.1f}".format(pp)
            else:
                pp = "0"
            msg += "▸ [{} - {} [{}]]({}) (`{}`|`{}pp`|+`{}`) [[download]({})]\n".format(
                beatmapset['artist'], beatmapset['title'], beatmap['version'], url,
                ft_info['rank'], pp, ''.join(ft_info['mods']), dl_links[0])

        if msg == '':
            msg = "None."

        em.description = msg
        return em


    async def _create_favorites_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author
        info = soup.find("script", {"id": "json-extras"}, type='application/json')
        web_data = json.loads(info.text)
        favorite_maps = web_data['favouriteBeatmapsets']

        # info
        user_url = 'https://osu.ppy.sh/u/{}'.format(user['user_id'])
        profile_url ='https://a.ppy.sh/{}'.format(user['user_id'])

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="Favorite Maps for {}".format(user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)

        msg = ''
        for fav_info in favorite_maps:
            dl_links = self._get_dl_links(fav_info['id'], fav_info['beatmaps'][0]['id'])
            url = 'https://osu.ppy.sh/s/' + str(fav_info['id'])
            user_url = 'https://osu.ppy.sh/users/' + str(fav_info['user_id'])
            msg += "▸ [{} - {}]({}) by [{}]({}) [[download]({})]\n".format(
                fav_info['artist'], fav_info['title'], url, fav_info['creator'], user_url, dl_links[0])

        if msg == '':
            msg = "None"

        em.description = msg
        return em


    async def _create_beatmaps_embed(self, ctx, user, gamemode=0, api='bancho'):
        server = ctx.message.guild
        server_user = ctx.message.author
        info = soup.find("script", {"id": "json-extras"}, type='application/json')
        web_data = json.loads(info.text)
        user_maps_approved = web_data['rankedAndApprovedBeatmapsets']
        user_maps_unranked = web_data["unrankedBeatmapsets"]
        user_maps_graveyard = web_data["graveyardBeatmapsets"]
        gamemode_text = utils.get_gamemode_text(gamemode)
        # info
        user_url = 'https://osu.ppy.sh/u/{}'.format(user['user_id'])
        profile_url ='https://a.ppy.sh/{}'.format(user['user_id'])

        em = discord.Embed(description='', colour=server_user.colour)
        em.set_author(name="Beatmaps created by {}".format(user['username']), icon_url = profile_url, url = user_url)
        colour = (server_user.colour.r/255, server_user.colour.g/255, server_user.colour.b/255)

        types = ['Ranked', 'Unranked', 'Graveyard']
        for status in types:
            if status == 'Ranked':
                maps = user_maps_approved
            elif status == "Unranked":
                maps = user_maps_unranked
            else:
                maps = user_maps_graveyard
            msg = ''
            for beatmap in maps:
                dl_links = self._get_dl_links(beatmap['id'], beatmap['beatmaps'][0]['id'])
                url = 'https://osu.ppy.sh/s/' + str(beatmap['id'])
                msg += "▸ [{} - {}]({}) (Maps: `{}` ♥: `{}`) [[download]({})]\n".format(
                    beatmap['artist'], beatmap['title'], url, len(beatmap['beatmaps']), beatmap['favourite_count'],
                    dl_links[0])

            if not maps:
                msg += "None currently.\n"

            em.add_field(name = "__{} Maps ({})__\n".format(status, len(maps)), value = msg, inline = False)
        return em

    # ------------------------- some database commands -------------------
    
    async def update_user_servers_list(self, discord_user, server):

        # update discord user server and username
        caller_user = await self.players.find_one(
            {"user_id":str(discord_user.id)})

        if caller_user:
            # print("found user")
            if "servers" in caller_user and caller_user["servers"]:
                if str(server.id) not in caller_user["servers"]:
                    caller_user["servers"].append(str(server.id))
                    # print("adding to list")
            else:
                caller_user["servers"] = [str(server.id)]
                # print("single server")
            await self.players.update_many({"user_id":str(discord_user.id)},
                {"$set": {"servers": caller_user["servers"]}})

    """
    async def update_user_servers_leave(self, member):
        db_user = db.osu_settings.find_one({"user_id":member.id})
        if not db_user:
            return

        if "servers" in db_user and member.str(server.id) in db_user["servers"]:
            try:
                db_user["servers"].remove(member.str(server.id))
            except:
                pass
        else:
            db_user["servers"] = []

        await self.players.update_one({"user_id":member.id},
            {"$set": {"servers":db_user["servers"]}})

    async def update_user_servers_join(self, member):
        db_user = db.osu_settings.find_one({"user_id":member.id})
        if not db_user:
            None

        if "servers" in db_user and member.str(server.id) not in db_user["servers"]:
            db_user["servers"].append(member.str(server.id))
        else:
            db_user["servers"] = [member.str(server.id)]

        await self.players.update_one({"user_id":member.id},
            {"$set": {"servers":db_user["servers"]}})
    """
    

    # -------------------------- live map feed ---------------------------------------------
    @checks.mod_or_permissions(manage_guild=True)
    @commands.command(name="mapfeed", aliases = ['mf', 'feed'])
    async def mapfeed(self, ctx, *options):
        """
        Set channel for map feeds (default all maps/modes). Sets channel you execute command in. Max 5 channels per server. Overrides previous settings.

        [Options]
        Info (-info): check the options of the mapfeed on your server.
        Map Status (-st): 1 = Ranked, 2 = Approved, 3 = Qualified, 4 = Loved. Exclusively these map statuses.
        Modes (-m #): 0 = std, 1 = taiko, 2 = ctb, 3 = mania. Exclusively these modes.
        Min Stars (-ls): greater than this value. (float)
        Max Stars (-hs): less than this value. (float)
        Min Length (-ll): maps longer than this value. (int, in seconds)
        Max Length (-hl): maps shorter than this value. (int, in seconds)
        Mapper (-mpr): Name or ID of mappers, ID preferred. Delimiter (,). (str)
        Excluded Mapper (-xmpr): Name or ID of mappers, ID preferred. Delimiter (,). (str)
        Remove (-rm): remove the channel from map feed.

        [Example]
        +<COMMAND> -m 03 -st 14 -xmpr "Sotarks,Monstrata,Stevy" -ls 5.2
        """
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        map_track_limit = 5
        new_channel_entry = {
            "channel_id": str(channel.id), # just in case?
            "status": [],
            "modes": [],
            "min_stars": None,
            "max_stars": None,
            "mappers": [],
            "xmappers": [],
            "max_length": None,
            "min_length": None,
        }
        option_parser = OptionParser()
        option_parser.add_option('st',      'status',       opt_type='str',     default=None)
        option_parser.add_option('m',       'modes',        opt_type='str',     default=None)
        option_parser.add_option('ls',      'min_stars',    opt_type='float',   default=None)
        option_parser.add_option('hs',      'max_stars',    opt_type='float',   default=None)
        option_parser.add_option('ll',      'min_length',   opt_type='int',     default=None)
        option_parser.add_option('hl',      'max_length',   opt_type='int',     default=None)
        option_parser.add_option('rm',      'remove',       opt_type=None,      default=False)
        option_parser.add_option('o',       'overwrite',    opt_type=None,      default=False)
        option_parser.add_option('info',    'info',         opt_type=None,      default=False)
        option_parser.add_option('mpr',     'mappers',      opt_type='str',     default=None)
        option_parser.add_option('xmpr',    'xmappers',     opt_type='str',     default=None)

        _, options = option_parser.parse(options)

        # get server info
        server_mf_info = await self.get_server_mapfeed(server)
        channel_mf_info = None
        new_entry = False
        if str(channel.id) in server_mf_info["channels"].keys():
            channel_mf_info = server_mf_info["channels"][str(channel.id)]
        else:
            channel_mf_info = new_channel_entry
            new_entry = True

        if options["info"]:
            # give info
            embeds = []
            if not server_mf_info['channels']:
                return await ctx.send(
                    "**No maps are being tracked in this server.**")

            for channel_id in server_mf_info["channels"]:
                em = discord.Embed(color=user.colour)
                em.set_author(name = f"{server.name}'s Map Feeds", icon_url = server.icon_url)
                msg = ""
                # try:
                channel = self.bot.get_channel(int(channel_id))
                for attr in server_mf_info["channels"][channel_id]:
                    value = server_mf_info["channels"][channel_id][attr]
                    if isinstance(value, list) and value != []:
                        value = ", ".join([str(i) for i in value]) # ensure string
                    elif value is None or value == []:
                        value = "N/A"

                    if attr == 'xmappers': # just too look better
                        attr = 'Excluded Mappers'

                    if "channel_id" not in attr:
                        msg += "**{}**: `{}`\n".format(attr.replace("_", " ").title(),
                            value)
                em.add_field(name=f"#{channel.name}", value = msg)
                embeds.append(em)

            if embeds:
                return await self.bot.menu(ctx, embeds)
            else:
                return ctx.send(":white_circle: **The server currently does not have any map feed channels!**")

        if options["remove"]:
            if channel_mf_info:
                del server_mf_info["channels"][str(channel.id)]
                await self.map_track.update_one({"server_id":str(server.id)},
                    {"$set": {"channels": server_mf_info["channels"]}})
                return await ctx.send(f":white_check_mark: **`#{channel.name}` removed from map feed list.**")
            else:
                return await ctx.send(f":red_circle: **`#{channel.name}` is not on the map feed list.**")

        if options["overwrite"]:
            server_mf_info["channels"][str(channel.id)] = new_channel_entry

        if new_entry and len(server_mf_info["channels"].keys()) >= map_track_limit and \
            not options["overwrite"]:
            return await ctx.send(f":red_circle: **You can only track in {map_track_limit} channels per server!**")

        # ------ filtering options-------
        valid_status = ["1", "2", "3", "4"]
        if options["status"]:
            status_list = list(options["status"])
            user_status = []
            for s in valid_status:
                if s in status_list:
                    user_status.append(s)
            channel_mf_info["status"] = user_status
        else: # default to tracking all of them
            channel_mf_info["status"] = valid_status

        valid_modes = [0,1,2,3]
        if options["modes"]:
            user_modes = []
            for m in valid_modes:
                if str(m) in str(options["modes"]):
                    user_modes.append(m)
            channel_mf_info["modes"] = user_modes
        else:
            channel_mf_info["modes"] = valid_modes

        # -------- check stars-----------
        if options["min_stars"]:
            try:
                min_stars = float(options["min_stars"])
                channel_mf_info["min_stars"] = min_stars
            except:
                return await ctx.send(":red_circle: **Please check your minimum stars.**")

            if min_stars > 6:
                return await ctx.send(":red_circle: **Your minimum stars can't be greater than 6!**")
        else:
            channel_mf_info["min_stars"] = 0

        if options["max_stars"]:
            try:
                max_stars = float(options["max_stars"])
                channel_mf_info["max_stars"] = max_stars
            except:
                return await ctx.send(":red_circle: **Please check your maximum stars.**")

            if (options["min_stars"] and min_stars) and max_stars < min_stars: # kinda riskyyy lol
                return await ctx.send(":red_circle: **Min stars can't be greater than max stars...**")
        else:
            channel_mf_info["max_stars"] = 100

        # -------- check length-----------
        if options["min_length"]:
            try:
                min_length = int(options["min_length"])
                channel_mf_info["min_length"] = min_length
            except:
                return await ctx.send(":red_circle: **Please check your minimum length (in seconds).**")
        else:
            channel_mf_info["min_length"] = 0
        if options["max_length"]:
            try:
                max_length = int(options["max_length"])
                channel_mf_info["max_length"] = max_length
            except:
                return await ctx.send(":red_circle: **Please check your maximum length (in seconds).**")

            if (options["min_length"] and min_length) and max_length < min_length: # kinda riskyyy lol
                return await ctx.send(":red_circle: **Min length can't be greater than max length...**")
        else:
            channel_mf_info["max_length"] = 10000 # god knows if we'll ever have a map this long

        if options["mappers"]:
            if str(options['mappers']) == None:
                channel_mf_info['mappers'] = []
            else:
                user_mappers = []
                mappers = options["mappers"].split(",")
                for mapper in mappers:
                    mapper = mapper.strip()
                    if mapper:
                        user_mappers.append(mapper)
                channel_mf_info["mappers"].extend(user_mappers)

        if options["xmappers"]:
            if str(options['xmappers']) == None:
                channel_mf_info['xmappers'] = []
            else:
                user_mappers = []
                mappers = options["xmappers"].split(",")
                for mapper in mappers:
                    mapper = mapper.strip()
                    if mapper:
                        user_mappers.append(mapper)
                channel_mf_info["xmappers"].extend(user_mappers)

        server_mf_info["channels"][str(channel.id)] = channel_mf_info

        # print(server_mf_info) # **

        await self.map_track.update_one({"server_id":str(server.id)},
            {"$set": {"channels": server_mf_info["channels"]}})

        if options["overwrite"]:
            return await ctx.send(f":white_check_mark: **Successfully overwrote map feed options in `#{channel.name}`.**")
        elif new_entry:
            return await ctx.send(f":white_check_mark: **Successfully activated map feed in `#{channel.name}`.**")
        else:
            return await ctx.send(f":white_check_mark: **Edited map feed for `#{channel.name}`.**")
        #await ctx.send(server_mf_info["channels"][str(channel.id)])


    async def get_server_mapfeed(self, server):
        server_mf_info = await self.map_track.find_one({"server_id": str(server.id)})
        if not server_mf_info:
            new_entry = {
                "server_id": str(server.id),
                "channels": {}
            }
            await self.map_track.insert_one(new_entry)
            server_mf_info = await self.map_track.find_one({"server_id": str(server.id)})
        return server_mf_info


    async def map_feed(self):
        MAP_FEED_INTERVAL = 60 # seconds

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

        while self == self.bot.get_cog('Osu'):
            # get new beatmaps
            sql_date = datetime.datetime.strftime(map_feed_last, '%Y-%m-%d %H:%M:%S')
            try:
                beatmaps = await self.owoAPI.get_beatmap(None, since=sql_date, use_cache=False)
            except:
                await self.map_feed()
            # print(beatmaps)
            print('QUERY TIME', sql_date)

            # save and update
            map_feed_last = datetime.datetime.utcnow()
            sql_date_new = datetime.datetime.strftime(map_feed_last, '%Y-%m-%d %H:%M:%S')
            map_json = {"last_check": sql_date_new}
            fileIO(filepath, "save", data=map_json)
            print('UPDATED TIME', sql_date_new)
            # print('Time elapsed', sql_date-map_feed_last)

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

                # send to appropriate channels
                async for server_options in self.map_track.find({}, no_cursor_timeout=True):
                    guild_id = int(server_options["server_id"])
                    for channel_id in server_options['channels']:
                        channel_options = server_options['channels'][channel_id]
                        channel = self.bot.get_channel(int(channel_id))

                        # if pass the filters
                        guest_mapper = False # only for the mappers, not xmappers
                        for option_mapper in channel_options['mappers']:
                            for diff_name in bmpset_summary['diff_names']:
                                if option_mapper.lower() in diff_name.lower():
                                    guest_mapper = True

                        if 'mappers' in channel_options and channel_options['mappers'] != [] and \
                            bmpset_summary['creator'] not in channel_options['mappers'] and \
                            bmpset_summary['creator_id'] not in channel_options['mappers'] and \
                            not guest_mapper:
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
                            await channel.send(embed=new_bmpset_embed)
                await asyncio.sleep(1)
            await asyncio.sleep(MAP_FEED_INTERVAL)


    async def _create_new_bmp_embed(self, beatmaps):
        # create embed
        status = beatmaps[0]['status']

        em = discord.Embed()

        # determine color of embed based on status
        colour, colour_text = self._determine_status_color(status) # not the case anymore!
        m0, s0 = divmod(int(beatmaps[0]['total_length']), 60)
        desc = '**Length:** {}:{} **BPM:** {}\n'.format(m0,
            str(s0).zfill(2), beatmaps[0]['bpm'])

        # download links
        dl_links = self._get_dl_links(beatmaps[0])
        dl_text_links = []
        for dl_name, dl_link in dl_links:
            dl_text_links.append("[{}]({})".format(dl_name, dl_link))
        desc += '**Download:** {}\n'.format(" | ".join(dl_text_links))

        # symbols/diffs
        desc += self._get_beatmap_diff_icons(beatmaps) + "\n"

        beatmap_url = "https://osu.ppy.sh/beatmapsets/{}/".format(beatmaps[0]["beatmapset_id"])
        # create return em
        em.colour = colour
        em.description = desc

        profile_url = await self.owoAPI.get_user_avatar(beatmaps[0]["user_id"], 'bancho')
        em.set_author(name="{} – {} by {}".format(
            beatmaps[0]['artist'], beatmaps[0]['title'], beatmaps[0]['creator']),
            url=beatmap_url, icon_url = profile_url)
        try:
            map_cover_url = beatmaps[0]["covers"]["card@2x"] 
        except: # old api
            map_cover_url = 'https://assets.ppy.sh/beatmaps/{}/covers/cover.jpg'.format(beatmaps[0]["beatmapset_id"])
        em.set_image(url=map_cover_url)

        rel_time = datetime.datetime.strptime(beatmaps[0]['ranked_date'], '%Y-%m-%d %H:%M:%S').strftime('%B %d %Y at %H:%M:%S')
        fav_count = "{} ❤︎ | ".format(beatmaps[0]["favourite_count"])

        em.set_footer(text = 'Newly {} | {}{} on {} UTC'.format(
            colour_text, fav_count, colour_text, rel_time))
   
        return em


    def _group_beatmaps(self, beatmap_list):
        combined_beatmaps = {}
        for beatmap in beatmap_list:
            if beatmap['beatmapset_id'] not in combined_beatmaps:
                combined_beatmaps[beatmap['beatmapset_id']] = []
            combined_beatmaps[beatmap['beatmapset_id']].append(beatmap)

        return combined_beatmaps


    def _get_bmpset_summary(self, beatmaps):
        map_summary = {}
        map_summary["creator"] = beatmaps[0]['creator']
        try:
            map_summary["creator_id"] = beatmaps[0]['creator_id']
        except:
            map_summary["creator_id"] = beatmaps[0]['user_id']
        map_summary["total_length"] = beatmaps[0]['total_length']
        map_summary["hit_length"] = [bmp['hit_length'] for bmp in beatmaps]
        map_summary["stars"] = [float(bmp['difficulty_rating']) for bmp in beatmaps]
        map_summary["modes"] = list(set([int(bmp['mode']) for bmp in beatmaps]))
        map_summary["status"] = beatmaps[0]['status']
        map_summary["diff_names"] = [str(bmp['version']) for bmp in beatmaps]

        return map_summary


    def _get_beatmap_diff_icons(self, beatmap_list):
        msg = ""
        counter = 0
        beatmap_list = sorted(beatmap_list, key=operator.itemgetter('difficulty_rating'), reverse=True)
        for beatmap in beatmap_list:
            beatmap_url = "https://osu.ppy.sh/b/{}".format(beatmap['beatmap_id'])
            diff = self._determine_emote_name(beatmap)
            mode = str(beatmap["mode"])
            msg += "{} [{}]({}) ({}★) ".format(self.DIFF_EMOTES[mode][diff],
                beatmap["version"], beatmap_url, round(float(beatmap["difficulty_rating"]),2))
        return msg


    def _determine_emote_name(self, beatmap):
        diff = float(beatmap["difficulty_rating"])
        if diff <= 1.99:
            name = "easy"
        elif 1.99 < diff <= 2.69:
            name = "normal"
        elif 2.69 < diff <= 3.99:
            name = "hard"
        elif 3.99 < diff <= 5.29:
            name = "insane"
        elif 5.29 < diff <= 6.49:
            name = "expert"
        else:
            name = "expertplus"
        return name


    def _get_beatmap_id_list(self, beatmap_list):
        id_list = []
        for beatmap in beatmap_list:
            id_list.append(beatmap["id"])
        return id_list


    async def _update_local_info(self, user, discord_user, gamemode):
        osu_user_id = user['user_id']
        discord_user_id = str(discord_user.id)
        database_user_discord = await self.players.find_one({"user_id":discord_user_id})

        if database_user_discord and database_user_discord["osu_user_id"] == osu_user_id:
            await self.players.update_one({"user_id":discord_user_id},
                {"$set": {self.MODES[gamemode]: user}})
            return database_user_discord
        else:
            return None


    # Gets the user's most recent score
    async def process_user_recent(self, ctx, inputs):
        channel = ctx.message.channel
        user = ctx.message.author
        server = ctx.message.guild
        message = ctx.message

        # update server info
        await self.update_user_servers_list(user, server)

        db_user = await self.get_user(user)
        server_settings = None

        # define options
        try:
            outputs, cmd_gamemode = self._gamemode_option_parser(inputs)
            outputs, server_options = self.server_option_parser(outputs)
            api = self.determine_api(server_options, db_user=db_user)
            option_parser = OptionParser()
            option_parser.add_option('b',       'best',         opt_type=None,      default=False)
            option_parser.add_option('m',       'gamemode',     opt_type='str',     default=None)
            option_parser.add_option('ps',      'pass',         opt_type=None,      default=None)
            option_parser.add_option('p',       'page',         opt_type=int,       default=None)
            option_parser.add_option('i',       'index',        opt_type='range',   default=None)
            option_parser.add_option('?',       'search',       opt_type='str',     default=None)
            option_parser.add_option('np',      'now_playing',  opt_type='str',     default=False)
            option_parser.add_option('g',       'graph',        opt_type=None,      default=False)
            option_parser.add_option('l',       'list',         opt_type=None,      default=False)
            option_parser.add_option('10',      'cond_10',      opt_type=None,      default=False)
            option_parser.add_option('im',      'image',        opt_type=None,      default=False)
            option_parser.add_option('u',       'user',         opt_type=None,      default=False)
            usernames, options = option_parser.parse(outputs)
        except:
            await ctx.send("**Please check your inputs for errors!**")

        # print(usernames, options) # **  

        # gives the final input for osu username + get user info
        usernames = list(set(usernames))
        if not usernames: # if still empty, then use self + account
            usernames = [None]
        final_usernames = []
        for username in usernames:
            test_username = await self.process_username(ctx, username, 
                api=api, force_username=options['user'])
            if test_username is not None:
                final_usernames.append(test_username)
        if not final_usernames:
            return await ctx.send("**No players found.**")
        username = final_usernames[0]

        # print(username) # **

        # determines which recent gamemode to display based on user 
        if cmd_gamemode is None:
            if options["gamemode"]:
                gamemode = int(options["gamemode"])
            elif db_user:
                gamemode = int(db_user["default_gamemode"])
            else:
                gamemode = 0
        else:
            gamemode = cmd_gamemode

        # get necessary user/play info
        if options['best']:
            userinfo = await self.owoAPI.get_user(username, mode=gamemode, api=api) # get user info
            full_play_list = await self.owoAPI.get_user_best(
                userinfo[0]['user_id'], mode=gamemode, limit=100, api=api)

            # print('RET LENGTH', len(full_play_list))
            # original play indexing
            for idx, play in enumerate(full_play_list):
                play['play_idx'] = idx + 1

            # print(dates[0:10], dates[60:70])
            full_play_list = sorted(full_play_list, key=lambda k: (k['date']), reverse=True)
            # print(full_play_list[0:2])
        elif options['now_playing'] is not False: # now playing is a person's username
            return await ctx.send('**Currently disabled.**')
            # return await self._get_np(ctx, options['now_playing'])
        else:
            # requests
            userinfo = await self.owoAPI.get_user(username, mode=gamemode, api=api) # get user info
            if userinfo is None or not userinfo:
                return await ctx.send(
                    "**`{}` was not found or no recent plays in `{}` for `{}`.**".format(
                    username, self.owoAPI.get_server_name(api), utils.get_gamemode_text(gamemode)))

            # print(userinfo)
            try:
                full_play_list = await self.owoAPI.get_user_recent(
                    userinfo[0]['user_id'], mode=gamemode, limit=50, api=api)
            except:
                return await ctx.send(
                    "**`{}` was not found or no recent plays in `{}` for `{}`.**".format(
                    username, self.owoAPI.get_server_name(api), utils.get_gamemode_text(gamemode)))


            if not full_play_list:
                return await ctx.send("**`{}` has no recent plays in `{}` for `{}`**".format(
                    username, self.owoAPI.get_server_name(api), utils.get_gamemode_text(gamemode)))
        
            # original play indexing
            for idx, play in enumerate(full_play_list):
                play['play_idx'] = idx + 1

            # print([i['date'] for i in full_play_list])

        # index filters
        indices = None
        if options['pass']: # check for passes, can't also check for index
            # print('Pass option found')
            # print('Pass length', len(full_play_list))
            indices = []
            for idx, play in enumerate(full_play_list):
                # print('Rank', play['rank'], play['rank'] != 'F', play['date'])
                if play['rank'] != 'F':
                    # print('Append', idx)
                    indices.append(idx)

            if not indices:
                return await ctx.send('**No maps passed recently.**') 

        if options['index']:
            try:
                if len(options['index']) == 2 and options['index'][1] is not None: # if it's a range
                    start_idx = int(options['index'][0]) - 1
                    end_idx = int(options['index'][1]) # don't -1 because upper bound
                    if end_idx < start_idx: # input protection
                        temp = start_idx
                        start_idx = end_idx
                        end_idx = temp
                    end_idx = min(end_idx, start_idx + self.LIST_MAX)

                    if indices:
                        indices = [indices[list(range(start_idx, end_idx))]]
                    else:
                        indices = list(range(start_idx, end_idx))
                else:
                    list_idx = int(options['index'][0])-1 # because starts at 0
                    list_idx = max(0, min(list_idx, len(full_play_list)))
                    if indices:
                        if list_idx >= len(indices):
                            return await ctx.send('**`{}` only has `{}` recently passed play{}.**'.format(
                                username, len(indices), self._plural_text(len(indices))))
                        indices = [indices[list_idx]]
                    else:
                        indices = [list_idx]
            except:
                return await ctx.send('**Please provide a number index (e.g. `-i 10`).**')

        if options['search']:
            if api != 'bancho': # !!!!!!!!!!!!!!!!!!!!!!!!!!!! must update
                return await ctx.send('**Searching not currently supported for `{}` server**.'.format(
                    self.owoAPI.get_server_name(api)))
            indices = self._get_play_search(full_play_list, options['search'])
            if not indices:
                return await ctx.send('**No plays found!**')

        # list vs single
        if options['cond_10']: # get the full list for scrolling
            max_length = len(full_play_list)
            indices = indices[0:max_length]
        elif options['list']:
            max_length = min(self.LIST_MAX, len(full_play_list))
            if not indices: # default case
                indices = list(range(max_length))
            indices = indices[0:max_length]
        else:
            max_length = 1
            if not indices: # default case, take the first one in list
                indices = [0]
            indices = [indices[0]]

        if not userinfo or not full_play_list:
            return await ctx.send("**`{}` was not found or no recent plays in `{}`.**".format(
                username, utils.get_gamemode_text(gamemode)))
        
        # get single user
        userinfo = userinfo[0]

        # print(len(full_play_list), indices)
        # do default recent processing/filtering
        userrecent_filtered = [full_play_list[i] for i in indices]
        # print(userrecent_filtered[0])
        # handle embed/image according to single or list
        if options['image']:
            if self.bot.is_production:
                donor_ids = await self.bot.patreon.get_donors_list()
                if str(user.id) not in donor_ids:
                    return await ctx.send("**You must be a supporter to use this feature! `>support`**")

            beatmap = await self.owoAPI.get_beatmap(userrecent_filtered[0]['beatmap_id'])
            enabled_mods = 0
            if 'enabled_mods' in userrecent_filtered[0].keys():
                enabled_mods = int(userrecent_filtered[0]['enabled_mods'])
            elif 'mods' in userrecent_filtered[0].keys():
                enabled_mods = utils.mod_to_num(''.join(userrecent_filtered[0]['mods']))

            # print(userrecent_filtered[0].keys())
            # download the beatmap image
            beatmap_image_file = await self.owoAPI.get_full_beatmapset_image(
                beatmap[0]['beatmapset_id'], beatmap_id=beatmap[0]['beatmap_id'])
            beatmap_info, _, bmp_filepath = await self.owoAPI.get_full_beatmap_info(beatmap[0], 
                mods=enabled_mods, extra_info={'play_info': userrecent_filtered[0]})
            beatmap_chunks = await self.owoAPI.get_beatmap_chunks(beatmap[0], bmp_filepath)
            return await drawing.draw_score(ctx, userinfo, userrecent_filtered[0],
                beatmap_info, gamemode, bmp_chunks=beatmap_chunks, 
                beatmap_image_file=beatmap_image_file, 
                api_name=self.owoAPI.get_server_name(api))
        elif len(userrecent_filtered) == 1:
            if not options['best']:

                if api == 'droid':
                    temp_beatmap = await self.owoAPI.get_beatmap(
                        userrecent_filtered[0]["beatmap_id"], api='ripple')
                    try:
                        userrecent_filtered[0]["beatmap_id"] = temp_beatmap[0]['beatmap_id']
                    except:
                        return await ctx.send("**No beatmap found!**")
                try:
                    attempt_num = self._get_attempt_num(full_play_list, 
                        beatmap_id=userrecent_filtered[0]["beatmap_id"])
                except:
                    attempt_num = None
                score_type = 'Recent'
            else:
                attempt_num = None
                score_type = 'Top {}'.format(userrecent_filtered[0]['play_idx'])

            msg, embed, file = await self.create_recent_play_embed(
                ctx, userinfo, userrecent_filtered[0], gamemode,
                graph=options["graph"], api=api, attempt_num=attempt_num, 
                score_type=score_type)

            if not msg and not embed:
                return await ctx.send('**Issue fetching data.**')
        elif options['cond_10']:
            return
            num_txt = ''
            if len(userrecent_filtered) > 1:
                num_txt = ' {} '.format(len(userrecent_filtered))
            header_txt = "Recent{}{} Play{} for {}".format(
                num_txt, utils.get_gamemode_text(gamemode), 
                self._plural_text(userrecent_filtered), userinfo['username'])

            total_entries = len(userrecent_filtered) # before page
            total_pages = math.ceil(total_entries/max_length)
            if api == 'bancho': # make a list since we have all the beatmaps
                embed_list = []
                for page_idx in range(total_pages):
                    # print(page_idx)
                    start_idx = (page_idx) * max_length
                    end_idx = (page_idx+1) * max_length
                    # print(start_idx, end_idx)
                    play_list_part = userrecent_filtered[start_idx:end_idx]
                    best_maps_part = best_beatmaps[start_idx:end_idx]
                    page_info = (page_idx, total_pages)
                    embed = await self.create_condensed_play_list_embed(
                        ctx, userinfo, play_list_part, best_maps_part, gamemode, 
                        api=api, header_txt=header_txt, 
                        page_info=page_info, var_attr=target_attr)
                    embed_list.append(embed)
                return await self.bot.menu(ctx, embed_list, page=page, timeout=30)  
            else:
                embed = await self.create_condensed_play_list_embed(
                    ctx, userinfo, userrecent_filtered, best_beatmaps, gamemode, 
                    api=api, header_txt=header_txt, page_info=page_info, 
                    var_attr=target_attr)
                return await ctx.send(embed=embed)  

        else: # display normally
            # get all relevant beatmaps
            temp_userrecent = []
            recent_beatmaps = []
            for play in userrecent_filtered:
                try:
                    if api == 'droid':
                        beatmap = await self.owoAPI.get_beatmap(play['beatmap_id'], api='ripple')
                    else:
                        beatmap = await self.owoAPI.get_beatmap(play['beatmap_id'], api=api)
                    recent_beatmaps.append(beatmap[0])
                    temp_userrecent.append(play)
                except:
                    pass
            userrecent_filtered = temp_userrecent # ensures all beatmaps are there

            # print(recent_beatmaps[0])
            file = None
            num_txt = ''
            if len(userrecent_filtered) > 1:
                num_txt = ' {} '.format(len(userrecent_filtered))
            header_txt = "Recent{}{} Play{} for {}".format(
                num_txt, utils.get_gamemode_text(gamemode), 
                self._plural_text(userrecent_filtered), userinfo['username'])
            msg, embed = await self.create_play_list_embed(
                ctx, userinfo, userrecent_filtered, recent_beatmaps, gamemode,
                header_txt=header_txt, api=api)

        if file:
            return await ctx.send(msg, embed=embed, files=[file])
        else:
            return await ctx.send(msg, embed=embed)
        #except:
            # return await ctx.send("**`{}` was not found or no recent plays in `{}`.**".format(
                # username, utils.get_gamemode_text(gamemode)))

        await ctx.send(msg, embed=embed)


    def _gamemode_option_parser(self, inputs):
        option_parser = OptionParser()
        option_parser.add_option('std',     '0',    opt_type=None,  default=False)
        option_parser.add_option('osu',     '0',    opt_type=None,  default=False)
        option_parser.add_option('taiko',   '1',    opt_type=None,  default=False)
        option_parser.add_option('ctb',     '2',    opt_type=None,  default=False)
        option_parser.add_option('mania',   '3',    opt_type=None,  default=False)
        outputs, options = option_parser.parse(inputs)

        gamemode = None
        for option in options:
            if options[option]:
                gamemode = int(option)

        # print(outputs, options, gamemode) # **

        return outputs, gamemode


    async def _recent_list(self):
        userrecent = userrecent[:5]
        for i, score in enumerate(userrecent):
            userrecent[i]['index'] = i
        recent_beatmaps = []
        recent_acc = []
        for play in userrecent:
            bmp = await api_utils.get_beatmap(key, api, beatmap_id=play['beatmap_id'])
            recent_beatmaps.append(bmp[0])
            recent_acc.append(utils.calculate_acc(play, gamemode))
            await asyncio.sleep(.15)
        msg, embed = await self._get_user_top(
            ctx, api, userinfo, userrecent, recent_beatmaps, recent_acc, gamemode,
            recent_list = True)
   

    async def _get_np(self, ctx, target_username):
        beatmap_info = None
        target_user = await ctx.guild.query_members(query=target_username, presences=True)
        if target_user:
            target_user = target_user[0]
        else:
            return await ctx.send("**Discord user not found!**")

        if not target_user.activity or \
            (target_user.activity and str(target_user.activity.application_id) != "367827983903490050"):
            return await ctx.send("**{} is not playing osu! right now.**".format(target_user.name))
            
        # userinfo = await self.players.find_one({"user_id":str(target_user.id)})
        if target_user.activity and target_user.activity.name and "osu" in target_user.activity.name:
            search_query = target_user.activity.details

        search_results = await self.owoAPI.map_search(search_query)
        beatmap_info = await self.owoAPI.get_beatmap(search_results[0]['beatmap_id'])

        if beatmap_info:
            await self.disp_beatmap(ctx.message, beatmap_info)
        else:
            await ctx.send("**`{}` is not playing an osu! map right now.**".format(target_user.name))


    async def _recent_best(self):
        # save keep index
        for i, score in enumerate(userbest):
            userbest[i]['index'] = i
        userbest = sorted(userbest, key=operator.itemgetter('date'), reverse=True)
        userbest = [userbest[options["index"]]]

        # get best plays map information and scores, assume length is self.LIST_MAX
        best_beatmaps = []
        best_acc = []

        beatmap = await api_utils.get_beatmap(key, api, beatmap_id=userbest[0]['beatmap_id'])
        beatmap = beatmap[0]
        best_beatmaps = [beatmap]
        best_acc = [utils.calculate_acc(userbest[options["index"]], gamemode)]
        score_num = userbest[0]['index']

        msg, embed = await self._get_user_top(
            ctx, api, userinfo, userbest, best_beatmaps, best_acc, gamemode,
            score_num = score_num, web = web, is_single = True)


    async def create_recent_play_embed(self, ctx, userinfo, userrecent, gamemode, 
        attempt_num=None, graph=None, api='bancho', score_type='Recent'):

        server_user = ctx.message.author
        server = ctx.message.guild

        if api == 'droid':
            gamemode = 0

        gamemode_text = utils.get_gamemode_text(gamemode)

        if not userrecent:
            return ("**No recent score for `{}` in user's default gamemode (`{}`)**".format(
                server_user['username'], gamemode_text), None)

        profile_url = await self.owoAPI.get_user_avatar(userinfo['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(userinfo['country'])

        # get best plays map information and scores
        """ !!!!!!!!!!!!!!!!!!!
        if api == 'gatari' and gamemode == 0:
            bmp_api = 'gatari'
        elif api == 'droid':
            bmp_api = 'droid'
        else:
            bmp_api = 'bancho'
            """
        bmp_api = api
        beatmap = await self.owoAPI.get_beatmap(userrecent['beatmap_id'], api=bmp_api)
        if not beatmap:
            return None, None, None

        beatmap = beatmap[0]
        beatmap_url = self.owoAPI.get_beatmap_url(beatmap)
        beatmap_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap)

        # calculations
        if api == 'droid':
            acc = float(userrecent['accuracy'])
        else:
            acc = utils.calculate_acc(userrecent, gamemode)

        # enabled_mods
        # print(userrecent['mods']) # **
        enabled_mods = 0
        if 'enabled_mods' in userrecent.keys():
            enabled_mods = int(userrecent['enabled_mods'])
        elif 'mods' in userrecent.keys():
            enabled_mods = utils.mod_to_num(''.join(userrecent['mods']))
        # print('DATA ', userrecent) # **
        try:
            calc_info, bmp, bmp_file_path = await self.owoAPI.get_full_beatmap_info(beatmap, 
                mods=enabled_mods, extra_info={'play_info': userrecent})
        except:
            calc_info = beatmap
            bmp, bmp_filepath = None, None


        # determine mods
        mods = utils.num_to_mod(enabled_mods)
        if not mods:
            mods.append('No Mod')

        msg = "**{} {} Play for {}:**".format(score_type, gamemode_text, userinfo['username'])
        info = ""

        # calculate potential pp
        if 'pp' in userrecent.keys() and userrecent['pp'] and \
            float(userrecent['pp']) != 0: # !!!!!!!!!!!!! needs to be updated later
            # print('using api pp') # **
            play_pp = float(userrecent['pp'])
        elif calc_info is not None and 'extra_info' in calc_info:
            # print('using calc pp')
            play_pp = float(calc_info['extra_info']['play_pp'])
        else:
            play_pp = 0

        # print(userrecent['pp'], calc_info['extra_info']['play_pp'])

        droid_pp_txt = ''
        if api == 'droid':
            try:
                droid_calc_info, _, _ = await self.owoAPI.get_full_beatmap_info(beatmap, 
                    mods=enabled_mods, extra_info={'play_info': userrecent}, api='droid')
                droid_pp_txt = ' | **{:.2f}DPP**'.format(
                    float(droid_calc_info['extra_info']['play_pp']))
            except:
                pass

        pot_txt = ''
        if calc_info != None:
            if 'extra_info' in calc_info and gamemode == 0 and \
                ('max_combo' in calc_info and calc_info['max_combo'] is not None) and \
                (int(userrecent['count_miss']) >= 1 or (int(userrecent['max_combo']) <= 0.96*int(calc_info['max_combo']) and 'S' in userrecent['rank'])) and \
                (abs(play_pp - float(calc_info['extra_info']['fc_pp'])) > 3):

                pot_txt = '**{:.2f}PP**{} ({:.2f}PP for {:.2f}% FC)'.format(
                    play_pp, droid_pp_txt,
                    float(calc_info['extra_info']['fc_pp']), 
                    float(calc_info['extra_info']['fc_acc']))
            elif 'S' in userrecent['rank'] or 'X' in userrecent['rank'] :
                pot_txt = '**{:.2f}PP**{}'.format(play_pp, droid_pp_txt)
            else:
                try:
                    pot_txt = '**{:.2f}PP**{} ({:.2f}PP for {:.2f}% FC)'.format(
                        play_pp, droid_pp_txt,
                        float(calc_info['extra_info']['fc_pp']), 
                        float(calc_info['extra_info']['fc_acc']))
                except:
                    pot_txt = '**{:.2f}PP**{} (_Unofficial_)'.format(
                        play_pp, droid_pp_txt)

        # define acc text
        if gamemode == 3:
            if float(userrecent['count_300']) != 0:
                ratio_300 = float(userrecent['count_geki'])/float(userrecent['count_300'])
                acc_txt = '{:.2f}% ▸ {:.2f}:1'.format(round(acc, 2), ratio_300)
            else:
                acc_txt = '{:.2f}% ▸ ∞:1'.format(round(acc, 2))
        else:
            acc_txt = '{:.2f}%'.format(round(acc, 2))

        info += "▸ **{}** ▸ {} ▸ {}\n".format(
            self.RANK_EMOTES[userrecent['rank']], pot_txt, acc_txt)

        max_combo_den_str = '/{}'.format(str(beatmap['max_combo']))
        if 'none' in str(beatmap['max_combo']).lower() or \
            str(beatmap['max_combo']) == '0':
            max_combo_den_str = ''

        info += "▸ {:,} ▸ x{}{} ▸ {}\n".format(
            int(userrecent['score']),
            userrecent['max_combo'], max_combo_den_str,
            self._get_score_breakdown(userrecent, gamemode))

        # form map completion
        if 'extra_info' in calc_info and \
            'map_completion' in calc_info['extra_info'] and \
            calc_info['extra_info']['map_completion'] != 100 and not graph:
            info += "▸ **Map Completion:** {:.2f}%".format(calc_info['extra_info']['map_completion'])

        # graph, if needed
        if userrecent['rank'] == 'F' and calc_info and graph:
            # print(beatmap)
            color, color_text = self._determine_status_color(beatmap['status'])
            color = '#{}'.format('{:02X}'.format(color).rjust(6, '0'))
            beatmap_chunks = await self.owoAPI.get_beatmap_chunks(
                beatmap, bmp_file_path)
            graph_file, graph_url = await map_utils.plot_map_stars(
                beatmap_chunks, calc_info, color=color)
        else:
            graph_file, graph_url = (None, None)

        # print(calc_info)
        if gamemode == 0:
            star_str, _ = self.compare_val_params(calc_info, 'difficulty_rating', 'stars_mod', 
                precision=2, single=True)
        else:
            star_str = self.adjust_val_str_mod(
                calc_info, "difficulty_rating", enabled_mods, gamemode)
        star_str = '{}★'.format(star_str)
        star_str = self._fix_star_arrow(star_str)

        em = discord.Embed(description=info, colour=server_user.colour)
        em.set_author(name="{} [{}]{} +{} [{}]".format(beatmap['title'], beatmap['version'],
            self._get_keys(beatmap, gamemode, beatmap['version']), 
            utils.fix_mods(''.join(mods)), star_str), 
            url=beatmap_url, icon_url=profile_url)

        # print('GRAPH URL ', graph_url) # **
        if graph and graph_file is not None and graph_url is not None:
            em.set_image(url=graph_url)
        else:
            em.set_thumbnail(url=beatmap_image_url)

        try:
            play_time = datetime.datetime.strptime(userrecent['date'], '%Y-%m-%d %H:%M:%S')
        except:
            play_time = datetime.datetime.strptime(userrecent['date'], '%Y-%m-%dT%H:%M:%S+00:00')
        
        try:
            timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=0)
        except:
            try:
                timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=2)
            except:
                timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=8)

        attempt = ""
        if attempt_num:
            attempt = "Try #{} | ".format(attempt_num)

        server_name = self.owoAPI.get_server_name(api)
        server_icon_url = self.owoAPI.get_server_avatar(api)
        em.set_footer(text = "On osu! {} Server".format(server_name),
            icon_url=self.owoAPI.get_server_avatar(api))

        em.set_footer(text = "{}{}Ago On osu! {} Server".format(attempt, timeago, server_name),
            icon_url=server_icon_url)

        return (msg, em, graph_file)


    def _get_attempt_num(self, recents, mode = 0, beatmap_id = None):
        # if beatmap_id is none, we assume that it's the most recent map
        try_count = 0

        check_id = recents[0]["beatmap_id"]
        if beatmap_id:
            check_id = beatmap_id

        found_first = False
        for recent in recents:
            if recent["beatmap_id"] == check_id:
                found_first = True
                try_count += 1
            elif found_first:
                break

        return try_count


    async def _get_discord_id(self, username:str, api='bancho'):
        name_type = "{}_username".format(api)
        user = await self.players.find_one({name_type:username})
        if user:
            return user['user_id']
        return -1


    # ------------------------ top plays --------------------------
    # Gets information to proccess the top play version of the image
    async def process_user_top(self, ctx, inputs, gamemode: int):
        channel = ctx.message.channel
        user = ctx.message.author
        server = ctx.message.guild

        # update server info
        await self.update_user_servers_list(user, server)

        db_user = await self.get_user(user)

        try:
            outputs, server_options = self.server_option_parser(inputs)
            api = self.determine_api(server_options, db_user=db_user)

            option_parser = OptionParser()
            option_parser.add_option('i',   'index',        opt_type='range',   default=None)
            option_parser.add_option('r',   'recent',       opt_type=None,      default=False)
            option_parser.add_option('m',   'mods',         opt_type=str,       default=None)
            option_parser.add_option('mx',  'mods_ex',      opt_type=str,       default=None) 
            option_parser.add_option('rk',  'rank',         opt_type=None,      default=False)
            option_parser.add_option('sc',  'score',        opt_type=None,      default=False)
            option_parser.add_option('acc', 'acc',          opt_type=None,      default=False)
            option_parser.add_option('c',   'combo',        opt_type=None,      default=False)
            option_parser.add_option('nc',  'no_choke',     opt_type=None,      default=False)
            option_parser.add_option('rev', 'reverse',      opt_type=None,      default=False)
            option_parser.add_option('g',   'greater',      opt_type=float,     default=None)
            option_parser.add_option('p',   'page',         opt_type=int,       default=1)
            option_parser.add_option('?',   'search',       opt_type=str,       default=None)
            option_parser.add_option('im',  'image',        opt_type=None,      default=False)
            option_parser.add_option('10',  'cond_10',      opt_type=None,      default=False)
            option_parser.add_option('wif', 'wif',          opt_type=float,     default=None)        
            option_parser.add_option('u',   'user',         opt_type=None,      default=False)
            usernames, options = option_parser.parse(outputs)
        except:
            await ctx.send("**Please check your inputs for errors!**")

        # get rid of duplicates initially
        usernames = list(set(usernames))
        if not usernames: # if still empty, then use self + account
            usernames = [None]

        # gives the final input for osu username
        final_usernames = []
        for username in usernames:
            test_username = await self.process_username(ctx, username, 
                api=api, force_username=options['user'])
            if test_username is not None:
                final_usernames.append(test_username)
        if not final_usernames:
            return await ctx.send("**No players found.**")
        final_usernames = list(set(final_usernames)) # get rid of duplicates

        embed_list = [] # final list to display
        for username in final_usernames[:3]:
            # get info, get from website if api is official
            userinfo = await self.owoAPI.get_user(username, mode=gamemode, api=api)
            try:
                userinfo = userinfo[0]
            except:
                await ctx.send('**`{}` not found in `{}`.**'.format(
                    username, self.owoAPI.get_server_name(api)))
                continue

            try:
                if options['cond_10']:
                    num_per_page = 15
                else:
                    num_per_page = self.LIST_MAX 
                top_limit = 50
                if int(options['page']) * int(num_per_page) > 50 or \
                    (options['index'] and int(options['index'][0]) > 50):
                    top_limit = 100
                if any(options[o_type] for o_type in \
                    ['rank', 'recent', 'combo', 'acc', 'score']):
                    top_limit = 100
                if options['search'] or options['greater'] or options['wif'] or \
                    options['mods'] or options['mods_ex']:
                    top_limit = 100
            except:
                return await ctx.send('**Please check your input options.**')
                
            try:
                if options['no_choke']:
                    if gamemode != 0 or api != 'bancho':
                        return await ctx.send("**No-choke calculation not available for specified options.**")

                    full_play_list = await self.owoAPI.get_user_best_no_choke(
                        userinfo['user_id'], mode=gamemode, api=api)
                else:
                    full_play_list = await self.owoAPI.get_user_best(
                        userinfo['user_id'], mode=gamemode, limit=top_limit, api=api)
            except:
                await ctx.send('**`{}` not found in `{}`.**'.format(
                    username, self.owoAPI.get_server_name(api)))
                continue

            # print('RETURN RESPONSE ', full_play_list)

            if not username:
                return
            elif not userinfo or not full_play_list:
                return await ctx.send("**`{}` was not found or not enough plays in `{}`.**".format(
                    username, self.owoAPI.get_server_name(api)))

            # generate new fields for index and other
            rank_order = ['SSH','SSHD','XH','SS','X','SH','SHD','S','A','B','C','D']
            rank_order = rank_order[::-1]
            for i, score in enumerate(full_play_list):
                full_play_list[i]['play_idx'] = i+1
                full_play_list[i]['letter_rank_num'] = rank_order.index(full_play_list[i]['rank'])

                if 'accuracy' not in full_play_list[i].keys():
                    full_play_list[i]['accuracy'] = utils.calculate_acc(full_play_list[i], gamemode)
            

            # filtering/get the approrpiate indices
            indices = None
            if options['index']: # grab the index
                score_type = 'Number'
                indices = self._parse_index_option(full_play_list, options['index'])
            elif options['search']:
                score_type = 'Found'
                indices = self._get_play_search(full_play_list, options['search'])
                if not indices:
                    return await ctx.send('**No plays found!**')
            elif options['mods'] or options['mods_ex']: # filter by mods, mods_ex means exclusive
                score_type = 'Filtered'
                indices = []
                if options['mods']:
                    input_mods_list = utils.str_to_mod(options['mods'])
                elif options['mods_ex']:
                    input_mods_list = utils.str_to_mod(options['mods_ex'])

                for idx, score in enumerate(full_play_list):
                    score_mods_list = utils.num_to_mod(score['enabled_mods'])
                    if options['mods']:
                        if set(input_mods_list).issubset(set(score_mods_list)):
                            indices.append(idx)
                    elif options['mods_ex']:
                        if set(input_mods_list) == set(score_mods_list):
                            indices.append(idx)
            else: # or just grab all of them
                score_type = 'Top'
                indices = list(range(len(full_play_list)))

            if options['wif'] is not None:
                query_pp = float(options['wif'])

                old_pp_list = [play['pp'] for play in full_play_list]
                new_pp_list = [play['pp'] for play in full_play_list]
                new_pp_list.append(query_pp)
                new_pp_list = sorted(new_pp_list, reverse=True)[0:100]

                old_total_pp = float(userinfo['pp_raw'])
                new_play_idx = 0
                old_weighted_pp = 0
                new_weighted_pp = 0
                new_pp_weighted = 0
                found_index = False
                for play_idx, pp_val in enumerate(old_pp_list):
                    # old_unweighted_pp = float(old_pp_list[play_idx])
                    old_weighted_pp += float(old_pp_list[play_idx]) * 0.95 ** play_idx

                    # new_unweighted_pp = float(new_pp_list[play_idx])
                    new_weighted_pp += float(new_pp_list[play_idx]) * 0.95 ** play_idx

                    if pp_val <= query_pp and not found_index:
                        new_play_idx = play_idx
                        new_pp_weighted = query_pp * 0.95 ** new_play_idx
                        found_index = True

                if found_index:
                    pp_diff = new_weighted_pp-old_weighted_pp
                    return await ctx.send(
                        "**A score of `{:,.2f}pp` (`{:,.2f}pp` weighted) for `{}` would be their `#{}` top play and "\
                        "increase their total to `{:,.2f}pp` (`+{:,.2f}`).**".format(
                            round(query_pp, 2), new_pp_weighted, 
                            userinfo['username'], new_play_idx+1, 
                            old_total_pp+pp_diff, pp_diff))
                else:
                    return await ctx.send(
                        "**This would not be a top play for `{}` and their total pp would not change.**".format(
                            userinfo['username']))                  


            # get the filtered list of plays
            target_attr = 'acc'
            filtered_full_play_list = [full_play_list[i] for i in indices]
            # handle options for sorting
            if options['rank'] and options['recent']:
                score_type = 'Sorted (Rank) Recent'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('letter_rank_num', 'date'), reverse=True)
            elif options['rank'] and options['score']:
                target_attr = 'score'
                score_type = 'Sorted (Rank/Score)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('letter_rank_num', 'score'), reverse=True)
            elif options['rank'] and options['acc']:
                score_type = 'Sorted (Rank/Acc)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('letter_rank_num', 'accuracy'), reverse=True)
            elif options['rank'] and options['combo']:
                target_attr = 'max_combo'
                score_type = 'Sorted (Rank/Max Combo)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('letter_rank_num', 'max_combo'), reverse=True)
            elif options['recent']:
                score_type = 'Recent Top'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('date'), reverse=True)              
            elif options['rank']:
                score_type = 'Sorted (Rank)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('letter_rank_num'), reverse=True)
            elif options['acc']:
                score_type = 'Sorted (Acc)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('accuracy'), reverse=True)
            elif options['combo']:
                target_attr = 'max_combo'
                score_type = 'Sorted (Max Combo)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('max_combo'), reverse=True)
            elif options['score']:
                target_attr = 'score'
                score_type = 'Sorted (Score)'
                filtered_full_play_list = sorted(filtered_full_play_list, 
                    key=operator.itemgetter('score'), reverse=True)

            if options['reverse']:
                score_type = 'Reverse-' + score_type
                filtered_full_play_list = filtered_full_play_list[::-1]
            
            if options['greater']: # count how in filtered list are above pp criteria
                greater_than = float(options['greater'])
                counter = 0
                for idx, score in enumerate(filtered_full_play_list):
                    if float(score['pp']) >= greater_than:
                        counter += 1
                return await ctx.send("**`{}` has {} plays worth more than {}PP**".format(
                    username, str(counter), greater_than))

            # if check user wants to draw an image first
            if options['image']:
                if self.bot.is_production:
                    donor_ids = await self.bot.patreon.get_donors_list()
                    if str(user.id) not in donor_ids:
                        return await ctx.send("**You must be a supporter to use this feature! `>support`**")

                beatmap = await self.owoAPI.get_beatmap(
                    filtered_full_play_list[0]['beatmap_id'], api=api)

                enabled_mods = 0
                if 'enabled_mods' in filtered_full_play_list[0].keys():
                    enabled_mods = int(filtered_full_play_list[0]['enabled_mods'])
                elif 'mods' in filtered_full_play_list[0].keys():
                    enabled_mods = utils.mod_to_num(''.join(filtered_full_play_list[0]['mods']))

                # download the beatmap image
                beatmap_image_file = await self.owoAPI.get_full_beatmapset_image(beatmap[0]['beatmapset_id'])
                beatmap_info, _, bmp_filepath = await self.owoAPI.get_full_beatmap_info(beatmap[0], 
                    mods=enabled_mods, extra_info={'play_info': filtered_full_play_list[0]})
                beatmap_chunks = await self.owoAPI.get_beatmap_chunks(beatmap[0], bmp_filepath)
                return await drawing.draw_score(ctx, userinfo, filtered_full_play_list[0],
                    beatmap_info, gamemode, bmp_chunks=beatmap_chunks, 
                    beatmap_image_file=beatmap_image_file)

            # another check for length
            if options['cond_10']:
                max_length = min(10, len(filtered_full_play_list))
            else:
                max_length = min(self.LIST_MAX, len(filtered_full_play_list))

            # handle page. page defaults to 1
            total_entries = len(filtered_full_play_list) # before page
            page = int(options['page'])
            start_idx = (page-1) * max_length
            end_idx = (page) * max_length
            if api != 'bancho' or not options['cond_10']:
                filtered_full_play_list = filtered_full_play_list[start_idx:end_idx]

            # only get full beatmap if we want the slightly more detailed version
            best_beatmaps = []
            test_full_play_list = [] # in the event grabbing beatmaps fail. happens for droid a lot
            
            if api == 'bancho': # temporary!!!! DELETE LATER ***** !!!!
                use_cache = True
            else:
                use_cache = False

            for i in range(len(filtered_full_play_list)):
                # print(filtered_full_play_list[i].keys())
                try:
                    if 'beatmap' in filtered_full_play_list[i] and \
                        'beatmapset' in filtered_full_play_list[i]:
                        beatmapset = filtered_full_play_list[i]['beatmapset']
                        beatmap = filtered_full_play_list[i]['beatmap']

                        # combine
                        beatmap.update(beatmapset)
                        beatmap = [beatmap]
                    else:
                        beatmap = await self.owoAPI.get_beatmap(
                            filtered_full_play_list[i]['beatmap_id'], 
                            api=api, use_cache=use_cache) # force
                        await asyncio.sleep(self.SLEEP_TIME)

                    best_beatmaps.append(beatmap[0])
                    test_full_play_list.append(filtered_full_play_list[i])
                except:
                    pass

            filtered_full_play_list = test_full_play_list

            if len(filtered_full_play_list) == 0:
                return await ctx.send("**No plays found.**")  

            # depending on how many plays there are, do different embed
            if score_type == 'Number':
                # print(indices)
                header_num = '{}'.format(indices[0]+1)
                if indices[0] != indices[-1]:
                    header_num += '-{}'.format(indices[-1]+1)
            else:
                header_num = len(filtered_full_play_list)

            no_choke_header = ' '
            if options['no_choke']:
                no_choke_header = ' No-Choke '

            header_txt = "{} {}{}{} Play{} for {}".format(score_type,
                header_num, no_choke_header, utils.get_gamemode_text(gamemode), 
                self._plural_text(filtered_full_play_list), userinfo['username'])
            total_pages = math.ceil(total_entries/max_length)
            page_info = (page, total_pages)
            if options['cond_10']:
                if api == 'bancho': # make a list since we have all the beatmaps
                    embed_list = []
                    for page_idx in range(total_pages):
                        # print(page_idx)
                        start_idx = (page_idx-1) * max_length
                        end_idx = (page_idx) * max_length
                        # print(start_idx, end_idx)
                        play_list_part = filtered_full_play_list[start_idx:end_idx]
                        best_maps_part = best_beatmaps[start_idx:end_idx]
                        page_info = (page_idx, total_pages)
                        embed = await self.create_condensed_play_list_embed(
                            ctx, userinfo, play_list_part, best_maps_part, gamemode, 
                            api=api, header_txt=header_txt, 
                            page_info=page_info, var_attr=target_attr)
                        embed_list.append(embed)

                    try:
                        return await self.bot.menu(ctx, embed_list, page=page, timeout=30)
                    except:
                        pass 
                else:
                    embed = await self.create_condensed_play_list_embed(
                        ctx, userinfo, filtered_full_play_list, best_beatmaps, gamemode, 
                        api=api, header_txt=header_txt, page_info=page_info, 
                        var_attr=target_attr)
                    return await ctx.send(embed=embed)  

            else:
                if options['no_choke']:
                    msg, embed = await self.create_no_choke_list_embed(
                        ctx, userinfo, filtered_full_play_list, best_beatmaps, gamemode, 
                        api=api, header_txt=header_txt, page_info=page_info)
                else:
                    msg, embed = await self.create_play_list_embed(
                        ctx, userinfo, filtered_full_play_list, best_beatmaps, gamemode, 
                        api=api, header_txt=header_txt, page_info=page_info)
                return await ctx.send(msg, embed=embed)


    # Gives a user profile image with some information
    async def create_condensed_play_list_embed(self, ctx, 
        user, plays, beatmaps, gamemode, api='bancho', header_txt=None, page_info=None, 
        var_attr='acc'):
        server_user = ctx.message.author
        server = ctx.message.guild

        avatar_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        gamemode_text = utils.get_gamemode_text(gamemode)

        desc = ''
        # takes in the processed userbest
        for i in range(len(plays)):
            # handle mods
            # print('Play info', plays[i]) # **
            if api == 'droid':
                mod_num = 0
            else:
                mod_num = int(plays[i]['enabled_mods'])
                # print('mod num', mod_num)

            mods_list = utils.num_to_mod(mod_num)
            if not mods_list:
                mods_list.append('NM')

            # generate values
            title_txt = '{}'.format(self._truncate_text(beatmaps[i]['title'], 30))
            version_trun_len = 50 - len(title_txt) - 12
            version_txt = '[{}]'.format(self._truncate_text(beatmaps[i]['version'], version_trun_len))
            full_map_txt = '{} {}'.format(title_txt, version_txt)
            number_txt = '{}'.format(str(plays[i]['play_idx']))

            """
            if 'stars_mod' in full_beatmap_info.keys():
                star_str = '{:.2f}'.format(float(full_beatmap_info['stars_mod']))
            else:
                star_str = '{:.2f}'.format(float(full_beatmap_info['difficulty_rating']))
            """

            # variable attrs
            # calculate accuracy if needed, depends on api
            if 'accuracy' not in plays[i]:
                acc = utils.calculate_acc(plays[i], gamemode)
            else:
                acc = plays[i]['accuracy']

            if 'max_combo' in plays[i]:
                max_combo_txt = 'x{:,}'.format(int(plays[i]['max_combo']))
            else:
                max_combo_txt = ''
            acc_txt = '{:.2f}%'.format(float(acc))
            score_txt = '{:,}'.format(int(plays[i]['score']))

            if var_attr == 'max_combo':
                var_txt = max_combo_txt
            elif var_attr == 'score':
                var_txt = score_txt
            else:
                var_txt = acc_txt

            # other components
            rank_txt = '{}'.format(self.RANK_EMOTES[plays[i]['rank']])
            misses_txt = '{}m'.format(plays[i]['count_miss'])
            mods_txt = '+{}'.format(utils.fix_mods(''.join(mods_list)))

            is_spaced = True
            if gamemode == 3:
                is_spaced = False
            score_breakdown = self._get_score_breakdown(plays[i], gamemode, spaced=is_spaced)

            # print('Play ', plays[i]) # **
            if 'pp' in plays[i] and plays[i]['pp'] is not None and \
                float(plays[i]['pp']) != 0:
                pp_txt = '{:}pp'.format(round(plays[i]['pp']))
            else: # otherwise calculate play pp (like for recent/failed)
                # play_pp = round(full_beatmap_info['extra_info']['play_pp'])
                pp_txt = '-pp'# .format(play_pp)

            play_time = datetime.datetime.strptime(plays[i]["date"], '%Y-%m-%d %H:%M:%S')
            try:
                timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, 
                    shift=0, abbr=True)
            except:
                try:
                    timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, 
                        shift=2, abbr=True)
                except:
                    timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, 
                        shift=8, abbr=True)
            timeago += ' ago'

            # put the information together
            info = '`{:<3}`{}`{:<42}{:<10}`\n`{:<3}{:<28}{:<9}{:<8}{:<10}`\n'.format(
                number_txt, rank_txt, full_map_txt, mods_txt, 
                '▸', score_breakdown, var_txt, pp_txt, timeago)

            desc += info

        em = discord.Embed(description=desc, colour=server_user.colour)
        # online_status = await self._get_online_icon(user, api)
        sort_txt = ""
        title = header_txt
        page_txt = ''
        if page_info:
            page_txt = ' | Page {} of {}'.format(page_info[0], page_info[1])
        profile_link_url = self.owoAPI.get_user_url(user['user_id'], api=api)
        server_name = self.owoAPI.get_server_name(api)
        em.set_author(name = title, url=profile_link_url, icon_url=flag_url)
        em.set_footer(text = "On osu! {} Server{}".format(server_name, page_txt),
            icon_url=self.owoAPI.get_server_avatar(api))
        em.set_thumbnail(url=avatar_url)
        return em


    # Gives a user profile image with some information
    async def create_play_list_embed(self, ctx, 
        user, plays, beatmaps, gamemode, api='bancho', header_txt=None, page_info=None):
        server_user = ctx.message.author
        server = ctx.message.guild

        avatar_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        gamemode_text = utils.get_gamemode_text(gamemode)

        msg = ''
        desc = ''
        # takes in the processed userbest
        for i in range(len(plays)):
            # handle mods
            mod_num = int(plays[i]['enabled_mods'])

            mods_list = utils.num_to_mod(mod_num)
            if not mods_list:
                mods_list.append('No Mod')
            # print('mod list', mods_list)

            beatmap_url = self.owoAPI.get_beatmap_url(beatmaps[i])

            extra_info = {}
            extra_info['play_info'] = plays[i]
            # print('test 3') # **
            try:
                # print(beatmaps[i])
                full_beatmap_info, bmap_raw, bmap_file_path = await self.owoAPI.get_full_beatmap_info(
                    beatmaps[i], extra_info=extra_info, mods=mod_num)
            except: # if the beatmap not longer exists
                # print(sys.exc_info())
                continue

            # print(full_beatmap_info)

            info = ''
            # generate the title portion
            if 'Number' not in header_txt or len(plays) != 1:
                number_txt = '{}. '.format(str(plays[i]['play_idx']))
            else:
                number_txt = ''

            if gamemode == 0:
                if 'stars_mod' in full_beatmap_info.keys():
                    star_str = '{:.2f}'.format(float(full_beatmap_info['stars_mod']))
                else:
                    star_str = '{:.2f}'.format(float(full_beatmap_info['difficulty_rating']))
            else:
                star_str = self.adjust_val_str_mod(
                    full_beatmap_info, "difficulty_rating", 
                    int(plays[i]['enabled_mods']), gamemode)
            star_str = '{}★'.format(star_str)
            star_str = self._fix_star_arrow(star_str)

            title_txt = '**{}[{} [{}]{}]({}) +{}** [{}]\n'.format(
                number_txt , beatmaps[i]['title'].replace('*','\*'),
                beatmaps[i]['version'].replace('*','\*'), 
                self._get_keys(beatmaps[i], gamemode, beatmaps[i]['version']),
                beatmap_url, utils.fix_mods(''.join(mods_list)), star_str)
            info += title_txt

            # create details section
            choke_text = '' # choke text
            # if there is a max combo available in the beatmap, compare with play.
            if (('max_combo' in full_beatmap_info) and \
                ('extra_info' in full_beatmap_info and full_beatmap_info['extra_info']) and \
                ('fc_pp' in full_beatmap_info['extra_info']) and \
                (full_beatmap_info['max_combo'] is not None)) and \
                (gamemode == 0) and \
                (int(plays[i]['count_miss']) >= 1 or (int(plays[i]['max_combo']) <= 0.95*int(full_beatmap_info['max_combo']) and 'S' in plays[i]['rank'])):
                choke_text += ' _({:.2f}pp for FC)_'.format(full_beatmap_info['extra_info']['fc_pp'])

            # max combo text
            max_combo_txt = 'x{:,}/{:,}'.format(
                int(plays[i]['max_combo']), int(full_beatmap_info['max_combo'])) \
                if 'max_combo' in full_beatmap_info and full_beatmap_info['max_combo'] \
                    else "x{:,}".format(int(plays[i]['max_combo']))

            # add droid pp if necessary
            droid_pp_txt = ''
            if api == 'droid':
                try:
                    droid_calc_info, _, _ = await self.owoAPI.get_full_beatmap_info(
                        beatmaps[i], extra_info=extra_info, mods=mod_num, api='droid')
                    droid_pp_txt = ' | **{:.2f}DPP**'.format(
                        float(droid_calc_info['extra_info']['play_pp']))
                except:
                    pass

            # check if pp is in plays
            # print('Play ', plays[i]) # **
            if 'pp' in plays[i] and plays[i]['pp'] is not None and \
                float(plays[i]['pp']) != 0:
                pp_txt = '**{:.2f}PP**{}{}'.format(float(plays[i]['pp']), 
                    droid_pp_txt, choke_text)
            elif 'extra_info' in full_beatmap_info: # otherwise calculate play pp (like for recent/failed)
                play_pp = float(full_beatmap_info['extra_info']['play_pp'])
                pp_txt = '**{:.2f}PP**{} (_Unofficial_)'.format(
                    play_pp, droid_pp_txt)
            else:
                pp_txt = '**-PP**{} (_Unofficial_)'.format(droid_pp_txt)

            # calculate accuracy if needed, depends on api
            if 'accuracy' not in plays[i]:
                acc = utils.calculate_acc(plays[i], gamemode)
            else:
                acc = plays[i]['accuracy']

            # define acc text
            if gamemode == 3:
                if float(plays[i]['count_300']) != 0:
                    ratio_300 = float(plays[i]['count_geki'])/float(plays[i]['count_300'])
                    acc_txt = '{:.2f}% ▸ {:.2f}:1'.format(round(acc, 2), ratio_300)
                else:
                    acc_txt = '{:.2f}% ▸ ∞:1'.format(round(acc, 2))
            else:
                acc_txt = '{:.2f}%'.format(round(acc, 2))

            info += '▸ **{}** ▸ {} ▸ {}\n'.format(
                self.RANK_EMOTES[plays[i]['rank']], pp_txt, acc_txt)
            info += '▸ {:,} ▸ {} ▸ {}\n'.format(
                int(plays[i]['score']), max_combo_txt,
                self._get_score_breakdown(plays[i], gamemode))

            # whatever this mess is. deals with displaying time
            play_time = datetime.datetime.strptime(plays[i]["date"], '%Y-%m-%d %H:%M:%S')
            try:
                timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=0)
            except:
                try:
                    timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=2)
                except:
                    timeago = utils.time_ago(datetime.datetime.utcnow(), play_time, shift=8)

            info += '▸ Score Set {}Ago\n'.format(timeago)
            desc += info

        em = discord.Embed(description=desc, colour=server_user.colour)
        # online_status = await self._get_online_icon(user, api)
        title = header_txt
        page_txt = ''
        if page_info:
            page_txt = ' | Page {} of {}'.format(page_info[0], page_info[1])
        profile_link_url = self.owoAPI.get_user_url(user['user_id'], api=api)
        server_name = self.owoAPI.get_server_name(api)
        em.set_author(name = title, url=profile_link_url, icon_url=flag_url)
        em.set_footer(text = "On osu! {} Server{}".format(server_name, page_txt),
            icon_url=self.owoAPI.get_server_avatar(api))
        em.set_thumbnail(url=avatar_url)
        return (msg, em)


    # Gives a user profile image with some information
    async def create_no_choke_list_embed(self, ctx, 
        user, plays, beatmaps, gamemode, api='bancho', header_txt=None, page_info=None):
        server_user = ctx.message.author
        server = ctx.message.guild

        avatar_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        flag_url = self.owoAPI.get_country_flag_url(user['country'])
        gamemode_text = utils.get_gamemode_text(gamemode)

        msg = ''
        desc = ''
        # takes in the processed userbest
        for i in range(len(plays)):
            # handle mods
            mod_num = int(plays[i]['enabled_mods'])

            mods_list = utils.num_to_mod(mod_num)
            if not mods_list:
                mods_list.append('No Mod')
            # print('mod list', mods_list)

            beatmap_url = self.owoAPI.get_beatmap_url(beatmaps[i])

            extra_info = {}
            extra_info['play_info'] = plays[i]
            # print('test 3') # **
            try: # unfortunately, have to calculate this again
                # print(beatmaps[i])
                full_beatmap_info, bmap_raw, bmap_file_path = await self.owoAPI.get_full_beatmap_info(
                    beatmaps[i], extra_info=extra_info, mods=mod_num)
            except: # if the beatmap not longer exists
                # print(sys.exc_info())
                continue

            # print(full_beatmap_info)

            info = ''
            # generate the title portion
            if 'Number' not in header_txt or len(plays) != 1:
                number_txt = '{} `[{}]`. '.format(
                    str(plays[i]['play_idx']), str(plays[i]['original_idx']))
            else:
                number_txt = ''

            if gamemode == 0:
                if 'stars_mod' in full_beatmap_info.keys():
                    star_str = '{:.2f}'.format(float(full_beatmap_info['stars_mod']))
                else:
                    star_str = '{:.2f}'.format(float(full_beatmap_info['difficulty_rating']))
            else:
                star_str = self.adjust_val_str_mod(
                    full_beatmap_info, "difficulty_rating", 
                    int(plays[i]['enabled_mods']), gamemode)

            title_txt = '**{}[{} [{}]{}]({}) +{}** [{}★]\n'.format(
                number_txt , beatmaps[i]['title'].replace('*','\*'),
                beatmaps[i]['version'].replace('*','\*'), 
                self._get_keys(beatmaps[i], gamemode, beatmaps[i]['version']),
                beatmap_url, utils.fix_mods(''.join(mods_list)), star_str)
            info += title_txt

            if plays[i]['original'] is not None:
                # max combo text
                max_combo_txt = 'x{:,} ➔ **x{:,}**/{:,}'.format(
                    int(plays[i]['original']['max_combo']), 
                    int(plays[i]['max_combo']), 
                    int(plays[i]['max_combo']))
                pp_txt = '{:.2f} ➔ **{:.2f}PP**'.format(
                    float(plays[i]['original']['pp']), 
                    float(plays[i]['pp']))
                acc_txt = '{:.2f}% ➔ **{:.2f}%**'.format(
                    round(plays[i]['original']['accuracy'], 2), round(plays[i]['accuracy'], 2))
                info += '▸ {} ➔ **{}** ▸ {} ▸ {}\n'.format(
                    self.RANK_EMOTES[plays[i]['original']['rank']], 
                    self.RANK_EMOTES[plays[i]['rank']], pp_txt, acc_txt)
                info += '▸ {} ▸ {} ➔ **{}**\n'.format(
                    max_combo_txt,
                    self._get_score_breakdown(plays[i]['original'], gamemode),
                    self._get_score_breakdown(plays[i], gamemode))
            else:
                # max combo text
                max_combo_txt = 'x{:,}/{:,}'.format(
                    int(plays[i]['max_combo']), 
                    int(bmap_raw.max_combo()))
                pp_txt = '{:.2f}PP'.format(
                    float(plays[i]['pp']))
                acc_txt = '{:.2f}%'.format(
                    round(plays[i]['accuracy'], 2))
                info += '▸ {} ▸ {} ▸ {}\n'.format(
                    self.RANK_EMOTES[plays[i]['rank']], pp_txt, acc_txt)
                info += '▸ {} ▸ {}\n'.format(
                    max_combo_txt,
                    self._get_score_breakdown(plays[i], gamemode))

            desc += info

        em = discord.Embed(description=desc, colour=server_user.colour)
        # online_status = await self._get_online_icon(user, api)
        title = header_txt
        page_txt = ''
        if page_info:
            page_txt = ' | Page {} of {}'.format(page_info[0], page_info[1])
        profile_link_url = self.owoAPI.get_user_url(user['user_id'], api=api)
        server_name = self.owoAPI.get_server_name(api)
        em.set_author(name = title, url=profile_link_url, icon_url=flag_url)
        em.set_footer(text = "On osu! {} Server{}".format(server_name, page_txt),
            icon_url=self.owoAPI.get_server_avatar(api))
        em.set_thumbnail(url=avatar_url)
        return (msg, em)


    def _get_score_breakdown(self, play, gamemode, spaced=False):
        gamemode = int(gamemode)
        if spaced:
            if gamemode == 0 or gamemode == 2:
                ret = "[ {} / {} / {} / {} ]".format(play['count_300'], play['count_100'], play['count_50'], play['count_miss'])
            elif gamemode == 1:
                ret = "[ {} / {} / {} ]".format(play['count_300'], play['count_100'], play['count_miss'])
            elif gamemode == 3:
                ret = "[ {} / {} / {} / {} / {} / {} ]".format(play['count_geki'], play['count_300'],
                    play['count_katu'], play['count_100'], play['count_50'], play['count_miss'])
        else:
            if gamemode == 0 or gamemode == 2:
                ret = "[{}/{}/{}/{}]".format(play['count_300'], play['count_100'], play['count_50'], play['count_miss'])
            elif gamemode == 1:
                ret = "[{}/{}/{}]".format(play['count_300'], play['count_100'], play['count_miss'])
            elif gamemode == 3:
                ret = "[{}/{}/{}/{}/{}/{}]".format(play['count_geki'], play['count_300'],
                    play['count_katu'], play['count_100'], play['count_50'], play['count_miss'])
            
        return ret


    def _get_keys(self, beatmap, gamemode, version):
        # cs is the the key number
        ret = ""
        if gamemode == 3:
            if "{}k".format(beatmap["cs"]) not in version.lower():
                ret = "[{}k] ".format(beatmap["cs"])
        return ret


    async def process_user_score(self, ctx, inputs, 
        beatmapset_id=None, beatmap_id=None, score_id=None, 
        map_gamemode=None, forced_gamemode=None, api=None):

        try:
            channel = ctx.message.channel
            user = ctx.message.author
            server = ctx.message.guild
        except:
            channel = ctx.channel
            user = ctx.author
            server = ctx.guild
        
        # update server info
        await self.update_user_servers_list(user, server)

        db_user = await self.get_user(user)

        # determine parameters
        inputs, cmd_gamemode = self._gamemode_option_parser(inputs) # map gamemode might not be the same
        # print('GAMEMODE 1', cmd_gamemode)

        inputs, server_options = self.server_option_parser(inputs)
        if not api:
            api = self.determine_api(server_options, db_user=db_user)

        # print('SCORE COMMAND API', api)
        try:
            option_parser = OptionParser()
            option_parser.add_option('m',   'mode',         opt_type=int,       default=None)
            option_parser.add_option('?',   'search',       opt_type=str,       default=None)
            option_parser.add_option('i',   'index',        opt_type='range',   default=None)
            option_parser.add_option('mx',  'mods_ex',      opt_type=str,       default=None)
            option_parser.add_option('im',  'image',        opt_type=None,      default=False)
            option_parser.add_option('u',   'user',         opt_type=None,      default=False)
            usernames, options = option_parser.parse(inputs)
        except:
            await ctx.send("**Please check your inputs for errors!**")
        # print('OPTIONS', options)
        # print('MAP SCORE USERNAMES', usernames)

        # gives the final input for osu username
        usernames = list(set(usernames))
        if not usernames: # if still empty, then use self + account
            usernames = [None]
        final_usernames = []
        for username in usernames:
            test_username = await self.process_username(ctx, username, 
                api=api, force_username=options['user'])
            if test_username is not None:
                final_usernames.append(test_username)
        if not final_usernames:
            return await ctx.send("**No players found.**")
        username = await self.process_username(ctx, final_usernames[0], 
            api=api, force_username=options['user'])
        # print('2', usernames)

        # figure out which gamemode to use
        is_gamemode_forced = False
        implied_gamemode = 0
        if forced_gamemode is not None:
            is_gamemode_forced = True
            implied_gamemode = forced_gamemode
        elif cmd_gamemode is not None: # this is a forced option
            is_gamemode_forced = True
            implied_gamemode = int(cmd_gamemode)
            # print('GM 1', implied_gamemode)
        elif options["mode"] is not None: # this is also a forced option, so goes first
            is_gamemode_forced = True
            implied_gamemode = int(options["mode"])
            # print('GM 2', implied_gamemode)
        elif map_gamemode:
            implied_gamemode = int(map_gamemode)
            # print('GM 3', implied_gamemode)
        elif db_user:
            implied_gamemode = int(db_user["default_gamemode"])
            # print('GM 4', implied_gamemode)

        # print('GAMEMODE 2', gamemode)

        # get the appropriate beatmap (at time of writing, 
        # api v2 is lacking docs for getting converts; this is hacky)
        # map_gamemode = int(map_gamemode)

        # print(map_gamemode, gamemode, beatmapset_id, beatmap_id)
        # print(map_gamemode is None, beatmapset_id is None, beatmap_id is not None)
        if api == 'droid':
            get_map_api = 'ripple'
        else:
            get_map_api = api

        if options['search']:
            search_results = await self.owoAPI.map_search(options['search'])
            if not search_results:
                return await ctx.send(":red_circle: **{}, no maps found.**".format(user.mention))

            result = search_results[0]
            beatmap = await self.owoAPI.get_beatmap(result['beatmap_id'], api=get_map_api)
        elif map_gamemode is not None and implied_gamemode != int(map_gamemode) and \
            beatmap_id is not None:

            beatmapset = await self.owoAPI.get_beatmapset(beatmapset_id)
            beatmap = []
            for bmp in beatmapset:
                if (int(bmp['mode']) == int(implied_gamemode)) and \
                    str(beatmap_id) == str(bmp['beatmap_id']):
                    beatmap.append(bmp)
                    break

            if not beatmap:
                return await ctx.send('**Convert not found.**')
        elif map_gamemode is not None and implied_gamemode == int(map_gamemode) and beatmap_id:
            beatmap = await self.owoAPI.get_beatmap(beatmap_id, api=get_map_api)
        elif map_gamemode is None and beatmapset_id is None and beatmap_id:
            beatmap = await self.owoAPI.get_beatmap(beatmap_id, api=get_map_api)
        else:
            return await ctx.send('**Please provide a single beatmap link. (i.e. not beatmap set).**')

        if not beatmap:
            return await ctx.send('**Beatmap was not found!**')            

        # finalize the gamemode
        if not is_gamemode_forced:
            gamemode = int(beatmap[0]['mode'])
        else:
            gamemode = implied_gamemode

        # print('GAMEMODE 2', gamemode)

        # for getting user scores
        # print('BEATMAP INFO', beatmap[0])
        userinfo = await self.owoAPI.get_user(username, mode=gamemode, api=api)

        if not userinfo or userinfo is None:
            return await ctx.send('**User was not found!**')

        if api == 'droid':
            temp_beatmap_id = beatmap[0]['file_md5']
        else:
            temp_beatmap_id = beatmap[0]['beatmap_id']

        try:
            userscores = await self.owoAPI.get_scores(
                temp_beatmap_id, userinfo[0]['user_id'], gamemode, api=api)
        except:
            return await ctx.send('**No scores found for `{}`!**'.format(username))

        # print('SCORES', len(userscores))

        # handle indices
        if options['index']:
            indices = self._parse_index_option(userscores, options['index'])
        elif options['mods_ex']:
            indices = []
            input_mods_list = utils.str_to_mod(options['mods_ex'])
            for idx, score in enumerate(userscores):
                score_mods_list = utils.num_to_mod(score['enabled_mods'])
                if options['mods_ex']:
                    if set(input_mods_list) == set(score_mods_list):
                        indices.append(idx)
        else:
            indices = list(range(len(userscores)))# all of them because we make a menu

        # print('SCORE INDICES', indices)

        if options['image']:
            if self.bot.is_production:
                donor_ids = await self.bot.patreon.get_donors_list()
                if str(user.id) not in donor_ids:
                    return await ctx.send("**You must be a supporter to use this feature! `>support`**")

            if len(indices) > 1:
                return await ctx.send('**Please use the `-im` tag with either an index (e.g. `-i 2`) '
                    'or mod specifier (e.g. `-mx HD`).**')
            else: # create the image
                score = userscores[indices[0]]
                enabled_mods = 0
                if 'enabled_mods' in score.keys():
                    enabled_mods = int(score['enabled_mods'])
                elif 'mods' in score.keys():
                    enabled_mods = utils.mod_to_num(''.join(score['mods']))

                beatmap_image_file = await self.owoAPI.get_full_beatmapset_image(
                    beatmap[0]['beatmapset_id'], beatmap_id=beatmap[0]['beatmap_id'])
                beatmap_info, _, bmp_filepath = await self.owoAPI.get_full_beatmap_info(beatmap[0], 
                    mods=enabled_mods, extra_info={'play_info': score})
                beatmap_chunks = await self.owoAPI.get_beatmap_chunks(beatmap[0], bmp_filepath)
                return await drawing.draw_score(ctx, userinfo[0], score,
                    beatmap_info, gamemode, bmp_chunks=beatmap_chunks, 
                    beatmap_image_file=beatmap_image_file)                

        # otherwise, return
        if userinfo and userscores:
            filtered_scores = [userscores[idx] for idx in indices]
            msg, embeds = await self.create_user_scores_embed(
                ctx, api, userinfo[0], filtered_scores, beatmap[0], gamemode, 
                    indices=indices)
            await self.bot.menu(ctx, embeds, message=msg, page=0, timeout=20)
        else:
            if options['search']:
                full_name = '`{} - {} [{}]` by `{}`'.format(
                    beatmap[0]['artist'], beatmap[0]['title'], 
                    beatmap[0]['version'], beatmap[0]['creator'])
                await ctx.send("**`{}` was not found or no scores on {}.**".format(username, full_name))
            else:
                await ctx.send("**`{}` was not found or no scores on the map.**".format(username))


    def _parse_index_option(self, user_list, idx_options):
        if len(idx_options) == 2 and idx_options[1] is not None: # if it's a range
            start_idx = int(idx_options[0])-1
            end_idx = int(idx_options[1]) # don't -1 because upper bound
            if end_idx < start_idx:
                temp = start_idx
                start_idx = end_idx
                end_idx = temp
            end_idx = min(end_idx, start_idx + self.LIST_MAX)
            indices = list(range(start_idx, end_idx))
        else:
            list_idx = int(idx_options[0])-1 # because starts at 0
            list_idx = max(0, min(list_idx, len(user_list)))
            indices = [list_idx]

        return indices


    def _get_play_search(self, full_play_list, query):
        indices = None
        search_indices = []
        # similarity_idxs = []
        for idx, play in enumerate(full_play_list):
            full_title = None
            if 'beatmapset' in play:
                creator = play['beatmapset']['creator']
                artist = play['beatmapset']['artist']
                title = play['beatmapset']['title']
                version = play['beatmap']['version']
                full_title = '{} {} {} {}'.format(artist, title, version, creator)
            elif 'artist' in play:
                creator = play['creator']
                artist = play['artist']
                title = play['title']
                version = play['version']
                full_title = '{} {} {} {}'.format(artist, title, version, creator)
            elif 'beatmap' in play: # ripple versions
                full_title = play['beatmap']['song_name']

            # full_title similarity
            full_similarity = utils.get_similarity(full_title, query)

            max_word_similarity = 0
            for word in full_title.split(' '):
                word_similarity = utils.get_similarity(word, query)

                if word_similarity > max_word_similarity:
                    max_word_similarity = word_similarity

            similarity = max(max_word_similarity, full_similarity)
            if query.lower() in full_title.lower() or \
                similarity > 0.75:
                search_indices.append(idx)

        if indices is None:
            indices = search_indices
        else:
            indices = set(indices).intersection(set(search_indices))

        return indices


    async def process_username(self, ctx, username, api='bancho', mode=0, force_username=False):
        command_user = ctx.message.author

        # username is a string of the name entered
        # print('Initial', username)

        server_user = None
        if username: # try to find the server user
            # print('USERNAME', username)
            try:
                if username.startswith('<@!') or username.startswith('<@') or username.endswith('>'):
                    discord_user_id = username.replace('<@!', '').replace('<@', '').replace('>','')
                    query_res = await ctx.guild.query_members(
                        user_ids=[int(discord_user_id)])
                elif str(username).isdigit():
                    query_res = await ctx.guild.query_members(
                        user_ids=[int(username)])                
                else:
                    query_res = await ctx.guild.query_members(
                        query=str(username))
            except:
                query_res = None
            
            if query_res:
                # check here for exact match !!!!!
                # server_user = query_res[0]
                for temp_server_user in query_res:
                    if temp_server_user.name == username or \
                        str(temp_server_user.id) in str(username):
                        server_user = temp_server_user
                        break
                # print('Found username in discord server.', server_user.name)

        if not username and not force_username:
            # print("Username not found.")
            # if the username is not provided, assume that the user wants himself
            db_user = await self.get_user(command_user)
            if not db_user:
                # print("Not found in database.", command_user.name)
                # if the user is not found, then try to use their username
                return str(command_user.name)

            # if the user does exist in the database
            # try to find the information based on what they gave
            api = self.remove_api_suffix(api) # should be the same account
            username_key = f"{api}_username"
            if username_key in db_user.keys():
                # if that specific username/api pair was found, return it
                username = db_user[username_key]
                # print("API username found in database.", username)
                if username is None:
                    return None
                else:
                    return str(username)

            # if it wasn't found for specific api, just return the username
            # print("API username not found, using command_user username.")
            return str(command_user.name)

        elif server_user and not force_username:
            # print("Username found in server.")
            # if username correspond to a server user, then try to load their information
            db_user = await self.get_user(server_user)
            if not db_user:
                # print("Server User not found in database.", server_user.name)
                return server_user.name
    
            api = self.remove_api_suffix(api) # should be the same account
            username_key = f"{api}_username"
            if username_key in db_user.keys():
                username = db_user[username_key]
                # print("Server User with specific API found in database.", username)
                return str(username)

            # print("API username not found, Using server_user username.", server_user.name)
            return str(server_user.name)
        elif not server_user and force_username:
            if not username:
                # print("Username found in server. + force username", server_user.name)
                # if username correspond to a server user, then try to load their information
                db_user = await self.get_user(command_user)
                if not db_user:
                    # print("Server User not found in database.", server_user.name)
                    return command_user.name
        
                api = self.remove_api_suffix(api) # should be the same account
                username_key = f"{api}_username"
                if username_key in db_user.keys():
                    username = db_user[username_key]
                    # print("Server User with specific API found in database.", username)
                    return str(username)
            else:
                return str(username)
        else:
            # clean up username for api
            # print("Using entered username.", username)
            return str(username)


    async def create_user_scores_embed(self, ctx, api, user, userscore, beatmap, gamemode, indices=None):
        map_id = beatmap['beatmap_id']

        server_user = ctx.message.author
        server = ctx.message.guild

        profile_url = await self.owoAPI.get_user_avatar(user['user_id'], api)
        gamemode_text = utils.get_gamemode_text(gamemode)

        # convert to floats
        for i in range(len(userscore)):
            try:
                userscore[i]['pp'] = float(userscore[i]['pp'])
            except:
                userscore[i]['score'] = float(userscore[i]['score'])

        # sort the scores based on pp
        try:
            userscore = sorted(userscore, key=operator.itemgetter('pp'), reverse=True)
        except:
            # print(userscore)
            userscore = sorted(userscore, key=operator.itemgetter('score'), reverse=True)

        # get best plays map information and scores
        best_beatmaps = []
        best_acc = []
        pp_sort = []
        for i in range(len(userscore)):
            score = userscore[i]
            best_beatmaps.append(beatmap)
            best_acc.append(utils.calculate_acc(score, gamemode))

        all_plays = []
        mapname = '{} [{}]'.format(
            best_beatmaps[i]['title'],
            best_beatmaps[i]['version'])

        per_page = 3
        embeds = []
        # page system
        pages = math.ceil(len(userscore)/per_page)
        for page in range(pages):
            em = discord.Embed(colour=server_user.colour)
            start_ind = per_page*page
            end_ind = per_page*page + per_page
            if end_ind > len(userscore):
                end_ind = len(userscore)
            desc = ''
            for i in range(start_ind, end_ind):
                beatmap_url = self.owoAPI.get_beatmap_url(best_beatmaps[i])

                info = ''
                mods = utils.num_to_mod(userscore[i]['enabled_mods'])
                if not mods:
                    mods = []
                    mods.append('No Mod')

                # set play info
                extra_info = {}
                # if api != 'droid':
                extra_info['play_info'] = userscore[i]

                # beatmap pp calculation
                bmp_calc, _, _ = await self.owoAPI.get_full_beatmap_info(best_beatmaps[i],
                    accs=[float(best_acc[i])], mods=int(userscore[i]['enabled_mods']), 
                    extra_info=extra_info)

                if gamemode == 0:
                    star_str, _ = self.compare_val_params(bmp_calc, 
                        "difficulty_rating", "stars_mod", precision=2, single=True)
                else:
                    star_str = self.adjust_val_str_mod(
                        bmp_calc, "difficulty_rating", 
                        int(userscore[i]['enabled_mods']), gamemode)
                star_str = '{}★'.format(star_str)
                star_str = self._fix_star_arrow(star_str)

                if indices is not None:
                    list_num = indices[i]+1
                else:
                    list_num = i+1
                info += '**{}. `{}` Score** [{}]\n'.format(
                    list_num, utils.fix_mods(''.join(mods)), star_str)

                # choke text
                # print(bmp_calc) # **

                choke_text = ''
                if (gamemode == 0 and bmp_calc != None and userscore[i]['count_miss'] != None and best_beatmaps[i]['max_combo']!= None) and \
                    (int(userscore[i]['count_miss'])>=1 or (int(userscore[i]['max_combo']) <= 0.95*int(best_beatmaps[i]['max_combo']) and \
                        'S' in userscore[i]['rank'])):
                        choke_text += ' _({:.2f}pp for FC)_'.format(bmp_calc['extra_info']['fc_pp'])
                
                # define acc text
                acc = float(best_acc[i])
                if gamemode == 3:
                    if float(userscore[i]['count_300']) != 0:
                        ratio_300 = float(userscore[i]['count_geki'])/float(userscore[i]['count_300'])
                        acc_txt = '{:.2f}% ▸ {:.2f}:1'.format(round(acc, 2), ratio_300)
                    else:
                        acc_txt = '{:.2f}% ▸ ∞:1'.format(round(acc, 2))
                else:
                    acc_txt = '{:.2f}%'.format(round(acc, 2))


                droid_pp_txt = ''
                if api == 'droid':
                    try:
                        droid_calc_info, _, _ = await self.owoAPI.get_full_beatmap_info(best_beatmaps[i],
                            accs=[float(best_acc[i])], mods=int(userscore[i]['enabled_mods']), 
                            extra_info=extra_info, api='droid')
                        droid_pp_txt = ' | **{:.2f}DPP**'.format(
                            float(droid_calc_info['extra_info']['play_pp']))
                    except:
                        pass

                # print('Play ', plays[i]) # **
                is_official_pp = False
                if 'pp' in userscore[i] and userscore[i]['pp'] is not None and \
                    float(userscore[i]['pp']) != 0:
                    is_official_pp = True
                    pp_val = round(float(userscore[i]['pp']), 2)
                else:
                    pp_val = round(float(bmp_calc['extra_info']['play_pp']), 2)

                if is_official_pp:
                    info += '▸ **{}** ▸ **{:.2f}pp**{}{} ▸ {}\n'.format(
                        self.RANK_EMOTES[userscore[i]['rank']], 
                        pp_val, droid_pp_txt, 
                        choke_text, acc_txt)
                else:
                    info += '▸ **{}** ▸ **{:.2f}pp**{} (_Unofficial_) ▸ {}\n'.format(
                        self.RANK_EMOTES[userscore[i]['rank']], 
                        pp_val, droid_pp_txt, acc_txt)

                combo_denom = ''
                if 'max_combo' in best_beatmaps[i] and best_beatmaps[i]['max_combo'] is not None:
                    combo_denom = '/{:,}'.format(int(best_beatmaps[i]['max_combo']))

                # print('SCORES ', userscore[i]['score'])
                info += '▸ {:,} ▸ x{:,}{} ▸ {}\n'.format(
                    int(userscore[i]['score']), int(userscore[i]['max_combo']), combo_denom,
                    self._get_score_breakdown(userscore[i], gamemode))

                shift = 0
                timeago = utils.time_ago(datetime.datetime.utcnow(),
                    datetime.datetime.strptime(userscore[i]['date'], '%Y-%m-%d %H:%M:%S'), shift=shift)
                info += '▸ Score Set {}Ago\n'.format(timeago)
                desc += info

            em.description = desc
            title = "Top {} Play{} for {} on {}".format(
                gamemode_text, self._plural_text(userscore), user['username'], mapname)
            em.set_author(name = title, url=beatmap_url, icon_url=profile_url)
            footer_addition = " | Page {} of {}".format(page + 1, pages)
            icon_url = self.owoAPI.get_server_avatar(api)
            em.set_footer(text = "On osu! {} Server{}".format(
                self.owoAPI.get_server_name(api), footer_addition), icon_url=icon_url)
            map_image_url = self.owoAPI.get_beatmap_thumbnail(best_beatmaps[0])
            em.set_thumbnail(url=map_image_url)
            embeds.append(em)

        return ("", embeds)


    def _plural_text(self, data_list):
        ret_str = ""
        if isinstance(data_list, list):
            if len(data_list) > 1:
                ret_str = "s"
            return ret_str
        else:
            if data_list > 1:
                ret_str = "s"
            return ret_str


    #--------------------- Suggestion Database Creation/Methods ------------------------
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(no_pm=True, aliases = ['r','rec'])
    async def recommend(self, ctx, *options):
        """
        Get a recommendation for a map. Ranges should follow `x1-x2` format.

        [Options]
        Stars (-s): The target stars of your map. (float/range)
        Time (-t): Target time for a map in seconds. (float/range)
        Approach Rate (-ar): Target approach rate for recommended map. (float/range)
        Overall Diff (-od): Target overall diff for recommended map. (float/range)
        HP (-hp): Target HP for recommended map. (float/range)
        Cricle Size (-cs): Target cs for recommended map. (float/range)
        PP (-pp): Target fc pp for recommended map. (float/range)
        Graph (-g): Get a graph for the map that is recommended. (no param)
        Farm Rating (-f): How much of a farm map it is. (1 (hard)-10 (easy))
        Mods: Mods that you want to apply, no - needed. Use "any" for any/NM for no mod.
        Mode (-m) or (-{mode}): 0 = std, 1 = taiko, 2 = ctb, 3 = mania (int or tag)

        [Example]
        +<COMMAND> -pp 500 HDDT -ar 10.3 -g
        """
        user = ctx.message.author
        db_user = await self.get_user(user)

        # get options
        options, cmd_gamemode = self._gamemode_option_parser(options) # map gamemode might not be the same
        options, server_options = self.server_option_parser(options)
        api = self.determine_api(server_options, db_user=db_user)
        option_parser = OptionParser()
        option_parser.add_option('ar',      'approach_rate',    opt_type='range',   default=None)
        option_parser.add_option('bpm',     'bpm',              opt_type='int',     default=None)
        option_parser.add_option('od',      'overall_diff',     opt_type='range',   default=None)
        option_parser.add_option('pp',      'pp',               opt_type='range',   default=None)
        option_parser.add_option('hp',      'hp',               opt_type='range',   default=None)
        option_parser.add_option('cs',      'circle_size',      opt_type='range',   default=None)
        option_parser.add_option('s',       'stars',            opt_type='range',   default=None)
        option_parser.add_option('len',     'length',           opt_type='range',   default=None)
        option_parser.add_option('st',      'status',           opt_type='int',     default=0)
        option_parser.add_option('m',       'mode',             opt_type='int',     default=0)
        option_parser.add_option('f',       'farm',             opt_type='int',     default=0) # 0 - 10
        option_parser.add_option('info',    'info',             opt_type=None,      default=False) # 0 - 10
        option_parser.add_option('g',       'graph',            opt_type=None,      default=False) # 0 - 10
        output, options = option_parser.parse(options)

        username = await self.process_username(ctx, None) # can only recommend for yourself

        if not username:
            return await ctx.send("**No username linked! Can't recommend.**")

        # ---------------- check for valid options? --------------------
        if "info" in options and options["info"]:
            num_std_maps = await self.rec_std.count_documents({})
            num_taiko_maps = await self.rec_taiko.count_documents({})
            num_ctb_maps = await self.rec_ctb.count_documents({})
            num_mania_maps = await self.rec_mania.count_documents({})
            return await ctx.send(
                f"**In the recommendation database, there are currently `{num_std_maps}` maps for `std`, " \
                    f"`{num_taiko_maps}` maps for `taiko`, `{num_ctb_maps}` maps for `ctb`, "\
                    f"and `{num_mania_maps}` maps for `mania`.**")
    
        if options["farm"]:
            try:
                temp = int(options["farm"])
            except:
                return ctx.send(f":red_circle: **Please check your input! Farm rating must be an integer.**")
            if temp < 0 or temp > 10:
                return ctx.send(f":red_circle: **Please enter an integer between 0-10.**")

        # determine gamemode
        if cmd_gamemode is None:
            gamemode = int(options['mode']) # will default to 0
        else:
            gamemode = int(cmd_gamemode)

        try:
            userinfo = await self.owoAPI.get_user(
                username, mode=gamemode, api=api)
            userbest = await self.owoAPI.get_user_best(
                userinfo[0]['user_id'], mode=gamemode, api=api)
        except:
            return await ctx.send("**User not found in `{}` or not enough plays for recommendation.**".format(
                self.owoAPI.get_server_name(api)))

        # divert to other gamemodes from here
        if gamemode == 0:
            await self.get_std_rec(ctx, userinfo, userbest, output, options)
        else:
            await self.get_non_std_rec(ctx, userinfo, userbest, output, options, gamemode)


    async def get_std_rec(self, ctx, userinfo, userbest, output, options):
        top_num = 15 # use top 15 plays
        user = ctx.message.author
        db_user = await self.get_user(user)

        top_beatmap_ids = [str(play['beatmap_id']) for play in userbest]
        userbest = userbest[:top_num]

        # determine average easiness factor
        easiness = []
        pp = []
        stars = []
        mods = []
        top_ids = []
        for i in range(len(userbest)):
            score = userbest[i]
            mod_list = utils.num_to_mod(score['enabled_mods'])
            mod_list = self.clean_rec_mods(mod_list)
            mods.append(tuple(mod_list))
            top_ids.append(score['beatmap_id'])

            mods_list_query = [{"$elemMatch": {"$eq": mod}} for mod in mod_list]
            rec_beatmap = await self.rec_std.find_one({
                'beatmap_id': str(score['beatmap_id']),
                'mods': {"$all": mods_list_query}})

            if not rec_beatmap:
                await self.append_suggestion_database(score)
                rec_beatmap = await self.rec_std.find_one({
                    'beatmap_id': str(score['beatmap_id']),
                    'mods': {"$all": mods_list_query}})
                stars.append(rec_beatmap['stars'])
                pp.append(score['pp'])
            else:
                easiness.append(rec_beatmap['easiness'])
                stars.append(rec_beatmap['stars'])
                pp.append(score['pp'])

        # take in account options, find beatmaps from ranges
        if options['pp']:
            if options['pp'][1]:
                pp_range = (options['pp'][0],options['pp'][1])
            else:
                pp_base = int(options['pp'][0])
                pp_range = self._get_bounds(pp_base, 30)
        else:
            pp_random_factor = random.randint(0,15)
            pp_base = sum(pp)/len(pp) + pp_random_factor
            pp_range = self._get_bounds(pp_base, 30)
        # print('PP RANGE: ', options['pp'], pp_range)

        if options['stars']:
            if options['stars'][1]:
                star_range = (options['stars'][0],options['stars'][1])
            else:
                star_base = float(options['stars'][0])
                star_range = self._get_bounds(star_base, .2)
        else:
            star_base = sum(stars)/len(stars)
            star_range = self._get_bounds(star_base, .2)
        # print('STAR RANGE: ',options['stars'], star_range)

        if output:
            select_mods = utils.num_to_mod(
                utils.mod_to_num(''.join(output)))
            if select_mods == []:
                select_mods.append('NM')
        else:
            select_mods = list(random.choice(mods))

        # ----------------------------- build query ---------------------------------
        if options["stars"]:
            query = {
                'stars': {'$gte': star_range[0], '$lt': star_range[1]},
                'mods': select_mods}
        elif options["pp"] and mods:
            query = {
                'pp': {'$gte': pp_range[0], '$lt': pp_range[1]},
                'mods': select_mods}
        else:
            query = {
                'pp': {'$gte': pp_range[0], '$lt': pp_range[1]},
                # 'stars': {'$gte': star_range[0], '$lt': star_range[1]},
                'mods': select_mods}

        # handle ar, od, hp, cs ------------------------------------------------------
        if options['approach_rate']:
            if options['approach_rate'][1]:
                ar_range = (options['approach_rate'][0],options['approach_rate'][1])
            else:
                ar_base = float(options['approach_rate'][0])
                ar_range = self._get_bounds(ar_base, .2)
            query['ar'] = {'$gte': ar_range[0], '$lt': ar_range[1]}
        if options['overall_diff']:
            if options['approach_rate'][1]:
                od_range = (options['overall_diff'][0],options['overall_diff'][1])
            else:
                od_base = float(options['overall_diff'][0])
                od_range = self._get_bounds(od_base, 1)
            query['od'] = {'$gte': od_range[0], '$lt': od_range[1]}
        if options['hp']:
            if options['hp'][1]:
                hp_range = (options['hp'][0],options['hp'][1])
            else:
                hp_base = float(options['hp'][0])
                hp_range = self._get_bounds(od_base, 1)
            query['hp'] = {'$gte': hp_range[0], '$lt': hp_range[1]}
        if options['circle_size']:
            if options['circle_size'][1]:
                cs_range = (options['circle_size'][0],options['circle_size'][1])
            else:
                cs_base = float(options['circle_size'][0])
                cs_range = self._get_bounds(cs_base, 1)
            query['cs'] = {'$gte': cs_range[0], '$lt': cs_range[1]}

        # print(query)

        suggest_list = []
        async for beatmap in self.rec_std.find(query):
            if str(beatmap['beatmap_id']) not in top_beatmap_ids:
                suggest_list.append((beatmap['beatmap_id'], beatmap['mods'], beatmap['easiness']))

        # try:
        if suggest_list:
            # factor in ease here....
            try:
                if options["farm"]:
                    farm_rating = int(options["farm"])
                elif 'farm' in db_user:
                    farm_rating = int(db_user['farm'])
                else:
                    farm_rating = 8
            except:
                farm_rating = 8

            suggest_list = sorted(suggest_list, key=operator.itemgetter(2))
            block_size = round(len(suggest_list)/11)
            percent_farm = int(farm_rating)/11
            start_ind = round(len(suggest_list) * percent_farm)
            end_ind = start_ind + block_size
            suggest_list = suggest_list[start_ind:end_ind]

            beatmap_id, mods, ease = random.choice(suggest_list)
            mods = ''.join(mods).replace('NM','-')

            beatmap = await self.owoAPI.get_beatmap(beatmap_id)
            extra_info = {"username": ctx.message.author.name}
            return await self.disp_beatmap(ctx.message, beatmap,
                mods=mods, include_graph=options['graph'], extra_info=extra_info)
        else:
            return await ctx.send(':blue_circle: **No suggestions at the moment.**')


    async def get_non_std_rec(self, ctx, userinfo, userbest, output, options, mode):
        # print('MODE', mode)

        if mode == 0:
            return
        elif mode == 1:
            rec_db = self.rec_taiko
        elif mode == 2:
            rec_db = self.rec_ctb
        elif mode == 3:
            rec_db = self.rec_mania

        top_num = 50 # use top 15 plays
        user = ctx.message.author
        db_user = await self.get_user(user)

        top_beatmap_ids = [str(play['beatmap_id']) for play in userbest]
        userbest = userbest[:top_num]

        pp = []
        mods = []
        top_ids = []
        # score = []

        for i in range(len(userbest)):
            score = userbest[i]
            mod_list = utils.num_to_mod(score['enabled_mods'])
            mod_list = self.clean_rec_mods(mod_list)
            mods.append(tuple(mod_list))
            top_ids.append(score['beatmap_id'])

            pp.append(score['pp'])

        # take in account options, find beatmaps from ranges
        if options['pp']:
            if options['pp'][1]:
                pp_range = (options['pp'][0],options['pp'][1])
            else:
                pp_base = int(options['pp'][0])
                pp_range = self._get_bounds(pp_base, 20)
        else:
            pp_random_factor = random.randint(0,5)
            pp_base = sum(pp)/len(pp) + pp_random_factor
            pp_range = self._get_bounds(pp_base, 20)
        # print('PP RANGE: ', options['pp'], pp_range)

        # handle modes
        if output:
            select_mods = utils.num_to_mod(
                utils.mod_to_num(''.join(output)))
            if select_mods == []:
                select_mods.append('NM')
        else:
            select_mods = list(random.choice(mods))

        # aggregation pipeline
        query = {
            'pp_avg': {'$gte': pp_range[0], '$lt': pp_range[1]},
            'mods': select_mods
        }
        pipeline = [
            {"$project": {
                "pp_avg": {"$avg": "$pp"},
                "score_avg": {"$avg": "$score"},
                "acc_avg": {"$avg": "$acc"},
                "beatmap_id": "$beatmap_id",
                "mods": "$mods",
                "easiness": "$easiness",
            }},
            {"$match": query}
        ]

        suggest_list = []
        async for beatmap in rec_db.aggregate(pipeline, allowDiskUse=True):
            if str(beatmap['beatmap_id']) not in top_beatmap_ids:
                # print(beatmap)
                beatmapset_id = None
                if 'beatmapset_id' in beatmap:
                    beatmapset_id = beatmap['beatmapset_id']
                suggest_list.append((beatmap['beatmap_id'], beatmapset_id, 
                    beatmap['mods'], beatmap['easiness']))
            
        # try:
        if suggest_list:
            try:
                # factor in ease here....
                if options["farm"]:
                    farm_rating = int(options["farm"])
                elif 'farm' in db_user:
                    farm_rating = int(db_user['farm'])
                else:
                    farm_rating = 8
            except:
                farm_rating = 8
                
            suggest_list = sorted(suggest_list, key=operator.itemgetter(2))
            block_size = round(len(suggest_list)/11)
            percent_farm = int(farm_rating)/11
            start_ind = round(len(suggest_list) * percent_farm)
            end_ind = start_ind + block_size
            suggest_list = suggest_list[start_ind:end_ind]

            beatmap_id, beatmapset_id, mods, ease = random.choice(suggest_list)
            mods = ''.join(mods).replace('NM','-')

            # slightly different procedure in events of beatmapset_id and beatmap_id
            if beatmapset_id:
                beatmap = None
                beatmapset = await self.owoAPI.cache.beatmapset.entries.find_one(
                    {'beatmapset_id': beatmapset_id, "api": "bancho"})
                if beatmapset and beatmapset['data']:
                    beatmapset = beatmapset['data']
                else:
                    beatmapset = await self.owoAPI.get_beatmapset(beatmapset_id)

                # search for specific map
                for temp_bmp in beatmapset:
                    # print(beatmap_id, temp_bmp['beatmap_id'], beatmap_id == temp_bmp['beatmap_id'], temp_bmp['mode'], temp_bmp['mode_int'], temp_bmp['convert'])
                    if str(temp_bmp['beatmap_id']) == str(beatmap_id) and \
                        temp_bmp['mode'] == mode:
                        beatmap = [temp_bmp]
                        break 

                if not beatmap:
                    beatmap = await self.owoAPI.cache.beatmap.entries.find_one(
                        {'beatmap_id': beatmap_id, "api": "bancho"})
                    if beatmap and beatmap['data']:
                        beatmap = [beatmap['data']]
                    else:
                        beatmap = await self.owoAPI.get_beatmap(beatmap_id)
                        # beatmap = beatmap[0]                    
            else:
                beatmap = await self.owoAPI.cache.beatmap.entries.find_one(
                    {'beatmap_id': beatmap_id, "api": "bancho"})
                if beatmap and beatmap['data']:
                    beatmap = [beatmap['data']]
                else:
                    beatmap = await self.owoAPI.get_beatmap(beatmap_id)
                    # beatmap = beatmap[0]

                # if the mode isn't correct, look for the convert via set
                if beatmap[0]['mode'] != mode:
                    beatmapset_id = beatmap[0]['beatmapset_id']

                    beatmapset = await self.owoAPI.cache.beatmapset.entries.find_one(
                        {'beatmapset_id': beatmapset_id, "api": "bancho"})
                    if beatmapset and beatmapset['data']:
                        beatmapset = beatmapset['data']
                    else:
                        beatmapset = await self.owoAPI.get_beatmapset(beatmapset_id)

                    # search for specific map
                    for temp_bmp in beatmapset:
                        # print(beatmap_id, temp_bmp['beatmap_id'], beatmap_id == temp_bmp['beatmap_id'], temp_bmp['mode'], temp_bmp['mode_int'], temp_bmp['convert'])
                        if str(temp_bmp['beatmap_id']) == str(beatmap_id) and \
                            temp_bmp['mode'] == mode:
                            beatmap = [temp_bmp]
                            break              

            extra_info = {"username": ctx.message.author.name}
            return await self.disp_beatmap(ctx.message, beatmap,
                mods=mods, include_graph=options['graph'], extra_info=extra_info)
        else:
            return await ctx.send(':blue_circle: **No suggestions at the moment.**')



    def _get_bounds(self, value, val_range, min_val=False):
        fudge_factor = random.uniform(0,.5)
        if min_val:
            return (value*(1+fudge_factor), value*(1+fudge_factor) + val_range)
        else:
            return (value-val_range/2 + val_range*fudge_factor,
                value+val_range/2 + val_range*fudge_factor)

    """
    @commands.command(no_pm=True)
    async def createrec(self, ctx):
        user = ctx.message.author

        if user.id != 91988142223036416:
            return

        for i in range(1, 4):
            await self.create_non_std_rec_database(i)
            """


    async def create_std_rec_database(self):
        # await self.rec_std.drop()
        print("Creating suggestion database!")
        self.SLEEP_TIME = .25
        print('Sleep per user: ', self.SLEEP_TIME)

        current_time = datetime.datetime.now()
        loop = asyncio.get_event_loop()
        bound_size = 0 # EDIT THIS VALUE
        force_list = [] # empty
        total_players = await self.track.count_documents({})
        counter = 0
        async for player in self.track.find({}, no_cursor_timeout=True):
            print(f"PLAYER {counter}/{total_players}")
            loop.create_task(self.suggestion_play_parser(player))
            await asyncio.sleep(self.SLEEP_TIME)
            counter += 1

        loop_time = datetime.datetime.now()
        elapsed_time = loop_time - current_time
        print("Time ended: " + str(elapsed_time))
        print("Suggestion Database Creation ENDED!!!. Took: {}".format(str(elapsed_time)))


    async def create_non_std_rec_database(self, mode):
        if mode == 0:
            return
        elif mode == 1:
            rec_db = self.rec_taiko
        elif mode == 2:
            rec_db = self.rec_ctb
        elif mode == 3:
            rec_db = self.rec_mania
        await rec_db.drop()

        # load in mongo dump json file
        print('Loading tracking file.')
        folderpath = os.path.join(os.getcwd(), 'database', 'dump')
        track_filepath = os.path.join(
            folderpath, 'owo_database_2_track.json')
        with open(track_filepath) as json_file:
            track_data = json.load(json_file)

        total_players = len(track_data)

        for idx, tracked_user in enumerate(track_data):
            print(f'Processing {idx}/{total_players}')
            try:
                if self.MODES[mode] not in tracked_user['plays']['best']:
                    continue
            except:
                continue

            top_plays = tracked_user['plays']['best'][self.MODES[mode]]
            
            for play in top_plays:
                await self.append_suggestion_database_non_std(play, mode)

    async def append_suggestion_database_non_std(self, play, mode):
        if mode == 0:
            return
        elif mode == 1:
            database = self.rec_taiko
        elif mode == 2:
            database = self.rec_ctb
        elif mode == 3:
            database = self.rec_mania

        mods_list = utils.num_to_mod(play['enabled_mods']) # list
        mods_list = self.clean_rec_mods(mods_list)

        # check to see if this beatmap/mod pair is in the database
        mods_list_query = [{"$elemMatch": {"$eq": mod}} for mod in mods_list]
        rec_beatmap = await database.find_one({
            'beatmap_id': str(play['beatmap_id']),
            'mods': {"$all": mods_list_query}
            })

        if not rec_beatmap:
            rec_beatmap = {
                'pp':           [],
                'acc':          [],
                'score':        [],
                'easiness':     0,
                'mods':         mods_list,
                'beatmap_id':   str(play['beatmap_id']),
                'gamemode':     mode
            }

        if 'S' in play['rank'] or 'X' in play['rank']:
            play = self._rec_fix_play_keys(play)
            acc = utils.calculate_acc(play, mode)
            
            rec_beatmap['pp'].append(float(play['pp']))
            rec_beatmap['acc'].append(acc)
            rec_beatmap['score'].append(int(play['score']))
            rec_beatmap['easiness'] += 1

            await database.update_one({
                'beatmap_id': str(play['beatmap_id']),
                'mods': {"$all": mods_list_query}},
                {'$set': rec_beatmap}, upsert=True)
            """
            print("Updated {} mods: {} freq: {}".format(
                play['beatmap_id'], str(mods_list), rec_beatmap['easiness']))"""


    def _rec_fix_play_keys(self, play):
        hit_types = ['geki', 'katu', 'miss', '50', '300', '100']
        for hit_type in hit_types:
            if f'count_{hit_type}' not in play:
                play[f'count_{hit_type}'] = play[f'count{hit_type}']

        return play


    async def verify_std_rec_database(self):
        # await self.rec_std.drop()
        print("Creating suggestion database!")
        self.SLEEP_TIME = .25
        print('Sleep per user: ', self.SLEEP_TIME)

        current_time = datetime.datetime.now()
        loop = asyncio.get_event_loop()
        bound_size = 0 # EDIT THIS VALUE
        force_list = [] # empty
        total_recs = await self.rec_std.count_documents({})
        counter = 0
        async for rec in self.rec_std.find({}, no_cursor_timeout=True):
            """
            if 'osu_id' in player:
                osu_id = player['osu_id']
            else:
                osu_id = player['userinfo']['osu']['user_id']"""
            # print(f'Examining {osu_id}')
            # if (counter > start_index and counter <= end_index) or osu_id in force_list:
            print(f"ITEM {counter}/{total_recs}")
            loop.create_task(self.suggestion_play_parser(player))
            await asyncio.sleep(self.SLEEP_TIME)
            counter += 1

        loop_time = datetime.datetime.now()
        elapsed_time = loop_time - current_time
        print("Time ended: " + str(elapsed_time))
        print("Suggestion Database Creation ENDED!!!. Took: {}".format(str(elapsed_time)))


    # this code is very similar to the play tracker
    async def suggestion_play_parser(self, player):
        # ensures that data is recieved
        got_data = False
        get_data_counter = 1
        top_plays = None
        mode = 0
        if 'osu_id' in player:
            osu_id = player['osu_id']
        else:
            osu_id = player['userinfo']['osu']['user_id']

        top_plays = await self.owoAPI.get_user_best(osu_id, 
            mode=mode, api='bancho')

        # if still no data
        if top_plays == None:
            print("Data fetched failed for {}".format(player['username']))
            return

        for play in top_plays:
            await self.append_suggestion_database(play)
            await asyncio.sleep(.1)


    async def append_suggestion_database(self, play, status=0):
        # calculate the pp for the beatmap
        accs = [100] # based on 100% acc
        mods_list = utils.num_to_mod(play['enabled_mods']) # list
        mods_list = self.clean_rec_mods(mods_list)

        # create structure...
        mods_list_query = [{"$elemMatch": {"$eq": mod}} for mod in mods_list]
        rec_beatmap = await self.rec_std.find_one({
            'beatmap_id': str(play['beatmap_id']),
            'mods': {"$all": mods_list_query}
            })

        mod_num = utils.mod_to_num(''.join(mods_list))
        beatmap = await self.owoAPI.get_beatmap(play['beatmap_id'])
        beatmap_info, _, _ = await self.owoAPI.get_full_beatmap_info(beatmap[0], 
            mods=mod_num, extra_info={'play_info': play})

        # print(beatmap_info)
        if not beatmap_info:
            return

        if not rec_beatmap:
            rec_beatmap = {
                'pp':           float(beatmap_info['pp_mod'][2]),
                'ar':           float(beatmap_info['ar_mod']),
                'bpm':          float(beatmap_info['bpm_mod']),
                'easiness':     0,
                'length':       float(beatmap_info['total_length_mod']),
                'stars':        float(beatmap_info['stars_mod']),
                'od':           float(beatmap_info['od_mod']),
                'mods':         mods_list,
                'beatmap_id':   str(play['beatmap_id']),
                'hp':           float(beatmap_info['hp_mod']),
                'cs':           float(beatmap_info['cs_mod']),
                'gamemode':     int(beatmap_info['mode']),
                'status':       int(status)
            }
        rec_beatmap['easiness'] += 1

        await self.rec_std.update_one({
            'beatmap_id': play['beatmap_id'],
            'mods': {"$all": mods_list_query}},
            {'$set': rec_beatmap}, upsert=True)

        print("Updated {} mods: {} freq: {}".format(
            play['beatmap_id'], str(mods_list), rec_beatmap['easiness']))


    def clean_rec_mods(self, mods_list):
        # fix mods
        for n, mod in enumerate(mods_list):
            if mod == 'NC':
                mods_list[n] = 'DT'
        if 'SD' in mods_list:
            mods_list.remove('SD')
        if 'SO' in mods_list:
            mods_list.remove('SO')
        if 'NF' in mods_list:
            mods_list.remove('NF')
        if 'PF' in mods_list:
            mods_list.remove('PF')

        if not mods_list:
            mods_list = ['NM']

        return mods_list

    # ---------------------------- Detect Links ------------------------------
    async def find_link(self, message):
        """
        if not message.content.startswith("!") and \
            not message.content.startswith("?"):
            return

        if '>' in message.content:
            return
        """        

        # process from a url in msg
        original_message = message.content
        server = message.guild
        channel = message.channel
        discord_user = message.author

        # to process a link, the channel must be osu related
        """
        full_process_test = '{} {} {}'.format(
            channel.name, channel.category.name, channel.topic)
        if not any([x not in full_process_test.lower() for x in ['osu', 'owo']]):
            return"""


        # define escape sequences for links
        try:
            # handle whitelisting/blacklisting
            if not server:
                return
            if server.id in self.bot.blacklist['servers']:
                return
            if discord_user.id in self.bot.blacklist['users']:
                return        
            if (self.bot.whitelist['servers'] and \
                server.id not in self.bot.whitelist['servers']) and \
                (self.bot.whitelist['users'] and \
                    discord_user.id not in self.bot.whitelist['users']):
                return

            if discord_user.id == self.bot.user.id:
                return
            if discord_user.bot:
                return
            if message.author.id == self.bot.user.id:
                return
            # handle common prefixes
            if '>' in message.content[0:5]:
                return
            if '!' in message.content[0:5]:
                return
            if '?' in message.content[0:5]:
                return
            if discord_user.id in self.bot.blacklist["users"]:
                return
            if server.id in self.bot.blacklist["servers"]:
                return
        except:
            # print('Find link error') # **
            return

        if original_message == '' and not message.attachments:
            return

        # check if there's a url or attachment, if not, stop
        if not self._contains_url(message.content) and not message.attachments:
            # print('No urls or attachments found!')
            return

        ignore_links = [
            'yout', 'reddit', 'insta', 'tenor', 'twitter', 'tik', 'spotify',
            'strawpoll', 'gyazo', 'steam', 'hoyo', 'emojis', 'twitch', 'mp4',
            'gif', 'android', 'facebook', 'chess', '<', '.gg', '.tv', 'amazon',
            '.mov', 'anim', 'google', 'roblox', 'streamable', 'genshin', '.webm'
        ]
        if any([x in message.content.lower() for x in ignore_links]):
            return
        for att in message.attachments:
            if any([x in str(att.proxy_url).lower() for x in ignore_links]):
                return

        # must have
        att_must_have = ['screenshot', 'osu', 'osr']
        attach_contains = False
        for att in message.attachments:
            if any([x in str(att.proxy_url).lower() for x in att_must_have]):
                attach_contains = True
                break
        if original_message == '' and not attach_contains:
            return

        # see if server can process link again
        if self._is_link_cooldown(server):
            # print('On cooldown')
            return

        print("Processing message: '{}'".format(original_message))

        # look at server setting to see if it should be disabled.
        server_options = await self.bot.get_setting(server, 'osu')
        should_process = (not server_options or \
            (server_options and "process_url" not in server_options.keys()) or \
            (server_options and "process_url" in server_options.keys() and server_options['process_url']))
        if not should_process:
            return

        # ------------------------ get attachments ------------------------
        all_urls = []
        screnshot_urls = []
        replays = []
        must_have = ['screenshot','osu']
        replay_link = ['osr']
        for att in message.attachments:
            # finding screenshots
            if any([x in str(att.filename).lower() for x in must_have]):
                all_urls.append((str(att.proxy_url), ''))

            # finding replays
            if any([x in str(att.filename).lower() for x in replay_link]):
                replays.append(att)

        # ---------- start processing pipeline --------------------
        # loop = asyncio.get_event_loop()
        # -------- process replays ------------
        for replay in replays:
            await self.process_replay(message, all_urls, replay, server_options)
            # loop.create_task(self.process_replay(message, all_urls, replay, server_options))
        # ------------------- find other osu urls ----------------------
        all_urls.extend(self.find_osu_urls(original_message))
        all_urls = list(set(all_urls)) # remove duplicates
        if len(all_urls) > 3: # limit three urls
            all_urls = all_urls[0:3]
        ## ------- process youtube link ---------------
        # loop.create_task(self.process_youtube(message, server_options))
        ## --------- user url detection ---------------------
        await self.process_user_url(message, all_urls, server_options)
        # loop.create_task(self.process_user_url(message, all_urls, server_options))
        ## -------- beatmap detection ----------------
        await self.process_beatmap(message, all_urls, server_options)
        # loop.create_task(self.process_beatmap(message, all_urls, server_options))
        ## ------- screenshot detection ---------------
        await self.process_screenshot(message, all_urls, server_options)
        # loop.create_task(self.process_screenshot(message, all_urls, server_options))

    def _is_link_cooldown(self, server):
        is_new = False
        is_cooldown = False
        if str(server.id) not in self.server_link_cooldown:
            is_new = True
            self.server_link_cooldown[str(server.id)] = time.time()

        if time.time() - self.server_link_cooldown[str(server.id)] < self.LINK_COOLDOWN \
            and not is_new:
            is_cooldown = True

        # do a check of all servers quickly
        slc_copy = copy.deepcopy(self.server_link_cooldown)
        for s_id in slc_copy:
            if time.time() - slc_copy[s_id] >= self.LINK_COOLDOWN:
                try:
                    del self.server_link_cooldown[s_id]
                except:
                    pass

        return is_cooldown


    def _contains_url(self, message):
        """
        regex = re.compile(
            #r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
            r'(https?://[^\s]+)'
        )
        if regex.match(message):"""

        if re.findall(r'(https?://[^\s]+)', message):
            return True
        else:
            return False


    def find_osu_urls(self, msg):
        all_urls = []
        get_urls = re.findall("((https|http):\/\/" \
            "(osu|puu|gatari|akatsuki|ripple|kawata|ainu|horizon|dgsrz|enjuu|kurikku|troke|ez-pp)" \
            "[^\s]+)([ ]\+[A-Za-z][^\s]+)?", msg)

        for url, _, _, mods in get_urls:
            all_urls.append((url, mods))

        all_urls = list(set(all_urls))

        # sort by where is shows up
        found_idx = []
        for url, mods in all_urls:
            found_idx.append(msg.find(url))
        all_urls = [x for _,x in sorted(zip(found_idx, all_urls))]

        return all_urls


    async def process_user_url(self, message, all_urls, server_options=None):
        # processes user input for user profile link
        user_urls = [
            'https://osu.ppy.sh/u/',
            'https://osu.ppy.sh/users/'
            ]

        server_user = message.author
        channel = message.channel

        # print('OSU USER URL', server_options)
        if (server_options and "user_urls" in server_options.keys() and \
            not server_options["user_urls"]):
            return

        # quick url check
        found = False
        for url, _ in all_urls:
            # print('DETECT URL', url)
            for base_url in user_urls:
                if base_url in url:
                    found = True
                    break
        if not found:
            # print('Not found')
            return

        # print('PROCESSING USER URL')
        # return

        for url, suffix in all_urls:
            if url.find('https://osu.ppy.sh/u/') != -1 or \
                url.find('https://osu.ppy.sh/users/') != -1:
                user_id = self._url_to_userid(url)
                find_user = await self.players.find_one({"user_id":user_id})
                find_user_id = await self.players.find_one({"osu_user_id":user_id})
                try:
                    if find_user:
                        gamemode = int(find_user["default_gamemode"])
                    elif find_user_id:
                        gamemode = int(find_user_id["default_gamemode"])
                    else:
                        gamemode = 0
                except:
                    gamemode = 0

                user_info = await self.owoAPI.get_user(user_id, 
                    mode=gamemode, api='bancho')
                if user_info:
                    url = 'https://osu.ppy.sh/users/{}'.format(user_info[0]['user_id'])
                    em = await self.create_user_embed(message, user_info[0], gamemode)
                    await channel.send(embed = em)


    def _url_to_userid(self, user_url):
        try:
            user_id = user_url.replace('https://osu.ppy.sh/u/','').replace('https://osu.ppy.sh/users/','')
            user_id = user_id.replace('http://osu.ppy.sh/u/','').replace('http://osu.ppy.sh/users/','')
            return user_id
        except:
            return None


    async def process_youtube(self, message, server_options=None):

        return None
        youtube_urls = await self._find_youtube_urls(message.content)

        channel = message.channel
        user = message.author
        server = message.guild

        server_options = await self.server_settings.find_one({"server_id":str(server.id)})
        # print(server_options)
        if (server_options and \
            "youtube" in server_options.keys() and \
            not server_options["youtube"]):
            return

        # perform search
        youtube_key = self.api_keys["YOUTUBE"]
        search_results = await web_utils.youtube_search(url, youtube_key)
        # list of things to looks for
        regex = "(\w+)\s?[:|-]\s?([^\s]+)\s" # finds key-value pairs

        osu_user = None
        osu_skin = None
        osu_map = None
        try:
            result = search_results[0]
        except:
            return
        video_id = result["id"]["videoId"]
        query = "https://www.googleapis.com/youtube/v3/videos?part=snippet&id={}&key={}".format(
            video_id, youtube_key)

        info = await web_utils.get_REST(query)

        info = info["items"][0]
        description = info["snippet"]["description"].replace("\n"," ")
        title = info["snippet"]["title"]
        # print(description, title)

        if "osu" in title or "osu" in description:
            words = description.split(" ")

            for i, word in enumerate(words):
                word = word.lower()
                if not osu_user and ("profile" in word or "user" in word):
                    osu_user = words[i+1]
                    if "osu.ppy.sh/users/" in words[i] or "osu.ppy.sh/u/" in words[i]:
                        osu_user = words[i]
                    osu_user = self._fix_youtube_url(osu_user)
                elif not osu_map and "map" in word:
                    osu_map = words[i+1]
                    if "http" not in osu_map:
                        osu_map = words[i]
                    osu_map = self._fix_youtube_url(osu_map)
                elif not osu_skin and "skin" in word:
                    osu_skin = words[i+1]
                    if "http" not in osu_skin or "osk" in words[i]:
                        osu_skin = words[i]
                    osu_skin = self._fix_youtube_url(osu_skin)
                if osu_user and osu_map and osu_skin:
                    break

        max_occ = (None, 0)
        if not osu_user: #whatever
            words = title.split("|") # only words for circle people
            # test the frequency of each in the description
            for word in words:
                if word.startswith(" "):
                    word = word[1:]
                if word.endswith(" "):
                    word = word[:-1]

                occurences = 0
                # can't use .count because it might not
                # be the exact string
                for desc_word in description.split(" "):
                    if word in desc_word:
                        occurences += 1
                if occurences > max_occ[1] and len(word) > 4:
                    max_occ = (word, occurences)

            osu_user = max_occ[0]

        # print(osu_user, osu_map, osu_skin)
        await self._display_youtube_embed(message, osu_user, osu_map, osu_skin)


    async def _find_youtube_urls(self, original_message):
        # clean up big function up there
        words = original_message.split(" ")
        required = ["youtube"]
        youtube_urls = []
        for word in words:
            if any([x in word for x in required]):
                youtube_urls.append(word)
        return youtube_urls


    def _fix_youtube_url(self, url):
        # strips the link of random stuff
        return url.replace("|","").replace(",","")


    async def _display_youtube_embed(self, message, user, map_url, skin_url, gamemode = 0):
        # user can come in as a url or username
        user_id = self._url_to_userid(user) # probably a username
        beatmapset_id, beatmap_id, map_gamemode = self._url_to_bmapid(map_url)

        # api = self.osu_keys["OFFICIAL"]["URL"]

        if not beatmap_id:
            return

        if is_set:
            beatmap = await api_utils.get_beatmapset(key, api, beatmap_id)
        else:
            beatmap = await api_utils.get_beatmap(key, api, beatmap_id)
        url = 'https://osu.ppy.sh/b/{}'.format(beatmap_id)

        # if not user_id and beatmap[0]['status'] not in [1,3,8]:
        return await self.disp_beatmap(message, beatmap, url, "", graph = False)

        # this stuff is for later....

        user_scores = await api_utils.get_scores(
            key, api, beatmap_id, user_id, gamemode)

        # stop if not found
        if not user_scores:
            return
        # convert to floats
        for i in range(len(user_scores)):
            try:
                user_scores[i]['pp'] = float(user_scores[i]['pp'])
            except:
                user_scores[i]['score'] = float(user_scores[i]['score'])
        # sort the scores based on pp
        try:
            user_scores = sorted(user_scores, key=operator.itemgetter('pp'), reverse=True)
        except:
            # print(userscore)
            user_scores = sorted(user_scores, key=operator.itemgetter('score'), reverse=True)
        user_score = user_scores[0]

        try:
            pp = user_score["pp"]
        except:
            pp = None
        extra_info = {
            "rank": user_score["rank"],
            "pp": pp,
            "created_at": user_score['date'],
            "accuracy": (utils.calculate_acc(user_score, 0))/100,
            "username": user_id,
            "skin": self._fix_skin(skin_url, user_id),
            "statistics": user_score}
        mod_list = utils.num_to_mod(user_score['enabled_mods'])
        mods = utils.fix_mods(''.join(mod_list))
        await self.disp_beatmap(message, [beatmap], url, mods,
            extra_info = extra_info, graph = False)


    async def _handle_beatmap_msg(self, server, all_urls, original_message):
        server_options = await self.server_settings.find_one({"server_id":str(server.id)})
        # print(server_options)
        if all_urls and (server_options is None or \
            "beatmap_urls" not in server_options.keys() or \
            not server_options["beatmap_urls"]):
            # try:
            beatmap_url_triggers = [
                'https://osu.ppy.sh/beatmapsets/',
                'https://osu.ppy.sh/s/',
                'https://osu.ppy.sh/b/',
                'http://osu.ppy.sh/ss/',
                'https://osu.ppy.sh/ss/',
                'http://ripple.moe/ss/',
                'https://ripple.moe/ss/',
                'https://puu.sh', 'screenshot',
                '.jpg', '.png'
                ]
            if any([link in original_message for link in beatmap_url_triggers]) or in_attachments:
                loop = asyncio.get_event_loop()
                loop.create_task(self.process_beatmap(all_urls, message, server_options))
                pass

            # add to user servers
            await self.update_user_servers_list(discord_user, server)


    async def process_replay(self, message, all_urls, att, server_options=None):
        rand_id = random.randint(0,20)
        channel = message.channel
        user = message.author
        server = message.guild

        if all_urls and (server_options is None or \
            "replays" not in server_options.keys() or \
            not server_options["replays"]):
            return

        # print('PROCESSING REPLAY!')
        # return

        # download file
        file_path = 'cogs/osu/temp/{}.osr'.format(rand_id) # some unique filepath
        await att.save(file_path) # save file

        # process
        replay_data = self.replay_parser(file_path)
        beatmap = await self.owoAPI.get_beatmap(
            beatmap_id=replay_data.beatmap_hash, api='ripple') # ripple supports hash
        if beatmap:
            beatmap = beatmap[0]
            em, file = await self._get_replay_embed(message, beatmap, replay_data)
            try:
                return await channel.send(embed=em, files=[file])
            except:
                return await channel.send(embed=em)

        await channel.send("**That map does not exist in the database.**")


    async def _get_replay_embed(self, message, beatmap, replay_data, api='bancho'):
        user = message.author
        server = message.guild

        # get replay graph
        # try:
        color = user.colour.to_rgb()
        color = (color[0]/255, color[1]/255, color[2]/255)
        file, lifebar_url = await map_utils.plot_life_bar(replay_data.life_bar_graph,
            color=color, mapset_id = beatmap['beatmapset_id'])
        # except:
            # file, lifebar_url = (None, None)

        # determine mods
        mods = utils.num_to_mod(replay_data.mod_combination)
        if not mods:
            mods = []
            mods.append('No Mod')

        profile_url = "https://i.imgur.com/LrnCwlp.png"
        osu_user = await self.owoAPI.get_user(
            replay_data.player_name, mode=replay_data.game_mode, api=api)
        if osu_user:
            osu_user = osu_user[0]
            profile_url = await self.owoAPI.get_user_avatar(osu_user['user_id'], api)

        # get best plays map information and scores
        beatmaps_bd = {
            "count_300": replay_data.number_300s,
            "count_100": replay_data.number_100s,
            "count_50": replay_data.number_50s,
            "count_katu": replay_data.katus,
            "count_geki": replay_data.gekis,
            "count_miss": replay_data.misses,
            "max_combo": int(replay_data.max_combo),
        }
        gamemode = int(replay_data.game_mode)
        acc = utils.calculate_acc(beatmaps_bd, replay_data.game_mode)
        # fc_acc = utils.no_choke_acc(beatmaps_bd, replay_data.game_mode) # !!! need to put fc acc too
        beatmaps_bd['accuracy'] = acc
        beatmaps_bd['rank'] = utils.calculate_rank(beatmaps_bd, acc, mods)

        # calculate potential pp
        bmp_calc, bmp, bmp_file_path = await self.owoAPI.get_full_beatmap_info(beatmap, 
            mods=int(replay_data.mod_combination), 
            extra_info={'play_info': beatmaps_bd})

        msg = "**Replay data for {}:**".format(replay_data.player_name)
        info = ""

        if bmp_calc != None:
            if 'extra_info' in bmp_calc and \
                abs(float(bmp_calc['extra_info']['play_pp']) - \
                float(bmp_calc['extra_info']['fc_pp'])) > 2 and \
                gamemode == 0:
                pot_pp = '**{:.2f}PP** ({:.2f}PP for {:.2f}% FC)'.format(
                    float(bmp_calc['extra_info']['play_pp']), 
                    float(bmp_calc['extra_info']['fc_pp']), 
                    float(bmp_calc['extra_info']['fc_acc']))
            else:
                pot_pp = '**{:.2f}PP** (_Unofficial_)'.format(
                    float(bmp_calc['extra_info']['play_pp']))


        max_combo_den_str = '/{}'.format(str(beatmap['max_combo']))
        if 'none' in str(beatmap['max_combo']).lower() or \
            str(beatmap['max_combo']) == '0':
            max_combo_den_str = ''

        info += "▸ **{}** ▸ {} ▸ {}% ▸ {} UR\n".format(
            self.RANK_EMOTES[beatmaps_bd['rank']], pot_pp, round(acc,2), "-")
        info += "▸ {} ▸ x{}{} ▸ {}\n".format(replay_data.score,
            replay_data.max_combo, max_combo_den_str,
            self._get_score_breakdown(beatmaps_bd, replay_data.game_mode))

        # get stars
        star_str, _ = self.compare_val_params(bmp_calc, 'difficulty_rating', 'stars_mod', 
            precision=2, single=True)

        # grab beatmap image
        map_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap)
        beatmap_url = self.owoAPI.get_beatmap_url(beatmap)
        em = discord.Embed(description=info, colour=user.colour)
        if not replay_data.player_name:
            replay_data.player_name = "(Unknown)"
        em.set_author(name="{}: {} [{}]{} +{} [{}★]".format(
            replay_data.player_name, beatmap['title'], beatmap['version'],
            self._get_keys(beatmap, replay_data.game_mode, beatmap['version']),
            utils.fix_mods(''.join(mods)),star_str), url = beatmap_url, icon_url = profile_url)

        if not lifebar_url:
            em.set_thumbnail(url=map_image_url)
        else:
            em.set_image(url=lifebar_url)

        timeago = utils.time_ago(
            datetime.datetime.utcnow(),
            replay_data.timestamp)
        em.set_footer(text = "{}Ago On osu! Official Server".format(timeago))

        return em, file


    async def process_screenshot(self, message, all_urls, server_options=None):
        message_content = message.content
        # print('OSU SERVER OPTIONS', server_options)
        display_screenshot = (not server_options or \
            (server_options and "screenshot" not in server_options.keys()) or \
            (server_options and "screenshot" in server_options.keys() and \
                server_options["screenshot"]))
        if not display_screenshot:
            return

        display_screenshot_graph = (
            (server_options and "screenshot_graph" in server_options.keys() and \
                server_options["screenshot_graph"]))

        screenshot_links = [
            'http://osu.ppy.sh/ss/',
            'https://osu.ppy.sh/ss/',
            'http://ripple.moe/ss/',
            'https://ripple.moe/ss/',
            'https://puu.sh','screenshot',
            '.jpg', '.png']

        for url, _ in all_urls:
            # print(str(url))
            extra_info = {}

            screenshot_exists = any([link in url for link in screenshot_links])
            # print([link in url for link in screenshot_links], screenshot_exists)
            if not screenshot_exists:
                continue

            # print('Found screenshot, RETURNING', url)
            # return # ******** DELETE 

            beatmap, mods, extra_info = await self._get_screenshot_map(
                url, unique_id = str(message.author.id), message=message)
            if beatmap:
                await self.disp_beatmap(message, beatmap, 
                    mods=mods, include_graph=display_screenshot_graph, extra_info=extra_info)


    async def _get_screenshot_map(self, url, unique_id, message = None):
        mods = ''
        extra_info = {}
        none_response = (None, None, None)
        discord_user = message.author
        loop_best = True

        if not unique_id:
            unique_id = '0'

        rand_id = random.randint(0,50)
        filepath = 'cogs/osu/temp/ss_{}.png'.format(rand_id)

        # print('Getting SS')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    image = await r.content.read()
            with open(filepath,'wb') as f:
                f.write(image)
                f.close()
            original_image = Image.open(filepath)
        except:
            # print('Get SS Failed')
            return none_response

        # get certain measurements for screenshot
        height = original_image.size[1]
        width = original_image.size[0]
        title_bar_height = height*0.126 # approximate ratio
        title_bar_width = width*0.66 # approximate ratio
        info_image = original_image.crop((0, 0, title_bar_width, title_bar_height))

        # info_image.save('ss_test.png')
        # deallocate memory?
        os.remove(filepath)
        info = pytesseract.image_to_string(info_image).split('\n')

        # process info
        map_name = None
        map_author = None # not as important
        player_name = None
        # print(info)
        for text in info:
            if len(text) != 0:
                if ('-' in text or "—" in text) and not map_name:
                    map_name = text

                played_by_present = utils.get_similarity('Played by', text) > (len('Played by')/len(text))*(0.9)
                if played_by_present and not player_name and "by" in text:
                    player_name = text[text.find('by')+3:]
                    player_name = player_name[0:player_name.find(' on ')]
                    player_name = player_name.replace('|<', 'k').replace('l<', 'k')

                beatmap_author_present = utils.get_similarity('Beatmap by', text) > (len('Beatmap by')/len(text))*(0.9)
                if beatmap_author_present and "by" in text:
                    map_author = text[text.find('by')+3:]

        # if the player name doesn't exit, then try to force it
        discord_user_info = await self.players.find_one({"user_id":str(str(discord_user.id))})
        if discord_user_info:
            try:
                player_name = discord_user_info["osu_username"]
            except:
                player_name = discord_user_info["bancho_username"]
            loop_best = False

        # -------- last resorts for map names --------
        if len(info) > 0 and not map_name:
            map_name = info[0] # try setting the map name to the first thing

        # if there's no difficulty information, then try the whole top
        if '[' not in map_name or ']' not in map_name:
            title_image = original_image.crop((0, 0, width, title_bar_height/3 + 2))
            map_name = pytesseract.image_to_string(title_image)

        # deallocated memory?
        original_image = None
        info = None

        # if it couldn't get the name, not point in continuing
        if map_name is None or map_name == "" or len(map_name) < 5:
            return none_response

        map_name = "{}".format(map_name).replace('—', '-').replace('\n','').replace('|<', 'k').replace('l<','k')
        full_query = '{} {}'.format(map_name, map_author)
        # print('INFO ', map_name, map_author, player_name) # **

        search_results = await self.owoAPI.map_search(full_query)
        # print('RESULTS ', search_results) # **

        sim_upper_threshold = 0.95
        overall_map_list = []
        max_similarity = 0
        for beatmap in search_results:
            # beatmap = beatmap["_source"]
            # depending on if the author is known
            if map_author:
                comparison_str = f"{map_name} {map_author}"
                title = '{} - {} [{}] {}'.format(
                    beatmap['artist'], beatmap['title'], beatmap['version'], beatmap['creator'])
            else:
                comparison_str = map_name
                title = '{} - {} [{}]'.format(beatmap['artist'], beatmap['title'], beatmap['version'])

            beatmap_id = beatmap['beatmap_id']
            similarity = utils.get_similarity(title, comparison_str)
            # print(beatmap_id, similarity)
            if similarity >= sim_upper_threshold:
                beatmap_info = await self.owoAPI.get_beatmap(beatmap_id) # , api='ripple')
                return beatmap_info, mods, extra_info
            overall_map_list.append((float(similarity), beatmap_id))

        # print('OVERALL MAP LIST', overall_map_list)

        lower_threshold = 0.50
        if overall_map_list:
            # sort by similarity
            overall_map_list = sorted(overall_map_list, key=lambda x: x[0], reverse = True)
            if overall_map_list[0][0] >= lower_threshold:
                beatmap_info = await self.owoAPI.get_beatmap(overall_map_list[0][1])
                return beatmap_info, mods, extra_info

        return none_response


    # processes user input for the beatmap
    async def process_beatmap(self, message, all_urls, server_options=None):
        server = message.guild

        # get server options... haha lmao this block of code
        run_beatmap_url = (not server_options or \
            (server_options and "beatmap_urls" not in server_options.keys()) or \
            (server_options and "beatmap_urls" in server_options.keys() and server_options["beatmap_urls"]))
        if not run_beatmap_url: # if server doesn't want beatmap urls processed
            return

        if not all_urls:
            return

        # find options
        option_parser = OptionParser()
        option_parser.add_option('i',   'index',         opt_type=int,      default=None)
        option_parser.add_option('v',   'version',       opt_type=str,      default=None)
        option_parser.add_option('s',   'set',           opt_type=None,     default=False)
        option_parser.add_option('g',   'graph',         opt_type=None,     default=False)
        option_parser.add_option('a',   'acc',           opt_type=float,    default=None)
        option_parser.add_option('c',   'combo',         opt_type=int,      default=None)
        option_parser.add_option('b',   'breakdown',     opt_type=str,      default=None)
        option_parser.add_option('m',   'mode',          opt_type=int,      default=None)
        option_parser.add_option('cv',  'convert',       opt_type=None,     default=None)
        option_parser.add_option('lb',  'leaderboard',   opt_type=None,     default=None)
        option_parser.add_option('p',   'page',          opt_type=int,      default=1)
        _, options = option_parser.parse(tuple(message.content.split(' ')))

        # other options
        display_graph = (not server_options or \
                (server_options and "graph_beatmap" not in server_options.keys()) or \
                (server_options and "graph_beatmap" in server_options.keys() and server_options['graph_beatmap']))

        for url, mods in all_urls:

            ignore_links = [
                'http://osu.ppy.sh/ss/',
                'https://osu.ppy.sh/ss/',
                'http://ripple.moe/ss/',
                'https://ripple.moe/ss/',
                'screenshot', 'community', 'forum',
                'https://puu.sh', 'discord',
                '.jpg', '.png', 'users', '/u/'
                ]
            is_ignore = any([link in url.lower() for link in ignore_links]) # checked twice..?
            if is_ignore:
                return

            # print("PROCESSING BEATMAP", all_urls)
            # continue

            mod_num = utils.mod_to_num(mods)

            # clean up url
            url = self._clean_beatmap_url(url)

            # log information in variables
            beatmapset_id, beatmap_id, _ = self._url_to_bmapid(url)

            if beatmapset_id and not beatmap_id:
                is_set = True
                beatmap = await self.owoAPI.get_beatmapset(beatmapset_id)
            else:
                is_set = False
                beatmap = await self.owoAPI.get_beatmap(beatmap_id)
            include_graph = display_graph and (len(beatmap) == 1 or options['graph'])

            if options['version']:
                if not is_set:
                    beatmap_set = await self.owoAPI.get_beatmapset(
                        beatmap[0]['beatmapset_id'])
                else:
                    beatmap_set = beatmap

                similar_sig = []
                for i in range(len(beatmap_set)):
                    full_query = '{}'.format(beatmap_set[i]['version'])
                    similar_sig.append(utils.get_similarity(
                        full_query.lower(), options['version'].lower()))
                similar_idx = np.argmax(similar_sig)
                beatmap = [beatmap_set[similar_idx]]
            elif options['set']:
                if not is_set: # otherwise, it should already be a beatmapset
                    beatmap = await self.owoAPI.get_beatmapset(
                        beatmap[0]['beatmapset_id'])

            # handle other filtering options
            indices = []
            for idx, bmp in enumerate(beatmap): # beatmap is a list until this point
                try:
                    if not options['convert'] and options['mode'] is None:
                        if not bool(bmp['convert']): # default
                            indices.append(idx)
                            continue
                except:
                    pass

                is_valid_map = False
                if options['mode'] and int(bmp['mode']) != int(options['mode']):
                    continue
                elif options['mode'] and int(bmp['mode']) == int(options['mode']):
                    is_valid_map = True

                try:
                    if not bool(options['convert']) and bool(bmp['convert']):
                        is_valid_map = False
                    elif bool(options['convert']) and bool(bmp['convert']):
                        is_valid_map = True
                except:
                    is_valid_map = True

                if is_valid_map:
                    indices.append(idx)

            if not indices:
                return await message.channel.send(
                    "**No beatmaps found with those options.**")

            # handle the actual index option
            if options['index']:
                i = min(max(0, int(options['index']) - 1), len(indices))
                indices = [indices[i]]

            beatmap = [beatmap[idx] for idx in indices] # filtered

            if options['leaderboard'] and len(beatmap) == 1:
                gamemode = str(beatmap[0]['mode'])
                leaderboard_info = await self.owoAPI.get_leaderboard(
                    beatmap[0]['beatmap_id'], mods=None, mode=gamemode)
                return await self.disp_leaderboard(message, beatmap, leaderboard_info, 
                    options=options)
            elif options['leaderboard']:
                return await message.channel.send(
                    "**Please specify the map in the mapset by using `-v version_name`.**")

            # stuff with extra info, probably not the best way to do this...
            extra_info = {}
            if options["acc"]:
                extra_info['extra_acc'] = float(str(options["acc"]).replace("%",''))
            elif options["breakdown"] and int(beatmap[0]['mode']) == 0:
                breakdown_txt = options["breakdown"]
                extra_info['play_info'] = self.parse_breakdown(breakdown_txt)
            include_graph = len(beatmap) == 1
            await self.disp_beatmap(message, beatmap,
                mods=''.join(mods), include_graph=include_graph, extra_info=extra_info)

            # pause between each one
            await asyncio.sleep(.25)


    def _newurl_to_gamemode(self, url):
        gamemodes = ['osu','taiko','fruits','mania']
        gamemode = 0
        for mode_idx, m_txt in enumerate(gamemodes):
            if m_txt in url:
                return mode_idx

        return gamemode


    def _clean_beatmap_url(self, url):
        if url.endswith('/'):
            url = url[:-1]
        if "#" in url and "/#" not in url:
            url = url.replace("#","/#")
        if "?" in url:
            url = url.replace("?", '')
        return url
    

    async def disp_leaderboard(self, message, beatmap, leaderboard, options={}):
        beatmap = beatmap[0] # only take the first one if there are multiple

        # print('disp_leaderboard', beatmap.keys()) # **

        # create embed
        em = discord.Embed()
        channel = message.channel

        beatmap_msg = ""

        # determine color of embed based on status
        colour, colour_text = self._determine_status_color(beatmap['status'])
        em.colour = colour

        # download links ifrst layer
        dl_links = self._get_dl_links(beatmap)
        dl_text_links = []
        for dl_name, dl_link in dl_links:
            dl_text_links.append("[{}]({})".format(dl_name, dl_link))
        desc = '**Download:** {}\n'.format(" | ".join(dl_text_links))
        em.description = desc

        # generate information
        if 'max_combo' in beatmap.keys() and beatmap['max_combo'] != None:
            objects_label = "Objects"
            max_combo = 'x{}'.format(beatmap['max_combo'])
        else:
            objects_label = "Max Combo"
            max_combo = 'x{}'.format(
                int(beatmap['count_circles']) + int(beatmap['count_sliders']))
    
        stars_str = float(beatmap["difficulty_rating"])
        ar_str = float(beatmap["ar"])
        od_str = float(beatmap["od"])
        hp_str = float(beatmap["hp"])
        cs_str = float(beatmap["cs"])

        beatmap_info = ""
        m0, s0 = divmod(int(beatmap['total_length']), 60)
        beatmap_info += '**▸Length:** {}:{}  **▸BPM:** {:.1f} '.format(
            m0, str(s0).zfill(2), float(beatmap['bpm']))
        beatmap_info += "**▸Diff:** {:.2f}★ **▸{}:** {}\n".format(
            stars_str, objects_label, max_combo)
        beatmap_info += "**▸AR:** {:.1f} **▸OD:** {:.1f} **▸HP:** {:.1f} **▸CS:** {:.1f}\n".format(
            ar_str, od_str, hp_str, cs_str)

        leaderboard_txt = "\n"
        page = int(options['page'])
        per_page = 10
        start_idx = (page-1) * per_page
        end_idx = page * per_page
        for ld_idx, player_score in enumerate(leaderboard[start_idx:end_idx]):
            num_rank = start_idx + ld_idx + 1 

            breakdown_txt = self._get_score_breakdown(player_score, beatmap['mode'])
            mod_emotes, mod_list = self.mod_num_to_emotes(player_score['enabled_mods'])
            if mod_emotes:
                if len(mod_list) > 3:
                    mod_emotes = "+{} MODS".format(len(mod_list))
                else:
                    mod_emotes = '+' + mod_emotes
            player_acc = float(utils.calculate_acc(player_score, beatmap['mode']))
            try:
                # metric_txt = '{:.2f}'.format(round(float(player_score['pp']), 2)) + "pp"
                metric_txt = '{:.2f}'.format(round(float(player_score['pp']), 2)) + "pp"
            except:
                metric_txt = '{:.3}k'.format(int(player_score['score'])/1000)

            leaderboard_txt += "`{:<3}`{}`{:<15} {:<7.2f} {:<3} {:<6} {:<8} {:<6}`\n".format(num_rank, 
                self.RANK_EMOTES[player_score['rank']], player_score['username'][:15], 
                player_acc, player_score['count_miss'] + "m", "x" + player_score['max_combo'],
                metric_txt, mod_emotes)

        complete_text = beatmap_info + leaderboard_txt
        diff_name = self._determine_emote_name(beatmap)
        diff_emote = self.DIFF_EMOTES[str(beatmap['mode'])][diff_name]
        em.add_field(name = "{} __{}__\n".format(
            diff_emote, beatmap['version']), 
            value=complete_text, inline=False)

        # create return em
        beatmap_user_icon = await self.owoAPI.get_user_avatar(
            beatmap['user_id'], 'bancho')
        beatmap_url = self.owoAPI.get_beatmap_url(beatmap)
        em.set_author(name="{} – {} by {}".format(
            beatmap['artist'], beatmap['title'], 
            beatmap['creator']), url=beatmap_url,
            icon_url=beatmap_user_icon)

        # footer: status, favorite count, created/appr/rank date
        fav_count = "{} ❤︎ | ".format(beatmap["favourite_count"])

        if str(beatmap['status']) == '2' or str(beatmap['status']) == '1':
            status_txt = 'Approved'
            status_key = 'ranked_date'
        else:
            status_txt = 'Last Updated'
            status_key = 'last_update'
        rel_time = datetime.datetime.strptime(beatmap[status_key], '%Y-%m-%d %H:%M:%S').strftime('%B %d %Y')
        em.set_footer(text = '{} | {}{} {}'.format(colour_text, fav_count, status_txt, rel_time))

        map_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap)
        em.set_thumbnail(url=map_image_url)

        await channel.send(embed = em)


    def mod_num_to_emotes(self, mod_num):
        mod_list = utils.num_to_mod(mod_num)
        emote_str = ""
        for mod in mod_list:
            emote_str += "{}".format(mod)
        emote_str = utils.fix_mods(emote_str)
        return emote_str, mod_list


    # displays the beatmap properly
    async def disp_beatmap(self, message, beatmap, 
        mods='', include_graph=False, extra_info={}):

        # determine mods, mods is a string
        mod_num = utils.mod_to_num(mods)
        mods = utils.fix_mods("".join(utils.num_to_mod(mod_num))) # rid of random inputs

        # create embed
        em = discord.Embed()
        channel = message.channel

        # message
        msg = None
        num_disp = min(len(beatmap), self.MAX_MAP_DISP)
        if (len(beatmap) > self.MAX_MAP_DISP):
            msg = "Found {} maps, but only displaying {}.\n".format(len(beatmap), self.MAX_MAP_DISP)

        # sort by difficulty first
        map_order = []
        for i in range(len(beatmap)):
            map_order.append((i,float(beatmap[i]['difficulty_rating'])))
        map_order = sorted(map_order, key=operator.itemgetter(1), reverse=True)
        map_order = map_order[0:num_disp]

        beatmap_msg = ""
        accs = [95, 99, 100]
        """
        if int(beatmap['mode']) == 3:
            accs = [850000, 950000, 1000000] # 万"""
        if 'extra_acc' in extra_info.keys():
            extra_acc = extra_info['extra_acc']
            if extra_acc <= accs[0]:
                accs[0] = extra_acc
            elif accs[0] < extra_acc <= accs[1]:
                accs[1] = extra_acc
            elif accs[1] < extra_acc <= accs[2]:
                accs[1] = extra_acc

        # determine color of embed based on status
        colour, colour_text = self._determine_status_color(beatmap[0]['status'])

        # get other info for beatmap
        # print(beatmap[0]['beatmap_id'])
        full_beatmap_info, bmap_raw, bmap_file_path = await self.owoAPI.get_full_beatmap_info(
            beatmap[0], accs=accs, mods=mod_num)

        # use total_length_mod
        _, is_diff_length = self.compare_val_params(
            full_beatmap_info, "total_length", "total_length_mod")
        if is_diff_length:
            m0, s0 = divmod(int(full_beatmap_info['total_length']), 60)
            m1, s1 = divmod(int(full_beatmap_info['total_length_mod']), 60)
            desc = '**Length:** {}:{}({}:{})  **BPM:** {:.1f}({:.1f}) '.format(
                m0, str(s0).zfill(2), m1, str(s1).zfill(2), 
                float(full_beatmap_info['bpm']), float(full_beatmap_info['bpm_mod']))
        else:
            m0, s0 = divmod(int(full_beatmap_info['total_length']), 60)
            desc = '**Length:** {}:{}  **BPM:** {:.1f} '.format(
                m0, str(s0).zfill(2), float(full_beatmap_info['bpm']), 
                float(full_beatmap_info['bpm_mod']))

        # Handle mods
        desc += "**Mods:** "
        if mods != '':
            desc += mods
        else:
            desc += '-'
        desc += '\n'

        # handle times
        times = []
        for i, diff in map_order:
            # handle times
            times.append(beatmap[i]['last_update'])
            try:
                if beatmap[0]['status'] == 2 or beatmap[0]['status'] == 1:
                    times.append(beatmap[i]['last_updated'])
            except:
                pass

            # calculate pp for other gamemodes if necessary
            gamemode = int(beatmap[i]['mode'])
            if i == 0:
                bmap_calculated_info = full_beatmap_info
            else:
                # print('BEATMAP KEYS', gamemode, beatmap[i]['mode'], 
                    # beatmap[i]['mode_int'], beatmap[i]['convert'])
                bmap_calculated_info, bmap_raw, bmap_file_path = \
                    await self.owoAPI.get_full_beatmap_info(
                        beatmap[i], accs=accs, mods=mod_num)

            # updated values, if it has the oppai value, it will give it
            if gamemode == 0:
                single = False
                stars_str, _ = self.compare_val_params(bmap_calculated_info, 
                    "difficulty_rating", "stars_mod", single=single)
            else: # for other gamemodes
                stars_str = self.adjust_val_str_mod(
                    bmap_calculated_info, "difficulty_rating", mod_num, gamemode)
            stars_str = '{}★'.format(stars_str)
            stars_str = self._fix_star_arrow(stars_str)

            if 'max_combo' in bmap_calculated_info and \
                bmap_calculated_info['max_combo'] != None:
                max_combo = 'x{}'.format(bmap_calculated_info['max_combo'])
            else:
                max_combo = '-'

            if gamemode == 0:
                ar_str, _ = self.compare_val_params(bmap_calculated_info, "ar", "ar_mod", precision=1, single=single)
                od_str, _ = self.compare_val_params(bmap_calculated_info, "od", "od_mod", precision=1, single=single)
                hp_str, _ = self.compare_val_params(bmap_calculated_info, "hp", "hp_mod", precision=1, single=single)
                cs_str, _ = self.compare_val_params(bmap_calculated_info, "cs", "cs_mod", precision=1, single=single)
            else:
                ar_str = self.adjust_val_str_mod(bmap_calculated_info, "ar", mod_num, gamemode)
                od_str = self.adjust_val_str_mod(bmap_calculated_info, "od", mod_num, gamemode)
                hp_str = self.adjust_val_str_mod(bmap_calculated_info, "hp", mod_num, gamemode)
                cs_str = self.adjust_val_str_mod(bmap_calculated_info, "cs", mod_num, gamemode)                

            beatmap_info = ""
            beatmap_info += "**▸Difficulty:** {} **▸Max Combo:** {}\n".format(
                stars_str, max_combo)
            if gamemode in [1, 3]:
                beatmap_info += "**▸OD:** {} **▸HP:** {} **▸CS:** {}\n".format(
                    od_str, hp_str, cs_str)
            else:
                beatmap_info += "**▸AR:** {} **▸OD:** {} **▸HP:** {} **▸CS:** {}\n".format(
                    ar_str, od_str, hp_str, cs_str)

            # calculate pp values
            beatmap_info += '**▸PP:** '
            # print('BEATMAP PP MOD', bmap_calculated_info['pp_mod'])
            for j in range(len(accs[0:3])):
                beatmap_info += '○ **{}%**–{:.2f} '.format(
                    accs[j], bmap_calculated_info['pp_mod'][j])

            # determine if convert
            convert_txt = ''
            if 'convert' in beatmap[i] and beatmap[i]['convert']:
                convert_txt = ' [convert]'

            diff_name = self._determine_emote_name(beatmap[i])
            diff_emote = self.DIFF_EMOTES[str(gamemode)][diff_name]
            em.add_field(name = "{} __{}__{}\n".format(
                diff_emote, bmap_calculated_info['version'], convert_txt), 
                value=beatmap_info, inline=False)

        # download links
        dl_links = self._get_dl_links(beatmap[i])
        dl_text_links = []
        for dl_name, dl_link in dl_links:
            dl_text_links.append("[{}]({})".format(dl_name, dl_link))
        desc += '**Download:** {}\n'.format(" | ".join(dl_text_links))

        # create return em
        em.colour = colour
        em.description = desc
        try:
            beatmap_user_icon = await self.owoAPI.get_user_avatar(
                beatmap[0]['user_id'], 'bancho')
        except:
            beatmap_user_icon = "https://i.imgur.com/LrnCwlp.png"
        beatmap_url = self.owoAPI.get_beatmap_url(bmap_calculated_info)
        em.set_author(name="{} – {} by {}".format(
            bmap_calculated_info['artist'], bmap_calculated_info['title'], 
            bmap_calculated_info['creator']), url=beatmap_url,
            icon_url = beatmap_user_icon)

        # await self.bot.send_message(message.channel, map_image_url)
        for_user = ''
        if 'username' in extra_info.keys():
            username = extra_info['username']
            for_user = 'Request for {} | '.format(username)

        # favorite count
        fav_count = "{} ❤︎ | ".format(bmap_calculated_info["favourite_count"])

        times = sorted(times, reverse=True)
        # icon_url = self.owoAPI.get_server_avatar('bancho')
        if str(bmap_calculated_info['status']) == '1':
            rel_time = datetime.datetime.strptime(
                bmap_calculated_info['ranked_date'], '%Y-%m-%d %H:%M:%S').strftime('%B %d %Y')
            em.set_footer(text = '{} | {}{}Approved {}'.format(
                colour_text, fav_count, for_user, rel_time))
        else:
            rel_time = datetime.datetime.strptime(
                times[0], '%Y-%m-%d %H:%M:%S').strftime('%B %d %Y')
            em.set_footer(text = '{} | {}{}Last Updated {}'.format(
                colour_text, fav_count, for_user, rel_time))

        # images
        if include_graph:
            rgb_color = '#{}'.format('{:02X}'.format(colour).rjust(6, '0'))

            beatmap_chunks = await self.owoAPI.get_beatmap_chunks(
                beatmap[i], bmap_file_path) # no mods, cause they really don't matter
            discord_file, graph_url = await map_utils.plot_map_stars(
                beatmap_chunks, bmap_calculated_info, color=rgb_color)

            if not discord_file:
                map_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap[0])
                em.set_thumbnail(url=map_image_url)
                if msg:
                    await channel.send(msg, embed=em)
                else:
                    await channel.send(embed=em)
            else:
                em.set_image(url=graph_url)
                await channel.send(msg, files=[discord_file], embed = em)
        else:
            map_image_url = self.owoAPI.get_beatmap_thumbnail(beatmap[0])
            em.set_thumbnail(url=map_image_url)
            if msg:
                await channel.send(msg, embed=em)
            else:
                await channel.send(embed=em)


    def _fix_star_arrow(self, star_str):
        if '🠗' in star_str:
            star_str = star_str.replace('🠗', '')
            star_str += '🠗'
        elif '🠕' in star_str:
            star_str = star_str.replace('🠕', '')
            star_str += '🠕'
            
        return star_str

    def adjust_val_str_mod(self, info, param, mod_num, gamemode):

        mod_list = utils.num_to_mod(mod_num)

        # sort so that HT, DT, NC are first because of cs
        mod_list = sorted(mod_list, 
            key=lambda e: (e in ['HT', 'DT', 'NC'], e), reverse=True)

        # print(mod_list)

        decr_mods = ['HT', 'EZ']
        incr_mods = ['DT', 'NC', 'HR']

        float_str = round(float(info[param]), 2)
        ret_str = '{:.2f}'.format(float_str)
        for mod in mod_list:
            if mod in decr_mods:
                if (param == 'cs' and mod == 'HT') or \
                    (gamemode == 3 and param in ['cs','od','hp']):
                    ret_str = '{:.2f}'.format(float_str)
                else:
                    ret_str = '{:.2f}🠗'.format(float_str)

            elif mod in incr_mods:
                if (param == 'cs' and (mod == 'DT' or mod == 'NC')) or \
                    (gamemode == 3 and param in ['cs','od','hp']):
                    ret_str = '{:.2f}'.format(float_str)
                else:
                    ret_str = '{:.2f}🠕'.format(float_str)
             
        return ret_str


    def compare_val_params(self, data, key_1, key_2, precision=2, single=False):
        data_1 = float(data[key_1])
        data_1_fmt = "{value:{width}.{precision}f}".format(
            value=data_1, width=0, precision=precision)

        try:
            data_2 = float(data[key_2])
            data_2_fmt = "{value:{width}.{precision}f}".format(
                value=data_2, width=0, precision=precision)

            max_num = max(data_1, data_2)
            if abs(data_2-data_1) > max_num * .03 and data_2 != 0:
                if single:
                    return f'{data_2_fmt}', True
                else:
                    return f'{data_1_fmt}({data_2_fmt})', True
            return f'{data_1_fmt}', False
        except:
            return f'{data_1_fmt}', False


    def compare_vals(self, map_stat, omap, param, dec_places:int = 1, single = False):
        try:
            if not map_stat:
                if param in omap.keys():
                    return omap[param], int(omap[param])
                return "None", None
            elif not omap:
                if dec_places == 0:
                    return "{}".format(int(float(map_stat))), int(float(map_stat))
                return "{}".format(round(float(map_stat), dec_places)), round(float(map_stat), dec_places)
            elif omap and not map_stat:
                if dec_places == 0:
                    return "{}".format(int(float(omap[param]))), int(float(omap[param]))
                return "{}".format(round(float(omap[param]), dec_places)), round(float(omap[param]), dec_places)
            else:
                map_stat = float(map_stat)
                op_stat = float(omap[param])
                if int(round(op_stat, dec_places)) != 0 and abs(round(map_stat, dec_places) - round(op_stat, dec_places)) > 0.05:
                    if single:
                        if dec_places == 0:
                            return "{}".format(int(float(op_stat))), int(float(op_stat))
                        return "{}".format(round(op_stat, dec_places)), round(op_stat, dec_places)
                    else:
                        if dec_places == 0:
                            return "{}({})".format(int(float(map_stat)), int(float(op_stat))), int(float(op_stat))
                        return "{}({})".format(round(map_stat, dec_places),
                            round(op_stat, dec_places)), round(op_stat, dec_places)
                else:
                    if dec_places == 0:
                        return "{}".format(int(float(map_stat))), int(float(map_stat))
                    return "{}".format(round(map_stat, dec_places)), round(map_stat, dec_places)
        except:
            if dec_places == 0:
                return "{}".format(int(float(map_stat))), int(float(map_stat))
            return "{}".format(round(map_stat, dec_places)), round(map_stat, dec_places)


    def _get_dl_links(self, beatmap_info):
        ret = []

        if 'video' in beatmap_info and int(beatmap_info['video']):
            vid = 'https://osu.ppy.sh/d/{}'.format(
                beatmap_info['beatmapset_id'])
            ret.append(('map', vid))
            novid = 'https://osu.ppy.sh/d/{}n'.format(
                beatmap_info['beatmapset_id'])
            ret.append(('no vid', novid))
        else:
            novid = 'https://osu.ppy.sh/d/{}'.format(
                beatmap_info['beatmapset_id'])
            ret.append(('map', novid))

        # direct = 'osu://dl/{}'.format(beatmap_info['beatmapset_id'])
        # ret.append(('direct', direct))
        # bloodcat = 'https://bloodcat.com/osu/s/{}'.format(beatmap_info['beatmapset_id'])
        # ret.append(('bloodcat', bloodcat))
        nerina = 'https://nerina.pw/d/{}'.format(beatmap_info['beatmapset_id'])
        ret.append(('nerina', nerina))        
        beatconnect = 'https://beatconnect.io/b/{}/'.format(beatmap_info['beatmapset_id'])
        ret.append(('beatconnect', beatconnect))
        sayobot = 'https://osu.sayobot.cn/osu.php?s={}'.format(beatmap_info['beatmapset_id'])
        ret.append(('sayobot', sayobot))

        return ret


    def _determine_status_color(self, status):
        # print('map status', status)
        colour = 0xFFFFFF
        text = 'Unknown'

        is_int = False
        try:
            status = int(status)
            is_int = True
        except ValueError:
            status = status.lower()

        if is_int:
            if status == -2: # graveyard, red
                colour = 0xc10d0d
                text = 'Graveyard'
            elif status == -1: # WIP, purple
                colour = 0x713c93
                text = 'Work in Progress'
            elif status == 0: # pending, blue
                colour = 0x1466cc
                text = 'Pending'
            elif status == 1: # ranked, bright green
                colour = 0x02cc37
                text = 'Ranked'
            elif status == 2: # approved, dark green
                colour = 0x0f8c4a
                text = 'Approved'
            elif status == 3: # qualified, turqoise
                colour = 0x00cebd
                text = 'Qualified'
            elif status == 4: # loved, pink
                colour = 0xea04e6
                text = 'Loved'
        else:
            status = str(status).lower()
            if status == 'graveyard': # graveyard, red
                colour = 0xc10d0d
                text = 'Graveyard'
            elif status in ['work in progress', 'wip']: # WIP, purple
                colour = 0x713c93
                text = 'Work in Progress'
            elif status == 'pending': # pending, blue
                colour = 0x1466cc
                text = 'Pending'
            elif status == 'ranked': # ranked, bright green
                colour = 0x02cc37
                text = 'Ranked'
            elif status == 'approved': # approved, dark green
                colour = 0x0f8c4a
                text = 'Approved'
            elif status == 'qualified': # qualified, turqoise
                colour = 0x00cebd
                text = 'Qualified'
            elif status == 'loved': # loved, pink
                colour = 0xea04e6
                text = 'Loved'

        return (colour, text)


# ------------------------ database functions ----------------------------
    async def get_user(self, user):
        # print(str(user.id))
        find_user = await self.players.find_one({"user_id":str(user.id)})
        if not find_user:
            return None
        return find_user

# ----------------------- Tracking Section -------------------------------

    @commands.group(name = "track")
    async def osutrack(self, ctx):
        """Set some tracking options"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return


    # @commands.cooldown(1, 300, commands.BucketType.user)
    @osutrack.command(name = "latency", no_pm=True)
    async def track_latency(self, ctx):
        """
        Check tracking latency for past 300 plays.

        [Example]
        +<COMMAND>
        """
        return
        channel = ctx.message.channel
        latency = await self.track_latency.find_one(
            {'shard_id':'{}'.format(str(self.bot.shard_id))})
        shard_latencies = {}
        all_latencies = []

        for shard_id in range(self.bot.shard_count):
            latency = await self.track_latency.find_one(
                {'shard_id':'{}'.format(str(shard_id))})
            all_latencies.extend(latency)
            shard_latencies[shard_id] = latency

        plt.figure(figsize=(10, 5))
        plt.style.use('ggplot')
        self.latency = collections.deque([i for i in self.latency if i < 1200], maxlen = 300)
        x = np.array(self.latency)/60 # for minutes
        plt.hist(x, bins=18, color='c')
        plt.axvline(x.mean(), color='b', linestyle='dashed', linewidth=2)
        plt.xlabel('min')
        plt.ylabel('# Plays')
        plt.tight_layout()
        filepath = 'cogs/osu/temp/latency.png'
        plt.savefig(filepath)
        plt.close()
        await self.bot.send_file(channel, filepath, content='**Tracking Latency for Previous 300 Plays**')
        # self.save_latency()


    @commands.cooldown(1, 5, commands.BucketType.guild)
    @osutrack.command(name="list", no_pm=True)
    async def track_list(self, ctx):
        """
        Check which players are currently tracked in the channel.

        [Example]
        +track <COMMAND>
        """
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        channel_tracks = {}
        channel_totals = {}
        # ----------------------- find country tracks ---------------
        country_settings = {} # channel_id > country > modes/settings
        server_query = {'server_id': str(server.id)}
        country_tracks = await self.track_country.find_one(server_query)
        if country_tracks:
            for channel_id in country_tracks['channels']:
                for country in country_tracks['channels'][channel_id]:
                    country_settings = country_tracks['channels'][channel_id][country]
                        
                    track_channel = self.bot.get_channel(int(channel_id))
                    if track_channel.name not in channel_tracks:
                        channel_tracks[track_channel.name] = []
                        channel_totals[track_channel.name] = 0

                    channel_totals[track_channel.name] += country_settings['num_players']
                    country_settings_str = self._display_country_track_options(country_settings)
                    full_ctry_str = "**{}** {}".format(country, country_settings_str)

                    channel_tracks[track_channel.name].append(full_ctry_str)
        else:
            country_tracks = []

        # print(channel_tracks)

        # ------------------------ find player tracks ----------------
        query = {"servers.{}".format(server.id): {"$exists": True}}
        ret_fields = {
            "servers.{}.top".format(server.id): 1, 
            "username": 1
        }

        total_people = 0
        async for track_user in self.track.find(query, ret_fields):
            track_user_settings = track_user['servers'][str(server.id)]['top']

            # print('TUS', track_user['username'], track_user_settings)
            # group settings
            setting_by_channel = {}
            for mode in track_user_settings:
                mode_settings = track_user_settings[mode]
                channel_id = mode_settings["channel_id"]
                track_channel = self.bot.get_channel(int(channel_id))

                if track_channel.name not in setting_by_channel.keys():
                    setting_by_channel[track_channel.name] = {}

                if 'gamemodes' not in setting_by_channel[track_channel.name]:
                    setting_by_channel[track_channel.name]['gamemodes'] = []

                setting_by_channel[track_channel.name]['gamemodes'].append(
                    utils.mode_to_num(mode))

                for setting in mode_settings:
                    setting_by_channel[track_channel.name][setting] = \
                        mode_settings[setting]
            
            # print('SBC', track_user['username'], setting_by_channel)

            for channel_name in setting_by_channel:
                channel_settings = setting_by_channel[channel_name]
                player_settings_str = self._display_player_track_options(channel_settings)
                full_player_str = "__{}__ {}".format(track_user['username'], player_settings_str)
                if channel_name not in channel_tracks:
                    channel_tracks[channel_name] = []

                channel_tracks[channel_name].append(full_player_str)
                
                if not channel_name in channel_totals:
                    channel_totals[channel_name] = 0
                channel_totals[channel_name] += 1

            # print('CT', channel_tracks)

        total_tracked = await self._get_server_track_num(server)

        # format and print
        embeds = []
        start_page = 0
        current_page = 0
        for channel_name in channel_tracks.keys():
            total_in_channel = channel_totals[channel_name]
            total_items = len(channel_tracks[channel_name])

            # for a single channel
            num_per_page = 30
            total_pages = math.ceil(total_items/num_per_page)
            for page in range(total_pages):
                if page == 0 and channel_name == channel.name:
                    start_page = current_page

                start_index = (page)*num_per_page
                end_index = (page+1)*num_per_page
                players = sorted(channel_tracks[channel_name])
                page_list = players[start_index:end_index]

                em = discord.Embed(colour=user.colour)
                em.set_author(name="osu! Players Currently Tracked in {} ({})".format(
                    server.name, total_tracked), icon_url = server.icon_url)
                
                continued = ""
                if page != 0:
                    continued = " continued..."
                em.add_field(name = "#{} ({}){}".format(
                    channel_name, total_in_channel, continued),
                    value = ", ".join(page_list))
                embeds.append(em)
                current_page += 1

        if embeds:
            for i, em in enumerate(embeds):
                em.set_footer(text = "Page {} of {}".format(i+1, len(embeds)))
            await self.bot.menu(ctx, embeds, message=None, page=start_page, timeout=15)
        else:
            await ctx.send("**No one is being tracked in this server.**")


    @commands.cooldown(1, 5, commands.BucketType.guild)
    @checks.mod_or_permissions(manage_guild = True)
    @osutrack.command(name="add", no_pm=True)
    async def track_add(self, ctx, *usernames):
        """
        Adds a player to track for top scores. Tracking by country only counts by # plyarers. x = not implemented yet.

        [Options]
        usernames: Username of the player. Also works for roles
        Server:  <osu_servers> x
        Mode (-m): 0 = std, 1 = taiko, 2 = ctb, 3 = mania
        Top Plays (-t): Number of top plays to include in tracking (1-100)
        Country (-c): Track top players from country. Use 2-char country code; try https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2. "global" for global
        Num Players (-p): Used in conjunction with (-c), track top X players from that country. (1-50)
        Overwrite (-o): To completely overwrite previously tracked user as opposed to update with new info. (no params)

        [Example]
        +track <COMMAND> "<USER>" -m 03 -t 30
        """
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        # server tracking limits
        # await self.track_country.drop() # obviously comment this out

        if not usernames:
            return await self.bot.send_cmd_help(ctx)

        # print(server.id)
        track_num = await self._get_server_track_num(server)
        if str(server.id) in ['290312423309705218', '462114721290780672']:
            track_limit = None
        elif str(server.id) in ['287849068280152064']:
            track_limit = 400
        elif str(server.id) in []:
            track_limit = 300
        elif str(server.id) in []:
            track_limit = 250
        else:
            track_limit = self.TRACK_LIMIT

        # print('TRACK LIMIT', track_limit)

        msg = ""
        count_add = 0
        count_update = 0

        # gets options for tracking
        try:
            options, server_options = self.server_option_parser(usernames)
            api = self.determine_api(server_options)
            option_parser = OptionParser()
            option_parser.add_option('m',   'mode',             opt_type=str,       default=None)
            option_parser.add_option('r',   'role',             opt_type=str,       default=None)
            option_parser.add_option('t',   'top_num',          opt_type=int,       default=None)
            option_parser.add_option('pp',  'pp_min',           opt_type=int,       default=None)
            option_parser.add_option('c',   'country',          opt_type=str,       default=None)
            option_parser.add_option('p',   'top_player_num',   opt_type=int,       default=None)
            option_parser.add_option('o',   'overwrite',        opt_type=None,      default=False)
            usernames, options = option_parser.parse(options)
        except:
            await ctx.send("**Please check your options.**")

        if api != "bancho":
            return ctx.send("**Tracking currently only available for `Bancho`.**")

        # define defaults for a single player
        default_player_options = {
            "gamemodes": [0],
            "plays": 50,
            "pp_min": 0
        }
        default_server_options = {
            "server_id": str(server.id),
            "channels": {},
            "api": api
        }

        # handle options needed for both player and server
        player_options = copy.deepcopy(default_player_options)
        if options['mode']:
            final_modes = []
            valid_modes = [0,1,2,3]
            for mode_num in options['mode']:
                if mode_num.isdigit() and int(mode_num) in valid_modes:
                    final_modes.append(int(mode_num))
            if not final_modes:
                player_options["gamemodes"] = default_player_options["gamemodes"]
            else:
                player_options["gamemodes"] = final_modes
        if options['top_num']:
            try:
                player_options["plays"] = min(int(options['top_num']), 100)
            except:
                player_options["plays"] = default_player_options["top"]
        if options['pp_min']:
            try:
                player_options['pp_min'] = int(options['pp_min'])
            except:
                player_options['pp_min'] = default_player_options["pp_min"]

        # ------------------------- adding countries ---------------------------

        if options['country']:
            db_country_track = await self.track_country.find_one(
                {"server_id": str(server.id)})

            # handle country options
            country_codes = options['country'].split(',')
            final_country_codes = []
            for country in country_codes:
                if 'global' in country:
                    final_country_codes.append("GLOBAL")
                else:
                    final_country_codes.append(countries.get(country).alpha2)

            if options['top_player_num']:
                temp_player_num = int(options['top_player_num'])
            else:
                temp_player_num = 25 # is the default

            # calculate how many they can track
            # print('RUNNING COUNTRY TRACK OPTION')
            # await self.track_country.drop() # obviously comment this out
            country_track = default_server_options

            if db_country_track:
                # print('Found previous server data.')
                country_track['channels'] = db_country_track['channels']

            if str(channel.id) not in country_track['channels']:
                country_track['channels'][str(channel.id)] = {}

            for country in final_country_codes:
                if country not in country_track['channels'][str(channel.id)]:
                    country_track['channels'][str(channel.id)][country.upper()] = {}

                country_track['channels'][str(channel.id)][country.upper()] = {
                    "modes": player_options["gamemodes"],
                    "num_players": temp_player_num,
                    "plays": player_options["plays"],
                    "pp_min": player_options['pp_min']
                }

                if country == 'GLOBAL':
                    country_name = 'Global'
                else:
                    country_name = countries.get(country).name

                msg += '**Tracking top `{}` player{} from `{}` for gamemode{} `{}`.**\n'.format(
                    temp_player_num, self._plural_text(temp_player_num), 
                    country_name, self._plural_text(player_options["gamemodes"]),','.join(
                        [str(gm) for gm in player_options["gamemodes"]]))

                count_add += temp_player_num # won't count by modes

            # determine if this track operation is allowed based on track limit
            hypo_total_track_num = await self._get_server_track_num(server, 
                new_country_settings=country_track)
            # total_track = hypo_track_num + len(final_country_codes) * temp_player_num
            if track_limit and hypo_total_track_num > track_limit:
                return await ctx.send("**`{}` players are currently tracked in this server. " \
                    "Adding `{}` countries with `{}` players each will put you `{}` over the limit. " \
                    "Consider adding countries individually, decreasing player number (`-p #`), or removing tracked players.**".format(
                        track_num, len(final_country_codes), temp_player_num, hypo_total_track_num - track_limit))
            else:
                # save to the database
                await self.track_country.update_one(
                    {"server_id": str(server.id)}, {"$set":country_track}, upsert=True)

                # show the server settings for debugging
                """
                test_res = await self.track_country.find_one(
                    {"server_id": str(server.id)})
                print(test_res)"""

        # ---------------------- adding users -------------------------         

        # process usernames that are mentions and/or role stuff
        add_usernames = []
        if options['role']:
            role_name = str(options['role'])
            role_success = False
            for role in server.roles:
                if role.name.lower() == role_name.lower():
                    role_success = True
                    role_member_ids = [str(member.id) for member in role.members]

                    db_users = await self.players.find(
                        {"user_id":{"$in": role_member_ids}}, {"osu_username"})

                    new_usernames = [db_user["osu_username"] for db_user in db_users]
                    add_usernames.extend(new_usernames)
                    break

            if not role_success:
                await ctx.send("**`{}` role not found.**".format(role_name))

            # print(new_usernames) # **

        for username in list(usernames):
            if "<@&" in username: # mentioned role
                role_id = int(username.replace('<@&','').replace('>', ''))
                role = server.get_role(role_id)
                role_member_ids = [str(member.id) for member in role.members]
                # print('Role member IDs', role_member_ids)
                db_users = []
                async for db_user in self.players.find(
                    {"user_id":{"$in": role_member_ids}}, {"osu_username"}):
                    db_users.append(db_user)
                new_usernames = [db_user["osu_username"] for db_user in db_users]
                add_usernames.extend(new_usernames)
            elif "<@!" in username or "<@" in username: # mentioned user
                discord_user_id = int(username.replace('<@!','').replace('<@','').replace('>',''))
                member = server.get_member(discord_user_id)
                db_user = await self.players.find_one({"user_id":str(member.id)})
                if not db_user:
                    await ctx.send("**`{}` does not have an account linked. Use `>osuset user \"your username\"`.**".format(member.name))
                else:
                    add_usernames.append(db_user["osu_username"])
            else: # just a regular string
                member = await ctx.guild.query_members(query=username)
                db_user = None
                if member:
                    member = member[0]
                    db_user = await self.players.find_one({"user_id":str(member.id)})
                
                if not db_user:
                    add_usernames.append(username)
                else:
                    add_usernames.append(db_user["osu_username"])

        add_usernames = list(set(add_usernames))

        counter = 0
        for username in add_usernames:
            total_tracked = count_add + counter + track_num
            if (track_limit is not None and total_tracked >= track_limit):
                return await ctx.send('**You are at or passed the user tracking limit: `{}`/`{}`.**'.format(
                    str(total_tracked), str(track_limit)))
                """
                msg = "**Added `{}` users to tracking on `#{}`. {}**".format(
                    count_add, channel.name, self._display_player_track_options(options))
                break"""

            # try to get it from the cache first, then try the api
            cache_info = await self.owoAPI.cache.user.entries.find_one(
                {"data.username": username, "api": api})
            cache_info_id = await self.owoAPI.cache.user.entries.find_one(
                {"data.user_id": username, "api": api})
            if cache_info:
                userinfo = [cache_info['data']]
            elif cache_info_id:
                userinfo = [cache_info_id['data']]
            else: # try the cache
                userinfo = await self.owoAPI.get_user(username, mode=0)
                await asyncio.sleep(.1)

            if not userinfo or len(userinfo) == 0:
                msg += "`{}` does not exist in the osu! database.\n".format(username)
            else:
                track_num += 1
                userinfo = userinfo[0]
                username = str(userinfo['username'])
                osu_id = str(userinfo["user_id"])

                track_user = await self.track.find_one({"osu_id":osu_id})
                if not track_user:
                    track_user = await self.track.find_one({"username":username})

                if not track_user:
                    if username:
                        print("Existing Create ID")
                        await self.track.update_one({"username":username},
                            {'$set':{"osu_id":osu_id}})
                    else:
                        new_json = {}
                        # handle user information
                        new_json['api'] = api
                        new_json['username'] = username
                        new_json['osu_id'] = osu_id
                        new_json["userinfo"] = {}
                        for mode in self.MODES:
                            # try to get info from cache!
                            cached_user = await self.owoAPI.cache.user.entries.find_one(
                                {"data.user_id": osu_id, "api": api, "mode": utils.mode_to_num(mode)})
                            if cached_user:
                                userinfo = cached_user['data']
                            else:
                                userinfo = await self.owoAPI.get_user(username, mode=mode)
                                userinfo = userinfo[0]

                            new_json["userinfo"][mode] = userinfo
                            await asyncio.sleep(self.SLEEP_TIME)

                        # handle server options
                        new_json["servers"] = {}
                        new_json["servers"][str(server.id)] = {}
                        new_json["servers"][str(server.id)]["top"] = {}
                        # new_json["servers"][str(server.id)]["options"] = options

                        # each tracked player for a server can be tracked in different channels for each gamemode.
                        for mode_num in options['gamemodes']:
                            new_json["servers"][str(server.id)]["top"][self.MODES[mode_num]] = {}
                            new_json["servers"][str(server.id)]["top"][self.MODES[mode_num]]["channel_id"] = str(channel.id)
                            new_json["servers"][str(server.id)]["top"][self.MODES[mode_num]]["plays"] = options["plays"]

                        # add last tracked time
                        current_time = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                        new_json["last_check"] = current_time
                        await self.track.insert_one(new_json)
                    count_add += 1
                    msg += "**`{}` added. Will now track on `#{}`. {}**\n".format(
                        username, channel.name, self._display_player_track_options(player_options))
                else:

                    # clean up database_user, then update. fix legacy version
                    track_user = await self._clean_track_db_user(track_user, api)

                    # track_user, orignal object is this
                    if "servers" not in track_user:
                        track_user["servers"] = {}

                    if str(server.id) not in track_user["servers"]:
                        track_user["servers"][str(server.id)] = {}
                        track_num += 1

                    count_add += 1

                    ## update server options, if -o in username, then start from scratch, otherwise update
                    if options['overwrite']: # do only what was defined in options/replace old format
                        gm_json = {}
                    else:
                        try:
                            gm_json = track_user["servers"][str(server.id)]["top"]
                        except:
                            gm_json = {}

                    for mode_num in player_options['gamemodes']:
                        gm_json[self.MODES[mode_num]] = {}
                        gm_json[self.MODES[mode_num]]["channel_id"] = str(channel.id)
                        gm_json[self.MODES[mode_num]]["plays"] = player_options["plays"]

                    await self.track.update_one({"osu_id":osu_id, "api":api}, 
                        {'$set':{
                            "servers.{}.options".format(str(server.id)): player_options,
                            "servers.{}.top".format(server.id): gm_json
                        }})

                    msg += "**`{}` now tracking on `#{}`. {}**\n".format(
                        username, channel.name, self._display_player_track_options(player_options))
            await asyncio.sleep(self.SLEEP_TIME)
            counter += 1

        if len(msg) > 500:
            await ctx.send("**Added `{}` users to tracking on `#{}`. {}**".format(
                count_add, channel.name, self._display_player_track_options(player_options)))
        else:
            await ctx.send(msg)


    async def _clean_track_db_user(self, db_user, api='bancho'):
        return db_user # !!!!!!!!!!!!!!!!!!!!

        # already fixed
        if 'api' in db_user:
            return db_user

        db_user['api'] = api
        stale_fields = ['recent', 'map_rank_achievements', 'map_updates', 'user_updates']
        stale_options = ['recent_gamemodes', 'recent_pass', 'map_rank_achievements', 'user_updates', 'map_updates']
        for server_id in db_user['servers']:
            for field in stale_fields:
                try:
                    del db_user['servers'][server_id][field]
                except:
                    pass

            for field in stale_options:
                try:
                    del db_user['servers'][server_id]['options'][field]
                except:
                    pass

        # get rid of the plays field
        try:
            del db_user['plays']
        except:
            pass

        await self.track.replace_one({"osu_id": db_user['osu_id']}, db_user)
        return db_user


    async def _get_server_track_num(self, server, new_country_settings=None):
        """Reads database to see how many people are tracked on this server"""
        
        query = {"servers.{}".format(server.id): {"$exists": True}}
        counter = 0
        async for db_track in self.track.find(query):
            counter += 1

        # so we can test how many users in hypothetical track
        db_country_settings = await self.track_country.find_one(
            {"server_id": str(server.id)})

        if not db_country_settings:
            db_country_settings = {}

        if new_country_settings:
            db_country_settings.update(new_country_settings)

        # print(country_settings)
        # combine channels since don't count different modes
        if db_country_settings:
            overall_list = {}
            for channel_id in db_country_settings['channels']:
                for country in db_country_settings['channels'][channel_id]:
                    if country not in overall_list:
                        overall_list[country] = 0

                    num_tracked = \
                        int(db_country_settings['channels'][channel_id][country]['num_players'])
        
                    if num_tracked > overall_list[country]:
                        overall_list[country] = num_tracked

            for country in overall_list:
                counter += overall_list[country]

        return counter


    def _display_player_track_options(self, options):
        msg = ""
        gamemodes_str = [str(mode) for mode in options['gamemodes']]
        min_pp_str = ''
        if 'pp_min' in options and options['pp_min'] != 0:
            min_pp_str = ' min:`{}`'.format(options['pp_min'])
        msg += "(m:`{}`, t:`{}`{})".format(
            ','.join(gamemodes_str), str(options['plays']), min_pp_str)
        return msg

    def _display_country_track_options(self, options):
        msg = ""
        gamemodes_str = [str(mode) for mode in options['modes']]
        min_pp_str = ''
        if 'pp_min' in options and options['pp_min'] != 0:
            min_pp_str = ' min:`{}`'.format(options['pp_min'])
        msg += "(p:`{}`, m:`{}`,t:`{}`{})".format(
            str(options['num_players']), ','.join(gamemodes_str),
            str(options['plays']), min_pp_str)
        return msg


    @commands.cooldown(1, 5, commands.BucketType.guild)
    @checks.mod_or_permissions(manage_guild = True)
    @osutrack.command(name="remove", no_pm=True)
    async def track_remove(self, ctx, *usernames):
        """
        Removes a player/country to track for top scores.

        [Options]
        Usernames: People you wish to remove from the current channel for tracking.
        All (-a): Remove all people in the server from tracking. (no param)
        Country (-c): Removes tracking for a country in the current channel. (str)
        Channel (-ch): Remove all people from the current channel from tracking. (no param)

        [Example]
        +osutrack <COMMAND> <USER>
        """
        server = ctx.message.guild
        channel = ctx.message.channel
        msg = ""
        count_remove = 0

        if usernames == ():
            await ctx.send("Please enter a user")
            return

        options, server_options = self.server_option_parser(usernames)
        api = self.determine_api(server_options)
        option_parser = OptionParser()
        option_parser.add_option('a',   'all',      opt_type=None,  default=None)
        option_parser.add_option('c',   'country',  opt_type=str,   default=None)
        option_parser.add_option('ch',  'channel',  opt_type=str,   default=None)
        usernames, options = option_parser.parse(options)

        # check if clear all users + countries
        if options['all']:
            await self._track_clear_server(ctx)
            return

        if options['channel']:
            await self._track_clear_channel(ctx)
            return

        if options['country']:
            await self._track_remove_country(ctx, options['country'])
            return

        for username in usernames:
            user_find = await self.track.find_one({"username":username})
            if not user_find:
                # try to use the cache first
                cache_info = await self.owoAPI.cache.user.entries.find_one(
                    {"data.username": username, "api": api})

                if cache_info:
                    osu_userinfo = cache_info['data']
                else: # try the cache
                    osu_userinfo = await self.owoAPI.get_user(username, mode=0)
                    osu_userinfo = osu_userinfo[0]
                    await asyncio.sleep(.1)

                user_find = await self.track.find_one({"osu_id": osu_userinfo['user_id']})

            if user_find and "servers" in user_find and str(server.id) in user_find["servers"]:
                del user_find["servers"][str(server.id)]
                await self.track.update_one({"username":username}, {"$set":{"servers":user_find["servers"]}})
                msg += "**No longer tracking `{}` in the server.**\n".format(username)
                count_remove += 1
            else:
                msg += "**`{}` is not currently being tracked.**\n".format(username)
            user_find = await self.track.find_one({"username":username})

        if len(msg) > 500:
            await ctx.send("**Removed `{}` users from tracking on `#{}`.**".format(count_remove, channel.name))
        else:
            await ctx.send(msg)


    async def _track_clear_server(self, ctx):
        server = ctx.message.guild
        user = ctx.message.author
        def check_event(m):
            return m.author == ctx.author

        await ctx.send('**You are about to clear users tracked on this server. Confirm by typing `yes`.**')
        try:
            answer = await self.bot.wait_for('message', check=check_event, timeout=15)
        except asyncio.TimeoutError:
            answer = None

        if answer is None:
            return await ctx.send('**Clear canceled.**')
        elif "yes" not in answer.content.lower():
            return await ctx.send('**No action taken.**')
        
        # clear players
        player_query = {
            "servers.{}".format(str(server.id)): {"$exists": True}
        }
        async for username in self.track.find(player_query):
            servers = username['servers']
            del servers[str(server.id)]
            await self.track.update_one(
                {'username':username['username']},
                {'$set': {'servers':servers}})

        # clear countries
        country_query = {"server_id": str(server.id)}
        await self.track_country.delete_one(country_query)
        await ctx.send('**Users and countries tracked on `{}` cleared.**'.format(server.name))


    async def _track_clear_channel(self, ctx):
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author
        def check_event(m):
            return m.author == ctx.author

        await ctx.send('**You are about to clear users tracked on this channel. Confirm by typing `yes`.**')
        try:
            answer = await self.bot.wait_for('message', check=check_event, timeout=15)
        except asyncio.TimeoutError:
            answer = None

        if answer is None:
            return await ctx.send('**Clear canceled.**')
        elif "yes" not in answer.content.lower():
            return await ctx.send('**No action taken.**')
        
        # clear players
        player_query = {
            "servers.{}".format(str(server.id)): {"$exists": True}
        }
        async for username in self.track.find(player_query):
            server_settings = username['servers'][str(server.id)]
            new_server_settings = copy.deepcopy(server_settings)

            for mode in server_settings['top']:
                if server_settings['top'][mode]['channel_id'] == str(channel.id):
                    del new_server_settings['top'][mode]

            await self.track.update_one(
                {'username':username['username']},
                {'$set': {'servers.{}'.format(str(server.id)):new_server_settings}})

        # clear countries
        country_query = {"server_id": str(server.id)}
        country_channel_settings = await self.track_country.find_one(country_query)
        if country_channel_settings:
            if str(channel.id) in country_channel_settings['channels']:
                del country_channel_settings['channels'][str(channel.id)]

            await self.track_country.update_one(country_query, 
                {'$set': {'channels': country_channel_settings['channels']}})
        await ctx.send('**Users and countries tracked in `#{}` cleared.**'.format(channel.name))


    async def _track_remove_country(self, ctx, country_name):
        server = ctx.message.guild
        channel = ctx.message.channel
        user = ctx.message.author

        # clean country name
        country_rm_abbr = countries.get(country_name).alpha2.upper()
        country_rm_name = countries.get(country_name).name

        if not country_rm_abbr:
            return await ctx.send(
                '**Country `{}` was not found.**'.format(country_name))            

        # clear countries
        country_query = {"server_id": str(server.id)}
        country_channel_settings = await self.track_country.find_one(country_query)

        channel_set_copy = copy.deepcopy(country_channel_settings['channels'])

        # print('CCS COPY', ccs_copy)
        # print('CHANNEL ID', channel.id)

        country_deleted = False
        for channel_id in country_channel_settings['channels']:
            print('CID COMP', channel_id, channel.id)
            if str(channel_id) == str(channel.id):
                for country in country_channel_settings['channels'][channel_id]:
                    if country == country_rm_abbr:
                        del channel_set_copy[channel_id][country]
                        country_deleted = True

        # print(channel_set_copy)
        if country_deleted:
            await self.track_country.update_one(country_query, 
                {'$set': {'channels': channel_set_copy}})
            await ctx.send('**Players from `{}` tracked in `#{}` removed.**'.format(
                country_rm_name, channel.name))
        else:
            await ctx.send('**Players from `{}` are not currently being tracked in `#{}`**'.format(
                country_rm_name, channel.name))




def setup(bot):
    osu = Osu(bot)

    if bot.is_passive_bot:
        bot.add_listener(osu.find_link, "on_message")
        # bot.add_listener(osu.update_user_servers_leave, "on_member_remove")
        # bot.add_listener(osu.update_user_servers_join, "on_member_join")
    else:
        bot.add_cog(osu)
