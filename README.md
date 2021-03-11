![osu profile](https://i.imgur.com/8fufXHA.png)

This is the mostly-complete repo for the owo Discord osu! bot which you can invite [here](https://discord.com/oauth2/authorize?client_id=289066747443675143&scope=bot&permissions=305187840). As you look through this repo, please keep in mind that all of this code is written for *me* and not for anyone else, so the only consideration for code structure is that it's convenient and works for *me*. Here's a quick [FAQ section](#coding-faq) for you programmers or anyone who's considering trying to get this to work on your end. For a full list of commands, visit the website [here](http://owo-bot.xyz/).

# Overview of Features

**Firstly, if you're annoyed by the implicitly triggered "owo"-type  commands, I'm with you - do `>funadmin prefixless` to disable them.**

Secondly, if you haven't already, link your osu! account by doing `>osuset user "your username"`; if you have a space in your name, use quotes. The official server can provide **verification** for your account if you have your discord information on your osu! profile (settings section). If you wish to link your account to a private server, append the suffix `-(server name)` e.g. (`>osuset user "your username" -ripple`); things like `rx` are not needed in the server name when setting user. Do `>botinfo` to view supported private servers.

## Table of Contents
- [Profile Commands](#profile-commands)
- [Top Play Commands](#top-play-commands)
- [Map Recommendations](#map-recommendations)
- [Tracking](#tracking)
- [Map Feed](#map-feed)
- [Implicit Commands](#implicit-commands)
- [Getting More Info w/ `>help`](#getting-more-info-w-help)

## Profile Commands
Firstly, to view some basic profile information, there are four commands: `>osu` `>taiko` `>ctb` `>mania`. If no parameters are provided, they will display the information of the account you linked, otherwise, it will use your input as a username and find that user's info. Examples: `>osu Stevy`, `>taiko syaron105`, `>ctb AutoLs`, `>mania Jakads`.

![osu profile](https://i.imgur.com/pCWcxvI.png)
![taiko profile](https://i.imgur.com/baKLg8a.png)
![ctb profile](https://i.imgur.com/1Cx8wAp.png)
![mania profile](https://i.imgur.com/aewzgof.png)

If you append `-d` to any one of those, you will get a _detailed_ profile. If you append `-s`, you will get some calculated statistics for the user using their top plays. Examples: `>osu -d "Stevy"`, `>osu -s "chocomint"`.

![detailed profile](https://i.imgur.com/Q3COkJj.png)
![stats profile](https://i.imgur.com/WMvdDob.png)

[Return to Table of Contents](#table-of-contents)

## Top Play Commands

Next, there are the `top` commands: `>osutop` `>taikotop` `>ctbtop` `>maniatop`. Input convention follows the "core" commands from above. This will display your top 5 plays for that gamemode. Example: `>osutop "chocomint"`.

![osutop](https://i.imgur.com/Oy7NK4a.png)

The top command supports various types of sorting and filtering functions. By appending tags, you can sort by accuracy (`-acc`), max combo (`-c`), rank achieved (`-rk`), and score (`-sc`). You can filter by using tags like index (`-i #`) and mod (`-m (mods)`). Additionally, there is a no-choke option (`-nc`) that will calculate hypothetical no-choke plays for your entire top 100 - sorting and filters can be applied here as well. There is also a supporter feature (`-im`) that allows you to generate a score image of one of your plays. If you'd like to support, do `>support` or [visit the patreon page](https://www.patreon.com/stevy). Examples: `>osutop chocomint -nc`, `>osutop chocomint -im -i 3`

![no choke](https://i.imgur.com/9MTpepG.png)
![score image](https://i.imgur.com/LHqkMvw.png)

For more information, use the `>help` command on the respective top command (e.g. `>help osutop`) in Discord or visit the [website](http://owo-bot.xyz/) for examples.

[Return to Table of Contents](#table-of-contents)

## Map Recommendations

The bot can give recommendations for any mode based on a user's top 15 plays and mods in the respective mode (e.g. `>recommend` or `>r`). If you think a recommendation is too easy, use the `-f` or farm parameter; the higher the number, the more farmy. If you don't like the mods it gives, you can specify by just writing the  mod afterwards, like `HDDT`. If you want a specific ar, use the `-ar` tag. You can also use ranges, like `4-5`. However, it should be noted that for non-std recommendations, only the `-pp` and `-f` options work. For more information, visit the [website](http://owo-bot.xyz/). Example: `>r -f 10 -ar 10-10.4 HDDT -pp 300-350` (Farm rating = 10 (easy to farm), AR = 10-10.4, mods = HDDT, target pp = 300-350).

![rec image](https://i.imgur.com/MWcU8wF.png)

[Return to Table of Contents](#table-of-contents)

## Tracking

To track a user or users, type the command `>track add (username) (username2) ...`. The default mode and number tracked is `0` (std) and `50`. To specify the # of top plays to be notified about, append `-t #` to the command. To specify the modes to be tracked, append `-m (modes)` to your command; 0=std, 1=taiko, 2=ctb, 3=mania. e.g. `>track add -m 23 -t 75 Stevy` would track the top `75` plays for `Stevy` on that channel for modes `2` and `3`. You can also track certain countries and the number of players by appending `-c` and a [two-character country code](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) or `global`, and specify the number of top players using `-p #`. The number of top plays and the modes are, again, defined by `-t` and `-m`, respectively. Please keep in mind that servers have a default track limit of 200 players, but tracking a country's top 30 players for 3 different gamemodes will only add 30 to your list! If you made a mistake in adding a user, simply use the add command again. 

If you want to completely overwrite with new options, use `-o`. If you want to remove that user or users from tracking, use `>track remove (username) (username2) ...`. If you want to clear all people on the server, do `>track remove -a`. If you want to clear a single channel, do `track remove -ch` in that channel. For more info, use `>help track add` or visit the [website](http://owo-bot.xyz/).

[Return to Table of Contents](#table-of-contents)

## Map Feed

The bot can track newly qualified, ranked, and loved maps for all gamemodes. To enable, pick a channel and do `>mapfeed`. By default, the bot will display all new maps that are either qualified, ranked, or loved and in all gamemodes. To filter what maps gets displayed, you can introduce filters such as excluded mappers (`-xmpr`) or least stars (`-ls`) to only get beatmap sets containing at least one map with a star value greater than what was specified. To view your settings, do `>mapfeed -info`. To remove a channel from the map feed, do `>mapfeed -rm`. For more information, visit the [website](http://owo-bot.xyz/). An example of a newly ranked map is shown below.

![map feed image](https://i.imgur.com/Xp3INzz.png)

[Return to Table of Contents](#table-of-contents)

## Implicit Commands

There are a few passive triggers for owo, mostly to do with osu links and screenshots. There is a 5 second cooldown per server when any of these are triggered. The way to disable all of these server-wide is `>osuadmin implicit`. To toggle, do the command again. Below are ways to selectively enable/disable different links.

### Beatmap Links

If a beatmap linked from the official site is posted, owo will post that map's information, pp information, along with some download links. If it is a single beatmap, a graph (only accurate for std) will be displayed. If it's a beatmap set, the top 3 difficulties will be displayed. If you wanted to see how certain mods will effect the map's pp values, you can simply append +(mods) to the end of the link. This is very similar to the `>map` command. Examples: `https://osu.ppy.sh/beatmapsets/93523#osu/252238`, `https://osu.ppy.sh/beatmapsets/93523#osu/252238 +HDHR`

![beatmap image](https://i.imgur.com/7vsoqXB.png)
![beatmap_mod image](https://i.imgur.com/rlS1guk.png)

[Return to Table of Contents](#table-of-contents)

### User Links

The bot also detects user links and displays them in the same format as the basic profile commands. Example: `https://osu.ppy.sh/users/5053158`.

![user link image](https://i.imgur.com/FhvMpHU.png)

### Screenshots

The bot is able to detect maps from screenshots (to varying degrees of accuracy...). If a top or recent play is detected, then it will provide some information of that play, otherwise, it will only be the map information. The screenshot must be from the official server or directly from the game (no modified filenames). Normally, screenshot files should follow the format `screenshot#.png`.

![screenshot image](https://i.imgur.com/nYYEBOm.png)

### Toggling Implicit/Passive Settings

To toggle settings for link and screenshot detection, use the `>osuadmin` command and sub-commands. Toggling the `implicit` setting will enable/disable all link/screenshot detection (e.g. `>osuadmin implicit`). Sub-commands like `beatmapurl` will disable beatmap url detection. Other options are listed in the `osuadmin` stem command. To get an overview of your settings (not just for osu!), do `>overview`. Example: `>overview`.

![overview image](https://i.imgur.com/oa6xKP1.png)

## Getting More Info w/ `>help`

As mentioned previously, if you want to explore more stuff about the bot, use the `>help` or `>h` command. If you are dealing with a nested command, you can do something like `>h track add`. You can also visit the [website](http://owo-bot.xyz/) which includes many examples. Example: `>h track add`.

![help image](https://i.imgur.com/H7daDP7.png)

[Return to Table of Contents](#table-of-contents)

# Coding FAQ

### Why are cogs mostly in a huge file and not separated?
Writing in a single file is extremely convenient for me to apply hotfixes and reload the module. After fiddling around with `importlib` for several days, I haven't been successful in reloading files that aren't the one the cog is located in. If you have gotten this to work in Python/discord.py, then I'd love to know about it.

### What is with all this spaghetti code?
Like you, my intensions aren't to write code that is unreadable. But when things get as complex as they do with new feature requests coming in every week, you just give into the mess while trying to implement things as fast as possible. So as I said up top, this code is for no one and is not meant to be read. To me, if it works, it works. 

### Why are there so many unspecified try-catches?
At some point, you just get tired of seeing errors in your console from bad user inputs. Doing this is akin to [this meme](https://i.imgur.com/A1X5zhR.png).

### Will you ever upload the databases you use?
No, there is too much back-end going on and helping everyone get the database working will be a hassle.

### I have osu API questions, can you help?
Yeah, of course! I'm open to any questions if people need help with the osu! API or programming questions in general. Although, after reading this code, I'm not so sure you'd want it! But if you still do, feel free to chat in the [Discord server](https://discord.gg/aNKde73).

[Return to Table of Contents](#table-of-contents)
