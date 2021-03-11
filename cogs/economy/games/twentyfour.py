import os
import random
import asyncio
import discord
import datetime
import collections
import motor.motor_asyncio
from discord.ext import commands
from discord.utils import get
from PIL import Image

from   itertools  import permutations, combinations, product, chain
from   pprint     import pprint as pp
from   fractions  import Fraction as F
import random, ast, re
import sys
from itertools import zip_longest

class TwentyFour:
    def __init__(self, bot, difficulty=1):
        self.digits = []
        self.bot = bot
        self.difficulty = difficulty

        # constant
        self.CARDS_FOLDER = os.path.join(os.getcwd(), 
            'cogs','economy','games','resources','cards')
        self.TEMP_FOLDER = os.path.join(os.getcwd(), 
            'cogs','economy','games','temp')

    async def start_game(self, ctx):
        def check_event(m):
            return m.author == ctx.author

        user = ctx.message.author
        channel = ctx.message.channel

        self.digits = self.get_digits()
        answer = ''
        chk = False
        ans = False

        # draw embed
        fake_cards = self._get_cards(self.digits)
        cards_filepath = self._draw_cards(fake_cards)
        cards_file, cards_url = self._get_discord_image_info(cards_filepath)

        em = discord.Embed(description='', colour=user.colour)
        em.description = '**Ok {}, your numbers are: **'.format(user.mention)
        em.set_image(url=cards_url)
        await ctx.send(embed=em, files=[cards_file])

        sol = await self.solve(self.digits)
        print(sol)

        # wait for user answer
        try:
            answer = await self.bot.wait_for('message', check=check_event, timeout=30)
        except asyncio.TimeoutError:
            answer = None
        if answer:
            answer = answer.content
            answer = answer.replace('x',"*").replace('X',"*")

        # check user solution
        chk = self.check(answer, self.digits)

        if not answer:
            await ctx.send('**Sorry {}, you ran out of time. One possible answer was: `{}` **'.format(user.mention, sol))
            return False
        elif answer == '?' or answer.lower() == "pass":
            await ctx.send('**Give up? One possible answer was: `{}` **'.format(sol))
            return False

        if not chk:
            if user:
                await ctx.send('**{}, your input is not valid. One possible answer was `{}`.**'.format(user.mention, sol))
            else:
                await ctx.send('**Your input is not valid. One possible answer was `{}`**'.format(sol))
        else:
            if '/' in answer:
                # Use Fractions for accuracy in divisions
                answer = ''.join( (('F(%s)' % char) if char in '123456789' else char)
                                  for char in answer )

            if answer.lower() == "none" and sol == None:
                await ctx.send("**Congrats {}! You're correct!**".format(user.mention))
                return True

            try:
                ans = eval(answer)
            except:
                ans = None

            if ans == 24:
                await ctx.send("**Congrats {}! You're correct!**".format(user.mention))
                return True
            else:
                if sol == None:
                    await ctx.send("**Nope, sorry {}. The correct answer was: `{}`**".format(user.mention, sol))
                else:
                    await ctx.send("**Nope, sorry {}. One possible answer was: `{}`**".format(user.mention, sol))
                return

    def get_digits(self, num_digits=4):
        return [str(random.randint(1, 10)) for i in range(num_digits)]

    def check(self, answer, digits):
        if not answer:
            return False
        elif answer.lower() == "none":
            return True

        allowed = set('() +-*/\t'+''.join(digits))
        ok = all(ch in allowed for ch in answer) and \
             all(digits.count(dig) == answer.count(dig) for dig in set(digits)) \
             and not re.search('\d\d', answer)
        if ok:
            try:
                ast.parse(answer)
            except:
                ok = False
        return ok

    async def solve(self, digits, target=24):
        digilen = len(digits)
        # length of an exp without brackets
        exprlen = 2 * digilen - 1
        # permute all the digits
        digiperm = sorted(set(permutations(digits)))
        # All the possible operator combinations
        opcomb   = list(product('+-*/', repeat=digilen-1))
        # All the bracket insertion points:
        brackets = ( [()] + [(x,y)
                             for x in range(0, exprlen, 2)
                             for y in range(x+4, exprlen+2, 2)
                             if (x,y) != (0,exprlen+1)]
                     + [(0, 3+1, 4+2, 7+3)] ) # double brackets case
        for d in digiperm:
            for ops in opcomb:
                if '/' in ops:
                    d2 = [('F(%s)' % i) for i in d] # Use Fractions for accuracy
                else:
                    d2 = d
                ex = list(chain.from_iterable(zip_longest(d2, ops, fillvalue='')))
                for b in brackets:
                    exp = ex[::]
                    for insertpoint, bracket in zip(b, '()'*(len(b)//2)):
                        exp.insert(insertpoint, bracket)
                    txt = ''.join(exp)
                    try:
                        num = eval(txt)
                    except ZeroDivisionError:
                        continue
                    if num == target:
                        if '/' in ops:
                            exp = [ (term if not term.startswith('F(') else term[2])
                                   for term in exp ]
                        ans = ' '.join(exp).rstrip()
                        return ans
        return None

    def _draw_cards(self, cards):
        # create a unique id for save file
        rand_id = random.randint(0, 100)

        for idx, card in enumerate(cards):
            card_image = self._get_card_image(card)
            if idx == 0:
                total_width = card_image.width * len(cards)
                total_height = card_image.height

                full_im = Image.new('RGBA', (total_width, total_height))
            
            full_im.paste(card_image, (idx*card_image.width, 0), card_image)


        output_im_name = 'blackjack_{}.png'.format(rand_id)
        output_filepath = os.path.join(self.TEMP_FOLDER, output_im_name)

        full_im.save(output_filepath)

        return output_filepath


    def _get_card_image(self, card):
        suit = int(card[0])
        if suit == 1:
            suit_str = 'club'
        elif suit == 2:
            suit_str = 'diamond'
        elif suit == 3:
            suit_str = 'heart'
        elif suit == 4:
            suit_str = 'spade'

        val = int(card[1])
        if val == 11: 
            val_str = 'Jack'
        elif val == 12: 
            val_str = 'Queen'
        elif val == 13: 
            val_str = 'King'
        elif val == 14: 
            val_str = 'Ace'
        else:
            val_str = str(val)

        card_file = '{}{}.png'.format(suit_str, val_str)
        card_full_path = os.path.join(self.CARDS_FOLDER, card_file)

        card_image = Image.open(card_full_path)
        return card_image


    def _get_discord_image_info(self, card_path):
        discord_file = discord.File(card_path, filename="cards.png")
        url = 'attachment://' + "cards.png"

        return discord_file, url


    def _get_cards(self, digits):
        cards = []
        for digit in digits:
            rand_suit = random.randint(1, 4)
            card = (rand_suit, digit)

            while card in cards:
                rand_suit = random.randint(1, 4)
                card = (rand_suit, digit)

            cards.append(card)

        return cards
