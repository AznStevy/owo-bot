    @lvladmin.group(name = "bg", pass_context=True)
    async def lvladminbg(self, ctx):
        """Admin Background Configuration"""
        if ctx.invoked_subcommand is None or \
                isinstance(ctx.invoked_subcommand, commands.Group):
            await send_cmd_help(ctx)
            return

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def addprofilebg(self, name:str, url:str):
        """Add a profile background. Proportions: (290px x 290px)"""
        if name in self.backgrounds["profile"].keys():
            await self.bot.say("**That profile background name already exists!**")
        elif not await self._valid_image_url(url):
            await self.bot.say("**That is not a valid image url!**")
        else:
            self.backgrounds["profile"][name] = url
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**New profile background(`{}`) added.**".format(name))

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def addrankbg(self, name:str, url:str):
        """Add a rank background. Proportions: (360px x 100px)"""
        if name in self.backgrounds["rank"].keys():
            await self.bot.say("**That rank background name already exists!**")
        elif not await self._valid_image_url(url):
            await self.bot.say("**That is not a valid image url!**")
        else:
            self.backgrounds["rank"][name] = url
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**New rank background(`{}`) added.**".format(name))

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def addlevelbg(self, name:str, url:str):
        '''Add a level-up background. Proportions: (85px x 105px)'''
        if name in self.backgrounds["levelup"].keys():
            await self.bot.say("**That level-up background name already exists!**")
        elif not await self._valid_image_url(url):
            await self.bot.say("**That is not a valid image url!**")
        else:
            self.backgrounds["levelup"][name] = url
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**New level-up background(`{}`) added.**".format(name))

    @checks.is_owner()
    @lvladminbg.command(no_pm=True, pass_context=True)
    async def setcustombg(self, ctx, bg_type:str, user_id:str, img_url:str):
        """Set one-time custom background"""
        valid_types = ['profile', 'rank', 'levelup']
        type_input = bg_type.lower()

        if type_input not in valid_types:
            await self.bot.say('**Please choose a valid type: `profile`, `rank`, `levelup`.')
            return

        # test if valid user_id
        userinfo = await self.all_users.find_one({'user_id':user_id})
        if not userinfo:
            await self.bot.say("**That is not a valid user id!**")
            return

        if not await self._valid_image_url(img_url):
            await self.bot.say("**That is not a valid image url!**")
            return

        await self.all_users.update_one({'user_id':user_id}, {'$set':{"{}_background".format(type_input): img_url}})
        await self.bot.say("**User {} custom {} background set.**".format(user_id, bg_type))

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def delprofilebg(self, name:str):
        '''Delete a profile background.'''
        if name in self.backgrounds["profile"].keys():
            del self.backgrounds["profile"][name]
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**The profile background(`{}`) has been deleted.**".format(name))
        else:
            await self.bot.say("**That profile background name doesn't exist.**")

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def delrankbg(self, name:str):
        '''Delete a rank background.'''
        if name in self.backgrounds["rank"].keys():
            del self.backgrounds["rank"][name]
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**The rank background(`{}`) has been deleted.**".format(name))
        else:
            await self.bot.say("**That rank background name doesn't exist.**")

    @checks.is_owner()
    @lvladminbg.command(no_pm=True)
    async def dellevelbg(self, name:str):
        '''Delete a level background.'''
        if name in self.backgrounds["levelup"].keys():
            del self.backgrounds["levelup"][name]
            fileIO('data/leveler/backgrounds.json', "save", self.backgrounds)
            await self.bot.say("**The level-up background(`{}`) has been deleted.**".format(name))
        else:
            await self.bot.say("**That level-up background name doesn't exist.**")