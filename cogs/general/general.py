import os
import json
import random
import discord
import datetime
import pyttanko
import collections
import motor.motor_asyncio
from discord.utils import get
from discord.ext import commands
from utils.dataIO import fileIO


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # define database variables
        self.server_settings = self.bot.db["general"]

        client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = client['{}_general'.format(self.bot.config['bot_name'])] # doesn't follow typical structure

        self.remove_commands()


    def remove_commands(self):
        self.bot.remove_command('help')

    """
    @commands.command(pass_context=True)
    async def updatesl(self, ctx, *, command = None):
        user = ctx.message.author
        server = ctx.message.guild

        if user.id != 91988142223036416:
            return

        special_lists = fileIO(
            os.path.join(os.getcwd(), 'database','other','special_lists.json'), "load")
        
        self.bot.blacklist = special_lists['blacklist']
        self.bot.whitelist = special_lists['whitelist']
        print('Whitelist/blacklist updated.')
        """

    @commands.cooldown(1, 2, commands.BucketType.user)
    @commands.command(pass_context=True, name='help', aliases = ["h"])
    async def help(self, ctx, *, command = None):
        """Get a full command list or get info on a certain command.

        [Options]
        command: The name of the command you would like to see

        [Example]
        +<COMMAND> osu
        """
        user = ctx.message.author
        server = ctx.message.guild
        color = 0xffa500

        if not command:
            msg = "Command list for {}:".format(self.bot.user.name)

            em = discord.Embed(description='', color=color)
            em.set_author(name=msg, icon_url = self.bot.user.avatar_url, 
                url = 'https://discord.gg/aNKde73')

            coms = {}
            for com in self.bot.all_commands.keys():
                #try:
                # print(self.bot.all_commands[com].__dict__)
                group_name = str(self.bot.all_commands[com].module).split('.')
                group_name = group_name[2]

                if group_name not in coms.keys():
                    coms[group_name] = []

                if com not in self.bot.all_commands[com].aliases:
                    coms[group_name].append(com)

            final_coms = collections.OrderedDict(sorted(coms.items()))
            desc = ''
            ignore_groups = ['Owner','Misc','Status']
            for group in final_coms:
                cog_name = group.title()
                if cog_name not in ignore_groups:
                    desc += '**{}** - '.format(cog_name.title())

                    final_coms[group].sort()
                    count = 0
                    for com in final_coms[group]:
                        if count == 0:
                            desc += '`{}`'.format(com)
                        else:
                            desc += ' `{}`'.format(com)
                        count += 1
                    desc += "\n"

            em.description = desc
            em.set_footer(text = "Join the owo! Official server: https://discord.gg/aNKde73 | Website: http://owo-bot.xyz/")
            await ctx.send(embed=em)
        else:
            try:
                cmd = self.bot.get_command(command)
                if cmd:
                    ctx.command = cmd
                    await self.bot.send_cmd_help(ctx)
                else:
                    await ctx.send("Couldn't find command! Try again.")
            except:
                await ctx.send("Couldn't find command! Try again.")



    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, 
        name = 'changelog', no_pm=True, aliases = ['updates','cl','changes'])
    async def changelog(self, ctx):
        """
        View changes of the recent bot version

        [Example]
        +<COMMAND>
        """
        # read changelog
        version = '3.5.0'
        color = 0xffa500
        changelog_filepath = os.path.join(
            os.getcwd(), 'cogs', 'general', 'changelog.json')
        with open(changelog_filepath, 'rb') as f:
            changelog = json.load(f)

        version_info = changelog[version]

        em = discord.Embed(description='', colour=color)
        em.set_author(name="Changelog for owo! version {}".format(version), 
            icon_url=self.bot.user.avatar_url)
        em.set_thumbnail(url=self.bot.user.avatar_url)

        for module in version_info:
            module_details = ['▸ {}\n'.format(change) for change in version_info[module]]
            em.add_field(name=module.capitalize(), 
                value=''.join(module_details), inline=False)

        await ctx.send(embed=em)


    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(pass_context=True, name = 'contact', no_pm=True, 
        aliases = ['alert','bother','botherstevy','report'])
    async def contact(self, ctx, *, message):
        """Message Stevy remotely about issues (or if you want to give some compliments). If you use this excessively, you will be blacklisted from the bot.

        [Example]
        +<COMMAND> Your bot sucks. <- this will not get you blacklisted, unfortunately.
        """
        user = ctx.message.author
        server = ctx.message.guild
        user_channel = ctx.message.channel

        channel_id = 810746278324862976 # hardcoded, sorry
        channel = await self.bot.fetch_channel(channel_id)
        # owner = await self.bot.fetch_user(int(self.bot.config["owner"]))

        if len(message) > 300:
            return await ctx.send(":x: **Must be <=300 characters!**")


        desc = "**Channel ID:** `{}`\n**Server ID:** `{}`\n\n```{}```".format(user_channel.id, server.id, message)
        em = discord.Embed(description=desc, colour=user.colour)
        em.set_author(name="{}: {}".format(user.name, user.id), icon_url=server.icon_url)
        em.set_thumbnail(url=user.avatar_url)

        send_msg = await channel.send(embed=em)
        em.set_footer(text = "Message ID: {}".format(send_msg.id))

        await send_msg.edit(embed=em)

        broken_messages = [
            "Don't you have better things to do than to bother Stevy? Sheesh...",
            "Why you gotta be like this man? Sending messages about broken stuff and stuff...",
            "Man, you really wanna get blacklisted don't you? Just kidding, message sent.",
            "Yeah yeah, I get it. Stuff goes wrong blah blah blah Stevy sucks at coding.",
            "Seriously dude, why you gotta break stuff? This is _all_ your fault! Jk, message sent.",
            "Just adding more things to my to-do list, huh? Kidding... message sent."
        ]
        fun_messages = [
            "You and your server have been blacklisted! Just kidding... message sent.",
            "Don't you have better things to do than to bother Stevy? Sheesh...",
            "Yeah yeah, I get it. Stuff goes wrong blah blah blah Stevy sucks at coding.",
            "OK, I sent your message to Stevy, but for a _small_ fee of **1 million credits**!!!",
            "_Sigh_ ok, message sent.", "Why you gotta be like this man? Sending messages and stuff...",
            "Man, you really wanna get blacklisted don't you? Just kidding, message sent."
        ]
        if "broke" in message or (("does" in message or "work" in message) and "not" in message):
            message = random.choice(broken_messages)
        else:
            message = random.choice(fun_messages)

        await ctx.send(f":white_check_mark: **{message}**")


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, name = 'botinfo', no_pm=True, aliases = ['info'])
    async def botinfo(self, ctx):
        """Shows some info about the bot.

        [Example]
        +<COMMAND>
        """

        """
        since = self.bot.start_time.strftime("%Y-%m-%d %H:%M:%S")
        passed = self.get_bot_uptime()
        await ctx.send("**owo! (shard `{}`) has been up for: `{}` (since `{}` UTC)**".format(self.bot.shard_id, passed, since))
        """

        author_repo = "https://github.com/AznStevy"
        instant_invite = "https://discord.gg/aNKde73"
        osu_api_repo = "https://github.com/ppy/osu-api/"
        ripple = "https://ripple.moe/"
        pyttanko_repo = "https://github.com/Francesco149/pyttanko"
        dpy_repo = "https://github.com/Rapptz/discord.py"
        python_url = "https://www.python.org/"
        since = datetime.datetime(2017, 3, 12, 0, 0)
        days_since = (datetime.datetime.utcnow() - since).days
        dpy_version = "[{}]({})".format(discord.__version__, dpy_repo)
        py_version = "[{}.{}.{}]({})".format(*os.sys.version_info[:3],
                                             python_url)
        pyttanko_version = "[{}]({})".format(
            pyttanko.__version__, pyttanko_repo)
        osu_web = "https://osu.ppy.sh/"

        about = "This is owo!, a discord bot created by [Stevy]({}) and made primarily " \
            "for [osu!]({}). To find out more, join the bot server today!: https://discord.gg/aNKde73\n\n" \
            "".format(author_repo, osu_web)

        supported_servers = "Bancho, Ripple, Ripple RX (ripplerx), Gatari, " \
            "Akatsuki, Akatsuki RX (akatsukirx), Droid, Kawata, Ainu, Ainu RX (ainurx), " \
            "Horizon, Horizon RX (horizonrx), Enjuu, Kurikku, Datenshi, " \
            "EZ PP Farm (ezpp), EZ PP Farm RX (ezpprx), EZ PP Farm AP (ezppap), EZ PP Farm v2 (ezppv2)"

        uptime = self.get_bot_uptime(brief=True)

        embed = discord.Embed(colour=discord.Colour.red())
        embed.add_field(name="About owo", value=about, inline=False)
        embed.add_field(name="Bot Version", value='3.5')
        embed.add_field(name="Python", value=py_version)
        embed.add_field(name="discord.py", value=dpy_version)
        embed.add_field(name="Pyttanko", value=pyttanko_version)
        embed.add_field(name="Uptime", value=uptime)
        embed.add_field(name="Total Shards", value=self.bot.shard_count)
        embed.add_field(name="Total Guilds", value=len(self.bot.guilds))
        embed.add_field(name="Supported osu! Servers", value=supported_servers, inline=False)
        embed.set_footer(text="Created on 12 March 2017 (over "
                         "{} days ago!)".format(days_since))
        embed.set_thumbnail(url=self.bot.user.avatar_url)

        await ctx.send(embed=embed)


    def get_bot_uptime(self, *, brief=False):
        now = datetime.datetime.utcnow()
        delta = now - self.bot.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
            else:
                fmt = '{h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h}h {m}m {s}s'
            if days:
                fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True, aliases=['emote'])
    async def emotes(self, ctx, emote_name:str = None):
        """Get emotes of server or image for single emote.

        [Options]
        emote_name: The name of one of your server emotes

        [Example]
        +<COMMAND>
        """
        server = ctx.message.guild
        emotes = ctx.message.guild.emojis
        user = ctx.message.author

        if emote_name == None:
            final_list = [str(emote) for emote in emotes]
            # = "<:{}:{}>".format(emote.name, emote.id)
            #print(emote_str)
            em = discord.Embed(description=' '.join(final_list), colour=user.colour)
            em.set_author(name="Server emotes:", icon_url=server.icon_url)
            em.set_footer(text='Total: {}'.format(len(final_list)))
            return await ctx.send(embed = em)
        else:
            for emote in emotes:
                if emote_name in str(emote):
                    em = discord.Embed(colour=user.colour)
                    em.set_author(name='Name: {}'.format(emote.name), 
                        url=emote.url, icon_url=server.icon_url)
                    em.set_image(url=emote.url)
                    em.set_footer(text='ID: {}'.format(emote.id))
                    return await ctx.send(embed = em)
            return await ctx.send('**Emote not found!**')


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True)
    async def ping(self, ctx):
        """Still ping. You must be really bored.

        [Example]
        +<COMMAND>
        """
        start_time = datetime.datetime.utcnow()
        pong_message = await ctx.send('**Pong!**')
        end_time = datetime.datetime.utcnow()
        delta = end_time - start_time

        new_message = '**Pong! Took: {0:.2f} ms**'.format(delta.microseconds/1000)
        await pong_message.edit(content=new_message)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True)
    async def avatar(self, ctx, user : discord.Member = None):
        """Get the avatar of a user.

        [Options]
        user: User you would like to see the avatar of.

        [Example]
        +<COMMAND>
        """
        author = ctx.message.author
        if not user:
            user = author
        roles = [x.name for x in user.roles if x.name != "@everyone"]
        if not roles: roles = ["None"]
        data = "{}'s Avatar: \n".format(str(user))
        em = discord.Embed(colour=user.colour)
        em.set_author(name = data, url = user.avatar_url)
        em.set_image(url=user.avatar_url)
        await ctx.send(embed = em)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True, aliases=['add','invite','get','bot'])
    async def addbot(self, ctx):
        """Add this bot to your servers. You know you want to!

        [Example]
        +<COMMAND>
        """
        msg = "**Here's my OAUTH2 link:\n{}\nEnjoy!\n\nAlso, come hang out in the [official bot server]({}) or visit the [website]({})!**".format(
            'https://discordapp.com/oauth2/authorize?client_id=289066747443675143&scope=bot&permissions=305187840',
            'https://discord.gg/aNKde73','http://owo-bot.xyz/')
        em = discord.Embed(description=msg, colour=0xeeeeee)
        em.set_thumbnail(url=self.bot.user.avatar_url)
        return await ctx.send(embed = em)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True, aliases=['support'])
    async def donate(self, ctx):
        """Support owo's development! A.k.a throw money at owo so it works better.

        [Example]
        +<COMMAND>
        """
        msg = "**The existence of this bot is made possible by its generous supporters. " \
            "If you'd like to support the development and maintenance of owo," \
            " you can do so __[here]({})__. Thanks! :heart:** -Stevy".format(
            'https://www.patreon.com/stevy')
        em = discord.Embed(description=msg, colour=0xeeeeee)

        # get list of current supporters
        donor_ids = await self.bot.patreon.get_donors_list()
        donor_discord_users = []
        for donor_id in donor_ids:
            user = await self.bot.fetch_user(int(donor_id))
            if user:
                donor_discord_users.append('**{}**#_{}_'.format(
                    user.name, user.discriminator))

        # so not the same ones appearing
        random.shuffle(donor_discord_users)
        donor_discord_users = donor_discord_users[0:20] # truncate

        em.set_thumbnail(url=self.bot.user.avatar_url)
        em.add_field(
            name='Current Supporters ({})'.format(len(donor_discord_users)), 
            value=', '.join(donor_discord_users) + ', ...')

        return await ctx.send(embed = em)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True, aliases=['ui'])
    async def userinfo(self, ctx, *, user: discord.Member=None):
        """Shows a user's information.

        [Options]
        user: User you would like to see info for.

        [Example]
        +<COMMAND>
        """
        author = ctx.message.author
        server = ctx.message.guild

        if not user:
            user = author

        roles = [x.name for x in user.roles if x.name != "@everyone"]

        joined_at = user.joined_at
        current_time = datetime.datetime.now()
        since_created = (current_time - user.created_at).days
        since_joined = (current_time - joined_at).days
        user_joined = joined_at.strftime("%b %d %Y @ %H:%M")
        user_created = user.created_at.strftime("%b %d %Y @ %H:%M")

        created_on = "{} ({} days ago)".format(user_created, since_created)
        joined_on = "{} ({} days ago)".format(user_joined, since_joined)

        game = "User is {}".format(user.status)

        if user.activity is None:
            game = "User is {}".format(user.status)
        else :
            game = "Currently playing {}".format(user.activity.name)

        #else:
            #game = "Currently streaming: [{}]({})".format(user.game, user.game.url)

        if roles:
            roles = sorted(roles, key=[x.name for x in user.roles
                                       if x.name != "@everyone"].index)
            roles = ", ".join(roles)
        else:
            roles = "None"

        data = discord.Embed(description=game, colour=user.colour)
        data.add_field(name="User ID", value=user.id, inline=True)
        data.add_field(name="Nickname", value=user.nick)
        data.add_field(name="Joined Discord on", value=created_on, inline=False)
        data.add_field(name="Joined Server on", value=joined_on, inline=False)
        data.add_field(name="Roles ({})".format(len(roles)-1), value=roles, inline=False)

        if user.avatar_url:
            name = str(user)
            name = " ~ ".join((name, user.nick)) if user.nick else name
            data.set_author(name=name, url=user.avatar_url)
            data.set_thumbnail(url=user.avatar_url)
        else:
            data.set_author(name=user.name)

        return await ctx.send(embed=data)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True, aliases=['si'])
    async def serverinfo(self, ctx):
        """Shows some server information.

        [Example]
        +<COMMAND>
        """

        server = ctx.message.guild
        user = ctx.message.author

        online = len([m.status for m in server.members
                      if m.status == discord.Status.online or
                      m.status == discord.Status.idle])
        total_users = len(server.members)
        text_channels = len([x for x in server.channels
                             if isinstance(x, discord.TextChannel)])
        voice_channels = len(server.channels) - text_channels
        categories = len(server.categories)
        passed = (datetime.datetime.now() - server.created_at).days
        created_at = "Created on {} ({} days ago)".format(
                        server.created_at.strftime("%b %d %Y %H:%M"),passed)
        roles = []
        for role in server.roles:
            if 'everyone' in role.name:
                continue

            roles.append(role.mention)

        colour = user.colour
        data = discord.Embed(description=created_at, colour=colour)
        data.add_field(name="Server ID", value=str(server.id))
        data.add_field(name="Region", value=str(server.region).upper())
        # data.add_field(name="Users", value="{}/{}".format(online, total_users))
        data.add_field(name="Categories", value=categories)
        data.add_field(name="Text Channels", value=text_channels)
        data.add_field(name="Voice Channels", value=voice_channels)
        try:
            data.add_field(name="Owner", value='{}#{}'.format(
                server.owner.name, server.owner.discriminator))
        except:
            pass
        data.add_field(name="Roles ({})".format(len(server.roles)-1), 
            value=', '.join(roles[::-1]), inline=False)
        # data.set_footer(text="Server ID: " + str(server.id))

        if server.icon_url:
            data.set_author(name=server.name, url=server.icon_url)
            data.set_thumbnail(url=server.icon_url)
        else:
            data.set_author(name=server.name)

        try:
            await ctx.send(embed=data)
        except discord.HTTPException:
            await ctx.send(":red_circle: I need the `Embed links` permission "
                               "to send this")


def setup(bot):
    bot.add_cog(General(bot))
