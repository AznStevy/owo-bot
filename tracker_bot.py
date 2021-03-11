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

import uvloop
import motor.motor_asyncio

import discord
from discord.ext import commands

from cogs.osu.updater import Updater

class TrackerBot(commands.AutoShardedBot):
    def __init__(self, **kwargs):
        # specify intents
        intents = discord.Intents.default()
        intents.members = True

        self.start_time = time.time()

        super().__init__(
            command_prefix='###',
            description=kwargs.pop('description'),
            shard_count=kwargs.pop('shard_count'),
            chunk_guilds_at_startup=False,
            intents=intents
        )

        self.config = kwargs['config']
        self.logger = set_logger(self)
        self.settings = None

        # load database
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(
            port=self.config['database']['primary'],
            connectTimeoutMS=5000, 
            socketTimeoutMS=5000, 
            serverSelectionTimeoutMS=5000)
        self.db = self.db_client[str(self.config['bot_name'])]

        # load cogs
        self.loop.create_task(self.load_updater())

    async def load_updater(self):
        await self.wait_until_ready()
        self.load_extension(f'cogs.osu.updater')

    async def on_ready(self):
        # self.settings = await self.application_info()
        print(f'All {len(self.shards.keys())} tracking shards loaded.')
        elapsed_time = str(time.time() - self.start_time)
        print(f'Took {elapsed_time} seconds.')

    async def on_message(self, message):
        return

    async def process_commands(self, message):
        return

    async def on_command_error(self, ctx, error):
        return

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
    bot = TrackerBot(
        config=config, 
        description=config['description'],
        shard_count=config["shard_count"])
    bot.run(config['token'])

if __name__ == '__main__':
    warnings.filterwarnings("ignore")
    config = json.loads(open('config.json').read())

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    start_bot(config)