import codecs
import math
import os
import re

from . import slidercalc


# Translated from JavaScript to Python by Awlex

class BeatmapParser():
    def __init__(self):

        self.osu_section = None
        self.beatmap = {
            "nbCircles": 0,
            "nbSliders": 0,
            "nbSpinners": 0,
            "timingPoints": [],
            "breakTimes": [],
            "hitObjects": []
        }

        self.timing_lines = []
        self.object_lines = []
        self.events_lines = []
        self.section_reg = re.compile('^\[([a-zA-Z0-9]+)\]$')
        self.key_val_reg = re.compile('^([a-zA-Z0-9]+)[ ]*:[ ]*(.+)$')
        self.curve_types = {
            "C": "catmull",
            "B": "bezier",
            "L": "linear",
            "P": "pass-through"
        }

    # Get the timing point affecting a specific offset
    # @param  {Integer} offset
    # @return {Object} timingPoint
    async def get_timing_point(self, offset):
        for i in reversed(range(len(self.beatmap["timingPoints"]))):
            if self.beatmap["timingPoints"][i]["offset"] <= offset:
                return self.beatmap["timingPoints"][i]
        return self.beatmap["timingPoints"][0]

    # Parse additions member
    # @param  {String} str         additions member (sample:add:customSampleIndex:Volume:hitsound)
    # @return {Object} additions   a list of additions
    async def parse_additions(self, line):
        if not line:
            return {}

        additions = {}
        adds = line.split(':')

        if adds[0] and adds[0] != '0':
            additions["sample"] = {
                '1': 'normal',
                '2': 'soft',
                '3': 'drum'
            }[adds[0]]

        if adds[1] and adds[1] != '0':
            additions["additionalSample"] = {
                '1': 'normal',
                '2': 'soft',
                '3': 'drum'
            }[adds[1]]

            if len(adds) > 2 and adds[2] and adds[2] != '0':
                additions["customSampleIndex"] = int(adds[2])
                if len(adds) > 3 and adds[3] and adds[3] != '0':
                    additions["hitsoundVolume"] = int(adds[3])
                    if len(adds) > 4 and adds[4]:
                        additions["hitsound"] = adds[4]
        return additions

    # Parse a timing line
    # @param  {String} line
    async def parse_timing_point(self, line):
        members = line.split(',')

        timing_point = {
            "offset": int(float(members[0])),
            "beatLength": float(members[1]),
            "velocity": 1,
            "timingSignature": int(members[2]),
            "sampleSetId": int(members[3]),
            "customSampleIndex": int(members[4]),
            "sampleVolume": int(members[5]),
            "timingChange": (members[6] == 1),
            "kiaiTimeActive": (members[7] == 1)
        }

        if not math.isnan(timing_point["beatLength"]) and timing_point["beatLength"] != 0:
            if timing_point["beatLength"] > 0:
                # If positive, beatLength is the length of a beat in milliseconds
                bpm = round(60000 / timing_point["beatLength"])
                self.beatmap["bpmMin"] = min(self.beatmap["bpmMin"], bpm) if "bpmMin" in self.beatmap else bpm
                self.beatmap["bpmMax"] = max(self.beatmap["bpmMax"], bpm) if "bpmMax" in self.beatmap else bpm
                timing_point["bpm"] = bpm
            else:
                # If negative, beatLength is a velocity factor
                timing_point["velocity"] = abs(100 / timing_point["beatLength"])

        self.beatmap["timingPoints"].append(timing_point)

    # Parse an object line
    # @param  {String} line
    async def parse_hit_object(self, line):
        members = line.split(',')

        sound_type = int(members[4])
        object_type = int(members[3])

        hit_object = {
            "startTime": int(members[2]),
            "newCombo": object_type & 4,
            "soundTypes": [],
            "position": [
                int(members[0]),
                int(members[1])
            ]
        }

        # sound type is a bitwise flag enum
        # 0 : normal
        # 2 : whistle
        # 4 : finish
        # 8 : clap
        if sound_type & 2:
            hit_object["soundTypes"].append('whistle')
        if sound_type & 4:
            hit_object["soundTypes"].append('finish')

        if sound_type & 8:
            hit_object["soundTypes"].append('clap')

        if not len(hit_object["soundTypes"]):
            hit_object["soundTypes"].append('normal')

        # object type is a bitwise flag enum
        # 1: circle
        # 2: slider
        # 8: spinner
        if object_type & 1:
            # Circle
            self.beatmap["nbCircles"] += 1
            hit_object["object_name"] = 'circle'
            if len(members) > 6:
                hit_object["additions"] = await self.parse_additions(members[5])
        elif object_type & 8:
            # Spinner
            self.beatmap["nbSpinners"] += 1
            hit_object["object_name"] = 'spinner'
            hit_object["end_time"] = int(members[5])
            if len(members) > 7:
                hit_object["additions"] = await self.parse_additions(members[6])
        elif object_type & 2:
            # Slider
            try:
                self.beatmap["nbSliders"] += 1
                hit_object["object_name"] = 'slider'
                hit_object["repeatCount"] = int(members[6])
                hit_object["pixelLength"] = int(round(float(members[7])))
                if len(members) > 10:
                    hit_object["additions"] = await self.parse_additions(members[10])
                hit_object["edges"] = []
                hit_object["points"] = [
                    [hit_object["position"][0], hit_object["position"][1]]
                ]
            except Exception as e:
                raise e

            # Calculate slider duration
            timing = await self.get_timing_point(hit_object["startTime"])

            if timing:
                px_per_beat = float(self.beatmap["SliderMultiplier"]) * 100 * float(timing["velocity"])
                beats_number = (hit_object["pixelLength"] * int(hit_object["repeatCount"])) / px_per_beat
                hit_object["duration"] = math.ceil(beats_number * timing["beatLength"])
                hit_object["end_time"] = hit_object["startTime"] + hit_object["duration"]

            # Parse slider points
            points = (members[5] or '').split('|')
            if len(points):
                hit_object["curveType"] = self.curve_types[points[0]] or 'unknown'

                for i in range(1, len(points)):
                    coordinates = points[i].split(':')
                    hit_object["points"].append([
                        int(coordinates[0]),
                        int(coordinates[1])
                    ])

            if len(members) > 9:
                edge_sounds = []
                edge_additions = []
                if members[8]:
                    edge_sounds = members[8].split('|')

                if members[9]:
                    edge_additions = members[9].split('|')

                # Get soundTypes and additions for each slider edge
                for j in range(hit_object["repeatCount"] + 1):
                    edge = {
                        "soundTypes": [],
                        "additions": await self.parse_additions(edge_additions[j])
                    }

                    if edge_sounds[j]:
                        sound = int(edge_sounds[j])
                        if sound & 2:
                            edge["soundTypes"].append('whistle')

                        if sound & 4:
                            edge["soundTypes"].append('finish')

                        if sound & 8:
                            edge["soundTypes"].append('clap')

                        if not len(edge["soundTypes"]):
                            edge["soundTypes"].append('normal')

                    else:
                        edge["soundTypes"].append('normal')

                    hit_object["edges"].append(edge)

            # get coordinates of the slider endpoint
            end_point = slidercalc.get_end_point(hit_object["curveType"], hit_object["pixelLength"],
                                                 hit_object["points"])
            if end_point and end_point[0] and end_point[1]:
                hit_object["end_position"] = [
                    round(end_point[0]),
                    round(end_point[1])
                ]
            else:
                # If endPosition could not be calculated, approximate it by setting it to the last point
                hit_object["end_position"] = hit_object["points"][len(hit_object["points"]) - 1]

        else:
            # Unknown
            hit_object["object_name"] = 'unknown'

        self.beatmap["hitObjects"].append(hit_object)

    # Parse an event line
    # @param  {String} line
    async def parse_event(self, line):
        # Background line : 0,0,"bg.jpg"
        # TODO: confirm that the second member is always zero
        #
        # Breaktimes lines : 2,1000,2000
        # second integer is start offset
        # third integer is end offset
        members = line.split(',')

        if members[0] == '0' and members[1] == '0' and members[2]:
            bg_name = members[2].trim()

            if bg_name[0] == '"' and bg_name[len(bg_name) - 1] == '"':
                self.beatmap["bg_filename"] = bg_name.substring(1, bg_name.length - 1)
            else:
                self.beatmap["bg_filename"] = bg_name
        elif members[0] == '2' and re.search('/^[0-9]+$/', members[1]) and re.search('/^[0-9]+$/', members[2]):
            self.beatmap["breakTimes"].append({
                "startTime": int(members[1]),
                "endTime": int(members[2])
            })

    # Compute the total time and the draining time of the beatmap
    async def compute_duration(self):
        if not len(self.beatmap["hitObjects"]):
            return
        first_object = self.beatmap["hitObjects"][0]
        last_object = self.beatmap["hitObjects"][len(self.beatmap["hitObjects"]) - 1]

        total_break_time = 0

        for break_time in self.beatmap["breakTimes"]:
            total_break_time += (break_time.endTime - break_time.startTime)

        if first_object and last_object:
            self.beatmap["total_time"] = math.floor(last_object["startTime"] / 1000)
            self.beatmap["draining_time"] = math.floor(
                (last_object["startTime"] - first_object["startTime"] - total_break_time) / 1000)
        else:
            self.beatmap["total_time"] = 0
            self.beatmap["draining_time"] = 0

    # Browse objects and compute max combo
    async def compute_max_combo(self):
        if not len(self.beatmap["timingPoints"]):
            return

        max_combo = 0
        slider_multiplier = float(self.beatmap["SliderMultiplier"])
        slider_tick_rate = float(self.beatmap["SliderTickRate"])

        timing_points = self.beatmap["timingPoints"]
        current_timing = timing_points[0]
        next_offset = timing_points[1]["offset"] if len(timing_points) > 1 else math.inf
        i = 1

        for hit_object in self.beatmap["hitObjects"]:
            if hit_object["startTime"] >= next_offset:
                current_timing = timing_points[i]
                i += 1
                next_offset = timing_points[i]["offsxet"] if i in timing_points else math.inf

            osupx_per_beat = slider_multiplier * 100 * current_timing["velocity"]
            tick_length = osupx_per_beat / slider_tick_rate

            if hit_object["object_name"] == 'spinner' or hit_object["object_name"]== 'circle':
                max_combo += 1
            elif hit_object["object_name"]== 'slider':
                tick_per_side = math.ceil((math.floor(hit_object["pixelLength"] / tick_length * 100) / 100) - 1)
                max_combo += (len(hit_object["edges"]) - 1) * (
                    tick_per_side + 1) + 1  # 1 combo for each tick and endpoint

        self.beatmap["maxCombo"] = max_combo

    # Read a single line, parse when key/value, store when further parsing needed
    # @param  {String|Buffer} line
    async def read_line(self, line: str):
        line = line.strip()
        if not line:
            return

        match = self.section_reg.match(line)
        if match:
            self.osu_section = match.group(1).lower()
            return

        if self.osu_section == 'timingpoints':
            self.timing_lines.append(line)
        elif self.osu_section == 'hitobjects':
            self.object_lines.append(line)
            self.events_lines.append(line)
        else:
            match = re.match('^osu file format (v[0-9]+)$', line)
            if match:
                self.beatmap["fileFormat"] = match.group(1)

            # Apart from events, timingpoints and hitobjects sections, lines are "key: value"
            match = self.key_val_reg.match(line)
            if match:
                self.beatmap[match.group(1)] = match.group(2)

    # Compute everything that require the file to be completely parsed and return the beatmap
    # @return {Object} beatmap
    async def build_beatmap(self):
        if "Tags" in self.beatmap:
            self.beatmap["Tags"] = str(self.beatmap["Tags"]).split(" ")

        for event_line in self.events_lines:
            await self.parse_event(event_line)
        self.beatmap["breakTimes"].sort(key=lambda a, b: 1 if a.startTime > b.startTime else -1)

        for timing_line in self.timing_lines:
            await self.parse_timing_point(timing_line)
        self.beatmap["timingPoints"].sort(key=lambda a: a['offset'])
        timing_points = self.beatmap["timingPoints"]

        for i in range(1, len(timing_points)):
            if not "bpm" in timing_points[i]:
                timing_points[i]["beatLength"] = timing_points[i - 1]["beatLength"]
                timing_points[i]["bpm"] = timing_points[i - 1]["bpm"]

        for object_line in self.object_lines:
            await self.parse_hit_object(object_line)
        self.beatmap["hitObjects"].sort(key=lambda a: a["startTime"])
        await self.compute_max_combo()
        await self.compute_duration()
        return self.beatmap

        # return {
        #     "readLine": readLine,
        #     "buildBeatmap": buildBeatmap
        # }

    # Parse a .osu file
    # @param  {String}   file  path to the file

    async def parseFile(self, file):
        if os.path.isfile(file):

            with codecs.open(file, 'r', encoding="utf-8") as file:
                line = file.readline()
                while line:
                    await self.read_line(line)
                    line = file.readline()