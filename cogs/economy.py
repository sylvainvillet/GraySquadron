import discord
from discord.ext import commands, tasks, menus
import asyncio
import random
import datetime
import math
import numpy as np
import decimal
import pandas as pd
from itertools import cycle

from utils import helper


class Economy(commands.Cog):

    def __init__(self, client):
        self.client = client
        # self.game_role.start()
        self.tax_players.start()
        self.restock_shop.start()

        self.credit_msg_reward = 100
        self.lotto_cost = 5

        # SW Card DB
        self.affiliation_list = ['Villain', 'Neutral', 'Hero']
        self.affiliation_codes_list = ['villain', 'neutral', 'hero']
        self.faction_list = ['Command', 'Force', 'Rogue', 'General']
        self.set_list = ['Legacies', 'Redemption', 'Spirit of Rebellion']
        self.card_rate_list = [0.45, 0.4, 0.14, 0.0099, 0.0001]
        self.item_code_card_rarity_dict = {'cp1': 'S', 'cp2': 'C', 'cp3': 'U', 'cp4': 'R', 'cp5': 'L'}
        self.item_code_card_rarity_name_dict = {'cp1': 'Starter', 'cp2': 'Common', 'cp3': 'Uncommon', 'cp4': 'Rare', 'cp5': 'Legendary'}
        self.card_rarity_list = ['S', 'C', 'U', 'R', 'L']
        self.card_pack_type_dict = {'cpa': 'affiliation_name', 'cpf': 'faction_name', 'cps': 'set_name'}
        self.current_affiliation = random.choice(self.affiliation_list)
        self.current_faction = random.choice(self.faction_list)
        self.current_set = random.choice(self.set_list)

    def cog_unload(self):
        self.tax_players.cancel()
        self.restock_shop.cancel()
        # self.game_role.cancel()

    async def get_card_db_info(self):
        """Get sw card database metadata information"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                affiliation_records = await connection.fetch(
                    """SELECT DISTINCT affiliation_name FROM gray.sw_card_db""")
                faction_records = await connection.fetch("""SELECT DISTINCT faction_name FROM gray.sw_card_db""")
                sw_set_records = await connection.fetch("""SELECT DISTINCT set_name FROM gray.sw_card_db""")
                card_rarity_records = await connection.fetch(
                    """SELECT rarity_rate FROM gray.card_rarity_rate ORDER BY rarity_idx ASC""")
        self.affiliation_list = [affiliation[0] for affiliation in affiliation_records]
        self.faction_list = [faction[0] for faction in faction_records]
        self.set_list = [sw_set[0] for sw_set in sw_set_records]
        self.card_rate_list = [rarity[0] for rarity in card_rarity_records]
        self.current_affiliation = random.choice(self.affiliation_list)
        self.current_faction = random.choice(self.faction_list)
        self.current_set = random.choice(self.set_list)

    async def update_shop_quantity(self):
        """Update quantities in the shop"""
        # TODO: Code this part
        pass

    async def check_cd(self, discord_uid: int, cd_type: str) -> (bool, str):
        """Function to return specified cooldown for specified user. True = on cooldown, False = off cooldown."""
        this_time = datetime.datetime.utcnow()
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                set_time = await connection.fetchval("""SELECT set_time FROM gray.cooldown
                                                    where discord_uid = $1 AND cooldown_type = $2""",
                                                     discord_uid, cd_type)
        if set_time is None:
            return True, 0.0
        else:
            time_left = set_time - this_time
            return this_time > set_time, time_left

    async def set_cd(self, discord_uid: int, cd_type: str, delta_type: str, delta_num: int, now: bool = True):
        """Function to set cooldown for specified user"""
        interval_type = 'seconds'
        if delta_type == 'SS':
            interval_type = 'seconds'
        elif delta_type == 'MI':
            interval_type = 'minutes'
        elif delta_type == 'HH':
            interval_type = 'hours'
        base = "now() at time zone 'utc'" if now else 'cooldown.set_time'
        query_statement = f"""INSERT INTO gray.cooldown (discord_uid, cooldown_type, set_time)
                                            VALUES ($1, $2, now() at time zone 'utc' + interval '{delta_num} {interval_type}')
                                            ON CONFLICT (discord_uid, cooldown_type) DO UPDATE 
                                            SET set_time = {base} + interval '{delta_num} {interval_type}'"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(query_statement,
                                         discord_uid,
                                         cd_type)

    async def get_credits(self, discord_uid: int):
        """Function get get credit of specified discord user"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                credits_total = await connection.fetchval("""SELECT credits FROM gray.rpginfo
                                                            where discord_uid = $1""",
                                                          discord_uid)
        if credits_total is None:
            credits_total = 0
        return credits_total

    async def change_credits(self, discord_uid: int, credit_change: int):
        """Function to set a specific discord users credits"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.rpginfo (discord_uid, credits)
                                            VALUES ($1, $2) ON CONFLICT (discord_uid) DO 
                                            UPDATE SET credits = rpginfo.credits + $2""",
                                         discord_uid,
                                         round(credit_change))

    async def get_item_cost_quantity(self, discord_uid: int, item_code: str) -> (int, int, int):
        """Function to get cost of item"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                item_record = await connection.fetch("""SELECT shop_items.cost, shop_items.quantity, user_shop_quantity.user_quantity FROM 
                                                    (SELECT item_code, cost, quantity FROM gray.shop_items WHERE item_code = $2) AS shop_items 
                                                    LEFT JOIN 
                                                    (SELECT item_code, quantity AS "user_quantity" FROM gray.user_shop_quantity WHERE item_code = $2 AND discord_uid = $1) AS user_shop_quantity
                                                    ON shop_items.item_code = user_shop_quantity.item_code""",
                                                     discord_uid, item_code)
        return item_record[0]

    async def get_item_category(self, item_code: str) -> (str, str):
        """Function to get item category"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                item_record = await connection.fetch("""SELECT category, subcategory FROM gray.shop_items
                                                                   where item_code = $1""", item_code)
        if item_record:
            return item_record[0]
        else:
            return 'None', 'None'

    async def change_shop_item_quantity(self, discord_uid: int, item_code: str, quantity: int):
        """Change quantity of specific item code"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.user_shop_quantity (discord_uid, item_code, quantity)
                                        VALUES ($1, $2, $3) ON CONFLICT (discord_uid, item_code) DO
                                        UPDATE SET quantity = user_shop_quantity.quantity + $3
                                        WHERE user_shop_quantity.item_code = $2 and user_shop_quantity.discord_uid = $1""", discord_uid, item_code, quantity)

    async def change_user_item_quantity(self, discord_uid: int, item_category: str, item_subcategory: str, item_code: str, quantity: int):
        """Function go give items to player inventory"""
        if item_category == 'deck':
            current_time = datetime.datetime.utcnow()
            async with self.client.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("""INSERT INTO gray.user_deck (discord_uid, code, count, first_acquired)
                                            VALUES ($1, $2, $3, $4) ON CONFLICT (discord_uid, code) DO 
                                            UPDATE SET count = user_deck.count + $3""",
                                             discord_uid, item_code, quantity, current_time)

    async def open_cardpack(self, item_code: str, quantity: int) -> (list, list):
        """Open random cardpacks"""

        async def get_cards(f_base_string, f_rarity, f_quantity) -> (list, list):
            async with self.client.pool.acquire() as f_connection:
                async with f_connection.transaction():
                    cards_record = await f_connection.fetch(f_base_string, f_rarity, f_quantity)
            return [code[0] for code in cards_record], [code[1] for code in cards_record]

        base_string = """SELECT code, name  FROM gray.sw_card_db WHERE rarity_code = $1"""
        rarity = ''
        if item_code in self.item_code_card_rarity_dict.keys():
            rarity = self.item_code_card_rarity_dict.get(item_code)
        else:
            # Pick rarity
            cum_rates = np.cumsum(self.card_rate_list)
            rand_num = round(random.uniform(0.0001, 1.0000), 4)
            for cum_idx, threshold in enumerate(cum_rates):
                if rand_num <= threshold:
                    rarity = self.card_rarity_list[cum_idx]
                    break
            # Where filter
            col_name = self.card_pack_type_dict.get(item_code)
            col_value = ''
            if item_code == 'cpa':
                col_value = self.current_affiliation
            elif item_code == 'cpf':
                col_value = self.current_faction
            elif item_code == 'cps':
                col_value = self.current_set
            base_string += f" AND {col_name} = '{col_value}'"
        base_string += ' ORDER BY RANDOM() LIMIT $2'

        card_codes, card_names = await get_cards(base_string, rarity, quantity)

        # If not enough cards, try all the rarity from S to L until we have enough cards
        if len(card_codes) != quantity:
            for new_rarity in self.card_rarity_list:
                new_card_codes, new_card_names = await get_cards(base_string, new_rarity, quantity - len(card_codes))
                card_codes.extend(new_card_codes)
                card_names.extend(new_card_names)
                if len(card_codes) == quantity:
                    break;

        return card_codes, card_names

    @staticmethod
    def credits_tier(credits_total: int):
        """Credit Image"""
        coin_tier = {
            'poor0': ['https://media.discordapp.net/attachments/800431166997790790/839901701887885352/none.png', 0.00],
            'bronze1': ['https://cdn.discordapp.com/attachments/800431166997790790/838211670982656000/bronze_1.png',
                        .01],
            'bronze2': ['https://cdn.discordapp.com/attachments/800431166997790790/838211775391989780/bronze_2.png',
                        .02],
            'bronze3': ['https://cdn.discordapp.com/attachments/800431166997790790/838211793242816532/bronze_3.png',
                        .03],
            'bronze4': ['https://cdn.discordapp.com/attachments/800431166997790790/838212333914161172/bronze_4.png',
                        .04],
            'bronze5': ['https://cdn.discordapp.com/attachments/800431166997790790/838212351492358174/bronze_5.png',
                        .05],
            'bronze6': ['https://cdn.discordapp.com/attachments/800431166997790790/838212363127488522/bronze_6.png',
                        .06],
            'bronze7': ['https://cdn.discordapp.com/attachments/800431166997790790/838212456073396234/bronze_7.png',
                        .07],
            'silver1': ['https://media.discordapp.net/attachments/800431166997790790/838961364629585970/silver_1.png',
                        .08],
            'silver2': ['https://media.discordapp.net/attachments/800431166997790790/838961376448872488/silver_2.png',
                        .09],
            'silver3': ['https://media.discordapp.net/attachments/800431166997790790/838961392471375872/silver_3.png',
                        .1],
            'silver4': ['https://media.discordapp.net/attachments/800431166997790790/838961637188436010/silver_4.png',
                        .11],
            'silver5': ['https://media.discordapp.net/attachments/800431166997790790/838961646046412880/silver_5.png',
                        .12],
            'silver6': ['https://media.discordapp.net/attachments/800431166997790790/838961655156834364/silver_6.png',
                        .13],
            'silver7': ['https://media.discordapp.net/attachments/800431166997790790/838961718989815868/silver_7.png',
                        .14]
        }
        bracket = 'poor0'
        if credits_total <= 0:
            pass
        elif credits_total < 100:
            bracket = 'bronze1'
        elif credits_total < 500:
            bracket = 'bronze2'
        elif credits_total < 2_500:
            bracket = 'bronze3'
        elif credits_total < 12_500:
            bracket = 'bronze4'
        elif credits_total < 62_500:
            bracket = 'bronze5'
        elif credits_total < 312_500:
            bracket = 'bronze6'
        elif credits_total < 1_562_500:
            bracket = 'bronze7'
        elif credits_total < 7_812_500:
            bracket = 'silver1'
        elif credits_total < 39_062_500:
            bracket = 'silver2'
        elif credits_total < 195_312_500:
            bracket = 'silver3'
        elif credits_total < 976_562_500:
            bracket = 'silver4'
        elif credits_total < 4_882_812_500:
            bracket = 'silver5'
        elif credits_total < 24_414_062_500:
            bracket = 'silver6'
        elif credits_total < 122_070_312_500:
            bracket = 'silver7'
        img_link = coin_tier.get(bracket)[0]
        tax_rate = coin_tier.get(bracket)[1]
        return img_link, bracket, tax_rate

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Cog is online.')

    @commands.Cog.listener()
    async def on_message(self, message):
        """Trigger word triggered"""
        discord_uid = message.author.id
        # if discord_uid == 195747311136145409:
        if discord_uid != 775808657199333376:
            if 'HOPE' in message.content.upper().replace(' ', ''):
                cd, _ = await self.check_cd(discord_uid, 'HOPE')
                if cd:
                    await message.add_reaction('<:rebel:761887570656231434>')
                    await self.change_credits(discord_uid, self.credit_msg_reward)
                    await self.set_cd(discord_uid, 'HOPE', 'MI', 30)
            if 'VAPOR' in message.content.upper().replace(' ', ''):
                await message.add_reaction('<:SidSmile:768524163505061918>')

    # Commands
    @commands.command()
    async def game(self, ctx):
        """Information on game"""
        rules = 'Competitive seasonal play where ranking is determined by final Galactic Imperial Points!' \
                '\nPrizes: 1st - $20, 2nd - $10, 3rd - $5'
        start = f'Send a message with the keyword "HOPE" in chat for {self.credit_msg_reward} credits every 30 mins from the Rebel Alliance!' \
                '\nCheck out the other game commands with $help Economy'
        road_map = 'Inventory\nRPGAdventure'
        embed = discord.Embed(title='Game?', description='*Season 1: The Beginning*')
        embed.set_thumbnail(
            url='https://media.discordapp.net/attachments/800431166997790790/839847320224923648/gonk_droid.jpg')
        embed.add_field(name='What Is?', value=rules, inline=False)
        embed.add_field(name='Get Started!', value=start, inline=False)
        embed.add_field(name='Road Map', value=road_map, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def lotto(self, ctx):
        """Buy lotto tickets...will you moon?"""
        discord_uid = ctx.author.id
        credits_total = await self.get_credits(discord_uid)
        lotto_list = [['SLOTTO', 'HH', 2, 'Scratcher', 0.5], ['DLOTTO', 'HH', 24, 'Daily', 6],
                      ['WLOTTO', 'HH', 168, 'Weekly', 20]]
        if credits_total >= self.lotto_cost:
            prize_total = 0
            result_string = ''
            cd_string = ''
            header_state = 'still'
            display_name = ctx.author.display_name
            if display_name.find(']') > 0:
                display_name = display_name[display_name.find(']') + 2:]
            for lotto_type in lotto_list:
                cd, time_left = await self.check_cd(discord_uid, lotto_type[0])
                if cd:
                    header_state = 'now'
                    prize = random.randint(1, 5) * lotto_type[4] * self.credit_msg_reward
                    result_string += f'\n{display_name} won {prize:,.0f} credits from their {lotto_type[3]}!'
                    prize_total += prize
                    await self.set_cd(discord_uid, lotto_type[0], lotto_type[1], lotto_type[2])
                else:
                    cd_string += f"\n{lotto_type[3]}: {str(time_left).split('.')[0]}"
            await self.change_credits(discord_uid, prize_total - 1)
            await self.change_credits(775808657199333376, 1)
            header_string = f'{ctx.author.mention} {header_state} has {credits_total + prize_total - self.lotto_cost:,.0f} credits!'
            footer_string = f'Lotto cost: {self.lotto_cost} C'

            embed = discord.Embed(title="Lotto Results", description=header_string, colour=ctx.author.colour)
            embed.set_thumbnail(
                url='https://cdn.discordapp.com/attachments/800431166997790790/838200985443893279/ticket.gif')
            if len(result_string) > 0:
                embed.add_field(name='__Prize__', value=result_string, inline=False)
            if len(cd_string) > 0:
                embed.add_field(name='__Time Remaining__', value=cd_string, inline=False)
            embed.set_footer(text=footer_string)
            await ctx.send(embed=embed)

        else:
            await ctx.send(f'Sorry, a credit lotto combo-pack costs {self.lotto_cost} C.', delete_after=15)

    @commands.command()
    async def bal(self, ctx):
        """Displays users credit balance"""
        discord_uid = ctx.author.id
        credit_total = await self.get_credits(discord_uid)
        img_link, bracket, tax_rate = self.credits_tier(credit_total)
        tax_bracket_string = f'{bracket[:-1].capitalize()} {bracket[-1]}'
        header_string = f'\nBalance: {credit_total:,}'
        embed = discord.Embed(title=f"{tax_bracket_string} Wallet", description=header_string, colour=ctx.author.colour)
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_thumbnail(url=img_link)
        # TODO: Stats on wallet growth
        embed.set_footer(text=f'Tax Rate: {tax_rate * 100:.1f}%')
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role('Droid Engineer')
    async def credit_hax(self, ctx, member: discord.Member = None, count: int = 100_000_000):
        """For testing only"""
        user = member
        if user is None:
            user = ctx.author
        await self.change_credits(user.id, count)

    @commands.command()
    @commands.cooldown(rate=1, per=30, type=commands.BucketType.user)
    async def transfer(self, ctx, member: discord.Member, count: int, *, reason: str = 'None'):
        """Transfer credits to another user"""
        giver = ctx.author.id
        taker = member.id
        giver_total = await self.get_credits(giver)
        if giver_total > 0:
            if count > 5:
                if count <= giver_total:
                    _, _, tax_rate = self.credits_tier(giver_total)
                    give_count = math.ceil(count * (1 - tax_rate)) - 5
                    tax_count = count - give_count
                    await ctx.send(f'{ctx.author.mention} have gifted {member.mention} {count} credits! '
                                   f'\nMemo: {reason}'
                                   f'\n{tax_count} credits were withheld for handling fees.')
                    await self.change_credits(giver, -1 * count)
                    await self.change_credits(taker, give_count)
                    await self.change_credits(775808657199333376, tax_count)
                else:
                    await ctx.send(f'You only have {giver_total} credits!')
            else:
                await ctx.send(f'The flat transaction fee is 5 C!', delete_after=10)

    @transfer.error
    async def transfer_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('How many credits are you transferring?', delete_after=10)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send('You are limited to 1 transfer per 30 seconds!', delete_after=5)
        else:
            print(error)

    @commands.command()
    async def lb(self, ctx):
        """Canto Bight's High Rollers"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                value_lb = await connection.fetch("""
                SELECT rpginfo.discord_uid, 
                rpginfo.credits + coalesce(ct."S",0)*4000 + coalesce(ct."C",0)*15000 + coalesce(ct."U",0)*80000 + coalesce(ct."R",0)*400000 + coalesce(ct."L",0)*5000000 AS "TOTAL",
                rpginfo.credits, coalesce(ct."S",0) as "S", coalesce(ct."C",0) as "C", coalesce(ct."U",0) as "U", coalesce(ct."R",0) as "R", coalesce(ct."L",0) as "L"

                FROM crosstab(
               'SELECT deck.discord_uid, cards_db.rarity_code, SUM(deck.count) FROM gray.user_deck AS deck 
                INNER JOIN gray.sw_card_db AS cards_db on deck.code = cards_db.code GROUP BY 1,2 ORDER BY 1,2;',
                'SELECT DISTINCT rarity_code FROM gray.sw_card_db ORDER BY 1'
               ) AS ct (discord_uid bigint, "C" int, "L" int, "R" int, "S" int, "U" int) 
   
                RIGHT JOIN gray.rpginfo AS rpginfo on ct.discord_uid = rpginfo.discord_uid ORDER BY "TOTAL" DESC;""")
        menu = menus.MenuPages(source=EconomyLB(ctx, value_lb), clear_reactions_after=True)
        await menu.start(ctx)
        await ctx.message.delete()

    @commands.command()
    @commands.cooldown(rate=1, per=30, type=commands.BucketType.user)
    async def duel(self, ctx, opponent: discord.Member, wager: int):
        """Duel a specific user for x credits"""
        if ctx.author.id == opponent.id:
            await ctx.send('You cannot duel yourself.')
            return
        one_credits_total = await self.get_credits(ctx.author.id)
        two_credits_total = await self.get_credits(opponent.id)
        if one_credits_total < wager:
            await ctx.send(f'{ctx.author.mention} only has {one_credits_total} credits.')
        elif two_credits_total < wager:
            await ctx.send(f'{opponent.mention} only has {two_credits_total} credits.')
        else:
            emoji_list = ['<:swblaster:763109456774430821>', '<:sabergreen:839526247113555998>',
                          '<:SidSmile:768524163505061918>', '🏃']

            async def duel_helper(one: discord.Member, two: discord.Member, emojis, b_count):
                msg = await one.send(f'Dueling against {two.display_name} for {b_count} credits!'
                                     f'\nPlease select one of the below emojis!'
                                     f'\n(Response is final, you cannot change after submission.)'
                                     f'\nBlaster < Saber < Force < Blaster'
                                     f'\nYou can also flee, coward.')
                for emoji in emojis:
                    await msg.add_reaction(emoji)

                def check(r, u):
                    # R = Reaction, U = User
                    return u == one and str(
                        r.emoji) in emojis and r.message.channel == one.dm_channel and r.message.id == msg.id

                try:
                    reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=300)
                except asyncio.TimeoutError:
                    await one.send(f'Duel has timed out between {one.display_name} and {two.display_name}.')
                    await ctx.send(f'Duel has timed out between {one.display_name} and {two.display_name}.')
                    return
                return str(reaction.emoji)

            if not opponent.bot:
                one_helper = duel_helper(ctx.author, opponent, emoji_list, wager)
                two_helper = duel_helper(opponent, ctx.author, emoji_list, wager)
                one_r, two_r = await asyncio.gather(one_helper, two_helper)
            else:
                one_r = await duel_helper(ctx.author, opponent, emoji_list, wager)
                two_r = random.choice(emoji_list[:3])

            try:
                one_index = emoji_list.index(one_r)
                two_index = emoji_list.index(two_r)
            except ValueError as e:
                return

            if opponent.bot:
                result = random.randint(1, 3)
                if result > 2:
                    if one_index == 0:
                        two_index = 1
                    elif one_index == 1:
                        two_index = 2
                    elif one_index == 2:
                        two_index = 0
                two_r = emoji_list[two_index]

            def check_results(one_i, two_i):
                result_matrix = [[0, 10, 22, 29], [20, 0, 11, 29], [12, 21, 0, 29], [19, 19, 19, -99]]
                return result_matrix[two_i][one_i]

            result = check_results(one_index, two_index)

            one_name = ctx.author.display_name
            if one_name.find(']') > 0:
                one_name = one_name[one_name.find(']') + 2:]
            two_name = opponent.display_name
            if two_name.find(']') > 0:
                two_name = two_name[two_name.find(']') + 2:]

            if result == -99:
                em_color = 0xFFFFFF
                result_string = 'Both duelists flee cowardly!'
            elif result == 19:
                em_color = ctx.author.colour
                result_string = f'{two_name} flees from the duel against {one_name}!'
            elif result == 29:
                em_color = opponent.color
                result_string = f'{one_name} flees from the duel against {two_name}!'
            elif result == 0:
                em_color = 0x000000
                result_string = f'{one_name} and {two_name} clash violently!'
            elif result == 10:
                result_string = f'{one_name} slices down {two_name}!'
            elif result == 20:
                result_string = f'{two_name} slices down {one_name}!'
            elif result == 11:
                result_string = f'{one_name} force chokes {two_name}!'
            elif result == 21:
                result_string = f'{two_name} force chokes {one_name}!'
            elif result == 12:
                result_string = f'{one_name} shoots down {two_name}!'
            elif result == 22:
                result_string = f'{two_name} shoots down {one_name}!'
            else:
                result_string = 'This result is not possible!'

            prize = math.ceil(wager * .9)
            tax = wager - prize

            if str(result)[-1] == '9' or str(result)[:1] == '0':
                em_avatar = 'https://cdn.discordapp.com/attachments/800431166997790790/838120002849603584/small.png'
                tax = 0
            else:
                if str(result)[:1] == '1':
                    em_color = ctx.author.colour
                    em_avatar = ctx.author.avatar_url
                    await self.change_credits(ctx.author.id, (-1 * wager) + (2 * prize))
                    await self.change_credits(opponent.id, (-1 * wager))
                elif str(result)[:1] == '2':
                    em_color = opponent.color
                    em_avatar = opponent.avatar_url
                    await self.change_credits(ctx.author.id, (-1 * wager))
                    await self.change_credits(opponent.id, (-1 * wager) + (2 * prize))
                else:
                    print('This is not in the result matrix.')
                await self.change_credits(775808657199333376, (2 * tax))
                coin_string1 = f'{one_name}\n{two_name}'
                coin_string2 = f'{one_credits_total:,} > {one_credits_total - wager:,} -> {await self.get_credits(ctx.author.id):,} C' \
                               f'\n{two_credits_total:,} > {two_credits_total - wager:,} -> {await self.get_credits(opponent.id):,} C'
            embed = discord.Embed(title="Duel Results", description=result_string, colour=em_color)
            embed.set_thumbnail(url=em_avatar)
            embed.add_field(name='Aggressor', value=f'{ctx.author.mention}', inline=True)
            embed.add_field(name='~V.S~', value=f'{one_r}v{two_r}', inline=True)
            embed.add_field(name='Defender', value=f'{opponent.mention}', inline=True)
            if not str(result)[-1] == '9' and not str(result)[:1] == '0':
                embed.add_field(name='__Prize__', value=f'{2 * prize:,} C', inline=False)
                embed.add_field(name='__Name__', value=coin_string1, inline=True)
                embed.add_field(name='__Change__', value=coin_string2, inline=True)
            embed.set_footer(text=f'Cleaner Fee: {2 * tax} C')
            await ctx.send(embed=embed)

    @duel.error
    async def duel_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('How many credits are you wagering in the duel?', delete_after=10)
        elif isinstance(error, ValueError):
            return
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send('You can only initiate a duel once every 30 seconds!', delete_after=5)
        else:
            print(error)

    @commands.command(aliases=['slot_stat'])
    @commands.has_any_role('Droid Engineer')
    async def slot_stats(self, ctx):
        """Get stats of the slot machine"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                slot_stats_record = await connection.fetch(
                    """SELECT machine_name, AVG(total_spins) AS "AVG SPIN", AVG(profit) AS "AVG PROFIT", 
                    AVG(porg_multi) AS "AVG PORG MULTI", AVG(input_multi) AS "AVG MULTI" FROM gray.slot_history GROUP BY machine_name""")
        slot_stats_dict = helper.record_to_dict(slot_stats_record, 'machine_name')
        machine_names_list = slot_stats_dict.keys()

        spin_avg = [slot_stats_dict.get(machine).get('AVG SPIN') for machine in machine_names_list]
        profit_avg = [slot_stats_dict.get(machine).get('AVG PROFIT')/slot_stats_dict.get(machine).get('AVG MULTI') for machine in machine_names_list]
        multi_avg = [decimal.Decimal('1.1') ** slot_stats_dict.get(machine).get('AVG PORG MULTI') for machine in
                     machine_names_list]

        n_profit_pg = [str(round((a / s), 1)) for a, s in zip(profit_avg, spin_avg)]
        n_multi_pg = [str(round(mu / s * 10, 1)) for mu, s in zip(multi_avg, spin_avg)]

        n_profit_pg_string = '\n'.join(n_profit_pg)
        n_multi_pg_string = '\n'.join(n_multi_pg)

        embed = discord.Embed(title='Slot Stats', description='Quick Info')
        embed.add_field(name='Names', value='\n'.join(machine_names_list))
        embed.add_field(name='Profit/Spin', value=n_profit_pg_string)
        embed.add_field(name='PorgMulti/10Spins', value=n_multi_pg_string)
        await ctx.send(embed=embed)

    @slot_stats.error
    async def slot_stats_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have access to this intel.')
        else:
            print(error)

    @commands.command(aliases=['s', 'slots'])
    # @commands.has_any_role('Droid Engineer')
    @commands.cooldown(rate=1, per=30, type=commands.BucketType.user)
    async def slot(self, ctx):
        """Tempt fate will you?"""
        slot_machine = SlotMachine(self, ctx)
        await slot_machine.run()

    @slot.error
    async def slot_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send('You can only play the slots once every 30 seconds!', delete_after=5)
        else:
            print(error)

    @commands.command(aliases=['slots_info'])
    async def slot_info(self, ctx):
        """Information on the slot machine"""
        slot_emoji_list = ['<:saberwhite:839526247209500712>',
                           '<:saberred:839526247108575272>', '<:saberpurple:839526247159037982>',
                           '<:saberblue:839526247146848284>', '<:sabergreen:839526247113555998>',
                           '<:swblaster:763109456774430821>', '<:PorgStab:761886195432423474>',
                           '<:SidSmile:768524163505061918>', '<:GraySquadron:761887065448251412>']
        symbol_string = '\n'.join(slot_emoji_list)
        action_emoji_list = ['🕹️', '💰', '⬅', '➡', '🛑']
        action_list = '\n'.join(['Spin!', 'Cash out current net', 'Previous Machine', 'Next Machine', 'Quit.'])
        control_string = '\n'.join(action_emoji_list)
        info_emoji_list = ['⬅', '➡', '🛑']
        stop = False

        async def get_machine_info():
            """Gets all the slot machine info"""
            async with self.client.pool.acquire() as connection:
                async with connection.transaction():
                    reward_record = await connection.fetch("""SELECT machine_name, symbol_idx, symbol_reward_type, 
                                                            symbol_reward_value FROM gray.slot_machine_values""")
                    symbol_reward_dict = {}
                    for reward in iter(reward_record):
                        machine_name = reward[0]
                        r_position = reward[1]
                        r_type = reward[2]
                        if r_type == 'coin':
                            type_string = 'C'
                        elif r_type == 'multi':
                            type_string = 'Multi'
                        elif r_type == 'turn':
                            type_string = 'Spin(s)'
                        r_value = reward[3]
                        if r_value > 0:
                            value_string = f'+{r_value}'
                        else:
                            value_string = str(r_value)
                        result_string = f'{value_string} {type_string}'
                        try:
                            previous_string = symbol_reward_dict[machine_name].get(r_position)
                            if previous_string is not None:
                                result_string = f'{previous_string}/{result_string}'
                            symbol_reward_dict[machine_name].update({r_position: result_string})
                        except KeyError:
                            symbol_reward_dict[machine_name] = {r_position: result_string}

                    info_record = await connection.fetch("""SELECT * FROM gray.slot_machine_info""")
                    machine_info_dict = helper.record_to_dict(info_record, 'machine_name')
                    machine_names_cycle = cycle(list(machine_info_dict.keys()))
            return symbol_reward_dict, machine_info_dict, machine_names_cycle

        async def generate_slot_info_embed(symbol_reward_dict: dict, machine_info_dict: dict, machine_name: str):
            """Returns an embed with slot information for given machine"""
            selected_rewards = symbol_reward_dict.get(machine_name)
            selected_info = machine_info_dict.get(machine_name)
            info_string = 'Medals'
            rewards_string = ''
            for idx in range(1, 10):
                reward = selected_rewards.get(idx)
                rewards_string += f'{reward}\n'
            new_embed = discord.Embed(title='Slot Machine Info!', description='Your personal guide to gambling.',
                                      colour=0xFFFF)
            new_embed.add_field(name='Slot Type', value=machine_name, inline=True)
            new_embed.add_field(name='Cost', value=selected_info.get('cost') * selected_info.get('max_spin'),
                                inline=True)
            new_embed.add_field(name='Major Jackpot', value=selected_info.get('major_jackpot'), inline=True)
            new_embed.add_field(name='Symbol', value=symbol_string, inline=True)
            new_embed.add_field(name='Reward', value=rewards_string, inline=True)
            new_embed.add_field(name='Bonuses',
                                value='Any 2 sabers to x2 that spin!\nAny 3 sabers to x5 that spin!\nGet 3 Gray Symbols for JACKPOT!',
                                inline=False)
            new_embed.add_field(name='Controls', value=control_string, inline=True)
            new_embed.add_field(name='Action', value=action_list, inline=True)
            new_embed.add_field(name='Future updates to include:', value=info_string, inline=False)
            new_embed.set_footer(text='Help Hotline: 1-800-522-4700')
            return new_embed

        async def slot_info_reaction_waiter(msg):
            """Async helper to await for reactions"""
            for emoji in info_emoji_list:
                await msg.add_reaction(emoji)

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in info_emoji_list and r.message.id == msg.id

            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                return 'Timeout'
            return str(reaction.emoji)

        reward_dict, info_dict, names_cycle = await get_machine_info()
        current_name = next(names_cycle)
        embed = await generate_slot_info_embed(reward_dict, info_dict, current_name)
        sent_embed = await ctx.send(embed=embed)

        while not stop:
            user_input = await slot_info_reaction_waiter(sent_embed)
            if user_input == info_emoji_list[0]:
                await sent_embed.remove_reaction(user_input, ctx.author)
                for _ in range(0, len(list(info_dict.keys())) - 1):
                    current_name = next(names_cycle)
                await sent_embed.edit(embed=await generate_slot_info_embed(reward_dict, info_dict, current_name))
            elif user_input == info_emoji_list[1]:
                await sent_embed.remove_reaction(user_input, ctx.author)
                current_name = next(names_cycle)
                await sent_embed.edit(embed=await generate_slot_info_embed(reward_dict, info_dict, current_name))
            else:
                stop = True
        await sent_embed.clear_reactions()
        await asyncio.sleep(30)
        await sent_embed.delete()

    @commands.command()
    async def shop(self, ctx):
        """Khajit has wares if you have coin"""
        shop = Shop(self, ctx)
        await shop.run()

    @commands.command()
    # @commands.has_any_role('Droid Engineer')
    async def buy(self, ctx, item_command: str, quantity: int = 1):
        """Provide item code and quantity to purchase.

        Arguments:
        - item_code: Code from the item you want to buy (cp1, cp2, ...)
        - all: Buy all the items in the shop (cp1 to cp5, cpa, cpf and cps)
        - cpx: Buy all the cp1 to cp5 items
        - quantity: If you provided an item_code, you can specify an optional quantity

        Examples:
        - $buy cp1
        Buy one cp1 card

        - $buy cp4 3
        Buy 3 cp4 cards

        - $buy all
        Buy everything you can until the shop is empty or you run out of money

        - $buy cpx
        Buy all the cp1 to cp5 cards until the shop is empty or you run out of money"""

        # Build the list of items to buy
        item_code_list = []
        buy_single_item = False
        quantity_bought = 0
        if item_command == "all":
            item_code_list=list(self.item_code_card_rarity_dict.keys())+list(self.card_pack_type_dict.keys())
        elif item_command == "cpx":
            item_code_list=list(self.item_code_card_rarity_dict.keys())
        else:
            buy_single_item = True
            item_code_list.append(item_command)

        messages = []
        for item_code in item_code_list:
            # Validate user quantity is a positive number
            if quantity < 1:
                return
            discord_uid = ctx.author.id
            user_credit_total = await self.get_credits(discord_uid)
            # Validate item exists in database
            try:
                item_cost, item_quantity, user_quantity = await self.get_item_cost_quantity(discord_uid, item_code)
                user_quantity = 0 if user_quantity is None else user_quantity
            except IndexError:
                await ctx.send('Sorry, that is not a valid item code! Please check $shop.')
                return
            
            total_cost = 0

            # Only handle quantity argument for single purchase, buy as many as possible otherwise
            if buy_single_item:
                # Validate this item is in stock
                if item_quantity + user_quantity < quantity:
                    await ctx.send('Sorry, there are not enough available to purchase!')
                    return
                total_cost = item_cost * quantity
                # Validate user has funds to purchase item
                if total_cost > user_credit_total:
                    await ctx.send('Sorry, you do not have enough credits for this purchase!')
                    return
            else:
                # No cards to buy, continue
                if item_quantity + user_quantity == 0:
                    continue
                # Buy as many cards as possible
                quantity = min(item_quantity + user_quantity, math.floor(user_credit_total / item_cost))
                # Not enough money to buy more cards, exit
                if quantity == 0:
                    if quantity_bought == 0:
                        await ctx.send('Sorry, you do not have enough credits for this purchase!')
                    else:
                        await ctx.send('{}\n{}'.format('\n'.join(messages), 
                            f'You have bought {quantity_bought} card(s) but you do not have enough credits to buy all the cards requested.'))
                    return
                total_cost = item_cost * quantity

            _, _, tax_rate = self.credits_tier(user_credit_total)
            try:
                # Update item quantity
                quantity_bought += quantity
                await self.change_shop_item_quantity(discord_uid, item_code, -1 * quantity)
                item_category, item_subcategory = await self.get_item_category(item_code)
                if item_category == 'deck':
                    cards_list, names_list = await self.open_cardpack(item_code, quantity)
                    for card_code in cards_list:
                        await self.change_user_item_quantity(discord_uid, item_category, item_subcategory, card_code, 1)

                    item_name = ''
                    if item_code in ['cp1', 'cp2', 'cp3', 'cp4', 'cp5']:
                        item_name = self.item_code_card_rarity_name_dict[item_code]
                    elif item_code == 'cpa':
                        item_name = self.current_affiliation
                    elif item_code == 'cpf':
                        item_name = self.current_faction
                    elif item_code == 'cps':
                        item_name = self.current_set

                    messages.append('{} cards revealed:\n- {}'.format(item_name, helper.join_with_and('{} ({})'.format(name, code) for code, name in zip(cards_list, names_list))))
            except Exception as e:
                print(e)
                return
            else:
                # Update credits balances
                tax_amount = math.floor(total_cost * tax_rate)
                await self.change_credits(discord_uid, -1 * total_cost)
                await self.change_credits(775808657199333376, tax_amount)
                # TODO: Embed to display what was bought
                # - When you buy a card, show it's bonus (like +2% blablabla) directly in the message instead of having to open and scroll through the deck to find the card
                # - Show the "value" of the card when browsing the deck (how much it counts on the leaderboard)
                # - Show a break down of the total fortune used for the leaderboard with the $bal command (like the wallet + 1x 4k for Starters + 17x 15k for Common, etc...)
        if quantity_bought > 0:
            messages.append('Transaction successful! For more details about cards, use \"$deck <card_code(s)>\".')
        else:
            messages.append('Nothing to buy!')
        await ctx.send('\n'.join(messages))

    @buy.error
    async def buy_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('You must provide the item code! Browse item codes using $shop', delete_after=10)
        else:
            print(error)

    @commands.command(aliases=['card', 'cards'])
    async def deck(self, ctx, *args):
        """Displays your collection of cards, or the one from another user.

        You can use various arguments to filter the deck by affiliation and/or faction,
        and you can use the "missing" argument to see card you don't own.
        
        Arguments:
        - h, hero, heroes: Affiliation filter for hero cards
        - n, neutral, neutrals: Affiliation filter for neutral cards
        - v, villain, villains: Affiliation filter for villain cards
        - s, starter, starters: Rarity filter for starters cards
        - c, common: Rarity filter for common cards
        - u, uncommon: Rarity filter for uncommon cards
        - r, rare: Rarity filter for rare cards
        - l, legendary: Rarity filter for legendary cards
        - Card codes: One or multiple card numbers seperated by a space
        - missing: Shows the cards you don't own, can be combined with filters

        Examples:
        - $deck
        Shows your complete deck

        - $deck @user villain
        Shows all the villains cards from user

        - $deck l
        Shows all your legendary cards

        - $deck h s
        Shows all your hero starters cards

        - $deck h n r l
        Shows all your cards of affiliation hero or neutral, and of rarity rare or legendary

        - $deck 01001 
        Shows the card 01001

        - $deck 01001 01002
        Shows the cards 01001 and 01002

        - $deck missing
        Shows all the cards you don't own

        - $deck missing v l
        Shows all the villains legendary cards you don't own"""
        missing = False
        try:
            if 'missing' in args:
                missing = True
            user, _, affiliation_codes, rarity_codes, card_codes = await helper.parse_input_args_filters(ctx, commands, [arg for arg in args if arg != 'missing'])
        except ValueError as err:
            await ctx.send('{}\nType "$help deck" for more info.'.format(err))

        if missing and card_codes:
            await ctx.send('Invalid arguments. You can\'t use both "missing" and card codes at the same time.\nType "$help request_card" for more info.')
            return
        else:
            if user is None:
                user = ctx.author

            user_deck = Deck(self, ctx, user, affiliation_codes, rarity_codes, card_codes, missing)
            await user_deck.run()

    # TODO: Maybe have $send_card and $request_card commands would make things clearer than $trade_card that many people don't know which way it's going
    @commands.command()
    async def trade_card(self, ctx, user: discord.Member, request_card_code: str):
        """$trade_card @user <card_code>"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                card_quantity = await connection.fetchval(
                    """SELECT count FROM gray.user_deck WHERE discord_uid = $1 AND code = $2""",
                    user.id, request_card_code)
                card_name = await connection.fetchval(
                    """SELECT name FROM gray.sw_card_db WHERE code = $1""", request_card_code)

                if card_quantity is None or card_quantity == 0:
                    await ctx.send(f'{user.display_name} does not have {request_card_code} in their deck.')
                else:
                    trade_emojis = ['✅', '🚫']

                    async def trade_card_helper() -> str:

                        msg = await user.send(f'{ctx.author.display_name} is requesting card: {card_name}')
                        for emoji in trade_emojis:
                            await msg.add_reaction(emoji)

                        def check(r, u):
                            # R = Reaction, U = User
                            return u == user and str(
                                r.emoji) in trade_emojis and r.message.channel == user.dm_channel and r.message.id == msg.id

                        try:
                            reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
                        except asyncio.TimeoutError:
                            await ctx.send(f'Trade has timed out between {ctx.author.display_name} and {user.display_name}.')
                            return 'Timeout'
                        return str(reaction.emoji)
                    user_input = await trade_card_helper()
                    # Accept
                    if user_input == trade_emojis[0]:
                        card_quantity = await connection.fetchval(
                            """SELECT count FROM gray.user_deck WHERE discord_uid = $1 AND code = $2""",
                            user.id, request_card_code)
                        if card_quantity > 0:
                            await self.change_user_item_quantity(ctx.author.id, 'deck', 'card', request_card_code, 1)
                            await self.change_user_item_quantity(user.id, 'deck', 'card', request_card_code, -1)
                            await ctx.send(f'{user.mention} has traded {card_name} to {ctx.author.mention}!')

    # Background Tasks
    @tasks.loop(seconds=600, reconnect=True)
    async def game_role(self):
        """Give game role to all users with credits"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        game_role = discord.utils.get(guild.roles, name='Game')
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                game_players = await connection.fetch("""SELECT discord_uid FROM gray.rpginfo WHERE credits > 0""")
        for player in game_players:
            discord_uid = player[0]
            member = guild.get_member(discord_uid)
            await member.add_roles(game_role)

    @tasks.loop(hours=12, reconnect=True)
    async def tax_players(self):
        """Taxes players Sunday based on wallet holdings"""
        if datetime.datetime.now().weekday() == 6:
            guild = self.client.get_guild(helper.get_config('guild_id'))
            async with self.client.pool.acquire() as connection:
                async with connection.transaction():
                    game_players = await connection.fetch(
                        """SELECT discord_uid, credits FROM gray.rpginfo WHERE credits > 0""")
            for player in game_players:
                discord_uid, credits_total = player[0], player[1]
                _, _, tax_rate = self.credits_tier(credits_total)
                tax_amount = math.ceil(credits_total * tax_rate)
                await self.change_credits(discord_uid, -1 * tax_amount)
                await self.change_credits(775808657199333376, tax_amount)
                member = guild.get_member(discord_uid)
                await member.send(f'You have been taxed {tax_rate} on your balance of {credits_total}.'
                                  f'\nThank you for being an integral cog of our society!')

    # @tasks.loop(hours=24, reconnect=True)
    # async def refresh_backend_info(self):
    #     """Refresh backend card info"""
    #     await self.get_card_db_info()

    @tasks.loop(minutes=1, reconnect=True)
    async def restock_shop(self):
        """Check every minute whether the shop needs restock"""
        cd, _ = await self.check_cd(775808657199333376, 'RESTOCK')
        cdm, _ = await self.check_cd(775808657199333376, 'RESTOCK_MINOR')
        if cd:
            # Update shop quantity
            await self.set_cd(775808657199333376, 'RESTOCK', 'HH', 24, False)
            async with self.client.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("""UPDATE gray.user_shop_quantity SET quantity = 0""")
            # Cycle Card Packs
            await self.get_card_db_info()
        elif cdm:
            # Update shop quantity
            await self.set_cd(775808657199333376, 'RESTOCK_MINOR', 'HH', 8, False)
            async with self.client.pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute("""UPDATE gray.user_shop_quantity
                                            SET quantity = CASE WHEN user_shop_quantity.quantity > -1*floor(shop_items.quantity*0.2) THEN 0
                                            ELSE user_shop_quantity.quantity + floor(shop_items.quantity*0.2) END
                                            FROM gray.shop_items
                                            WHERE user_shop_quantity.item_code = shop_items.item_code and user_shop_quantity.quantity < 0;""")


class SlotMachine:
    # TODO: Han Solo Machine
    slot_emoji_list = ['<a:sw_slot:839526247255375892>', '<:saberwhite:839526247209500712>',
                       '<:saberred:839526247108575272>', '<:saberpurple:839526247159037982>',
                       '<:saberblue:839526247146848284>', '<:sabergreen:839526247113555998>',
                       '<:swblaster:763109456774430821>', '<:PorgStab:761886195432423474>',
                       '<:SidSmile:768524163505061918>', '<:GraySquadron:761887065448251412>']
    # Black, Red, Yellow, Green, Black
    state_list = [['SLOT IDLE', 0x000000], ['YOU LOST', 0xFF0800], ['SPINNING', 0xFFF700],
                  ['YOU WIN', 0x2EFF00], ['CLOSED', 0x000000]]
    action_emoji_list = ['🕹️', '💰', '⬅', '➡', '🛑']
    card_bonus_dict = {'S': 1, 'C': 2, 'U': 8, 'R': 20, 'L': 50}

    def __init__(self, economy, ctx):
        self.economy = economy
        self.ctx = ctx

        self.machine_info_dict = None
        self.machine_type_names = None
        self.machine_count = 0

        self.author = ctx.author
        self.player_credits_total = 0
        self.player_bonus_dict = {}
        self.user_slot_stats_dict = None

        self.machine_level = 1
        self.machine_exp = 0
        self.next_exp = 999

        self.state = 0
        self.start_slots = [SlotMachine.slot_emoji_list[0], SlotMachine.slot_emoji_list[0],
                            SlotMachine.slot_emoji_list[0]]
        self.active_slots = [SlotMachine.slot_emoji_list[9], SlotMachine.slot_emoji_list[9],
                             SlotMachine.slot_emoji_list[9]]
        self.final_slots = None

        self.selected = False
        self.selected_machine_name = None
        self.selected_machine_cost = 0
        self.selected_machine_icon = None
        self.symbol_rate_list = None
        self.symbol_reward_list = None
        self.current_jackpot = None
        self.epic_fail = 0
        self.profit = 0
        self.porg_multi = 0
        self.spins_left = 0
        self.total_spins = 0
        self.win_bool = False
        self.bonus = 0
        self.multi = 1

        self.sent_embed = None

    async def setup_selected_machine(self):
        if self.selected_machine_name == 'JEDI HERO':
            self.bonus = self.player_bonus_dict.get('Hero', 0)
        elif self.selected_machine_name == 'PORG LOVE':
            self.bonus = self.player_bonus_dict.get('Neutral', 0)
        elif self.selected_machine_name == 'SITH REVENGE':
            self.bonus = self.player_bonus_dict.get('Villain', 0)
        current_machine_dict = self.machine_info_dict.get(self.selected_machine_name)
        active_slots = current_machine_dict.get('active_slots')
        for idx, slot in enumerate(active_slots):
            slot_emoji = SlotMachine.slot_emoji_list[slot]
            self.active_slots[idx] = slot_emoji
        self.selected_machine_cost = current_machine_dict.get('cost') * current_machine_dict.get('max_spin')
        self.spins_left = current_machine_dict.get('max_spin')
        self.selected_machine_icon = current_machine_dict.get('icon')
        self.epic_fail = current_machine_dict.get('epic_fail')
        self.current_jackpot = await self.get_jackpot(self.selected_machine_name)
        current_machine_user_slot_stats_dict = self.user_slot_stats_dict.get(self.selected_machine_name,
                                                                             {'experience': 0})
        self.machine_exp = current_machine_user_slot_stats_dict.get('experience')
        a = 50
        b = 100
        c = -150 - self.machine_exp
        self.machine_level = math.floor((-b + math.sqrt(b*b-4*a*c)) / (2 * a))
        self.next_exp = a * math.pow(self.machine_level+1, 2) + b*(self.machine_level+1) - 150

        if self.machine_level > 1:
            self.spins_left = math.floor(self.spins_left*4/3)

        #odd levels multi: 1: x1, 2: x10, 3: x100...
        if self.machine_level % 2 == 1: 
            self.multi = int(10**((self.machine_level-1) / 2))
        #even levels multi: 2: x3, 4: x30, 6: x300...
        else:
            self.multi = int(3*10**((self.machine_level-2) / 2))

    async def select_machine(self):
        """Function get get data for selected machine"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                rate_record = await connection.fetch("""SELECT symbol_rate FROM gray.slot_machine_rates where machine_name = $1 
                                                        ORDER BY symbol_idx ASC""", self.selected_machine_name)
                self.symbol_rate_list = [rate[0] for rate in rate_record]
                reward_record = await connection.fetch("""SELECT symbol_idx, symbol_reward_type, symbol_reward_value 
                                                       FROM gray.slot_machine_values where machine_name = $1
                                                       ORDER BY symbol_idx""",
                                                       self.selected_machine_name)
                await connection.execute("""INSERT INTO gray.user_slot_stats (discord_uid, machine_name, experience)
                                                            VALUES ($1, $2, $3) ON CONFLICT (discord_uid, machine_name) DO 
                                                            UPDATE SET experience = user_slot_stats.experience + $3""",
                                         self.author.id, self.selected_machine_name, 1)
                self.machine_exp += 1

                symbol_reward_list = []
                for reward in iter(reward_record):
                    try:
                        symbol_reward_list[reward[0] - 1].append((reward[1], reward[2]))
                    except IndexError:
                        symbol_reward_list.append([(reward[1], reward[2])])
                self.symbol_reward_list = symbol_reward_list
        self.selected = True

    async def get_jackpot(self, machine_name) -> list:
        """Function get get jackpot value for specified slot machine"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                jackpots = await connection.fetch("""SELECT bonus, minor_jackpot, major_jackpot FROM gray.slot_machine_info
                                                    where machine_name = $1""", machine_name)
        jackpot_list = []
        for reward in iter(jackpots):
            for jackpot in reward:
                jackpot_list.append(jackpot)
        return jackpot_list

    async def add_jackpot(self, machine_name, change: int):
        """Function to add to jackpot value for specified slot machine"""
        bonus, minor, major = await self.get_jackpot(machine_name)
        c_major = change * 10
        c_minor = change * 3
        c_bonus = change
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.slot_machine_info (machine_name, bonus, minor_jackpot, major_jackpot)
                                            VALUES ($1, $2, $3, $4) ON CONFLICT (machine_name) DO 
                                            UPDATE SET bonus = $2, minor_jackpot = $3, major_jackpot = $4""",
                                         machine_name, bonus + c_bonus, minor + c_minor, major + c_major)

    async def clear_jackpot(self, machine_name, jackpot_type):
        """Function to clear jackpot value for specified slot machine"""
        jackpot_list = await self.get_jackpot(machine_name)
        jackpot_list[jackpot_type - 1] = 0
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.slot_machine_info (machine_name, bonus, minor_jackpot, major_jackpot)
                                            VALUES ($1, $2, $3, $4) ON CONFLICT (machine_name) DO 
                                            UPDATE SET bonus = $2, minor_jackpot = $3, major_jackpot = $4""",
                                         machine_name, *jackpot_list)

    async def cash_out(self, c_amount: int, porg_multi: int, epic: int = 0):
        """Cashout users current slot position"""
        # final_c_amount = -1 * self.player_credits_total if -1 * c_amount > self.player_credits_total else c_amount
        if c_amount > 0:
            profit_change = c_amount * (1.1 ** porg_multi)
            if epic == 0:
                profit_change = profit_change * (1+self.bonus/100)
        else:
            profit_change = c_amount
        await self.economy.change_credits(self.author.id, profit_change)
        if self.total_spins > 0:
            await self.post_results()

    def get_final_slot(self):
        """Generate final slots and returns win/lose bool"""
        rates = self.symbol_rate_list
        cum_rates = np.cumsum(rates)
        result_list = [0, 0, 0]
        win_bool = True
        for slot in range(0, 3):
            rand_num = round(random.uniform(0.01, 1.00), 2)
            for cum_idx, threshold in enumerate(cum_rates):
                if rand_num <= threshold:
                    result_list[slot] = SlotMachine.slot_emoji_list[cum_idx + 1]
                    if cum_idx == 7:
                        win_bool = False
                    break
        self.final_slots = result_list
        self.win_bool = win_bool

    def get_result(self) -> int:
        """Get results of slot, returns epic"""
        c_coin, saber_multi, c_porg_multi, c_spin, epic, sith_penalty = 0, 0, 0, 0, 0, 0
        one_index = SlotMachine.slot_emoji_list.index(self.final_slots[0])
        two_index = SlotMachine.slot_emoji_list.index(self.final_slots[1])
        three_index = SlotMachine.slot_emoji_list.index(self.final_slots[2])
        slot_idx = [one_index, two_index, three_index]
        if slot_idx.count(8) == 3:
            epic = -1
            self.spins_left = 0
            c_coin -= self.epic_fail
            sith_penalty = math.floor(self.player_credits_total * .1) if self.selected_machine_name == 'SITH REVENGE' else 0
        else:
            if 9 in slot_idx:
                epic = slot_idx.count(9)
            for slot in slot_idx:
                rewards = self.symbol_reward_list[slot - 1]
                for reward in rewards:
                    r_type, r_value = reward
                    if not self.win_bool:
                        if slot != 8:
                            continue
                    if r_type == 'coin':
                        c_coin += r_value
                        if slot in range(1, 6):
                            saber_multi += 1
                    elif r_type == 'turn':
                        c_spin += r_value
                    elif r_type == 'multi':
                        c_porg_multi += r_value
        profit_change = (c_coin * ((2 ** saber_multi) - saber_multi)) * self.multi - sith_penalty
        self.profit += profit_change
        self.porg_multi += c_porg_multi
        self.spins_left += c_spin
        return epic

    async def check_epic(self, epic: int):
        """Check for epic and adjust jackpot/wallet"""
        if epic != 0:
            guild = self.economy.client.get_guild(helper.get_config('guild_id'))
            casino_channel = discord.utils.get(guild.text_channels, name='canto-bight')
            # 3 SITH
            if epic == -1:
                sid = SlotMachine.slot_emoji_list[8]
                sith_penalty = math.floor(self.player_credits_total*.1) if self.selected_machine_name == 'SITH REVENGE' else 0
                await self.add_jackpot(self.selected_machine_name, int((self.epic_fail + sith_penalty) / 100))
                await casino_channel.send(
                    f'{sid}{sid} {self.author.mention} LOST TO THE HIGHGROUND! -{self.epic_fail*self.multi + sith_penalty:,} Credits! {sid}{sid}')
            # GRAY
            elif epic > 0 and self.win_bool:
                await self.cash_out(self.current_jackpot[epic - 1], 0, epic)
                await self.clear_jackpot(self.selected_machine_name, epic)
                self.player_credits_total += self.current_jackpot[epic - 1]
                if epic == 3:
                    await casino_channel.send(
                        f'💰💰 @here {self.author.mention} WON THE JACKPOT OF {self.current_jackpot[epic - 1]:,}! 💰💰')
                elif epic == 2:
                    await self.ctx.send(f'You won the minor jackpot of {self.current_jackpot[epic-1]:,}!', delete_after=600)

    async def slot_reaction_waiter(self) -> str:
        """Async helper to await for reactions"""

        def check(r, u):
            # R = Reaction, U = User
            return u == self.ctx.author \
                   and str(r.emoji) in SlotMachine.action_emoji_list and r.message.id == self.sent_embed.id

        try:
            reaction, _ = await self.economy.client.wait_for('reaction_add', check=check, timeout=60)
        except asyncio.TimeoutError:
            # await self.ctx.send(f'{self.author.display_name} has run out of time on their slot machine.')
            return 'Timeout'
        return str(reaction.emoji)

    async def generate_slot_embed(self) -> discord.Embed:
        """Returns new embed object"""
        slot_state, slot_color = SlotMachine.state_list[self.state]
        if self.profit > -1:
            porg_string = f'x{1.1 ** self.porg_multi:.1f}'
        else:
            porg_string = f'(x{1.1 ** self.porg_multi:.1f})'
        slot_string = f'| {self.active_slots[0]} | {self.active_slots[1]} | {self.active_slots[2]} |'
        result_string = f'-- {slot_state} --'
        embed = discord.Embed(title=f'**LVL {self.machine_level} {self.selected_machine_name} x{self.multi}**',
                              description=f'EXP: {self.machine_exp} / {self.next_exp:.0f}'
                                          f'\nMajor Jackpot: {self.current_jackpot[2]:,}'
                                          f'\nMinor Jackpot: {self.current_jackpot[1]:,}'
                                          f'\nBonus: {self.current_jackpot[0]:,}',
                              color=slot_color)
        embed.set_author(name=self.author.display_name, icon_url=self.author.avatar_url)
        embed.set_thumbnail(url=self.selected_machine_icon)
        embed.add_field(name='------------------', value=slot_string, inline=False)
        embed.add_field(name='------------------', value=result_string, inline=False)
        embed.add_field(name='Profit', value=str(self.profit), inline=True)
        embed.add_field(name='Multi', value=porg_string, inline=True)
        embed.add_field(name='CardBonus', value=f'x{1+self.bonus/100:.2f}', inline=True)
        embed.add_field(name='Spins', value=str(self.spins_left), inline=True)
        embed.add_field(name='Wallet', value=f'{self.player_credits_total:,} C', inline=True)
        embed.set_footer(
            text=f'Play Cost: {self.selected_machine_cost*self.multi:,}\nConfused? $slot_info\nTime: %s'
                 % datetime.datetime.now().strftime('%Y-%b-%d %H:%M:%S'))
        return embed

    async def post_results(self):
        """Posts stats to db"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.slot_history (discord_uid, machine_name, timestamp, total_spins, profit, porg_multi, input_multi)
                                            VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                                         self.author.id, self.selected_machine_name, datetime.datetime.utcnow(),
                                         self.total_spins, self.profit, self.porg_multi, self.multi)

    async def start_up(self):
        """Start up the slot machine"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                info_record = await connection.fetch("""SELECT * FROM gray.slot_machine_info""")
                bonus = await connection.prepare("""
                                SELECT cards_db.rarity_code, cards_db.affiliation_name, SUM(deck.count) AS "count" FROM gray.user_deck AS deck 
                                INNER JOIN gray.sw_card_db AS cards_db on deck.code = cards_db.code WHERE deck.discord_uid = $1 GROUP BY 1,2""")
                columns = [a.name for a in bonus.get_attributes()]
                data = await bonus.fetch(self.author.id)
                user_slot_stats_record = await connection.fetch("""SELECT machine_name, experience FROM gray.user_slot_stats 
                                                                WHERE discord_uid = $1""", self.author.id)
                self.selected_machine_name = await connection.fetchval("""SELECT machine_name FROM gray.slot_history 
                                                                WHERE discord_uid = $1 ORDER BY "timestamp" DESC LIMIT 1""", self.author.id)

        def bonus_val(row):
            val = SlotMachine.card_bonus_dict.get(row['rarity_code'])
            return val

        bonus_data = pd.DataFrame(data, columns=columns)
        if not bonus_data.empty:
            bonus_data['bonus'] = bonus_data.apply(bonus_val, axis=1)
            bonus_data['bonus_total'] = bonus_data['bonus'] * bonus_data['count']
            self.player_bonus_dict = bonus_data.groupby(['affiliation_name']).agg({'bonus_total': "sum"}).T.to_dict('records')[0]

        self.machine_info_dict = helper.record_to_dict(info_record, 'machine_name')
        self.user_slot_stats_dict = helper.record_to_dict(user_slot_stats_record, 'machine_name')
        self.machine_count = len(list(self.machine_info_dict.keys()))
        self.machine_type_names = cycle(list(self.machine_info_dict.keys()))

        # Set the iterator to the selected position
        while self.selected_machine_name != next(self.machine_type_names):
            pass
        
        await self.setup_selected_machine()
        self.player_credits_total = await self.economy.get_credits(self.author.id)
        self.sent_embed = await self.ctx.send(embed=await self.generate_slot_embed())
        for e in SlotMachine.action_emoji_list:
            await self.sent_embed.add_reaction(e)

    async def play(self):
        """Play the slot machine"""
        # action_emoji_list = ['🕹️', '💰', '⬅', '➡', '🛑']
        while self.spins_left > 0:
            user_input = await self.slot_reaction_waiter()
            # ROLL
            if user_input == '🕹️':
                if not self.selected:
                    if self.player_credits_total < self.selected_machine_cost * self.multi and self.selected_machine_name == 'SITH REVENGE':
                        await self.ctx.send('You must be in good standing to spin this machine!')
                        break
                    await self.select_machine()
                    await self.add_jackpot(self.selected_machine_name, self.selected_machine_cost * self.multi)
                    await self.economy.change_credits(self.author.id, -1 * self.selected_machine_cost * self.multi)
                    self.player_credits_total -= self.selected_machine_cost * self.multi
                self.spins_left -= 1
                self.total_spins += 1
                self.current_jackpot = await self.get_jackpot(self.selected_machine_name)
                self.get_final_slot()
                await self.sent_embed.remove_reaction(user_input, self.author)
                await self.sent_embed.remove_reaction('⬅', self.sent_embed.author)
                await self.sent_embed.remove_reaction('➡', self.sent_embed.author)
                for slot in range(0, len(self.active_slots) + 1):
                    self.state = 2
                    if slot == len(self.active_slots):
                        if self.win_bool:
                            self.state = 3
                        else:
                            self.state = 1
                    if slot == 0:
                        self.active_slots = self.start_slots[:]
                    else:
                        await asyncio.sleep(1.5)
                        self.active_slots[slot - 1] = self.final_slots[slot - 1]
                    await self.sent_embed.edit(embed=await self.generate_slot_embed())
                epic = self.get_result()
                await self.sent_embed.edit(embed=await self.generate_slot_embed())
                # Check for epic result
                await self.check_epic(epic)
            # CASHOUT
            elif user_input == '💰':
                await self.sent_embed.remove_reaction(user_input, self.author)
                await self.cash_out(self.profit, self.porg_multi)
                self.player_credits_total = await self.economy.get_credits(self.author.id)
                self.profit, self.porg_multi = 0, 0
                self.state = 0
                await self.sent_embed.edit(embed=await self.generate_slot_embed())
            # Previous
            # elif user_input == '⬅' and not self.selected:
            elif user_input == '⬅':
                await self.sent_embed.remove_reaction(user_input, self.author)
                for _ in range(0, self.machine_count - 1):
                    self.selected_machine_name = next(self.machine_type_names)
                await self.setup_selected_machine()
                await self.sent_embed.edit(embed=await self.generate_slot_embed())
            # Next
            elif user_input == '➡':
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.selected_machine_name = next(self.machine_type_names)
                await self.setup_selected_machine()
                await self.sent_embed.edit(embed=await self.generate_slot_embed())
            # No response or STOP
            else:
                self.spins_left = 0

    async def close_out(self):
        """Close out the slot machine"""
        self.state = 4
        await self.cash_out(self.profit, self.porg_multi)
        self.player_credits_total = await self.economy.get_credits(self.author.id)
        await self.sent_embed.clear_reactions()
        await asyncio.sleep(1.5)
        await self.sent_embed.edit(embed=await self.generate_slot_embed())
        if self.ctx.channel.id != 838559622540427334:
            await asyncio.sleep(30)
            await self.sent_embed.delete()

    async def run(self):
        await self.start_up()
        await self.play()
        await self.close_out()


class Shop:
    action_emoji_list = ['⏮', '⬅', '➡', '⏭', '🛑']

    def __init__(self, economy, ctx):
        self.economy = economy
        self.ctx = ctx
        self.author = ctx.author

        self.shop_dict = None
        self.categories_max = None
        self.shop_category_cycle = None
        self.shop_category_list = None
        self.category_index = None

        self.selected_shop_category = None
        self.selected_shop_dict = None

        self.user_quantity_dict = {}

        self.sent_embed = None

    async def run(self):
        """Entry Point"""
        await self.open()
        await self.browse()
        await self.close_out()

    async def open(self):
        """Start up the shop"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                shop_record = await connection.fetch("SELECT * FROM gray.shop_items WHERE category NOT LIKE 'other%' ORDER BY item_idx ASC")
                user_quantity_record = await connection.fetch("SELECT item_code, quantity FROM gray.user_shop_quantity WHERE discord_uid = $1", self.author.id)
        shop_dict = {}
        for record in shop_record:
            category_name = ''
            item_name = ''
            for f, v in record.items():
                if f == 'category':
                    category_name = v
                elif f == 'name':
                    item_name = v
                # TODO: Keep subcategory in dictionary
                elif f == 'subcategory':
                    pass
                else:
                    try:
                        shop_dict[category_name][item_name].update({f: v})
                    except KeyError:
                        try:
                            shop_dict[category_name][item_name] = ({f: v})
                        except KeyError:
                            shop_dict[category_name] = {item_name: {f: v}}
        self.user_quantity_dict = helper.record_to_dict(user_quantity_record, 'item_code')
        self.shop_dict = shop_dict
        self.shop_category_list = list(shop_dict.keys())
        self.categories_max = len(self.shop_category_list)
        self.shop_category_cycle = cycle(list(shop_dict.keys()))
        self.selected_shop_category = next(self.shop_category_cycle)
        self.category_index = self.shop_category_list.index(self.selected_shop_category)
        self.selected_shop_dict = self.shop_dict.get(self.selected_shop_category)
        self.sent_embed = await self.ctx.send(embed=await self.generate_shop_embed())
        for e in Shop.action_emoji_list:
            await self.sent_embed.add_reaction(e)

    async def next_category(self, distance: int = 1):
        for _ in range(0, distance):
            self.selected_shop_category = next(self.shop_category_cycle)
        self.selected_shop_dict = self.shop_dict.get(self.selected_shop_category)
        self.category_index = self.shop_category_list.index(self.selected_shop_category)

    async def shop_reaction_waiter(self) -> str:
        """Async helper to await for reactions"""

        def check(r, u):
            # R = Reaction, U = User
            return u == self.ctx.author \
                   and str(r.emoji) in Shop.action_emoji_list and r.message.id == self.sent_embed.id

        try:
            reaction, _ = await self.economy.client.wait_for('reaction_add', check=check, timeout=60)
        except asyncio.TimeoutError:
            return 'Timeout'
        return str(reaction.emoji)

    async def generate_shop_embed(self) -> discord.Embed:
        """Returns new embed object"""
        embed = discord.Embed(title=f'**Trade Station** - {self.selected_shop_category.capitalize()}',
                              # TODO: Put description in DB by creating another table
                              description=f'Buy SW Trading Cards Here!',
                              color=0x0400FF)
        embed.set_author(name='Watto',
                         icon_url='https://media.discordapp.net/attachments/800431166997790790/839632354493595718/watto.jpg')
        embed.set_thumbnail(
            url='https://cdn.discordapp.com/attachments/800431166997790790/839635695475621898/poker-hand.png')
        item_name_list = []
        item_cost_list = []
        item_code_list = []
        for item_name in self.selected_shop_dict.keys():
            item_dict = self.selected_shop_dict.get(item_name)
            item_quantity = item_dict.get('quantity')
            item_code = item_dict.get('item_code')
            user_quantity = self.user_quantity_dict.get(item_code, {'quantity': 0}).get('quantity', 0)
            item_quantity = item_quantity + user_quantity if item_quantity + user_quantity > 0 else 0
            if item_name == 'Random Set':
                item_name = item_name.replace('Set', self.economy.current_set)
            elif item_name == 'Random Faction':
                item_name = item_name.replace('Faction', self.economy.current_faction)
            elif item_name == 'Random Affiliation':
                item_name = item_name.replace('Affiliation', self.economy.current_affiliation)
            item_name_list.append(f"{item_dict.get('emoji')} {item_quantity:,}x{item_name}")
            item_cost_list.append(f"{item_dict.get('cost'):,}")
            item_code_list.append(f"{item_dict.get('item_code')}")
        embed.add_field(name='Item', value='\n'.join(item_name_list))
        embed.add_field(name='Cost', value='\n'.join(item_cost_list))
        embed.add_field(name='Code', value='\n'.join(item_code_list))
        _, time_left = await self.economy.check_cd(775808657199333376, 'RESTOCK')
        _, time_left_minor = await self.economy.check_cd(775808657199333376, 'RESTOCK_MINOR')
        major_text = 'Restocking' if time_left < datetime.timedelta(0) else str(time_left).split('.')[0]
        minor_text = 'Restocking' if time_left_minor < datetime.timedelta(0) else str(time_left_minor).split('.')[0]
        embed.set_footer(text=f"Major Restock: {major_text}"
                              f"\nMinor Restock: {minor_text}")
        return embed

    async def browse(self):
        """Browse the shop"""
        while True:
            user_input = await self.shop_reaction_waiter()
            # First
            if user_input == Shop.action_emoji_list[0] and self.category_index != 0:
                await self.sent_embed.remove_reaction(user_input, self.author)
                await self.next_category(self.categories_max - self.category_index)
                await self.sent_embed.edit(embed=await self.generate_shop_embed())
            # Backwards
            elif user_input == Shop.action_emoji_list[1]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                if self.category_index != 0:
                    await self.next_category(self.categories_max - 1)
                    await self.sent_embed.edit(embed=await self.generate_shop_embed())
            # Forward
            elif user_input == Shop.action_emoji_list[2]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                if self.category_index < self.categories_max:
                    await self.next_category()
                    await self.sent_embed.edit(embed=await self.generate_shop_embed())
            # Last
            elif user_input == Shop.action_emoji_list[3] and self.category_index != self.categories_max:
                await self.sent_embed.remove_reaction(user_input, self.author)
                await self.next_category(self.categories_max - self.category_index - 1)
                await self.sent_embed.edit(embed=await self.generate_shop_embed())
            # No response or STOP
            else:
                break

    async def close_out(self):
        """Close out the shop"""
        await self.sent_embed.clear_reactions()
        await asyncio.sleep(30)
        await self.sent_embed.delete()


class Deck:
    deck_action_emoji_list = ['⏪', '◀', '⬆', '👁', '⬇', '▶', '⏩', '🛑']
    card_action_emoji_list = ['↩', '◀', '▶', '🛑']
    card_bonus_dict = {'S': 1, 'C': 2, 'U': 8, 'R': 20, 'L': 50}

    def __init__(self, economy, ctx, user: discord.Member, affiliation_codes: list, rarity_codes: list, card_codes: list, missing: bool):
        self.empty = False  # If the users deck is completely empty
        self.is_card = False

        self.economy = economy
        self.ctx = ctx
        self.author = ctx.author
        self.target = user
        self.affiliation_codes = affiliation_codes
        self.rarity_codes = rarity_codes
        self.card_codes = card_codes
        self.missing = missing

        self.user_deck_dict = {}  # gray.user_deck
        self.db_select_dict = {}  # gray.sw_card_db
        self.set_list = []  # Alphabetically sorted set list

        self.current_set_idx = 0
        self.current_set_dict = {}  # Dictionary that holds all cards of current set
        self.current_set_name = None
        self.current_set_code = None  # Code of current set
        self.current_set_page_idx = 0  # Index of page of current set
        self.current_set_max_page = 0  # Index of set in deck
        self.current_card_idx = 0  # Index of currently displayed card
        self.current_display_names = []  # 10 cards names currently being displayed
        self.current_display_code = []  # 10 cards codes currently being displayed
        self.current_card_counts = []  # 10 card quantities held

        self.sent_embed = None  # Sent embed to update on emoji reaction

    async def start(self):
        """Pull card info from database"""
        async with self.economy.client.pool.acquire() as connection:
            async with connection.transaction():
                user_deck_record = None
                if len(self.card_codes) > 0:
                    user_deck_record = await connection.fetch(
                        """SELECT deck.code, deck.count, first_acquired FROM gray.user_deck AS deck 
                        INNER JOIN gray.sw_card_db AS cards_db on deck.code = cards_db.code 
                        WHERE deck.discord_uid = $1 AND deck.count > 0 AND deck.code = ANY($2::text[])""",
                        self.target.id, self.card_codes)
                else:
                    user_deck_record = await connection.fetch(
                        """SELECT deck.code, deck.count, first_acquired FROM gray.user_deck AS deck 
                        INNER JOIN gray.sw_card_db AS cards_db on deck.code = cards_db.code 
                        WHERE deck.discord_uid = $1 AND deck.count > 0 AND 
                        cards_db.affiliation_code = ANY($2::text[]) AND cards_db.rarity_code = ANY($3::text[])""",
                        self.target.id, 
                        self.affiliation_codes if self.affiliation_codes else self.economy.affiliation_codes_list, 
                        self.rarity_codes if self.rarity_codes else self.economy.card_rarity_list)

                # Get the card codes you don't have
                if self.missing:
                    user_deck_record = await connection.fetch(
                        """SELECT code FROM gray.sw_card_db 
                        WHERE affiliation_code = ANY($1::text[]) AND rarity_code = ANY($2::text[]) AND code <> ALL($3::text[])""",
                        self.affiliation_codes if self.affiliation_codes else self.economy.affiliation_codes_list, 
                        self.rarity_codes if self.rarity_codes else self.economy.card_rarity_list,
                        [card['code'] for card in user_deck_record])

                for card in user_deck_record:
                    card_code = ''
                    for f, v in card.items():
                        if f == 'code':
                            card_code = v
                            if self.missing:
                                self.user_deck_dict[card_code] = {'count': 0, 'first_acquired': None}
                        else:
                            try:
                                self.user_deck_dict[card_code].update({f: v})
                            except KeyError:
                                self.user_deck_dict[card_code] = {f: v}
                card_list = list(self.user_deck_dict.keys())
                if len(card_list) == 0:
                    self.empty = True
                    return

                db_select_record = await connection.fetch(
                    """SELECT set_code, * FROM gray.sw_card_db WHERE code = ANY($1::text[])""", card_list)
                self.db_select_dict = {}
                for record in db_select_record:
                    set_code = ''
                    card_code = ''
                    for f, v in record.items():
                        if f == 'set_code':
                            set_code = v
                        elif f == 'code':
                            card_code = v
                        else:
                            try:
                                self.db_select_dict[set_code][card_code].update({f: v})
                            except KeyError:
                                try:
                                    self.db_select_dict[set_code][card_code] = ({f: v})
                                except KeyError:
                                    self.db_select_dict[set_code] = {card_code: {f: v}}
        self.set_list = sorted(list(self.db_select_dict.keys()))
        self.current_set_code = self.set_list[self.current_set_idx]
        self.current_set_dict = self.db_select_dict.get(self.set_list[self.current_set_idx])

        # If there's only one card to show, show directly the card embed without reactions
        self.get_current_deck_info()
        if len(self.user_deck_dict.keys()) == 1:
            self.is_card = 1
            self.sent_embed = await self.ctx.send(embed=await self.generate_card_embed())
        else:
            self.sent_embed = await self.ctx.send(embed=await self.generate_deck_embed())
            for e in Deck.deck_action_emoji_list:
                await self.sent_embed.add_reaction(e)

    def get_current_deck_info(self):
        keys = self.current_set_dict.keys()
        self.current_set_max_page = math.ceil(len(list(self.current_set_dict.keys())) / 10)
        self.current_set_name = self.current_set_dict[next(iter(self.current_set_dict))].get('set_name')
        self.current_display_names = [self.current_set_dict.get(code).get('name') for idx, code in enumerate(keys) if
                                      (10 * self.current_set_page_idx <= idx < 10 * (self.current_set_page_idx + 1))]
        self.current_display_code = [code for idx, code in enumerate(keys) if
                                     (10 * self.current_set_page_idx <= idx < 10 * (self.current_set_page_idx + 1))]
        self.current_card_counts = [self.user_deck_dict.get(code).get('count') for idx, code in enumerate(keys) if
                                    (10 * self.current_set_page_idx <= idx < 10 * (self.current_set_page_idx + 1))]

    async def generate_deck_embed(self) -> discord.Embed:
        """Generate embed that shows entire deck by set"""
        current_i_display_names = self.current_display_names[:]
        current_i_display_names[self.current_card_idx] = f' ▶ {self.current_display_names[self.current_card_idx]}'
        for idx, name in enumerate(current_i_display_names):
            if self.current_card_counts[idx] > 1:
                current_i_display_names[idx] = f'{current_i_display_names[idx]} ({self.current_card_counts[idx]}x {self.current_display_code[idx]})'
            else:
                current_i_display_names[idx] = f'{current_i_display_names[idx]} ({self.current_display_code[idx]})'
        card_names_string = '\n'.join(current_i_display_names)

        embed = discord.Embed(title='Set', description=self.current_set_name, colour=self.ctx.author.colour)
        embed.set_author(name=self.target.display_name, icon_url=self.target.avatar_url)
        if self.missing:
            embed.add_field(name='Missing cards', value=card_names_string, inline=True)
        else:
            embed.add_field(name='Cards', value=card_names_string, inline=True)
        embed.set_footer(
            text=f'Page {self.current_set_page_idx + 1}/{self.current_set_max_page} of Set {self.current_set_idx + 1}/{len(self.set_list)}')
        return embed

    async def generate_card_embed(self) -> discord.Embed:
        """Generate embed that shows specific card"""
        current_card_code = self.current_display_code[self.current_card_idx]
        current_card_dict = self.current_set_dict.get(current_card_code)
        first_acquired = self.user_deck_dict.get(current_card_code).get('first_acquired')
        rarity_name = f"{current_card_dict.get('rarity_name')}"
        rarity_bonus = Deck.card_bonus_dict.get(current_card_dict.get('rarity_code'))
        slot_effect = f"+{rarity_bonus}% on {current_card_dict.get('affiliation_name')} slots."
        game_effect = current_card_dict.get('game_effect')
        effect = f'{slot_effect}\n{game_effect}' if game_effect is not None else slot_effect
        position = current_card_dict.get('position')
        set_name = current_card_dict.get('set_name')
        faction_name = current_card_dict.get('faction_name')
        color = 0x7C8E92
        if faction_name == 'Command':
            color = 0xEA040B
        elif faction_name == 'Rogue':
            color = 0xF2FA3B
        elif faction_name == 'Force':
            color = 0x3B58FA
        imagesrc = current_card_dict.get('imagesrc')
        embed = discord.Embed(title=rarity_name, description=effect, colour=color)
        embed.set_image(url=imagesrc)
        if first_acquired is None:
            embed.set_footer(
                text=f"{current_card_code}\n{position} of {set_name}\nYou do not own this card")
        else:
            embed.set_footer(
                text=f"{current_card_code}\n{position} of {set_name}\nFirst Acquired {first_acquired.strftime('%Y-%b-%d %H:%M:%S')}")
        return embed

    async def deck_reaction_waiter(self) -> str:
        """Async helper to await for reactions"""

        def check(r, u):
            emoji_list = Deck.deck_action_emoji_list + Deck.card_action_emoji_list
            # R = Reaction, U = User
            return u == self.ctx.author \
                   and str(r.emoji) in emoji_list \
                   and r.message.id == self.sent_embed.id

        try:
            reaction, _ = await self.economy.client.wait_for('reaction_add', check=check, timeout=60)
        except asyncio.TimeoutError:
            return 'Timeout'
        return str(reaction.emoji)

    def previous_set(self):
        if self.current_set_idx == 0:
            self.current_set_idx = len(self.set_list)
        self.current_set_idx -= 1
        self.current_set_dict = self.db_select_dict.get(self.set_list[self.current_set_idx])
        self.current_set_page_idx = 0
        self.current_card_idx = 0
        self.get_current_deck_info()

    def next_set(self):
        if self.current_set_idx == len(self.set_list) - 1:
            self.current_set_idx = -1
        self.current_set_idx += 1
        self.current_set_dict = self.db_select_dict.get(self.set_list[self.current_set_idx])
        self.current_set_page_idx = 0
        self.current_card_idx = 0
        self.get_current_deck_info()

    def previous_page(self):
        if self.current_set_page_idx == 0:
            self.current_set_page_idx = self.current_set_max_page
        self.current_set_page_idx -= 1
        self.current_card_idx = 0
        self.get_current_deck_info()

    def next_page(self):
        if self.current_set_page_idx == self.current_set_max_page - 1:
            self.current_set_page_idx = -1
        self.current_set_page_idx += 1
        self.current_card_idx = 0
        self.get_current_deck_info()

    def up_page(self):
        if self.current_card_idx == 0:
            self.current_card_idx = len(self.current_display_names)
        self.current_card_idx -= 1

    def down_page(self):
        if self.current_card_idx == len(self.current_display_names) - 1:
            self.current_card_idx = -1
        self.current_card_idx += 1

    async def open(self):
        """Open up deck embed"""
        while True:
            user_input = await self.deck_reaction_waiter()
            # Previous Set - Loopable
            if user_input == Deck.deck_action_emoji_list[0]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.previous_set()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Previous Page - Loopable
            elif user_input == Deck.deck_action_emoji_list[1] and not self.is_card:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.previous_page()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Up - Loopable
            elif user_input == Deck.deck_action_emoji_list[2]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.up_page()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Card
            elif user_input == Deck.deck_action_emoji_list[3]:
                await self.sent_embed.clear_reactions()
                await self.sent_embed.edit(embed=await self.generate_card_embed())
                for e in Deck.card_action_emoji_list:
                    await self.sent_embed.add_reaction(e)
                self.is_card = True
            # Down - Loopable
            elif user_input == Deck.deck_action_emoji_list[4]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.down_page()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Next Page - Loopable
            elif user_input == Deck.deck_action_emoji_list[5] and not self.is_card:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.next_page()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Next Set - Loopable
            elif user_input == Deck.deck_action_emoji_list[6]:
                await self.sent_embed.remove_reaction(user_input, self.author)
                self.next_set()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
            # Return
            elif user_input == Deck.card_action_emoji_list[0]:
                await self.sent_embed.clear_reactions()
                await self.sent_embed.edit(embed=await self.generate_deck_embed())
                for e in Deck.deck_action_emoji_list:
                    await self.sent_embed.add_reaction(e)
                self.is_card = False
            # Previous Card
            elif user_input == Deck.card_action_emoji_list[1] and self.is_card:
                await self.sent_embed.remove_reaction(user_input, self.author)
                if self.current_card_idx == 0:
                    if self.current_set_page_idx == 0:
                        self.previous_set()
                        self.previous_page()
                        self.up_page()
                    else:
                        self.previous_page()
                        self.up_page()
                else:
                    self.up_page()
                await self.sent_embed.edit(embed=await self.generate_card_embed())
            # Next Card
            elif user_input == Deck.card_action_emoji_list[2] and self.is_card:
                await self.sent_embed.remove_reaction(user_input, self.author)
                if self.current_card_idx == len(self.current_display_names) - 1:
                    if self.current_set_page_idx == self.current_set_max_page - 1:
                        self.next_set()
                    else:
                        self.next_page()
                else:
                    self.down_page()
                await self.sent_embed.edit(embed=await self.generate_card_embed())
            # No response or STOP
            else:
                break

    async def close_out(self):
        """Close out the deck"""
        await self.sent_embed.clear_reactions()
        await asyncio.sleep(30)
        await self.sent_embed.delete()

    async def run(self):
        """Entry Point"""
        await self.start()
        if not self.empty:
            await self.open()
            await self.close_out()
        else:
            await self.ctx.send('No cards found.')


class EconomyLB(menus.ListPageSource):
    def __init__(self, ctx, data):
        self.ctx = ctx
        super().__init__(data, per_page=10)

    async def write_page(self, offset, fields=None):
        if fields is None:
            fields = []
        len_data = len(self.entries)
        embed = discord.Embed(title="Leaderboard", description="Galactic Points", colour=self.ctx.author.colour)
        embed.set_thumbnail(url='https://media.discordapp.net/attachments/800431166997790790/840009740855934996/gray_squadron_logo.png')
        embed.set_footer(text=f"{offset:,} - {min(len_data, offset+self.per_page-1):,} of {len_data:,}.")
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        return embed

    async def format_page(self, menu, entries):
        offset = (menu.current_page * self.per_page) + 1
        fields = []
        table = "\n".join(f"{idx+offset}. {self.ctx.guild.get_member(entry[0]).display_name} - {entry[1]:,} Points" for idx, entry in enumerate(entries))
        fields.append(("Rank", table))
        return await self.write_page(offset, fields)


def setup(client):
    client.add_cog(Economy(client))

# *Rarity_Name
# Starter - White
# Common - Green
# Uncommon - Blue
# Rare - Red
# Legendary - Yellow
#
# -Rotating Faction - Teal
# *Faction_Name
# Command
# Rogue
# General
# Force
#
# -Rotating Affiliation - Orange
# *Affiliation_Name
# Hero
# Neutral
# Villain
#
# -Rotating Set - Pink
