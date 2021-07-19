import discord
import asyncpg
import asyncio
from discord.ext import commands, tasks, menus
from collections import defaultdict
from utils import gonk_menus
import datetime
import random
import time
import pandas as pd
from utils import helper
import numpy as np


# noinspection PyMethodMayBeStatic
class Dev(commands.Cog):

    def __init__(self, client):
        self.client = client
        self._last_member = None

    def cog_unload(self):
        pass

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Cog is online.')

    # Commands
    @commands.command()
    async def hello(self, ctx, *, member: discord.Member = None):
        """Says hello"""
        # 0 refers to ctx as it is the first parameter
        # Example of storing variable in cog
        member = member or ctx.author
        if self._last_member is None or self._last_member.id != member.id:
            await ctx.send('Hello {0.name}~'.format(member))
        else:
            await ctx.send('Hello {0.name}... This feels familiar.'.format(member))
        self._last_member = member

    @commands.command()
    async def test(self, ctx):
        pass

def setup(client):
    client.add_cog(Dev(client))
