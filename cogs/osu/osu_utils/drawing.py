import os
import json
import random
import discord
import aiohttp
import asyncio
import zipfile
import aiofiles
import operator
import datetime
import pyttanko
import numpy as np
from PIL import Image
import scipy
from scipy import cluster
from bs4 import BeautifulSoup

import matplotlib as mpl
mpl.use('Agg') # for non gui
from matplotlib import ticker
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from cogs.osu.osu_utils import map_utils, web_utils, utils, owoAPI
from cogs.osu.osu_utils.chunks import chunks

async def plot_profile(user, color = 'blue'):
    rank_data = user['rank_history']["data"]
    replays_watched_counts = user["replays_watched_counts"]
    monthly_playcounts = user["monthly_playcounts"]

    if color == (0.0, 0.0, 0.0):
        color = (.8, .8, .8)

    other_color = (1, 0.647, 0)
    # print(luminance(other_color), luminance(color), luminance(other_color) - luminance(color))
    if abs(luminance(other_color) - luminance(color)) < .1:
        other_color = (1, 0.4, 0.667)

    base = datetime.datetime.today()
    date_list = [base - datetime.timedelta(days=x) for x in range(0, 89)]
    date_list = date_list[::-1]
    fig = plt.figure(figsize=(8, 4))
    plt.rcParams['text.antialiased'] = True
    ax = fig.add_subplot(211)
    plt.style.use('ggplot')
    ax.plot(date_list, rank_data[:-1], color=color, linewidth=3.0, antialiased=True, label='Rank (90 days)')
    ax.tick_params(axis='y', colors=color, labelcolor = color)
    ax.yaxis.label.set_color(color)
    ax.grid(color='w', linestyle='-', axis='y', linewidth=1)
    ax.legend(loc='best')
    rank_range = max(rank_data) - min(rank_data)
    plt.ylim(max(rank_data) + int(.15*rank_range), min(rank_data) - int(.15*rank_range))
    # plt.xticks([date_list[0], date_list[int(len(date_list-1)/2)], date_list[len(date_list)-1]])
    plt.xticks([])
    #plt.xaxis.label.set_color('white')
    #plt.yaxis.label.set_color('white')

    ax1 = fig.add_subplot(212)
    dates = []
    watched = []
    playcounts = []
    for point in replays_watched_counts:
        dates.append(point['start_date'])
        watched.append(point['count'])
    dates_list_replay = [datetime.datetime.strptime(date, '%Y-%m-%d').date() for date in dates]

    dates = []
    for point in monthly_playcounts:
        dates.append(point['start_date'])
        playcounts.append(point['count'])
    dates_list_playcount = [datetime.datetime.strptime(date, '%Y-%m-%d').date() for date in dates]
    xlabels = [dt.strftime('%m/%y') for dt in dates_list_playcount]
    #ax1.xaxis.set_major_locator(mdates.MonthLocator())
    #ax1.xaxis.set_minor_locator(mdates.DayLocator(bymonthday=(1,30)))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%y'))

    lns1 = ax1.plot(dates_list_replay, watched, '-', color=color, linewidth=3.0, label='Replays Watched')
    # Make the y-axis label, ticks and tick labels match the line color.
    ax1.tick_params('y', colors=color)

    ax2 = ax1.twinx()
    lns2 = ax2.plot(dates_list_playcount, playcounts, '-', color=other_color, linewidth=3.0, label='Play Hist.')
    ax2.tick_params('y', colors=other_color)
    ax2.tick_params('x', colors=(255, 255, 255))

    lns = lns1 + lns2
    labs = [l.get_label() for l in lns]
    ax2.legend(lns, labs, loc='best')
    ax1.grid(False)

    fig.tight_layout()

    img_id = random.randint(0, 50)
    foreground_filepath = "cogs/osu/temp/graph_{}.png".format(img_id)
    fig.savefig(foreground_filepath, transparent=True)
    plt.close()

    # download background image, use another as default
    if 'cover' in user and 'url' in user['cover']:
        bg_url = user['cover']['url']
    else:
        bg_url = 'https://i.imgur.com/dm47q3B.jpg'

    filepath = os.path.join(
        'cogs','osu','temp','profile_bg_{}.png'.format(img_id))
    await web_utils.download_file(user['cover']['url'], filepath)
    background = Image.open(filepath).convert('RGBA')

    # get images
    foreground = Image.open(foreground_filepath).convert('RGBA')
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

    # foreground = foreground.crop((23, 8, foreground.size[0], foreground.size[1]))
    target_size = (800, 400)
    min_side = min(background.width, background.height)
    scale_factor = target_size[0]/min_side

    background = background.resize(
        (round(background.width * scale_factor), 
            round(background.height * scale_factor)), Image.ANTIALIAS)
    # determine crop area
    center = (round(background.width/2), round(background.height/2))
    upper_left = (round(center[0] - target_size[0]/2), 
        round(center[1] - target_size[1]/2))
    bottom_right = (round(center[0] + target_size[0]/2), 
        round(center[1] + target_size[1]/2))
    background = background.crop((
        upper_left[0], upper_left[1], 
        bottom_right[0], bottom_right[1]))
    background = background.filter(ImageFilter.GaussianBlur(10))
    background = ImageEnhance.Brightness(background).enhance(0.50)
    # background = ImageEnhance.Sharpness(background).enhance(0.75)
    # background = Image.alpha_composite(foreground, background.convert('RGBA'))
    background.paste(foreground, (0, 0), foreground)
    background.save(filepath, transparent=True)

    discord_file = discord.File(filepath, filename="profile_{}.png".format(img_id))
    url = 'attachment://' + "profile_{}.png".format(img_id)

    return discord_file, url


async def draw_score(ctx, userinfo, userrecent, beatmap_info, gamemode, 
    beatmap_image_file=None, bmp_chunks=None, api_name='Bancho'):
    img_id = random.randint(0, 50)
    try:
        channel = ctx.message.channel
        user = ctx.message.author
        server = ctx.message.guild
    except:
        channel = ctx.channel
        user = ctx.author
        server = ctx.guild


    font_folder_root = os.path.join(os.path.abspath(os.getcwd()), 
        'cogs/osu/resources/fonts/')
    osu_folder_root = os.path.join(os.path.abspath(os.getcwd()),
        'cogs/osu/resources/')

    # get information for display
    full_title = beatmap_info['artist'] + ' - ' + beatmap_info['title']
    version = beatmap_info['version']
    play_date = userrecent['date']
    score = "{:,}".format(int(userrecent['score']))
    acc_num = utils.calculate_acc(userrecent, gamemode)
    acc = str(round(acc_num, 2))
    fc_acc_num = utils.no_choke_acc(userrecent, gamemode)
    fc_acc = str(round(fc_acc_num, 2))
    totalhits = (int(userrecent['count_50']) + int(userrecent['count_100']) +
        int(userrecent['count_300']) + int(userrecent['count_miss']))

    combo = int(userrecent['max_combo'])
    try:
        max_combo = int(beatmap_info['max_combo'])
    except:
        max_combo = None

    stars_float = float(beatmap_info['stars_mod'])
    if stars_float > 10:
        map_stars = str(round(stars_float, 1))
    else:
        map_stars = str(round(stars_float, 2))

    map_creator = beatmap_info['creator']
    mods = utils.fix_mod_list(utils.num_to_mod(userrecent['enabled_mods']))

    m1, s1, bpm_mod = utils.calc_time(beatmap_info['total_length'], beatmap_info['bpm'], 1)
    if 'DT' in mods or 'NC' in mods:
        m1, s1, bpm_mod = utils.calc_time(beatmap_info['total_length'], beatmap_info['bpm'], 1.5)
    elif 'HT' in mods:
        m1, s1, bpm_mod = utils.calc_time(beatmap_info['total_length'], beatmap_info['bpm'], (2/3))
    map_time = '{}:{}'.format(m1, str(s1).zfill(2))
    bpm = '{}'.format(round(bpm_mod))

    ar = str(round(beatmap_info['ar_mod'], 1))
    od = str(round(beatmap_info['od_mod'], 1))
    cs = str(round(beatmap_info['cs_mod'], 1))
    hp = str(round(beatmap_info['hp_mod'], 1))

    # try_num = int(userrecent['attempt'])
    rank = str(userrecent['rank']).upper()
    data = userrecent['date']
    if 'pp' in userrecent and userrecent['pp'] is not None and \
        int(userrecent['pp']) != 0:
        performance = round(userrecent['pp'])
    else:
        performance = round(beatmap_info['extra_info']['play_pp'])
    performance_max = round(beatmap_info['pp_mod'][2]) # for 100% 

    if gamemode == 0:
        score_hits = ['count_300', 'count_geki', 'count_100', 'count_katu', 'count_50', 'count_miss']
    elif gamemode == 1:
        score_hits = ['count_300', 'count_geki', 'count_100', 'count_katu', 'count_miss']
    elif gamemode == 2:
        score_hits = ['count_300', 'count_miss', 'count_100', None, 'count_50', None]
        # score_hits = ['count_300', 'count_geki', 'count_100', 'count_miss']
    elif gamemode == 3:
        score_hits = ['count_300', 'count_geki', 'count_100', 'count_katu', 'count_50', 'count_miss']

    num_score = []
    for hit_type in score_hits:
        if not hit_type:
            num_score.append(None)
        else:
            num_score.append(userrecent[hit_type])
    score_hits = num_score
    # print('SCORE HITS', score_hits)

    diff_name = _determine_emote_name(beatmap_info)
    username = userinfo['username']

    # draw image
    filename = 'cogs/osu/temp/score_{}.png'.format(img_id)

    # set canvas
    width = 1500
    height = 500
    width_center = width/2
    height_center = height/2
    default_color = (45, 45, 45, 230)
    canvas = Image.new('RGBA', (width, height), default_color)

    # get background image
    # background_filepath = 'test_images/background_' + str(bg_num) + '.jpg'
    # background_image = Image.open(background_filepath).convert('RGBA')
    background_image = Image.open(beatmap_image_file).convert('RGBA')
    # await get_full_map_image(beatmap_info['beatmapset_id'])
    resize_ratio = max(width/background_image.width, 
        height/background_image.height)
    background_image = background_image.resize(
        (round(resize_ratio*background_image.width), 
        round(resize_ratio*background_image.height)))
    left_bound = round(background_image.width - width)/2
    right_bound = background_image.width - left_bound
    background_image = background_image.crop(box=(left_bound,0,right_bound,height))
    background_image = background_image.resize((width, height), Image.ANTIALIAS)
    background_image = background_image.filter(ImageFilter.GaussianBlur(10))
    canvas.paste(background_image)

    # get rank image
    rank_left = 865
    rank_top = 120
    rank_width = 250
    rank_height = 250
    rank_filepath = os.path.join(osu_folder_root, f'ranks/{rank}.png')
    rank_image = Image.open(rank_filepath).convert('RGBA')
    resize_ratio = min(rank_width/rank_image.width, 
        rank_height/rank_image.height)
    rank_image = rank_image.resize((round(resize_ratio*rank_image.width), 
        round(resize_ratio*rank_image.height)), Image.ANTIALIAS)
    rank_canvas = Image.new('RGBA', (width, height))
    rank_canvas.paste(rank_image, (rank_left, rank_top))

    # generate graph
    color = (0, 200, 0, 255)
    percentage = 75
    graph = Image.new('RGBA', (240, 75))

    # set drawing canvas
    process = Image.new('RGBA', (width, height), default_color)
    draw = ImageDraw.Draw(process)
    text_canvas = Image.new('RGBA', (width, height))

    ## draw boxes
    # sidebar dims
    sidebar_width = 25
    vert_padding = 18
    horiz_padding = 15
    box_color = (40, 40, 40, 230)
    # title box
    main_left = sidebar_width + 1
    main_right = 1145
    title_box_top = vert_padding
    title_box_left = main_left
    title_box_bottom = 120
    title_box_right = main_right - horiz_padding
    draw.rectangle([(title_box_left,title_box_top),
        (title_box_right, title_box_bottom)], fill=box_color)

    # info box
    info_box_top = title_box_bottom + vert_padding - 3
    info_box_bottom = height - vert_padding
    info_box_left = main_left
    info_box_right = 830
    draw.rectangle([(info_box_left, info_box_top),
        (info_box_right, info_box_bottom)], fill=box_color)

    # pp box
    pp_box_top = 370
    pp_box_left = info_box_right + horiz_padding
    pp_box_bottom = height - vert_padding
    pp_box_right = main_right - horiz_padding
    # draw.rectangle([(pp_box_left, pp_box_top),
        # (pp_box_right, pp_box_bottom)], fill=box_color)
    # map box
    map_box_top = 0
    map_box_left = main_right
    map_box_bottom = height
    map_box_right = width
    draw.rectangle([(map_box_left, map_box_top),
        (map_box_right, map_box_bottom)], fill=box_color)

    ## write lables
    label_left = 40
    text_padding = label_left - sidebar_width
    label_mid_horiz = 390
    label_right = 620
    label_top = 150
    label_mid_vert = 260
    label_bottom = 370
    label_color = (200, 200, 200, 200)
    label_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 18)
    draw.text((label_left, label_top), 'SCORE', font=label_font, fill=label_color)
    draw.text((label_mid_horiz, label_top), 'ACCURACY', font=label_font, fill=label_color)
    draw.text((label_right, label_top), 'MODS', font=label_font, fill=label_color)
    draw.text((label_left, label_mid_vert), 'COMBO', font=label_font, fill=label_color)
    try_label_offset = 200
    # draw.text((label_left+try_label_offset, label_mid_vert), 'TRY', 
    #     font=label_font, fill=label_color)
    draw.text((label_left, label_bottom), 'GRAPH', font=label_font, fill=label_color)
    draw.text((pp_box_left+text_padding, label_bottom + 10), 'PERFORMANCE', 
        font=label_font, fill=label_color)
    map_label_top = 215
    map_label_left = map_box_left + text_padding

    small_label_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 16)
    small_label_left = map_label_left
    small_label_right = map_box_left + round((width - map_box_left)/2)
    small_label_top = 315
    small_label_bottom = label_bottom + 10
    draw.text((small_label_left, map_label_top), 'DIFFICULTY', 
        font=label_font, fill=label_color)
    # draw.text((small_label_right, map_label_top), 'BPM', 
        # font=label_font, fill=label_color)
    draw.text((small_label_left, small_label_top), 'AR', 
        font=small_label_font, fill=label_color)
    draw.text((small_label_right, small_label_top), 'OD', 
        font=small_label_font, fill=label_color)
    draw.text((small_label_left, small_label_bottom), 'HP', 
        font=small_label_font, fill=label_color)
    draw.text((small_label_right, small_label_bottom), 'CS', 
        font=small_label_font, fill=label_color)

    # get 300, 100, 50, x tag
    tag_canvas = Image.new('RGBA', (width, height))
    if gamemode == 0:
        score_images = ['score_300', 'score_g', 'score_100', 'score_k_g', 'score_50', 'score_x']
    elif gamemode == 1:
        score_images = ['score_300', 'score_g', 'score_100', 'score_k_g', 'score_x']
    elif gamemode == 2:
        score_images = ['score_ctb_fruit', 'score_x', 'score_ctb_big', None, 'score_ctb_small', None]
    elif gamemode == 3:
        score_images = ['score_300r', 'score_300', 'score_200', 'score_100', 'score_50', 'score_x']

    tag_width = 80
    tag_height = 80
    tag_left = label_mid_horiz - 5
    tag_right = label_right - 15
    tag_top = label_mid_vert - text_padding # - 5
    tag_bottom = 370
    tag_mid = round((tag_top + tag_bottom)/2)

    for i, file in enumerate(score_images):
        if not file:
            continue

        if i % 2 == 0: # first column
            h_coord = tag_left
        else:
            h_coord = tag_right - 5

        if i/2 < 1:
            v_coord = tag_top
        elif i/2 < 2:
            if gamemode == 2:
                v_coord = tag_mid + 5
            else:
                v_coord = tag_mid
        else:
            v_coord = tag_bottom

        tag_filename = os.path.join(osu_folder_root, 'hits/' + file + '.png')
        tag_image = Image.open(tag_filename).convert('RGBA')
        resize_ratio = min(tag_width/tag_image.width, 
            tag_height/tag_image.height)
        tag_image = tag_image.resize((round(resize_ratio*tag_image.width), 
            round(resize_ratio*tag_image.height)), Image.ANTIALIAS)

        temp_canvas_w_tag_image = Image.new("RGBA", tag_canvas.size)
        temp_canvas_w_tag_image.paste(tag_image, (h_coord, v_coord))

        # tag_canvas.paste(tag_image, (h_coord, v_coord)) # good
        tag_canvas = Image.alpha_composite(tag_canvas, temp_canvas_w_tag_image)

    # get diff image
    diff_left = main_left + text_padding - 1
    diff_top = 75
    diff_dim = 40
    letter_modes = ['s', 't', 'c', 'm']
    diff_filepath = os.path.join(osu_folder_root, 'mode_symbols/' + diff_name + '-'+ letter_modes[gamemode] + '.png')
    diff_image = Image.open(diff_filepath).convert('RGBA')
    diff_image = diff_image.resize((diff_dim, diff_dim), Image.ANTIALIAS) 
    diff_canvas = Image.new('RGBA', (width, height))
    diff_canvas.paste(diff_image, (diff_left, diff_top))

    # paste thumbnail image
    max_size = [325, 183]
    thumbnail_left = map_label_left
    thumbnail_top = title_box_top
    thumbnail_width = width - text_padding - thumbnail_left
    # get thumbnail/necessary for colors
    thumbnail_image = Image.open(beatmap_image_file).convert('RGBA') # await get_full_map_image(beatmap_info['beatmapset_id'])
    resize_ratio = thumbnail_width/thumbnail_image.width
    thumbnail_image = thumbnail_image.resize(
        (round(resize_ratio*thumbnail_image.width), 
        round(resize_ratio*thumbnail_image.height)), Image.ANTIALIAS)
    thumbnail_image_2 = thumbnail_image.copy()
    thumbnail_image = thumbnail_image.resize(max_size)
    thumbnail_image = thumbnail_image.filter(ImageFilter.GaussianBlur(5))
    thumbnail_image_2.thumbnail(max_size, Image.ANTIALIAS)
    thumbnail_left_2 = thumbnail_left + round((max_size[0] - thumbnail_image_2.width)/2)
    thumbnail_canvas = Image.new('RGBA', (width, height))
    thumbnail_canvas.paste(thumbnail_image, (thumbnail_left, thumbnail_top))
    thumbnail_canvas.paste(thumbnail_image_2, (thumbnail_left_2, thumbnail_top))

    # colors
    color_scheme = await auto_color(thumbnail_image)

    # draw sidebar
    sidebar_color = color_scheme[4] # 5 colors in total
    draw.rectangle([(0,0),(sidebar_width, height)], fill=sidebar_color)

    ## write actual text
    # title
    if len(full_title) >= 58:
        title_main_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 40)
        title_text_top = title_box_top + 5
        full_title = full_title[0:55] + '...'
    else:
        title_main_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 45)
        title_text_top = title_box_top
    title_text_left = main_left + text_padding
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (title_text_left, title_text_top), full_title, title_main_font)

    # difficulty title
    diff_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 40)
    diff_text_left = diff_left + diff_dim + 5
    diff_text_top = diff_top - 5
    text_canvas, version_text_size = draw_text_w_shadow(text_canvas, 
        (diff_text_left, diff_text_top), version, diff_font,
        font_color = color_scheme[1])
    text_canvas, played_text_size = draw_text_w_shadow(text_canvas, 
        (diff_text_left + version_text_size[0], diff_text_top), ' played by ', diff_font,
        font_color = (100, 100, 100, 200), shadow_color = (100, 100, 100, 50))
    text_canvas, version_text_size = draw_text_w_shadow(text_canvas, 
        (diff_text_left + version_text_size[0] + played_text_size[0], diff_text_top), username, diff_font,
        font_color = color_scheme[1])

    # put on profile picture
    pfp_canvas = Image.new('RGBA', (width, height))
    pfp_dim = 20
    pfp_left = 0
    pfp_top = 0
    # get pfp
    pfp_image = 0
    # pfp_canvas.paste(pfp_image, (pfp_left, pfp_top))
    
    text_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 60)  

    # score text
    text_horiz_shift = -3
    score_text_left = label_left + text_horiz_shift
    score_text_top = label_top + 23
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (score_text_left, score_text_top), score, text_font)        
    # accuracy text
    acc_text_left = label_mid_horiz + text_horiz_shift
    acc_text_top = score_text_top
    text_canvas, acc_size = draw_text_w_shadow(text_canvas, 
        (acc_text_left, acc_text_top), acc, text_font)
    small_acc_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 30)
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (acc_text_left + acc_size[0] + 3, acc_text_top + 27), '%', small_acc_font)     
    # combo
    combo_text_left = main_left + text_padding
    combo_text_top = label_mid_vert + 25
    text_canvas, combo_text_size = draw_text_w_shadow(text_canvas, 
        (combo_text_left, combo_text_top), combo, text_font)

    # put in mods
    if len(mods) > 0:
        all_mod_canvas = Image.new('RGBA', (width, height))
        mod_size = 75 # pixels
        mods_left = label_right - 8
        mods_top = label_top + 23
        mods_right = mods_left + mod_size * (len(mods) + 2)
        if len(mods) < 3:
            add_comp = 3
        elif len(mods) == 3:
            add_comp = 3
        else:
            add_comp = 2
        mod_shift = round((mods_right - mods_left)/(len(mods)+add_comp)) # pixels
        for i, mod in enumerate(mods):
            mod_canvas = Image.new('RGBA', (width, height))
            current_shift = i * mod_shift
            mod_filename = os.path.join(osu_folder_root, 'mods/mods_' + mod + '.png')
            mod_image = Image.open(mod_filename).convert('RGBA')
            mod_image = mod_image.resize((mod_size, mod_size), Image.ANTIALIAS)
            mod_canvas.paste(mod_image, (mods_left + current_shift, mods_top))
            all_mod_canvas = Image.alpha_composite(all_mod_canvas, mod_canvas)
    else:
        text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (label_right, score_text_top), '-', text_font)  

    # hits text
    hits_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 50)
    for i, file in enumerate(score_images):
        if not file:
            continue

        if i % 2 == 0: # first column
            h_coord = tag_left + tag_width + 10
        else:
            h_coord = tag_right + tag_width

        if i/2 < 1:
            v_coord = tag_top + 13
        elif i/2 < 2:
            v_coord = tag_mid + 14
        else:
            v_coord = tag_bottom + 12
        text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (h_coord, v_coord), score_hits[i], hits_font)
    # pp
    pp_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 70)
    pp_text_left = pp_box_left + text_padding
    pp_text_top = label_bottom + 30
    text_canvas, pp_text_size = draw_text_w_shadow(text_canvas, 
        (pp_text_left, pp_text_top), performance, pp_font,
        font_color = (255,105,180,255))

    # map infor text
    map_info_vert_offset = -10
    map_info_horiz_offset = 30
    # print(os.path.join(font_folder_root, 'Asimov.ttf'))
    large_map_info_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 55)
    unicode_font = ImageFont.truetype(os.path.join(font_folder_root, 'unicode.ttf'), 50)
    text_canvas, stars_size = draw_text_w_shadow(text_canvas, 
        (map_label_left, map_label_top + map_info_vert_offset + 30), map_stars, 
        large_map_info_font, font_color = color_scheme[1])
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (map_label_left + stars_size[0], map_label_top + map_info_vert_offset + 38), '★', 
        unicode_font, font_color = color_scheme[1])
    text_canvas, bpm_size = draw_text_w_shadow(text_canvas, 
        (small_label_right, map_label_top + map_info_vert_offset + 30), bpm, 
        large_map_info_font)
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (small_label_right + bpm_size[0], map_label_top + map_info_vert_offset + 54), ' BPM', 
        small_acc_font)

    text_canvas, _ = draw_text_w_shadow(text_canvas, 
        (small_label_left + map_info_horiz_offset, 
        small_label_top + map_info_vert_offset), ar, 
        large_map_info_font)
    text_canvas, _ = draw_text_w_shadow(text_canvas,
        (small_label_right + map_info_horiz_offset, 
        small_label_top + map_info_vert_offset), od, 
        large_map_info_font)
    text_canvas, _ = draw_text_w_shadow(text_canvas,
        (small_label_left + map_info_horiz_offset, 
        small_label_bottom + map_info_vert_offset), hp, 
        large_map_info_font)
    text_canvas, _ = draw_text_w_shadow(text_canvas,
        (small_label_right + map_info_horiz_offset, 
        small_label_bottom + map_info_vert_offset), cs, 
        large_map_info_font)

    ## write small text
    small_padding = 2
    small_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 30)
    # max combo
    max_combo_text_left = combo_text_left + combo_text_size[0] + small_padding
    max_combo_text_top = combo_text_top + 26
    if max_combo:
        text_canvas, _ = draw_text_w_shadow(text_canvas, 
                (max_combo_text_left, max_combo_text_top), '/'+str(max_combo), small_font)
    # max pp possible
    max_pp_text_left = pp_text_left + pp_text_size[0] + small_padding
    max_pp_text_top = pp_text_top + 36

    max_pp_text = ''
    if gamemode == 0:
        max_pp_text = '/'+str(performance_max)
    text_canvas, _ = draw_text_w_shadow(text_canvas,
            (max_pp_text_left, max_pp_text_top), max_pp_text+' PP', small_font)
    # write map time
    time_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 20)
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (320, 445), map_time, time_font, shadow_color=color_scheme[1])
    # write play time + server
    play_time_vert_shift = 74
    play_time_font = ImageFont.truetype(os.path.join(font_folder_root, 'Asimov.ttf'), 20)
    text_canvas, play_time_text_size = draw_text_w_shadow(text_canvas, 
            (label_mid_horiz, label_bottom + play_time_vert_shift), '@ ', time_font, 
            font_color = (100, 100, 100, 200), shadow_color = (100, 100, 100, 50))
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (label_mid_horiz + play_time_text_size[0], label_bottom + play_time_vert_shift), 
            play_date + ' UTC', time_font, 
            font_color = color_scheme[1])
    """
    time_text_shift = 100
    server_horizontal_shift = label_mid_horiz + play_time_text_size[0] +  time_text_shift
    text_canvas, play_time_text_size = draw_text_w_shadow(text_canvas, 
        (label_mid_horiz + play_time_text_size[0] +  time_text_shift, 
            label_bottom + play_time_vert_shift), 'on ', time_font, 
        font_color = (100, 100, 100, 200), shadow_color = (100, 100, 100, 50))
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (label_mid_horiz + play_time_text_size[0], label_bottom + play_time_vert_shift), 
            play_date + ' UTC', time_font, 
            font_color = color_scheme[1])"""

    # write mapper name
    mapper_name_vert_shift = 65
    text_canvas, by_text_size = draw_text_w_shadow(text_canvas, 
            (small_label_left, small_label_bottom + mapper_name_vert_shift), 'By ', time_font, 
            font_color = (100, 100, 100, 200), shadow_color = (100, 100, 100, 50))
    text_canvas, _ = draw_text_w_shadow(text_canvas, 
            (small_label_left + by_text_size[0], small_label_bottom + mapper_name_vert_shift), 
            map_creator, time_font, 
            font_color = color_scheme[1])

    # get player graph
    graph_left = label_left - 13
    graph_top = 390
    graph_image = await get_draw_score_graph_image(bmp_chunks,
        beatmap_info, userrecent['enabled_mods'], color=color_scheme[1])
    graph_canvas = Image.new('RGBA', (width, height))
    graph_canvas.paste(graph_image, (graph_left, graph_top))

    # paste
    canvas = Image.alpha_composite(canvas, process)
    canvas = Image.alpha_composite(canvas, rank_canvas)
    canvas = Image.alpha_composite(canvas, thumbnail_canvas)
    canvas = Image.alpha_composite(canvas, tag_canvas)
    canvas = Image.alpha_composite(canvas, diff_canvas)
    canvas = Image.alpha_composite(canvas, graph_canvas)
    if len(mods) > 0:
        canvas = Image.alpha_composite(canvas, all_mod_canvas)
    canvas = Image.alpha_composite(canvas, text_canvas)
    canvas.save(filename,'PNG', quality=100)
    file = discord.File(filename)
    await ctx.send(file=file)

def draw_text_w_shadow(image, position, text, font, 
    font_color=(255,255,255,255), radius=5, shadow_color=(0,0,0,255)):
    temp_layer = Image.new('RGBA', (image.width, image.height))
    text_draw = ImageDraw.Draw(temp_layer)

    # draw text in all black
    text_draw.text((position[0], position[1]), str(text),
        font=font, fill=shadow_color)
    # put Gaussian filter over black text
    temp_layer = temp_layer.filter(ImageFilter.GaussianBlur(radius=radius))
    text_draw = ImageDraw.Draw(temp_layer)
    text_draw.text((position[0], position[1]), str(text),
        font=font, fill=font_color)
    size = text_draw.textsize(str(text), font=font)

    # paste onto image
    image = Image.alpha_composite(image, temp_layer)
    return image, size

# uses k-means algorithm to find color from bg, rank is abundance of color, descending
async def auto_color(im):
    default_colors = [
        (100, 100, 100),
        (255, 102, 170),
        (255, 165, 0),
        (100, 100, 100),
        (255, 102, 170)
        ]
    try:
        im = im.resize((10,10), Image.ANTIALIAS)
        clusters = 5
        ranks = range(clusters)
        ar = np.asarray(im)
        shape = ar.shape
        ar = ar.reshape(scipy.product(shape[:2]), shape[2])

        codes, dist = cluster.vq.kmeans(ar.astype(float), clusters)
        vecs, dist = cluster.vq.vq(ar, codes)         # assign codes
        counts, bins = scipy.histogram(vecs, len(codes))    # count occurrences

        # sort counts
        freq_index = []
        index = 0
        for count in counts:
            freq_index.append((index, count))
            index += 1
        sorted_list = sorted(freq_index, key=operator.itemgetter(1), reverse=True)

        colors = []
        luminances = []
        for rank in ranks:
            color_index = min(rank, len(codes))
            peak = codes[sorted_list[color_index][0]] # gets the original index
            peak = peak.astype(int)
            colors.append(tuple(peak))
            luminances.append(luminance(tuple(peak)))

        # sort by luminance, highest luminance first
        colors = [x for _, x in sorted(zip(luminances, colors), reverse=True)]

        return colors # returns array
    except:
        return default_colors


def luminance(color):
    # convert to greyscale
    luminance = float((0.2126*color[0]) + (0.7152*color[1]) + (0.0722*color[2]))
    return luminance


def hex_to_rgb(self, hex):
     hex = hex.lstrip('#')
     hlen = len(hex)
     return tuple(int(hex[i:i+hlen/3], 16) for i in range(0, hlen, hlen/3))


def _determine_emote_name(beatmap):
    diff = float(beatmap["difficulty_rating"])
    if diff <= 1.99:
        name = "easy"
    elif 1.99 < diff <= 2.69:
        name = "normal"
    elif 2.69 < diff <= 3.99:
        name = "hard"
    elif 3.99 < diff <= 5.29:
        name = "insane"
    elif 5.29 < diff <= 6.49:
        name = "expert"
    else:
        name = "expertplus"
    return name


async def get_draw_score_graph_image(bmp_chunks, beatmap_info, mods, 
    color=None):

    star_list, speed_list, aim_list, time_list = [], [], [], []
    # results = chunks(file_path, mods=int(mods))
    results = bmp_chunks
    for chunk in results:
        time_list.append(chunk['time'])
        star_list.append(chunk['stars'])

    fig = plt.figure(figsize=(.350, .080), dpi=100, frameon=False)
    plt.rcParams['text.antialiased'] = True
    ax = plt.Axes(fig, [0., 0., 1., 1.])
    ax.set_axis_off()
    fig.add_axes(ax)

    plt.style.use('ggplot')
    # print('DRAW GRAPH COMPLETION', completion)
    if 'extra_info' in beatmap_info and \
        'map_completion' in beatmap_info['extra_info'] and \
        beatmap_info['extra_info']['map_completion']:
        # print('GRAPH MAP COMPLETION', beatmap_info['extra_info']['map_completion'])
        p_comp = beatmap_info['extra_info']['map_completion']/100
        color_incomp = [color[0]/255, color[1]/255, color[2]/255, .2]
        color_comp = [color[0]/255, color[1]/255, color[2]/255, 1]
        ax.plot(time_list, star_list, 
            color=color_incomp, linewidth=.1, antialiased=True)
        ax.fill_between(time_list, 0, star_list, 
            facecolor=color_incomp)
        max_fill_idx = round(len(time_list)*p_comp)
        ax.fill_between(time_list[0:max_fill_idx], 0, star_list[0:max_fill_idx], 
            facecolor=color_comp)
    else:
        color = [color[0]/255, color[1]/255, color[2]/255, 1]
        ax.plot(time_list, star_list, color=color, linewidth=.1, antialiased=True)
        ax.fill_between(time_list, 0, star_list, facecolor=color)

    # fig.gca().xaxis.set_major_formatter(ticker.FuncFormatter(plot_time_format))
    # fig.gca().xaxis.grid(True)
    # fig.gca().yaxis.grid(False)
    # plt.ylabel('Stars')
    fig.tight_layout()
    ax.xaxis.label.set_color(color)
    ax.set_yticks([])
    ax.set_yticklabels([])
    # ax.get_yaxis().set_visible(False)

    # ax.yaxis.label.set_color(color)
    ax.tick_params(axis='both', colors=color, labelcolor = color)
    # ax.grid(color='w', linestyle='-', linewidth=1)

    img_id = random.randint(0, 50)
    filepath = "../owo_v3.5/cogs/osu/temp/map_{}.png".format(img_id)
    fig.savefig(filepath, transparent=True, dpi=1000)
    plt.close()

    im = Image.open(filepath)
    return im