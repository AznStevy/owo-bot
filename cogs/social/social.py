import os
import re
import copy
import json
import time
import math
import redis
import random
import string
import asyncio
import aiohttp
import operator
import textwrap
import datetime
import platform
from threading import Thread

import discord
from discord.utils import find
from discord.ext import commands
from utils import checks
from utils.dataIO import fileIO
from utils.chat_formatting import pagify
from utils.option_parser import OptionParser

import motor.motor_asyncio

import numpy as np
import scipy
import scipy.misc
import scipy.cluster
# from scipy import cluster

from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps, ImageFilter, ImageSequence

font_thin_file = 'cogs/social/fonts/Uni_Sans_Thin.ttf'
font_heavy_file = 'cogs/social/fonts/Uni_Sans_Heavy.ttf'
font_file = 'cogs/social/fonts/SourceSansPro-Regular.ttf'
font_bold_file = 'cogs/social/fonts/SourceSansPro-Semibold.ttf'
font_cjk_file = 'cogs/social/fonts/YasashisaAntique.ttf'
font_unicode_file = 'cogs/social/fonts/unicode.ttf'

default_avatar_url = "http://i.imgur.com/XPDO9VH.jpg"
default_profile_bg_url = "http://i.imgur.com/8T1FUP5.jpg"
default_rank_bg_url = "http://i.imgur.com/SorwIrc.jpg"

class Social(commands.Cog):
    """A level up thing with image generation!"""

    def __init__(self, bot):
        self.bot = bot

        # contains the server settings database for bot
        self.server_settings = self.bot.db["social"]
        client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = client['{}_social'.format(self.bot.config['bot_name'])]

        # leveler db stuff
        self.all_users = self.bot.db["users"] # users collection of bot
        # the servers aspect of the leveler database, like role links and badges
        self.servers = self.db["servers"] # anything to do with a server and leveler
        self.backgrounds = fileIO("cogs/social/backgrounds/backgrounds.json", "load")

        # cache the exp table
        self.exp_table = [65]
        self._total_required_exp(100)

        # speaking user cache
        self.server_msg_cooldown = {}
        self.user_msg_cooldown = {}

        # constants
        self.LB_MAX = 15
        self.USER_EXP_COOLDOWN = 120 # seconds
        self.SERVER_EXP_COOLDOWN = 2 # seconds


    async def _get_server_settings(self, server_id):
        return await self.server_settings.find_one({"server_id":server_id})

    def _has_property(self, info, prop:str):
        if info and prop in info:
            return True
        return False


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(name = "profile", no_pm=True)
    async def profile(self, ctx, *, user : discord.Member=None):
        """Displays a user profile.

        [Options]
        user: Server member. You, if none.

        [Example]
        +<COMMAND> Stevy
        """
        if user == None:
            user = ctx.message.author
        channel = ctx.message.channel
        server = ctx.message.guild
        start_time = datetime.datetime.now()

        # get server settings
        server_settings = await self._get_server_settings(str(server.id))

        # creates user if doesn't exist
        userinfo = await self.get_user(user)
        end_time = datetime.datetime.now()
        #print('Request time: ', (end_time-start_time).total_seconds())

        # no cooldown for text only
        if self._has_property(server_settings, "text_only") and server_settings["text_only"]:
            em = await self.profile_text(user, server, userinfo)
            await channel.send(embed = em)
        else:
            async with channel.typing():
                start_time = datetime.datetime.now()
                filepath = await self.draw_profile(ctx, user)
                end_time = datetime.datetime.now()
                #print('Draw time: ', (end_time-start_time).total_seconds())
                file = discord.File(filepath)
                try:
                    await ctx.send(file=file,
                        content='**User profile for {}**'.format(self._is_mention(user)))
                except:
                    await ctx.send(":red_circle: **No permissions**", delete_after=5)

    async def profile_text(self, user, server, userinfo):
        def test_empty(text):
            if text == '':
                return "None"
            else:
                return text

        em = discord.Embed(description='', colour=user.colour)
        em.add_field(name="Title:", value = test_empty(userinfo["title"]))
        em.add_field(name="Reps:", value= userinfo["rep"])
        em.add_field(name="Global Rank:", value = '#{}'.format(await self._find_global_rank(user, userinfo)))
        em.add_field(name="Server Rank:", value = '#{}'.format(await self._find_server_rank(user, server)))
        em.add_field(name="Server Level:", value = format(userinfo["servers"][str(server.id)]["level"]))
        em.add_field(name="Total Exp:", value = userinfo["total_exp"])
        em.add_field(name="Server Exp:", value = await self._find_server_exp(user, server))
        em.add_field(name="Info: ", value = test_empty(userinfo["info"]))
        em.add_field(name="Badges: ", value = test_empty(", ".join(userinfo["badges"])).replace("_", " "))
        em.set_author(name="Profile for {}".format(user.name), url = user.avatar_url_as(static_format='png'))
        em.set_thumbnail(url=user.avatar_url_as(static_format='png'))
        return em

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def rank(self,ctx,user : discord.Member=None):
        """Displays rank of a user.

        [Options]
        user: Server member. You, if none.

        [Example]
        +<COMMAND> Stevy
        """
        if user == None:
            user = ctx.message.author
        channel = ctx.message.channel
        server = ctx.message.guild
        curr_time = time.time()

        server_settings = await self._get_server_settings(str(server.id))

        # creates user if doesn't exist
        userinfo = await self.get_user(user)

        # check if server is in info, if not initialize it
        if str(server.id) not in userinfo['servers']:
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                "servers.{}.level".format(str(server.id)): 0,
                "servers.{}.current_exp".format(str(server.id)): 0,
                }})

        # no cooldown for text only
        if self._has_property(server_settings, "text_only") and server_settings["text_only"]:
            em = await self.rank_text(user, server, userinfo)
            await ctx.send('', embed = em)
        else:
            async with channel.typing():
                filepath = await self.draw_rank(ctx, user)
                file = discord.File(filepath)
                try:
                    await ctx.send(file = file,
                        content='**Ranking & Statistics for {}**'.format(self._is_mention(user)))
                except:
                    await ctx.send(":red_circle: **No permissions**", delete_after=5)


    async def rank_text(self, user, server, userinfo):
        em = discord.Embed(description='', colour=user.colour)
        em.add_field(name="Server Rank", value = '#{}'.format(await self._find_server_rank(user, server)))
        em.add_field(name="Reps", value = userinfo["rep"])
        em.add_field(name="Server Level", value = userinfo["servers"][str(server.id)]["level"])
        em.add_field(name="Server Exp", value = await self._find_server_exp(user, server))
        em.set_author(name="Rank and Statistics for {}".format(user.name), url = user.avatar_url)
        em.set_thumbnail(url=user.avatar_url)
        return em

    # should the user be mentioned based on settings?
    def _is_mention(self,user):
        return user.name
        """
        if "mention" not in self.settings.keys() or self.settings["mention"]:
            return user.mention
        else:
            return user.name"""

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True, aliases=['st', 'soctop'])
    async def socialtop(self, ctx, *inputs):
        """Displays a leaderboard for exp or reps.

        [Options]
        Global (-global): Global Leaderboard. Exp by default. (no param)
        Rep (-rep): Rep leaderboard. (no param)
        Page (-p): The page you wish to view. (int)

        [Example]
        +<COMMAND> -global
        """

        # options parser
        option_parser = OptionParser()
        option_parser.add_option('global',  'global',   opt_type=None,   default=False)
        option_parser.add_option('rep',     'rep',      opt_type=None,   default=False)
        option_parser.add_option('p',       'page',     opt_type=int,    default=1)
        _, options = option_parser.parse(inputs)

        server = ctx.message.guild
        user = ctx.message.author
        userinfo = await self.get_user(user)

        skip_num = self.LB_MAX * (int(options['page'])-1)

        users = []
        board_type = ''
        user_stat = None
        att_rank = None
        if options['rep'] and options['global']:
            title = "Global Rep Leaderboard for {}\n".format(self.bot.user.name)

            user_rank = await self._find_global_rep_rank(user, userinfo)
            sort_criteria = [("rep", -1)]

            relevant_users = []
            async for entry in self.all_users.find({}).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):
                relevant_users.append(entry)

            for info in relevant_users:
                try:
                    users.append((info["username"], info["rep"]))
                except:
                    users.append((info["user_id"], info["rep"]))

            board_type = 'Rep'
            icon_url = str(self.bot.user.avatar_url_as(static_format='png'))
        elif options['global']:
            title = "Global Exp Leaderboard for {}\n".format(self.bot.user.name)

            user_rank = await self._find_global_rank(user, userinfo)
            sort_criteria = [("total_exp", -1)]

            relevant_users = []
            async for entry in self.all_users.find({}).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):
                relevant_users.append(entry)

            for info in relevant_users:
                try:
                    users.append((info["username"], info["total_exp"]))
                except:
                    users.append((info["user_id"], info["total_exp"]))

            board_type = 'Exp'
            icon_url = str(self.bot.user.avatar_url_as(static_format='png'))
        elif options['rep']:
            title = "Rep Leaderboard for {}\n".format(server.name)
            query = {"servers.{}".format(server.id): {"$exists": True}}

            user_rank = await self._find_server_rep_rank(user, server)
            sort_criteria = [("rep", -1)]

            relevant_users = []
            async for entry in self.all_users.find(query).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):
                relevant_users.append(entry)

            for info in relevant_users:
                try:
                    users.append((info["username"], info["rep"]))
                except:
                    users.append((info["user_id"], info["rep"]))

            board_type = 'Rep'
            footer_text = "Your Rank: {}         {}: {}".format(
                att_rank, board_type, user_stat)
            icon_url = server.icon_url
        else:
            title = "Exp Leaderboard for {}\n".format(server.name)
            query = {"servers.{}".format(server.id): {"$exists": True}}

            sort_criteria = [
                ("servers.{}.level".format(server.id), -1),
                ("servers.{}.current_exp".format(server.id), -1)]
            user_rank = await self._find_server_exp_rank(user, userinfo, server)
            user_stat = self._total_required_exp(
                userinfo['servers'][str(server.id)]['level']) + \
                userinfo['servers'][str(server.id)]['current_exp']

            relevant_users = []
            async for info in self.all_users.find(query).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):

                user_server_info = info["servers"][str(server.id)]
                level = user_server_info["level"]
                current_exp = user_server_info["current_exp"]
                relevant_users.append((info, level, current_exp))

            for info, level, c_exp in relevant_users:
                exp = self._total_required_exp(level) + c_exp
                try:
                    users.append((info["username"], exp))
                except:
                    users.append((info["user_id"], exp))

            board_type = 'Points'
            icon_url = server.icon_url

        # drawing leaderboard
        sorted_list = users
        msg = ""
        start_index = self.LB_MAX*(int(options['page'])-1)

        default_label = "  "
        special_labels = ["♔", "♕", "♖", "♗", "♘", "♙"]

        for rank_idx, single_user in enumerate(sorted_list):
            current_rank = start_index+rank_idx+1
            # print(current_rank)
            if current_rank-1 < len(special_labels):
                label = special_labels[current_rank-1]
            else:
                label = default_label

            msg += u'`{:<2}{:<2}{:<40}'.format(
                current_rank, label, 
                self._truncate_text(single_user[0],30))
            msg += u'{:<12}`\n'.format(
                "{}: ".format(board_type) + str(single_user[1]))

        em = discord.Embed(description='', colour=user.colour)
        em.set_author(name=title, icon_url = icon_url)
        em.description = msg
        em.set_footer(text="Your Rank: {} | {}: {}".format(
            att_rank , board_type, user_stat))

        await ctx.send(embed = em)


    @commands.command(no_pm=True)
    async def rep(self, ctx, user : discord.Member = None):
        """Gives a reputation point to a designated player.

        [Options]
        user: A server member.

        [Example]
        +<COMMAND> Stevy
        """
        channel = ctx.message.channel
        org_user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        org_userinfo = await self.get_user(org_user)
        curr_time = time.time()

        if user and str(user.id) == str(org_user.id):
            await ctx.send(":red_circle: **You can't give a rep to yourself!**")
            return
        if user and user.bot:
            await ctx.send(":red_circle: **You can't give a rep to a bot!**")
            return
        if "rep_block" not in org_userinfo:
            org_userinfo["rep_block"] = 0

        delta = float(curr_time) - float(org_userinfo["rep_block"])
        if user and delta >= 43200.0 and delta>0:
            userinfo = await self.get_user(user)
            await self.all_users.update_one({'user_id':str(org_user.id)}, {'$set':{
                    "rep_block": curr_time,
                }})
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                    "rep":  userinfo["rep"] + 1,
                }})
            await ctx.send(":heart_decoration: **You have just given {} a reputation point!**".format(self._is_mention(user)))
        else:
            # calulate time left
            seconds = 43200 - delta
            if seconds < 0:
                await ctx.send(":white_check_mark: **You can give a rep!**")
                return

            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            await ctx.send(":red_circle: **You need to wait {} hours, {} minutes, and {} seconds until you can give reputation again!**".format(
                int(h), int(m), int(s)), delete_after=5)

    @commands.command(no_pm=True)
    async def lvlinfo(self, ctx, user : discord.Member = None):
        """Gives more specific details about a user's exp/profile data.

        [Options]
        user: A server member.

        [Example]
        +<COMMAND> Stevy
        """
        if not user:
            user = ctx.message.author
        server = ctx.message.guild
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})
        server = ctx.message.guild

        em = discord.Embed(colour=user.colour)
        # creates user if doesn't exist
        await self._create_user(user, server)
        msg = ""
        msg += "Name: `{}`\n".format(user.name)
        msg += "Title: `{}`\n".format(userinfo["title"])
        msg += "Reps: `{}`\n".format(userinfo["rep"])
        msg += "Server Level: `{}`\n".format(userinfo["servers"][str(server.id)]["level"])
        total_server_exp = 0
        total_server_exp = self._total_required_exp(userinfo["servers"][str(server.id)]["level"])
        total_server_exp += userinfo["servers"][str(server.id)]["current_exp"]
        msg += "Server Exp: `{}`\n".format(total_server_exp)
        msg += "Total Exp: `{}`\n".format(userinfo["total_exp"])
        msg += "Info: `{}`\n".format(userinfo["info"])
        em.add_field(name="General", value = msg)

        msg = ""
        msg += "Profile background: {}\n".format(userinfo["profile_background"])
        if "profile_info_color" in userinfo.keys() and userinfo["profile_info_color"]:
            msg += "Profile info color: `{}`\n".format(self._rgb_to_hex(userinfo["profile_info_color"]))
        if "profile_exp_color" in userinfo.keys() and userinfo["profile_exp_color"]:
            msg += "Profile exp color: `{}`\n".format(self._rgb_to_hex(userinfo["profile_exp_color"]))
        if "rep_color" in userinfo.keys() and userinfo["rep_color"]:
            msg += "Rep section color: `{}`\n".format(self._rgb_to_hex(userinfo["rep_color"]))
        if "badge_col_color" in userinfo.keys() and userinfo["badge_col_color"]:
            msg += "Badge section color: `{}`\n".format(self._rgb_to_hex(userinfo["badge_col_color"]))
        em.add_field(name="Profile", value = msg)

        msg = ""
        msg += "Rank background: {}\n".format(userinfo["rank_background"])
        if "rank_info_color" in userinfo.keys() and userinfo["rank_info_color"]:
            msg += "Rank info color: `{}`\n".format(self._rgb_to_hex(userinfo["rank_info_color"]))
        if "rank_exp_color" in userinfo.keys() and userinfo["rank_exp_color"]:
            msg += "Rank exp color: `{}`\n".format(self._rgb_to_hex(userinfo["rank_exp_color"]))
        em.add_field(name="Rank", value = msg)

        msg = ""
        msg += "Levelup background: {}\n".format(userinfo["levelup_background"])
        if "levelup_info_color" in userinfo.keys() and userinfo["levelup_info_color"]:
            msg += "Level info color: `{}`\n".format(self._rgb_to_hex(userinfo["levelup_info_color"]))
        em.add_field(name="Levelup", value = msg)

        msg = ""
        msg += "Badges: "
        try:
            badge_list = []
            for badge in userinfo["badges"]:
                bsplit = badge.split("_")
                name = bsplit[0]
                server_id = bsplit[1]
                if server_id != "global":
                    try:
                        server = self.bot.get_guild(int(server_id))
                        server_name = server.name
                    except:
                        server_name = "None"
                else:
                    server_name = server_id
                badge_list.append(f"{name} (`{server_name}`)")

            msg += ", ".join(badge_list)
        except:
            pass
        em.add_field(name="Badges", value = msg)

        em.set_author(name="Level Information for {}".format(user.name), icon_url = user.avatar_url_as(static_format='png'))
        # em.set_thumbnail(url = user.avatar_url_as(static_format='png'))
        await ctx.send(embed = em)

    def _rgb_to_hex(self, rgb):
        rgb = tuple(rgb[:3])
        return '#%02x%02x%02x' % rgb

    @commands.group(name = "lvlset")
    async def lvlset(self, ctx):
        """Profile Configuration Options"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @lvlset.group(name = "profile")
    async def profileset(self, ctx):
        """Options to change your profile image."""
        if ctx.invoked_subcommand is None or \
                isinstance(ctx.invoked_subcommand, commands.Group):
            await self.bot.send_cmd_help(ctx)
            return

    @lvlset.group(name = "rank")
    async def rankset(self, ctx):
        """Options to change your rank image."""
        if ctx.invoked_subcommand is None or \
                isinstance(ctx.invoked_subcommand, commands.Group):
            await self.bot.send_cmd_help(ctx)
            return

    @lvlset.group(name = "levelup")
    async def levelupset(self, ctx):
        """Options to change your level-up image."""
        if ctx.invoked_subcommand is None or \
                isinstance(ctx.invoked_subcommand, commands.Group):
            await self.bot.send_cmd_help(ctx)
            return

    @profileset.command(name = "color", no_pm=True)
    async def profilecolors(self, ctx, section:str, color:str):
        """Set your profile colors.

        [Options]
        section: exp, rep, badge, info, all
        color: default, white, hex (with #), auto (will calculate based on image)

        [Example]
        +<COMMAND> all auto
        """
        user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        section = section.lower()
        default_info_color = (30, 30 ,30, 200)
        white_info_color = (150, 150, 150, 180)
        default_rep = (92,130,203,230)
        default_badge = (128,151,165,230)
        default_exp = (255, 255, 255, 230)
        default_a = 200

        # get correct section for db query
        if section == "rep":
            section_name = "rep_color"
        elif section == "exp":
            section_name = "profile_exp_color"
        elif section == "badge":
            section_name = "badge_col_color"
        elif section == "info":
            section_name = "profile_info_color"
        elif section == "all":
            section_name = "all"
        else:
            await ctx.send("**Not a valid section. (rep, exp, badge, info, all)**")
            return

        # get correct color choice
        if color == "auto":
            if section == "exp":
                color_ranks = [random.randint(2,3)]
            elif section == "rep":
                color_ranks = [random.randint(2,3)]
            elif section == "badge":
                color_ranks = [0] # most prominent color
            elif section == "info":
                color_ranks = [random.randint(0,1)]
            elif section == "all":
                color_ranks = [random.randint(2,3), random.randint(2,3), 0, random.randint(0,2)]

            hex_colors = await self._auto_color(ctx, userinfo["profile_background"], color_ranks)
            set_color = []
            for hex_color in hex_colors:
                color_temp = self._hex_to_rgb(hex_color, default_a)
                set_color.append(color_temp)

        elif color == "white":
            set_color = [white_info_color]
        elif color == "default":
            if section == "exp":
                set_color = [default_exp]
            elif section == "rep":
                set_color = [default_rep]
            elif section == "badge":
                set_color = [default_badge]
            elif section == "info":
                set_color = [default_info_color]
            elif section == "all":
                set_color = [default_exp, default_rep, default_badge, default_info_color]
        elif self._is_hex(color):
            set_color = [self._hex_to_rgb(color, default_a)]
        else:
            await ctx.send("**Not a valid color. (default, hex, white, auto)**")
            return

        if section == "all":
            if len(set_color) == 1:
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "profile_exp_color": set_color[0],
                        "rep_color": set_color[0],
                        "badge_col_color": set_color[0],
                        "profile_info_color": set_color[0]
                    }})
            elif color == "default":
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "profile_exp_color": default_exp,
                        "rep_color": default_rep,
                        "badge_col_color": default_badge,
                        "profile_info_color": default_info_color
                    }})
            elif color == "auto":
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "profile_exp_color": set_color[0],
                        "rep_color": set_color[1],
                        "badge_col_color": set_color[2],
                        "profile_info_color": set_color[3]
                    }})
            await ctx.send("**Colors for profile set.**")
        else:
            # print("update one")
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                    section_name: set_color[0]
                }})
            await ctx.send("**Color for profile {} set.**".format(section))

    @rankset.command(name = "color", no_pm=True)
    async def rankcolors(self, ctx, section:str, color:str = None):
        """Set your rank image colors.

        [Options]
        section: exp, info, all
        color: default, white, hex (with #), auto (will calculate based on image)

        [Example]
        +<COMMAND> all auto
        """
        user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        section = section.lower()
        default_info_color = (30, 30 ,30, 200)
        white_info_color = (150, 150, 150, 180)
        default_exp = (255, 255, 255, 230)
        default_a = 200

        # get correct section for db query
        if section == "exp":
            section_name = "rank_exp_color"
        elif section == "info":
            section_name = "rank_info_color"
        elif section == "all":
            section_name = "all"
        else:
            await ctx.send("**Not a valid section. (exp, info, all)**")
            return

        # get correct color choice
        if color == "auto":
            if section == "exp":
                color_ranks = [random.randint(2,3)]
            elif section == "info":
                color_ranks = [random.randint(0,1)]
            elif section == "all":
                color_ranks = [random.randint(2,3), random.randint(0,1)]

            hex_colors = await self._auto_color(ctx, userinfo["rank_background"], color_ranks)
            set_color = []
            for hex_color in hex_colors:
                color_temp = self._hex_to_rgb(hex_color, default_a)
                set_color.append(color_temp)
        elif color == "white":
            set_color = [white_info_color]
        elif color == "default":
            if section == "exp":
                set_color = [default_exp]
            elif section == "info":
                set_color = [default_info_color]
            elif section == "all":
                set_color = [default_exp, default_rep, default_badge, default_info_color]
        elif self._is_hex(color):
            set_color = [self._hex_to_rgb(color, default_a)]
        else:
            await ctx.send("**Not a valid color. (default, hex, white, auto)**")
            return

        if section == "all":
            if len(set_color) == 1:
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "rank_exp_color": set_color[0],
                        "rank_info_color": set_color[0]
                    }})
            elif color == "default":
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "rank_exp_color": default_exp,
                        "rank_info_color": default_info_color
                    }})
            elif color == "auto":
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "rank_exp_color": set_color[0],
                        "rank_info_color": set_color[1]
                    }})
            await ctx.send("**Colors for rank set.**")
        else:
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                    section_name: set_color[0]
                }})
            await ctx.send("**Color for rank {} set.**".format(section))

    @levelupset.command(name = "color", no_pm=True)
    async def levelupcolors(self, ctx, section:str, color:str = None):
        """Set your level-up image colors.

        [Options]
        section: info, all
        color: default, white, hex (with #), auto (will calculate based on image)

        [Example]
        +<COMMAND> all auto
        """
        user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        section = section.lower()
        default_info_color = (30, 30 ,30, 200)
        white_info_color = (150, 150, 150, 180)
        default_a = 200

        # get correct section for db query
        if section == "info":
            section_name = "levelup_info_color"
        else:
            await ctx.send("**Not a valid section. (info)**")
            return

        # get correct color choice
        if color == "auto":
            if section == "info":
                color_ranks = [random.randint(0,1)]
            hex_colors = await self._auto_color(ctx, userinfo["levelup_background"], color_ranks)
            set_color = []
            for hex_color in hex_colors:
                color_temp = self._hex_to_rgb(hex_color, default_a)
                set_color.append(color_temp)
        elif color == "white":
            set_color = [white_info_color]
        elif color == "default":
            if section == "info":
                set_color = [default_info_color]
        elif self._is_hex(color):
            set_color = [self._hex_to_rgb(color, default_a)]
        else:
            await ctx.send("**Not a valid color. (default, hex, white, auto)**")
            return

        await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                section_name: set_color[0]
            }})
        await ctx.send("**Color for level-up {} set.**".format(section))

    # uses k-means algorithm to find color from bg, rank is abundance of color, descending
    async def _auto_color(self, ctx, url:str, ranks):
        phrases = ["Calculating colors..."] # in case I want more
        #try:
        await ctx.send("**{}**".format(random.choice(phrases)))
        clusters = 10

        temp_path = 'cogs/social/temp/temp_auto_{}.png'.format(random.randint(0,5))
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                image = await r.content.read()
            with open(temp_path,'wb') as f:
                f.write(image)

        im = Image.open(temp_path).convert('RGBA')
        im = im.resize((290, 290)) # resized to reduce time
        ar = im # scipy.misc.fromimage(im)
        shape = ar.shape
        ar = ar.reshape(scipy.product(shape[:2]), shape[2])

        codes, dist = scipy.cluster.vq.kmeans(ar.astype(float), clusters)
        vecs, dist = scipy.cluster.vq.vq(ar, codes)         # assign codes
        counts, bins = scipy.histogram(vecs, len(codes))    # count occurrences

        # sort counts
        freq_index = []
        index = 0
        for count in counts:
            freq_index.append((index, count))
            index += 1
        sorted_list = sorted(freq_index, key=operator.itemgetter(1), reverse=True)

        colors = []
        for rank in ranks:
            color_index = min(rank, len(codes))
            peak = codes[sorted_list[color_index][0]] # gets the original index
            peak = peak.astype(int)

            colors.append(''.join(format(c, '02x') for c in peak))
        return colors # returns array
        #except:
            #await ctx.send("```Error or no scipy. Install scipy doing 'pip3 install numpy' and 'pip3 install scipy' or read here: https://github.com/AznStevy/Maybe-Useful-Cogs/blob/master/README.md```")

    # converts hex to rgb
    def _hex_to_rgb(self, hex_num: str, a:int):
        h = hex_num.lstrip('#')

        # if only 3 characters are given
        if len(str(h)) == 3:
            expand = ''.join([x*2 for x in str(h)])
            h = expand

        colors = [int(h[i:i+2], 16) for i in (0, 2 ,4)]
        colors.append(a)
        return tuple(colors)

    # dampens the color given a parameter
    def _moderate_color(self, rgb, a, moderate_num):
        new_colors = []
        for color in rgb[:3]:
            if color > 128:
                color -= moderate_num
            else:
                color += moderate_num
            new_colors.append(color)
        new_colors.append(230)

        return tuple(new_colors)


    @profileset.command(no_pm=True)
    async def info(self, ctx, *, info):
        """Set your info section.

        [Options]
        info: Some (edgy) descrption of yourself, because discord.

        [Example]
        +<COMMAND> "I'm the coolest cat in the whole world!"
        """
        user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})
        max_char = 150

        if len(info) < max_char:
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{"info": info}})
            await ctx.send("**Your info section has been succesfully set!**")
        else:
            await ctx.send("**Your description has too many characters! Must be <{}**".format(max_char))

    @levelupset.command(name = "bg", no_pm=True)
    async def levelbg(self, ctx, *, image_name:str):
        """Set your level background.

        [Options]
        image_name: Name of image. No quotes needed.

        [Example]
        +<COMMAND> abstract cubes
        """
        await self._set_background(ctx, "levelup", image_name)

    @profileset.command(name = "bg", no_pm=True)
    async def profilebg(self, ctx, *, image_name:str):
        """Set your profile background.

        [Options]
        image_name: Name of image. No quotes needed.

        [Example]
        +<COMMAND> greenery
        """
        await self._set_background(ctx, "profile", image_name)

    async def _set_background(self, ctx, bg_type:str, image_name:str):
        user = ctx.message.author
        server = ctx.message.guild
        userinfo = await self.get_user(user)
        user_backgrounds = userinfo["inventory"]["backgrounds"][bg_type]

        if image_name not in user_backgrounds:
            await ctx.send(":red_circle: You currently don't have that background. Available: `{}`".format(
                ', '.join(user_backgrounds)))
            return

        bg_url = None
        for bg_name in self.backgrounds[bg_type].keys():
            if image_name == bg_name:
                bg_url = self.backgrounds[bg_type][bg_name]["url"]

        # if it's a special background
        if not bg_url:
            bg_url = image_name

        await self.all_users.update_one({'user_id':str(user.id)}, {
            '$set':{
                "{}_background".format(bg_type): bg_url
            }})
        await ctx.send(f":white_check_mark: **Your new {bg_type} background has been succesfully set!**")
        # await ctx.send(f"<{bg_url}>")

    @rankset.command(name = "bg", no_pm=True)
    async def rankbg(self, ctx, *, image_name:str):
        """Set your rank background.

        [Options]
        image_name: Name of image. No quotes needed.

        [Example]
        +<COMMAND> abstract cubes
        """
        await self._set_background(ctx, "rank", image_name)

    @profileset.command(no_pm=True)
    async def title(self, ctx, *, title):
        """Set your title.

        [Options]
        title: Some title. <20 characters.

        [Example]
        +<COMMAND> Cookielord
        """
        user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})
        max_char = 20

        if len(title) < max_char:
            userinfo["title"] = title
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{"title": title}})
            await ctx.send("**Your title has been succesfully set!**")
        else:
            await ctx.send("**Your title has too many characters! Must be <{}**".format(max_char))

    async def _process_purchase(self, ctx):
        user = ctx.message.author
        server = ctx.message.guild

        try:
            bank = self.bot.get_cog('Economy').bank
            if bank.account_exists(user) and self.settings["bg_price"] != 0:
                if not bank.can_spend(user, self.settings["bg_price"]):
                    await ctx.send("**Insufficient funds. Backgrounds changes cost: ${}**".format(self.settings["bg_price"]))
                    return False
                else:
                    await ctx.send('**{}, you are about to buy a background for `{}`. Confirm by typing `yes`.**'.format(self._is_mention(user), self.settings["bg_price"]))
                    answer = await self.bot.wait_for_message(timeout=15, author=user)
                    if answer is None:
                        await ctx.send('**Purchase canceled.**')
                        return False
                    elif "yes" not in answer.content.lower():
                        await ctx.send('**Background not purchased.**')
                        return False
                    else:
                        new_balance = bank.get_balance(user) - self.settings["bg_price"]
                        bank.set_credits(user, new_balance)
                        return True
            else:
                if self.settings["bg_price"] == 0:
                    return True
                else:
                    await ctx.send("**You don't have an account. Do {}bank register**".format(prefix))
                    return False
        except:
            if self.settings["bg_price"] == 0:
                return True
            else:
                await ctx.send("**There was an error with economy cog. Fix to allow purchases or set price to $0. Currently ${}**".format(prefix, self.settings["bg_price"]))
                return False

    async def _give_chat_credit(self, user, server):
        try:
            bank = self.bot.get_cog('Economy').bank
            if bank.account_exists(user) and "msg_credits" in self.settings:
                bank.deposit_credits(user, self.settings["msg_credits"][str(server.id)])
        except:
            pass

    async def _valid_image_url(self, url):
        pic_id = random.randint(0,5)
        max_byte = 1000
        test_path = f'cogs/social/temp/badge_test_{pic_id}.png'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    image = await r.content.read()
                with open(test_path,'wb') as f:
                    f.write(image)
                image = Image.open(test_path).convert('RGBA')
                os.remove(test_path)
            return True
        except:
            return False

    @commands.group(pass_context=True)
    async def badge(self, ctx):
        """Do fancy things with badges."""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @badge.command(name="available", no_pm=True)
    async def available(self, ctx):
        """Get a list of available badges for server.

        [Options]
        global_badge: -global

        [Example]
        +<COMMAND> global
        """
        user = ctx.message.author
        server = ctx.message.guild

        global_info = await self.get_server("global")
        server_info = await self.get_server(server)
        user_info = await self.get_user(user)

        global_badges = global_info["badges"]
        server_badges = server_info["badges"]
        user_badges = user_info["inventory"]["badges"]

        title_text = "Available Badges"
        em = discord.Embed(description='', colour=user.colour)
        em.set_author(name=title_text, icon_url=str(self.bot.user.avatar_url_as(static_format='png')))
        badges = []
        for badge_name in global_badges.keys():
            badge = global_badges[badge_name]
            badges.append("[{}]({}) ({})".format(
                badge["badge_name"], badge["bg_img"], self._get_badge_price(badge["price"])))
        em.add_field(name="Global", value=", ".join(self._get_badge_list(badges)))

        badges = []
        for badge_name in server_badges.keys():
            badge = server_badges[badge_name]
            badges.append("[{}]({}) ({})".format(
                badge["badge_name"], badge["bg_img"], self._get_badge_price(badge["price"])))
        em.add_field(name=f"{server.name}", value=", ".join(self._get_badge_list(badges)))

        badges = []
        for badge_name in user_badges.keys():
            badge = user_badges[badge_name]
            equip_name = "{}_{}".format(badge["server_id"], badge["badge_name"])

            underline = ""
            if badge["server_id"] == "global":
                underline = "__"

            if equip_name in user_info["active_badges"].keys():
                badges.append("**[{}]({})** ({}{}{})".format(
                    badge["badge_name"], badge["bg_img"],
                    underline, badge["server_name"], underline))
            else:
                badges.append("[{}]({}) ({}{}{})".format(
                    badge["badge_name"], badge["bg_img"],
                    underline, badge["server_name"], underline))
        em.add_field(name=f"Your Badges", inline=False, value=", ".join(self._get_badge_list(badges)))
        await ctx.send(embed = em)

    def _get_badge_list(self, badges):
        if not badges:
            return ["None"]
        return badges

    def _get_badge_price(self, price):
        if price == -1:
            return "Unpurchaseable"
        elif price == 0:
            return "Free"
        else:
            return price

    @badge.command(name="buy", no_pm=True)
    async def buy_badge(self, ctx, name:str, global_badge:str = None):
        """Get a badge from repository.

        [Options]
        name: The name of the badge
        global_badge: -global

        [Example]
        +<COMMAND> owo -global
        """
        return
        user = ctx.message.author
        server = ctx.message.guild
        if global_badge == '-global' or global_badge == '-g':
            server_id = 'global'
            server = "global"
        else:
            server_id = str(server.id)

        user_info = await self.get_user(user)
        user_badges = user_info["inventory"]["badges"]
        server_info = await self.get_server(server)
        server_badges = server_info["badges"]

        # check if they have it already
        equip_name = "{}_{}".format(server_id, name)
        for badge_name in user_badges.keys():
            if equip_name == badge_name:
                user_badges[badge_name]["bg_img"] = server_badges[name]["bg_img"]
                user_badges[badge_name]["border_color"] = server_badges[name]["border_color"]
                user_badges[badge_name]["description"] = server_badges[name]["description"]
                """
                await self.all_users.update_one({'user_id':str(user.id)},
                    {'$set': {'inventory.badges': user_badges}})"""
                return await ctx.send(f":white_check_mark: **{name} badge updated.**")

        # give the user the new badge
        buy_badge = None
        for badge_name in server_badges.keys():
            badge = server_badges[badge_name]
            if badge["badge_name"] == name and badge["server_id"] == server_id:
                buy_badge = badge
                break
        if not buy_badge:
            return await ctx.send(":red_circle: **Sorry, that badge doesn't exist!**")

        # process purchase
        # owner can do anything
        is_owner = False
        if self.bot.config["owner"] == str(user.id):
            is_owner = True

        equip_name = "{}_{}".format(server_id, buy_badge["badge_name"])
        if buy_badge["price"] == -1 and not is_owner:
            return await ctx.send(":red_circle: **That badge can't be purchased!**")
        elif user_info["credits"] >= buy_badge["price"] or is_owner:
            if not is_owner:
                user_info["credits"] = int(user_info["credits"] - buy_badge["price"])
            user_badges[equip_name] = buy_badge
            await self.all_users.update_one({'user_id':str(user.id)},
                {'$set': {
                    'inventory.badges': user_badges,
                    "credits": user_info["credits"]
                }})
            # await ctx.send(user_badges)
            return await ctx.send(f":white_check_mark: **Successfully bought `{name}` badge!**")
        else:
            return await ctx.send(":red_circle: **You need `{}` more credits to purchase that badge!**".format(
                str(buy_badge["price"]-user_info["credits"])))

    @badge.command(name="equip", no_pm=True)
    async def equip_badge(self, ctx, name:str, priority_num:int, global_badge:str=None):
        """Put a badge onto your profile. You must equip in server to which the badge belongs.

        [Options]
        name: The name of the badge
        priority_num: 0(not on profile)-100; the higher, the more in front it is. -1 to remove from active list.

        [Example]
        +<COMMAND> owo 100
        """
        return
        user = ctx.message.author
        server = ctx.message.guild
        userinfo = await self.get_user(user)

        if priority_num < -1 or priority_num > 100:
            await ctx.send("**Invalid priority number! `-1-100`**")
            return

        if global_badge == '-global' or global_badge == '-g':
            server_id = 'global'
            server = "global"
        else:
            server_id = str(server.id)

        equip_name = f"{server_id}_{name}"
        if equip_name in userinfo["active_badges"].keys() and priority_num != -1:
            # edit the priority number
            userinfo["active_badges"][equip_name]["priority_num"] = priority_num
            await self.all_users.update_one({'user_id': str(user.id)},
                {'$set':{"active_badges": userinfo["active_badges"]}})
            return await ctx.send(f":white_check_mark: **`{name}` badge priority edited to `{priority_num}`.**")
        elif priority_num == -1:
            # remove the badge from the active list
            del userinfo["active_badges"][equip_name]
            await self.all_users.update_one({'user_id': str(user.id)},
                {'$set':{"active_badges": userinfo["active_badges"]}})
            return await ctx.send(f":white_check_mark: **`{name}` badge removed from active list.**")
        else:
            # regular equip the badge
            if equip_name in userinfo["inventory"]["badges"].keys() and \
                userinfo["inventory"]["badges"][equip_name]["server_id"] == server_id:
                equip_badge = userinfo["inventory"]["badges"][equip_name]
                userinfo["active_badges"][equip_name] = equip_badge
                userinfo["active_badges"][equip_name]["priority_num"] = priority_num
                await self.all_users.update_one({'user_id': str(user.id)},
                    {'$set':{"active_badges": userinfo["active_badges"]}})
                await ctx.send(f":white_check_mark: **`{name}` has been set active with priority `{priority_num}`**")
            else:
                await ctx.send(":red_circle: **That badge doesn't exist in this server!**")

    @commands.has_permissions(manage_roles=True)
    @badge.command(name="add", pass_context = True, no_pm=True)
    async def add_badge(self, ctx, name:str, bg_img:str, border_color:str, price:int, *description):
        """Add a badge for your server. Limit 25 per server (so think about adding wisely).

        [Options]
        name: The name of the badge
        bg_img: Must be a imgur url. Might expire if not.
        border_color: Color in hex
        price: Price of the badge. -1(non-purchasable), 0, ..., 1000

        [Example]
        +<COMMAND> Cookie https://i.imgur.com/4QEfDjd.png #FFF 500 "This is a cookie badge!"
        """
        return
        user = ctx.message.author
        server = ctx.message.guild
        server_name = server.name
        server_key = str(server.id)

        # check members
        badge_limit = 25
        required_members = 30
        members = 0
        for member in server.members:
            if not member.bot:
                members += 1
        if str(user.id) == self.bot.config["owner"]: # for testing
            pass
        elif members < required_members:
            await ctx.send(":red_circle: **You may only add badges in servers with {}+ non-bot members**".format(required_members))
            return

        option_parser = OptionParser()
        option_parser.add_option('g','global', opt_type=None, default=False)
        description, options = option_parser.parse(description[0].split(" "))

        if '.' in name:
            await ctx.send(":red_circle: **Name cannot contain `.` Please use an underscore or space (with quotes) instead.**")
            return
        if not await self._valid_image_url(bg_img):
            await ctx.send(":red_circle: **Background is not valid. Enter hex or image url!**")
            return
        if not self._is_hex(border_color):
            await ctx.send(":red_circle: **Border color is not valid!**")
            return
        if price < -1 or price > 1000:
            await ctx.send(":red_circle: **Price is not valid!**")
            return
        if len(description.split(" ")) > 40:
            return await ctx.send(":red_circle: **Description is too long! <=40**")

        is_owner = False
        if self.bot.config["owner"] == str(user.id):
            is_owner = True

        if options["global"] and not is_owner:
            return await ctx.send(":red_circle: **Only the owner can add global badges! You can suggest some in the owo! server.**")
        if options["global"]:
            server = "global"
            server_key = "global"
            server_name = "global"

        server_info = await self.get_server(server) # ensures correct structure
        new_badge = {
                "badge_name": name,
                "bg_img": bg_img,
                "price": price,
                "description": description,
                "border_color": border_color,
                "server_id": server_key,
                "server_name": server_name,
                "priority_num": 0
            }

        badges = server_info["badges"]
        if name not in badges.keys():
            if server_key != "global" and len(server_info["badges"].keys()) >= badge_limit:
                return await ctx.send(":red_circle: **You have reached the badge limit.**")
            # create the badge regardless
            badges[name] = new_badge
            await self.servers.update_one({'server_id':server_key}, {'$set': {
                'badges': badges
                }})
            await ctx.send(":white_check_mark: **`{}` badge added in `{}` server.**".format(name, server_name))
        else:
            # update badge in the server
            badges[name] = new_badge
            await self.servers.update_one({'server_id':server_key}, {'$set': {
                'badges': badges
                }})
            await ctx.send(":white_check_mark: **The `{}` badge has been updated**".format(name))

    def _is_hex(self, color:str):
        if color != None and len(color) != 4 and len(color) != 7:
            return False

        reg_ex = r'^#(?:[0-9a-fA-F]{3}){1,2}$'
        return re.search(reg_ex, str(color))

    @commands.has_permissions(manage_roles=True)
    @badge.command(name="delete", no_pm=True)
    async def del_badge(self, ctx, *, name:str):
        """Delete a badge. Users with badge will still have it.

        [Options]
        name: The name of the badge

        [Example]
        +<COMMAND> Cookie
        """
        return
        user = ctx.message.author
        channel = ctx.message.channel
        server = ctx.message.guild

        if '-global' in name and str(user.id) == self.owner:
            name = name.replace(' -global', '')
            serverid = 'global'
        else:
            serverid = str(server.id)

        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        server_info = await self.get_server(server)
        if name in server_info['badges'].keys():
            del server_info['badges'][name]
            await self.badges.update_one({'server_id':server_info['server_id']}, {'$set':{
                "badges":server_info['badges'],
                }})
            await ctx.send(":white_check_mark: **The `{}` badge has been removed.**".format(name))
        else:
            await ctx.send(":red_circle: **That badge does not exist.**")

    @commands.has_permissions(manage_roles=True)
    @badge.command(pass_context = True, no_pm=True)
    async def give(self, ctx, user : discord.Member, name: str):
        """Give a specific user a badge. Used mostly for unpurchaseable badges (-1).

        [Options]
        user: A server member
        name: The name of the badge

        [Example]
        +<COMMAND> Stevy Cookie
        """
        return
        org_user = ctx.message.author
        server = ctx.message.guild
        # creates user if doesn't exist
        await self._create_user(user, server)
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        server_info = await self.get_server(server)
        badges = server_info['badges']
        badge_name = "{}_{}".format(name, str(server.id))

        if name not in badges:
            return await ctx.send(":red_circle: **That badge doesn't exist in this server!**")
        elif badge_name in badges.keys():
            return await ctx.send(":large_blue_circle: **{} already has that badge!**".format(self._is_mention(user)))
        else:
            userinfo["badges"][badge_name] = badges[name]
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{"badges": userinfo["badges"]}})
            return await ctx.send(":white_check_mark: **{} has just given `{}` the `{}` badge!**".format(
                self._is_mention(org_user), self._is_mention(user), name))

    @commands.has_permissions(manage_roles=True)
    @badge.command(name = 'link', no_pm=True)
    async def linkbadge(self, ctx, badge_name:str, level:int):
        """Associate a role with a level. Only one link per badge.

        [Options]
        badge_name: The name of the badge
        level: Level you get the badge at. Can only be 5 higher than server's highest level.

        [Example]
        +<COMMAND> Cookie 5
        """
        return
        server = ctx.message.guild
        server_info = await self.get_server(server)
        serverbadges = server_info['badges']

        if serverbadges == None:
            await ctx.send(":red_circle: **This server does not have any badges!**")
            return
        if badge_name not in serverbadges['badges'].keys():
            await ctx.send(":red_circle: **Please make sure the `{}` badge exists!**".format(badge_name))
            return
        else:
            server_linked_badges = db.badgelinks.find_one({'server_id':str(server.id)})
            if not server_linked_badges:
                new_server = {
                    'server_id': str(server.id),
                    'badges': {
                        badge_name:str(level)
                    }
                }
                db.badgelinks.insert_one(new_server)
            else:
                server_linked_badges['badges'][badge_name] = str(level)
                db.badgelinks.update_one({'server_id':str(server.id)}, {'$set':{'badges':server_linked_badges['badges']}})
            await ctx.send("**The `{}` badge has been linked to level `{}`**".format(badge_name, level))

        if not server_info:
            new_server = {
                'server_id': str(server.id),
                'roles': {},
                'badges': {
                    str(badge_name): {
                        'level':str(level)
                    }
                }
            }
            await self.servers.insert_one(new_server)
        else:
            if str(badge_name) not in server_info['badges'].keys():
                server_info['badges'][str(badge_name)] = {}

            server_info['badges'][str(badge_name)]['level'] = str(level)
            await self.servers.update_one({'server_id':str(server.id)}, {
                '$set':{'badges':server_info['badges']}})

    @commands.has_permissions(manage_roles=True)
    @badge.command(name = 'unlink', no_pm=True)
    async def unlinkbadge(self, ctx, badge_name:str):
        """Delete a role/level association.

        [Options]
        badge_name: The name of the badge

        [Example]
        +<COMMAND> Cookie
        """
        return
        server = ctx.message.guild
        server_info = await self.get_server(server)
        if 'badges' not in server_info:
            return await ctx.send(":red_circle: **You currently have no badge links!**")

        badge_names = list(server_info['badges'].keys()) # uses ids
        if badge_name in badge_names:
            await ctx.send("**Badge/Level association `{}`/`{}` removed.**".format(
                badge_name, server_info['badges'][str(badge_name)]['level']))
            del server_info['badges'][str(badge_name)]
            await self.servers.update_one({'server_id':str(server.id)}, {
                '$set':{'badges':server_info['badges']}})
        else:
            await ctx.send("**The `{}` badge is not linked to any levels!**".format(badge_name))

    @badge.command(name = 'listlinks', no_pm=True)
    async def listbadge(self, ctx):
        """List level/role associations.

        [Example]
        +<COMMAND>
        """
        return
        server = ctx.message.guild
        user = ctx.message.author

        server_info = await self.get_server(server)

        em = discord.Embed(description='', colour=user.colour)
        em.set_author(name="Current Badge - Level Links for {}".format(server.name), icon_url = server.icon_url)

        if server_info == None or 'badges' not in server_info or server_info['badges'] == {}:
            msg = 'None'
        else:
            badges = list(server_info['badges'].keys())
            msg = '**Badge** → Level\n'
            for badge_name in badges:
                msg += '**• {} →** {}\n'.format(
                    badge_name, server_info['badges'][badge_name]['level'])

        em.description = msg
        await ctx.send(embed = em)

    @commands.group(pass_context=True)
    async def role(self, ctx):
        """Associate roles with levels.
        """
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @commands.has_permissions(manage_roles=True)
    @role.command(name = 'link', no_pm=True)
    async def linkrole(self, ctx, role_name:str, level:int, remove_role = None):
        """Associate a role with a level. Removes previous role if given.

        [Options]
        role_name: The name of the role
        level: Level to give role at
        remove_role: Role to remove at that level.

        [Example]
        +<COMMAND> Cookielord 5 "Cookie peasant"
        """
        return
        server = ctx.message.guild
        try:
            role_obj = await commands.RoleConverter().convert(ctx, role_name)
        except commands.CommandError:
            return await ctx.send(":red_circle: **That role doesn't exist!**")

        try:
            if remove_role:
                remove_role_obj = await commands.RoleConverter().convert(ctx, remove_role)
        except commands.CommandError:
            return await ctx.send(":red_circle: **That role to remove doesn't exist!**")

        server_info = await self.get_server(server)
        if not remove_role:
            remove_role_val = None
        else:
            remove_role_val = str(remove_role_obj.id)

        if not server_info:
            new_server = {
                'server_id': str(server.id),
                'roles': {
                    str(role_obj.id): {
                        'level':str(level),
                        'remove_role': remove_role_val
                        }
                },
                'badges': {}
            }
            await self.servers.insert_one(new_server)
        else:
            if str(role_obj.id) not in server_info['roles'].keys():
                server_info['roles'][str(role_obj.id)] = {}

            server_info['roles'][str(role_obj.id)]['level'] = str(level)
            server_info['roles'][str(role_obj.id)]['remove_role'] = remove_role_val
            await self.servers.update_one({'server_id':str(server.id)}, {
                '$set':{'roles':server_info['roles']}})

        if not remove_role:
            await ctx.send("**The `{}` role has been linked to level `{}`**".format(role_name, level))
        else:
            await ctx.send("**The `{}` role has been linked to level `{}`. Will also remove `{}` role.**".format(
                role_name, level, remove_role))

    @commands.has_permissions(manage_roles=True)
    @role.command(name = 'unlink', no_pm=True)
    async def unlinkrole(self, ctx, role_name:str):
        """Delete a role/level association.

        [Options]
        role_name: The name of the role to delete.

        [Example]
        +<COMMAND> Cookielord
        """
        return
        server = ctx.message.guild

        try:
            role_obj = await commands.RoleConverter().convert(ctx, role_name)
        except commands.CommandError:
            return await ctx.send(":red_circle: **That role doesn't exist!**")

        server_info = await self.get_server(server)
        if 'roles' not in server_info:
            return await ctx.send(":red_circle: **You currently have no role links!**")

        roles = list(server_info['roles'].keys()) # uses ids
        if str(role_obj.id) in roles:
            await ctx.send("**Role/Level association `{}`/`{}` removed.**".format(
                role_name, server_info['roles'][str(role_obj.id)]['level']))
            del server_info['roles'][str(role_obj.id)]
            await self.servers.update_one({'server_id':str(server.id)}, {
                '$set':{'roles':server_info['roles']}})
        else:
            await ctx.send("**The `{}` role is not linked to any levels!**".format(role_name))

    @commands.has_permissions(manage_roles=True)
    @role.command(name = 'list', no_pm=True)
    async def listrole(self, ctx):
        """List level/role associations.

        [Example]
        +<COMMAND>
        """
        return
        server = ctx.message.guild
        user = ctx.message.author

        server_info = await self.get_server(server)

        em = discord.Embed(description='', colour=user.colour)
        em.set_author(name="Current Role - Level Links for {}".format(server.name), icon_url = server.icon_url)

        if server_info == None or 'roles' not in server_info or server_info['roles'] == {}:
            msg = 'None'
        else:
            roles = list(server_info['roles'].keys())
            msg = '**Role** → Level\n'
            for role_id in roles:
                try:
                    role_obj = await commands.RoleConverter().convert(ctx, role_id)
                except commands.CommandError:
                    pass

                if server_info['roles'][role_id]['remove_role']:
                    try:
                        role_remove_obj = await commands.RoleConverter().convert(
                            ctx, roles[role_id]['remove_role'])
                    except commands.CommandError:
                        pass

                    msg += '**• {} →** {} (Removes: {})\n'.format(
                        role_obj.name, server_info['roles'][role_id]['level'], role_remove_obj.name)
                else:
                    msg += '**• {} →** {}\n'.format(
                        role_obj.name, server_info['roles'][role_id]['level'])
        em.description = msg
        await ctx.send(embed = em)

    @commands.group(aliases=['bg','bgs'])
    async def background(self, ctx):
        """Background Configuration Options"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @background.command(name = 'add', no_pm=True)
    async def add_background(self, ctx, bg_type:str, bg_name:str,
            bg_url:str, price:int, credits=None):
        """
        Adds a background of a certain type.

        [Options]
        bg_type: profile, rank, levelup
        bg_name: Whatever you want to call it.
        bg_url: Imgur link of the url.
        price: Price of the background.
        credits: Who made the image/gif. Optional but prefered.

        [Example]
        +<COMMAND> profile "stevy is stevy" https://i.imgur.com/TfyYUkP.png 30000 Stevy
        """

        user = ctx.message.author
        if str(user.id) != self.bot.config["owner"]:
            await ctx.send(f":red_circle: **Silly {user.name}, only Stevy can do that. \
                If you want to suggest backgrounds, you can do so in the owo! server. \
                After all, you already have all the parts to suggest one.**")
            return

        if bg_name in self.backgrounds[bg_type].keys():
            await ctx.send("**That background name already exists!**")
        elif not await self._valid_image_url(bg_url):
            await ctx.send("**That is not a valid image url!**")
        else:
            self.backgrounds[bg_type][bg_name] = {
                "url": bg_url,
                "price": price,
                "credits": credits
            }
            fileIO('cogs/social/backgrounds/backgrounds.json', "save", self.backgrounds)
            await ctx.send("**New {} background(`{}`) added.**".format(
                bg_type, bg_name))

    @background.command(name="delete", no_pm=True)
    async def delete_background(self, ctx, bg_type:str, bg_name:str):
        """
        Deletes a background of a certain type.

        [Options]
        bg_type: profile, rank, levelup
        bg_name: Whatever the background is called.

        [Example]
        +<COMMAND> profile "stevy is stevy"
        """
        user = ctx.message.author
        if str(user.id) != self.bot.config["owner"]:
            await ctx.send(f":red_circle: **Not happy with current backgrounds, {user.name}? You can suggest more in the owo! server.**")
            return

        if bg_name in self.backgrounds[bg_type].keys():
            del self.backgrounds[bg_type][bg_name]
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**The {} background(`{}`) has been deleted.**".format(
                bg_type, bg_name))
        else:
            await self.bot.say("**That background name doesn't exist.**")

    @background.command(name = 'special', hidden=True, no_pm=True)
    async def special_background(self, ctx, target_user, bg_type:str, bg_url:str):
        """Give a special background.

        [Options]
        target_user: Preferably a user id
        bg_type: profile, rank, levelup
        bg_url: Link to an image. Must have image file extension!

        [Example]
        +<COMMAND> 91988142223036416 profile https://i.imgur.com/ed2SkCh.gif
        """
        user = ctx.message.author
        if str(user.id) != self.bot.config["owner"]:
            return

        valid_types =  ['levelup','rank','profile']
        if bg_type not in valid_types:
            await ctx.send(":red_circle: **Please pick a correct bg type: `{}`.**".format(
                ', '.join(valid_types)))
            return

        try:
            target_user = await commands.UserConverter().convert(ctx, target_user)
        except commands.CommandError:
            await ctx.send(":red_circle: **Can't find that user!**")
            return

        # find in database
        db_user = await self.get_user(target_user)
        if not db_user:
            await ctx.send(":red_circle: **User is not in database!**")
            return

        # give the background
        user_bg_list = db_user["inventory"]["backgrounds"][bg_type]
        if bg_url in user_bg_list:
            await ctx.send(":red_circle: **That user already has that background!**")
            return

        if any(x in bg_url for x in ["gifv"]) or \
            not any(x in bg_url for x in ["png", "jpg", "gif"]):
            await ctx.send(":red_circle: **Please check your url.**")
            return

        user_bg_list.append(bg_url)
        # download
        bg_name_code = bg_url.replace(
            '.png','').replace('_','').replace(
            '/','').replace('.','').replace(':','')
        if 'gif' in bg_url:
            bg_path = 'cogs/social/backgrounds/special/{}/{}.gif'.format(
                bg_type, bg_name_code)
        else:
            bg_path = 'cogs/social/backgrounds/special/{}/{}.png'.format(
                bg_type, bg_name_code)

        async with aiohttp.ClientSession() as session:
            async with session.get(bg_url) as r:
                image = await r.content.read()
                with open(bg_path,'wb') as f:
                    f.write(image)

        await self.all_users.update_one({'user_id':str(user.id)},
            {'$set':{
                "inventory.backgrounds.{}".format(bg_type): user_bg_list,
            }})

        await ctx.send(f":white_check_mark: **Gave {target_user.name} a special {bg_type} background: <{bg_url}>**")

    @background.command(name = 'buy', no_pm=True)
    async def buy_background(self, ctx, bg_type:str, bg_name:str):
        """Buy a background.

        [Options]
        type: profile, rank, levelup
        bg_name: use +backgrounds list to check.

        [Example]
        +<COMMAND> profile greenery
        """
        promotion = False
        user = ctx.message.author
        db_user =  await self.get_user(user)
        valid_types =  ['levelup','rank','profile']
        if bg_type not in valid_types:
            await ctx.send(":red_circle: **Please pick a correct bg type: `{}`.**".format(
                ', '.join(valid_types)))
            return
        backgrounds = self.backgrounds[bg_type].keys()
        if bg_name not in backgrounds:
            await ctx.send(":red_circle: **That background doesn't exist. Use quotes for names with spaces.**")
            return

        background = self.backgrounds[bg_type][bg_name]
        user_bg_list = db_user["inventory"]["backgrounds"][bg_type]
        if bg_name in user_bg_list:
            await ctx.send(":red_circle: **You already have that background.**")
            return

        # define the background price
        price = background["price"]
        if promotion:
            price = 200
        elif str(user.id) == self.bot.config["owner"]:
            price = 0

        if db_user["credits"] < price:
            await ctx.send(":red_circle: **Not enough credits. You need `{}` more.**".format(
                price-db_user["credits"]))
            return

        await ctx.send(f":white_check_mark: **You successfully bought the `{bg_name}` {bg_type} background.**")

        db_user["credits"] = db_user["credits"] - price
        user_bg_list.append(bg_name)

        await self.all_users.update_one({'user_id':str(user.id)},
            {'$set':{
                "inventory.backgrounds.{}".format(bg_type): user_bg_list,
                "credits":db_user["credits"]
            }})

    @background.command(name = 'list', no_pm=True)
    async def disp_backgrounds(self, ctx, type:str = None):
        """Get a list of all available backgrounds.

        [Options]
        type: profile, rank, levelup

        [Example]
        +<COMMAND> profile
        """
        server = ctx.message.guild
        user = ctx.message.author
        max_all = 20

        em = discord.Embed(description='', colour=user.colour)
        if not type:
            em.set_author(name="All Backgrounds for {}".format(self.bot.user.name), icon_url = str(self.bot.user.avatar_url_as(static_format='png')))

            for category in self.backgrounds.keys():
                bg_url = []
                for background_name in sorted(self.backgrounds[category].keys()):
                    bg_url.append("[{}]({})".format(
                        background_name, self.backgrounds[category][background_name]["url"]))
                max_bg = min(max_all, len(bg_url))
                bgs = ", ".join(bg_url[0:max_bg])
                if len(bg_url) >= max_all:
                    bgs += "..."
                em.add_field(name = category.upper(), value = bgs, inline = False)
                em.set_footer(text = "For more backgrounds/info, use >background list [profile|rank|levelup]")
            await ctx.send(embed = em)
        else:
            if type.lower() == "profile":
                em.set_author(name="Profile Backgrounds for {}".format(self.bot.user.name), icon_url = str(self.bot.user.avatar_url_as(static_format='png')))
                bg_key = "profile"
            elif type.lower() == "rank":
                em.set_author(name="Rank Backgrounds for {}".format(self.bot.user.name), icon_url = str(self.bot.user.avatar_url_as(static_format='png')))
                bg_key = "rank"
            elif type.lower() == "levelup":
                em.set_author(name="Level Up Backgrounds for {}".format(self.bot.user.name), icon_url = str(self.bot.user.avatar_url_as(static_format='png')))
                bg_key = "levelup"
            else:
                bg_key = None

            if bg_key:
                bg_url = []
                for background_name in sorted(self.backgrounds[bg_key].keys()):
                    bg_url.append("[{}]({}) `{}`".format(
                        background_name, self.backgrounds[bg_key][background_name]["url"],
                        self.backgrounds[bg_key][background_name]["price"]))
                bgs = ", ".join(bg_url)

                total_pages = 0
                for page in pagify(bgs, [" "]):
                    total_pages +=1

                counter = 1
                for page in pagify(bgs, [" "]):
                    em.description = page
                    em.set_footer(text = "Page {} of {}".format(counter, total_pages))
                    await ctx.send(embed = em)
                    counter += 1
            else:
                await ctx.send("**Invalid Background Type. (profile, rank, levelup)**")

    def get_bg_name(self, bg_type, url):
        try:
            for bg_name in self.backgrounds[bg_type]:
                if self.backgrounds[bg_type][bg_name]["url"] == url:
                    return str(bg_name)
            return "default"
        except:
            return "default"

    async def draw_profile(self, ctx, user):
        # start_time = datetime.datetime.now()
        pic_id = random.randint(0, 25)
        name_size = 30
        long_name = False
        if len(user.name) >= 12:
            name_size = 22
            long_name = True
        name_fnt = ImageFont.truetype(font_heavy_file, name_size)
        name_u_fnt = ImageFont.truetype(font_unicode_file, name_size)
        name_cjk_fnt = ImageFont.truetype(font_cjk_file, 30)
        title_fnt = ImageFont.truetype(font_heavy_file, 22)
        title_u_fnt = ImageFont.truetype(font_unicode_file, 23)
        title_cjk_fnt = ImageFont.truetype(font_cjk_file, 22)
        label_fnt = ImageFont.truetype(font_bold_file, 18)
        exp_fnt = ImageFont.truetype(font_bold_file, 13)
        large_fnt = ImageFont.truetype(font_thin_file, 33)
        rep_fnt = ImageFont.truetype(font_heavy_file, 26)
        rep_u_fnt = ImageFont.truetype(font_unicode_file, 30)
        text_fnt = ImageFont.truetype(font_file, 14)
        text_u_fnt = ImageFont.truetype(font_unicode_file, 14)
        text_cjk_fnt = ImageFont.truetype(font_cjk_file, 16)
        symbol_u_fnt = ImageFont.truetype(font_unicode_file, 15)

        def _write_unicode(text, init_x, y, font, unicode_font, fill, cjk_font = None):
            write_pos = init_x
            if not cjk_font:
                cjk_font = unicode_font
            for char in text:
                if self._is_cjk(char):
                    draw.text((write_pos, y), char, font=cjk_font, fill=fill)
                    write_pos += cjk_font.getsize(char)[0]
                elif char.isalnum() or char in string.punctuation or char in string.whitespace:
                    draw.text((write_pos, y), char, font=font, fill=fill)
                    write_pos += font.getsize(char)[0]
                else:
                    draw.text((write_pos, y), u"{}".format(char), font=unicode_font, fill=fill)
                    write_pos += unicode_font.getsize(char)[0]

        # get urls
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})
        try:
            bg_url = userinfo["profile_background"]["url"]
        except:
            bg_url = userinfo["profile_background"]

        # COLORS
        white_color = (240,240,240,255)
        light_color = (160,160,160,255)
        if "rep_color" not in userinfo.keys() or not userinfo["rep_color"]:
            rep_fill = (92,130,203,230)
        else:
            rep_fill = tuple(userinfo["rep_color"])
        # determines badge section color, should be behind the titlebar
        if "badge_col_color" not in userinfo.keys() or not userinfo["badge_col_color"]:
            badge_fill = (128,151,165,230)
        else:
            badge_fill = tuple(userinfo["badge_col_color"])
        if "profile_info_color" in userinfo.keys():
            info_fill = tuple(userinfo["profile_info_color"])
        else:
            info_fill = (30, 30 ,30, 220)
        info_fill_tx = (info_fill[0], info_fill[1], info_fill[2], 150)
        if "profile_exp_color" not in userinfo.keys() or not userinfo["profile_exp_color"]:
            exp_fill = (255, 255, 255, 230)
        else:
            exp_fill = tuple(userinfo["profile_exp_color"])
        if badge_fill == (128,151,165,230):
            level_fill = white_color
        else:
            level_fill = self._contrast(exp_fill, rep_fill, badge_fill)

        # create image objects
        bg_image = Image
        profile_image = Image

        # get images
        profile_url = str(user.avatar_url_as(static_format='png'))
        profile_path = 'cogs/social/temp/{}_temp_profile_profile.png'.format(pic_id)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(profile_url) as r:
                    image = await r.content.read()
            except:
                async with session.get(default_avatar_url) as r:
                    image = await r.content.read()
            with open(profile_path,'wb') as f:
                f.write(image)
            profile_image = Image.open(profile_path).convert('RGBA')

        file_found = None
        is_gif = False
        bg_name = self.get_bg_name("profile", bg_url)
        if bg_url and "gif" in bg_url:
            is_gif = True
            filepath = 'cogs/social/backgrounds/profile/{}.gif'.format(bg_name)
            special_file_name = bg_url.replace('.gif','').replace('_','').replace('/','').replace('.','').replace(':','')
            filepath_special = 'cogs/social/backgrounds/special/profile/{}.gif'.format(special_file_name)
            if os.path.exists(filepath):
                file_found = filepath
            elif os.path.exists(filepath_special):
                file_found = filepath_special
        elif bg_url:
            filepath = 'cogs/social/backgrounds/profile/{}.png'.format(bg_name)
            special_file_name = bg_url.replace('.png','').replace('_','').replace('/','').replace('.','').replace(':','')
            filepath_special = 'cogs/social/backgrounds/special/profile/{}.png'.format(special_file_name)
            if os.path.exists(filepath):
                file_found = filepath
            elif os.path.exists(filepath_special):
                file_found = filepath_special

        if not file_found:
            if not bg_url:
                bg_url = default_profile_bg_url

            if 'gif' in bg_url:
                bg_path = 'cogs/social/temp/{}_temp_profile_bg.gif'.format(pic_id)
            else:
                bg_path = 'cogs/social/temp/{}_temp_profile_bg.png'.format(pic_id)

            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as r:
                    image = await r.content.read()

            with open(bg_path,'wb') as f:
                f.write(image)
            bg_image = Image.open(bg_path)
        else:
            if is_gif:
                bg_image = Image.open(file_found)
            else:
                bg_image = Image.open(file_found).convert('RGBA')

        # set canvas
        bg_color = (255,255,255,0)
        result = Image.new('RGBA', (340, 390), bg_color)
        process = Image.new('RGBA', (340, 390), bg_color)

        # draw
        draw = ImageDraw.Draw(process)

        # draw filter
        draw.rectangle([(0,0),(340, 340)], fill=(0,0,0,10))

        # draw transparent overlay
        vert_pos = 305
        left_pos = 0
        right_pos = 340
        title_height = 30
        gap = 3

        draw.rectangle([(0,134), (340, 325)], fill=info_fill_tx) # general content

        # draw circle mask
        multiplier = 4
        lvl_circle_dia = 116
        circle_left = 14
        circle_top = 48
        raw_length = lvl_circle_dia * multiplier
        mask = Image.new('L', (raw_length, raw_length), 0) # mask ---------------

        draw_thumb = ImageDraw.Draw(mask)
        draw_thumb.ellipse((0, 0) + (raw_length, raw_length), fill = 255, outline = 0)

        # border
        lvl_circle = Image.new("RGBA", (raw_length, raw_length))
        draw_lvl_circle = ImageDraw.Draw(lvl_circle)
        draw_lvl_circle.ellipse([0, 0, raw_length, raw_length], fill=(255, 255, 255, 255), outline = (255, 255, 255, 250))
        # put border
        lvl_circle = lvl_circle.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        lvl_bar_mask = mask.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        process.paste(lvl_circle, (circle_left, circle_top), lvl_bar_mask)

        # put in profile picture
        total_gap = 6
        border = int(total_gap/2)
        profile_size = lvl_circle_dia - total_gap
        raw_length = profile_size * multiplier
        output = ImageOps.fit(profile_image, (raw_length, raw_length), centering=(0.5, 0.5))
        output = output.resize((profile_size, profile_size), Image.ANTIALIAS)
        mask = mask.resize((profile_size, profile_size), Image.ANTIALIAS)
        profile_image = profile_image.resize((profile_size, profile_size), Image.ANTIALIAS)
        process.paste(profile_image, (circle_left + border, circle_top + border), mask)

        # write label text
        white_color = (240,240,240,255)
        light_color = (160,160,160,255)
        dark_color = (35, 35, 35, 255)

        head_align = 140
        name_v_align = 142
        if long_name:
            name_v_align += 3
        # determine info text color
        info_text_color = self._contrast(info_fill, white_color, dark_color)
        _write_unicode(self._truncate_text(user.name, 22).upper(), head_align, name_v_align, name_fnt, name_u_fnt, info_text_color, cjk_font = name_cjk_fnt) # NAME
        _write_unicode(userinfo["title"].upper(), head_align, 170, title_fnt, title_u_fnt, info_text_color, cjk_font = title_cjk_fnt)

        # draw divider
        draw.rectangle([(0,323), (340, 324)], fill=(0,0,0,255)) # box
        # draw text box
        draw.rectangle([(0,324), (340, 390)], fill=(info_fill[0],info_fill[1],info_fill[2],255)) # box

        #rep_text = "{} REP".format(userinfo["rep"])
        rep_text = "{}".format(userinfo["rep"])
        _write_unicode("❤", 257, 9, rep_fnt, rep_u_fnt, info_text_color)
        draw.text((self._center(278, 340, rep_text, rep_fnt), 10), rep_text,  font=rep_fnt, fill=info_text_color) # Exp Text

        lvl_left = 100
        label_align = 362 # vertical
        draw.text((self._center(0, 140, "    RANK", label_fnt), label_align), "    RANK",  font=label_fnt, fill=info_text_color) # Rank
        draw.text((self._center(0, 340, "    LEVEL", label_fnt), label_align), "    LEVEL",  font=label_fnt, fill=info_text_color) # Exp
        draw.text((self._center(200, 340, "BALANCE", label_fnt), label_align), "BALANCE",  font=label_fnt, fill=info_text_color) # Credits

        if "linux" in platform.system().lower():
            global_symbol = u"\U0001F30E "
            fine_adjust = 1
        else:
            global_symbol = "G."
            fine_adjust = 0

        _write_unicode(global_symbol, 36, label_align + 5, label_fnt, symbol_u_fnt, info_text_color) # Symbol
        _write_unicode(global_symbol, 134, label_align + 5, label_fnt, symbol_u_fnt, info_text_color) # Symbol

        # userinfo
        global_rank = "#{}".format(await self._find_global_rank(user, userinfo))
        global_level = "{}".format(self._find_level(userinfo["total_exp"]))
        draw.text((self._center(0, 140, global_rank, large_fnt), label_align-27), global_rank,  font=large_fnt, fill=info_text_color) # Rank
        draw.text((self._center(0, 340, global_level, large_fnt), label_align-27), global_level,  font=large_fnt, fill=info_text_color) # Exp
        # draw level bar
        exp_font_color = self._contrast(exp_fill, light_color, dark_color)
        exp_frac = int(userinfo["total_exp"] - self._level_exp(int(global_level)))
        exp_total = self._required_exp(int(global_level) + 1)
        bar_length = int(exp_frac/exp_total * 340)
        draw.rectangle([(0, 305), (340, 323)], fill=(level_fill[0],level_fill[1],level_fill[2],245)) # level box
        draw.rectangle([(0, 305), (bar_length, 323)], fill=(exp_fill[0],exp_fill[1],exp_fill[2],255)) # box
        exp_text = "{}/{}".format(exp_frac, exp_total)# Exp
        draw.text((self._center(0, 340, exp_text, exp_fnt), 305), exp_text,  font=exp_fnt, fill=exp_font_color) # Exp Text

        try:
            credits = userinfo['credits']
        except:
            credits = 0
        credit_txt = "${}".format(credits)
        draw.text((self._center(200, 340, credit_txt, large_fnt), label_align-27), self._truncate_text(credit_txt, 18),  font=large_fnt, fill=info_text_color) # Credits

        if userinfo["title"] == '':
            offset = 170
        else:
            offset = 195
        margin = 140
        txt_color = self._contrast(info_fill, white_color, dark_color)
        for line in textwrap.wrap(userinfo["info"], width=32):
        # for line in textwrap.wrap('userinfo["info"]', width=200):
            # draw.text((margin, offset), line, font=text_fnt, fill=white_color)
            _write_unicode(line, margin, offset, text_fnt, text_u_fnt, txt_color, cjk_font = text_cjk_fnt)
            offset += text_fnt.getsize(line)[1] + 2

        # sort badges
        priority_badges = []
        if self._has_property(userinfo, 'active_badges'):
            for badge_name in userinfo['active_badges'].keys():
                badge = userinfo['active_badges'][badge_name]
                priority_num = badge["priority_num"]
                if priority_num != 0 and priority_num != -1:
                    priority_badges.append((badge, priority_num))
        sorted_badges = sorted(priority_badges, key=operator.itemgetter(1), reverse=True)

        # TODO: simplify this. it shouldn't be this complicated... sacrifices conciseness for customizability
        # if self._has_property(self.settings, "badge_type"):
        # circles require antialiasing
        vert_pos = 172
        right_shift = 0
        left = 9 + right_shift
        right = 52 + right_shift
        size = 38
        total_gap = 4 # /2
        hor_gap = 6
        vert_gap = 6
        border_width = int(total_gap/2)
        multiplier = 3 # for antialiasing
        raw_length = size * multiplier
        mult = [
            (0,0), (1,0), (2,0),
            (0,1), (1,1), (2,1),
            (0,2), (1,2), (2,2)]

        # draw mask circle
        mask = Image.new('L', (raw_length, raw_length), 0)
        draw_thumb = ImageDraw.Draw(mask)
        draw_thumb.ellipse((0, 0) + (raw_length, raw_length), fill = 255, outline = 0)
        badge_holder, badge_mask = self._draw_badge_holder(mask, exp_fill, info_fill)
        badge_outer_mask = mask.resize((size, size), Image.ANTIALIAS)
        badge_inner_mask = mask.resize((size - total_gap, size - total_gap), Image.ANTIALIAS)

        for num in range(9):
            coord = (left + int(mult[num][0])*int(hor_gap+size), vert_pos + int(mult[num][1])*int(vert_gap + size))
            if num < len(sorted_badges[:9]):
                pair = sorted_badges[num]
                badge = pair[0]
                bg_img = badge["bg_img"]
                border_color = badge["border_color"]
                # determine image or color for badge bg

                badge_path = 'cogs/social/badges/{}/{}.png'.format(
                    badge["server_id"], badge["badge_name"])
                try:
                    badge_image = Image.open(badge_path).convert('RGBA')
                    # structured like this because if border = 0, still leaves outline.
                except:
                    badge_image = await self._download_badge_image(badge, no_save = True)

                if border_color:
                    square = Image.new('RGBA', (size, size), border_color)
                    # put border on ellipse/circle
                    process.paste(square, coord, badge_outer_mask)

                    # put on ellipse/circle
                    output = ImageOps.fit(badge_image, (raw_length, raw_length), centering=(0.5, 0.5))
                    output = badge_image.resize((size - total_gap, size - total_gap), Image.ANTIALIAS)
                    process.paste(output, (coord[0] + border_width, coord[1] + border_width), badge_inner_mask)
                else:
                    # put on ellipse/circle
                    output = ImageOps.fit(badge_image, (raw_length, raw_length), centering=(0.5, 0.5))
                    output = output.resize((size, size), Image.ANTIALIAS)
                    outer_mask = mask.resize((size, size), Image.ANTIALIAS)
                    process.paste(output, coord, badge_outer_mask)
            else:
                process.paste(badge_holder, coord, badge_mask)

            # attempt to remove badge image
            try:
                os.remove('data/leveler/temp/{}_temp_badge.png'.format(pic_id))
            except:
                pass

        # print("Generation Finished", (datetime.datetime.now()-start_time).total_seconds())

        # put background + saving
        if is_gif:
            filename = 'cogs/social/temp/{}_profile.gif'.format(pic_id)
            foreground = process
            background = result
            final_gif = []
            for single_image in ImageSequence.Iterator(bg_image):
                # puts in background
                single_image = single_image.resize((340, 340), Image.ANTIALIAS)
                single_image = single_image.crop((0,0,340, 305))
                background.paste(single_image,(0,0))
                frame = Image.alpha_composite(background, foreground)
                # frame = self._add_corners(frame, 25, multiplier=8)
                final_gif.append(frame)

            """
            with WandImage() as wand:
                # Add new frames into sequance
                for frame in final_gif:
                    with WandImage(frame) as wandframe:
                        wand.sequence.append(wandframe)
                for cursor in range(len(final_gif)):
                    with wand.sequence[cursor] as frame:
                        frame.delay = 10
                wand.save(filename=filename)"""

            """
            imageio.mimsave(filename, final_gif)
            """
            final_gif[0].save(filename, format="GIF", save_all=True,
                quality=100, append_images=final_gif[1:],
                duration = 100, loop=0)
        else:
            filename = 'cogs/social/temp/{}_profile.png'.format(pic_id)
            # puts in background
            bg_image = bg_image.resize((340, 340), Image.ANTIALIAS)
            bg_image = bg_image.crop((0,0,340, 305))
            result.paste(bg_image,(0,0))
            result = Image.alpha_composite(result, process)
            result = self._add_corners(result, 25)
            result.save(filename,'PNG', quality=100)

        # print("Save Finished", (datetime.datetime.now()-start_time).total_seconds())
        return filename

    async def _download_badge_image(self, badge, no_save = False):
        size = 40
        if not no_save:
            badge_path = "cogs/social/badges/"
            if not os.path.exists(badge_path):
                os.makedirs(badge_path)

            server_badge_path = "cogs/social/badges/{}".format(badge["server_id"])
            if not os.path.exists(server_badge_path):
                os.makedirs(server_badge_path)

            badge_name = badge["badge_name"]
            file_path = f"{server_badge_path}/{badge_name}.png"
        else:
            # get image
            file_path = "cogs/social/temp/{}_badge.png".format(
                random.randint(0,5))

        async with aiohttp.ClientSession() as session:
            async with session.get(badge["bg_img"]) as r:
                image = await r.content.read()
            with open(file_path,'wb') as f:
                f.write(image)
        badge_image = Image.open(file_path).convert('RGBA')
        badge_image = badge_image.resize((size, size), Image.ANTIALIAS) # what the badge is supposed to be
        badge_image.save(file_path, quality=100)
        return badge_image

    def _draw_badge_holder(self, mask, plus_fill, info_fill, multiplier = 6):
        size = 38
        raw_length = size * multiplier

        # put on ellipse/circle
        plus_square = Image.new('RGBA', (raw_length, raw_length))
        plus_draw = ImageDraw.Draw(plus_square)
        plus_draw.rectangle([(0,0), (raw_length, raw_length)], fill=(info_fill[0],info_fill[1],info_fill[2],245))
        # draw plus signs
        margin = 60
        thickness = 40
        v_left = int(raw_length/2 - thickness/2)
        v_right = v_left + thickness
        v_top = margin
        v_bottom = raw_length - margin
        plus_draw.rectangle([(v_left,v_top), (v_right, v_bottom)], fill=(plus_fill[0],plus_fill[1],plus_fill[2],245))
        h_left = margin
        h_right = raw_length - margin
        h_top = int(raw_length/2 - thickness/2)
        h_bottom = h_top + thickness
        plus_draw.rectangle([(h_left,h_top), (h_right, h_bottom)], fill=(plus_fill[0],plus_fill[1],plus_fill[2],245))
        # put border on ellipse/circle
        output = ImageOps.fit(plus_square, (raw_length, raw_length), centering=(0.5, 0.5))
        output = output.resize((size, size), Image.ANTIALIAS)
        outer_mask = mask.resize((size, size), Image.ANTIALIAS)
        return output, outer_mask

    # returns color that contrasts better in background
    def _contrast(self, bg_color, color1, color2):
        color1_ratio = self._contrast_ratio(bg_color, color1)
        color2_ratio = self._contrast_ratio(bg_color, color2)
        if color1_ratio >= color2_ratio:
            return color1
        else:
            return color2

    def _luminance(self, color):
        # convert to greyscale
        luminance = float((0.2126*color[0]) + (0.7152*color[1]) + (0.0722*color[2]))
        return luminance

    def _contrast_ratio(self, bgcolor, foreground):
        f_lum = float(self._luminance(foreground)+0.05)
        bg_lum = float(self._luminance(bgcolor)+0.05)

        if bg_lum > f_lum:
            return bg_lum/f_lum
        else:
            return f_lum/bg_lum

    # returns a string with possibly a nickname
    def _name(self, user, max_length):
        if user.name == user.display_name:
            return user.name
        else:
            return "{} ({})".format(user.name, self._truncate_text(user.display_name, max_length - len(user.name) - 3), max_length)

    async def _add_dropshadow(self, image, offset=(4,4), background=0x000, shadow=0x0F0, border=3, iterations=5):
        totalWidth = image.size[0] + abs(offset[0]) + 2*border
        totalHeight = image.size[1] + abs(offset[1]) + 2*border
        back = Image.new(image.mode, (totalWidth, totalHeight), background)

        # Place the shadow, taking into account the offset from the image
        shadowLeft = border + max(offset[0], 0)
        shadowTop = border + max(offset[1], 0)
        back.paste(shadow, [shadowLeft, shadowTop, shadowLeft + image.size[0], shadowTop + image.size[1]])

        n = 0
        while n < iterations:
            back = back.filter(ImageFilter.BLUR)
            n += 1

        # Paste the input image onto the shadow backdrop
        imageLeft = border - min(offset[0], 0)
        imageTop = border - min(offset[1], 0)
        back.paste(image, (imageLeft, imageTop))
        return back

    async def draw_rank(self, ctx, user):
        pic_id = random.randint(50, 70) # probably less needed
        server = ctx.message.guild
        name_fnt = ImageFont.truetype(font_heavy_file, 24)
        name_u_fnt = ImageFont.truetype(font_unicode_file, 24)
        label_fnt = ImageFont.truetype(font_bold_file, 16)
        exp_fnt = ImageFont.truetype(font_bold_file, 9)
        large_fnt = ImageFont.truetype(font_thin_file, 24)
        large_bold_fnt = ImageFont.truetype(font_bold_file, 24)
        symbol_u_fnt = ImageFont.truetype(font_unicode_file, 15)

        def _write_unicode(text, init_x, y, font, unicode_font, fill):
            write_pos = init_x
            for char in text:
                if char.isalnum() or char in string.punctuation or char in string.whitespace:
                    draw.text((write_pos, y), char, font=font, fill=fill)
                    write_pos += font.getsize(char)[0]
                else:
                    draw.text((write_pos, y), u"{}".format(char), font=unicode_font, fill=fill)
                    write_pos += unicode_font.getsize(char)[0]

        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        # get urls
        bg_url = userinfo["rank_background"]
        profile_url = str(user.avatar_url_as(static_format='png'))
        server_icon_url = server.icon_url

        # create image objects
        bg_image = Image
        profile_image = Image

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(profile_url) as r:
                    image = await r.content.read()
            except:
                async with session.get(default_avatar_url) as r:
                    image = await r.content.read()
            with open('cogs/social/temp/{}_temp_rank_profile.png'.format(str(pic_id)),'wb') as f:
                f.write(image)

        bg_name = self.get_bg_name("rank", bg_url)
        bg_image = Image.open('cogs/social/backgrounds/rank/{}.png'.format(bg_name)).convert('RGBA')
        profile_image = Image.open('cogs/social/temp/{}_temp_rank_profile.png'.format(str(pic_id))).convert('RGBA')

        # set canvas
        width = 390
        height = 100
        bg_color = (255,255,255, 0)
        bg_width = width - 50
        result = Image.new('RGBA', (width, height), bg_color)
        process = Image.new('RGBA', (width, height), bg_color)
        draw = ImageDraw.Draw(process)

        # info section
        info_section = Image.new('RGBA', (bg_width, height), bg_color)
        info_section_process = Image.new('RGBA', (bg_width, height), bg_color)
        draw_info = ImageDraw.Draw(info_section)
        # puts in background
        bg_image = bg_image.resize((width, height), Image.ANTIALIAS)
        bg_image = bg_image.crop((0,0, width, height))
        info_section.paste(bg_image, (0,0))

        # draw transparent overlays
        draw_overlay = ImageDraw.Draw(info_section_process)
        draw_overlay.rectangle([(0,0), (bg_width,20)], fill=(230,230,230,200))
        draw_overlay.rectangle([(0,20), (bg_width,30)], fill=(120,120,120,180)) # Level bar
        exp_frac = int(userinfo["servers"][str(server.id)]["current_exp"])
        exp_total = self._required_exp(userinfo["servers"][str(server.id)]["level"])
        exp_width = int((bg_width) * (exp_frac/exp_total))
        if "rank_info_color" in userinfo.keys():
            exp_color = tuple(userinfo["rank_info_color"])
            exp_color = (exp_color[0], exp_color[1], exp_color[2], 180) # increase transparency
        else:
            exp_color = (140,140,140,230)
        draw_overlay.rectangle([(25,20), (25+exp_width,30)], fill=exp_color) # Exp bar
        draw_overlay.rectangle([(0,30), (bg_width,31)], fill=(0,0,0,255)) # Divider
        draw_overlay.rectangle([(0,35), (bg_width,100)], fill=(230,230,230,0)) # title overlay
        for i in range(0,70):
            draw_overlay.rectangle([(0,height-i), (bg_width,height-i)], fill=(20,20,20,255-i*3)) # title overlay

        # draw corners and finalize
        info_section = Image.alpha_composite(info_section, info_section_process)
        info_section = self._add_corners(info_section, 25)
        process.paste(info_section, (35,0))

        # draw level circle
        multiplier = 6
        lvl_circle_dia = 100
        circle_left = 0
        circle_top = int((height- lvl_circle_dia)/2)
        raw_length = lvl_circle_dia * multiplier

        # create mask
        mask = Image.new('L', (raw_length, raw_length), 0)
        draw_thumb = ImageDraw.Draw(mask)
        draw_thumb.ellipse((0, 0) + (raw_length, raw_length), fill = 255, outline = 0)

        # drawing level border
        lvl_circle = Image.new("RGBA", (raw_length, raw_length))
        draw_lvl_circle = ImageDraw.Draw(lvl_circle)
        draw_lvl_circle.ellipse([0, 0, raw_length, raw_length], fill=(250, 250, 250, 250))
        # determines exp bar color
        """
        if "rank_exp_color" not in userinfo.keys() or not userinfo["rank_exp_color"]:
            exp_fill = (255, 255, 255, 230)
        else:
            exp_fill = tuple(userinfo["rank_exp_color"])"""
        exp_fill = (255, 255, 255, 230)

        # put on profile circle background
        lvl_circle = lvl_circle.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        lvl_bar_mask = mask.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        process.paste(lvl_circle, (circle_left, circle_top), lvl_bar_mask)

        # draws mask
        total_gap = 6
        border = int(total_gap/2)
        profile_size = lvl_circle_dia - total_gap
        raw_length = profile_size * multiplier
        # put in profile picture
        output = ImageOps.fit(profile_image, (raw_length, raw_length), centering=(0.5, 0.5))
        output = output.resize((profile_size, profile_size), Image.ANTIALIAS)
        mask = mask.resize((profile_size, profile_size), Image.ANTIALIAS)
        profile_image = profile_image.resize((profile_size, profile_size), Image.ANTIALIAS)
        process.paste(profile_image, (circle_left + border, circle_top + border), mask)

        # draw text
        grey_color = (100,100,100,255)
        white_color = (220,220,220,255)

        # name
        left_text_align = 130
        name_color = 0
        _write_unicode(self._truncate_text(self._name(user, 20), 20), 100, 0, name_fnt, name_u_fnt, grey_color) # Name

        # labels
        v_label_align = 75
        info_text_color = white_color
        draw.text((self._center(100, 200, "  RANK", label_fnt), v_label_align), "  RANK",  font=label_fnt, fill=info_text_color) # Rank
        draw.text((self._center(100, 360, "  LEVEL", label_fnt), v_label_align), "  LEVEL",  font=label_fnt, fill=info_text_color) # Rank
        draw.text((self._center(260, 360, "BALANCE", label_fnt), v_label_align), "BALANCE",  font=label_fnt, fill=info_text_color) # Rank
        local_symbol = u"\U0001F3E0 "
        if "linux" in platform.system().lower():
            local_symbol = u"\U0001F3E0 "
        else:
            local_symbol = "S. "
        _write_unicode(local_symbol, 117, v_label_align + 4, label_fnt, symbol_u_fnt, info_text_color) # Symbol
        _write_unicode(local_symbol, 195, v_label_align + 4, label_fnt, symbol_u_fnt, info_text_color) # Symbol

        # userinfo
        server_rank = "#{}".format(await self._find_server_rank(user, server))
        draw.text((self._center(100, 200, server_rank, large_fnt), v_label_align - 30), server_rank,  font=large_fnt, fill=info_text_color) # Rank
        level_text = "{}".format(userinfo["servers"][str(server.id)]["level"])
        draw.text((self._center(95, 360, level_text, large_fnt), v_label_align - 30), level_text,  font=large_fnt, fill=info_text_color) # Level
        try:
            credits = userinfo['credits']
        except:
            credits = 0

        credit_txt = "${}".format(credits)
        draw.text((self._center(260, 360, credit_txt, large_fnt), v_label_align - 30), credit_txt,  font=large_fnt, fill=info_text_color) # Balance
        exp_text = "{}/{}".format(exp_frac, exp_total)
        draw.text((self._center(80, 360, exp_text, exp_fnt), 19), exp_text,  font=exp_fnt, fill=info_text_color) # Rank


        result = Image.alpha_composite(result, process)
        filename = 'cogs/social/temp/{}_rank.png'.format(str(pic_id))
        result.save(filename,'PNG', quality=100)
        return filename

    def _add_corners(self, im, rad, multiplier = 4):
        raw_length = rad * 2 * multiplier
        circle = Image.new('L', (raw_length, raw_length), 0)
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, raw_length, raw_length), fill=255)
        circle = circle.resize((rad * 2, rad * 2), Image.ANTIALIAS)

        alpha = Image.new('L', im.size, 255)
        w, h = im.size
        alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
        alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
        alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
        alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
        im.putalpha(alpha)
        return im

    async def draw_levelup(self, user, server):
        # fonts
        pic_id = random.randint(0, 50) # probably less needed
        font_thin_file = 'cogs/social/fonts/Uni_Sans_Thin.ttf'
        level_fnt = ImageFont.truetype(font_thin_file, 23)

        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        # get urls
        bg_url = userinfo["levelup_background"]
        profile_url = str(user.avatar_url_as(static_format='png'))

        # create image objects
        bg_image = Image
        profile_image = Image

        profile_path = 'cogs/social/temp/{}_temp_level_profile.png'.format(pic_id)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(profile_url) as r:
                    image = await r.content.read()
            except:
                async with session.get(default_avatar_url) as r:
                    image = await r.content.read()
            with open(profile_path,'wb') as f:
                f.write(image)

        bg_name = self.get_bg_name("levelup", bg_url)
        bg_image = Image.open('cogs/social/backgrounds/levelup/{}.png'.format(bg_name)).convert('RGBA')
        profile_image = Image.open(profile_path).convert('RGBA')

        # set canvas
        width = 176
        height = 67
        bg_color = (255,255,255, 0)
        result = Image.new('RGBA', (width, height), bg_color)
        process = Image.new('RGBA', (width, height), bg_color)
        draw = ImageDraw.Draw(process)

        # puts in background
        bg_image = bg_image.resize((width, height), Image.ANTIALIAS)
        bg_image = bg_image.crop((0,0, width, height))
        result.paste(bg_image, (0,0))

        # info section
        lvl_circle_dia = 60
        total_gap = 2
        border = int(total_gap/2)
        info_section = Image.new('RGBA', (165, 55), (230,230,230,20))
        info_section = self._add_corners(info_section, int(lvl_circle_dia/2))
        process.paste(info_section, (border,border))

        # draw transparent overlay
        if "levelup_info_color" in userinfo.keys():
            info_color = tuple(userinfo["levelup_info_color"])
            info_color = (info_color[0], info_color[1], info_color[2], 150) # increase transparency
        else:
            info_color = (30, 30 ,30, 150)

        for i in range(0,height):
            draw.rectangle([(0,height-i), (width,height-i)], fill=(info_color[0],info_color[1],info_color[2],255-i*3)) # title overlay

        # draw circle
        multiplier = 6
        circle_left = 4
        circle_top = int((height- lvl_circle_dia)/2)
        raw_length = lvl_circle_dia * multiplier
        # create mask
        mask = Image.new('L', (raw_length, raw_length), 0)
        draw_thumb = ImageDraw.Draw(mask)
        draw_thumb.ellipse((0, 0) + (raw_length, raw_length), fill = 255, outline = 0)

        # border
        lvl_circle = Image.new("RGBA", (raw_length, raw_length))
        draw_lvl_circle = ImageDraw.Draw(lvl_circle)
        draw_lvl_circle.ellipse([0, 0, raw_length, raw_length], fill=(250, 250, 250, 180))
        lvl_circle = lvl_circle.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        lvl_bar_mask = mask.resize((lvl_circle_dia, lvl_circle_dia), Image.ANTIALIAS)
        process.paste(lvl_circle, (circle_left, circle_top), lvl_bar_mask)

        profile_size = lvl_circle_dia - total_gap
        raw_length = profile_size * multiplier
        # put in profile picture
        output = ImageOps.fit(profile_image, (raw_length, raw_length), centering=(0.5, 0.5))
        output = output.resize((profile_size, profile_size), Image.ANTIALIAS)
        mask = mask.resize((profile_size, profile_size), Image.ANTIALIAS)
        profile_image = profile_image.resize((profile_size, profile_size), Image.ANTIALIAS)
        process.paste(profile_image, (circle_left + border, circle_top + border), mask)

        # write label text
        white_text = (250,250,250,255)
        dark_text = (35, 35, 35, 230)
        level_up_text = self._contrast(info_color, white_text, dark_text)
        lvl_text = "LEVEL {}".format(userinfo["servers"][str(server.id)]["level"])
        draw.text((self._center(60, 170, lvl_text, level_fnt), 23), lvl_text, font=level_fnt, fill=level_up_text) # Level Number

        result = Image.alpha_composite(result, process)
        result = self._add_corners(result, int(height/2))
        filename = 'cogs/social/temp/{}_level.png'.format(pic_id)
        result.save(filename,'PNG', quality=100)
        return filename

    async def _handle_on_message(self, message):
        return
        
        # print("Message detected")
        author = message.author
        server = message.guild
        content = message.content

        try:
            if server.id != 2903124233097052: # must remove this line eventually!!!!!!
                return
            if author.bot:
                return
            if str(author.id) in self.bot.blacklist['users']:
                return
            if str(server.id) in self.bot.blacklist['servers']:
                return

            try:
                prefixes = await self.bot.get_server_prefixes(self.bot, message, prefix_list = True)
                first_char = content[0]
                if first_char in prefixes:
                    return
            except:
                pass
        except Exception as e:
            # print('ERROR', e)
            return

        loop = asyncio.get_event_loop()
        loop.create_task(self._task_message(message))

    async def _task_message(self, message):
        text = message.content
        channel = message.channel
        server = message.guild
        user = message.author
        curr_time = time.time()


        # creates user if doesn't exist, bots are not logged.
        userinfo = await self.get_user(user)

        if self._is_on_cooldown(user, server):
            return

        await self._process_exp(message, userinfo, random.randint(10, 15))

        """
        if float(curr_time) - float(userinfo["chat_block"]) >= exp_time: #and not any(text.startswith(x) for x in prefix):
            await self._process_exp(message, userinfo, random.randint(10, 15))
            # await self._give_chat_credit(user, server)
            if str(user.id) in self.user_msg_cooldown.keys():
                del self.user_msg_cache[str(user.id)]
        else:
            self.user_msg_cache[str(user.id)] = userinfo["chat_block"]
            """


    def _is_on_cooldown(self, user, server):
        is_cooldown = True
        # if not self._is_on_server_cooldown(server):
        if not self._is_on_user_cooldown(user):
            is_cooldown = False

        return is_cooldown

    def _is_on_server_cooldown(self, server):
        is_server_new = False
        is_server_cooldown = False
        if str(server.id) not in self.server_msg_cooldown:
            is_server_new = True
            self.server_msg_cooldown[str(server.id)] = time.time()

        if time.time() - self.server_msg_cooldown[str(server.id)] < self.SERVER_EXP_COOLDOWN \
            and not is_server_new:
            is_server_cooldown = True

        # do a check of all servers quickly
        smc_copy = copy.deepcopy(self.server_msg_cooldown)
        for s_id in smc_copy:
            if time.time() - smc_copy[s_id] >= self.SERVER_EXP_COOLDOWN:
                try:
                    del self.server_msg_cooldown[s_id]
                except:
                    pass

        return is_server_cooldown

    def _is_on_user_cooldown(self, user):
        is_user_new = False
        is_user_cooldown = False
        if str(user.id) not in self.user_msg_cooldown:
            is_user_new = True
            self.user_msg_cooldown[str(user.id)] = time.time()

        if time.time() - self.user_msg_cooldown[str(user.id)] < self.USER_EXP_COOLDOWN \
            and not is_user_new:
            is_user_cooldown = True

        # do a check of all servers quickly
        umc_copy = copy.deepcopy(self.user_msg_cooldown)
        for u_id in umc_copy:
            if time.time() - umc_copy[u_id] >= self.USER_EXP_COOLDOWN:
                try:
                    del self.user_msg_cooldown[u_id]
                except:
                    pass

        return is_user_cooldown


    async def _process_exp(self, message, userinfo, exp:int):
        print("Processing exp...")
        server = message.author.guild
        channel = message.channel
        user = message.author

        # check if server exists, if not add it to the dict to process later
        if str(server.id) not in userinfo["servers"] or \
            "level" not in userinfo["servers"][str(server.id)] or \
            "current_exp" not in userinfo["servers"][str(server.id)]:

            userinfo["servers"][str(server.id)] = {
                "level": 0,
                "current_exp": 0
            }

        # add to total exp
        #try:
        required = self._required_exp(userinfo["servers"][str(server.id)]["level"])
        new_total = userinfo["total_exp"] + exp

        #print(userinfo["total_exp"] + exp)
        if userinfo["servers"][str(server.id)]["current_exp"] + exp >= required:
            userinfo["servers"][str(server.id)]["level"] += 1
            await self.all_users.update_one({'user_id':str(user.id)}, 
                {'$set':{
                    "servers.{}.level".format(str(server.id)): userinfo["servers"][str(server.id)]["level"],
                    "servers.{}.current_exp".format(str(server.id)): userinfo["servers"][str(server.id)]["current_exp"] + exp - required,
                    "chat_block": time.time(),
                    "total_exp": new_total
                }})
            await self._handle_levelup(user, userinfo, server, channel)
        else:
            await self.all_users.update_one({'user_id':str(user.id)}, 
                {'$set':{
                    "servers.{}.level".format(str(server.id)): userinfo["servers"][str(server.id)]["level"],
                    "servers.{}.current_exp".format(str(server.id)): userinfo["servers"][str(server.id)]["current_exp"] + exp,
                    "chat_block": time.time(),
                    "total_exp": new_total
                }})

        print("Exp updated.")

    async def _handle_levelup(self, user, userinfo, server, channel):
        server_info = await self.bot.get_setting(server, 'leveler')
        # default no alert
        if not server_info or ("lvlup_alert" in server_info.keys() and not server_info["lvlup_alert"]):
            return

        # channel lock implementation
        if server_info and "lock_channel" in server_info.keys() \
            and server_info["lock_channel"]:
            channel_id = server_info["lock_channel"]
            channel = server.get_channel(int(channel_id))

        server_identifier = "" # super hacky
        name = self._is_mention(user) # also super hacky
        # private message takes precedent, of course
        if server_info and "private" in server_info and server_info["private"]:
            server_identifier = " on {}".format(server.name)
            channel = user
            name = "You"

        """
        try:
            new_level = str(userinfo["servers"][str(server.id)]["level"])
            # add to appropriate role if necessary
            if self._has_property(server_info, 'roles'):
                for role_id in server_info['roles'].keys():
                    if int(server_info['roles'][role_id]['level']) == int(new_level):
                        role_obj = discord.utils.get(server.roles, id=int(role_id))
                        await user.add_roles(role_obj)

                    if server_role_links['roles'][role_id]['remove_role']:
                        remove_role_obj = discord.utils.get(server.roles, id=int(
                            server_role_links['roles'][role_id]['remove_role']))
                        await user.remove_roles(remove_role_obj)
        except:
            pass
            """

        """
        try:
            # add appropriate badge if necessary
            if self._has_property(server_info, 'badges'):
                for badge_name in server_settings['badges'].keys():
                    if int(server_settings['badges'][badge_name]) == int(new_level):
                        userinfo_db = await self.all_users.find_one({'user_id':str(user.id)})
                        new_badge_name = "{}_{}".format(badge_name, str(server.id))
                        userinfo_db["badges"][new_badge_name] = server_badges['badges'][badge_name]
                        await self.all_users.update_one({'user_id':str(user.id)}, 
                            {'$set':{"badges": userinfo_db["badges"]}})
        except:
            pass
            """

        filename = await self.draw_levelup(user, server)
        file = discord.File(filename)
        try:
            await channel.send(file=file, content='**{} just gained a level{}!**'.format(name, server_identifier))
        except:
            pass


    async def _find_server_rank(self, user, server):
        target_id = str(user.id)
        users = []
        query = {"servers.{}".format(server.id): {"$exists": True}}

        server_users = []
        async for userinfo in self.all_users.find(query):
            try:
                server_users.append((userinfo["user_id"],
                    userinfo["servers"][str(server.id)]["level"],
                    userinfo["servers"][str(server.id)]["current_exp"]))
            except:
                pass

        sorted_list = sorted(server_users, key=operator.itemgetter(1,2), reverse=True)

        rank = 1
        for a_user in sorted_list:
            if a_user[0] == target_id:
                return rank
            rank += 1
        return 0

    async def _find_server_rep_rank(self, user, server):
        target_id = str(user.id)
        users = []
        query = {
            "servers.{}".format(server.id): {"$exists": True},
        }

        server_users = []
        async for userinfo in self.all_users.find(query):
            try:
                server_users.append((userinfo["user_id"],
                    userinfo["rep"]))
            except:
                pass
        sorted_list = sorted(server_users, key=operator.itemgetter(1), reverse=True)

        rank = 1
        for a_user in sorted_list:
            if a_user[0] == target_id:
                return rank
            rank += 1
        return 0

    async def _find_server_exp_rank(self, user, userinfo, server):
        target_id = str(user.id)
        users = []
        query = {
            "servers.{}".format(server.id): {"$exists": True},
            'total_exp': {'$gt': userinfo['total_exp']}
        }

        # user_rank = await self.all_users.find(query).count()
        exp_rank = await self.all_users.count_documents(query) + 1
        return exp_rank

    async def _find_server_exp(self, user, server):
        server_exp = 0
        userinfo = await self.all_users.find_one({'user_id':str(user.id)})

        try:
            server_exp = server_exp = self._total_required_exp(userinfo["servers"][str(server.id)]["level"])
            server_exp +=  userinfo["servers"][str(server.id)]["current_exp"]
            return server_exp
        except:
            return server_exp

    async def _find_global_rank(self, user, userinfo):
        query = {
            'total_exp': {'$gt': userinfo['total_exp']}
        }
        # user_rank = await self.all_users.find(query).count()
        user_rank = await self.all_users.count_documents(query) + 1
        return user_rank

    async def _find_global_rep_rank(self, user, userinfo):
        query = {
            'rep': {'$gt': userinfo['rep']}
        }
        user_rank = await self.all_users.count_documents(query) + 1
        return user_rank


    # handles user creation, adding new server, blocking
    async def _create_user(self, user, server):
        try:
            userinfo = await self.all_users.find_one({'user_id':str(user.id)})
            if not userinfo:
                new_account = {
                    "user_id" : str(user.id),
                    "username" : user.name,
                    "servers": {},
                    "total_exp": 0,
                    "profile_background": self.backgrounds["profile"]["default"]["url"],
                    "rank_background": self.backgrounds["rank"]["default"]["url"],
                    "levelup_background": self.backgrounds["levelup"]["default"]["url"],
                    "title": "",
                    "info": "I am a mysterious person.",
                    "rep": 0,
                    "active_badges":{},
                    "rep_color": [],
                    "badge_col_color": [],
                    "rep_block": 0,
                    "chat_block": 0,
                    "supporter": False,
                    "inventory": {
                        "backgrounds": {
                            "profile": [],
                            "rank": [],
                            "levelup": []
                        },
                        "badges": {},
                        "cards": {}
                    }
                }
                await self.all_users.insert_one(new_account)

            userinfo = await self.all_users.find_one({'user_id':str(user.id)})

            if "servers" not in userinfo or str(server.id) not in userinfo["servers"]:
                await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                        "servers.{}.level".format(str(server.id)): 0,
                        "servers.{}.current_exp".format(str(server.id)): 0,
                    }}, upsert = True)
        except AttributeError as e:
            pass

    async def get_user(self, user):
        # check integrity
        userinfo = await self.check_user(user)
        return userinfo

    async def check_user(self, user):
        if user.bot:
            return None

        new_account = {
            "user_id" : str(user.id),
            "valid_format": 0,
            "username" : user.name,
            "servers": {},
            "total_exp": 0,
            "profile_background": self.backgrounds["profile"]["default"]["url"],
            "rank_background": self.backgrounds["rank"]["default"]["url"],
            "levelup_background": self.backgrounds["levelup"]["default"]["url"],
            "title": "",
            "info": "I am a mysterious person.",
            "rep": 0,
            "active_badges":{},
            "rep_color": [],
            "badge_col_color": [],
            "rep_block": 0,
            "chat_block": 0,
            "supporter": False,
            "inventory": {
                "backgrounds": {
                    "profile": [],
                    "rank": [],
                    "levelup": []
                },
                "badges": {},
                "cards": {}
            }
        }

        # pass object which includes all fields
        # if not, add it
        userinfo = await self.all_users.find_one({"user_id":str(user.id)})
        if userinfo:
            if self._has_property(userinfo, "valid_format") and userinfo["valid_format"] == 0:
                return userinfo
            else:
                # check for all fields
                for keyname in new_account.keys():
                    if keyname not in userinfo:
                        await self.all_users.update_one({"user_id": str(user.id)},
                            {"$set":{keyname:new_account[keyname]}})
                userinfo = await self.all_users.find_one({"user_id":str(user.id)})
                return userinfo
        else:
            # insert new
            await self.all_users.insert_one(new_account)
            userinfo = await self.all_users.find_one({"user_id":str(user.id)})
            return userinfo

    async def get_server(self, server):
        # check integrity
        server_info = await self.check_server(server)
        return server_info

    async def check_server(self, server):
        if server == "global":
            server_key = "global"
        else:
            server_key = str(server.id)

        if server_key in self.bot.blacklist["server_blacklist"]:
            return None

        # pass object which includes all fields
        # if not, add it
        server_info = await self.servers.find_one({"server_id": server_key})
        if server_info:
            if "badges" not in server_info:
                await self.servers.update_one({"server_id": server_key}, {
                    '$set':{"badges": {},
                }})
                server_info["badges"] = {}
            if "roles" not in server_info:
                await self.servers.update_one({"server_id": server_key}, {
                    '$set':{"roles": {},
                }})
                server_info["roles"] = {}
            return server_info
        else:
            # insert new
            new_account = {
                "server_id" : server_key,
                "badges": {},
                "roles" : {}
            }
            await self.servers.insert_one(new_account)
            server_info = await self.servers.find_one({"server_id": server_key})
            return server_info

        return None

    def _truncate_text(self, text, max_length):
        if len(text) > max_length:
            if text.strip('$').isdigit():
                text = int(text.strip('$'))
                return "${:.2E}".format(text)
            return text[:max_length-3] + "..."
        return text

    # finds the the pixel to center the text
    def _center(self, start, end, text, font):
        dist = end - start
        width = font.getsize(text)[0]
        start_pos = start + ((dist-width)/2)
        return int(start_pos)

    # calculates required exp for next level
    def _required_exp(self, level:int):
        if level < 0:
            return 0
        return 139*level+65

    def _total_required_exp(self, level):
        if len(self.exp_table) < level + 1:
            level_exp = self.exp_table[-1]
            for l in range(len(self.exp_table),level + 1):
                level_exp += self._required_exp(l)
                self.exp_table.append(level_exp)

        return self.exp_table[level]

    def _level_exp(self, level: int):
        return level*65 + 139*level*(level-1)//2

    def _find_level(self, total_exp):
        # this is specific to the function above
        return int((1/278)*(9 + math.sqrt(81 + 1112*(total_exp))))

    def _is_cjk(self, character):
        # from https://stackoverflow.com/questions/30069846/how-to-find-out-chinese-or-japanese-character-in-a-string-in-python
        ranges = [
            {"from": ord(u"\u3300"), "to": ord(u"\u33ff")},         # compatibility ideographs
            {"from": ord(u"\ufe30"), "to": ord(u"\ufe4f")},         # compatibility ideographs
            {"from": ord(u"\uf900"), "to": ord(u"\ufaff")},         # compatibility ideographs
            {"from": ord(u"\U0002F800"), "to": ord(u"\U0002fa1f")}, # compatibility ideographs
            {"from": ord(u"\u30a0"), "to": ord(u"\u30ff")},         # Japanese Kana
            {"from": ord(u"\u2e80"), "to": ord(u"\u2eff")},         # cjk radicals supplement
            {"from": ord(u"\u4e00"), "to": ord(u"\u9fff")},
            {"from": ord(u"\u3400"), "to": ord(u"\u4dbf")},
            {"from": ord(u"\U00020000"), "to": ord(u"\U0002a6df")},
            {"from": ord(u"\U0002a700"), "to": ord(u"\U0002b73f")},
            {"from": ord(u"\U0002b740"), "to": ord(u"\U0002b81f")},
            {"from": ord(u"\U0002b820"), "to": ord(u"\U0002ceaf")}  # included as of Unicode 8.0
        ]

        return any([range["from"] <= ord(character) <= range["to"] for range in ranges])

# ------------------------------ setup ----------------------------------------
def check_folders():
    if not os.path.exists("cogs/social/temp"):
        print("Creating leveler/temp folder...")
        os.makedirs("cogs/social/temp")

def check_files():
    default = {
            "badge_type": "circles",
            "msg_credits": [1,3],
            "msg_exp": [15,20],
            "mention" : False,
            "rep_cooldown": 43200,
            "chat_cooldown": 120,
            "bg_default": {
                "profile": {
                    "price": 2000,
                    "credit": None
                },
                "rank": {
                    "price": 1000,
                    "credit": None
                },
                "levelup": {
                    "price": 500,
                    "credit": None
                }
            },
        }

    settings_path = "cogs/social/settings.json"
    if not os.path.isfile(settings_path):
        print("Creating default leveler settings.json...")
        fileIO(settings_path, "save", default)

    bgs = {
        "levelup" : {
            "abstract cubes" : "http://i.imgur.com/FKQCevB.png",
            "bob ross" : "http://i.imgur.com/Jn6PxSr.png",
            "city blur" : "http://i.imgur.com/9ZXt9XX.png",
            "default" : "http://i.imgur.com/eEFfKqa.jpg",
            "falling" : "https://i.imgur.com/Y62UnNI.jpg",
            "japan" : "http://i.imgur.com/xrrVemk.png",
            "nagisa x kayano" : "http://i.imgur.com/7qflCez.png",
            "neon mountains" : "http://i.imgur.com/wqbwzqk.jpg",
            "sunset" : "http://i.imgur.com/G12AtvB.png",
            "waves" : "http://i.imgur.com/qu5BglB.jpg"
        },
        "profile" : {
            "alice" : "http://i.imgur.com/MUSuMao.png",
            "aqua" : "https://imgur.com/UMH6fT3.png",
            "blue stairs" : "http://i.imgur.com/EjuvxjT.png",
            "burning lake" : "http://i.imgur.com/bxNebc3.png",
            "catgirl" : "https://i.imgur.com/LJE6MQw.png",
            "coastline" : "http://i.imgur.com/XzUtY47.jpg",
            "default" : "http://i.imgur.com/8T1FUP5.jpg",
            "ene chan" : "https://i.imgur.com/EreyRFX.png",
            "pink triangles" : "http://i.imgur.com/vFSrnRQ.png",
            "fireworks" : "http://i.imgur.com/FLYDbeO.png",
            "greenery" : "http://i.imgur.com/70ZH6LX.png",
            "iceberg" : "http://i.imgur.com/8KowiMh.png",
            "inori" : "http://i.imgur.com/1xRa7R1.png",
            "inori red" : "http://i.imgur.com/S6ptPvo.png",
            "lakehouse" : "http://i.imgur.com/1nc1fbK.png",
            "lamp" : "http://i.imgur.com/0nQSmKX.jpg",
            "lazy miku" : "https://i.imgur.com/CrMucxg.png",
            "match" : "http://i.imgur.com/1wLD5Dw.jpg",
            "mirai glasses" : "http://i.imgur.com/2Ak5VG3.png",
            "mirai kuriyama" : "http://i.imgur.com/jQ4s4jj.png",
            "mountain dawn" : "http://i.imgur.com/kJ1yYY6.jpg",
            "okita" : "https://i.imgur.com/HOK2cx3.png",
            "railroad" : "https://i.imgur.com/xWqMc70.png",
            "rain" : "http://i.imgur.com/zrfhqTq.png",
            "red black" : "http://i.imgur.com/74J2zZn.jpg",
            "sea and sky" : "https://i.imgur.com/NXdYpqL.png",
            "ship" : "http://i.imgur.com/wPlvXWy.png",
            "sistine" : "http://i.imgur.com/afMkhGz.png",
            "starry lake" : "https://i.imgur.com/3VviLum.jpg",
            "sunset" : "http://i.imgur.com/v0vojT4.png",
            "sunset river" : "https://i.imgur.com/NGBnb8v.png",
            "swing" : "http://i.imgur.com/hjabaBc.png",
            "waterlilies" : "http://i.imgur.com/qwdcJjI.jpg",
            "wind chime" : "https://i.imgur.com/xPRaLVu.png"
        },
        "rank" : {
            "abstract" : "http://i.imgur.com/70ZH6LX.png",
            "abstract cubes" : "http://i.imgur.com/NAXyoEc.png",
            "aurora" : "http://i.imgur.com/gVSbmYj.jpg",
            "bob ross" : "http://i.imgur.com/uKP9XGV.png",
            "city" : "http://i.imgur.com/yr2cUM9.jpg",
            "city blur" : "http://i.imgur.com/X7MdzJR.png",
            "default" : "http://i.imgur.com/SorwIrc.jpg",
            "lake" : "http://i.imgur.com/M1VxnjY.png",
            "mitsuha" : "http://i.imgur.com/JImELja.jpg",
            "mountain" : "http://i.imgur.com/qYqEUYp.jpg",
            "nagisa x kayano" : "http://i.imgur.com/40iz2fV.png",
            "nebula" : "http://i.imgur.com/V5zSCmO.jpg",
            "neon mountains" : "http://i.imgur.com/nYbuByV.jpg",
            "sunset" : "http://i.imgur.com/YRKLcQU.png",
            "waves" : "http://i.imgur.com/D2pgb6e.jpg"
        }
    }
    bgs_path = "cogs/social/backgrounds/backgrounds.json"
    if not os.path.isfile(bgs_path):
        print("Creating default leveler backgrounds.json...")
        bgs = create_bg_json(bgs, default["bg_default"])
        fileIO(bgs_path, "save", bgs)

def create_bg_json(bg_list, defaults):
    new_bg = {}
    for bg_type in bg_list.keys():
        new_bg[bg_type] = {}
        for bg_name in bg_list[bg_type].keys():
            new_bg[bg_type][bg_name] = {}
            for prop in defaults[bg_type].keys():
                new_bg[bg_type][bg_name][prop] = defaults[bg_type][prop]
            new_bg[bg_type][bg_name]["url"] = str(bg_list[bg_type][bg_name])
    return new_bg

def setup(bot):
    check_folders()
    check_files()

    n = Social(bot)

    if bot.is_passive_bot:
        bot.add_listener(n._handle_on_message, "on_message")
    else:
        bot.add_cog(n)