import os
import random
import asyncio
import discord
import datetime
import collections
import motor.motor_asyncio
from discord.ext import commands
from discord.utils import get

from   itertools  import permutations, combinations, product, chain
from   pprint     import pprint as pp
from   fractions  import Fraction as F
import random, ast, re
import sys
from itertools import zip_longest

class EmoteRace:
    def __init__(self, bot):
        self.bot = bot

    async def start_game(self, ctx):


    def is_winner(self):
        pass

    def calc_total(self, hand):
        pass

    def get_cards(self, num = 1):
        pass

    def check_drawn(self, card):
        pass

    def pretty_card(self, cards):
        pass
