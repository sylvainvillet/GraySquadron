import discord
import platform
import os
import sys
import asyncpg
import asyncio
from discord.ext import commands, tasks

from utils import helper

# pm2 start gonk_droid.py --interpreter=/root/gray-squadron-bot/venv/bin/python3
# source /root/gray-squadron-bot/venv/bin/activate

description = '''I am the Gray Squadron Gonk Droid!'''

TOKEN = helper.get_config('bot_token')
POSTGRES_INFO = helper.get_config('postgres_info')

intents = discord.Intents.all()
client = commands.Bot(command_prefix='$', description=description, intents=intents)

# TODO: Set up more detailed logging
# TODO: Revisit serverinfo command

# TODO: Bot suggestions channel with slowmode and emoji react votes
# TODO: list counts of each role to replace other bot

# TODO: Baseball stat cards for each user
# TODO: Computer vision to read end-game scoreboard and parse stats into DB

# TODO: Command to tell bot your EA/other ID
# TODO: Command to get list of IDs for users in your VC


@client.event
async def on_ready():
    """Startup Messages"""
    await helper.bot_log(client, '------'
                f'\nLogged in as {client.user.name}'
                f'\nDiscord.py API version: {discord.__version__}'
                f'\nPython version: {platform.python_version()}'
                f'\nInterpretor: {sys.executable}'
                f'\nRunning on: {platform.system()} {platform.release()} ({os.name})'
                '\n------')
    activity = discord.Activity(name='Jizz Droid', type=discord.ActivityType.listening)
    await client.change_presence(status=discord.Status.online, activity=activity)
    await load_all()
    # spam_test.start()


@client.command()
async def ping(ctx):
    """Ping bot for reactivity"""
    await ctx.send(f'Pong! {round(client.latency * 1000)}ms')


# region check is vapor using custom check
def check_is_vapor(ctx):
    return ctx.author.id == 195747311136145409


@client.command()
@commands.check(check_is_vapor)
async def is_vapor(ctx):
    """Are you vapor?"""
    await ctx.send(f'It is {ctx.author}')


@is_vapor.error
async def is_vapor_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send('IMPOSTER!')
# endregion


# region Cog Load/Unload/Reload
async def load_all():
    cog_list = [f for f in os.listdir('./cogs') if f.endswith('.py')]
    for cog in cog_list:
        try:
            client.load_extension(f'cogs.{cog[:-3]}')
        except Exception:
            pass


@client.command()
@commands.has_any_role('Commander', 'Droid Engineer')
async def load(ctx, extension: str):
    """Load cogs"""
    cog_list = [f for f in os.listdir('./cogs') if f.endswith('.py')]
    if extension.lower() == 'all':
        for cog in cog_list:
            try:
                client.load_extension(f'cogs.{cog[:-3]}')
            except commands.ExtensionAlreadyLoaded:
                await ctx.send(f'{cog[:-3]} cog is already loaded.')
            except commands.ExtensionNotFound:
                await ctx.send(f"{extension} cog was not found.")
            else:
                await ctx.send(f'{cog[:-3]} loaded!')
    else:
        if extension+'.py' in cog_list:
            try:
                client.load_extension(f'cogs.{extension}')
            except commands.ExtensionAlreadyLoaded:
                await ctx.send(f'{extension} cog is already loaded.')
            except commands.ExtensionNotFound:
                await ctx.send(f"{extension} cog was not found.")
            else:
                await ctx.send(f'{extension} loaded!')


@load.error
async def load_error(ctx, error):
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send('You are not a Droid Engineer!')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Missing target cog parameter')
    else:
        await helper.bot_log(client, error)


@client.command()
@commands.has_any_role('Commander', 'Droid Engineer')
async def unload(ctx, extension: str):
    """Unload cogs"""
    cog_list = [f for f in os.listdir('./cogs') if f.endswith('.py')]
    if extension.lower() == 'all':
        for cog in cog_list:
            try:
                client.unload_extension(f'cogs.{cog[:-3]}')
            except commands.ExtensionNotLoaded:
                await ctx.send(f"{extension} cog was not loaded to begin with.")
            else:
                await ctx.send(f'{cog[:-3]} unloaded!')
    else:
        try:
            client.unload_extension(f'cogs.{extension}')
        except commands.ExtensionNotLoaded:
            await ctx.send(f"{extension} cog was not loaded to begin with.")
        else:
            await ctx.send(f"{extension} unloaded!")


@unload.error
async def unload_error(ctx, error):
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send('You are not a Droid Engineer!')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Missing target cog parameter')
    else:
        await helper.bot_log(client, error)


@client.command()
@commands.has_any_role('Commander', 'Droid Engineer')
async def reload(ctx, extension: str):
    """Reload cogs"""
    cog_list = [f for f in os.listdir('./cogs') if f.endswith('.py')]
    if extension.lower() == 'all':
        for cog in cog_list:
            try:
                client.unload_extension(f'cogs.{cog[:-3]}')
                client.load_extension(f'cogs.{cog[:-3]}')
            except commands.ExtensionNotLoaded:
                await ctx.send(f"{cog[:-3]} cog was not loaded to begin with.")
            else:
                await ctx.send(f'{cog[:-3]} reloaded!')
    else:
        try:
            client.unload_extension(f'cogs.{extension}')
            client.load_extension(f'cogs.{extension}')
        except commands.ExtensionNotLoaded:
            await ctx.send(f"{extension} cog was not loaded to begin with.")
        else:
            await ctx.send(f"{extension} reloaded!")


@reload.error
async def reload_error(ctx, error):
    if isinstance(error, commands.MissingAnyRole):
        await ctx.send('You are not a Droid Engineer!')
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Missing target cog parameter')
    else:
        await helper.bot_log(client, error)
# endregion


# @tasks.loop(seconds=10)
# async def spam_test():
#     await client.wait_until_ready()
#     guild = client.get_guild(helper.get_config('guild_id'))
#     channel = discord.utils.get(guild.text_channels, name='bot-testing')
#     await channel.send('This is bot spam!')

loop = asyncio.get_event_loop()
# This blockingly executes the 'create_pool' coroutine, and adds the resultant pool to the bot class before it starts
client.pool = loop.run_until_complete(asyncpg.create_pool(**POSTGRES_INFO))
client.run(TOKEN)
