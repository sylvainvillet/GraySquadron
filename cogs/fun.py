import discord
from discord.ext import commands, tasks, menus
import random
import asyncio
import datetime

from utils import helper, gonk_menus


# TODO: Add firaxa command
# Firaxa link: https://media.discordapp.net/attachments/772905031501742100/778321282558722058/unknown.png


class Fun(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.scum_last_uwu = datetime.datetime.utcfromtimestamp(0)
        self.burfday.start()

    def cog_unload(self):
        # self.annoy.cancel()
        self.burfday.cancel()
        pass

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Cog is online.')

    @commands.Cog.listener()
    async def on_typing(self, channel, user, when):
        """Bot announces when Scum is typing"""
        response_list = ['UwU what are you typing there Scum?',
                         'Our great Commander Scum is preparing oration!',
                         'Senpai Scum Speaking!']
        time_difference = (when - self.scum_last_uwu).total_seconds()
        embed = discord.Embed(colour=discord.Colour(0xda0580))
        embed.add_field(name="<:questionwut:778245227319787530>", value=random.choice(response_list))
        if user.id == 377177416751251487:
            if time_difference < 120:
                return
            else:
                await channel.send(embed=embed, delete_after=4)
                self.scum_last_uwu = datetime.datetime.utcnow()

    # Commands
    @commands.command()
    @commands.has_any_role('Commander', 'Captain', 'Lieutenant', 'Flight Officer', 'Cadet')
    async def fc(self, ctx, member: discord.Member, *, reason='no reason'):
        """Force choke"""
        if ctx.author == member:
            await ctx.send(f'{member.mention} has force choked themselves for {reason}!')
        elif ctx.author.top_role > member.top_role:
            await ctx.send(f'{ctx.author.mention} mercilessly force chokes {member.mention} for {reason}!')
        elif ctx.author.top_role == member.top_role:
            if bool(random.getrandbits(1)):
                await ctx.send(f'{ctx.author.mention} force chokes {member.mention} for {reason}!')
            else:
                await ctx.send(f'{member.mention} was ready and force chokes {ctx.author.mention} first!')
        else:
            await ctx.send(f'{ctx.author.mention} is unable to force choke {member.mention}, they are too powerful!')
        await ctx.message.delete()

    @fc.error
    async def fc_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('Sorry you lack the force!')

    @commands.command(aliases=['8ball'])
    async def yoda(self, ctx):
        """Ask Yoda a question"""
        responses = ['Yes it is so',
                     'No the answer is',
                     'You will know',
                     'Unclear it is',
                     'Try not, do',
                     'Use the force']
        await ctx.send(f'Yoda says: {random.choice(responses)}')

    @commands.command(aliases=['gfl', 'ace5'])
    async def aces5(self, ctx, pick: int = -1):
        """Bot will randomly post a quality GFL message"""
        choices = ['https://media.discordapp.net/attachments/762354298867810335/776240542819811358/unknown.png',
                   'https://media.discordapp.net/attachments/762354298867810335/776241480750465055/unknown.png',
                   'https://media.discordapp.net/attachments/776827374825373697/776928914424725574/unknown.png',
                   'https://clips.twitch.tv/EnticingEnergeticSandpiperJonCarnage']
        if pick == -1:
            await ctx.send(random.choice(choices))
        else:
            await ctx.send(choices[pick])

    @aces5.error
    async def aces5_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, IndexError):
            await ctx.send('That index for choice selection is out of bounds.')

    @commands.command()
    async def tubbo(self, ctx):
        """Bot will remind us of tubbos conviction"""
        await ctx.send(
            'https://media.discordapp.net/attachments/764910645669265408/800428538062176346/Screenshot_20210117-101655.jpg')

    @commands.command(aliases=['f1', 'onlyforf1'])
    async def only4f1(self, ctx):
        """Abuse of power"""
        await ctx.send(
            'https://media.discordapp.net/attachments/800431166997790790/800431219895566436/OnlyForF1.jpg')

    @commands.command()
    async def tibby(self, ctx):
        """Blatant Racism"""
        await ctx.send(
            '404 - This object has been censored by the CCP.')

    @commands.command()
    async def cheese(self, ctx):
        """Stop trying to advertise your junk in gray discord"""
        await ctx.send(
            'https://media.discordapp.net/attachments/800431166997790790/847495939697934366/image0-1.png?width=1016&height=702')

    @commands.command()
    async def a1(self, ctx, content_type: str = 't'):
        """Avenger1 got jokes"""
        choices = ['https://media.discordapp.net/attachments/760342037962031116/800556460618285066/A1.png',
                   'https://media.discordapp.net/attachments/762354298867810335/800578363785216010/5Ofm3HK.png',
                   'https://cdn.discordapp.com/attachments/800431166997790790/801470872803606538/hi803rn.png',
                   'https://media.discordapp.net/attachments/800431166997790790/809513413922521088/unknown.png',
                   'https://media.discordapp.net/attachments/800431166997790790/820012592108929044/Screenshot_20210309-100825_Discord.png',
                   'https://cdn.discordapp.com/attachments/800431166997790790/825070459930017882/unknown.png',
                   'https://cdn.discordapp.com/attachments/800431166997790790/825070489415974972/unknown.png',
                   'https://cdn.discordapp.com/attachments/800431166997790790/837344853150531664/Screenshot_20210428-103121_Discord.png']
        if content_type == 'v':
            choices = ['https://youtu.be/0GJCerz1OdA',
                       'https://streamable.com/3k5qxf',
                       'https://streamable.com/17qliz']
        action_emoji_list = ['⬅', '➡', '🛑']
        pick = 0

        def generate_msg(idx: int):
            if content_type == 'v':
                new_msg = f'{choices[idx]}\nPage {idx + 1} of {len(choices)}'
            else:
                new_msg = discord.Embed(title='A1 Hall-o-Fame', colour=0xFFFF)
                new_msg.set_thumbnail(
                    url='https://media.discordapp.net/attachments/800431166997790790/839258516099563530/A1.jpg')
                new_msg.set_image(url=choices[idx])
                new_msg.set_footer(text=f'Page {idx + 1} of {len(choices)}')
            return new_msg

        async def a1_reaction_waiter(msg, emojis: list) -> str:
            for emoji in emojis:
                await msg.add_reaction(emoji)

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in emojis and r.message.id == msg.id

            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                print('Timeout')
                return 'Timeout'
            return str(reaction.emoji)

        msg = generate_msg(pick)
        if content_type == 'v':
            sent_msg = await ctx.send(msg)
        else:
            sent_msg = await ctx.send(embed=msg)

        while True:
            user_input = await a1_reaction_waiter(sent_msg, action_emoji_list)
            if user_input == action_emoji_list[0] and pick > 0:
                await sent_msg.remove_reaction(user_input, ctx.author)
                pick -= 1
            elif user_input == action_emoji_list[1] and pick != len(choices) - 1:
                await sent_msg.remove_reaction(user_input, ctx.author)
                pick += 1
            elif user_input == action_emoji_list[2]:
                await sent_msg.remove_reaction(user_input, ctx.author)
                break
            else:
                break
            if content_type == 'v':
                await sent_msg.edit(content=generate_msg(pick))
            else:
                await sent_msg.edit(embed=generate_msg(pick))
        await sent_msg.clear_reactions()
        await asyncio.sleep(30)
        await sent_msg.delete()

    @a1.error
    async def a1_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, IndexError):
            await ctx.send('That index for choice selection is out of bounds.')
        else:
            print(error)

    @commands.command()
    async def wolfofacts(self, ctx, pick: int = -1):
        """Facts about Wolfos"""
        choices = ['A wolf can run up to 37mph (60kph)',
                   'The Grey Wolf is known as the Timber Wolf in North America and the White Wolf in the Arctic, or more generally as the Common Wolf.',
                   'Wolves have 42 teeth with which to tear apart capital ships and creeping AI fighters.',
                   'You might find it interesting that there is a Wolf Sanctuary in my area a little north of town.',
                   'I’ve seen them in the wild in Yellowstone.',
                   'Wolf gestation period is 63 days.',
                   'A single wolf can consume 20lbs (9kg) of meat in a single feeding.',
                   'Wolves weight vary from 40lbs (think Basset Hound) to 175lbs (think Irish Wolfhound!)',
                   'All wolves in a pack help to raise the pups.',
                   'A female wolf is commonly known as a ‘she-wolf.’',
                   'Wolf litters are typically 4-6 pups!',
                   'Wolves develop close relationships and strong social bonds. They often demonstrate deep affection for their family and may even sacrifice themselves to protect the family unit.'
                   ]
        if pick == -1:
            await ctx.send(random.choice(choices))
        else:
            await ctx.send(choices[pick])

    @wolfofacts.error
    async def wolfofacts_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, IndexError):
            await ctx.send('That index for choice selection is out of bounds.')

    @commands.command()
    async def lfg(self, ctx, pick: int = -1):
        """LFG Maymays"""
        choices = ['https://cdn.discordapp.com/attachments/800431166997790790/847497925541101588/DTF1.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497928134492160/DTF2.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497930579247114/DTF3.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497932614008852/DTF4.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497934073233458/DTF5.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497935792242738/DTF6.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497937842995251/DTF7.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497939348881408/DTF8.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497941321252874/DTF9.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847497943288250439/DTF10.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498738058526760/DTF11.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498740318208020/DTF12.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498741585412166/DTF13.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498743275716608/DTF14.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498744269504522/DTF15.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498745737510982/DTF16.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498749311975503/DTF17.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498755484942396/DTF18.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498757171970108/DTF19.jpg',
                   'https://cdn.discordapp.com/attachments/800431166997790790/847498762459807795/DTF20.jpg',
                   'https://cdn.discordapp.com/attachments/760342037962031116/897340137573318696/image0.png',
                   ]
        if pick == -1:
            await ctx.send(random.choice(choices))
        else:
            await ctx.send(choices[pick])

    @lfg.error
    async def lfg_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, IndexError):
            await ctx.send('That index for choice selection is out of bounds.')

    @commands.command()
    async def bestwing(self, ctx, pick: int = -1):
        """Clips from the best wing"""
        choices = ['https://youtu.be/5ces3iYBX60',
                   'https://clips.twitch.tv/InventiveCrackySwallowRaccAttack',
                   'https://clips.twitch.tv/InventiveLightWatercressMcaT-C_4pIBDV_sLrU6dR'
                   ]
        if pick == -1:
            await ctx.send(random.choice(choices))
        else:
            await ctx.send(choices[pick])

    @bestwing.error
    async def bestwing_error(self, ctx, error):
        error = getattr(error, "original", error)
        if isinstance(error, IndexError):
            await ctx.send('That index for choice selection is out of bounds.')

    @commands.command()
    async def arios(self, ctx):
        """Arios Dumps"""
        await ctx.send(
            'https://clips.twitch.tv/HeartlessManlyBoarPlanking')

    @commands.command()
    async def vellian(self, ctx):
        """Vellian achieving infinite power"""
        await ctx.send(
            'https://media.discordapp.net/attachments/814237239084318762/826904531639074866/AndIAmVellian.gif')

    @commands.command()
    async def ca(self, ctx):
        """How2Dodge"""
        await ctx.send(
            'https://cdn.discordapp.com/attachments/800431166997790790/816315636426080296/image0.png')

    @commands.command()
    async def psyren(self, ctx):
        """Psyrens x-rated thoughts"""
        await ctx.send(
            'https://media.discordapp.net/attachments/800431166997790790/801862836656930836/psyren.PNG')

    @commands.command()
    async def shazam(self, ctx):
        """A story they will not tell you"""
        await ctx.send(
            'https://media.discordapp.net/attachments/800431166997790790/801875739778744341/shazam.PNG')

    @commands.command()
    async def nax(self, ctx):
        """Naxes dodger position"""
        await ctx.send(
            'https://media.discordapp.net/attachments/800431166997790790/801862864549052486/nax.PNG')

    @commands.command()
    async def scum(self, ctx):
        """Who, what is scum?"""
        await ctx.send("SCUM stands for: Society Can't Understand Me")

    @commands.command()
    async def drift(self, ctx):
        """Bot will share each drift definition"""
        await ctx.send('https://media.discordapp.net/attachments/800431166997790790/802010541433946192/Drift.png')

    @commands.command()
    async def firaxa(self, ctx):
        """Rockets are OP """
        await ctx.send('https://media.discordapp.net/attachments/800431166997790790/801932465111040070/Firaxa.png')

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain')
    async def echo(self, ctx, channel: discord.TextChannel, *, message):
        """echo..."""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        target_channel = discord.utils.get(guild.text_channels, name=channel.name)
        await target_channel.send(message)

    # Background Tasks
    @tasks.loop(seconds=10800)
    async def burfday(self):
        """It's Scum's Birthday!"""
        await self.client.wait_until_ready()
        today = (datetime.datetime.utcnow() - datetime.timedelta(hours=6)).strftime('%m/%d')
        if today == '12/15':
            scum = self.client.get_user(377177416751251487)
            guild = self.client.get_guild(helper.get_config('guild_id'))
            channel = discord.utils.get(guild.text_channels, name='general')
            await channel.send(f"Today is {scum.mention}'s burfdae!"
                               f" Please wish him a merry day by sliding into his DM's!")


def setup(client):
    client.add_cog(Fun(client))
