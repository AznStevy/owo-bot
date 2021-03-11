# Checks if user exists
async def check_user_exists(user):
    find_user = await self.players.find_one({"user_id":str(user.id)})
    if not find_user:
        return False
    return True

def add_edit_user(discord_user_id, data):
	pass

def add_edit_beatmap(discord_user_id, data):
	pass