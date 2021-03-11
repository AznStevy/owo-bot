#!/usr/bin/env python

"""
osu! pp and difficulty calculator.

pure python implementation of oppai-ng
this is meant to be used as a completely standalone python module,
more portable and easier to use than bindings.

this is over 10 times slower than the C version, so if you need to
calculate hundreds or thousands of scores you should consider
using the C version or making python bindings for it.

for comparison, the C version runs through the test suite (~12k
unique scores) in ~9-10 seconds on my i7-4790k while pyttanko takes
100+ seconds

if you want a command line interface, check out
https://github.com/Francesco149/oppai-ng
-------------------------------------------------------------------
usage:
put pyttanko.py in your project's folder and import pyttanko

for example usage, check out the __main__ at the bottom of the file
you can run it like:

    cat /path/to/map.osu | ./pyttanko.py +HDDT 200x 1m 95%

also, check out "pydoc pyttanko" for full documentation
-------------------------------------------------------------------
this is free and unencumbered software released into the public
domain. check the attached UNLICENSE or http://unlicense.org/
"""

__author__ = "Franc[e]sco <lolisamurai@tfwno.gf>"
__version__ = "1.0.22"

import sys
import math

if sys.version_info[0] < 3:
    # hack to force utf-8
    reload(sys)
    sys.setdefaultencoding("utf-8")

info = sys.stderr.write

class v2f:
    """2D vector with float values"""
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y


    def __sub__(self, other):
        return v2f(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        return v2f(self.x * other, self.y * other)

    def len(self):
        return math.sqrt(self.x * self.x + self.y * self.y)

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return str(self)


# -------------------------------------------------------------------------
# beatmap utils

MODE_STD = 0

class circle:
    def __init__(self, pos=None):
        """
        initializes a circle object.
        if pos is None, it will be set to v2f()
        """
        if pos == None:
            pos = v2f()

        self.pos = pos


    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return str(self)


class slider:
    def __init__(self, pos=None, distance=0.0, repetitions=0):
        """
        initializes a slider object.

        distance: distance travelled by one repetition (float)
        pos: instance of v2f. if None, it will be set to v2f()
        """
        if pos == None:
            pos = v2f()

        self.pos = pos
        self.distance = distance
        self.repetitions = repetitions


    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return str(self)


OBJ_CIRCLE = 1<<0
OBJ_SLIDER = 1<<1
OBJ_SPINNER = 1<<3

class hitobject:
    def __init__(self, time=0.0, objtype=OBJ_CIRCLE, data=None):
        """
        initializes a new hitobject.

        time: start time in milliseconds (float)
        data: an instance of circle, slider or None
        """
        self.time = time
        self.objtype = objtype
        self.data = data
        self.normpos = v2f()
        self.strains = [ 0.0, 0.0 ]
        self.is_single = False


    def typestr(self):
        res = ""

        if self.objtype & OBJ_CIRCLE != 0:
            res += "circle | "
        if self.objtype & OBJ_SLIDER != 0:
            res += "slider | "
        if self.objtype & OBJ_SPINNER != 0:
            res += "spinner | "

        return res[0:-3]


    def __str__(self):
        return (
            """hitobject(time=%g, objtype=%s, data=%s,
normpos=%s, strains=%s, is_single=%s)""" % (
                self.time, self.typestr(), str(self.data),
                str(self.normpos), str(self.strains),
                str(self.is_single)
            )
        )


    def __repr__(self):
        return str(self)


class timing:
    def __init__(self, time=0.0, ms_per_beat=-100.0, change=False):
        """
        initializes a timing point
        time: start time in milliseconds (float)
        ms_per_beat: float
        change: if False, ms_per_beat is -100.0 * bpm_multiplier
        """
        self.time = time
        self.ms_per_beat = ms_per_beat
        self.change = change


    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return str(self)


class beatmap:
    """
    the bare minimum amount of data about a beatmap to perform
    difficulty and pp calculation

    fields:
    mode: gamemode, see MODE_* constants (integer)
    title title_unicode artist artist_unicode
    creator: mapper name
    version: difficulty name
    ncircles, nsliders, nspinners
    hp cs od ar (float)
    sv tick_rate (float)
    hitobjects: list (hitobject)
    timing_points: list (timing)
    """
    def __init__(self):
        # i tried pre-allocating hitobjects and timing_points
        # as well as object data.
        # it didn't show any appreciable performance improvement
        self.format_version = 1
        self.hitobjects = []
        self.timing_points = []
        # these are assumed to be ordered by time low to high
        self.reset()


    def reset(self):
        """
        resets fields to prepare the object to store a new
        beatmap. used internally by the parser
        """
        self.mode = MODE_STD

        self.title = ""
        self.title_unicode = ""
        self.artist = ""
        self.artist_unicode = ""
        self.creator = ""
        self.version = ""

        self.ncircles = self.nsliders = self.nspinners = 0
        self.hp = self.cs = self.od = 5
        self.ar = None
        self.sv = self.tick_rate = 1.0

        self.hitobjects[:] = []
        self.timing_points[:] = []


    def __str__(self):
        s = self
        return """beatmap(
    title="%s", title_unicode="%s"
    artist="%s", artist_unicode="%s",
    creator="%s", version="%s",
    hitobjects=[ %s ],
    timing_points=[ %s ],
    ncircles=%d, nsliders=%d, nspinners=%d,
    hp=%g, cs=%g, od=%g, ar=%g,
    sv=%g, tick_rate=%g\n)""" % (
            s.title, s.title_unicode, s.artist, s.artist_unicode,
            s.creator, s.version,
            ",\n        ".join([str(x) for x in s.hitobjects]),
            ",\n        ".join([str(x) for x in s.timing_points]),
            s.ncircles, s.nsliders, s.nspinners, s.hp, s.cs, s.od,
            s.ar, s.sv, s.tick_rate
        )


    def __repr__(self):
        return str(self)

    def max_combo(self):
        res = 0

        points = self.timing_points
        tindex = -1
        tnext = -float("inf")

        px_per_beat = None

        for obj in self.hitobjects:
            if obj.objtype & OBJ_SLIDER == 0:
                res += 1
                continue


            # keep track of the current timing point without
            # looping through all of the timing points for every
            # object
            while tnext != None and obj.time >= tnext:
                tindex += 1
                if len(points) > tindex + 1:
                    tnext = points[tindex + 1].time
                else:
                    tnext = None

                t = points[tindex]
                sv_multiplier = 1.0

                if not t.change and t.ms_per_beat < 0:
                    sv_multiplier = (-100.0 / t.ms_per_beat)

                px_per_beat = self.sv * 100.0 * sv_multiplier
                if self.format_version < 8:
                    px_per_beat /= sv_multiplier


            # slider ticks
            sl = obj.data

            num_beats = (
                (sl.distance * sl.repetitions) / px_per_beat
            )

            ticks = int(
                math.ceil(
                    (num_beats - 0.1) /
                    sl.repetitions * self.tick_rate
                )
            )

            ticks -= 1
            ticks *= sl.repetitions
            ticks += sl.repetitions + 1

            res += max(0, ticks)


        return res



# -------------------------------------------------------------------------
# beatmap parser

class parser:
    """
    beatmap parser.

    fields:
    lastline lastpos: last line and token touched (strings)
    nline: last line number touched
    done: True if the parsing completed successfully
    """
    def __init__(self):
        self.lastline = ""
        self.lastpos = ""
        self.nline = 0
        self.done = False


    def __str__(self):
        """formats parser status if the parsing failed"""
        if self.done:
            return "parsing successful"

        return (
            "in line %d\n%s\n> %s\n" % (
                self.nline, self.lastline, self.lastpos
            )
        )


    def __repr__(self):
        return str(self)

    def setlastpos(self, v):
        # sets lastpos to v and returns v
        # should be used to access any string that can make the
        # parser fail
        self.lastpos = v
        return v


    def property(self, line):
        # parses PropertyName:Value into a tuple
        s = line.split(":")
        if len(s) < 2:
            raise SyntaxError(
                "property must be a pair of ':'-separated values"
            )
        return (s[0], "".join(s[1:]))


    def metadata(self, b, line):
        p = self.property(line)
        if p[0] == "Title":
            b.title = p[1]
        elif p[0] == "TitleUnicode":
            b.title_unicode = p[1]
        elif p[0] == "Artist":
            b.artist = p[1]
        elif p[0] == "ArtistUnicode":
            b.artist_unicode = p[1]
        elif p[0] == "Creator":
            b.creator = p[1]
        elif p[0] == "Version":
            b.version = p[1]


    def general(self, b, line):
        p = self.property(line)
        if p[0] == "Mode":
            b.mode = int(self.setlastpos(p[1]))


    def difficulty(self, b, line):
        p = self.property(line)
        if p[0] == "CircleSize":
            b.cs = float(self.setlastpos(p[1]))
        elif p[0] == "OverallDifficulty":
            b.od = float(self.setlastpos(p[1]))
        elif p[0] == "ApproachRate":
            b.ar = float(self.setlastpos(p[1]))
        elif p[0] == "HPDrainRate":
            b.hp = float(self.setlastpos(p[1]))
        elif p[0] == "SliderMultiplier":
            b.sv = float(self.setlastpos(p[1]))
        elif p[0] == "SliderTickRate":
            b.tick_rate = float(self.setlastpos(p[1]))


    def timing(self, b, line):
        s = line.split(",")

        if len(s) > 8:
            info("W: timing point with trailing values\n")

        elif len(s) < 2:
            raise SyntaxError(
                "timing point must have at least two fields"
            )


        t = timing(
            time=float(self.setlastpos(s[0])),
            ms_per_beat=float(self.setlastpos(s[1]))
        )

        if len(s) >= 7:
            t.change = int(s[6]) != 0

        b.timing_points.append(t)


    def objects_std(self, b, line):
        s = line.split(",")
        if len(s) > 11:
            info("W: object with trailing values\n")

        if len(s) < 5:
            raise SyntaxError(
                "hitobject must have at least 5 fields"
            )


        # I already tried calling the constructor with all of the
        # values on the fly and it wasn't any faster, don't bother
        obj = hitobject()
        obj.time = float(self.setlastpos(s[2]))
        obj.objtype = int(self.setlastpos(s[3]))
        if obj.objtype < 0 or obj.objtype > 255:
            raise SyntaxError("invalid hitobject type")

        # x,y,...
        if obj.objtype & OBJ_CIRCLE != 0:
            b.ncircles += 1
            c = circle()
            c.pos.x = float(self.setlastpos(s[0]))
            c.pos.y = float(self.setlastpos(s[1]))
            obj.data = c

        # ?,?,?,?,?,end_time,custom_sample_banks
        elif obj.objtype & OBJ_SPINNER != 0:
            b.nspinners += 1

        # x,y,time,type,sound_type,points,repetitions,distance,
        # per_node_sounds,per_node_samples,custom_sample_banks
        elif obj.objtype & OBJ_SLIDER != 0:
            if len(s) < 7:
                raise SyntaxError(
                    "slider must have at least 7 fields"
                )

            b.nsliders += 1
            sli = slider()
            sli.pos.x = float(self.setlastpos(s[0]))
            sli.pos.y = float(self.setlastpos(s[1]))
            sli.repetitions = int(self.setlastpos(s[6]))
            sli.distance = float(self.setlastpos(s[7]))
            obj.data = sli


        b.hitobjects.append(obj)


    def objects(self, b, line):
        if b.mode == MODE_STD:
            self.objects_std(b, line)

        # TODO: other modes

        else:
            raise NotImplementedError

    def map(self, osu_file, bmap = None):
        """
        reads a file object and parses it into a beatmap object
        which is then returned.

        if bmap is specified, it will be reused as a pre-allocated
        beatmap object instead of building a new one, speeding
        up parsing slightly because of less allocations
        """
        f = osu_file
        self.done = False

        section = ""
        b = bmap
        if b == None:
            b = beatmap()
        else:
            b.reset()

        for line in osu_file:
            self.nline += 1
            self.lastline = line

            # comments (according to lazer)
            if line.startswith(" ") or line.startswith("_"):
                continue

            line = line.strip()
            if line == "":
                continue

            # c++ style comments
            if line.startswith("//"):
                continue

            # [SectionName]
            if line.startswith("["):
                section = line[1:-1]
                continue

            try:
                if section == "Metadata":
                    self.metadata(b, line)
                elif section == "General":
                    self.general(b, line)
                elif section == "Difficulty":
                    self.difficulty(b, line)
                elif section == "TimingPoints":
                    self.timing(b, line)
                elif section == "HitObjects":
                    self.objects(b, line)
                else:
                    OSU_MAGIC = "file format v"
                    findres = line.strip().find(OSU_MAGIC)
                    if findres > 0:
                        b.format_version = int(
                            line[findres+len(OSU_MAGIC):]
                        )

            except (ValueError, SyntaxError) as e:
                info("W: %s\n%s\n" % (e, self))



        if b.ar is None:
            b.ar = b.od

        self.done = True
        return b



# -------------------------------------------------------------------------
# mods utils

MODS_NOMOD = 0
MODS_NF = 1<<0
MODS_EZ = 1<<1
MODS_TD = MODS_TOUCH_DEVICE = 1<<2
MODS_HD = 1<<3
MODS_HR = 1<<4
MODS_DT = 1<<6
MODS_HT = 1<<8
MODS_NC = 1<<9
MODS_FL = 1<<10
MODS_SO = 1<<12

def mods_str(mods):
    """
    gets string representation of mods, such as HDDT.
    returns "nomod" for nomod
    """
    if mods == 0:
        return "nomod"

    res = ""

    if mods & MODS_HD != 0: res += "HD"
    if mods & MODS_HT != 0: res += "HT"
    if mods & MODS_HR != 0: res += "HR"
    if mods & MODS_EZ != 0: res += "EZ"
    if mods & MODS_TOUCH_DEVICE != 0: res += "TD"
    if mods & MODS_NC != 0: res += "NC"
    elif mods & MODS_DT != 0: res += "DT"
    if mods & MODS_FL != 0: res += "FL"
    if mods & MODS_SO != 0: res += "SO"
    if mods & MODS_NF != 0: res += "NF"

    return res


def mods_from_str(string):
    """
    get mods bitmask from their string representation
    (touch device is TD)
    """

    res = 0

    while string != "":
        if string.startswith("HD"): res |= MODS_HD
        elif string.startswith("HT"): res |= MODS_HT
        elif string.startswith("HR"): res |= MODS_HR
        elif string.startswith("EZ"): res |= MODS_EZ
        elif string.startswith("TD"): res |= MODS_TOUCH_DEVICE
        elif string.startswith("NC"): res |= MODS_NC
        elif string.startswith("DT"): res |= MODS_DT
        elif string.startswith("FL"): res |= MODS_FL
        elif string.startswith("SO"): res |= MODS_SO
        elif string.startswith("NF"): res |= MODS_NF
        else:
            string = string[1:]
            continue

        string = string[2:]


    return res


def mods_apply(mods, ar = None, od = None, cs = None, hp = None):
    """
    calculates speed multiplier, ar, od, cs, hp with the given
    mods applied. returns (speed_mul, ar, od, cs, hp).

    the base stats are all optional and default to None. if a base
    stat is None, then it won't be calculated and will also be
    returned as None.
    """

    OD0_MS = 79.5
    OD10_MS = 19.5
    AR0_MS = 1800
    AR5_MS = 1200
    AR10_MS = 450

    OD_MS_STEP = (OD0_MS - OD10_MS) / 10.0
    AR_MS_STEP1 = (AR0_MS - AR5_MS) / 5.0
    AR_MS_STEP2 = (AR5_MS - AR10_MS) / 5.0

    MODS_SPEED_CHANGING = MODS_DT | MODS_HT | MODS_NC
    MODS_MAP_CHANGING = MODS_HR | MODS_EZ | MODS_SPEED_CHANGING

    if mods & MODS_MAP_CHANGING == 0:
        return (1.0, ar, od, cs, hp)

    speed_mul = 1.0

    if mods & (MODS_DT | MODS_NC) != 0:
        speed_mul = 1.5

    if mods & MODS_HT != 0:
        speed_mul *= 0.75

    od_ar_hp_multiplier = 1.0

    if mods & MODS_HR != 0:
        od_ar_hp_multiplier = 1.4

    if mods & MODS_EZ:
        od_ar_hp_multiplier *= 0.5

    if ar != None:
        ar *= od_ar_hp_multiplier

        # convert AR into milliseconds
        arms = AR5_MS

        if ar < 5.0:
            arms = AR0_MS - AR_MS_STEP1 * ar
        else:
            arms = AR5_MS - AR_MS_STEP2 * (ar - 5)

        # stats must be capped to 0-10 before HT/DT which brings
        # them to a range of -4.42-11.08 for OD and -5-11 for AR
        arms = min(AR0_MS, max(AR10_MS, arms))
        arms /= speed_mul

        # convert back to AR
        if arms > AR5_MS:
            ar = (AR0_MS - arms) / AR_MS_STEP1
        else:
            ar = 5.0 + (AR5_MS - arms) / AR_MS_STEP2


    if od != None:
        od *= od_ar_hp_multiplier
        odms = OD0_MS - math.ceil(OD_MS_STEP * od)
        odms = min(OD0_MS, max(OD10_MS, odms))
        odms /= speed_mul
        od = (OD0_MS - odms) / OD_MS_STEP


    if cs != None:
        if mods & MODS_HR != 0:
            cs *= 1.3

        if mods & MODS_EZ != 0:
            cs *= 0.5

        cs = min(10.0, cs)


    if hp != None:
        hp = min(10.0, hp * od_ar_hp_multiplier)

    return (speed_mul, ar, od, cs, hp)


# -------------------------------------------------------------------------
# difficulty calculator

DIFF_SPEED = 0
DIFF_AIM = 1

def d_spacing_weight(difftype, distance):
    # calculates spacing weight and returns (weight, is_single)
    # NOTE: is_single is only computed for DIFF_SPEED

    ALMOST_DIAMETER = 90.0 # almost the normalized circle diameter

    # arbitrary thresholds to determine when a stream is spaced
    # enough that it becomes hard to alternate
    STREAM_SPACING = 110.0
    SINGLE_SPACING = 125.0

    if difftype == DIFF_AIM:
        return (pow(distance, 0.99), False)

    elif difftype == DIFF_SPEED:
        if distance > SINGLE_SPACING:
            return (2.5, True)

        elif distance > STREAM_SPACING:
            return ((
                1.6 + 0.9 * (distance - STREAM_SPACING) /
                (SINGLE_SPACING - STREAM_SPACING)
            ), False)

        elif distance > ALMOST_DIAMETER:
            return ((
                1.2 + 0.4 * (distance - ALMOST_DIAMETER) /
                (STREAM_SPACING - ALMOST_DIAMETER)
            ), False)

        elif distance > ALMOST_DIAMETER / 2.0:
            return ((
                0.95 + 0.25 * (distance - ALMOST_DIAMETER / 2.0) /
                (ALMOST_DIAMETER / 2.0)
            ), False)

        return (0.95, False)


    raise NotImplementedError


DECAY_BASE = [ 0.3, 0.15 ] # strain decay per interval

def d_strain(difftype, obj, prevobj, speed_mul):
    # calculates the difftype strain value for a hitobject. stores
    # the result in obj.strains[difftype]
    # this assumes that normpos is already computed

    WEIGHT_SCALING = [ 1400.0, 26.25 ] # balances speed and aim

    t = difftype
    value = 0.0
    time_elapsed = (obj.time - prevobj.time) / speed_mul
    decay = pow(DECAY_BASE[t], time_elapsed / 1000.0)

    # this implementation doesn't account for sliders
    if obj.objtype & (OBJ_SLIDER | OBJ_CIRCLE) != 0:
        value, is_single = d_spacing_weight(
            t, (obj.normpos - prevobj.normpos).len()
        )
        value *= WEIGHT_SCALING[t]
        if t == DIFF_SPEED:
            obj.is_single = is_single


    # prevents retarded results for hit object spams
    value /= max(time_elapsed, 50.0)
    obj.strains[t] = prevobj.strains[t] * decay + value


class diff_calc:
    """
    difficulty calculator.

    fields:
    total: star rating
    aim: aim stars
    speed: speed stars
    nsingles: number of notes that are considered singletaps by
              the difficulty calculator
    nsingles_threshold: number of taps slower or equal to the
                        singletap threshold value
    """

    def __init__(self):
        self.strains = []
        # NOTE: i tried pre-allocating this to 600 elements or so
        # and it didn't show appreciable performance improvements

        self.reset()


    def reset(self):
        self.total = self.aim = self.speed = 0.0
        self.nsingles = self.nsingles_threshold = 0


    def __str__(self):
        return """%g stars (%g aim, %g speed)
%d spacing singletaps
%d taps within singletap threshold""" % (
            self.total, self.aim, self.speed, self.nsingles,
            self.nsingles_threshold
        )


    def calc_individual(self, difftype, bmap, speed_mul):
        # calculates total strain for difftype. this assumes the
        # normalized positions for hitobjects are already present

        # max strains are weighted from highest to lowest.
        # this is how much the weight decays
        DECAY_WEIGHT = 0.9

        # strains are calculated by analyzing the map in chunks
        # and taking the peak strains in each chunk. this is the
        # length of a strain interval in milliseconds
        strain_step = 400.0 * speed_mul

        self.strains[:] = []
        interval_end = strain_step
        max_strain = 0.0

        objs = bmap.hitobjects
        t = difftype

        for i, obj in enumerate(objs[1:]):
            prev = objs[i]

            d_strain(difftype, obj, prev, speed_mul)

            while obj.time > interval_end:
                # add max strain for this interval
                self.strains.append(max_strain)

                # decay last object's strains until the next
                # interval and use that as the initial max strain
                decay = pow(
                    DECAY_BASE[t],
                    (interval_end - prev.time) / 1000.0
                )

                max_strain = prev.strains[t] * decay
                interval_end += strain_step


            max_strain = max(max_strain, obj.strains[t])


        # weight the top strains sorted from highest to lowest
        weight = 1.0
        difficulty = 0.0

        strains = self.strains
        strains.sort(reverse=True)

        for strain in strains:
            difficulty += strain * weight
            weight *= DECAY_WEIGHT


        return difficulty


    def calc(self, bmap, mods=MODS_NOMOD, singletap_threshold=125):
        """
        calculates difficulty and stores results in self.total,
        self.aim, self.speed, self.nsingles,
        self.nsingles_threshold.

        returns self.

        singletap_threshold is the smallest milliseconds interval
        that will be considered singletappable, defaults to 125ms
        which is 240 bpm 1/2 ((60000 / 240) / 2)
        """

        # non-normalized diameter where the small circle size buff
        # starts
        CIRCLESIZE_BUFF_THRESHOLD = 30.0
        STAR_SCALING_FACTOR = 0.0675 # global stars multiplier

        # 50% of the difference between aim and speed is added to
        # star rating to compensate aim only or speed only maps
        EXTREME_SCALING_FACTOR = 0.5

        PLAYFIELD_WIDTH = 512.0 # in osu!pixels
        playfield_center = v2f(
            PLAYFIELD_WIDTH / 2, PLAYFIELD_WIDTH / 2
        )

        if bmap.mode != MODE_STD:
            raise NotImplementedError

        self.reset()

        # calculate CS with mods
        speed_mul, _, _, cs, _ = mods_apply(mods, cs=bmap.cs)

        # circle radius
        radius = (
            (PLAYFIELD_WIDTH / 16.0) *
            (1.0 - 0.7 * (cs - 5.0) / 5.0)
        )

        # positions are normalized on circle radius so that we can
        # calc as if everything was the same circlesize
        scaling_factor = 52.0 / radius

        # low cs buff (credits to osuElements)
        if radius < CIRCLESIZE_BUFF_THRESHOLD:
            scaling_factor *= (
                1.0 +
                min(CIRCLESIZE_BUFF_THRESHOLD - radius, 5.0)
                    / 50.0
            )


        playfield_center *= scaling_factor

        # calculate normalized positions
        objs = bmap.hitobjects
        for obj in objs:
            if obj.objtype & OBJ_SPINNER != 0:
                obj.normpos = v2f(
                    playfield_center.x, playfield_center.y
                )
            else:
                obj.normpos = obj.data.pos * scaling_factor


        # speed and aim stars
        b = bmap
        self.speed = self.calc_individual(DIFF_SPEED, b, speed_mul)
        self.aim = self.calc_individual(DIFF_AIM, b, speed_mul)

        self.speed = math.sqrt(self.speed) * STAR_SCALING_FACTOR
        self.aim = math.sqrt(self.aim) * STAR_SCALING_FACTOR
        if mods & MODS_TOUCH_DEVICE != 0:
            self.aim = pow(self.aim, 0.8)

        # total stars
        self.total = self.aim + self.speed
        self.total += (
            abs(self.speed - self.aim) *
                EXTREME_SCALING_FACTOR
        )

        # singletap stats
        for i, obj in enumerate(objs[1:]):
            prev = objs[i]

            if obj.is_single:
                self.nsingles += 1

            if obj.objtype & (OBJ_CIRCLE | OBJ_SLIDER) == 0:
                continue

            interval = (obj.time - prev.time) / speed_mul

            if interval >= singletap_threshold:
                self.nsingles_threshold += 1


        return self

# -------------------------------------------------------------------------
# pp calculator

def acc_calc(n300, n100, n50, misses):
    """calculates accuracy (0.0-1.0)"""
    h = n300 + n100 + n50 + misses

    if h <= 0:
        return 0.0

    return (n50 * 50.0 + n100 * 100.0 + n300 * 300.0) / (h * 300.0)


def acc_round(acc_percent, nobjects, misses):
    """
    rounds to the closest amount of 300s, 100s, 50s
    returns (n300, n100, n50)
    """

    misses = min(nobjects, misses)
    max300 = nobjects - misses
    maxacc = acc_calc(max300, 0, 0, misses) * 100.0
    acc_percent = max(0.0, min(maxacc, acc_percent))

    n50 = n300 = 0

    # just some black magic maths from wolfram alpha
    n100 = round(
        -3.0 *
        ((acc_percent * 0.01 - 1.0) * nobjects + misses) * 0.5
    )

    n100 = int(n100)

    if n100 > nobjects - misses:
        # acc lower than all 100s, use 50s
        n100 = 0
        n50 = round(
            -6.0 * (
                (acc_percent * 0.01 - 1.0) * nobjects
                + misses
            ) * 0.5
        )

        n50 = int(n50)
        n50 = min(max300, n50)

    else:
        n100 = min(max300, n100)

    n300 = nobjects - n100 - n50 - misses

    return (n300, n100, n50)


def pp_base(stars):
    # base pp value for stars, used internally by ppv2
    return (
        pow(5.0 * max(1.0, stars / 0.0675) - 4.0, 3.0) / 100000.0
    )


def ppv2(
    aim_stars=None, speed_stars=None, max_combo=None,
    nsliders=None, ncircles=None, nobjects=None, base_ar=5.0,
    base_od=5.0, mode=MODE_STD, mods=MODS_NOMOD, combo=None,
    n300=None, n100=0, n50=0, nmiss=0, score_version=1, bmap=None
):
    """
    calculates ppv2

    returns (pp, aim_pp, speed_pp, acc_pp, acc_percent)

    if bmap is provided, mode, base_ar, base_od, max_combo,
    nsliders, ncircles and nobjects are taken from it. otherwise
    they must be provided.

    if combo is None, max_combo is used.
    if n300 is None, max_combo - n100 - n50 - nmiss is used.
    """
    if mode != MODE_STD:
        info(
            "ppv2 is only implemented for osu!std at the moment\n"
        )
        raise NotImplementedError


    if bmap != None:
        mode = bmap.mode
        base_ar = bmap.ar
        base_od = bmap.od
        max_combo = bmap.max_combo()
        nsliders = bmap.nsliders
        ncircles = bmap.ncircles
        nobjects = len(bmap.hitobjects)

    else:
        if aim_stars == None:
            raise ValueError("missing aim_stars or bmap")

        if speed_stars == None:
            raise ValueError("missing speed_stars")

        if max_combo == None:
            raise ValueError("missing max_combo or bmap")

        if nsliders == None:
            raise ValueError("missing nsliders or bmap")

        if ncircles == None:
            raise ValueError("missing ncircles or bmap")

        if nobjects == None:
            raise ValueError("missing nobjects or bmap")


    if max_combo <= 0:
        info("W: max_combo <= 0, changing to 1\n")
        max_combo = 1

    if combo == None:
        combo = max_combo - nmiss

    if n300 == None:
        n300 = nobjects - n100 - n50 - nmiss

    # accuracy ----------------------------------------------------
    accuracy = acc_calc(n300, n100, n50, nmiss)
    real_acc = accuracy

    if score_version == 1:
        # scorev1 ignores sliders since they are free 300s
        # for whatever reason it also ignores spinners
        nspinners = nobjects - nsliders - ncircles
        real_acc = acc_calc(
            n300 - nsliders - nspinners, n100, n50, nmiss
        )

        # can go negative if we miss everything
        real_acc = max(0.0, real_acc)

    elif score_version == 2:
        ncircles = nobjects

    else:
        info("unsupported scorev%d\n" % (score_version))
        raise NotImplementedError

    # global values -----------------------------------------------
    nobjects_over_2k = nobjects / 2000.0

    length_bonus = 0.95 + 0.4 * min(1.0, nobjects_over_2k)

    if nobjects > 2000:
        length_bonus += math.log10(nobjects_over_2k) * 0.5

    miss_penality = pow(0.97, nmiss)
    combo_break = pow(combo, 0.8) / pow(max_combo, 0.8)

    # calculate stats with mods
    speed_mul, ar, od, _, _ = (
        mods_apply(mods, ar=base_ar, od=base_od)
    )

    # ar bonus ----------------------------------------------------
    ar_bonus = 1.0

    if ar > 10.33:
        ar_bonus += 0.45 * (ar - 10.33)

    elif ar < 8.0:
        low_ar_bonus = 0.01 * (8.0 - ar)

        if mods & MODS_HD != 0:
            low_ar_bonus *= 2.0

        ar_bonus += low_ar_bonus


    # aim pp ------------------------------------------------------
    aim = pp_base(aim_stars)
    aim *= length_bonus
    aim *= miss_penality
    aim *= combo_break
    aim *= ar_bonus

    if mods & MODS_HD != 0:
        aim *= 1.02 + (11 - ar) / 50

    if mods & MODS_FL != 0:
        aim *= 1.45 * length_bonus

    acc_bonus = 0.5 + accuracy / 2.0
    od_bonus = 0.98 + (od * od) / 2500.0

    aim *= acc_bonus
    aim *= od_bonus

    # speed pp ----------------------------------------------------
    speed = pp_base(speed_stars)
    speed *= length_bonus
    speed *= miss_penality
    speed *= combo_break
    speed *= acc_bonus
    speed *= od_bonus

    if mods & MODS_HD != 0:
        speed *= 1.18

    # acc pp ------------------------------------------------------
    acc = pow(1.52163, od) * pow(real_acc, 24.0) * 2.83

    # length bonus (not the same as speed/aim length bonus)
    acc *= min(1.15, pow(ncircles / 1000.0, 0.3))

    if mods & MODS_HD != 0:
        acc *= 1.02

    if mods & MODS_FL != 0:
        acc *= 1.02

    # total pp ----------------------------------------------------
    final_multiplier = 1.12

    if mods & MODS_NF != 0:
        final_multiplier *= 0.90

    if mods & MODS_SO != 0:
        final_multiplier *= 0.95

    total = (
        pow(
            pow(aim, 1.1) + pow(speed, 1.1) + pow(acc, 1.1),
            1.0 / 1.1
        ) * final_multiplier
    )

    return (total, aim, speed, acc, accuracy * 100.0)


# -------------------------------------------------------------------------
# usage example

if __name__ == "__main__":
    import traceback

    mods = 0
    acc_percent = 100.0
    combo = -1
    nmiss = 0

    # get mods, acc, combo, misses from command line arguments
    # format: +HDDT 95% 300x 1m
    for arg in sys.argv:
        if arg.startswith("+"):
            mods = mods_from_str(arg[1:])
        elif arg.endswith("%"):
            acc_percent = float(arg[:-1])
        elif arg.endswith("x"):
            combo = int(arg[:-1])
        elif arg.endswith("m"):
            nmiss = int(arg[:-1])


    try:
        p = parser()
        bmap = p.map(sys.stdin)
        if combo < 0:
            combo = bmap.max_combo()

        print("%s - %s [%s] +%s" % (bmap.artist, bmap.title,
            bmap.version, mods_str(mods)))
        print("OD%g AR%g CS%g HP%g" % (bmap.od, bmap.ar, bmap.cs,
            bmap.hp))
        stars = diff_calc().calc(bmap, mods)
        print("max combo: %d\n" % (bmap.max_combo()))
        print(stars)

        # round acc percent to the closest 300/100/50 count
        n300, n100, n50 = acc_round(acc_percent,
            len(bmap.hitobjects), nmiss)

        # ppv2 returns a tuple (pp, aim, speed, acc, percent)
        print("%g pp (%g aim, %g speed, %g acc) for %g%%" % (
            ppv2(
                aim_stars=stars.aim,
                speed_stars=stars.speed,
                bmap=bmap,
                n300=n300, n100=n100, n50=n50, nmiss=nmiss,
                mods=mods,
                combo=combo,
            )
        ))

    except KeyboardInterrupt:
        pass
    except Exception as e:
        if p.done:
            raise
        else: # beatmap parsing error, print parser state
            info("%s\n%s\n" % (traceback.format_exc(), str(p)))
