import socket
import asyncio
import re
import json
import time as time_obj
import threading
import motor.motor_asyncio
from time import strftime, time, sleep
from pymongo import MongoClient
from multiprocessing import Process

class BanchoBot():
    def __init__(self, config):
        self.bancho_usr = config["API_KEYS"]["BANCHO"]['USERNAME']
        self.bancho_pass = config["API_KEYS"]["BANCHO"]['PASSWORD']
        self.msg_chan = '#osu'

        # Define conditions where the loop should restart automatically
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            port=config["database"]["primary"],
            connectTimeoutMS=5000, 
            socketTimeoutMS=5000, 
            serverSelectionTimeoutMS=5000)
        self.db = self.client['owo_database']

        # sets are faster than lists
        self.online_set = set()
        self.track_set = set()

        # timer
        self.STALE_LIMIT = 5
        self.POLL_INTERVAL = 5 # seconds
        self.prev_online_num = 0 
        self.prev_track_num = 0
        self.stale_counter = 0
        self.time = time()

    async def initialize_list(self):
        await self.create_db()

        # empty list
        await self.db.online.update_one({'type': 'userlist'},
            {'$set':{"userlist": list(self.track_set)}})
        await self.db.online.update_one({'type': 'onlinelist'},
            {'$set':{"onlinelist": list(self.online_set)}})

    async def create_db(self):
        test = await self.db.online.find_one({'type': 'userlist'})
        if not test:
            await self.db.online.insert_one({'type': 'userlist', 'userlist': []})

        test = await self.db.online.find_one({'type': 'onlinelist'}) # in case people aren't tracked
        if not test:
            await self.db.online.insert_one({'type': 'onlinelist', 'onlinelist': []})

    async def add_online(self, username):

        # tests different variations of usernames
        test_usernames = [username]
        if "_" in username and username.find("_") != 0:
            test_usernames.append(username.replace("_", " "))
        if " " in username:
            test_usernames.append(username.replace(" ", "_"))

        for username in test_usernames:
            if username not in self.online_set:
                self.online_set.add(username)
                print("Online {} | Online List {}".format(username, len(self.online_set)))

            if username not in self.track_set:
                self.track_set.add(username)
                print("Added {} | Tracking {}".format(username, len(self.track_set)))

    async def remove_online(self, username):

        test_usernames = [username]
        if "_" in username and username.find("_") != 0:
            test_usernames.append(username.replace("_", " "))
        if " " in username:
            test_usernames.append(username.replace(" ", "_"))

        self.online_set.difference_update(test_usernames)
        print("Offline {} | Online List {}".format(username, len(self.online_set)))
        self.track_set.difference_update(test_usernames)
        print("Removed {} | Tracking {}".format(username, len(self.track_set)))

        """
            self.online_set.discard(username)
            print("Offline {} | Online List {}".format(username, len(self.online_set)))
            self.track_set.discard(username)
            print("Removed {} | Tracking {}".format(username, len(self.track_set)))
            """

    async def bancho(self):
        await self.initialize_list()
        self.stale_counter = 0
        self.prev_online_num = 0
        self.prev_track_num = 0

        network = 'irc.ppy.sh'
        port = 6667

        global irc
        irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        irc.connect((network, port))
        irc.send(bytearray('PASS {}\r\n'.format(self.bancho_pass), encoding='utf-8'))
        irc.send(bytearray('NICK {}\r\n'.format(self.bancho_usr), encoding='utf-8'))
        irc.send(bytearray('USER {} {} {}\r\n'.format(self.bancho_usr, self.bancho_usr, self.bancho_usr), encoding='utf-8'))
        print('CONNECTED to BANCHO')

        # Joins the default channel initially--->
        irc.send(b'JOIN #osu\r\n')

        # Populate the channel list-------------------->
        irc.send(bytearray('LIST\r\n', encoding='utf-8'))

        while True:
            time_elapsed = time() - self.time
            # print(time_elapsed)
            if time_elapsed > self.POLL_INTERVAL:
                # check number of people
                num_online = len(self.online_set)
                num_track = len(self.track_set)

                # otherwise do these
                await self.database_poll()
                self.time = time()

                # check if connection is broken
                # print(num_online, self.prev_online_num, num_track, self.prev_track_num)
                if num_online == self.prev_online_num and num_track == self.prev_track_num:
                    self.stale_counter += 1
                    print("STALE COUNTER: ", self.stale_counter)
                else:
                    self.stale_counter = 0

                if self.stale_counter >= self.STALE_LIMIT:
                    print("RESTARTING CONNECTION")
                    break
                self.prev_online_num = num_online
                self.prev_track_num = num_track
            
            await self.parse_messages()
            # await asyncio.sleep(0.1)

        #restart if broken
        try:
            irc.close()
        except:
            pass

        await asyncio.sleep(1) # arbitrary
        await self.bancho()

    async def database_poll(self):
        print("Updating Database")

        # send commands
        commands = await self.db.irc_commands.find_one({"type":"commands"})
        if commands:
            try:
                commands = commands["commands"]
                for command in commands:
                    try:
                        irc.send(command.encode('utf-8'))
                        print("SENT {}".format(command))
                    except:
                        pass
                await self.db.irc_commands.update_one({"type":"commands"},{'$set':{"commands": []}})
            except:
                pass

        # update list
        await self.db.online.update_one({'type': 'userlist'},
            {'$set':{"userlist": list(self.track_set)}})
        await self.db.online.update_one({'type': 'onlinelist'},
            {'$set':{"onlinelist": list(self.online_set)}})
        await asyncio.sleep(1)

    async def parse_messages(self):
        # process incoming
        try:
            data = irc.recv(4096)
            dats = data.decode('utf-8')
            # print(dats)
            a = dats.split('\n')
        except:
            return

        # print(a)

        for b in a:
            # print(b)
            for e in a:
                if 'No such nick' in e or 'End of /WHOIS' in e:
                    try:
                        c = e.split(':', maxsplit=2)
                        # print(c)
                        info = c[1].split()
                        username = info[3]
                        if 'No such nick' in e:
                            # print('{} left game'.format(username))
                            await self.remove_online(username)
                            # pass
                        if 'End of /WHOIS' in e:
                            if username not in self.online_set:
                                self.online_set.add(username)
                                print("Online {} | Online List {}".format(username, len(self.online_set)))
                    except:
                        pass

            if 'PING' in b:
                print("PONG")
                irc.send(b'PONG \r\n')

            if 'JOIN' in b:
                # for tracking
                try:
                    c = b.split(':', maxsplit=2)
                    info = c[1].split()
                    msg_author = info[0].split('!')[0]
                    msg_author = msg_author.replace('+','')
                    await self.add_online(msg_author)
                except:
                    pass
                    # print('Error c', c)

            if 'QUIT' in b:
                try:
                    c = b.split(':', maxsplit=2)
                    info = c[1].split()
                    msg_author = info[0].split('!')[0]
                    if msg_author in self.online_set:
                        irc.send('WHOIS {}\r\n'.format(msg_author).encode('utf-8'))
                        print('Testing channel/server leave for {}'.format(msg_author))
                except:
                    pass


            if 'cho.ppy.sh 322 Stevy #' in dats:
                a = dats.split('\n')
                join_servers = []
                for e in a:
                    if 'cho.ppy.sh 322 Stevy #' in e:
                        c = e.split(':', maxsplit=2)
                        d = c[1].split(' ')
                        join_servers.append(d[3])

                for server in join_servers:
                    irc.send('JOIN {}\r\n'.format(server).encode('utf-8'))

            if 'cho.ppy.sh 353' in dats and 'NAMES' in dats:
                """
                    This grabs all current uses in the channel.
                """
                a = dats.split('\n')
                for e in a:
                    if 'cho.ppy.sh 353' in e:
                        try:
                            # print(b)
                            c = e.split(':')
                            name_list = c[2].split()
                            for name in name_list:
                                await self.add_online(name.replace('+',''))
                        except:
                            pass

if __name__ == '__main__':
    with open('config.json', 'rb') as f:
        config = json.load(f)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(BanchoBot(config).bancho())


