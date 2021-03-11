import os
import copy
import random
import asyncio
import datetime
import collections
from pymongo import MongoClient

import discord
from discord.utils import get
from discord.ext import commands

from utils import checks
from utils.option_parser import OptionParser
class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # define database variables
        self.disabled_commands = self.bot.db["disabled"] # disable commands
        self.prefix_settings = self.bot.db["prefix"] # prefix stuff
        self.general_settings = self.bot.db["general"]
        self.audio_settings = self.bot.db["audio"]
        self.economy_settings = self.bot.db["economy"]
        self.fun_settings = self.bot.db["fun"]
        self.leveler_settings = self.bot.db["leveler"]
        self.osu_settings = self.bot.db["osu"]
        self.streams_settings = self.bot.db["streams"]
        self.utility_settings = self.bot.db["utility"]

    @commands.command(no_pm=True)
    async def overview(self, ctx):
        """Get an overview of the bot settings.

        [Example]
        +<COMMAND>
        """
        server = ctx.message.guild

        em = discord.Embed(colour=ctx.message.author.colour)
        em.set_author(name='Settings overview for {}'.format(server.name), 
            icon_url=server.icon_url)
        em.set_thumbnail(url=server.icon_url)
    
        em.add_field(name="Prefixes", value=await self._display_prefixes(ctx), inline=False)
        # em.add_field(name="Audio", value=await self._display_audio_settings(ctx))
        # em.add_field(name="Economy", value=await self._display_economy_settings(ctx))
        em.add_field(name="Fun", value=await self._display_fun_settings(ctx), inline=False)
        # em.add_field(name="General", value=await self._display_general_settings(ctx))
        # em.add_field(name="Social", value=await self._display_social_settings(ctx))
        em.add_field(name="Osu", value=await self._display_osu_settings(ctx), inline=False)
        # em.add_field(name="Utility", value=await self._display_utility_settings(ctx))
        disabled_commands = await self._display_disabled_commands(ctx)
        if disabled_commands:
            em.add_field(name="Disabled", value=disabled_commands, inline=False)

        return await ctx.send(embed=em)

    async def _display_prefixes(self, ctx):
        prefixes = await self.bot.get_server_prefixes(
            self.bot, ctx.message, prefix_list = True)
        prefixes_copy = copy.deepcopy(prefixes)
        prefixes_copy.insert(0, f"@{self.bot.user.name}")
        return "▸ " + ", ".join([f'`{prefix}`' for prefix in prefixes_copy])

    async def _display_disabled_commands(self, ctx):
        settings = await self.get_settings('disabled', ctx)

        disable_str = ""
        for channel_id in settings:
            if channel_id == "server_id":
                continue

            channel = ctx.message.guild.get_channel(int(channel_id))
            if channel:
                group_str = ''
                if 'group' in settings[channel_id] and settings[channel_id]['group']:
                    group_str = ', '.join([f'`{x}`' for x in settings[channel_id]['group']])
                    group_str = '__Groups__: {} '.format(group_str)

                command_str = ''
                if 'commands' in settings[channel_id] and settings[channel_id]['commands']:
                    command_str = ', '.join([f'`{x}`' for x in settings[channel_id]['commands']])
                    command_str = '__Commands__: {} '.format(command_str)

                if not group_str and not command_str:
                    continue

                disable_str += "▸ `#{}` - {}{}\n".format(channel.name,
                    group_str, command_str)

        return disable_str

    async def _display_general_settings(self, ctx):
        settings = await self.get_settings("general", ctx)
        # print('GENERAL', settings)
        return '`None`'

    async def _display_audio_settings(self, ctx):
        settings = await self.get_settings("audio", ctx)
        # print('AUDIO', settings)
        return '`None`'

    async def _display_economy_settings(self, ctx):
        settings = await self.get_settings("economy", ctx)
        # print('ECONOMY', settings)
        return '`None`'

    async def _display_fun_settings(self, ctx):
        settings = await self.get_settings("fun", ctx)
        # print('FUN', settings)

        prefixless_set = True
        if 'prefixless' in settings:
            prefixless_set = settings['prefixless']

        set_str = ''
        set_str += '▸ Prefixless Easteregg Responses: `{}`'.format(prefixless_set)

        return set_str

    async def _display_social_settings(self, ctx):
        settings = await self.get_settings("leveler", ctx)
        # print('SOCIAL', settings)
        return '`None`'

    async def _display_osu_settings(self, ctx):
        settings = await self.get_settings("osu", ctx)
        # print('OSU', settings)
        process_url = True
        if 'process_url' in settings:
            process_url = settings['process_url']
        beatmap_urls = True
        if 'beatmap_urls' in settings:
            beatmap_urls = settings['beatmap_urls']
        userurl = True
        if 'user_urls' in settings:
            userurl = settings['user_urls'] 
        screenshot = True
        if 'screenshot' in settings:
            screenshot = settings['screenshot']
        replays = True
        if 'replays' in settings:
            replays = settings['replays']  
        beatmap_graph = True
        if 'beatmap_graph' in settings:
            beatmap_graph = settings['beatmap_graph']
        ss_graph = False
        if 'screenshot_graph' in settings:
            ss_graph = settings['screenshot_graph']

        set_str = ''
        set_str += f'▸ Process any implicit messages (master): `{process_url}`\n'
        set_str += f'▸ Process beatmap urls: `{beatmap_urls}`\n'
        set_str += f'▸ Process user urls: `{userurl}`\n'
        set_str += f'▸ Process score screenshots: `{screenshot}`\n'
        set_str += f'▸ Process replays: `{replays}`\n'
        set_str += f'▸ Include beatmap graph on link detection: `{beatmap_graph}`\n'
        set_str += f'▸ Include beatmap graph on screenshot detection: `{ss_graph}`\n'

        return set_str


    async def _display_utility_settings(self, ctx):
        settings = await self.get_settings("utility", ctx)
        print('UTIL', settings)


    @checks.is_admin()
    @commands.command(no_pm=True)
    async def prefix(self, ctx, *options):
        """Set owo's prefixes for the server. Bot mention will always work.

        [Options]
        Add (-a): Add a custom prefix. Will override default. Must add default to include.
        Reset (-r): Reset prefix to global default.
        Info (-i): Display current server prefixes.

        [Example]
        +<COMMAND> -a ~
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        try:
            option_parser = OptionParser()
            option_parser.add_option('a','add', opt_type="str", default=None)
            option_parser.add_option('r','reset', opt_type=None, default=False)
            option_parser.add_option('i','info', opt_type=None, default=False)
            output, options = option_parser.parse(options)
        except:
            await ctx.send(":x: **Please check your option parameters!**")
            return

        server_prefix_settings = await self.get_settings("prefix", ctx)
        if "prefix" not in server_prefix_settings:
            server_prefix_settings["prefix"] = []

        if options["add"] and "" != str(options["add"]):
            server_prefix_settings["prefix"].append(str(options["add"]))
            extra_info = ""
            if len(server_prefix_settings["prefix"]) > 1:
                extra_info = "Current prefixes: `{}`".format(
                    ', '.join(server_prefix_settings["prefix"]))
            await ctx.send(":white_check_mark: **Added prefix: `{}`\n{}**".format(
                options["add"], extra_info))
        elif options["reset"]:
            server_prefix_settings["prefix"] = []
            await ctx.send(":white_check_mark: **Server prefix was set back to default: `{}`**".format(
                ', '.join(self.bot.config["prefix"])))
        else:
            if not server_prefix_settings["prefix"]:
                await ctx.send("**Current server prefix: `{}`**".format(
                    ', '.join(self.bot.config["prefix"])))
            else:
                await ctx.send("**Current server prefix(es): `{}`**".format(
                    ', '.join(server_prefix_settings["prefix"])))
            return

        # update if not info
        await self.prefix_settings.update_one(
            {'server_id':server_prefix_settings["server_id"]},
            {'$set': {"prefix":server_prefix_settings["prefix"]}})


    @checks.is_admin()
    @commands.command()
    async def disable(self, ctx, *options):
        """
        Disable certain commands in certain channels. One command/group at a time.

        [Options]
        All Channels (-a): Disable command for the entire server. Forced disable.
        Exclusive Channel (-ec): Enable a command/group on a specific channel. Forced disable.
        Group (-g): Toggle an entire command group.
        Reset (-r): Clear all disabled commands from the server.

        [Example]
        +<COMMAND> -g "osu" -ec osuplays
        """

        channel = ctx.message.channel
        server = ctx.message.guild
        disabled_commands = await self.get_settings("disabled", ctx)

        option_parser = OptionParser()
        option_parser.add_option('a',   'all',          opt_type=None,  default=False)
        option_parser.add_option('ec',  'exclusive',    opt_type=None, default=None)
        option_parser.add_option('g',   'group',        opt_type="str", default=None)
        option_parser.add_option('r',   'reset',        opt_type=None,  default=False)
        user_command, options = option_parser.parse(options)


        if not user_command:
            return await ctx.send("**Please indicate the command to disable!**")

        # if reset
        if options["reset"]:
            for channel_id in disabled_commands.keys():
                # print(channel_id)
                channel_id = str(channel_id)

                if channel_id == 'server_id':
                    continue

                disabled_commands[channel_id]["group"] = []
                disabled_commands[channel_id]["commands"] = []

            await self.disabled_commands.replace_one(
                {"server_id":str(server.id)}, disabled_commands)

            # check
            disabled_commands = await self.get_settings("disabled", ctx)

            return await ctx.send(":white_check_mark: **All commands enabled.**")

        # handle which channels
        # try:
        if options["all"]:
            channels = [str(ch.id) for ch in server.channels]
            channel_name = "entire server"
            force_disable = True
        elif options["exclusive"]:
            channels = [str(ch.id) for ch in server.channels]
            if str(channel.id) in channels:
                channels.remove(str(channel.id))
            channel_name = "all except {}".format(channel.name)
            force_disable = True
        else:
            channel_name = channel.name
            channels = [str(channel.id)]
            force_disable = False
        # except commands.CommandError:
            # return await ctx.send(":x: **Please check your parameters!**")

        # handle the function within each channel
        for channel in channels:
            # print('current channel ', channel)
            # handle command or command group
            if channel not in disabled_commands.keys():
                disabled_commands[channel] = {
                    "group": [], "commands": []
                }

            is_disable = False
            if options["group"]:
                group_name = await self.group_exists(options["group"])
                output_name = group_name
                if not group_name:
                    print('Group not found')
                    return await ctx.send(":x: **That command group doesn't exist/can't be silenced.**")

                if "group" not in disabled_commands[channel].keys():
                    disabled_commands[channel]["group"] = []

                if group_name not in disabled_commands[channel]["group"] or force_disable:
                    is_disable = True
                    disabled_commands[channel]["group"].append(group_name)
                    disabled_commands[channel]["group"] = \
                        list(set(disabled_commands[channel]["group"]))
                else:
                    if group_name in disabled_commands[channel]["group"]:
                        disabled_commands[channel]["group"].remove(group_name)
            else:
                print('user command', user_command)

                command_name = await self.command_exists(user_command[0])
                output_name = command_name
                if not command_name:
                    print('Command not found.')
                    return await ctx.send(":x: **That command doesn't exist/can't be silenced.**")

                if "commands" not in disabled_commands[channel].keys():
                    disabled_commands[channel]["commands"] = []

                if command_name not in disabled_commands[channel]["commands"] or force_disable:
                    is_disable = True
                    disabled_commands[channel]["commands"].append(command_name)
                    disabled_commands[channel]["commands"] = \
                        list(set(disabled_commands[channel]["commands"]))
                else:
                    if command_name in disabled_commands[channel]["commands"]:
                        disabled_commands[channel]["commands"].remove(command_name)

        # update database
        await self.disabled_commands.replace_one(
            {"server_id":str(server.id)}, disabled_commands)

        # check
        disabled_commands = await self.get_settings("disabled", ctx)
        # print('test', disabled_commands)

        # output
        if is_disable:
            if options["group"]:
                return await ctx.send(":white_check_mark: **Disabled `{}` group on `{}`.**".format(
                    group_name, channel_name))
            return await ctx.send(":white_check_mark: **Disabled `{}` on `{}`.**".format(
                output_name, channel_name))
        else:
            if options["group"]:
                return await ctx.send(":white_check_mark: **Enabled `{}` group on `{}`.**".format(
                    group_name, channel_name))
            return await ctx.send(":white_check_mark: **Enabled `{}` on `{}`.**".format(
                output_name, channel_name))


    async def group_exists(self, group:str):
        groups = []
        for com in self.bot.all_commands.keys():
            group_name = str(self.bot.all_commands[com].module).split('.')
            group_name = group_name[2]
            groups.append(group_name)

        groups = list(set(groups))
        try_remove = ["owner", "misc", "settings"]
        for trm in try_remove:
            try:
                groups.remove(trm)
            except:
                pass

        if group in groups:
            return group.lower()
        else:
            return None


    async def command_exists(self, command:str):
        try:
            # find the correct command
            no_disable = ["overview", "set"]
            if any([cmd in command for cmd in no_disable]):
                return None

            split_command = command.split(" ")
            user_command = split_command[0]
            sub_command = None
            if len(split_command) > 1:
                user_command = split_command[0]
                sub_command = split_command[1]
            bot_command = self.bot.all_commands[user_command.lower()]
            if isinstance(bot_command, commands.Group) and sub_command:
                return "{} {}".format(
                    str(bot_command).lower(), str(sub_command).lower())
                cmd_str = str(bot_command.get_command(sub_command).name)
            else:
                cmd_str = str(bot_command)
            return cmd_str
        except Exception as e:
            return None

    # ---------------------------------------------------------------
    @checks.is_admin()
    @commands.group()
    async def audioadmin(self, ctx):
        """Define audio settings"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @audioadmin.command(name = "add", no_pm=True)
    async def add_audio_admin(self, ctx, *options):
        """
        Add someone to the DJ list. They will be able to pause, skip, change volume, and stop the player at any time.

        [Options]
        user: Add a single user to be a DJ
        Role (-r): Add an entire role to be a DJ.

        [Example]
        +<COMMAND> <USER>
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("audio", ctx)
        attr_name = f"dj_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []
        server_settings[attr_name].append(attr_id)
        server_settings[attr_name] = list(set(server_settings[attr_name]))
        await ctx.send(":white_check_mark: **{} added to DJ list.**".format(list_type.title()))
        await self.audio_settings.update_one(
            {'server_id':server_settings["server_id"]},
            {'$set': {attr_name:server_settings[attr_name]}})
        # print(server_settings)

    @audioadmin.command(name = "remove", no_pm=True)
    async def remove_audio_admin(self, ctx, *options):
        """
        Remove someone from the DJ list.
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("audio", ctx)
        attr_name = f"dj_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []

        # check if that thing to remove exists
        if attr_id in server_settings[attr_name]:
            server_settings[attr_name].remove(attr_id)
            await self.audio_settings.update_one(
                {'server_id':server_settings["server_id"]},
                {'$set': {attr_name:server_settings[attr_name]}})
            if list_type == "role":
                await ctx.send(":white_check_mark: **DJ role has been removed.**")
            else:
                await ctx.send(":white_check_mark: **DJ has been removed.**")
        else:
            if list_type == "role":
                await ctx.send(":x: **That role either does not exist or does not have DJ status.**")
            else:
                await ctx.send(":x: **That member either does not exist or is not a DJ.**")
        # print(server_settings)

    @audioadmin.command(name = "dispnp", no_pm=True)
    async def disp_now_playing(self, ctx, toggle=None):
        """
        Toggle the now playing message.
        """
        server_settings = await self.get_settings("audio", ctx)
        attr_name = "disp_np"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = True
        server_settings[attr_name] = not server_settings[attr_name]
        await self.audio_settings.update_one(
            {'server_id':server_settings["server_id"]},
            {'$set': {attr_name:server_settings[attr_name]}})
        if server_settings[attr_name]:
            on_off = "on"
        else:
            on_off = "off"
        await ctx.send(f":white_check_mark: **Now playing messages turned `{on_off}`**")

    @audioadmin.command(name = "locknp", no_pm=True)
    async def lock_now_playing(self, ctx, channel):
        """
        Lock the now playing message to a single channel.
        """

        server_settings = await self.get_settings("audio", ctx)
        attr_name = "lock_np"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = None

        # test if channel exists
        try:
            channel = await commands.ChannelConverter().convert(ctx, output)
        except commands.CommandError:
            await ctx.send(":x: **That channel doesn't exist!**")
            return

        server_settings[attr_name] = str(channel.id)
        await self.audio_settings.update_one(
            {'server_id':server_settings["server_id"]},
            {'$set': {attr_name:server_settings[attr_name]}})
        await ctx.send(f":white_check_mark: **Now playing messages locked to `#{channel.name}`**")

    # ------------------- fun --------------------------
    @checks.is_mod()
    @commands.group()
    async def funadmin(self, ctx):
        """Define user settings"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return


    @funadmin.command(name = "prefixless", no_pm=True)
    async def prefixless(self, ctx, *options):
        """Toggle prefixless eastereggs.

        [Options]
        All Channels (-a): Disable command for the entire server.
        Channel (-c): Toggle a command on a certain channel.
        Exclusive Channel (-ec): Enable a command/group on a specific channel.
        Group (-g): Toggle an entire command group.
        Reset (-r): Clear all disabled commands from the server.

        [Example]
        +<COMMAND>
        """
        db_name = "fun"
        setting_name = "prefixless"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    # ----------------- osu ---------------------
    @checks.is_admin()
    @commands.group()
    async def osuadmin(self, ctx):
        """Define user settings"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return


    # @osuadmin.command(name = "add", no_pm=True)
    async def add_osu_track_admin(self, ctx, *options):
        """Add osu track admin. Can add and remove useres from tracking. Limit 5.

        [Options]
        user: Add a single user to be tracking admin.
        Role (-r): Add an entire role to be tracking admin.

        [Example]
        +<COMMAND> <USER>
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("osu", ctx)
        attr_name = f"track_admin_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []
        server_settings[attr_name].append(attr_id)
        server_settings[attr_name] = list(set(server_settings[attr_name]))
        await ctx.send(":white_check_mark: **{} added to tracking admin list.**".format(list_type.title()))
        await self.osu_settings.update_one(
            {'server_id':server_settings["server_id"]},
            {'$set': {attr_name:server_settings[attr_name]}})


    # @osuadmin.command(name = "remove", no_pm=True)
    async def remove_osu_track_admin(self, ctx, *options):
        """Remove osu track admin.

        [Options]
        user: Add a single user to be tracking admin.
        Role (-r): Add an entire role to be tracking admin.

        [Example]
        +<COMMAND> <USER>
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("osu", ctx)
        attr_name = f"track_admin_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []

        # check if that thing to remove exists
        if attr_id in server_settings[attr_name]:
            server_settings[attr_name].remove(attr_id)
            await self.osu_settings.update_one(
                {'server_id':server_settings["server_id"]},
                {'$set': {attr_name:server_settings[attr_name]}})
            if list_type == "role":
                await ctx.send(":white_check_mark: **Tracking admin role has been removed.**")
            else:
                await ctx.send(":white_check_mark: **Tracking admin has been removed.**")
        else:
            if list_type == "role":
                await ctx.send(":x: **That role either does not exist or does not have tracking admin status.**")
            else:
                await ctx.send(":x: **That member either does not exist or is not a tracking admin.**")


    # @osuadmin.command(no_pm=True)
    async def api(self, ctx, api_name):
        """Change the default server api. May result in buggy commands.

        [Options]
        api_name: <osu_servers>

        [Example]
        +<COMMAND> ripple
        """
        valid_apis = ["official", "gatari", "ripple","akatsuki","akatsukirx"]
        pass


    @osuadmin.command(no_pm=True)
    async def implicit(self, ctx):
        """Toggle all osu-related implicit commands.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "process_url"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @osuadmin.command(no_pm=True)
    async def beatmapgraph(self, ctx):
        """Toggle if the graph appears in the beatmap embed.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "beatmap_graph"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @osuadmin.command(no_pm=True)
    async def ssgraph(self, ctx):
        """Toggle if the graph appears in the beatmap embed.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "screenshot_graph"
        settings = await self.get_settings(db_name, ctx)
        default_value = False
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @osuadmin.command(no_pm=True)
    async def beatmapurl(self, ctx):
        """Toggle if a beatmap embed appears after user posts a link.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "beatmap_urls"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @commands.has_permissions(manage_guild = True)
    @osuadmin.command(no_pm=True)
    async def screenshot(self, ctx):
        """Toggle if the bot should try to find the map based on a screenshot.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "screenshot"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    # @commands.has_permissions(manage_guild = True)
    # @osuadmin.command(no_pm=True)
    async def youtube(self, ctx):
        """Toggle if the bot should try to find the map based on a screenshot.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "youtube"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @osuadmin.command(no_pm=True)
    async def replays(self, ctx):
        """Toggle if the graph appears in the beatmap embed.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "replays"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    @osuadmin.command(no_pm=True)
    async def userurl(self, ctx):
        """Toggle if the graph appears in the beatmap embed.

        [Example]
        +<COMMAND>
        """
        db_name = "osu"
        setting_name = "user_urls"
        settings = await self.get_settings(db_name, ctx)
        default_value = True
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)


    async def _handle_option(self, key_name, server_id):
        server_options = db.options.find_one({"server_id":server_id})
        if server_options is None:
            server_options = {
                "server_id": server_id,
                "graph_beatmap": True,
                "graph_screenshot": False,
                "beatmap": True,
                "screenshot": True,
                "api": self.osu_settings["type"]["default"]
            }
            server_options[key_name] = not server_options[key_name]
            db.options.insert_one(server_options)
        else:
            server_options[key_name] = not server_options[key_name]
            db.options.update_one({"server_id":server_id}, {
                '$set':{key_name: server_options[key_name]
                }})

        return server_options[key_name]

    # --------------------------------- leveler ------------------------------
    @checks.is_admin()
    @commands.group()
    async def lvladmin(self, ctx):
        """Level settings."""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return


    @lvladmin.command(name="addbadgead", no_pm=True)
    async def add_badgeadmin(self, ctx, *options):
        """Add a badge admin. This person can create, remove, and give badges.

        [Options]
        user: Person to whom you want to give badge admin permissions.
        Role (-r): Add a role that can add badges.

        [Example]
        +<COMMAND> -r "Cool People"
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("leveler", ctx)
        attr_name = f"badge_admin_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []
        server_settings[attr_name].append(attr_id)
        server_settings[attr_name] = list(set(server_settings[attr_name]))
        await self.leveler_settings.update_one(
            {'server_id':server_settings["server_id"]},
            {'$set': {attr_name:server_settings[attr_name]}})


    @lvladmin.command(name="removebadgead", no_pm=True)
    async def remove_badgeadmin(self, ctx, *options):
        """Remove a badge admin.

        [Options]
        user: Person to whom you want to give badge admin permissions.
        Role (-r): Remove a role that can add badges.

        [Example]
        +<COMMAND> -r "Cool People"
        """
        if not options:
            await self.bot.send_cmd_help(ctx)
            return

        option_parser = OptionParser()
        option_parser.add_option('r','role', opt_type="str", default=None)
        output, options = option_parser.parse(options)
        list_type, attr_id = await self.determine_special_rm(ctx, output, options)

        if not list_type or not attr_id:
            return await ctx.send(":x: **Please check your command.**")

        server_settings = await self.get_settings("osu", ctx)
        attr_name = f"badge_admin_{list_type}"
        if attr_name not in server_settings.keys():
            server_settings[attr_name] = []

        # check if that thing to remove exists
        if attr_id in server_settings[attr_name]:
            server_settings[attr_name].remove(attr_id)
            await self.leveler_settings.update_one(
                {'server_id':server_settings["server_id"]},
                {'$set': {attr_name:server_settings[attr_name]}})
            if list_type == "role":
                await ctx.send(":white_check_mark: **Tracking admin role has been removed.**")
            else:
                await ctx.send(":white_check_mark: **Tracking admin has been removed.**")
        else:
            if list_type == "role":
                await ctx.send(":x: **That role either does not exist or does not have tracking admin status.**")
            else:
                await ctx.send(":x: **That member either does not exist or is not a tracking admin.**")


    @lvladmin.command(name="lock", no_pm=True)
    async def lvlmsglock(self, ctx, channel:str=None):
        """Locks levelup messages to one channel. Disable command via locked channel.

        [Options]
        channel: Name of channel. Default is current channel.

        [Example]
        +<COMMAND> botspam
        """
        db_name = "leveler"
        setting_name = "lock_channel"
        settings = await self.get_settings(db_name, ctx)
        if not channel:
            channel = ctx.message.channel
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, channel)
            except:
                return await ctx.send(":x: **That channel doesn't exist!**")

        # handle values
        channel_id = str(channel.id)
        channel_name = channel.name

        if setting_name in settings.keys():
            if settings[setting_name] == channel_id:
                setting_val = None
            else:
                setting_val = channel_id
        else:
            # could potentially do something else here...
            setting_val = channel_id

        await self.update_setting(ctx, db_name, setting_name, setting_val)
        #print(await self.get_settings(db_name, ctx))

        # print updated
        if setting_val:
            return await ctx.send(f":white_check_mark: **Level-up messages locked to `{channel_name}`.**")
        else:
            return await ctx.send(":white_check_mark: **Level-up message no longer locked to a channel.**")


    @lvladmin.command(name="exclude", no_pm=True)
    async def lvlexclude(self, ctx, channel:str=None):
        """Exclude a certain channel from gaining exp.

        [Options]
        channel: Name of channel. Default is current channel.

        [Example]
        +<COMMAND> botspam
        """
        if not channel:
            channel = ctx.message.channel
        else:
            try:
                channel = await commands.TextChannelConverter().convert(ctx, channel)
            except:
                return await ctx.send(":x: **That channel doesn't exist!**")

        db_name = "leveler"
        setting_name = "exclude_channel"
        settings = await self.get_settings(db_name, ctx)
        default_value = []
        array_val = str(channel.id)
        is_remove = await self.handle_array_toggle(ctx, db_name, settings, setting_name, array_val,
            default=default_value)
        #print(await self.get_settings(db_name, ctx))

        if is_remove:
            return await ctx.send(f":white_check_mark: **`#{channel.name}` has been included in exp gain.**")
        else:
            return await ctx.send(f":white_check_mark: **`#{channel.name}` has been excluded in exp gain.**")


    @lvladmin.command(name="lvluptoggle", no_pm=True)
    async def lvluptoggle(self, ctx):
        """Toggle levelup messages on the server.

        [Example]
        +<COMMAND>
        """
        db_name = "leveler"
        setting_name = "lvlup_alert"
        settings = await self.get_settings(db_name, ctx)
        default_value = True

        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value) # prints automatically
        # print(await self.get_settings(db_name, ctx))


    @lvladmin.command(name="private", no_pm=True)
    async def lvlupprivate(self, ctx):
        """Toggle levelup messages on the server to be private message.

        [Example]
        +<COMMAND>
        """
        db_name = "leveler"
        setting_name = "private"
        settings = await self.get_settings(db_name, ctx)
        default_value = False
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)
        #print(await self.get_settings(db_name, ctx))


    @lvladmin.command(no_pm=True)
    async def textonly(self, ctx, all:str=None):
        """Toggle text-based messages on the server.

        [Example]
        +<COMMAND>
        """
        db_name = "leveler"
        setting_name = "text_only"
        settings = await self.get_settings(db_name, ctx)
        default_value = False
        await self.handle_toggle(ctx, db_name, settings, setting_name,
            default=default_value)
        #print(await self.get_settings(db_name, ctx))

    # -------------------------------------------------------------------
    async def update_setting(self, ctx, db_name, setting_name, setting_value):
        server = ctx.message.guild

        db_name = db_name.lower()
        db_names = ["global", "general", "audio",
                "osu", "economy", "fun", "leveler",
                "streams", "utility", "prefix", "disabled"]
        if not any([x == db_name for x in db_names]):
            return None

        cog_db = self.bot.db[db_name]
        settings = await self.get_settings(db_name, ctx)
        
        if db_name not in self.bot.cached_settings[str(server.id)].keys():
            self.bot.cached_settings[str(server.id)][db_name] = {}
        self.bot.cached_settings[str(server.id)][db_name][setting_name] = setting_value
        
        await cog_db.update_one({"server_id":str(server.id)},
            {'$set':{setting_name:setting_value}})

    async def get_settings(self, db_name, ctx):
        server = ctx.message.guild

        db_name = db_name.lower()
        db_names = ["global", "general", "audio",
                "osu", "economy", "fun", "leveler",
                "streams", "utility", "prefix", "disabled"]
        # double check
        if not any([x == db_name for x in db_names]):
            return None

        if str(server.id) in self.bot.cached_settings.keys() and \
            db_name in self.bot.cached_settings[str(server.id)].keys():
            del self.bot.cached_settings[str(server.id)][db_name]

        server = ctx.message.guild
        cog_db = self.bot.db[db_name]
        server_settings = await cog_db.find_one({"server_id":str(server.id)})
        if not server_settings:
            await cog_db.insert_one({"server_id":str(server.id)})
            server_settings = await cog_db.find_one({"server_id":str(server.id)})

        settings_copy = copy.deepcopy(server_settings)
        del settings_copy['_id']

        return settings_copy

    async def determine_special_rm(self, ctx, output, options):
        if options["role"]: # if role
            try:
                role = await commands.RoleConverter().convert(ctx, options["role"])
            except commands.CommandError:
                await ctx.send(":x: **That role doesn't exist!**")
                return None, None
            list_type = "role"
            attr_id = str(role.id)
        else: # if user
            try:
                member = await commands.MemberConverter().convert(ctx, output)
            except commands.CommandError:
                await ctx.send(":x: **That user doesn't exist!**")
                return None, None
            list_type = "member"
            attr_id = str(member.id)
        return (list_type, attr_id)

    async def handle_toggle(self, ctx, db_name, settings, setting_name, default=True):
        # get correct value
        if setting_name in settings.keys():
            setting_val = not settings[setting_name]
        else:
            setting_val = not default

        await self.update_setting(ctx, db_name, setting_name, setting_val)

        # print out result
        name = setting_name.replace("_", " ")
        if setting_val:
            return await ctx.send(f":white_check_mark: **`{name}` has been `enabled`.**")
        else:
            return await ctx.send(f":white_check_mark: **`{name}` has been `disabled`.**")

    async def handle_array_toggle(self, ctx, db_name, settings, setting_name, array_val, default=[]):
        is_remove = False
        # get correct value
        if setting_name in settings.keys():
            if not isinstance(settings[setting_name], list):
                return None

            setting_val = settings[setting_name]
            if array_val in setting_val:
                is_remove = True
                setting_val.remove(array_val)
            else:
                setting_val.append(array_val)
        else:
            setting_val = default
            setting_val.append(array_val)
        await self.update_setting(ctx, db_name, setting_name, setting_val)
        return is_remove

def setup(bot):
    bot.add_cog(Settings(bot))