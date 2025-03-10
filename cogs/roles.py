"""
MIT License

Copyright (c) 2019-present eibex

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from sqlite3 import Error as DatabaseError
import disnake
from disnake.ext import commands

from cogs.utils.i18n import response
from cogs.utils.locks import lock_manager


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent):
        reaction = str(payload.emoji)
        sanitized_reaction = str(payload.emoji.id) if payload.emoji.is_custom_emoji() else payload.emoji.name
        msg_id = payload.message_id
        ch_id = payload.channel_id
        user_id = payload.user_id
        guild_id = payload.guild_id
        try:
            exists = self.bot.db.exists(msg_id)
        except DatabaseError as error:
            await self.bot.report(response.get("db-error-reaction-add").format(exception=error), guild_id)
            return
        async with (await lock_manager.get_lock(user_id)):
            if not exists:
                # Checks that the message that was reacted to is a reaction-role message managed by the bot
                return
            try:
                reactions = self.bot.db.get_reactions(msg_id)
            except DatabaseError as error:
                await self.bot.report(guild_id, response.get("db-error-reaction-get").format(exception=error))
                return

            ch = await self.bot.getchannel(ch_id)
            msg = await ch.fetch_message(msg_id)
            user = await self.bot.getuser(user_id)
            if sanitized_reaction not in reactions:
                # Removes reactions added to the reaction-role message that are not connected to any role
                await msg.remove_reaction(reaction, user)
            else:
                # Gives role if it has permissions, else 403 error is raised
                role_id = reactions[sanitized_reaction]
                guild = await self.bot.getguild(guild_id)
                member = await self.bot.getmember(guild, user_id)
                role = disnake.utils.get(guild.roles, id=role_id)
                if user_id != self.bot.user.id:
                    try:
                        unique = self.bot.db.isunique(msg_id)
                    except DatabaseError as error:
                        await self.bot.report(guild_id, response.get("db-error-reaction-unique").format(exception=error))
                        return
                    if unique:
                        for existing_reaction in msg.reactions:
                            if str(existing_reaction.emoji) == reaction:
                                continue
                            async for reaction_user in existing_reaction.users():
                                if reaction_user.id == user_id:
                                    await msg.remove_reaction(existing_reaction, user)
                                    # We can safely break since a user can only have one reaction at once
                                    break

                    try:
                        await member.add_roles(role)
                        try:
                            notify = self.bot.db.notify(guild_id)
                        except DatabaseError as error:
                            await self.bot.report(response.get("db-error-notification-check").format(exception=error), guild_id)
                            return

                        if notify:
                            await user.send(response.get("new-role-dm").format(role_name=role.name))
                    except disnake.Forbidden:
                        await self.bot.report(guild_id, response.get("permission-error-add"))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent):
        sanitized_reaction = str(payload.emoji.id) if payload.emoji.is_custom_emoji() else payload.emoji.name
        msg_id = payload.message_id
        user_id = payload.user_id
        guild_id = payload.guild_id
        try:
            exists = self.bot.db.exists(msg_id)
        except DatabaseError as error:
            await self.bot.report(response.get("db-error-reaction-remove").format(exception=error), guild_id)
        if not exists:
            # Checks that the message that was unreacted to is a reaction-role message managed by the bot
            return
        try:
            reactions = self.bot.db.get_reactions(msg_id)
        except DatabaseError as error:
            await self.bot.report(guild_id, response.get("db-error-reaction-get").format(exception=error))
            return
        if sanitized_reaction in reactions:
            role_id = reactions[sanitized_reaction]
            # Removes role if it has permissions, else 403 error is raised
            guild = await self.bot.getguild(guild_id)
            member = await self.bot.getmember(guild, user_id)

            role = disnake.utils.get(guild.roles, id=role_id)
            try:
                await member.remove_roles(role)
                try:
                    notify = self.bot.db.notify(guild_id)
                except DatabaseError as error:
                    await self.bot.report(response.get("db-error-notification-check").format(exception=error), guild_id)
                    return

                if notify:
                    await member.send(response.get("removed-role-dm").format(role_name=role.name))
            except disnake.Forbidden:
                await self.bot.report(response.get("permission-error-remove"), guild_id)


def setup(bot):
    bot.add_cog(Roles(bot))
