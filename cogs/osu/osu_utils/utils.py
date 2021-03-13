import datetime
from operator import itemgetter
from difflib import SequenceMatcher

def get_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

def determine_range(value, range_of_value = 20):
    nearest_range = int(range_of_pp * round(float(pp)/range_of_pp))

    upper_bound = 0
    lower_bound = 0
    if (nearest_range - value) > 0:
        lower_bound = nearest_range - range_of_value
        upper_bound = nearest_range - 1
    else:
        lower_bound = nearest_range
        upper_bound = nearest_range + range_of_value - 1

    return "{}_{}".format(lower_bound, upper_bound)

def calc_time(total_sec, bpm, factor:float=1):
    m1, s1 = divmod(round(float(total_sec)/factor), 60)
    bpm1 = round(factor*float(bpm), 1)
    return (m1,s1,bpm1)

def time_ago(time1, time2, shift = 0, abbr=False):
    time_diff = time1 - time2
    if shift != 0:
        time_diff += datetime.timedelta(hours=int(shift))

    timeago = datetime.datetime(1,1,1) + time_diff
    time_limit = 0
    time_ago = ""
    if timeago.year-1 != 0:
        if abbr:
            time_ago += "{}Y".format(timeago.year-1)
        else:
            time_ago += "{} Year{} ".format(timeago.year-1, determine_plural(timeago.year-1))
        time_limit = time_limit + 1
    if timeago.month-1 !=0:
        if abbr:
            time_ago += "{}M".format(timeago.month-1)
        else:
            time_ago += "{} Month{} ".format(timeago.month-1, determine_plural(timeago.month-1))
        time_limit = time_limit + 1
    if timeago.day-1 !=0 and not time_limit == 2:
        if abbr:
            time_ago += "{}d".format(timeago.day-1)
        else:
            time_ago += "{} Day{} ".format(timeago.day-1, determine_plural(timeago.day-1))
        time_limit = time_limit + 1
    if timeago.hour != 0 and not time_limit == 2:
        if abbr:
            time_ago += "{}h".format(timeago.hour)
        else:
            time_ago += "{} Hour{} ".format(timeago.hour, determine_plural(timeago.hour))
        time_limit = time_limit + 1
    if timeago.minute != 0 and not time_limit == 2:
        if abbr:
            time_ago += "{}m".format(timeago.minute)
        else:
            time_ago += "{} Minute{} ".format(timeago.minute, determine_plural(timeago.minute))
        time_limit = time_limit + 1
    if not time_limit == 2:
        if abbr:
            time_ago += "{}s".format(timeago.second)
        else:
            time_ago += "{} Second{} ".format(timeago.second, determine_plural(timeago.second))
    return time_ago

def determine_plural(number):
    if int(number) != 1:
        return 's'
    else:
        return ''

def get_gamemode_text(gamemode:int):
    if gamemode == 1:
        gamemode_text = "Taiko"
    elif gamemode == 2:
        gamemode_text = "Catch the Beat!"
    elif gamemode == 3:
        gamemode_text = "osu! Mania"
    else:
        gamemode_text = "osu! Standard"
    return gamemode_text

def get_gamemode_display(gamemode):
    if gamemode == "osu":
        gamemode_text = "osu! Standard"
    elif gamemode == "ctb":
        gamemode_text = "Catch the Beat!"
    elif gamemode == "mania":
        gamemode_text = "osu! Mania"
    elif gamemode == "taiko":
        gamemode_text = "Taiko"
    return gamemode_text

def get_gamemode_number(gamemode:str):
    if gamemode == "taiko":
        gamemode_text = 1
    elif gamemode == "ctb":
        gamemode_text = 2
    elif gamemode == "mania":
        gamemode_text = 3
    elif gamemode == "osu":
        gamemode_text = 0
    else:
        gamemode_text = int(gamemode)

    return int(gamemode_text)

def calculate_rank(beatmap, acc:float, mods):
    if acc == 100:
        rank = 'X'
    elif acc >= 93:
        if beatmap['count_miss'] == 0:
            rank = 'S'
        else:
            rank = 'A'
    elif acc >= 86:
        if beatmap['count_miss'] == 0:
            rank = 'A'
        else:
            rank = 'B'
    elif acc >= 81:
        if beatmap['count_miss'] == 0:
            rank = 'B'
        else:
            rank = 'C'
    else:
        rank = 'D'

    if ('S' in rank or 'X' in rank)and "HD" in mods:
        rank += 'H'

    return rank

def calculate_acc(beatmap, gamemode):
    gamemode = int(gamemode)
    
    user_score = 0
    if gamemode == 0:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *=300
        user_score = float(beatmap['count_300']) * 300.0
        user_score += float(beatmap['count_100']) * 100.0
        user_score += float(beatmap['count_50']) * 50.0
    elif gamemode == 1:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *= 300
        user_score = float(beatmap['count_300']) * 1.0
        user_score += float(beatmap['count_100']) * 0.5
        user_score *= 300
    elif gamemode == 2:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score += float(beatmap['count_katu'])
        user_score = float(beatmap['count_300'])
        user_score += float(beatmap['count_100'])
        user_score  += float(beatmap['count_50'])
    elif gamemode == 3:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_geki'])
        total_unscale_score += float(beatmap['count_katu'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *=300
        user_score = float(beatmap['count_300']) * 300.0
        user_score += float(beatmap['count_geki']) * 300.0
        user_score += float(beatmap['count_katu']) * 200.0
        user_score += float(beatmap['count_100']) * 100.0
        user_score += float(beatmap['count_50']) * 50.0

    return (float(user_score)/float(total_unscale_score)) * 100.0

def no_choke_acc(beatmap, gamemode:int):
    if gamemode == 0:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *=300
        user_score = float(beatmap['count_300']) * 300.0
        user_score += (float(beatmap['count_100']) + float(beatmap['count_miss'])) * 100.0
        user_score += float(beatmap['count_50']) * 50.0
    elif gamemode == 1:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *= 300
        user_score = float(beatmap['count_300']) * 1.0
        user_score += (float(beatmap['count_100']) + float(beatmap['count_miss'])) * 0.5
        user_score *= 300
    elif gamemode == 2:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score += float(beatmap['count_katu'])
        user_score = float(beatmap['count_300'])
        user_score += (float(beatmap['count_100']) + float(beatmap['count_miss']))
        user_score  += float(beatmap['count_50'])
    elif gamemode == 3:
        total_unscale_score = float(beatmap['count_300'])
        total_unscale_score += float(beatmap['count_geki'])
        total_unscale_score += float(beatmap['count_katu'])
        total_unscale_score += float(beatmap['count_100'])
        total_unscale_score += float(beatmap['count_50'])
        total_unscale_score += float(beatmap['count_miss'])
        total_unscale_score *=300
        user_score = float(beatmap['count_300']) * 300.0
        user_score += float(beatmap['count_geki']) * 300.0
        user_score += float(beatmap['count_katu']) * 200.0
        user_score += (float(beatmap['count_100']) + float(beatmap['count_miss'])) * 100.0
        user_score += float(beatmap['count_50']) * 50.0

    return (float(user_score)/float(total_unscale_score)) * 100.0

# because you people just won't stop bothering me about it
def fix_mods(mods:str):
    if mods == 'PFSOFLNCHTRXDTSDHRHDEZNF':
        return '? KEY'
    else:
        mods = mods.replace('DTHRHD', 'HDHRDT').replace('DTHD','HDDT').replace('HRHD', 'HDHR')
        if "PF" in mods and "SD" in mods:
            mods = mods.replace('SD', '')
        if "NC" in mods and "DT" in mods:
            mods = mods.replace('DT', '')
            
        return mods

def fix_mod_list(mods_list):
    new_mod_list = []
    if 'DT' in mods_list and 'NC' in mods_list:
        mods_list.remove('DT')
    if 'PF' in mods_list and 'SD' in mods_list:
        mods_list.remove('SD') 

    if 'HD' in mods_list and 'DT' in mods_list and 'HR' in mods_list:
        new_mod_list.extend(['HD', 'HR', 'DT'])
    elif 'HD' in mods_list and 'NC' in mods_list and 'HR' in mods_list:
        new_mod_list.extend(['HD', 'HR', 'NC'])   
    elif 'HD' in mods_list and 'HR' in mods_list:
        new_mod_list.extend(['HD', 'HR'])
    elif 'HD' in mods_list and 'DT' in mods_list:
        new_mod_list.extend(['HD', 'DT'])

    for mod in mods_list:
        if mod not in new_mod_list:
            new_mod_list.append(mod)

    return new_mod_list


def str_to_mod(mod_str:str):
    mod_list = num_to_mod(mod_to_num(mod_str))
    return fix_mod_list(mod_list)

# gives a list of the ranked mods given a peppy number lol
def num_to_mod(number):
    # print('UTILS numtomod', number)
    mods = [
        'NF','EZ','TD','HD','HR','SD','DT','RX','HT','NC','FL','Auto',
        'SO','AP','PF','4K','5K','6K','7K','8K','FI','RDM','CI','TG',
        '9K','10K','1K','3K','2K','V2','MI'
    ]
    number = int(number)
    mod_list = []

    for mod_idx in range(len(mods)-1, -1, -1):
        mod = mods[mod_idx]
        # print(mods[mod_idx], mod_idx, 2**mod_idx)
        if mod == 'NC':
            if number >= 576:
                number -= 576
                mod_list.append(mod)
                continue
        elif mod == 'PF':
            if number >= 16416:
                number -= 16416
                mod_list.append(mod)
                continue

        if number >= 2**mod_idx:
            number -= 2**mod_idx
            mod_list.append(mod)

    # print('UTIL NUM2MOD', mod_list)

    return mod_list

def mod_to_num(input_mods:str):
    # Function checked.
    mods = [
        'NF','EZ','TD','HD','HR','SD','DT','RX','HT','NC','FL','Auto',
        'SO','AP','PF','4K','5K','6K','7K','8K','FI','RDM','CI','TG',
        '9K','10K','1K','3K','2K','V2','MI'
    ]
    input_mods = input_mods.upper()
    total = 0

    # remove TD first becuase it interferes with HD/DT
    if 'TD' in input_mods:
        total += 4
        input_mods = input_mods.replace('TD', '')

    for mod_idx in range(len(mods)-1, -1, -1):
        if mods[mod_idx] in input_mods:
            if mods[mod_idx] == 'DT':
                total += 64
            elif mods[mod_idx] == 'NC':
                total += 576
            elif mods[mod_idx] == 'SD':
                total += 32
            elif mods[mod_idx] == 'PF':
                total += 16416
            else:
                total += 2**mod_idx
            input_mods = input_mods.replace(mods[mod_idx], '')

    # print('UTIL MOD2NUM', total)

    return int(total)


def droid_mod_to_mod_list(droid_mods):
    """
    Converts droid mod string to PC mod string.
    """

    # Honestly not the best implementation, but the core is there
    final_mods = ""

    if "a" in droid_mods:
        final_mods += "at"
    if "x" in droid_mods:
        final_mods += "rx"
    if "p" in droid_mods:
        final_mods += "ap"
    if "e" in droid_mods:
        final_mods += "ez"
    if "n" in droid_mods:
        final_mods += "nf"
    if "r" in droid_mods:
        final_mods += "hr"
    if "h" in droid_mods:
        final_mods += "hd"
    if "i" in droid_mods:
        final_mods += "fl"
    if "d" in droid_mods:
        final_mods += "dt"
    if "c" in droid_mods:
        final_mods += "nc"
    if "t" in droid_mods:
        final_mods += "ht"
    if "s" in droid_mods:
        final_mods += "pr"
    if "m" in droid_mods:
        final_mods += "sc"
    if "b" in droid_mods:
        final_mods += "su"
    if "l" in droid_mods:
        final_mods += "re"
    if "f" in droid_mods:
        final_mods += "pf"
    if "u" in droid_mods:
        final_mods += "sd"
    if "v" in droid_mods:
        final_mods += "v2"

    return final_mods.upper()


def num_to_droid_mod(mod_num):
    # print('UTILS mod num', mod_num)
    mod_list = num_to_mod(mod_num)
    mods = [
        'NF','EZ','HD','HR','SD','DT','RX','HT','NC','FL','AT', 'V2'
    ]
    mod_droid = [
        'n', 'e', 'h', 'r', 'u', 'd', 'x', 't', 'c', 'i', 'a', 'v'
    ]
    droid_str = ''
    for mod in mod_list:
        if mod.upper() in mods:
            mod_idx = mods.index(mod.upper())
            droid_str += mod_droid[mod_idx]

    return droid_str


def mode_to_num(mode_str):
    if 'std' in mode_str:
        return 0
    if 'osu' in mode_str:
        return 0
    elif 'taiko' in mode_str:
        return 1
    elif 'ctb' in mode_str:
        return 2
    elif 'fruit' in mode_str:
        return 2
    elif 'mania' in mode_str:
        return 3
    else:
        return 0

def num_to_mode(mode_num):
    mode_num = int(mode_num)
    if mode_num == 0:
        return "std"
    elif mode_num == 1:
        return "taiko"
    elif mode_num == 2:
        return "ctb"
    elif mode_num == 3:
        return "mania"
    else:
        return None