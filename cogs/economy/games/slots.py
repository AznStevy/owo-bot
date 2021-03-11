import os
import random
import asyncio
import discord
import datetime
import collections
import numpy as np
import motor.motor_asyncio

from discord.ext import commands
from discord.utils import get

class Slots:
    def __init__(self, bot, bet):
        self.bot = bot
        self.bet = bet
        self.emotes_list = [
            "<:owo:494203160718737418>",
            "<:ppcat:494205106569347111>",
            "<:easys:483759698919686175>",
            "<:expertpluss:483759702119940116>",
            "<:experts:483759702606479360>",
            "<:hards:483759702749085706>",
            "<:insanes:483759703512580128>",
            "<:normals:483759703579688972>",
            "<:easyt:483759702103162900>",
            "<:expertplust:483759702581313536>",
            "<:expertt:483759703508385792>",
            "<:hardt:483759703587946496>",
            "<:insanet:483759704019959848>",
            "<:normalt:483759704074485760>",
            "<:easyc:483759696877191183>",
            "<:expertplusc:483759700123320320>",
            "<:expertc:483759700374978580>",
            "<:hardc:483759702765731841>",
            "<:insanec:483759702854074378>",
            "<:normalc:483759703927816212>",
            "<:easym:483759698852577280>",
            "<:expertm:483759700589150208>",
            "<:expertplusm:483759700790476820>",
            "<:hardm:483759703617437696>",
            "<:insanem:483759703932010517>",
            "<:normalm:483759703957045254>",
            "<:rankingXH:462313722556186626>",
            "<:rankingX:462313722736672780>",
            "<:rankingS:462313719762911233>"
        ]
        self.line_of_interest = None # line of interest

    async def start_slots(self, ctx):
        total_payout = 0
        #trials = 2000
        #for n in range(trials):
        reels  = []
        for n in range(5):
            reels.append(self.create_reel())
        slots = self.create_slot(reels)
        line = self.get_line_of_interest(reels)
        payout, payout_text = self.get_payout(line)
        #total_payout += payout
        em = self.create_embed(ctx, slots, payout, payout_text)

        #await ctx.send(f"Payout for {trials} trials: {total_payout/trials}")
        await ctx.send(embed = em)
        return payout

    def create_embed(self, ctx, slots, payout, payout_text):
        em = discord.Embed(colour=ctx.message.author.colour)
        em.add_field(name="Slots", value=slots, inline=True)

        payout_txt = ""
        payout_txt += "\n".join(payout_text)
        if self.bet > payout:
            net_type = "Lost"
            diff = self.bet - payout
        else:
            net_type = "Gained"
            diff = payout - self.bet

        payout_txt += f"\n-------------------\n**{payout}** (`{net_type} {diff}`)"
        em.add_field(name="Payout", value=payout_txt, inline=True)
        return em

    def create_reel(self):
        shuffled = sorted(self.emotes_list, key=lambda k: random.random())
        return shuffled[0:3]

    def get_line_of_interest(self, reels):
        reels = np.transpose(reels)
        self.line_of_interest = reels[1]
        # print(self.line_of_interest)
        return self.line_of_interest

    def create_slot(self, reels):
        reels = np.transpose(reels)
        msg = "" # line_break + "\n"
        for i, row in enumerate(reels):
            if i == 1:
                msg += "▸"
            msg += "".join(row)
            msg += "\n"
        return msg

    def get_payout(self, line_of_interest):
        # define payout values
        payout_text = []
        total_payout = 0
        for element in line_of_interest:
            amount = 0
            if "easy" in element:
                total_payout += (0/10) * self.bet
            if "normal" in element:
                # total_payout += (0/10) * self.bet
                amount = round((.5/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**Normal diff** (`+{amount}`)")
            if "hard" in element:
                # total_payout += (0/10) * self.bet
                amount = round((.5/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**Hard diff** (`+{amount}`)")
            if "insane" in element:
                amount = round((1/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**Insane diff** (`+{amount}`)")

            if "expertplus" in element:
                amount = round((3/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**Expert+ diff** (`+{amount}`)")
            elif "expert" in element:
                amount = round((2/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**Expert diff** (`+{amount}`)")

            if "XH" in element:
                amount = round((5/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**SSH Rank** (`+{amount}`)")
            elif "X" in element:
                amount = round((4/10) * self.bet)
                total_payout += amount
                payout_text.append(f"**SS Rank** (`+{amount}`)")

            if "owo" in element:
                amount = round((1.5) * self.bet)
                total_payout += amount
                payout_text.append(f"**owo** (`+{amount}`)")
            if "ppcat" in element:
                amount = round((1.25) * self.bet)
                total_payout += amount
                payout_text.append(f"**PP cat** (`+{amount}`)")

        # check if all the same mode
        for mode in ['s','c','t','m']:
            counter = 0
            for element in line_of_interest:
                parts = element.split(":")
                emote_name = parts[1]
                if emote_name.endswith(mode):
                    counter += 1

            if counter == 5:
                amount = round(2 * self.bet)
                total_payout += amount
                payout_text.append(f"Same mode (`+{amount}`)")
                break

        # check if all the same
        check_element = line_of_interest[0]
        same_counter = 0
        for element in line_of_interest:
            if element == check_element:
                same_counter += 1

        if same_counter == 5:
            amount = self.bet * 20
            total_payout += amount
            payout_text.append(f"ALL SAME (`+{amount}`)")

        total_payout = round(total_payout)
        return total_payout, payout_text
