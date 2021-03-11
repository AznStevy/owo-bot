import os
import json
import math
import random
import aiohttp
import asyncio
import pyoppai
import discord
import pyttanko
import statistics
from PIL import Image, ImageEnhance, ImageFilter
import matplotlib as mpl
mpl.use('Agg') # for non gui
from matplotlib import ticker
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from utils.dataIO import dataIO, fileIO

from pippy.beatmap import Beatmap
from cogs.osu.osu_utils.chunks import chunks
from cogs.osu.beatmap_parser import beatmap_parser
from cogs.osu.osu_utils import utils, web_utils, droid_pyttanko


def handle_status(beatmap_info):
    if 'status' in beatmap_info.keys():
        status = beatmap_info['status']
    elif 'approved' in beatmap_info.keys():
        status = beatmap_info['approved']
    else: # assume it's ranked?
        status = 1

    is_int = False
    try:
        status = int(status)
        is_int = True
    except ValueError:
        status = status.lower()

    if is_int:
        return status
    elif status == 'graveyard': # graveyard, red
        return -2
    elif status == 'work in progress' or status == 'wip': # WIP, purple
        return -1
    elif status == 'pending': # pending, blue
        return 0
    elif status == 'ranked': # ranked, bright green
        return 1
    elif status == 'approved': # approved, dark green
        return 2
    elif status == 'qualified': # qualified, turqoise
        return 3
    elif status == 'loved': # loved, pink
        return 4


async def get_std_data(beatmap_info, bmp_parsed,
    accs=[95, 99, 100], mods=0, extra_info={}):

    bmap = bmp_parsed

    key_append = '_mod'
    beatmap_id = beatmap_info['beatmap_id']

    # let pyttanko handle calculations
    ret_json = {}
    try:
        stars = pyttanko.diff_calc().calc(bmap, mods=mods)
    except:
        return beatmap_info, None

    ret_json['stars'+key_append] = float(stars.total)
    ret_json['aim_stars'+key_append] = float(stars.aim)
    ret_json['speed_stars'+key_append] = float(stars.speed)
    # print(beatmap_info.keys())
    if 'max_combo' not in beatmap_info:
        # print('Using parsed max combo')
        ret_json['max_combo'] = bmap.max_combo()
    else:
        # print('Using bmp max combo')
        ret_json['max_combo'] = beatmap_info['max_combo']
    ret_json['cs'] = float(bmap.cs)
    ret_json['od'] = float(bmap.od)
    ret_json['ar'] = float(bmap.ar)
    ret_json['hp'] = float(bmap.hp)
    _, ar_mod, od_mod, cs_mod, hp_mod = pyttanko.mods_apply(mods, 
        ar=bmap.ar, od=bmap.od, cs=bmap.cs, hp=bmap.hp)
    ret_json['cs'+key_append] = float(cs_mod)
    ret_json['od'+key_append] = float(od_mod)
    ret_json['ar'+key_append] = float(ar_mod)
    ret_json['hp'+key_append] = float(hp_mod)

    ret_json['accs'] = accs
    ret_json['pp'+key_append] = []
    ret_json['aim_pp'+key_append] = []
    ret_json['speed_pp'+key_append] = []
    ret_json['acc_pp'+key_append] = [] 

    ret_json["hit_length"+key_append], _ = time_mod(
        beatmap_info["hit_length"], beatmap_info['bpm'], mods)
    ret_json["total_length"+key_append], ret_json["bpm_mod"] = \
        time_mod(beatmap_info["total_length"], beatmap_info['bpm'], mods)

    for acc in accs:
        misses = 0
        n300, n100, n50 = pyttanko.acc_round(acc, len(bmap.hitobjects), misses)
        pp, aim_pp, speed_pp, acc_pp, _ = pyttanko.ppv2(
            stars.aim, stars.speed, bmap=bmap, mods=mods,
            n300=n300, n100=n100, n50=n50, nmiss=misses, combo=bmap.max_combo())
        ret_json['pp'+key_append].append(float(pp))
        ret_json['aim_pp'+key_append].append(float(aim_pp))
        ret_json['speed_pp'+key_append].append(float(speed_pp))
        ret_json['acc_pp'+key_append].append(float(acc_pp))
    
    ret_json['extra_info'] = {}
    if extra_info:
        if 'play_info' in extra_info.keys():
            play_info = extra_info['play_info']

            # clean up the data
            for hit_type in ['300', '100', '50', 'miss', 'geki', 'katu']:
                if 'count_{}'.format(hit_type) not in play_info.keys():
                    play_info['count_{}'.format(hit_type)] = 0

            # get fc data
            fc_info = {}
            missing_hits = int(bmap.max_combo()) - (
                int(play_info['count_300']) + int(play_info['count_100']) + \
                int(play_info['count_50']) + int(play_info['count_miss']))
            fc_info['count_300'] = int(play_info['count_300']) + \
                int(play_info['count_miss']) + missing_hits
            fc_info['count_100'] = int(play_info['count_100'])
            fc_info['count_50'] = int(play_info['count_50'])
            fc_info['count_miss'] = 0
            ret_json['extra_info']['fc_pp'], _, _, _, _ = pyttanko.ppv2(
                stars.aim, stars.speed, bmap=bmap, mods=mods,
                n300=fc_info['count_300'], n100=fc_info['count_100'], 
                n50=fc_info['count_50'], nmiss=fc_info['count_miss'], 
                combo=int(bmap.max_combo()))
            ret_json['extra_info']['fc_acc'] = float(utils.calculate_acc(fc_info, 0))

            # calculate play pp
            total_hits = int(play_info['count_300']) + int(play_info['count_geki']) + \
                    int(play_info['count_100']) + int(play_info['count_katu']) + \
                    int(play_info['count_50'])
            total_misses = int(play_info['count_miss']) # + bmap.max_combo() - total_hits
            ret_json['extra_info']['play_pp'], _, _, _, _ = pyttanko.ppv2(
                stars.aim, stars.speed, bmap=bmap, mods=mods,
                n300=int(play_info['count_300']) + int(play_info['count_geki']), 
                n100=int(play_info['count_100']) + int(play_info['count_katu']), 
                n50=int(play_info['count_50']), nmiss=total_misses, 
                combo=int(play_info['max_combo']))
            ret_json['extra_info']['play_acc'] = float(utils.calculate_acc(play_info, 0))

            # get map completion
            if play_info['rank'] == 'F':
                completion_hits = int(play_info['count_50']) + \
                int(play_info['count_100']) + \
                int(play_info['count_300']) + \
                int(play_info['count_miss'])

                numobj = completion_hits - 1
                timing = int(bmap.hitobjects[-1].time) - int(bmap.hitobjects[0].time)
                point = int(bmap.hitobjects[numobj].time) - int(bmap.hitobjects[0].time)
                ret_json['extra_info']['map_completion'] = (point / timing) * 100
            else:
                ret_json['extra_info']['map_completion'] = 100

    return ret_json, bmap


async def get_droid_data(beatmap_info, bmp_parsed,
    accs=[95, 99, 100], mods=0, extra_info={}):

    bmap = bmp_parsed

    key_append = '_mod'
    beatmap_id = beatmap_info['beatmap_id']

    # let pyttanko handle calculations
    ret_json = {}
    # try:
    droid_mods = utils.num_to_droid_mod(mods)
    stars = droid_pyttanko.diff_calc().calc(bmap, mods=droid_mods)
    # except:
        # return beatmap_info, None

    ret_json['stars'+key_append] = float(stars.total)
    ret_json['aim_stars'+key_append] = float(stars.aim)
    ret_json['speed_stars'+key_append] = float(stars.speed)
    # print(beatmap_info.keys())
    if 'max_combo' not in beatmap_info:
        # print('Using parsed max combo')
        ret_json['max_combo'] = bmap.max_combo()
    else:
        # print('Using bmp max combo')
        ret_json['max_combo'] = beatmap_info['max_combo']
    ret_json['cs'] = float(bmap.cs)
    ret_json['od'] = float(bmap.od)
    ret_json['ar'] = float(bmap.ar)
    ret_json['hp'] = float(bmap.hp)
    _, ar_mod, od_mod, cs_mod, hp_mod = droid_pyttanko.mods_apply(droid_mods, 
        ar=bmap.ar, od=bmap.od, cs=bmap.cs, hp=bmap.hp)
    ret_json['cs'+key_append] = float(cs_mod)
    ret_json['od'+key_append] = float(od_mod)
    ret_json['ar'+key_append] = float(ar_mod)
    ret_json['hp'+key_append] = float(hp_mod)

    ret_json['accs'] = accs
    ret_json['pp'+key_append] = []
    ret_json['aim_pp'+key_append] = []
    ret_json['speed_pp'+key_append] = []
    ret_json['acc_pp'+key_append] = [] 

    ret_json["hit_length"+key_append], _ = time_mod(
        beatmap_info["hit_length"], beatmap_info['bpm'], mods)
    ret_json["total_length"+key_append], ret_json["bpm_mod"] = \
        time_mod(beatmap_info["total_length"], beatmap_info['bpm'], mods)

    for acc in accs:
        misses = 0
        n300, n100, n50 = droid_pyttanko.acc_round(acc, len(bmap.hitobjects), misses)
        pp, aim_pp, speed_pp, acc_pp, _ = droid_pyttanko.ppv2(
            stars.aim, stars.speed, bmap=bmap, mods=droid_mods,
            n300=n300, n100=n100, n50=n50, nmiss=misses, combo=bmap.max_combo())
        ret_json['pp'+key_append].append(float(pp))
        ret_json['aim_pp'+key_append].append(float(aim_pp))
        ret_json['speed_pp'+key_append].append(float(speed_pp))
        ret_json['acc_pp'+key_append].append(float(acc_pp))
    
    ret_json['extra_info'] = {}
    if extra_info:
        if 'play_info' in extra_info.keys():
            play_info = extra_info['play_info']

            # clean up the data
            for hit_type in ['300', '100', '50', 'miss', 'geki', 'katu']:
                if 'count_{}'.format(hit_type) not in play_info.keys():
                    play_info['count_{}'.format(hit_type)] = 0

            # get fc data
            fc_info = {}
            fc_info['count_300'] = int(play_info['count_300']) + \
                int(play_info['count_miss'])
            fc_info['count_100'] = int(play_info['count_100'])
            fc_info['count_50'] = int(play_info['count_50'])
            fc_info['count_miss'] = 0
            ret_json['extra_info']['fc_pp'], _, _, _, _ = droid_pyttanko.ppv2(
                stars.aim, stars.speed, bmap=bmap, mods=droid_mods,
                n300=fc_info['count_300'], n100=fc_info['count_100'], 
                n50=fc_info['count_50'], nmiss=fc_info['count_miss'], 
                combo=int(bmap.max_combo()))
            ret_json['extra_info']['fc_acc'] = float(utils.calculate_acc(fc_info, 0))

            # calculate play pp
            total_hits = int(play_info['count_300']) + int(play_info['count_geki']) + \
                    int(play_info['count_100']) + int(play_info['count_katu']) + \
                    int(play_info['count_50'])
            total_misses = int(play_info['count_miss']) # + bmap.max_combo() - total_hits
            ret_json['extra_info']['play_pp'], _, _, _, _ = droid_pyttanko.ppv2(
                stars.aim, stars.speed, bmap=bmap, mods=droid_mods,
                n300=int(play_info['count_300']) + int(play_info['count_geki']), 
                n100=int(play_info['count_100']) + int(play_info['count_katu']), 
                n50=int(play_info['count_50']), nmiss=total_misses, 
                combo=int(play_info['max_combo']))
            ret_json['extra_info']['play_acc'] = float(utils.calculate_acc(play_info, 0))

            # get map completion
            if play_info['rank'] == 'F':
                completion_hits = int(play_info['count_50']) + \
                int(play_info['count_100']) + \
                int(play_info['count_300']) + \
                int(play_info['count_miss'])

                numobj = completion_hits - 1
                timing = int(bmap.hitobjects[-1].time) - int(bmap.hitobjects[0].time)
                point = int(bmap.hitobjects[numobj].time) - int(bmap.hitobjects[0].time)
                ret_json['extra_info']['map_completion'] = (point / timing) * 100
            else:
                ret_json['extra_info']['map_completion'] = 100

    return ret_json, bmap


def time_mod(length_sec, bpm, mod_num):
    length_sec = float(length_sec)
    bpm = float(bpm)
    mod_list = utils.num_to_mod(mod_num)

    if 'DT' in mod_list or 'NC' in mod_list:
        factor = 3/2
    elif 'HT' in mod_list:
        factor = 2/3
    else:
        factor = 1

    length_mod, bpm_mod = length_sec/factor, bpm*factor
    return length_mod, bpm_mod


async def get_rec_data(map_id:str, accs=[100], mods=0, misses=0, combo=None,
    completion=None, fc=None, plot = False, color = 'blue', gamemode = 0):
    try:
        file_path = 'cogs/osu/beatmaps/{}.osu'.format(map_id) # some unique filepath
        bmap = pyttanko.parser().map(open(file_path))
    except:
        url = 'https://osu.ppy.sh/osu/{}'.format(map_id)
        file_id = random.randint(0,50)
        file_path = 'cogs/osu/temp/{}.osu'.format(file_id) # some unique filepath
        fc_pp = 0
        # await download_file(url, file_path) # this is the file name that it downloaded
        return
        bmap = pyttanko.parser().map(open(file_path))
        print(f"Downloading {map_id}")

    stars = pyttanko.diff_calc().calc(bmap, mods=mods)
    bmap.stars = stars.total
    bmap.aim_stars = stars.aim
    bmap.speed_stars = stars.speed

    if not combo:
        combo = bmap.max_combo()

    bmap.pp = []
    bmap.aim_pp = []
    bmap.speed_pp = []
    bmap.acc_pp = []

    bmap.acc = accs

    for acc in accs:
        n300, n100, n50 = pyttanko.acc_round(acc, len(bmap.hitobjects), misses)
        pp, aim_pp, speed_pp, acc_pp, _ = pyttanko.ppv2(
            bmap.aim_stars, bmap.speed_stars, bmap=bmap, mods=mods,
            n300=n300, n100=n100, n50=n50, nmiss=misses, combo=combo)
        bmap.pp.append(pp)
        bmap.aim_pp.append(aim_pp)
        bmap.speed_pp.append(speed_pp)
        bmap.acc_pp.append(acc_pp)

    _, ar, od, cs, hp = pyttanko.mods_apply(mods, ar=bmap.ar, od=bmap.od,
        cs=bmap.cs, hp=bmap.hp)

    # print('THIS IS THE BPM AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA', bmap.bpm)
    # print(map_id, str(bmap.pp))
    ret_json = {
        'mode': bmap.mode, # bmap.mode
        'stars': bmap.stars, # stars.total
        'pp': bmap.pp, # list
        'acc': bmap.acc, # list
        'cs': cs, # bmap.cs
        'od': od, # bmap.od
        'ar': ar, # bmap.ar
        'hp': hp, # bmap.hp
        }
    return ret_json


# ------- taiko pp -------------
async def get_taiko_data(beatmap_info, accs=[95, 99, 100], mods=0, extra_info={}):
    key_append = '_mod'
    beatmap_id = beatmap_info['beatmap_id']
    """
    file_path = await download_beatmap(beatmap_id, 
        status=handle_status(beatmap_info))"""

    mods_list = utils.num_to_mod(mods)    

    ret_json = {}
    ret_json['accs'] = accs
    # handle mod specifics
    if 'beatmap_mod' in extra_info.keys():
        beatmap_mod = extra_info['beatmap_mod']
    else:
        beatmap_mod = beatmap_info

    ret_json["stars"+key_append] = float(beatmap_mod['difficulty_rating'])
    ret_json["hit_length"+key_append], _ = time_mod(
        beatmap_mod["hit_length"], beatmap_mod['bpm'], mods)
    ret_json["total_length"+key_append], ret_json["bpm_mod"] = time_mod(
        beatmap_mod["total_length"], beatmap_mod['bpm'], mods)
    ret_json['pp'+key_append] = await _get_taiko_pp(beatmap_info, beatmap_mod, mods=mods)
    ret_json['cs'+key_append] = beatmap_mod['cs']
    ret_json['od'+key_append] = beatmap_mod['od']
    ret_json['ar'+key_append] = beatmap_mod['ar']
    ret_json['hp'+key_append] = beatmap_mod['hp']

    ret_json['extra_info'] = {}
    if extra_info:
        if 'play_info' in extra_info.keys():
            play_info = extra_info['play_info']

            # print(play_info)

            # get fc data
            fc_info = {}
            fc_info['count_300'] = int(play_info['count_300']) + \
                int(play_info['count_miss'])
            fc_info['count_100'] = int(play_info['count_100'])
            fc_info['count_50'] = int(play_info['count_50'])
            fc_info['count_miss'] = 0
            fc_pp = await _get_taiko_pp(beatmap_info, beatmap_mod,
                play_info=fc_info)
            ret_json['extra_info']['fc_pp'] = fc_pp[0]
            ret_json['extra_info']['fc_acc'] = float(utils.calculate_acc(fc_info, 1))

            # calculate play pp
            total_hits = int(play_info['count_300']) + int(play_info['count_geki']) + \
                    int(play_info['count_100']) + int(play_info['count_katu']) + \
                    int(play_info['count_50'])
            total_misses = int(play_info['count_miss']) # + bmap.max_combo() - total_hits
            play_pp = await _get_taiko_pp(beatmap_info, beatmap_mod,
                play_info=play_info)
            ret_json['extra_info']['play_pp'] = play_pp[0]
            ret_json['extra_info']['play_acc'] = float(utils.calculate_acc(play_info, 1))

    return ret_json, None


async def _get_taiko_pp(beatmap_info, beatmap_mod, 
    mods=0, play_info=None, accs=[95,99,100]):
    mods_list = utils.num_to_mod(mods)

    stars = float(beatmap_mod['difficulty_rating'])
    try:
        total_hits = int(beatmap_info['count_circles'])
    except:
        total_hits = int(beatmap_info['max_combo'])
    od_mod = _get_hit_window(float(beatmap_info['od']), mods_list)
    max_combo = total_hits

    strain = float(beatmap_info['difficulty_rating'])
    try:
        hit_count = int(beatmap_info['count_circles'])
    except:
        hit_count = int(beatmap_info['max_combo'])

    if hit_count == 0: # avoid division by 0?..
        hit_count = 1500

    if play_info:
        misses = int(play_info['count_miss'])
    else:
        misses = 0
    usercombo = hit_count - misses

    final_pp = []
    for acc in accs:
        hundreds = round((1 - misses/hit_count - acc/100) * 2 * hit_count)

        strain_value = math.pow(max(1, strain/0.0075) * 5 - 4,2)/100000
        length_bonus = min(1, hit_count/1500) * 0.1 + 1
        strain_value *= length_bonus
        strain_value *= math.pow(0.985, misses)
        strain_value *= min(math.pow(usercombo, 0.5) / math.pow(hit_count,0.5),1)
        strain_value *= acc/100
        acc_value = math.pow(150/od_mod,1.1) * math.pow(acc/100,15) * 22
        acc_value *= min(math.pow(hit_count/1500,0.3),1.15)

        mod_multiplier = 1.10
        if "HD" in mods_list:
            mod_multiplier *= 1.10
            strain_value *= 1.025
        if "NF" in mods_list:
            mod_multiplier *= 0.90
        if "FL" in mods_list:
            strain_value *= 1.05 * length_bonus

        total_value = math.pow(math.pow(strain_value,1.1) + \
            math.pow(acc_value,1.1),1.0/1.1) * mod_multiplier
        pp = round(total_value * 100) / 100
        final_pp.append(pp)

    return final_pp


def _scale_od(od, mod_list):
    if "EZ" in mod_list:
        od /= 2
    if "HR" in mod_list:
        od *= 1.4
    od = max(min(od, 10), 0)
    return od


def _get_hit_window(od, mod_list):
    od = _scale_od(od, mod_list)
    max_val = 20
    min_val = 50
    result = min_val + (max_val - min_val) * od / 10
    result = math.floor(result) - 0.5
    
    if "HT" in mod_list:
        result /= 0.75
    if "DT" in mod_list:
        result /= 1.5

    # 2 decimals
    return round(result * 100) / 100


# ------- ctb pp -------------
async def get_ctb_data(beatmap_info, accs=[95, 99, 100], mods=0, extra_info={}):
    key_append = '_mod'
    beatmap_id = beatmap_info['beatmap_id']

    """
    file_path = await download_beatmap(beatmap_id, 
        status=handle_status(beatmap_info))""" 

    mods_list = utils.num_to_mod(mods)    

    ret_json = {}
    ret_json['accs'] = accs
    # handle mod specifics
    if 'beatmap_mod' in extra_info.keys():
        beatmap_mod = extra_info['beatmap_mod']
    else:
        beatmap_mod = beatmap_info

    ret_json["stars"+key_append] = float(beatmap_mod['difficulty_rating'])
    if "HR" in mods_list:
        ret_json["stars"+key_append] *= 1.23
    if "DT" in mods_list:
        ret_json["stars"+key_append] *= 1.46

    ret_json["hit_length"+key_append], _ = time_mod(
        beatmap_mod["hit_length"], beatmap_mod['bpm'], mods)
    ret_json["total_length"+key_append], ret_json["bpm_mod"] = time_mod(
        beatmap_mod["total_length"], beatmap_mod['bpm'], mods)
    ret_json['pp'+key_append] = await _get_ctb_pp(beatmap_info, beatmap_mod, mods=mods)
    ret_json['cs'+key_append] = beatmap_mod['cs']
    ret_json['od'+key_append] = beatmap_mod['od']
    ret_json['ar'+key_append] = beatmap_mod['ar']
    ret_json['hp'+key_append] = beatmap_mod['hp']

    ret_json['extra_info'] = {}
    if extra_info:
        if 'play_info' in extra_info.keys():
            play_info = extra_info['play_info']

            # print(play_info)

            # get fc data
            fc_info = {}
            fc_info['count_300'] = int(play_info['count_300']) + \
                int(play_info['count_miss'])
            fc_info['count_100'] = int(play_info['count_100'])
            fc_info['count_50'] = int(play_info['count_50'])
            fc_info['count_miss'] = 0
            fc_info['max_combo'] = int(play_info['max_combo'])
            fc_pp = await _get_ctb_pp(beatmap_info, beatmap_mod,
                play_info=fc_info)
            ret_json['extra_info']['fc_pp'] = fc_pp[0]
            ret_json['extra_info']['fc_acc'] = float(utils.calculate_acc(fc_info, 1))

            # calculate play pp
            total_hits = int(play_info['count_300']) + int(play_info['count_geki']) + \
                    int(play_info['count_100']) + int(play_info['count_katu']) + \
                    int(play_info['count_50'])
            total_misses = int(play_info['count_miss']) # + bmap.max_combo() - total_hits
            play_pp = await _get_ctb_pp(beatmap_info, beatmap_mod,
                play_info=play_info)
            ret_json['extra_info']['play_pp'] = play_pp[0]
            ret_json['extra_info']['play_acc'] = float(utils.calculate_acc(play_info, 1))

    return ret_json, None


async def _get_ctb_pp(beatmap_info, beatmap_mod, play_info=None, accs=[95, 99, 100], mods=0):
    # adapated from https://pakachan.github.io/osustuff/ppcalculator.html
    mods_list = utils.num_to_mod(mods)

    stars = float(beatmap_mod['difficulty_rating'])
    if stars == 0:
        stars = float(beatmap_info['difficulty_rating'])
    if "HR" in mods_list:
        stars *= 1.23
    if "DT" in mods_list:
        stars *= 1.46
    
    if 'max_combo' in beatmap_info and beatmap_info['max_combo']:
        max_combo = int(beatmap_info['max_combo'])
    else:
        try:
            max_combo = int(beatmap_info['count_circles']) + \
                int(beatmap_info['count_sliders']) + \
                int(beatmap_info['count_spinners'])
        except:
            return [0] * len(accs)

    od = float(beatmap_mod['od'])
    ar = float(beatmap_mod['ar'])

    # print(play_info)
    if play_info:
        combo = int(play_info['max_combo']) # player combo
        misses = int(play_info['count_miss'])
    else:
        combo = max_combo
        misses = 0

    # print('Stars', stars)
    final_pp = []
    for acc in accs:
        # Conversion from Star rating to pp
        final = math.pow(((5*stars/0.0049)-4), 2)/100000 
        # Length Bonus
        lengthbonus = (0.95 + 0.3 * min(1.0, max_combo / 2500.0))
        if max_combo > 2500:
            lengthbonus += math.log10(max_combo / 2500.0) * 0.475
        final *= lengthbonus
        # Miss Penalty
        final *= math.pow(0.97, misses)
        # Not FC combo penalty
        final *= math.pow(combo/max_combo, 0.8)
        # AR Bonus
        ar_bonus = 1
        if ar > 9:
            ar_bonus += 0.1 * (ar - 9.0)
        if ar > 10:
            ar_bonus += 0.1 * (ar - 10.0)
        if ar < 8:
            ar_bonus += 0.025 * (8.0 - ar)
        final *= ar_bonus
        # Hidden bonus
        hidden_bonus = 1
        if ar > 10:
            hidden_bonus = 1.01 + 0.04 * (11 - min(11, ar))
        else:
            hidden_bonus = 1.05 + 0.075 * (10 - ar)
        # Acc Penalty
        final *= math.pow(acc/100, 5.5)

        # mod bonuses
        if "HD" in mods_list:
            final *= hidden_bonus
        if "FL" in mods_list:
            final *= 1.35

        final_pp.append(final)

    return final_pp


# -------------- mania pp ------------------
async def get_mania_data(beatmap_info, accs=[95, 99, 100], mods=0, extra_info={}):
    key_append = '_mod'
    beatmap_id = beatmap_info['beatmap_id']

    """
    file_path = await download_beatmap(beatmap_id, 
        status=handle_status(beatmap_info))"""

    mods_list = utils.num_to_mod(mods)    

    ret_json = {}
    ret_json['accs'] = accs
    # handle mod specifics
    if 'beatmap_mod' in extra_info.keys():
        beatmap_mod = extra_info['beatmap_mod']
    else:
        beatmap_mod = beatmap_info

    ret_json["stars"+key_append] = float(beatmap_mod['difficulty_rating'])

    ret_json["hit_length"+key_append], _ = time_mod(
        beatmap_mod["hit_length"], beatmap_mod['bpm'], mods)
    ret_json["total_length"+key_append], ret_json["bpm_mod"] = time_mod(
        beatmap_mod["total_length"], beatmap_mod['bpm'], mods)
    ret_json['pp'+key_append] = await _get_mania_pp(beatmap_mod, mods=mods, accs=accs)
    ret_json['cs'+key_append] = beatmap_mod['cs']
    ret_json['od'+key_append] = beatmap_mod['od']
    ret_json['ar'+key_append] = beatmap_mod['ar']
    ret_json['hp'+key_append] = beatmap_mod['hp']

    if 'DT' in mods_list: # regression fit
        ret_json["stars"+key_append] = 1.45 * ret_json["stars"+key_append] - 0.2

    ret_json['extra_info'] = {}
    if extra_info:
        if 'play_info' in extra_info.keys():
            play_info = extra_info['play_info']

            # print(play_info)

            # get fc data
            # print('fc data')
            fc_info = {}
            fc_info['count_300'] = int(play_info['count_300']) + \
                int(play_info['count_miss'])
            fc_info['count_100'] = int(play_info['count_100'])
            fc_info['count_50'] = int(play_info['count_50'])
            fc_info['count_miss'] = 0
            fc_pp = await _get_mania_pp(beatmap_info, mods=mods,
                play_info=fc_info)
            ret_json['extra_info']['fc_pp'] = fc_pp[0]
            ret_json['extra_info']['fc_acc'] = float(utils.calculate_acc(fc_info, 1))

            # calculate play pp
            # print('play data')
            total_hits = int(play_info['count_300']) + int(play_info['count_geki']) + \
                    int(play_info['count_100']) + int(play_info['count_katu']) + \
                    int(play_info['count_50'])
            total_misses = int(play_info['count_miss']) # + bmap.max_combo() - total_hits
            play_pp = await _get_mania_pp(beatmap_info, mods=mods,
                play_info=play_info)
            ret_json['extra_info']['play_pp'] = play_pp[0]
            ret_json['extra_info']['play_acc'] = float(utils.calculate_acc(play_info, 1))

    return ret_json, None


async def _get_mania_pp(beatmap_info, play_info=None, accs=[95, 99, 100], mods=0):
    # calculate full pp
    # adapated from https://pcca.nctu.me/ompp
    # print(mods)
    mods_list = utils.num_to_mod(mods)

    if 'max_combo' in beatmap_info and beatmap_info['max_combo']:
        objects_count = int(beatmap_info['max_combo'])
    else:
        try:
            objects_count = int(beatmap_info['count_circles']) + \
                int(beatmap_info['count_sliders'])
        except:
            return [0] * len(accs)
    """
    try:
        objects_count = int(beatmap_info['count_circles']) + int(beatmap_info['count_sliders'])
    except:
        return [0]"""

    od = float(beatmap_info['od'])
    stars = float(beatmap_info['difficulty_rating'])
    if 'DT' in mods_list: # regression fit
        stars = 1.45 * stars - 0.2

    if not play_info or 'score' not in play_info:
        score = 1000000
    else:
        score = float(play_info['score'])

    # score multiplier
    score_rate = 1
    if "EZ" in mods_list:
        score_rate *= 0.5
    if "NF" in mods_list:
        score_rate *= 0.5
    if "HT" in mods_list:
        score_rate *= 0.5

    real_score = score # / score_rate # calculation

    hit300_window = 34 + 3 * (min(10, max(0, 10 - od)))
    strain_value = (5 * max(1, stars / 0.2) - 4) ** 2.2 / 135 * (1 + 0.1 * min(1, objects_count / 1500))
    if real_score <= 500000:
        strain_value = 0
    elif real_score <= 600000:
        strain_value *= (real_score - 500000) / 100000 * 0.3
    elif real_score <= 700000:
        strain_value *= 0.3 + (real_score - 600000) / 100000 * 0.25
    elif real_score <= 800000:
        strain_value *= 0.55 + (real_score - 700000) / 100000 * 0.20
    elif real_score <= 900000:
        strain_value *= 0.75 + (real_score - 800000) / 100000 * 0.15
    else:
        strain_value *= 0.9 + (real_score - 900000) / 100000 * 0.1

    acc_value = max(0, 0.2 - ((hit300_window - 34) * 0.006667)) * strain_value * \
        (max(0, real_score - 960000) / 40000) ** 1.1

    pp_multiplier = 0.8
    if 'NF' in mods_list:
        pp_multiplier *= 0.9
    if 'EZ' in mods_list:
        pp_multiplier *= 0.5

    pp_full = (strain_value ** 1.1 + acc_value ** 1.1) ** (1 / 1.1) * pp_multiplier

    final_pp = []
    for acc in accs:
        final_pp.append(pp_full * (acc/100))
    return final_pp


# ----------------- map plotting functions -----------------------
async def plot_life_bar(data, color = 'blue', mapset_id=None):
    # potential background
    # https://assets.ppy.sh/beatmaps/825377/covers/card@2x.jpg?
    comp = data.split(',')
    x = []
    lb = []
    for tick in comp:
        xy = tick.split("|")
        if len(xy) == 2: # corner case
            x.append(float(xy[0]))
            lb.append(float(xy[1]))

    fig = plt.figure(figsize=(6.2, 1.70))

    plt.rcParams['text.antialiased'] = True
    ax = fig.add_subplot(111)
    plt.style.use('ggplot')
    ax.xaxis.label.set_color(color)
    ax.yaxis.label.set_color(color)
    fig.gca().xaxis.grid(True)
    fig.gca().yaxis.grid(False)

    ax.tick_params(axis='both', colors=color, labelcolor = color)
    # ax.imshow(img, extent = [0, max(x), 0, 1.1])
    ax.plot(x, lb, color=color, label='Life bar', linewidth=2, antialiased=True)
    fig.gca().xaxis.set_major_formatter(ticker.FuncFormatter(plot_time_format))
    fig.gca().xaxis.grid(True)
    fig.gca().yaxis.grid(False)

    # ax.set_xticks([])
    ax.set_yticks([])
    ax.set_ybound(lower=0, upper=1.05)
    ax.legend(loc='lower right')
    fig.tight_layout()

    img_id = random.randint(0, 20)
    filepath = "cogs/osu/temp/replay_{}.png".format(img_id)

    fig.savefig(filepath, transparent=True)
    plt.close()

    # if we have a background image...
    bg_success = False
    if mapset_id:
        # get images
        try:
            background, bg_success = await _get_map_image(mapset_id)
            foreground = Image.open(filepath).convert('RGBA')
            dropshadow = foreground.copy()
            # create dropshadow for the graph
            datas = foreground.getdata()
            new_data = list()
            for item in datas:
                if item[3] != 0:
                    new_data.append((0,0,0,255))
                else:
                    new_data.append(item)
            dropshadow.putdata(new_data)
            # dropshadow.save('cogs/osu/temp/dropshadow1.png')
            dropshadow = dropshadow.filter(ImageFilter.GaussianBlur(10))
            # dropshadow.save('cogs/osu/temp/dropshadow2.png')
            # print(dropshadow.size, foreground.size)
            dropshadow = Image.alpha_composite(dropshadow, foreground)
            # dropshadow.paste(foreground, (0, 0), foreground)
            foreground = dropshadow
            #foreground = Image.alpha_composite(foreground, dropshadow)

            foreground = foreground.crop((9, 7, foreground.size[0], foreground.size[1]))
            background = background.resize((800, 200))
            background = background.crop((100, 35, 700, 185))
            background = ImageEnhance.Brightness(background).enhance(0.50)
            background = ImageEnhance.Sharpness(background).enhance(0.75)
            # background = Image.alpha_composite(foreground, background.convert('RGBA'))
            background.paste(foreground, (0, 0), foreground)
            background.save(filepath, transparent=True)
        except:
            pass

    f = discord.File(filepath, filename="replay_{}.png".format(img_id))
    url = 'attachment://' + "replay_{}.png".format(img_id)

    return f, url


# Returns url to uploaded stars graph
async def plot_map_stars(bmap_chunks, bmap_info, mods=0, color='blue'):
    star_list, speed_list, aim_list, time_list = [], [], [], []

    for chunk in bmap_chunks:
        time_list.append(chunk['time'])
        star_list.append(chunk['stars'])
        aim_list.append(chunk['aim_stars'])
        speed_list.append(chunk['speed_stars'])

    fig = plt.figure(figsize=(6.3, 1.70))
    plt.rcParams['text.antialiased'] = True
    ax = fig.add_subplot(111)
    plt.style.use('ggplot')
    ax.plot(time_list, star_list, color=color, linewidth=2, antialiased=True)
    if 'extra_info' in bmap_info.keys() and \
        'map_completion' in bmap_info['extra_info'].keys() and \
        bmap_info['extra_info']['map_completion'] != 100:
        completion = float(bmap_info['extra_info']['map_completion'])
        p_comp = completion/100
        mark_index = round(len(time_list)*p_comp)
        x_mark = time_list[mark_index]
        y_mark = star_list[mark_index]
        ax.plot(x_mark, y_mark, linestyle='None', marker='o', markersize=12,
            markeredgewidth=1, markeredgecolor="white",
            markerfacecolor=color, label="{:.2f}%".format(completion))
        ax.legend(loc='best')

    fig.gca().xaxis.set_major_formatter(ticker.FuncFormatter(plot_time_format))
    fig.gca().xaxis.grid(True)
    fig.gca().yaxis.grid(False)
    # plt.xlim([-10, max(time_list)+10])
    # fig.gca().ylim([0, y_max])
    # plt.ylabel('Stars')
    fig.tight_layout()
    ax.xaxis.label.set_color(color)
    ax.set_yticks([])
    ax.set_yticklabels([])
    ax.get_yaxis().set_visible(False)

    # ax.yaxis.label.set_color(color)
    ax.tick_params(axis='both', colors=color, labelcolor = color)
    # ax.grid(color='w', linestyle='-', linewidth=1)

    img_id = random.randint(0, 50)
    filepath = "cogs/osu/temp/map_{}.png".format(img_id)
    fig.savefig(filepath, transparent=True)
    plt.close()

    # if we have a background image...
    mapset_id = bmap_info['beatmapset_id']

    bg_success = False

    # get images
    background, bg_success = await _get_map_image(mapset_id)
    foreground = Image.open(filepath).convert('RGBA')
    dropshadow = foreground.copy()
    # create dropshadow for the graph
    datas = foreground.getdata()
    new_data = list()
    for item in datas:
        if item[3] != 0:
            new_data.append((0,0,0,255))
        else:
            new_data.append(item)
    dropshadow.putdata(new_data)
    dropshadow = dropshadow.filter(ImageFilter.GaussianBlur(10))
    dropshadow = Image.alpha_composite(dropshadow, foreground)
    foreground = dropshadow

    foreground = foreground.crop((23, 8, foreground.size[0], foreground.size[1]))
    background = background.resize((800, 200))
    background = background.crop((100, 35, 700, 185))
    background = ImageEnhance.Brightness(background).enhance(0.50)
    background = ImageEnhance.Sharpness(background).enhance(0.75)
    # background = Image.alpha_composite(foreground, background.convert('RGBA'))
    background.paste(foreground, (0, 0), foreground)
    background.save(filepath, transparent=True)

    discord_file = discord.File(filepath, filename="map_{}.png".format(img_id))
    url = 'attachment://' + "map_{}.png".format(img_id)

    return discord_file, url


async def _get_map_image(mapset_id):
    # also maintains length to 1500
    folder = f"cogs/osu/resources/beatmap_images"
    filename = f"{mapset_id}.jpg"
    file_path = f"{folder}/{filename}"

    # if it exists
    if os.path.exists(file_path):
        try:
            bg = Image.open(file_path)
            return bg, True
        except:
            pass

    # if it doesn't exist
    """
    config_data = fileIO("config.json", "load")
    official = config_data["API_KEYS"]["OSU"]["OFFICIAL"]
    username = official["USERNAME"]
    password = official["PASSWORD"]

    payload = {"username": username,
               "password": password,
               "redirect": "index.php",
               "sid": "",
               "login": "Login"}"""

    async with aiohttp.ClientSession() as session:
        # async with session.post('https://osu.ppy.sh/forum/ucp.php?mode=login', data = payload) as resp:
        # text = await resp.read()
        try:
            print("Attempting Download")
            bg, bg_success = await download_map_image_to_folder(mapset_id, session=session)
            # bg = Image.open("cogs/osu/resources/triangles_map.jpg")
            return bg, bg_success
            # return bg
        except:
            bg = Image.open(os.path.join(
                os.getcwd(), "cogs/osu/resources/triangles_map.jpg"))
            return bg, False


async def download_map_image_to_folder(mapset_id, session=None, limit=8000):
    # get map url from site
    folder = f"cogs/osu/resources/beatmap_images"
    file_path = f"{folder}/{mapset_id}.jpg"

    bg = None
    bg_success = False
    bg_images = []

    bg_images.append("https://assets.ppy.sh/beatmaps/{}/covers/card@2x.jpg?".format(mapset_id))
    # bg_images.append("https://assets.ppy.sh/beatmaps/{}/covers/cover.jpg".format(mapset_id))

    for bg_image in bg_images:
        async with session.get(bg_image) as r:
            image = await r.content.read()
        with open(file_path,'wb') as f:
            f.write(image)
        bg = Image.open(file_path)
        bg_success = True
        break
        # await asyncio.sleep(1)

    # if too many
    """
    path, dirs, files = next(os.walk(folder))
    file_count = len(files)
    if file_count > limit:
        delete_num = file_count - limit
        for i in range(delete_num):
            file = random.choice(files)
            delete_file = f"{folder}/{file}"
            if delete_file != file_path:
                os.remove(delete_file)"""
    return bg, bg_success


def plot_time_format(time, pos=None):
    s, mili = divmod(time, 1000)
    m, s = divmod(s, 60)
    return "%d:%02d" % (m, s)


async def _map_completion(btmap, totalhits=0):
    btmap = open(btmap, 'r').read()
    btmap = Beatmap(btmap)
    good = btmap.parse()
    if not good:
        raise ValueError("Beatmap verify failed. "
                         "Either beatmap is not for osu! standart, or it's malformed")
        return
    hitobj = []
    if totalhits == 0:
        totalhits = len(btmap.hit_objects)
    numobj = totalhits - 1
    num = len(btmap.hit_objects)
    for objects in btmap.hit_objects:
        hitobj.append(objects.time)
    timing = int(hitobj[num - 1]) - int(hitobj[0])
    point = int(hitobj[numobj]) - int(hitobj[0])
    map_completion = (point / timing) * 100
    return map_completion
