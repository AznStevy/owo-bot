#!/usr/bin/python3
"""oppai-chunks

 Moving-window difficulty calculation for osu beatmaps.
 Intended for mappers to check difficulty spikes/dips.

 Run in CLI as ./oppai-chunks.py <path_to_beatmap>
 Import oppai() and run oppai('path_to_beatmap')
"""
import codecs
import json
import sys
import tempfile
try:
    import pyoppai
except:
    raise RuntimeError("""You need to install pyoppai before you
        can run this program. https://github.com/Francesco149/oppai
        Check here for how to install it.""")
#import matplotlib.pyplot as plt


def print_usage():
    """Instructions on using the script
    """
    print(
        "oppai-chunks.py\n"
        "Usage: ./oppai-chunks.py beatmap [window [step]]\n"
        "beatmap is a .osu file for a specific difficulty.\n"
        "window is a number indicating the window size in ms\n"
        "step is a number indicating the step size in ms\n"
        "You can unzip a .osz file to extract the .osu files.\n"
    )


class ParseError(Exception):
    """Given file doesn't fit expected .osu format"""
    pass


def read(bmap):
    """Read in beatmap and split it into metadata and hitcircles
    Given a filename or the beatmap in one string or a list of lines,
    return two lists of lines - beatmap metadata and hit objects.
    Arguments:
        bmap {str, str list} -- filename (file.osu), or an already read
        beatmap as a single string (file.read) or lines (file.readlines)
    Returns:
        (str list, str list) -- (metadata, hitcircles)
    Raises:
        ParseError -- If [Hitobjects] not found (not an .osu file)
    """
    if bmap[-4:] == '.osu':
        # filename
        with codecs.open(bmap, 'r', 'utf-8') as beatmap:
            map_lines = beatmap.readlines()
    else:
        try:
            # file.read
            map_lines = bmap.split('\n')
        except AttributeError:
            # file.readlines
            map_lines = bmap
    try:  # Unicode life
        for i, line in enumerate(map_lines):
            map_lines[i] = line.decode()
    except AttributeError:
        # Already decoded
        pass
    index = -1
    for i, line in enumerate(map_lines):
        if line.startswith('[HitObjects]'):
            index = i
            break
    if index == -1:
        raise ParseError('Missing "[HitObjects]"')
    metadata = map_lines[:index]
    hitcircles = map_lines[index + 1:]
    return (metadata, hitcircles)


def parse_meta(metadata):
    """Parse necessary metadata lines from the beatmap.
    Arguments:
        metadata {str list} -- Metadata section of beatmap
    Raises:
        ParseError -- For missing fields
    """
    bm_info = {}
    bm_info['Title'] = [x for x in metadata if x.startswith('Title:')]
    bm_info['Artist'] = [x for x in metadata if x.startswith('Artist:')]
    bm_info['Mapper'] = [x for x in metadata if x.startswith('Creator:')]
    bm_info['Diff name'] = [x for x in metadata if x.startswith('Version:')]
    bm_info['HP'] = [x for x in metadata if x.startswith('HPDrainRate:')]
    bm_info['CS'] = [x for x in metadata if x.startswith('CircleSize:')]
    bm_info['OD'] = [x for x in metadata if x.startswith('OverallDifficulty:')]
    bm_info['AR'] = [x for x in metadata if x.startswith('ApproachRate:')]
    bm_info['SV'] = [x for x in metadata if x.startswith('SliderMultiplier:')]
    bm_info['TR'] = [x for x in metadata if x.startswith('SliderTickRate:')]
    if [] in bm_info.values():
        missing = [x for x in bm_info if bm_info[x] == []]
        raise ParseError(', '.join(missing))
    # Recover from using a list comprehension for everything
    bm_info = {x: bm_info[x][0] for x in bm_info}
    # The one line with a guaranteed position
    bm_info['format_ver'] = metadata[0]
    # Compose the necessary heading parts to keep oppai happy
    # and enable difficulty calculation
    bm_head = ''.join((bm_info['format_ver'],
                       '[General]\r\n',
                       '[Metadata]\r\n',
                       bm_info['Title'],
                       bm_info['Artist'],
                       bm_info['Mapper'],
                       bm_info['Diff name'],
                       '[Difficulty]\r\n',
                       bm_info['HP'],
                       bm_info['CS'],
                       bm_info['OD'],
                       bm_info['AR'],
                       bm_info['SV'],
                       bm_info['TR'],
                       '[TimingPoints]\r\n',
                       '[HitObjects]\r\n'))
    return bm_head


def chunks(bmap, mods=0, window_length=3000, step_size=500):
    """Open beatmap and process

    Runs oppai on chunks (default 30 sec windows) of the beatmap at regular
    intervals (default 5 second step).

    Arguments:
        bmap {} -- the lines of a beatmap file
        window_length {int} -- Window length in ms
        step_size {int} --- Step size in ms

    Returns:
        {list} -- A list of tuples for each chunk formatted as follows:
            (chunk start time (ms), overall stars, aim stars, speed stars)
    """
    metadata, hitcircles = read(bmap)
    bm_head = parse_meta(metadata)
    results = []  # Array of (time, stars, aim stars, speed stars) tuples
    seek = 0  # Time in ms
    with tempfile.TemporaryDirectory() as tmpdir:
        while hitcircles:
            # Slice out window of beatmap
            try:
                window = [x for x in hitcircles
                        if int(x.split(',')[2]) < seek + window_length]
            except IndexError:
                raise ParseError('Unexpected line in [HitObjects] section')
            if len(window) == 0:
                results.append({'time':seek, 'stars':0, 'speed_stars':0, 'aim_stars':0})
                seek = seek + 5000
                hitcircles = [x for x in hitcircles
                            if int(x.split(',')[2]) > seek]
                continue
            out = ''.join(window)
            with open(tmpdir + '/tmp.osu', 'w', encoding='utf-8') as tmp:
                tmp.write(bm_head + out)
            oppai_out = get_pyoppai(tmpdir + '/tmp.osu', mods=mods)
            oppai_out['time'] = seek
            results.append(oppai_out)

            # Step to next window
            seek = seek + step_size
            hitcircles = [x for x in hitcircles
                        if int(x.split(',')[2]) > seek]
    return results

def get_pyoppai(btmap_file, mods=0): # Pyoppai implementation rather than subprocess
    btmap = btmap_file
    ctx = pyoppai.new_ctx()
    b = pyoppai.new_beatmap(ctx)
    BUFSIZE = 2000000
    buf = pyoppai.new_buffer(BUFSIZE)
    pyoppai.parse(btmap, b, buf, BUFSIZE, True, 'data/osu/cache/')
    dctx = pyoppai.new_d_calc_ctx(ctx)
    pyoppai.apply_mods(b, mods)
    stars, aim, speed, _, _, _, _ = pyoppai.d_calc(dctx, b)
    cs, od, ar, hp = pyoppai.stats(b)
    combo = pyoppai.max_combo(b)
    acc, pp, aim_pp, speed_pp, acc_pp = pyoppai.pp_calc_acc(ctx, aim, speed, b, 100, 0, combo, 0)
    pyoppai_json = {
        'version': pyoppai.version(b),
        'title': pyoppai.title(b),
        'artist': pyoppai.artist(b),
        'creator': pyoppai.creator(b),
        'combo': combo,
        'misses': 0,
        'max_combo': pyoppai.max_combo(b),
        'mode': pyoppai.mode(b),
        'num_objects': pyoppai.num_objects(b),
        'num_circles': pyoppai.num_circles(b),
        'num_sliders': pyoppai.num_sliders(b),
        'num_spinners': pyoppai.num_spinners(b),
        'stars': stars,
        'aim_stars': aim,
        'speed_stars': speed,
        'pp': pp,
        'aim_pp': aim_pp,
        'speed_pp': speed_pp,
        'acc': acc,
        'cs': cs,
        'od': od,
        'ar': ar,
        'hp': hp
        }
    return pyoppai_json

def main():
    """oppai-chunks from CLI

    Prints table of time|stars|aim|speed when run
    ./oppai-chunks.py beatmap.osu
    """
    if len(sys.argv) > 4 or not sys.argv[1].endswith('.osu'):
        print_usage()
        sys.exit()

    print("Analyzing \"{}\"...".format(sys.argv[1]))
    try:
        results = oppai(sys.argv[1], *[int(x) for x in sys.argv[2:]])
    except ValueError:
        print_usage()
        sys.exit()
    #static = get_pyoppai(sys.argv[1]) # To get the map title and version name
    #star_list, speed_list, aim_list, time_list = [], [], [], []
    for chunk in results:
        #time_list.append(chunk['time'])
        #star_list.append(chunk['stars'])
        #aim_list.append(chunk['aim_stars'])
        #speed_list.append(chunk['speed_stars'])
        print("{}\t{}\t{}\t{}".format(
            chunk['time'],
            chunk['stars'],
            chunk['aim_stars'],
            chunk['speed_stars']))
    #plt.plot(time_list, star_list)
    #plt.plot(time_list, aim_list)
    #plt.plot(time_list, speed_list)
    #plt.ylabel('Stars')
    #plt.xlabel('Times')
    #plt.title('{} [{}]'.format(static['title'], static['version']))
    #plt.tight_layout()
    #plt.savefig('plot.png')

if __name__ == '__main__':
    main()