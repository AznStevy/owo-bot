import os
import random
import aiohttp
import asyncio
import discord
import datetime
import collections
from random import choice
import motor.motor_asyncio
from discord.ext import commands
from discord.utils import get

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server_settings = self.bot.db["fun"]

        self.prefix = self.bot.config['prefix'][0]
        self.all_users = self.bot.db["users"]

        client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = client['{}_fun'.format(self.bot.config['bot_name'])]
        self.markov = client['{}_markov'.format(self.bot.config['bot_name'])]

        # constants
        self.REACTION_FOLDER = os.path.join(
            os.getcwd(),'cogs','fun','resources','reactions')

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True, pass_context=True)
    async def hug(self, ctx, user : discord.Member=None):
        """Hug people.

        [Example]
        +<COMMAND> "<USER>" <OPTIONS>
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user

        if cmd_user.id == user.id:
            desc = 'Hugging yourself, huh?...'
        else:
            desc = f'{cmd_user.mention} hugged {user.mention}!'

        react_filepath = self._get_reaction_in_folder('hug')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    def _get_reaction_in_folder(self, folder_name):
        react_folder = os.path.join(self.REACTION_FOLDER, folder_name)
        all_images = os.listdir(react_folder)

        rand_image_filepath = random.choice(all_images)
        full_filepath = os.path.join(react_folder, rand_image_filepath)
        return full_filepath

    def _get_reaction_info(self, filepath):
        discord_file = discord.File(filepath, 
            filename="reaction.gif")
        url = 'attachment://' + "reaction.gif"

        return discord_file, url

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def triggered(self, ctx, user : discord.Member=None):
        """Become triggered. Because that's all we do these days.

        [Example]
        +<COMMAND> "<USER>" <OPTIONS>
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user

        if cmd_user.id == user.id:
            desc = 'Triggering... yourself?'
        else:
            desc = f'{cmd_user.mention} was triggered by {user.mention}!'

        react_filepath = self._get_reaction_in_folder('triggered')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def kiss(self, ctx, user : discord.Member=None):
        """Kiss someone. We all know it's never going to happen irl.

        [Example]
        +<COMMAND> "<USER>"
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user

        if cmd_user.id == user.id:
            desc = 'Kissing yourself? Gross...'
        else:
            desc = f'{cmd_user.mention} kissed {user.mention}!'

        react_filepath = self._get_reaction_in_folder('kiss')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def pout(self, ctx):
        """Make a pouting face. So sad.

        [Example]
        +<COMMAND> "<USER>"
        """
        cmd_user = ctx.message.author

        desc = '{} pouted...'.format(cmd_user.mention)

        react_filepath = self._get_reaction_in_folder('pout')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def pat(self, ctx, user : discord.Member):
        """Pat pat. :3

        [Example]
        +<COMMAND> "<USER>"
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user


        if cmd_user.id == user.id:
            desc = 'Patting yourself, huh?...'
        else:
            desc = f'{cmd_user.mention} patted {user.mention}!'

        react_filepath = self._get_reaction_in_folder('pat')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    '''
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def markov(self, ctx, start_text):
        """Generate a markov change based on a few texts.

        [Example]
        +<COMMAND> <USER> is a
        """
        pass'''

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True, aliases = ["neko"])
    async def cat(self, ctx):
        """Get a random picture of a cat!

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        search = "https://nekos.life/api/v2/img/meow"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search) as r:
                    result = await r.json()

                    em = discord.Embed(colour=user.colour)
                    em.set_image(url=result['url'])
                    await ctx.send(embed = em)
        except:
            await ctx.send("**Error. Try again later.**")


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True, aliases = ["doge","pupper"])
    async def dog(self, ctx):
        """Get a random picture of a dog!

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        search = "https://dog.ceo/api/breeds/image/random"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search) as r:
                    result = await r.json()

                    em = discord.Embed(colour=user.colour)
                    em.set_image(url=result['message'])
                    await ctx.send(embed = em)
        except:
            await ctx.send("**Error. Try again later.**")

    @commands.command(name="8ball", aliases=["8"])
    async def _8ball(self, ctx, *, question : str):
        """Ask 8 ball a question. Question must end with a question mark.

        [Example]
        +<COMMAND> Is owo a good bot? (the answer is no)
        """

        responses = ["As I see it, yes", "It is certain", "It is decidedly so", "Most likely", "Outlook good",
                     "Signs point to yes", "Without a doubt", "Yes", "Yes – definitely", "You may rely on it", "Reply hazy, try again",
                     "Ask again later", "Better not tell you now", "Cannot predict now", "Concentrate and ask again",
                     "Don't count on it", "My reply is no", "My sources say no", "Outlook not so good", "Very doubtful"]

        if question.endswith("?") and question != "?":
            await ctx.send("`" + choice(responses) + "`")
        else:
            await ctx.send("That doesn't look like a question.")


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def dance(self, ctx):
        """Do a dance! Better than you for sure.

        [Example]
        +<COMMAND>
        """
        cmd_user = ctx.message.author

        react_filepath = self._get_reaction_in_folder('dance')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def insult(self, ctx, user:discord.Member):
        """Insult someone. That's not very nice! :c

        [Example]
        +<COMMAND> "<USER>"
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user


        if cmd_user.id == user.id:
            desc = 'Why are you insulting yourself?'
        else:
            desc = f'{cmd_user.mention} roasted {user.mention}!'

        react_filepath = self._get_reaction_in_folder('insult')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def slap(self, ctx, user:discord.Member):
        """Slap someone. That must have hurt for both of you!

        [Example]
        +<COMMAND> "<USER>"
        """
        cmd_user = ctx.message.author
        if not user:
            user = cmd_user

        if cmd_user.id == user.id:
            desc = 'Why do you do this to yourself?'
        else:
            desc = f'{cmd_user.mention} slapped {user.mention}!'

        react_filepath = self._get_reaction_in_folder('slap')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def smug(self, ctx):
        """Smug af.

        [Example]
        +<COMMAND>
        """
        cmd_user = ctx.message.author

        desc = f'{cmd_user.mention} is being smug!'

        react_filepath = self._get_reaction_in_folder('smug')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])


    @commands.cooldown(1, 60, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def owo(self, ctx):
        """Does this really need an explanation at this point?

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        db_user = await self.bot.get_cog('Social').get_user(user)
        new_owo_count = 0
        if db_user and "owo_count" not in db_user:
            new_owo_count = 1
        elif db_user:
            new_owo_count = db_user["owo_count"] + 1

        await ctx.send(f"**What's this?** | {user.name}, you've **owo**'d `{new_owo_count}` times.")

        await self.all_users.update_one({'user_id': user.id}, {'$set':
            {'owo_count':new_owo_count}})

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True)
    async def loss(self, ctx):
        """This is loss.

        [Options]
        Link (-l): Check if an image is loss.

        [Example]
        +<COMMAND>
        """
        cmd_user = ctx.message.author

        desc = f'{cmd_user.mention} Loss.'

        react_filepath = self._get_reaction_in_folder('loss')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases = ['tsun'])
    async def tsundere(self,ctx):
        """B-baka! I died a bit on the inside after writing that.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        channel = ctx.message.channel
        server = user.guild

        phrases = [
            "I-It's not that I like you or anything!", 
            "B-Baka!", "N-No, it's not like I did it for you! I did it because I had free time, that's all!",
            "I like you, you idiot!", "I'm just here because I had nothing else to do!", "Are you stupid?", 
            "Don't misunderstand, it's not that I like you or anything!",
            "T-Tch! S-Shut up!", "Can you be ANY MORE CLUELESS?", 
            "I-I am not a tsundere, you b-baka!", "Don't get the wrong idea.",
            "I'm doing this p-purely for my own benefit. So d-don't misunderstand, you idiot!", 
            'Geez, stop pushing yourself! You\'re going to get yourself hurt one day, you idiot!'
        ]
        phrase = random.choice(phrases)
        cmd_user = ctx.message.author

        if cmd_user.id == user.id:
            desc = cmd_user.mention + ' ' + phrase

        react_filepath = self._get_reaction_in_folder('tsundere')
        file, url = self._get_reaction_info(react_filepath)

        em = discord.Embed(description=desc, colour=cmd_user.colour)
        em.set_image(url=url)
        await ctx.send(embed=em, files=[file])


    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command(no_pm=True, aliases=['easteregg', 'ee'])
    async def eastereggs(self, ctx):
        """Check how many easter eggs you've found!

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        channel = ctx.message.channel

        db_user = await self.bot.get_cog('Social').get_user(user)
        ee_count = 0
        if db_user and "eastereggs_found" in db_user:
            ee_count = len(db_user["eastereggs_found"])
        else:
            ee_count = 0

        await ctx.send(f"**{user.name}, you've found `{ee_count}` easter eggs!**")


def setup(bot):
    n = Fun(bot)
    bot.add_cog(n)
