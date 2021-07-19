import discord
from discord.ext import menus


class CustomDic:
    def __init__(self, key, value):
        self.key = key
        self.value = value

# Example of data format
# data = [
#     Test(key=key, value=value)
#     for key in ['test', 'other', 'okay']
#     for value in range(20)
# ]


# class TeamList(menus.GroupByPageSource):
#     async def format_page(self, menu, entry):
#         joined = '\n'.join(f'{v.value}' for i, v in enumerate(entry.items, start=1))
#         return f'**{entry.key}**\n{joined}\nPage {menu.current_page + 1}/{self.get_max_pages()}'


class TeamMenu(menus.GroupByPageSource):
    def __init__(self, ctx, data, key):
        self.ctx = ctx
        super().__init__(data, key=key, per_page=50)

    async def write_page(self, menu, metadata, fields=None):
        if fields is None:
            fields = []
        embed = discord.Embed(title=metadata[0], description=metadata[2], colour=metadata[1])
        embed.set_thumbnail(url=metadata[3])
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        return embed

    async def format_page(self, menu, entries):
        fields = []
        table = "\n".join(f"{idx}. {entry.value[0]}" for idx, entry in enumerate(entries.items, start=1))
        metadata = list(set([(entry.value[1], entry.value[2], entry.value[3], entry.value[4]) for entry in entries.items]))
        if metadata[0] == (0, 0, 0, 0):
            metadata.pop(0)
        fields.append(("Members", table))
        return await self.write_page(menu, metadata[0], fields)


# class EconomyLB(menus.ListPageSource):
#     def __init__(self, ctx, data):
#         self.ctx = ctx
#         super().__init__(data, per_page=10)
#
#     async def write_page(self, menu, offset, fields=None):
#         if fields is None:
#             fields = []
#         len_data = len(self.entries)
#         embed = discord.Embed(title="Leaderboard", description="Galactic Credits", colour=self.ctx.author.colour)
#         embed.set_thumbnail(url='https://media.discordapp.net/attachments/800431166997790790/840009740855934996/gray_squadron_logo.png')
#         embed.set_footer(text=f"{offset:,} - {min(len_data, offset+self.per_page-1):,} of {len_data:,} jedi.")
#         for name, value in fields:
#             embed.add_field(name=name, value=value, inline=False)
#         return embed
#
#     async def format_page(self, menu, entries):
#         offset = (menu.current_page * self.per_page) + 1
#         fields = []
#         table = "\n".join(f"{idx+offset}. {self.ctx.guild.get_member(entry[0]).display_name} - {entry[1]:,} Credits" for idx, entry in enumerate(entries))
#         fields.append(("Rank", table))
#         return await self.write_page(menu, offset, fields)

# Call somewhere else
# pages = menus.MenuPages(source=Source(data, key=lambda t: t.key, per_page=12), clear_reactions_after=True)
# await pages.start(ctx)
