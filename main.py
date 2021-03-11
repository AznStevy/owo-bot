import os
import re
import sys
import time
import json
import copy
import inspect
import logging
import logging.handlers
import asyncio
import pathlib
import textwrap
import datetime
import warnings
import operator
import importlib
import traceback
from io import TextIOWrapper
from threading import Thread
from utils.dataIO import fileIO
from utils.donor_utils import Patreon

import uvloop
# import pymongo
import motor.motor_asyncio

import discord
from discord.ext import commands

from cogs.osu.updater import Updater

class Bot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        # specify intents
        intents = discord.Intents.default()
        # intents = discord.Intents.all()
        #intents.presence = True
        intents.members = True

        self.start_time = datetime.datetime.utcnow()

        super().__init__(
            command_prefix=self.get_server_prefixes,
            description=kwargs.pop('description'),
            shard_count=kwargs.pop('shard_count'),
            chunk_guilds_at_startup=False,
            intents=intents
        )
        self.help_formatter = HelpFormatter()
        self.config = kwargs['config']
        self.logger = set_logger(self)
        self.settings = None

        # load database
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(
            port=self.config['database']['primary'],
            connectTimeoutMS=5000, 
            socketTimeoutMS=5000, 
            serverSelectionTimeoutMS=5000)

        self.db = self.db_client[str(self.config['bot_name'])] # overall database, not collection
        self.disabled_commands = self.db["disabled"]
        self.prefix_settings = self.db["prefix"] # settings for the cog

        # patreons
        self.patreon = Patreon(self.config['API_KEYS']['PATREON'])

        # load cogs
        self.loop.create_task(self.load_cogs())

        # special lists
        special_lists = fileIO(
            os.path.join(os.getcwd(), 'database','other','special_lists.json'), "load")
        self.blacklist = special_lists['blacklist']
        self.whitelist = special_lists['whitelist']

        # server settings
        self.cached_settings = {}

        # passive commands, separate bot
        self.is_passive_bot = False
        self.is_production = self.config['settings']['production']


    async def get_server_prefixes(self, bot, message, 
        one_prefix=False, prefix_list=False):
        """
        Obtains prefix based on server preference.
        """
        prefix = await self._get_prefix(message)
        if one_prefix:
            return prefix[0]
        elif prefix_list:
            return prefix
        return commands.when_mentioned_or(*prefix)(bot, message)


    async def _get_prefix(self, message):
        """
        Get prefixes for the server
        """
        server = message.guild
        default_prefixes = self.config['prefix']
        try:
            server_info = await self.prefix_settings.find_one({"server_id":str(server.id)})
            prefixes = server_info["prefix"]
        except:
            prefixes = None

        if not prefixes or prefixes == []:
            prefix = default_prefixes
        else:
            prefix = prefixes
        return prefix


    async def load_cogs(self):
        """
        Loads all cogs in folder.
        """
        ignore_list = ['streams','games','audio','updater']
        await self.wait_until_ready()
        # await asyncio.sleep(1) # sleep for 3 minutes

        loaded_cogs = []
        failed_cogs = []
        cog_directory = pathlib.Path('./cogs')
        for cog_name in cog_directory.iterdir():
            cog_name = cog_name.name
            if "__" not in cog_name and cog_name not in ignore_list:
                success = False
                while not success:
                    try:
                        self.load_extension(f'cogs.{cog_name}.{cog_name}')
                        success = True
                    except Exception as e:
                        print(traceback.format_exc())
                        # failed_cogs.append(cog_name)
                        # self.logger.exception(e)
                        await asyncio.sleep(5)


    async def on_ready(self):
        # self.settings = await self.application_info()
        print(f'All {len(self.shards.keys())} shards loaded.')
        elapsed_time = str(datetime.datetime.utcnow() - self.start_time)
        print(f'Took {elapsed_time} seconds.')


    async def on_message(self, message):
        server = message.guild
        user = message.author

        # check if dm
        if not server:
            return

        # handle whitelisting/blacklisting
        if server.id in self.blacklist['servers']:
            return
        if user.id in self.blacklist['users']:
            return        
        if (self.whitelist['servers'] and \
            server.id not in self.whitelist['servers']) and \
            (self.whitelist['users'] and \
                user.id not in self.whitelist['users']):
            return

        # also check if not on blacklist
        await self.process_commands(message)


    def escape_mass_mentions(self, text):
        return self._escape(text, mass_mentions=True)


    def _escape(self, text, *, mass_mentions=False, formatting=False):
        if mass_mentions:
            text = text.replace("@everyone", "@\u200beveryone")
            text = text.replace("@here", "@\u200bhere")
        if formatting:
            text = (text.replace("`", "\\`")
                        .replace("*", "\\*")
                        .replace("_", "\\_")
                        .replace("~", "\\~"))
        return text


    async def get_setting(self, server, db_name):
        if not server:
            return None

        db_name = self._check_db_name(db_name)
        db = self.db[db_name]

        try:
            settings = self.cached_settings[str(server.id)][db_name]
        except:
            settings = await db.find_one({"server_id":str(server.id)})
            await self.cache_setting(server, db_name, settings)

        return settings


    async def cache_setting(self, server, db_name, settings):
        if str(server.id) not in self.cached_settings.keys():
            self.cached_settings[str(server.id)] = {}
        if db_name not in self.cached_settings[str(server.id)].keys():
            self.cached_settings[str(server.id)][db_name] = settings


    def _check_db_name(self, db_name):
        db_name = db_name.lower()
        db_names = ["global", "general", "audio",
                "osu", "economy", "fun", "leveler",
                "streams", "utility", "prefix", "disabled"]

        # double check
        if not any([x == db_name for x in db_names]):
            return None
        return db_name


    async def process_commands(self, message):
        server = message.guild
        channel = message.channel
        # test if server has disabled the command, has to do this for every message
        server_disabled_cmd = await self.get_setting(server, 'disabled')

        # print('Server disabled commands', server_disabled_cmd)
        # if not there, then run normally
        try:
            if not server_disabled_cmd:
                return await super().process_commands(message)
        except:
            return

        ctx = await self.get_context(message)
        if not ctx:
            return
        command = None
        if not ctx.command and not ctx.invoked_subcommand:
            return
        elif ctx.invoked_subcommand:
            # print('SUB: ', ctx.invoked_subcommand)
            command = str(ctx.invoked_subcommand)
        else:
            # print('CMD: ', ctx.command)
            command = str(ctx.command)

        split_cmd = str(ctx.command.module).split(".")
        group = str(split_cmd[2])

        # check if group disabled channel
        if str(channel.id) in server_disabled_cmd.keys() and \
            "group" in server_disabled_cmd[str(channel.id)].keys() and \
            group in server_disabled_cmd[str(channel.id)]["group"]:
            return await channel.send(f":x: **The `{group}` command group is disabled!**", delete_after=5)
        # check if command disabled in channel
        if str(channel.id) in server_disabled_cmd.keys() and \
            "commands" in server_disabled_cmd[str(channel.id)].keys() and \
            command in server_disabled_cmd[str(channel.id)]["commands"]:
            return await channel.send(f":x: **The `{command}` command is disabled!**", delete_after=5)

        # otherwise, run command normally
        await super().process_commands(message)


    async def send_cmd_help(self, ctx):
        help_em = await self.help_formatter.help_format(ctx, ctx.command)
        await ctx.send(embed = help_em)


    async def on_command_error(self, ctx, error):
        channel = ctx.message.channel
        user = ctx.message.author

        if isinstance(error, commands.errors.MissingRequiredArgument):
            await self.send_cmd_help(ctx)
        elif isinstance(error, commands.errors.BadArgument):
            await self.send_cmd_help(ctx)
        elif isinstance(error, commands.errors.CommandInvokeError):
            self.logger.exception("Exception in command '{}'".format(
                ctx.command.qualified_name), exc_info=error.original)
            oneliner = "Error in command '{}' - {}: {}".format(
                ctx.command.qualified_name, type(error.original).__name__,
                str(error.original))
            await ctx.send(f'`{oneliner}`')
        elif isinstance(error, discord.HTTPException):
                await ctx.send("I need the `Embed links` permission "
                                   "to send this")
        elif isinstance(error, commands.errors.CheckFailure):
            pass
        elif isinstance(error, commands.errors.CommandNotFound):
            pass
        elif isinstance(error, commands.errors.NoPrivateMessage):
            pass
        elif isinstance(error, commands.errors.CommandOnCooldown):
            await ctx.send("{} needs to cool down! Try again in {:.2f}s".format(
                user.mention, float(error.retry_after)), delete_after=5)
        else:
            self.logger.exception(type(error).__name__, exc_info=error)


    # -----------------------------Menu Systems ---------------------------------
    async def menu(self, ctx, embed_list, 
        files=[], message:discord.Message=None, page=0, timeout: int=30):
        def react_check(r, u):
            return u == ctx.author and r.message.id == message.id and str(r.emoji) in expected

        expected = ["➡", "⬅"]
        numbs = {
            "end": ":track_next:",
            "next": "➡",
            "back": "⬅",
            "first": ":track_previous:",
            "exit": "❌"
        }

        embed = embed_list[page]

        if not message:
            message =\
                await ctx.send(embed=embed, files=files)
            if len(embed_list)>1:
                await message.add_reaction("⬅")
                await message.add_reaction("➡")
        else:
            await message.edit(embed=embed, files=files)

        try:
            react = await self.wait_for('reaction_add',
                check=react_check, timeout=timeout
            )
        except asyncio.TimeoutError:
            try:
                await message.clear_reactions()
            except discord.Forbidden:  # cannot remove all reactions
                for emote in expected:
                    await message.remove_reaction(emote, self.user)
            return None

        if react is None:
            try:
                try:
                    await message.clear_reactions()
                except:
                    await message.remove_reaction("⬅", self.user)
                    await message.remove_reaction("➡", self.user)
            except:
                pass
            return None
        reacts = {v: k for k, v in numbs.items()}
        react = reacts[react[0].emoji]
        if react == "next":
            page += 1
            next_page = page % len(embed_list)
            try:
                await message.remove_reaction("➡", ctx.message.author)
            except:
                pass
            return await self.menu(ctx, embed_list, message=message,
                                        page=next_page, timeout=timeout)
        elif react == "back":
            page -= 1
            next_page = page % len(embed_list)
            try:
                await message.remove_reaction("⬅", ctx.message.author)
            except:
                pass
            return await self.menu(ctx, embed_list, message=message,
                                        page=next_page, timeout=timeout)


class HelpFormatter(commands.MinimalHelpCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def help_format(self, ctx, command):
        try:
            self.ctx = ctx
            self.command = command
            user = ctx.message.author
            embed = discord.Embed(colour=user.colour)
            cmd_name = self.command.name
        except:
            return

        desc = ""
        # print(self.command.description, self.command.cog_name, self.command.__dict__)
        # we need a padding of ~80 or so
        """
        if isinstance(self.command, commands.Group):
            description = self.command.description
            if description:
                # <description> portion
                desc += '{}\n'.format(description)"""

        # get subcommands
        cmd_subcommands = []
        if hasattr(self.command, 'commands'):
            for cmd in self.command.commands:
                cmd_subcommands.append(cmd)

        if isinstance(self.command, commands.Group):
            max_width = 70
        else:
            max_width = 40

        if isinstance(self.command, commands.Command):
            # <signature portion>
            signature = self.get_command_signature(self.ctx, self.command)
            if len(signature) < max_width:
                white_space = max_width - len(signature)
            else:
                white_space = len(signature)
            desc += '```{}{}```\n'.format(signature, " "*white_space)

            # <long doc> section
            if self.command.help:
                help_text = self.command.help
                desc += '{}'.format(self.command.help)

            # end it here if it's just a regular command
            if not cmd_subcommands:
                embed.description = await self.pretty_format(desc, cmd_name, ctx=ctx)
                return embed

        # if there are subcommands, the append them to the end
        desc_limit = 40
        desc += "```"
        for sub_command in cmd_subcommands:
            cmd_help = sub_command.help.split("\n")
            cmd_help = cmd_help[0] # doesn't grab any options/examples
            cmd_help = textwrap.fill(cmd_help, desc_limit)
            cmd_help = cmd_help.split('\n')
            for num, line in enumerate(cmd_help):
                if num == 0:
                    desc += "{:<15}{:<25}\n".format(sub_command.name, line)
                else:
                    desc += "{:<15}{:<25}\n".format("", line)
        desc += "```"
        embed.description = await self.pretty_format(desc, cmd_name, ctx=ctx)
        return embed

    def get_command_signature(self, ctx, command):
        return '{0.prefix}{1.qualified_name} {1.signature}'.format(ctx, command)

    async def pretty_format(self, description, cmd_name, ctx = None):
        # replace <> stuff
        if ctx:
            description = description.replace("<USER>", "{}".format(ctx.message.author.name))
        else:
            description = description.replace("<USER>", "Stevy")

        if ctx.invoked_subcommand:
            # print(ctx.command, "/", cmd_name)
            description = description.replace(
                "<COMMAND>", "{}".format(ctx.command))
        else:
            description = description.replace("<COMMAND>", cmd_name)
        description = description.replace(" <OPTIONS>", "")
        description = description.replace("<osu_servers>", 
            ">botinfo for list of supported servers.")
        description = description.replace("+", ">")

        # make everything after [Example] code text
        look_for = "[Example]"
        find_ex = description.find(look_for)
        if find_ex != -1:
            description = list(description)
            description.insert(find_ex + len(look_for) + 1, '`')
            description = ''.join(description)
            description += '`'

        find_block = [m.start() for m in re.finditer('```', description)]
        description = list(description)
        new_desc = ""
        ind = 0
        for ch in description:
            if ind < find_block[0] or ind > find_block[1]:
                if ch == "[":
                    new_desc += "**["
                elif ch == "]":
                    new_desc += "]**"
                elif ch == "(":
                    new_desc += "`("
                elif ch == ")":
                    new_desc += ")`"
                else:
                    new_desc += ch
            else:
                new_desc += ch
            ind+=1

        # do things on the word level
        word_split = new_desc.split(' ')
        final_desc = []
        for word in word_split:
            if '-' in word and '(' not in word and 'Example' not in word:
                final_desc.append('{}'.format(word))
            else:
                final_desc.append('{}'.format(word))
        new_desc = ' '.join(final_desc)

        return new_desc


def set_logger(bot):
    logger = logging.getLogger("bot")
    logger.setLevel(logging.INFO)

    log_format = logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(log_format)
    stdout_handler.setLevel(logging.INFO)
    logger.setLevel(logging.INFO)

    fhandler = logging.handlers.RotatingFileHandler(
        filename='log/bot.log', encoding='utf-8', mode='a',
        maxBytes=10**7, backupCount=5)
    fhandler.setFormatter(log_format)

    logger.addHandler(fhandler)
    logger.addHandler(stdout_handler)

    dpy_logger = logging.getLogger("discord")
    dpy_logger.setLevel(logging.WARNING)
    handler = logging.FileHandler(
        filename='log/discord.log', encoding='utf-8', mode='a')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(module)s %(funcName)s %(lineno)d: '
        '%(message)s',
        datefmt="[%d/%m/%Y %H:%M]"))
    dpy_logger.addHandler(handler)

    return logger


def start_bot(config):
    bot = Bot(config=config, description=config['description'],
        shard_count=config["shard_count"])
    bot.run(config['token'])

if __name__ == '__main__':
    warnings.filterwarnings("ignore")
    config = json.loads(open('config.json').read())

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    start_bot(config)