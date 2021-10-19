import discord
from discord.ext import commands
import datetime
from utils import helper


class Admin(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        message = payload.cached_message
        if message.channel.name != 'bot-logs' and not message.content.startswith('$') and message.author.id != helper.get_config('bot_discord_uid'):
            em = discord.Embed(title='Message Deletion:', colour=0xff0000)
            em.add_field(name='Author', value='{0}'.format(message.author), inline=False)
            em.add_field(name='Channel', value='{0}'.format(message.channel), inline=False)
            em.add_field(name='Message', value=message.content, inline=False)
            em.set_footer(text='Deleted At: %s' % datetime.datetime.now())
            guild = self.client.get_guild(helper.get_config('guild_id'))
            log_channel = discord.utils.get(guild.text_channels, name='bot-logs')
            await log_channel.send(embed=em)

    @commands.command()
    @commands.has_any_role('Commander', 'Captain', 'Lieutenant')
    async def promote(self, ctx, member: discord.Member, *, role: str):
        await ctx.send("Superseded by slash command `/member promote <member> <rank>`")

    @commands.command()
    async def claim(self, ctx, new_fo: int):
        await ctx.send("Superseded by slash command `/roster claim <n>`")

    @commands.command()
    async def serverinvite(self, ctx):
        """PM a server invite code to invoker"""
        invite = await ctx.channel.create_invite(max_uses=0, unique=True)
        await ctx.author.send("Your invite URL is {}".format(invite.url))
        await ctx.send("Check Your Dm's :wink: ")

    @commands.command()
    async def set_team_description(self, ctx, *args, **kwargs):
        await ctx.send("Superseded by slash command `/team set_description`")

    @commands.command()
    async def set_team_emblem(self, ctx, *args, **kwargs):
        await ctx.send("Superseded by slash command `/team set_emblem`")

    @commands.command(aliases=['team'])
    async def teams(self, ctx, *args, **kwargs):
        await ctx.send("Superseded by slash command `/teams`")


def setup(client):
    client.add_cog(Admin(client))
