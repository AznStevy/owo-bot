import os
import math
import time
import urllib
import discord
import asyncio
import aiohttp
import datetime
import operator
import collections
from PIL import Image
from random import choice
from random import randint
import motor.motor_asyncio
from discord.ext import commands
from discord.utils import get
from utils.dataIO import fileIO
from googletrans import Translator
from urllib.parse import quote_plus
from utils.option_parser import OptionParser
from utils.chat_formatting import escape_mass_mentions, italics, pagify


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # define database variables
        self.server_settings = self.bot.db["utility"] # bot settings for utility
        client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = client['{}_utility'.format(self.bot.config['bot_name'])] # doesn't follow typical structure
        self.api_keys = fileIO("config.json", "load")["API_KEYS"]
        self.WOLFRAM_API_KEY = self.api_keys['WOLFRAM_API_KEY']
        self.poll_sessions = []
        self.stopwatches = {}

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True)
    async def roll(self, ctx, dice_num:str='6'):
        """Rolls random number between 1 and user's choice. Defaults to 100.

        [Options]
        dice_num: Number of faces on your dice.

        [Example]
        +<COMMAND> 727
        """
        author = ctx.message.author
        if dice_num.isdigit():
            number = int(dice_num)
        else:
            number = 6

        if number > 1:
            n = randint(1, number)
            await ctx.send("{} :game_die: {} :game_die:".format(author.mention, n))
        else:
            await ctx.send("{} Maybe higher than 1? ;P".format(author.mention))

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command()
    async def crypto(self, ctx, ticker:str):
        """Get info on a specific coin.

        [Options]
        ticker: Ticker of the coin.

        [Example]
        +<COMMAND> btc
        """
        user = ctx.message.author
        url = "https://min-api.cryptocompare.com/data/price?fsym={}&tsyms=USD,EUR".format(ticker.upper())
        # url = "https://api.coinmarketcap.com/v2/ticker/1/"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                result = await r.json()

                em = discord.Embed(colour=user.colour)
                desc = ""
                for value in result.keys():
                    desc += "{}: `{:,}`\n".format(value, result[value])
                full_url = f"https://www.cryptocompare.com/coins/{ticker.lower()}/overview/"
                em.set_author(name=f"{ticker.upper()}", url=full_url)
                em.description = desc
                em.set_footer(text="Data from https://cryptocompare.com/")
                await ctx.send(embed = em)
                return

        await ctx.send("**Error. Try again later.**")


    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command()
    async def lmgtfy(self, ctx, *, search_terms : str):
        """Creates a lmgtfy link.

        [Options]
        search_terms: The things you want it to show you how to look up...

        [Example]
        +<COMMAND> How do I add owo! bot to my server?
        """
        search_terms = escape_mass_mentions(search_terms.replace(" ", "+"))
        await ctx.send("https://lmgtfy.com/?q={}".format(search_terms))

    @commands.cooldown(1, 1, commands.BucketType.user)
    @commands.command(aliases=["sw"])
    async def stopwatch(self, ctx):
        """Stars/stops a stopwatch

        [Example]
        +<COMMAND>
        """
        author = ctx.message.author
        if not author.id in self.stopwatches:
            self.stopwatches[author.id] = int(time.perf_counter())
            await ctx.send(author.mention + " Stopwatch started!")
        else:
            tmp = abs(self.stopwatches[author.id] - int(time.perf_counter()))
            tmp = str(datetime.timedelta(seconds=tmp))
            await ctx.send(author.mention + " Stopwatch stopped! Time: **" + tmp + "**")
            self.stopwatches.pop(author.id, None)

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(aliases=["tr"])
    async def translate(self, ctx, *, text):
        """Translates text into something else. To english by default.

        [Options]
        From (-f): Language you're starting from.
        To (-t): Language you want it in.

        [Example]
        +<COMMAND> わたしは　にほんごがすこししか　はなせません。
        """
        return await ctx.send(":red_circle: **Sorry, currently unavailable.**")
        user = ctx.message.author

        text, options = self._get_translate_options(text)

        translator = Translator()
        tr_text = translator.translate(text)
        await ctx.send("**{}**: `{}`".format(user.display_name, tr_text.text))

    def _get_translate_options(self, text):
        return text, None

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases=["ud"])
    async def urban(self, ctx, *, search_terms : str, definition_number : int=1):
        """Get an urban dictionary definition of a word. I'm sure this will be good.

        [Options]
        search_terms: The words you want a definition to.
        definition_number: The definition number (int)

        [Example]
        +<COMMAND> cookiezi 1
        """
        user = ctx.message.author
        def encode(s):
            return quote_plus(s, encoding='utf-8', errors='replace')

        original_search = search_terms
        search_terms = search_terms.split(" ")
        try:
            if len(search_terms) > 1:
                pos = int(search_terms[-1]) - 1
                search_terms = search_terms[:-1]
            else:
                pos = 0
            if pos not in range(0, 11): # API only provides the
                pos = 0                 # top 10 definitions
        except ValueError:
            pos = 0

        search_terms = "+".join([encode(s) for s in search_terms])
        url = "http://api.urbandictionary.com/v0/define?term=" + search_terms
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    result = await r.json()
            if result["list"]:
                definition = result['list'][pos]['definition']
                example = result['list'][pos]['example']
                defs = len(result['list'])
                msg = ("**__Definition #{} of {}:__\n**{}\n\n"
                       "**__Example:__\n**{}".format(pos+1, defs, definition,
                                                 example))
                msg = pagify(msg, ["\n"])
                urban_icon = "http://i.imgur.com/nWfKsAS.png"
                counter = 1
                for page in msg:
                    em = discord.Embed(description=page, colour=user.colour)
                    em.set_author(name="{}".format(original_search).capitalize(), icon_url = urban_icon)
                    em.set_footer(text="Page {}".format(str(counter)))
                    await ctx.send(embed = em)
                    if counter >= 3:
                        break
                    counter += 1
            else:
                await ctx.send("Your search terms gave no results.")
        except IndexError:
            await ctx.send("There is no definition #{}".format(pos+1))
        except:
            await ctx.send("Error.")

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(pass_context=True)
    async def flip(self, ctx, user : discord.Member=None):
        """Flip a coin or a user.

        [Options]
        user: The user you would like to flip.

        [Example]
        +<COMMAND> <USER>
        """
        if user != None:
            msg = ""
            if user.id == self.bot.user.id:
                user = ctx.message.author
                msg = "Nice try. You think this is funny? How about *this* instead:\n\n"
            char = "abcdefghijklmnopqrstuvwxyz"
            tran = "ɐqɔpǝɟƃɥᴉɾʞlɯuodbɹsʇnʌʍxʎz"
            table = str.maketrans(char, tran)
            name = user.display_name.translate(table)
            char = char.upper()
            tran = "∀qƆpƎℲפHIſʞ˥WNOԀQᴚS┴∩ΛMX⅄Z"
            table = str.maketrans(char, tran)
            name = name.translate(table)
            await ctx.send("(╯°□°）╯︵ {}".format(name[::-1]))
        else:
            msg = await ctx.send("**Flips a coin and...**")
            await asyncio.sleep(1)
            await msg.edit(content="_**Flips a coin and... " + choice(["HEADS!**_", "TAILS!**_"]))

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command()
    async def choose(self, ctx, *choices):
        """Chooses between multiple choices.

        [Options]
        choises: The different choices. To denote multiple choices, you should use double quotes.

        [Example]
        +<COMMAND> Pizza Banana "Apple Pie" "Something else"
        """
        if len(choices) < 2:
            await ctx.send('Not enough choices to pick from.')
        else:
            await ctx.send(escape_mass_mentions(choice(choices)))

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(pass_context=True, no_pm=True)
    async def poll(self, ctx, *choices):
        """Start/stop a poll between multiple choices

        [Options]
        choises: The different choices. Separate using semi-colons.

        [Example]
        +<COMMAND> Question?;Banana;Apple Pie;Something else
        """
        message = ctx.message
        if len(choices) == 1:
            if choices[0].lower() == "stop":
                await self.endpoll(message)
                return
        if not self.getPollByChannel(message):
            check = " ".join(choices).lower()
            if "@everyone" in check or "@here" in check:
                await ctx.send("Nice try.")
                return
            p = NewPoll(message, self)
            if p.valid:
                self.poll_sessions.append(p)
                await p.start()
            else:
                await self.bot.send_cmd_help(ctx)
        else:
            await ctx.send("**A poll is already ongoing in this channel.**")

    async def endpoll(self, message):
        if self.getPollByChannel(message):
            p = self.getPollByChannel(message)
            if p.author == message.author.id: # or isMemberAdmin(message)
                await self.getPollByChannel(message).endPoll()
            else:
                await ctx.send("Only admins and the author can stop the poll.")
        else:
            await ctx.send("There's no poll ongoing in this channel.")

    def getPollByChannel(self, message):
        for poll in self.poll_sessions:
            if poll.channel == message.channel:
                return poll
        return False

    async def check_poll_votes(self, message):
        if message.author.id != self.bot.user.id:
            if self.getPollByChannel(message):
                    self.getPollByChannel(message).checkAnswer(message)

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def anime(self, ctx, *media_name):
        """Find an anime, manga, whatever you like.

        [Options]
        Manga (-m): If the media is a manga
        User (-u): If the search is a user

        [Example]
        +<COMMAND> Made in Abyss
        """
        user = ctx.message.author
        option_parser = OptionParser()
        option_parser.add_option('m','manga', opt_type=None, default=False)
        option_parser.add_option('u','user', opt_type=None, default=False)
        media_name, options = option_parser.parse(media_name)
        media_name = str(media_name)

        media_type = "anime"
        if options["manga"]:
            media_type = "manga"
        elif options["user"]:
            media_type = "user"

        try:
            top_result = await self._get_anime_search(media_type, media_name)
            if top_result:
                em = await self._create_anime_embed(media_type, top_result, user.colour)
                await ctx.send(embed = em)
            else:
                await ctx.send(f":red_circle: **{media_name} {media_type} was not found!**")
        except:
            return await ctx.send(f":red_circle: **No results!**")

    async def _create_anime_embed(self, media_type, result, color):
        # print(result)

        em = discord.Embed(colour=color)
        em.set_author(name="{}".format(result['title']), url=result['url'])
        em.add_field(name="Synopsis", value=result["synopsis"])
        #misc = ""
        #misc += "Rated: {}".format(result['rated'])
        #em.add_field(name="Misc", value=misc)
        em.set_thumbnail(url=result["image_url"])
        return em

    async def _get_anime_search(self, media_type, media_name):
        # returns top result and image url
        query = urllib.parse.quote_plus(media_name, encoding='utf-8', errors='replace')
        uri = f"https://api.jikan.moe/v3/search/{media_type}?q={query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(uri) as resp:
                data = await resp.json()
                return data["results"][0]
        return None

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(pass_context=True, name='wolfram', aliases=['w','ask'])
    async def wolfram(self, ctx, *, arguments : str):
        """Ask the wolfram god a question.

        [Options]
        arguments: The things you want to ask it.

        [Example]
        +<COMMAND> What is the airspeed velocity of an unladen swallow?
        """
        user = ctx.message.author
        channel = ctx.message.channel
        api_key = self.WOLFRAM_API_KEY
        width = 800
        max_height = 800
        font_size = 30
        layout = 'labelbar'
        background = '193555'
        foreground = 'white'

        rand_num = randint(0, 50)

        if not api_key:
            await ctx.send('Missing Api Key.')
            return

        try:
            query = urllib.parse.quote_plus(arguments, encoding='utf-8', errors='replace')
            url = 'http://api.wolframalpha.com/v1/simple?appid={}&i={}%3F&width={}&fontsize={}&background={}&foreground={}'.format(
                api_key, query, width, font_size, background, foreground)

            file = '{}.png'.format(rand_num)
            filename = 'cogs/utility/temp/{}.png'.format(rand_num)
            #filename = '{}.png'.format(user.id)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    image = await r.content.read()
            with open(filename,'wb') as f:
                f.write(image)

            # crop image
            image = Image.open(filename)
            width = image.size[0]
            height = image.size[1]

            # if too big
            if height > max_height:
                offset = 100
                size_det_img = image.crop((width-offset, 0, width - offset + 1, height))
                size_det_img = size_det_img.convert('RGB')
                current_color = size_det_img.getpixel((0, 0))
                change_height = 0
                for i in range(height):
                    new_pixel_color = size_det_img.getpixel((0, i))
                    if current_color != new_pixel_color:
                        if i > max_height:
                            break
                        change_height = i

                img2 = image.crop((0, 0, width, change_height + 3))
                image = img2

            image.save(filename)

            wolfram_file = discord.File(filename)
            em = discord.Embed(colour=user.colour)
            em.set_image(url='attachment://{}'.format(file))
            full_url = "http://www.wolframalpha.com/input/?i={}".format(query)
            em.description = "{} Click [here]({}) for full result".format(user.mention, full_url)
            await channel.send(embed = em, file = wolfram_file)
            os.remove(filename)
        except:
            await ctx.send('**Error. Try another search term.**')
            return

    '''
    @commands.group(pass_context=True)
    async def stream(self, ctx):
        """Get stream alerts from your favorite users"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @commands.has_permissions(manage_guild = True)
    @stream.command(name = "add", no_pm=True)
    async def add_stream(self, ctx, toggle=None):
        pass

    @commands.has_permissions(manage_guild = True)
    @stream.command(name = "remove", no_pm=True)
    async def remove_stream(self, ctx, toggle=None):
        pass

    @commands.has_permissions(manage_guild = True)
    @stream.command(name = "check", no_pm=True)
    async def stream_check(self, ctx, toggle=None):
        pass'''

    @commands.command(pass_context=True, no_pm=True, aliases = ['games'])
    async def whoplays(self, ctx, *game:str):
        """Shows a list of all the people playing a game.

        [Options]
        game: Name of the game you want to get a list of users for. (optional)

        [Example]
        +<COMMAND> osu!
        """
        user = ctx.message.author
        server = ctx.message.guild
        members = server.members

        game, options = OptionParser().parse(game)
        # print(game)

        if game and len(game) <= 2:
            await ctx.send("You need at least 3 characters.")
            return

        if game:
            playing_game = ""
            count_playing = 0
            players = []
            games = []
            for member in members:
                if member != None and member.activity != None and member.activity.name != None and not member.bot:
                    # print(member.activity.name.lower())
                    if game.lower() in member.activity.name.lower():
                        # print((member.name, member.activity.name))
                        players.append((member.name, member.activity.name))

            players = sorted(players, key=operator.itemgetter(0))

            if len(players) == 0:
                await ctx.send("No one is playing that game.")
            else:
                user_page = int(options["page"])
                per_page = 15
                total_pages = math.ceil(len(players)/per_page)
                embed_list = []
                for page in range(total_pages):
                    start_ind = per_page*page
                    end_ind = per_page*page + per_page

                    msg = "```"
                    for player, game in players[start_ind:end_ind]:
                        msg += u"▸ {:<25}   {:<30}\n".format(player, game)
                    msg += "```"

                    em = discord.Embed(description=msg, colour=user.colour)
                    showing = "({})".format(len(players))
                    em.set_author(name="These are the people who are playing {} {}: \n".format(game, showing))
                    em.set_footer(text="Page {}/{}".format(page+1, total_pages))
                    embed_list.append(em)

                await self.bot.menu(ctx, embed_list, message=None, page=user_page-1, timeout=15)
        else:
            freq_list = {}
            for member in members:
                if member != None and member.activity != None and member.activity.name != None and not member.bot:
                    if member.activity.name not in freq_list:
                        freq_list[member.activity.name] = 0
                    freq_list[member.activity.name]+=1

            sorted_list = sorted(freq_list.items(), key=operator.itemgetter(1), reverse = True)

            if not freq_list:
                await ctx.send("Surprisingly, no one is playing anything.")
            else:
                # create display
                msg = "```"
                games_per_page = 15
                max_games = min(len(sorted_list), games_per_page)
                for i in range(max_games):
                    game, freq = sorted_list[i]
                    msg += "▸ {:<25}   {:<30}\n".format(game[:25], freq_list[game])
                msg += "```"
                em = discord.Embed(description=msg, colour=user.colour)
                em.set_author(name="These are the server's most played games at the moment:")

                await ctx.send(embed = em)

class NewPoll():
    def __init__(self, message, main):
        self.channel = message.channel
        self.author = message.author.id
        self.client = main.bot
        self.poll_sessions = main.poll_sessions
        msg = message.content[6:]
        msg = msg.split(";")
        if len(msg) < 2: # Needs at least one question and 2 choices
            self.valid = False
            return None
        else:
            self.valid = True
        self.already_voted = []
        self.question = msg[0]
        msg.remove(self.question)
        self.answers = {}
        i = 1
        for answer in msg: # {id : {answer, votes}}
            self.answers[i] = {"ANSWER" : answer, "VOTES" : 0}
            i += 1

    async def start(self):
        msg = "**POLL STARTED!**\n\n{}\n\n".format(self.question)
        for id, data in self.answers.items():
            msg += "{}. *{}*\n".format(id, data["ANSWER"])
        msg += "\nType the number to vote!"
        await self.channel.send(msg)
        await asyncio.sleep(60)
        if self.valid:
            await self.endPoll()

    async def endPoll(self):
        self.valid = False
        msg = "**POLL ENDED!**\n\n{}\n\n".format(self.question)
        for data in self.answers.values():
            msg += "*{}* - {} votes\n".format(data["ANSWER"], str(data["VOTES"]))
        await self.channel.send(msg)
        self.poll_sessions.remove(self)

    def checkAnswer(self, message):
        try:
            i = int(message.content)
            if i in self.answers.keys():
                if message.author.id not in self.already_voted:
                    data = self.answers[i]
                    data["VOTES"] += 1
                    self.answers[i] = data
                    self.already_voted.append(message.author.id)
        except ValueError:
            pass

def setup(bot):
    n = Utility(bot)
    bot.add_cog(n)
    bot.add_listener(n.check_poll_votes, "on_message")