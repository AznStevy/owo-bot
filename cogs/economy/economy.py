import os
import time
import math
import random
import asyncio
import discord
import datetime
import operator
import collections
import motor.motor_asyncio
from discord.utils import get
from discord.ext import commands
from utils.option_parser import OptionParser

# related scripts
from cogs.economy.games.slots import Slots
from cogs.economy.games.blackjack import Blackjack
from cogs.economy.games.twentyfour import TwentyFour

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # self.prefix = self.bot.config['prefix'][0]
        self.all_users = self.bot.db["users"]

        client = motor.motor_asyncio.AsyncIOMotorClient()
        self.db = client['{}_economy'.format(self.bot.config['bot_name'])]

        # bet limit
        self.bet_limit = 500

        # dropped credits
        self.dropped = {}

        # constant
        self.LB_MAX = 15

    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.command()
    async def bank(self, ctx, *inputs):
        """Check who has the most credits

        [Example]
        +<COMMAND> -global
        """
        server = ctx.message.guild
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)

        option_parser = OptionParser()
        option_parser.add_option('global',  'global',   opt_type=None,   default=False)
        option_parser.add_option('rep',     'rep',      opt_type=None,   default=False)
        option_parser.add_option('p',       'page',     opt_type=int,    default=1)
        _, options = option_parser.parse(inputs)

        skip_num = self.LB_MAX * (int(options['page'])-1)

        users = []
        board_type = ''
        user_stat = userinfo['credits']
        att_rank = None
        if options['global']:
            title = "Global Credit Leaderboard for {}\n".format(self.bot.user.name)
            query = {"credits": {"$exists": True}}
            sort_criteria = [("credits", -1)]

            relevant_users = []
            async for entry in self.all_users.find(query).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):
                relevant_users.append(entry)

            for info in relevant_users:
                try:
                    users.append((info["username"], info["credits"]))
                except:
                    users.append((info["user_id"], info["credits"]))

            att_rank = await self._find_global_credit_rank(user, userinfo)     

            board_type = 'Credits'
            icon_url = self.bot.user.avatar_url
        else:
            title = "Credit Leaderboard for {}\n".format(server.name)
            query = {
                "servers.{}".format(server.id): {"$exists": True},
                "credits": {"$exists": True}
            }
            sort_criteria = [("credits", -1)]

            relevant_users = []
            async for entry in self.all_users.find(query).sort(sort_criteria).skip(
                skip_num).limit(self.LB_MAX):
                relevant_users.append(entry)

            for info in relevant_users:
                try:
                    users.append((info["username"], info["credits"]))
                except:
                    users.append((info["user_id"], info["credits"]))

            att_rank = await self._find_server_credit_rank(user, userinfo, server) 

            board_type = 'Credits'
            icon_url = server.icon_url


        # drawing leaderboard
        sorted_list = users
        msg = ""
        start_index = self.LB_MAX*(int(options['page'])-1)

        default_label = "   "
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
            msg += u'{:<12}`\n'.format("{}".format(int(single_user[1])))

        em = discord.Embed(description='', colour=user.colour)
        em.set_author(name=title, icon_url = icon_url)
        em.description = msg
        em.set_footer(text="Your Rank: {} | {}: {}".format(
            att_rank, board_type, user_stat))

        await ctx.send(embed = em)


    async def _find_global_credit_rank(self, user, userinfo):
        query = {
            'credits': {'$gt': userinfo['credits']}
        }
        # user_rank = await self.all_users.find(query).count()
        credit_rank = await self.all_users.count_documents(query) + 1
        return credit_rank


    async def _find_server_credit_rank(self, user, userinfo, server):
        target_id = str(user.id)
        query = {
            "servers.{}".format(server.id): {"$exists": True},
            'credits': {'$gt': userinfo['credits']}
        }

        # user_rank = await self.all_users.find(query).count()
        credit_rank = await self.all_users.count_documents(query) + 1
        return credit_rank


    def _truncate_text(self, text, max_length):
        if len(text) > max_length:
            if text.strip('$').isdigit():
                text = int(text.strip('$'))
                return "${:.2E}".format(text)
            return text[:max_length-3] + "..."
        return text


    @commands.command(aliases = ["daily", "payday", "payme"])
    async def pay(self, ctx):
        """Get your daily pay of 200 credits.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)
        curr_time = time.time()
        daily_credits = 50

        if userinfo and "eastereggs_found" in userinfo:
            ee_count = len(userinfo["eastereggs_found"])
            if ee_count != 0 and self.bot.num_eastereggs != 0:
                daily_credits = round(daily_credits*(1+(ee_count/self.bot.num_eastereggs)))

        day_seconds = 60*60*6 # quarter of a day
        if "credits_block" not in userinfo.keys() or curr_time-userinfo["credits_block"] > day_seconds:
            try:
                if userinfo["credits"] < 0:
                    userinfo["credits"] = 0
                new_credits = userinfo["credits"] + daily_credits
            except:
                new_credits = daily_credits

            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                "credits_block": curr_time,
                "credits": new_credits
            }})
            await ctx.send("**{}, you just received `{}` credits!**".format(
                user.mention, daily_credits))
        else:
            delta = curr_time-userinfo["credits_block"]
            seconds = day_seconds - delta
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            await ctx.send("**{}, you need to wait `{} hours, {} minutes, and {} seconds` until you can receive more credits!**".format(
                user.mention, int(h), int(m), int(s)), delete_after=5)


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases=['money'])
    async def credits(self, ctx, user:discord.Member=None):
        """Check how many credits you have.

        [Example]
        +<COMMAND>
        """
        if not user:
            user = ctx.message.author

        userinfo = await self.bot.get_cog('Social').get_user(user)
        try:
            credits = userinfo["credits"]
        except:
            credits = 0

        await ctx.send("**{}, you currently have `{}` credits!**".format(
            user.mention, credits))


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command()
    async def drop(self, ctx, amount:int):
        """Drop a certain number of credits.

        [Options]
        amount: The amount you want to drop. Tax 20%. (int)

        [Example]
        +<COMMAND> 100
        """
        user = ctx.message.author
        server = ctx.message.guild

        userinfo = await self.bot.get_cog('Social').get_user(user)

        deduct_amount = amount*(1.2)
        if amount and userinfo["credits"] < deduct_amount:
            return await ctx.send(
                ":red_circle: **{}, you can't drop more than you have!**".format(
                    user.mention))
        if amount and amount > self.bet_limit*5:
            return await ctx.send(
                ":red_circle: **{}, you can't drop more than `{}`!**".format(
                    user.mention, self.bet_limit*2))
        if amount and amount < 10:
            return await ctx.send(
                ":red_circle: **Must be greater than 10!**")
        if str(server.id) in self.dropped.keys():
            return await ctx.send(
                ":red_circle: **Someone already dropped credits recently!**")
            
        self.dropped[str(server.id)] = (amount, user.id)
        prefix = await self.bot.get_server_prefixes(
            self.bot, ctx.message, one_prefix = True)
        await ctx.send(f":arrow_down: **{user.name} just dropped `{amount}` credits. Type `{prefix}pick` to pick it up!**")

        if user.id != int(self.bot.config["owner"]): # hehe
            new_credits = int(userinfo["credits"] - deduct_amount)
            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                "credits": new_credits
            }})

        # pause for some time
        await asyncio.sleep(10)
        if str(server.id) in self.dropped.keys():
            try:
                del self.dropped[str(server.id)]
            except:
                pass
            await ctx.send(f":red_circle: **{user.name}, no one picked up your `{amount}` credit drop! :C**")

    @commands.command()
    async def pick(self, ctx):
        """Pick up dropped credits.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        server = ctx.message.guild

        if not str(server.id) in self.dropped.keys():
            return await ctx.send(":red_circle: **Nothing has been dropped in the server recently!**")
            

        if self.dropped[str(server.id)][1] == user.id and user.id != int(self.bot.config["owner"]):
            return await ctx.send(":red_circle: **You can't pick up your own drop!**")
            
        userinfo = await self.bot.get_cog('Social').get_user(user)
        amount_gained = int(self.dropped[str(server.id)][0])
        current_credits = userinfo["credits"] + amount_gained
        await ctx.send(f":arrow_up: **{user.name} picked up `{amount_gained}` credits!**")
        try:
            del self.dropped[str(server.id)]
        except:
            pass
        await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
            "credits": current_credits
        }})


    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.command(aliases=['t','coin','ht'])
    async def toss(self, ctx, bet:int, ht:str):
        """Toss a coin for money. Like of like flip.

        [Options]
        bet: The amount you want to bet. Tax 10%. (int)
        ht: Heads or tails. (str)

        [Example]
        +<COMMAND> 100 h
        """
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)

        if bet and userinfo["credits"] < bet:
            await ctx.send(":red_circle: **{}, you can't bet more than you have!**".format(user.mention))
            return
        if bet and (bet > self.bet_limit):
            await ctx.send(":red_circle: **{}, you can't bet more than `{}`!**".format(user.mention, self.bet_limit))
            return
        if bet and bet < 1:
            await ctx.send(":red_circle: **Must be greater than `0`!**")
            return

        if "h" in ht:
            guess = 0
        elif "t" in ht:
            guess = 1
        else:
            await ctx.send(":red_circle: **Must indicate heads (`h`) or tails (`t`)!**")
            return

        choice = random.choice([0,1])
        current_credits = userinfo["credits"] - bet
        if choice == guess: # win
            current_credits += 2*bet
            await ctx.send("**{}, you won `{}` credits!**".format(user.mention, bet))
        else:
            await ctx.send("**{}, you lost `{}` credits!**".format(user.mention, bet))
        await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
            "credits": current_credits
        }})


    @commands.cooldown(1, 3, commands.BucketType.user)
    @commands.command()
    async def guess(self, ctx, bet:int, guess:int, diff:int = 1):
        """Guess a number 1-10^(diff). (diff) mutliplies your amount earned if you win.

        [Options]
        bet: The amount you want to drop. Tax 10%. (int)
        guess: The number to guess.
        diff: Difficulty of the guess (int, 1-3)

        [Example]
        +<COMMAND> 100 2 2
        """
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)

        if bet and userinfo["credits"] < bet:
            await ctx.send(":red_circle: **{}, you can't bet more than you have!**".format(user.name))
            return
        if bet and (bet > self.bet_limit):
            await ctx.send(":red_circle: **{}, you can't bet more than `{}`!**".format(user.name, self.bet_limit))
            return
        if bet and bet < 1:
            await ctx.send(":red_circle: **Must be greater than `0`!**")
            return
        if diff > 3 or diff < 1:
            await ctx.send(":red_circle: **{}, your diff must be 1-3!**".format(user.name))
            return

        current_credits = userinfo["credits"]
        correct_num = random.randint(1, 10**diff+1)
        if correct_num == guess:
            # win
            win_amount = bet*diff
            current_credits += win_amount
            await ctx.send(":white_check_mark: **Congrats {}, you won `{}` credits for guessing `{}` correctly out of `{}` numbers!**".format(
                user.name, win_amount, correct_num, int(10**diff)))
        else:
            # lose
            lose_amount = round(bet*((1/10**diff)))
            if lose_amount == 0:
                lose_amount = 1
            current_credits -= lose_amount
            await ctx.send(":red_circle: **Sorry {}, you lost `{}` credit for guessing `{}` incorrectly**".format(
                user.name, lose_amount, correct_num))
        await self.all_users.update_one({'user_id':str(user.id)},
            {'$set':{
                "credits": current_credits
            }})


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(no_pm=True, aliases=['slot','reel','s'])
    async def slots(self, ctx, bet: int):
        """Play the slot machine.

        [Options]
        bet: The amount you want to bet.

        [Example]
        +<COMMAND> 100
        """
        user = ctx.message.author
        server = user.guild
        userinfo = await self.bot.get_cog('Social').get_user(user)

        if bet and userinfo["credits"] < bet:
            await ctx.send(":red_circle: **{}, you can't bet more than you have!**".format(user.name))
            return
        if bet and (bet > 100):
            await ctx.send(":red_circle: **{}, you can't bet more than `{}`!**".format(user.name, 100))
            return
        if bet and bet < 1:
            await ctx.send(":red_circle: **Must be greater than `0`!**")
            return

        slot_game = Slots(self.bot, bet)
        current_credits = userinfo["credits"] - bet
        payout = await slot_game.start_slots(ctx)
        current_credits += payout

        await self.all_users.update_one({'user_id':str(user.id)},
            {'$set':{
                "credits": current_credits
            }})


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases = ['24'])
    async def twentyfour(self, ctx, bet:int = None):
        """Play a game of twenty..four? against me.

        [Options]
        bet: The amount you want to bet. (int)

        [Example]
        +<COMMAND> 50
        """
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)

        if bet and userinfo["credits"] < bet:
            await ctx.send(":red_circle: **{}, you can't bet more than you have!**".format(user.name))
            return
        if bet and (bet > 50):
            await ctx.send(":red_circle: **{}, you can't bet more than `{}`!**".format(user.name, 50))
            return
        if bet and bet < 1:
            await ctx.send(":red_circle: **Must be greater than `0`!**")
            return

        # take amount away from user
        curr_time = time.time()
        twenty_four = TwentyFour(self.bot)
        twenty_four_win = await twenty_four.start_game(ctx)

        if bet:
            start_credits = userinfo["credits"]
            current_credits = userinfo["credits"] - bet

            allowed_time = 30
            baseline_time = allowed_time/2

            if twenty_four_win:
                end_time = time.time()
                time_took = round(end_time-curr_time)
                win_amount = round((2*bet)*((allowed_time-time_took)/allowed_time))
                current_credits = current_credits + win_amount
                diff = abs(current_credits - start_credits)
                if time_took < baseline_time:
                    # you win
                    await ctx.send(":white_check_mark: **You took `{}` sec and won `{}` credits!**".format(time_took, diff))
                elif time_took > baseline_time:
                    # you lose
                    await ctx.send(":red_circle: **You took `{}` sec and lost `{}` credits!**".format(time_took, diff))
                else:
                    await ctx.send(":white_circle: **You took `{}` sec and broke even!**".format(time_took))
            await self.all_users.update_one({'user_id':str(user.id)},
                {'$set':{
                    "credits": current_credits
                }})


    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.command(aliases = ['21'])
    async def blackjack(self, ctx, bet:int):
        """Play a game of twenty..one against me

        [Options]
        bet: The amount you want to bet. (int)

        [Example]
        +<COMMAND> 100
        """
        user = ctx.message.author
        userinfo = await self.bot.get_cog('Social').get_user(user)

        if bet and userinfo["credits"] < bet:
            await ctx.send(":red_circle: **{}, you can't bet more than you have!**".format(user.mention))
            return
        if bet and (bet > self.bet_limit):
            await ctx.send(":red_circle: **{}, you can't bet more than `{}`!**".format(user.mention, self.bet_limit))
            return
        if bet and bet < 1:
            await ctx.send(":red_circle: **Must be greater than `0`!**")
            return

        blackjack = Blackjack(self.bot)
        blackjack_win = await blackjack.start_game(ctx)
        if bet:
            current_credits = userinfo["credits"] - bet
            if blackjack_win is None:
                return await ctx.send("**{}, no credits gained.**")
            elif blackjack_win:
                current_credits += 2*bet
                await ctx.send("**{}, you won `{}` credits!**".format(user.mention, bet))
            elif blackjack_win == False:
                await ctx.send("**{}, you lost `{}` credits!**".format(user.mention, bet))

            await self.all_users.update_one({'user_id':str(user.id)}, {'$set':{
                "credits": current_credits
            }})

def setup(bot):
    bot.add_cog(Economy(bot))
