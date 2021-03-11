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
__version__ = "2.0.0"

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

    def dot(self, other):
        return self.x * other.x + self.y * other.y


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
        self.angle = 0.0
        self.strains = [ 0.0, 0.0 ]
        self.is_single = False
        self.delta_time = 0.0
        self.d_distance = 0.0


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

def convert_droid_mods(droidMods):
    """
    Converts droid mod string to PC mod string.
    """

    # Honestly not the best implementation, but the core is there
    finalMods = "td"

    if "a" in droidMods:
        finalMods += "at"

    if "x" in droidMods:
        finalMods += "rx"

    if "p" in droidMods:
        finalMods += "ap"

    if "e" in droidMods:
        finalMods += "ez"

    if "n" in droidMods:
        finalMods += "nf"

    if "r" in droidMods:
        finalMods += "hr"

    if "h" in droidMods:
        finalMods += "hd"

    if "i" in droidMods:
        finalMods += "fl"

    if "d" in droidMods:
        finalMods += "dt"

    if "c" in droidMods:
        finalMods += "nc"

    if "t" in droidMods:
        finalMods += "ht"

    if "s" in droidMods:
        finalMods += "pr"

    if "m" in droidMods:
        finalMods += "sc"

    if "b" in droidMods:
        finalMods += "su"

    if "l" in droidMods:
        finalMods += "re"

    if "f" in droidMods:
        finalMods += "pf"
        
    if "u" in droidMods:
        finalMods += "sd"

    if "v" in droidMods:
        finalMods += "v2"

    return finalMods.upper()

def mods_apply(mods, ar = None, od = None, cs = None, hp = None):
    """
    calculates speed multiplier, ar, od, cs, hp with the given
    mods applied. returns (speed_mul, ar, od, cs, hp).

    the base stats are all optional and default to None. if a base
    stat is None, then it won't be calculated and will also be
    returned as None.
    """

    AR0_MS = 1800
    AR5_MS = 1200
    AR10_MS = 450

    AR_MS_STEP1 = (AR0_MS - AR5_MS) / 5.0
    AR_MS_STEP2 = (AR5_MS - AR10_MS) / 5.0

    speed_mul = 1.0

    if "c" in mods or "d" in mods:
        speed_mul = 1.5

    if "t" in mods:
        speed_mul *= 0.75

    od_ar_hp_multiplier = 1.0

    if "r" in mods:
        od_ar_hp_multiplier = 1.4

    if "e" in mods:
        od_ar_hp_multiplier *= 0.5

    if ar != None:
        ar *= od_ar_hp_multiplier

        if "l" in mods:
            if "e" in mods:
                ar *= 2
                ar -= 0.5
            ar -= 0.5
            ar -= speed_mul - 1

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
        od = min(od * od_ar_hp_multiplier, 10)

        droidms = 55 + 6 * (5 - od) if "s" in mods else 75 + 5 * (5 - od)
        droidms /= speed_mul

        od = 5 - (droidms - 50) / 6


    if cs != None:
        scale = ((681 / 480) * (54.42 - cs * 4.48) * 2 / 128) + 0.5 * (11 - 5.2450170716245195) / 5
        if "r" in mods:
            scale -= 0.125

        if "e" in mods:
            scale += 0.125
        
        if "m" in mods:
            scale -= ((681 / 480) * (54.42 - 4 * 4.48) * 2 / 128)

        radius = 64 * scale / (681 * 0.85 / 384)
        cs = min(5 + (1 - radius / 32) * 5 / 0.7, 10)


    if hp != None:
        hp = min(10.0, hp * od_ar_hp_multiplier)

    return (speed_mul, ar, od, cs, hp)


# -------------------------------------------------------------------------
# difficulty calculator

DIFF_SPEED = 0
DIFF_AIM = 1

def d_spacing_weight(difftype, distance, delta_time, prev_distance,
    prev_delta_time, angle):

    # calculates spacing weight and returns (weight, is_single)
    # NOTE: is_single is only computed for DIFF_SPEED

    MIN_SPEED_BONUS = 75.0 # ~200BPM 1/4 streams
    MAX_SPEED_BONUS = 53.0 # ~280BPM 1/4 streams -- edit to fit droid
    ANGLE_BONUS_SCALE = 90
    AIM_TIMING_THRESHOLD = 107
    SPEED_ANGLE_BONUS_BEGIN = 5 * math.pi / 6
    AIM_ANGLE_BONUS_BEGIN = math.pi / 3

    # arbitrary thresholds to determine when a stream is spaced
    # enough that it becomes hard to alternate
    SINGLE_SPACING = 125.0

    strain_time = max(delta_time, 50.0)
    prev_strain_time = max(prev_delta_time, 50.0)

    if difftype == DIFF_AIM:
        result = 0.0
        if angle is not None and angle > AIM_ANGLE_BONUS_BEGIN:
            angle_bonus = math.sqrt(
                max(prev_distance - ANGLE_BONUS_SCALE, 0.0) *
                pow(math.sin(angle - AIM_ANGLE_BONUS_BEGIN), 2.0) *
                max(distance - ANGLE_BONUS_SCALE, 0.0)
            )
            result = (
                1.5 * pow(max(0.0, angle_bonus), 0.99) /
                max(AIM_TIMING_THRESHOLD, prev_strain_time)
            )
        weighted_distance = pow(distance, 0.99)
        res = max(result +
            weighted_distance / max(AIM_TIMING_THRESHOLD, strain_time),
            weighted_distance / strain_time)
        return (res, False)

    elif difftype == DIFF_SPEED:
        is_single = distance > SINGLE_SPACING
        distance = min(distance, SINGLE_SPACING)
        delta_time = max(delta_time, MAX_SPEED_BONUS)
        speed_bonus = 1.0
        if delta_time < MIN_SPEED_BONUS:
            speed_bonus += pow((MIN_SPEED_BONUS - delta_time) / 40.0, 2)
        angle_bonus = 1.0
        if angle is not None and angle < SPEED_ANGLE_BONUS_BEGIN:
             s = math.sin(1.5 * (SPEED_ANGLE_BONUS_BEGIN - angle))
             angle_bonus += s * s / 3.57
             if angle < math.pi / 2.0:
                angle_bonus = 1.28
                if distance < ANGLE_BONUS_SCALE and angle < math.pi / 4.0:
                    angle_bonus += (
                        (1.0 - angle_bonus) *
                        min((ANGLE_BONUS_SCALE - distance) / 10.0, 1.0)
                    )
                elif distance < ANGLE_BONUS_SCALE:
                    angle_bonus += (
                        (1.0 - angle_bonus) *
                        min((ANGLE_BONUS_SCALE - distance) / 10.0, 1.0) *
                        math.sin((math.pi / 2.0 - angle) * 4.0 / math.pi)
                    )
        res = (
            (1 + (speed_bonus - 1) * 0.75) * angle_bonus *
            (0.95 + speed_bonus * pow(distance / SINGLE_SPACING, 3.5))
        ) / strain_time
        return (res, is_single)


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
    obj.delta_time = time_elapsed
    decay = pow(DECAY_BASE[t], time_elapsed / 1000.0)

    # this implementation doesn't account for sliders
    if obj.objtype & (OBJ_SLIDER | OBJ_CIRCLE) != 0:
        distance = (obj.normpos - prevobj.normpos).len()
        obj.d_distance = distance
        value, is_single = d_spacing_weight(t, distance, time_elapsed,
            prevobj.d_distance, prevobj.delta_time, obj.angle)
        value *= WEIGHT_SCALING[t]
        if t == DIFF_SPEED:
            obj.is_single = is_single


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
        self.total = 0.0
        self.aim = self.aim_difficulty = self.aim_length_bonus = 0.0
        self.speed = self.speed_difficulty = self.speed_length_bonus = 0.0
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

        objs = bmap.hitobjects
        self.strains[:] = []
        # first object doesn't generate a strain so we begin with
        # an incremented interval end
        interval_end = (
          math.ceil(objs[0].time / strain_step) * strain_step
        )
        max_strain = 0.0

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


        # don't forget to add the last strain
        self.strains.append(max_strain)

        # weight the top strains sorted from highest to lowest
        weight = 1.0
        total = 0.0
        difficulty = 0.0

        strains = self.strains
        strains.sort(reverse=True)

        for strain in strains:
            total += pow(strain, 1.2)
            difficulty += strain * weight
            weight *= DECAY_WEIGHT


        return ( difficulty, total )


    def calc(self, bmap, mods, singletap_threshold=125):
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
        #
        # edit to 40% for droid
        EXTREME_SCALING_FACTOR = 0.4

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
                1.0 + min(CIRCLESIZE_BUFF_THRESHOLD - radius, 5.0) / 50.0
            )


        playfield_center *= scaling_factor

        # calculate normalized positions
        objs = bmap.hitobjects
        prev1 = None
        prev2 = None
        i = 0
        for obj in objs:
            if obj.objtype & OBJ_SPINNER != 0:
                obj.normpos = v2f(
                    playfield_center.x, playfield_center.y
                )
            else:
                obj.normpos = obj.data.pos * scaling_factor

            if i >= 2:
                v1 = prev2.normpos - prev1.normpos
                v2 = obj.normpos - prev1.normpos
                dot = v1.dot(v2)
                det = v1.x * v2.y - v1.y * v2.x
                obj.angle = abs(math.atan2(det, dot))
            else:
                obj.angle = None

            prev2 = prev1
            prev1 = obj
            i+=1

        b = bmap

        # speed and aim stars
        speed = self.calc_individual(DIFF_SPEED, b, speed_mul)
        self.speed = speed[0]
        self.speed_difficulty = speed[1]

        aim = self.calc_individual(DIFF_AIM, b, speed_mul)
        self.aim = aim[0]
        self.aim_difficulty = aim[1]

        def length_bonus(star, diff):
            return (
              0.32 + 0.5 * (math.log10(diff + star) - math.log10(star))
            )

        self.aim_length_bonus = length_bonus(self.aim, self.aim_difficulty)
        self.speed_length_bonus = (
          length_bonus(self.speed, self.speed_difficulty)
        )
        self.aim = pow(math.sqrt(self.aim) * STAR_SCALING_FACTOR, 0.8)
        self.speed = math.sqrt(self.speed) * STAR_SCALING_FACTOR

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
    base_od=5.0, mode=MODE_STD, mods="", combo=None,
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
    nspinners = nobjects - nsliders - ncircles

    if score_version == 1:
        # scorev1 ignores sliders since they are free 300s
        # for whatever reason it also ignores spinners
        real_acc = (
            ((n300 - (nobjects - ncircles)) * 6 + n100 * 2 + n50) / (ncircles * 6)
        ) if ncircles > 0 else 0

        # can go negative if we miss everything
        real_acc = max(0.0, real_acc)

    elif score_version == 2:
        ncircles = nobjects

    else:
        info("unsupported scorev%d\n" % (score_version))
        raise NotImplementedError

    # global values -----------------------------------------------
    length_bonus = 1.650668 + (0.4845796 - 1.650668) / (1 + pow(nobjects / 817.9306, 1.147469))

    miss_penality_aim = 0.97 * pow(1 - pow(float(nmiss) / nobjects, 0.775), nmiss)
    miss_penality_speed = (
      0.97 * pow(1 - pow(float(nmiss) / nobjects, 0.775), pow(nmiss, 0.875))
    )
    combo_break = min(pow(combo, 0.8) / pow(max_combo, 0.8), 1)

    # calculate stats with mods
    _, ar, od, _, _ = (
        mods_apply(mods, ar=base_ar, od=base_od)
    )

    # ar bonus ----------------------------------------------------
    ar_bonus = 0.0

    if ar > 10.33:
        ar_bonus += 0.4 * (ar - 10.33)

    elif ar < 8.0:
        ar_bonus += 0.01 * (8.0 - ar)


    # aim pp ------------------------------------------------------
    aim = pp_base(aim_stars)
    aim *= length_bonus
    if nmiss > 0:
        aim *= miss_penality_aim
    aim *= combo_break
    aim *= 1.0 + min(ar_bonus, ar_bonus * (nobjects / 1250.0))

    hd_bonus = 1.0
    if "h" in mods:
        # The bonus starts decreasing twice as fast
        # beyond AR10 and reaches 1 at AR11.
        if ar > 10:
            hd_bonus += max(0, 0.08 * (11.0 - ar))
        else:
            hd_bonus += 0.04 * (12.0 - ar)

    aim *= hd_bonus

    if "i" in mods:
        fl_bonus = 1.0 + 0.35 * min(1.0, nobjects / 200.0)
        if nobjects > 200:
            fl_bonus += 0.3 * min(1, (nobjects - 200) / 300.0)
        if nobjects > 500:
            fl_bonus += (nobjects - 500) / 1200.0
        aim *= fl_bonus

    acc_bonus = 0.5 + accuracy / 2.0
    # PC OD can be negative in droid.
    od_squared = od * od if od >= 0 else -(od * od)
    od_bonus = 0.98 + od_squared / 2500.0

    aim *= acc_bonus
    aim *= od_bonus

    # speed pp ----------------------------------------------------
    speed = pp_base(speed_stars)
    speed *= length_bonus
    if nmiss > 0:
        speed *= miss_penality_speed
    speed *= combo_break
    if ar > 10.33:
        speed *= 1.0 + min(ar_bonus, ar_bonus * (nobjects / 1250.0))
    speed *= hd_bonus

    speed *= (0.95 + od_squared / 750.0) * pow(accuracy, (12 - max(od, 2.5)) / 2.0)
    if n50 >= nobjects / 500.0:
        speed *= pow(0.98, n50 - nobjects / 500.0)

    # acc pp ------------------------------------------------------
    # Drastically change acc calculation to fit droid meta.
    # It is harder to get good accuracy with touchscreen, especially in small hit window.
    acc = pow(1.4, od) * pow(max(1, ar / 10), 3) * pow(real_acc, 12) * 10

    # length bonus (not the same as speed/aim length bonus)
    acc *= min(1.15, pow(ncircles / 1000.0, 0.3))

    if "h" in mods:
        acc *= 1.08

    if "i" in mods:
        acc *= 1.02

    # total pp ----------------------------------------------------
    final_multiplier = 1.44

    if "n" in mods:
        final_multiplier *= max(0.9, 1.0 - 0.2 * nmiss)

    # Extreme penalty
    # =======================================================
    # added to penalize map with little aim but ridiculously
    # high speed value (which is easily abusable by using more than 2 fingers).
    extreme_penalty = pow(
        1 - abs(speed - pow(aim, 1.15)) /
        max(speed, pow(aim, 1.15)),
        0.2
    )

    final_multiplier *= max(
        pow(extreme_penalty, 2),
        -2 * pow(1 - extreme_penalty, 2) + 1
    )

    total = (
        pow(
            pow(aim, 1.1) + pow(speed, 1.1) + pow(acc, 1.1),
            1.0 / 1.1
        ) * final_multiplier
    )

    return (total, aim, speed, acc, accuracy * 100.0)