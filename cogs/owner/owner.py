import os
import random
import asyncio
import discord
import datetime
import importlib
import collections
import motor.motor_asyncio
from discord.ext import commands
from discord.utils import get

class Owner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.is_owner()
    @commands.command(name = 'reply', no_pm=True)
    async def reply(self, ctx, user_id_channel_id, *, message):
        separate = user_id_channel_id.replace(' ','').split("|")
        channel_id = separate[1]
        user_id = separate[0]
        channel = self.bot.get_channel(int(channel_id))
        server = channel.guild
        user = self.bot.get_user(int(user_id))

        await channel.send(f"**{user.mention}:** `{message}`")

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_guild = True)
    async def unload(self, ctx, *, module: str):
        """Unloads a module

        Example: unload mod"""
        user = ctx.message.author
        if user.id == 91988142223036416:
            module = module.strip()
            if "cogs." not in module:
                module = f"cogs.{module}.{module}"
            if not self._does_cogfile_exist(module):
                await ctx.send("That module file doesn't exist. I will not"
                                   " turn off autoloading at start just in case"
                                   " this isn't supposed to happen.")
            await ctx.send("**Cog unloaded.**")

    @commands.is_owner()
    @commands.command(name="load")
    async def load(self, ctx, module):
        """Reloads a module

        Example: reload audio"""
        user = ctx.message.author
        if "cogs." not in module:
            module = f"cogs.{module}.{module}"

        try:
            self._load_cog(module)
            await ctx.send("**Cog loaded.**")
        except Exception as e:
            print(e)
            await ctx.send("**Load failed.**")

    @commands.is_owner()
    @commands.command(name="reload")
    async def reload(self, ctx, module):
        """Reloads a module

        Example: reload audio"""
        user = ctx.message.author
        if "cogs." not in module:
            module = f"cogs.{module}.{module}"

        try:
            self._unload_cog(module, reloading=True)
            self._load_cog(module)
            await ctx.send("**Cog reloaded.**")
        except Exception as e:
            print(e)
            await ctx.send("**Reload failed.**")

    def _unload_cog(self, cogname, reloading=False):
        #try:
        self.bot.unload_extension(cogname)
        #except:
            #raise CogUnloadError


    def _load_cog(self, cogname):
        mod_obj = importlib.import_module(cogname)
        importlib.reload(mod_obj)
        self.bot.load_extension(mod_obj.__name__)


def setup(bot):
    bot.add_cog(Owner(bot))