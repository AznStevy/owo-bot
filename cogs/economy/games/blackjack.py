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

class Blackjack:
    def __init__(self, bot):
        self.bot = bot
        self.nums = list(range(2,15))
        self.suits = list(range(1,5))

        # cards
        self.drawn_cards = []
        self.bot_hand = []
        self.user_hand = []

        # constant
        self.CARDS_FOLDER = os.path.join(os.getcwd(), 
            'cogs','economy','games','resources','cards')
        self.TEMP_FOLDER = os.path.join(os.getcwd(), 
            'cogs','economy','games','temp')

    async def start_game(self, ctx):
        def check_event(m):
            return any([x == m.content.lower() for x in ['h','hit','s','stay']]) and m.author == ctx.author

        user = ctx.message.author
        channel = ctx.message.channel

        self.user_cards = self.get_cards(num=2)

        self.bot_hand = self.get_cards(2)
        self.user_hand = self.get_cards(2)

        # draw cards
        user_cards_filepath = self._draw_cards(self.user_hand)
        cards_file, cards_url = self._get_discord_image_info(user_cards_filepath)

        # draw embed
        em = discord.Embed(description='', colour=user.colour)
        em.description = '**Ok {}, here are your cards: {}**\nWhat do you want to do? `hit(h)/stay(s)`'.format(
            user.mention, self.pretty_card(self.user_hand))
        em.set_image(url=cards_url)
        em.set_footer(text='Current Total: {}'.format(self.calc_total(self.user_hand)))
        await ctx.send(embed=em, files=[cards_file])

        try:
            response = await self.bot.wait_for('message', check=check_event, timeout=30)
        except asyncio.TimeoutError:
            response = None

        while response and any(res in response.content for res in ['h' or 'hit']) and self.calc_total(self.user_hand) <= 21:
            # print(any(res in response.content for res in ['h' or 'hit']) or self.calc_total(self.user_hand) < 21)
            card = self.get_cards(1)
            # await ctx.send('**New card: {}**'.format(self.pretty_card(card)))
            self.user_hand.extend(card)

            # draw cards
            user_cards_filepath = self._draw_cards(self.user_hand)
            cards_file, cards_url = self._get_discord_image_info(user_cards_filepath)

            # draw embed
            em = discord.Embed(description='', colour=user.colour)
            em.description = '**{}, your current cards are: {}**\nWhat do you want to do? `hit(h)/stay(s)`'.format(
                user.mention, self.pretty_card(self.user_hand))
            em.set_image(url=cards_url)
            em.set_footer(text='Current Total: {}'.format(self.calc_total(self.user_hand)))
            await ctx.send(embed=em, files=[cards_file])

            try:
                response = await self.bot.wait_for('message', check=check_event, timeout=30)
            except asyncio.TimeoutError:
                response = None

        max_limit = random.randint(13,16)
        while self.calc_total(self.bot_hand) < max_limit:
            self.bot_hand.extend(self.get_cards(1))

        winner = self.is_winner()
        if winner is None:
            await ctx.send('**Tie! Both had {}**'.format(self.calc_total(self.user_hand)))
            return None
        elif self.is_winner():
            await ctx.send('**Congrats, you won with `{}` vs `{}`**'.format(
                self.calc_total(self.user_hand), self.calc_total(self.bot_hand)))
            return True
        else:
            await ctx.send('**Sorry, you lost with `{}` vs `{}`**'.format(
                self.calc_total(self.user_hand), self.calc_total(self.bot_hand)))
            return False

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

    def is_winner(self):
        bot_val = self.calc_total(self.bot_hand)
        user_val = self.calc_total(self.user_hand)

        if bot_val > 21 and user_val > 21:
            return None
        elif bot_val > 21:
            return True
        elif user_val > 21:
            return False
        elif bot_val > user_val:
            return False
        elif bot_val < user_val:
            return True
        elif user_val == 21:
            return True

    def calc_total(self, hand):
        sum_hand = 0

        # sort by value so you handle aces at the end
        hand = sorted(hand, key=lambda tup: tup[1])

        for suit, val in hand:
            if val == 14:
                if sum_hand + 11 > 21:
                    val = 1
                else:
                    val = 11

            elif val > 10: # if it's a royal
                val = 10

            sum_hand += val
        return sum_hand

    def get_cards(self, num = 1):
        counter = 0
        cards = []

        while counter < num:
            new_card = (random.choice(self.suits), random.choice(self.nums))
            if self.check_drawn(new_card):
                counter+=1
                self.drawn_cards.append(new_card)
                cards.append(new_card)
        return cards

    def check_drawn(self, card):
        if card in self.drawn_cards:
            return False
        return True

    def pretty_card(self, cards):
        card_suit = [":clubs:", ":diamonds:",":hearts:",":spades:"]
        str_cards = []
        for card in cards:
            msg = '`{}`'.format(self._correct_card_num(card[1]))
            msg += card_suit[card[0]-1]
            str_cards.append(msg)

        return ', '.join(str_cards)

    def _correct_card_num(self, card_num):
        if card_num == '11':
            return 'J'
        elif card_num == '12':
            return 'Q'
        elif card_num == '13':
            return 'K'
        elif card_num == '14':
            return 'A'
        else:
            return str(card_num)
