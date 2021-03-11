import re
import math
import logging
import discord
import datetime
import lavalink
from utils import checks
from discord.ext import commands

time_rx = re.compile('[0-9]+')
url_rx = re.compile('https?:\/\/(?:www\.)?.+')

class Audio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.audio_settings = self.bot.db["audio"]
        self.queue_limit = 50

        if not hasattr(bot, 'lavalink'):
            lavalink.Client(bot=bot, password='youshallnotpass', log_level=logging.INFO, rest_port=2500, ws_retry=3, ws_port=2500)
            self.bot.lavalink.register_hook(self.track_hook)

    async def track_hook(self, event):
        if isinstance(event, lavalink.Events.TrackStartEvent):
            c = event.player.fetch('channel')
            if c:
                c = self.bot.get_channel(c)
                if c:
                    channel = c
                    guild = c.guild
                    player = self.bot.lavalink.players.get(guild.id)
                    # print("setting info")
                    # see if previous message was a now playing thing
                    prev_msg = None
                    async for msg in channel.history(limit=1):
                        try:
                            if msg.author.bot:
                                embeds = msg.embeds
                                if embeds:
                                    if embeds[0].title.lower() == "now playing":
                                        prev_msg = msg
                                        break
                        except:
                            pass
                    player.current_info = event.track
                    embed = discord.Embed(colour=c.guild.me.top_role.colour, title='Now Playing', description=event.track.title)
                    embed.set_thumbnail(url=event.track.thumbnail)
                    if prev_msg:
                        await prev_msg.edit(embed=embed)
                    else:
                        await c.send(embed=embed)

        elif isinstance(event, lavalink.Events.QueueEndEvent):
            c = event.player.fetch('channel')
            if c:
                c = self.bot.get_channel(c)
                if c:
                    guild = c.guild
                    player = self.bot.lavalink.players.get(guild.id)
                    await player.disconnect()

    @commands.command(aliases=['sing'])
    async def play(self, ctx, *, query):
        """Request a song using search terms.

        [Options]
        search: Terms you want to use to search for the song or a url.

        [Example]
        +<COMMAND> https://www.youtube.com/watch?v=Aiw3tVU54_E
        """
        user = ctx.message.author
        server = ctx.message.guild
        player = self.bot.lavalink.players.get(ctx.guild.id)
        queue = player.queue

        if len(queue) >= self.queue_limit and str(server.id) != "290312423309705218":
            return await ctx.send(f':red_circle: **The server is at the queue limit of {self.queue_limit}! Please wait.**')

        if not player.is_connected:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.send(':red_circle: **Join a voice channel!**')

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:
                return await ctx.send(':red_circle: **Missing permissions `CONNECT` and/or `SPEAK`.**')

            player.store('channel', ctx.channel.id)
            await player.connect(ctx.author.voice.channel.id)
        else:
            if not ctx.author.voice or not ctx.author.voice.channel or player.connected_channel.id != ctx.author.voice.channel.id:
                return await ctx.send(":red_circle: **Join owo's voice channel!**")

        query = query.strip('<>')

        if not url_rx.match(query):
            query = f'ytsearch:{query}'

        results = await self.bot.lavalink.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send(':red_circle: **Nothing found!**')

        embed = discord.Embed(colour=ctx.guild.me.top_role.colour)
        embed.set_footer(text = f"Requested by {user.name}",
            icon_url=user.avatar_url);

        if results['loadType'] == "PLAYLIST_LOADED":
            if await self.is_dj(ctx) or await self.is_alone(ctx):
                tracks = results['tracks']

                # keep track of limit
                num_queue = self.queue_limit - len(queue)
                queue_tracks = tracks[0:num_queue]
                for track in queue_tracks:
                    player.add(requester=ctx.author.id, track=track)

                trunc_msg = ""
                if len(queue_tracks) < len(tracks):
                    num_untracked = len(tracks) - len(queue_tracks)
                    trunc_msg = f"\n{num_untracked} tracks not queued. {self.queue_limit} limit."

                embed.title = "Playlist Queued!"
                embed.description = f"{results['playlistInfo']['name']} - {len(tracks)} tracks.{trunc_msg}"
                await ctx.send(embed=embed)
            else:
                return await ctx.send(":red_circle: **Only DJs can request playlists.**")
        else:
            track = results['tracks'][0]
            embed.title = "Track Queued"
            embed.description = f'[{track["info"]["title"]}]({track["info"]["uri"]})'
            await ctx.send(embed=embed)
            player.add(requester=ctx.author.id, track=track)

        if not player.is_playing:
            await player.play()

    @commands.command()
    async def seek(self, ctx, time):
        """Skip to a time in the song.

        [Options]
        time: The time you wish to skip to in seconds.

        [Example]
        +<COMMAND> 45
        """
        user = ctx.message.author
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Not playing.**')

        if (str(user.id) == str(song.requester) or
            await self.is_dj(ctx) or await self.is_alone(ctx)):

            seconds = time_rx.search(time)
            if not seconds:
                return await ctx.send(':red_circle: **You need to specify the amount of seconds to skip!**')
            seconds = int(seconds.group()) * 1000
            if time.startswith('-'):
                seconds *= -1
            track_time = player.position + seconds
            await player.seek(track_time)
            await ctx.send(f':white_check_mark: Moved track to **{lavalink.Utils.format_time(track_time)}**')
        else:
            await ctx.send(':red_circle: **No permission to seek.**')

    @commands.command(aliases=['next','forceskip', 'fs'])
    async def skip(self, ctx):
        """Skip the currently paused song.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Not playing.**')

        song = player.current
        requester = ctx.message.guild.get_member(song.requester)

        if (str(user.id) == str(song.requester) or
            await self.is_dj(ctx) or await self.is_alone(ctx)):
            await ctx.send('⏭ **Skipped.**')
            await player.skip()
        else:
            await ctx.send(':red_circle: **No permission to skip.**')

    async def is_alone(self, ctx):
        server = ctx.message.guild
        user = ctx.message.author
        voice_channels = server.voice_channels
        for vc in voice_channels:
            vc_users = vc.members
            if len(vc.members) == 2:
                if user in vc.members and self.bot.user in vc.members:
                    return True
        return False

    @commands.command(aliases=['kill'])
    async def stop(self, ctx):
        """Stop the currently playing song and clear the queue.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Not playing.**')

        if (await self.is_dj(ctx) or await self.is_alone(ctx)):
            player.queue.clear()
            await player.stop()
            await ctx.send('⏹ **Stopped.**')

    @commands.command(name="song", aliases=['now','np'])
    async def song(self, ctx):
        """Display information about the currently playing song.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        player = self.bot.lavalink.players.get(ctx.guild.id)
        song = 'Not playing anything!'

        if player.current:
            em = await self.get_np_embed(ctx, player)
            await ctx.send(embed=em)
            return
        await ctx.send(':red_circle: **Not playing anything!**')

    async def get_np_embed(self, ctx, player):
        song = player.current
        song_info = player.current_info
        requester = ctx.message.guild.get_member(song.requester)

        em = discord.Embed(description="", colour=requester.colour)
        em.set_author(name = f'{song.title}', url = song.uri)
        embed_msg = ""
        if hasattr(song, 'author'):
            embed_msg += f'Uploader: `{song.author}`\n'
        if hasattr(song_info, 'view_count'):
            embed_msg += f'Views: `{song_info.view_count}`\n'
        if hasattr(song_info, 'like_count'):
            embed_msg += f'Likes: `{song_info.like_count}/{song_info.like_count + song_info.dislike_count}'
            embed_msg += '({:.2f}%)`\n'.format(100*song_info.like_count/(song_info.like_count + song_info.dislike_count))
        if hasattr(player, 'position'):
            if song.stream:
                embed_msg += 'Length: `LIVE`\n'
            else:
                song_dur = lavalink.Utils.format_time(song.duration)
                embed_msg += 'Length: `{}`\n'.format(song_dur)

        if player.position and not song.stream:
            embed_msg += f'{self._draw_play(player.position, song.duration, paused=player.paused)}\n'

        em.description = embed_msg
        repeat_text = ""
        shuffle_text = ""
        if player.repeat:
            repeat_text = " | 🔂 Repeat enabled"
        if player.shuffle:
            shuffle_text = " | 🔀 Shuffle enabled"
        em.set_footer(text = f"Requested by {requester.display_name}{repeat_text}{shuffle_text}",
            icon_url = requester.avatar_url)
        if hasattr(song_info, 'thumbnail'):
            em.set_thumbnail(url = song_info.thumbnail)
        else:
            em.set_thumbnail(url = "https://i.imgur.com/onE7O71.png")
        return em

    @commands.command(aliases=['q'])
    async def queue(self, ctx, page: int=1):
        """Retrieve a list of upcoming songs.

        [Example]
        +<COMMAND>
        """
        user = ctx.message.author
        server = ctx.message.guild
        player = self.bot.lavalink.players.get(ctx.guild.id)

        em = discord.Embed(description="", colour=user.colour)
        queue_msg = ""

        if player.current:
            song = player.current
            song_info = player.current_info
            queue_msg = "**__Currently playing:__**\n"
            queue_msg += f"[{song.title}]({song.uri})\n"
            if player.position and not song.stream:
                queue_msg += f'{self._draw_play(player.position, song.duration, paused=player.paused)}\n'
            #em.set_thumbnail(url = song.get_thumbnail())
            if hasattr(song_info, 'thumbnail'):
                em.set_thumbnail(url = song_info.thumbnail)
            else:
                em.set_thumbnail(url = "https://i.imgur.com/onE7O71.png")

        if not player.queue:
            queue_msg += "**__Next up:__**\n"
            queue_msg += '**There are currently no queued songs.**'
            page = 1
            pages = 1
            total = 0
        else:
            items_per_page = 10
            total = len(player.queue)
            pages = math.ceil(total / items_per_page)

            if page <= pages:
                queue_msg += "**__Next up:__**\n"

                start = (page - 1) * items_per_page
                end = start + items_per_page
                for num, song in enumerate(player.queue[start:end], start=start):
                    # print(song)
                    duration = lavalink.Utils.format_time(int(song.duration))
                    requester = server.get_member(song.requester)
                    queue_msg += "**[{}]** [{}]({}) (`{}`) | `{}` \n".format(
                        num+1, song.title, song.uri, duration, requester.name)
            else:
                page = 'X'

        repeat_text = ""
        shuffle_text = ""
        if player.repeat:
            repeat_text = " | 🔂 Repeat enabled"
        if player.shuffle:
            shuffle_text = " | 🔀 Shuffle enabled"
        em.description = queue_msg
        em.set_footer(text = f"{total} songs in queue. | Page {page}/{pages}{repeat_text}{shuffle_text}")

        await ctx.send(content="**Queued Songs: **", embed = em)

    @commands.command(aliases=['resume'])
    async def pause(self, ctx):
        """Pause or resume the currently playing song.

        [Example]
        +<COMMAND>
        """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Not playing.**')

        if player.paused:
            await player.set_pause(False)
            await ctx.send('⏯ **Resumed**')
        else:
            await player.set_pause(True)
            await ctx.send('⏯ **Paused**')

    @commands.command(aliases=['vol'])
    async def volume(self, ctx, volume: int=None):
        """Change the player volume.

        [Options]
        vol: Volume to change the player to. (int: 1-100)

        [Example]
        +<COMMAND> 75
        """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not volume:
            return await ctx.send(f'🔈 **{player.volume}%**')

        await player.set_volume(volume)
        await ctx.send(f'🔈 **Set to {player.volume}%**')

    @commands.command()
    async def shuffle(self, ctx):
        """Shuffle the current queue.

        [Example]
        +<COMMAND>
        """
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Nothing playing.**')

        player.shuffle = not player.shuffle

        await ctx.send('🔀 Shuffle ' + ('enabled' if player.shuffle else 'disabled'))

    @commands.command()
    async def repeat(self, ctx):
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(':red_circle: **Nothing playing.**')

        player.repeat = not player.repeat

        await ctx.send('🔁 Repeat ' + ('enabled' if player.repeat else 'disabled'))

    @commands.command()
    async def remove(self, ctx, index: int):
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.queue:
            return await ctx.send(':red_circle: **Nothing queued.**')

        if index > len(player.queue) or index < 1:
            return await ctx.send('Index has to be >=1 and <=queue size')

        index -= 1
        removed = player.queue.pop(index)

        await ctx.send('Removed **' + removed.title + '** from the queue.')

    @commands.command(name="search")
    async def find(self, ctx, *, query):
        """Get a list of search results.

        [Example]
        +<COMMAND> Kanpyohgo - Unmei no Dark Side
        """
        if not query.startswith('ytsearch:') and not query.startswith('scsearch:'):
            query = 'ytsearch:' + query

        results = await self.bot.lavalink.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send(':red_circle: **Nothing found**')

        tracks = results['tracks'][:10]  # First 10 results

        o = ''
        for i, t in enumerate(tracks, start=1):
            o += f'**[{i}]** [{t["info"]["title"]}]({t["info"]["uri"]})\n'

        embed = discord.Embed(colour=ctx.guild.me.top_role.colour,
                              description=o)

        await ctx.send(embed=embed)

    @commands.command(aliases=["dc"])
    async def disconnect(self, ctx):
        player = self.bot.lavalink.players.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.send(':red_circle: **Not connected.**')

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.send('You\'re not in my voicechannel!')

        player.queue.clear()
        await player.disconnect()
        await ctx.send('*⃣  **Disconnected.**')

    def _draw_play(self, song_current_time, total_time, paused = False):
        # print(song_current_time, total_time)
        if song_current_time:
            sections = 20
            try:
                loc_time = round((song_current_time/total_time) * sections)  # sections
            except:
                loc_time = 0

            # bar_char = '\N{BOX DRAWINGS HEAVY HORIZONTAL}'
            bar_char = '■'
            seek_char = '\N{RADIO BUTTON}'
            play_char = '\N{BLACK RIGHT-POINTING TRIANGLE}'

            try:
                if not paused:
                    play_char = '\N{BLACK RIGHT-POINTING TRIANGLE}'
                else:
                    play_char = '\N{DOUBLE VERTICAL BAR}'
            except AttributeError:
                play_char = '\N{BLACK RIGHT-POINTING TRIANGLE}'

            msg = "\n" + play_char + " "

            for i in range(sections):
                if i == loc_time:
                    msg += seek_char
                else:
                    msg += bar_char

            elapsed_fmt = lavalink.Utils.format_time(song_current_time)
            total_fmt = lavalink.Utils.format_time(total_time)
            msg += " `{}`/`{}`".format(elapsed_fmt, total_fmt)
            return msg + "\n"
        return ""

    def _get_hms(self, seconds:int):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return (h,m,s)

    def _format_hms(self, h, m, s):
        msg = ""
        if h == 0:
            msg = '{}:{}'.format(str(s).zfill(2),
                str(s).zfill(2))
        else:
            msg = '{}:{}:{}'.format(str(h).zfill(2),
                str(m).zfill(2),str(s).zfill(2))
        return msg

    async def is_dj(self, ctx):
        user = ctx.message.author
        server = ctx.message.guild
        server_settings = await self.audio_settings.find_one(
            {"server_id":str(server.id)})
        if not server_settings:
            return True
        elif ("dj_member" in server_settings.keys() and
            str(user.id) in server_settings["dj_member"]):
            return True
        elif ("dj_role" in server_settings.keys() and
            any([str(role.id) in server_settings["dj_role"] for role in user.roles])):
            return True
        return False

    async def get_server_settings(self, ctx):
        server = ctx.message.guild
        server_settings = await self.audio_settings.find_one(
            {"server_id":str(server.id)})
        return server_settings

    async def get_settings(self, ctx, property_name):
        server = ctx.message.guild
        server_settings = await self.audio_settings.find_one(
            {"server_id":str(server.id)})
        try:
            return server_settings[property_name]
        except:
            return None

    async def has_property(self, dict_obj, prop_name):
        if prop_name in dict_obj.keys():
            return True
        return False

def setup(bot):
    bot.add_cog(Audio(bot))