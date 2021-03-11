import os
import discord
from discord.ext import commands
from discord.utils import find
from random import randint
import asyncio

class Status(commands.Cog):
    """Random things."""

    def __init__(self, bot):
        self.bot = bot

    async def display_status(self):
        while self == self.bot.get_cog('Status'):
            statuses = [
                '>help', '>addbot', '>addbot', 'osu!', 'owo!','with Random things',
                'Dedotated wam', 'with Circles!', 'òwó', 'o~o', '>~<',
                'in {} Servers'.format(len(self.bot.guilds)),
                'with {} Users'.format(str(len(set(self.bot.get_all_members())))),
                'with baskets underwater', '>help', '>help'
            ]
            status = randint(0, len(statuses)-1)
            new_status = statuses[status]
            await self.bot.change_presence(activity=discord.Game(new_status))
            await asyncio.sleep(60)

### ---------------------------- Setup ---------------------------------- ###
def setup(bot):
    n = Status(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(n.display_status())
    bot.add_cog(n)