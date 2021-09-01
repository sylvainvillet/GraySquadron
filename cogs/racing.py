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
from datetime import date, time, datetime, timezone, timedelta

from utils import helper


class Racing(commands.Cog):
    # Bonus constants
    finish_a_race_bonus = 100
    participation_streak_bonus = 2
    finishing_streak_bonus = 4
    first_in_class_bonus = 40
    podium_bonuses = [100, 50, 25]
    kill_bonus = 20
    disable_bonus = 10
    best_lap_bonus = 20
    most_damage_bonus = 20

    global_damage_factor = 1.0

    unstable_engine_damage = 500
    unstable_engine_range = 1000

    min_entry_bet_credits = 100
    base_jackpot = 10000

    # Progress bar max values
    max_hull = 3300
    max_shield = 1560
    max_speed = 221
    max_acceleration = 384
    max_maneuverability = 110
    max_dps = 1920

    race_time_utc = time(hour=20)

    def __init__(self, client):
        self.data_loaded = False
        self.race_reminder_sent = False
        self.bot_discord_uid = helper.get_config('bot_discord_uid')
        self.client = client
        self.guild = client.get_guild(helper.get_config('guild_id'))
        self.racing_channel = discord.utils.get(self.guild.text_channels, name='racing-results')
        self.race_task.start()

    def cog_unload(self):
        self.race_task.cancel()

    async def load_fixed_data(self):
        if not self.data_loaded:
            self.maps_info = await self.get_maps_info()
            self.maps_info_dict = helper.record_to_dict(self.maps_info, 'map_id')
            self.components_info = await self.get_components_info()
            self.components_info_dict = helper.record_to_dict(self.components_info, 'component_id')
            self.ships_info = await self.get_ships_info()
            self.ships_info_dict = helper.record_to_dict(self.ships_info, 'ship_id')
            self.economy = self.client.get_cog('Economy')
            self.data_loaded = True

    async def get_race_info(self) -> list:
        """Gets the current race info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetchrow("""SELECT * FROM gray.racing_races ORDER BY race_id DESC LIMIT 1""")

    async def get_races_info(self, limit: int = 1) -> list:
        """Gets the last X races info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_races ORDER BY race_id DESC LIMIT $1""", limit)

    async def race_registration(self, race_id: int, discord_uid: int, entry_bet_credits: int, ship_id: int, already_registered: bool = False):
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                if already_registered:
                    return await connection.fetch("""UPDATE gray.racing_results 
                                                SET entry_bet_credits=$1, ship_id=$2
                                                WHERE discord_uid=$3 AND race_id=$4""",
                                             entry_bet_credits, ship_id, discord_uid, race_id)
                else:
                    return await connection.fetch("""INSERT INTO gray.racing_results (discord_uid, race_id, entry_bet_credits, ship_id)
                                                VALUES ($1, $2, $3, $4)""",
                                             discord_uid, race_id, entry_bet_credits, ship_id)

    async def get_race_result(self, race_id) -> list:
        """Gets all the races info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_results 
                    WHERE gray.racing_results.race_id = $1""", race_id)

    async def get_user_race_results(self, discord_uid) -> list:
        """Gets all the race results for a user from newest to oldest"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_results 
                    WHERE discord_uid = $1
                    ORDER BY race_id DESC""", discord_uid)

    async def get_leaderboard(self) -> list:
        """Gets all the race results for a user from newest to oldest"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT discord_uid, SUM(bonus) AS total_points FROM gray.racing_results 
                    WHERE bonus is not NULL AND discord_uid <> $1
                    GROUP BY discord_uid
                    ORDER BY total_points DESC""",
                    self.bot_discord_uid)

    async def get_maps_info(self) -> list:
        """Gets all the racing maps info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_maps ORDER BY map_id ASC""")

    async def set_lap_record(self, map_id: int, best_lap: float, best_lap_uid: int):
        """Gets all the racing maps info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetch("""UPDATE gray.racing_maps 
                                          SET lap_record=$1, lap_record_uid=$2
                                          WHERE map_id=$3""",
                                          best_lap, best_lap_uid, map_id)

    def get_map_lap_length(self, map_info) -> int:
        """Gets the length of the lap"""
        return map_info['corners'] * (map_info['speed_factor'] + map_info['maneuverability_factor']) * map_info['distance_factor']

    async def get_components_info(self) -> list:
        """Gets all the racing maps info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_components ORDER BY component_id ASC""")

    async def get_ships_info(self) -> list:
        """Gets all the racing maps info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                return await connection.fetch("""SELECT * FROM gray.racing_ships ORDER BY ship_id ASC""")

    def get_components_bonus(self, ship_info, key) -> int:
        """Get the bonus value depending on loadout for key"""
        hull_component = self.components_info_dict.get(ship_info['hull_component_id'])
        shield_component = self.components_info_dict.get(ship_info['shield_component_id'])
        engine_component = self.components_info_dict.get(ship_info['engine_component_id'])
        weapon_component = self.components_info_dict.get(ship_info['primary_weapon_component_id'])
        if shield_component:
            return hull_component[key] + shield_component[key] + engine_component[key] + weapon_component[key]
        else:
            return hull_component[key] + engine_component[key] + weapon_component[key]

    def get_ship_spec(self, ship_info, key) -> (int, int, int):
        """Get the hull, shield, speed, acceleration and maneuverability values depending on loadout
        Returns the base value, the offset and the sum of both"""
        bonus_percent = self.get_components_bonus(ship_info, f'{key}_bonus')
        base_value = ship_info[key]
        offset = base_value * (bonus_percent / 100)
        return base_value, offset, base_value + offset

    def get_primary_weapon_info(self, ship_info) -> (int, str, int):
        """Get the primary weapon
        Returns the DPS, weapon type and range"""
        primary_weapon_info = self.components_info_dict.get(ship_info['primary_weapon_component_id'])
        dps = ship_info['primary_weapon_dps'] if primary_weapon_info['primary_weapon_dps'] is None else primary_weapon_info['primary_weapon_dps']
        return dps, primary_weapon_info['sub_type'], primary_weapon_info['primary_weapon_range']

    async def get_user_hangar_info(self, discord_uid: int) -> list:
        """Gets the user's ships info"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                user_hangar = await connection.fetch("""SELECT * FROM gray.user_racing_loadouts
                                WHERE discord_uid = $1""", discord_uid)

                # New user, initialize hangar with default values
                if not user_hangar:
                    for ship_info in self.ships_info:                    
                        await connection.execute("""INSERT INTO gray.user_racing_loadouts 
                            (discord_uid, ship_id, primary_weapon_component_id, hull_component_id, shield_component_id, engine_component_id)
                                                    VALUES ($1, $2, $3, $4, $5, $6)""",
                            discord_uid, ship_info['ship_id'], ship_info['default_primary_weapon_component_id'], ship_info['default_hull_component_id'], 
                            ship_info['default_shield_component_id'], ship_info['default_engine_component_id'])

                return await connection.fetch("""SELECT * FROM gray.racing_ships AS racing_ships
                                LEFT JOIN gray.user_racing_loadouts AS user_hangar
                                ON racing_ships.ship_id = user_hangar.ship_id
                                WHERE discord_uid = $1 ORDER BY racing_ships.ship_id ASC""", discord_uid)

    async def save_user_subscription_to_race_report(self, discord_uid: int, subscribe: bool):
        """Save the user subscription to the race report.
        Creates the entry if it doesn't exists yet."""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""UPDATE gray.user_racing_info 
                    SET personal_report_subscription = $2
                    WHERE discord_uid = $1""",
                    discord_uid, subscribe)

    async def is_user_subscribed_to_race_report(self, discord_uid: int) -> bool:
        """Returns true if the user is subscribed to the race report.
        Creates the entry if it doesn't exists yet."""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                is_subscribed = await connection.fetchval("""SELECT personal_report_subscription 
                                FROM gray.user_racing_info
                                WHERE discord_uid = $1
                                LIMIT 1""", discord_uid)

                # New user, initialize with default values
                if is_subscribed is None:
                    await connection.execute("""INSERT INTO gray.user_racing_info 
                        (discord_uid, personal_report_subscription)
                        VALUES ($1, $2)""",
                        discord_uid, True)
                    is_subscribed = True

                return is_subscribed

    async def save_loadout(self, ship_info):
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""UPDATE gray.user_racing_loadouts 
                    SET primary_weapon_component_id = $3, hull_component_id = $4, shield_component_id = $5, engine_component_id = $6
                    WHERE discord_uid = $1 AND ship_id = $2""",
                    ship_info['discord_uid'], ship_info['ship_id'], ship_info['primary_weapon_component_id'], ship_info['hull_component_id'], 
                    ship_info['shield_component_id'], ship_info['engine_component_id'])

    async def save_result_in_db(self, race_id: int, result: dict):
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                for discord_uid in result:
                    await connection.execute("""UPDATE gray.racing_results 
                        SET position = $3, is_alive = $4, bonus = $5, jackpot = $6,
                        gain_credits = $7, laps_completed = $8, final_time = $9, best_lap = $10, 
                        shield_damage_dealt = $11, hull_damage_dealt = $12, ioning_damage_dealt = $13, kills = $14, 
                        disables = $15, is_first_in_class = $16, is_race_best_lap = $17, is_race_most_damage = $18,
                        participation_streak = $19, finishing_streak = $20
                        WHERE race_id = $1 AND discord_uid = $2""",
                        race_id, discord_uid,
                        result[discord_uid]['position'], result[discord_uid]['is_alive'], result[discord_uid]['total_bonus'], result[discord_uid]['jackpot'],
                        result[discord_uid]['gain_credits'], result[discord_uid]['laps_completed'], result[discord_uid]['final_time'], result[discord_uid]['best_lap'],
                        result[discord_uid]['shield_damage_dealt'], result[discord_uid]['hull_damage_dealt'], result[discord_uid]['ioning_damage_dealt'], result[discord_uid]['kills'],
                        result[discord_uid]['disables'], result[discord_uid]['first_in_class_bonus'] > 0, 
                        result[discord_uid]['best_lap_bonus'] > 0, 
                        result[discord_uid]['most_damage_bonus'] > 0,
                        result[discord_uid]['participation_streak'], result[discord_uid]['finishing_streak'])

    def simulate_sector(self, map_info, ship_info) -> (float, float):
        '''Returns the sector time and average speed'''
        _, _, corner_speed = self.get_ship_spec(ship_info, 'maneuverability')
        _, _, top_speed = self.get_ship_spec(ship_info, 'speed')
        _, _, acceleration = self.get_ship_spec(ship_info, 'acceleration')
        top_speed_dist = map_info['speed_factor'] * map_info['distance_factor']
        acc_dec_corner_speed_dist = map_info['maneuverability_factor'] * map_info['distance_factor']  
        sector_dist = top_speed_dist + acc_dec_corner_speed_dist

        acceleration_time = (top_speed - corner_speed) / acceleration
        acceleration_avg_speed = (top_speed - corner_speed) / 2
        acceleration_dist = acceleration_time * acceleration_avg_speed
        corner_speed_dist = acc_dec_corner_speed_dist - 2 * acceleration_dist
        if corner_speed_dist < 0:
            corner_speed_dist = 0

        avg_speed = (2 * acceleration_avg_speed * acceleration_dist 
            + top_speed * top_speed_dist 
            + corner_speed * corner_speed_dist) / sector_dist
        sector_time = 2 * acceleration_time + top_speed_dist / top_speed + corner_speed_dist / corner_speed

        # For debug
        #print('dist: a: {:.1f} s: {:.1f} c: {:.1f}'.format(acceleration_dist, top_speed_dist, corner_speed_dist))
        #print('Map: {} ship: {} time: a: {:.1f} s: {:.1f} c: {:.1f} total:'.format(map_info['display_name'], ship_info['display_name'], acceleration_time, top_speed_dist / top_speed, corner_speed_dist / corner_speed, sector_time))

        return sector_time, avg_speed

    async def simulate_race(self, race_info: dict, entry_list_dict: dict, map_info: dict) -> (dict, dict):
        def simulate_bonk(result, discord_uid: int, lap: int, previous_lap_hull: int) -> bool:
            """ Simulate a contact with the map, returns True if dead"""
            bonk_damage = random.randint(200, 800)
            #print('Bonk! Damage:', bonk_damage, 'Lap:', lap, 'uid:', discord_uid)
            
            if previous_lap_hull <= bonk_damage:
                result[discord_uid][lap]['hull'] = 0
                result[discord_uid]['is_alive'] = False
                return True
            else:
                result[discord_uid][lap]['hull'] = previous_lap_hull - bonk_damage
                return False

        def apply_damage(result, attacker_discord_uid: int, victim_discord_uid: int, damage: float, lap: int, key: str, weapon_type: str) -> float:
            """ Apply damage to either hull or shield, returns the remaining damage"""
            loops = 1
            if key == 'shield':
                damage_received_multiplier = 1 + result[victim_discord_uid]['damage_received_bonus'] / 100
            else:
                damage_received_multiplier = 1

            # If the ship is stripped, ion primary dealt damages both to the hull ifself (5% DPS)
            # and to the "ioning" value to disable the ship
            if weapon_type == 'ion' and key == 'hull':
                ion_damage = damage
                damage = damage * 0.05
                loops = 2

            for i in range(0, loops):
                if damage * damage_received_multiplier >= result[victim_discord_uid][lap][key] > 0:
                    result[attacker_discord_uid][f'{key}_damage_dealt'] += result[victim_discord_uid][lap][key]
                    damage -= result[victim_discord_uid][lap][key] / damage_received_multiplier
                    result[victim_discord_uid][lap][key] = 0
                elif result[victim_discord_uid][lap][key] > damage * damage_received_multiplier:
                    result[victim_discord_uid][lap][key] -= damage * damage_received_multiplier
                    result[attacker_discord_uid][f'{key}_damage_dealt'] += damage
                    damage = 0

                # Setup the second loop for ioning
                if loops == 2:
                    key = 'ioning'
                    damage = ion_damage

            return damage

        corners = map_info['corners']
        pe_factor = map_info['pe_factor']
        result = {}
        for discord_uid in entry_list_dict:
            user_hangar_dict = helper.record_to_dict(await self.get_user_hangar_info(discord_uid), 'ship_id')
            ship_info = user_hangar_dict.get(entry_list_dict[discord_uid]['ship_id'])
            sector_time, _ = self.simulate_sector(map_info, ship_info)
            ideal_lap_time = sector_time * corners

            # Race info
            result[discord_uid] = {}
            result[discord_uid]['best_lap'] = None
            result[discord_uid]['laps_completed'] = 0
            result[discord_uid]['final_time'] = 0
            result[discord_uid]['ideal_lap_time'] = ideal_lap_time
            result[discord_uid]['is_alive'] = True
            result[discord_uid]['shield_damage_dealt'] = 0
            result[discord_uid]['hull_damage_dealt'] = 0
            result[discord_uid]['ioning_damage_dealt'] = 0
            result[discord_uid]['kills'] = []
            result[discord_uid]['disables'] = []

            # Ship info
            _, _, result[discord_uid]['hull'] = self.get_ship_spec(ship_info, 'hull')
            _, _, result[discord_uid]['shield'] = self.get_ship_spec(ship_info, 'shield')
            if result[discord_uid]['shield'] > 0:
                result[discord_uid]['shield_regen_bonus'] = self.components_info_dict[ship_info['shield_component_id']]['shield_regen_bonus']
                result[discord_uid]['shield_type'] = self.components_info_dict[ship_info['shield_component_id']]['sub_type']
                result[discord_uid]['damage_received_bonus'] = self.components_info_dict[ship_info['shield_component_id']]['damage_received_bonus']
            else:
                result[discord_uid]['shield_regen_bonus'] = 0
                result[discord_uid]['shield_type'] = None
                result[discord_uid]['damage_received_bonus'] = 0
            _, _, result[discord_uid]['speed'] = self.get_ship_spec(ship_info, 'speed')
            _, _, result[discord_uid]['maneuverability'] = self.get_ship_spec(ship_info, 'maneuverability')
            result[discord_uid]['engine_type'] = self.components_info_dict[ship_info['engine_component_id']]['sub_type']
            result[discord_uid]['class'] = ship_info['class']

            # Weapon info
            primary_weapon_info = self.components_info_dict[ship_info['primary_weapon_component_id']]
            if primary_weapon_info['primary_weapon_dps'] is None:
                result[discord_uid]['primary_weapon_dps'] = ship_info['primary_weapon_dps']
            else:
                result[discord_uid]['primary_weapon_dps'] = primary_weapon_info['primary_weapon_dps']
            result[discord_uid]['primary_weapon_type'] = primary_weapon_info['sub_type']
            result[discord_uid]['primary_weapon_range'] = primary_weapon_info['primary_weapon_range']

            # Initialize race start
            result[discord_uid][0] = {}
            result[discord_uid][0]['total_time'] = 0
            result[discord_uid][0]['hull'] = result[discord_uid]['hull']
            result[discord_uid][0]['ioning'] = result[discord_uid]['hull']
            result[discord_uid][0]['shield'] = result[discord_uid]['shield']

            # Initialize race events (kills, crashes, disables, ...)
            events = {}
            events[0] = []

        for lap in range(1, race_info['laps'] + 1):
            events[lap] = {}
            for discord_uid in entry_list_dict:
                if result[discord_uid]['is_alive']:
                    result[discord_uid][lap] = {}
                    previous_lap_hull = result[discord_uid][lap - 1]['hull']
                    result[discord_uid][lap]['hull'] = previous_lap_hull
                    result[discord_uid][lap]['shield'] = result[discord_uid][lap - 1]['shield']
                    result[discord_uid][lap]['ioning'] = result[discord_uid][lap - 1]['ioning']
                    result[discord_uid][lap]['shot_by_laser'] = False
                    result[discord_uid][lap]['shot_by_ion'] = False

                    # Bonk probability is "pe_factor" percent for each lap
                    rand_pe = random.randint(0, 99)
                    if rand_pe < pe_factor:
                        # If dead
                        if simulate_bonk(result, discord_uid, lap, previous_lap_hull):
                            events[lap][discord_uid] = {}
                            events[lap][discord_uid]['attacker'] = None
                            events[lap][discord_uid]['type'] = 'pilot_error'
                            result[discord_uid]['is_alive'] = False
                            continue
                    else:
                        result[discord_uid][lap]['hull'] = previous_lap_hull

                    # Lap time
                    lap_time = result[discord_uid]['ideal_lap_time'] + random.uniform(0.0, result[discord_uid]['ideal_lap_time'] * 0.1)
                    result[discord_uid][lap]['lap_time'] = lap_time
                    result[discord_uid][lap]['total_time'] = lap_time + float(result[discord_uid][lap - 1]['total_time'])
                    if result[discord_uid]['best_lap'] is None or result[discord_uid]['best_lap'] > lap_time:
                        result[discord_uid]['best_lap'] = lap_time

                    result[discord_uid]['laps_completed'] = lap
                    result[discord_uid]['final_time'] = result[discord_uid][lap]['total_time']

            result_last_to_first = {k: v for k, 
                v in sorted(result.items(), 
                key=lambda x: (-int(x[1]['laps_completed']), float(x[1]['final_time'])), reverse=True)}

            # Shoot people!
            conversion_shield_kicked_in = False
            for idx, discord_uid in enumerate(result_last_to_first):
                # If the last being shot triggered the conversion shield, he doesn't have any laser left so he can't shoot.
                if conversion_shield_kicked_in:
                    #print('Conversion shield kicked in, no shooting for you', discord_uid)
                    conversion_shield_kicked_in = False
                    continue

                if result[discord_uid]['is_alive'] and idx < len(list(result_last_to_first.keys())) - 1:
                    in_front_discord_uid = list(result_last_to_first.keys())[idx + 1]
                    if result[in_front_discord_uid]['is_alive'] and result[discord_uid]['laps_completed'] == result[in_front_discord_uid]['laps_completed']:
                        delta_time = result[discord_uid]['final_time'] - result[in_front_discord_uid]['final_time']
                        distance = result[discord_uid]['speed'] * delta_time
                        weapon_range = result[discord_uid]['primary_weapon_range']
                        if distance < weapon_range:
                            if result[discord_uid]['primary_weapon_type'] == 'ion':
                                result[in_front_discord_uid][lap]['shot_by_ion'] = True
                            else:
                                result[in_front_discord_uid][lap]['shot_by_laser'] = True

                            dps = result[discord_uid]['primary_weapon_dps'] * Racing.global_damage_factor

                            # [0.5..1.0]
                            map_factor = (map_info['kill_factor'] + 10) / 20

                            # [0.5..1.0]
                            drop_off_factor = (weapon_range - distance / 2) / weapon_range

                            # [0.45..0.98]
                            maneuverability_factor = (160 - result[in_front_discord_uid]['maneuverability']) / 110

                            if result[discord_uid]['primary_weapon_type'] == 'burst':
                                damage = dps * map_factor * maneuverability_factor**2
                            elif result[discord_uid]['primary_weapon_type'] == 'plasburst':
                                if random.randint(-3, 14) < map_info['kill_factor']:
                                    damage = dps * drop_off_factor
                                else:
                                    damage = 0
                            elif result[discord_uid]['primary_weapon_type'] == 'guided':
                                damage = dps * map_factor * drop_off_factor
                            else:
                                damage = dps * map_factor * drop_off_factor * maneuverability_factor

                            #print('Lap:', lap, discord_uid, 'Distance:', distance, 'Type:', result[discord_uid]['primary_weapon_type'], 'Damage:', damage)

                            # Apply damage to shield first, if any
                            shield_before_damage = result[in_front_discord_uid][lap]['shield']
                            damage = apply_damage(result, discord_uid, in_front_discord_uid, damage, lap, 'shield', result[discord_uid]['primary_weapon_type'])
                            shield_after_damage = result[in_front_discord_uid][lap]['shield']

                            if result[in_front_discord_uid]['shield_type'] is not None and \
                                result[in_front_discord_uid]['shield_type'] == 'conversion' and \
                                shield_before_damage > 0 and shield_after_damage == 0:
                                #print('Conversion shield kicks in!', in_front_discord_uid)
                                conversion_shield_kicked_in = True

                            # Apply damage to hull
                            if damage > 0 and not conversion_shield_kicked_in:
                                apply_damage(result, discord_uid, in_front_discord_uid, damage, lap, 'hull', result[discord_uid]['primary_weapon_type'])

                            if result[in_front_discord_uid][lap]['hull'] == 0:
                                # If dead
                                events[lap][in_front_discord_uid] = {}
                                events[lap][in_front_discord_uid]['attacker'] = discord_uid
                                events[lap][in_front_discord_uid]['type'] = 'kill'
                                result[in_front_discord_uid]['is_alive'] = False
                                result[in_front_discord_uid]['laps_completed'] -= 1
                                result[in_front_discord_uid]['final_time'] -= result[in_front_discord_uid][lap]['lap_time']
                                del result[in_front_discord_uid][lap]
                                result[discord_uid]['kills'] += [in_front_discord_uid]
                            elif result[in_front_discord_uid][lap]['ioning'] == 0:
                                # If iced
                                # Bonk probability is 5 times higher when iced
                                rand_pe = random.randint(0, 19)
                                if rand_pe < pe_factor:
                                    # If dead
                                    if simulate_bonk(result, in_front_discord_uid, lap, result[in_front_discord_uid]['hull']):
                                        events[lap][in_front_discord_uid] = {}
                                        events[lap][in_front_discord_uid]['attacker'] = discord_uid
                                        events[lap][in_front_discord_uid]['type'] = 'disable_kill'
                                        result[in_front_discord_uid]['is_alive'] = False
                                        result[in_front_discord_uid]['laps_completed'] -= 1
                                        result[in_front_discord_uid]['final_time'] -= result[in_front_discord_uid][lap]['lap_time']
                                        result[discord_uid]['kills'] += [in_front_discord_uid]

                                if result[in_front_discord_uid]['is_alive']:
                                    # 10s lost
                                    events[lap][in_front_discord_uid] = {}
                                    events[lap][in_front_discord_uid]['attacker'] = discord_uid
                                    events[lap][in_front_discord_uid]['type'] = 'disable'
                                    penalty = 10
                                    result[in_front_discord_uid][lap]['lap_time'] += penalty
                                    result[in_front_discord_uid][lap]['total_time'] += penalty
                                    result[in_front_discord_uid]['final_time'] += penalty
                                    result[in_front_discord_uid][lap]['ioning'] = result[in_front_discord_uid]['hull']
                                    result[discord_uid]['disables'] += [in_front_discord_uid]

                            # If dead and unstable engine, apply damage to the attacker
                            if not result[in_front_discord_uid]['is_alive'] and result[in_front_discord_uid]['engine_type'] == 'unstable':
                                damage = Racing.unstable_engine_damage * (Racing.unstable_engine_range - distance / 2) / Racing.unstable_engine_range
                                shield_before_damage = result[discord_uid][lap]['shield']
                                damage = apply_damage(result, in_front_discord_uid, discord_uid, damage, lap, 'shield', 'unstable')
                                shield_after_damage = result[discord_uid][lap]['shield']

                                # Handle conversion shield
                                if damage > 0 and \
                                    not (result[discord_uid]['shield_type'] is not None and \
                                    result[discord_uid]['shield_type'] == 'conversion' and \
                                    shield_before_damage > 0 and shield_after_damage == 0):
                                    apply_damage(result, in_front_discord_uid, discord_uid, damage, lap, 'hull', 'unstable')
                                    
                                if result[discord_uid][lap]['hull'] == 0:
                                    events[lap][discord_uid] = {}
                                    events[lap][discord_uid]['attacker'] = in_front_discord_uid
                                    events[lap][discord_uid]['type'] = 'unstable_kill'
                                    result[discord_uid]['is_alive'] = False
                                    result[discord_uid]['laps_completed'] -= 1
                                    result[discord_uid]['final_time'] -= result[discord_uid][lap]['lap_time']
                                    del result[discord_uid][lap]
                                    result[in_front_discord_uid]['kills'] += [discord_uid]

            # Regen shields and ion if there has been no shots this lap
            for discord_uid in entry_list_dict:
                if result[discord_uid]['is_alive']:
                    if (not result[discord_uid][lap]['shot_by_laser']) and (not result[discord_uid][lap]['shot_by_ion']):
                        if result[discord_uid][lap]['shield'] < result[discord_uid]['shield'] and \
                            not (result[discord_uid]['shield_type'] is not None and \
                                result[discord_uid]['shield_type'] == 'overloaded' and result[discord_uid][lap]['shield'] == 0):
                            #print('Lap:', lap, "Regen shield before:", result[discord_uid][lap]['shield'], discord_uid)
                            regen_shield = result[discord_uid]['shield'] * (0.1 * (1 + result[discord_uid]['shield_regen_bonus'] / 100))
                            result[discord_uid][lap]['shield'] += regen_shield
                            if result[discord_uid][lap]['shield'] > result[discord_uid]['shield']:
                                result[discord_uid][lap]['shield'] = result[discord_uid]['shield']
                            #print("Regen shield after:", result[discord_uid][lap]['shield'], discord_uid, 'regen value:', regen_shield)

                        if not result[discord_uid][lap]['shot_by_ion'] and result[discord_uid][lap]['ioning'] < result[discord_uid]['hull']:
                            #print('Lap:', lap, "Regen ioning before:", result[discord_uid][lap]['ioning'], discord_uid)
                            regen_ion = result[discord_uid]['hull'] * 0.1
                            result[discord_uid][lap]['ioning'] += regen_ion
                            if result[discord_uid][lap]['ioning'] > result[discord_uid]['hull']:
                                result[discord_uid][lap]['ioning'] = result[discord_uid]['hull']
                            #print("Regen ioning after:", result[discord_uid][lap]['ioning'], discord_uid)

        result_sorted = {k: v for k, 
            v in sorted(result.items(), 
            key=lambda x: (-int(x[1]['laps_completed']), float(x[1]['final_time'])))}

        for idx, discord_uid in enumerate(result_sorted):
            result_sorted[discord_uid]['position'] = idx + 1

        return result_sorted, events

    async def compute_bonuses(self, result: dict, entry_list_dict: dict, race_info: dict) -> (float, int, float, int):
        first_in_class_found = {}
        first_in_class_found['interceptor'] = False
        first_in_class_found['fighter'] = False
        first_in_class_found['bomber'] = False

        best_lap = None
        best_lap_uid = None
        most_damage = None
        most_damage_uid = None

        for discord_uid in result:
            result[discord_uid]['participation_streak_bonus'] = 0
            result[discord_uid]['finish_a_race_bonus'] = 0
            result[discord_uid]['finishing_streak_bonus'] = 0
            result[discord_uid]['first_in_class_bonus'] = 0
            result[discord_uid]['podium_bonus'] = 0
            result[discord_uid]['best_lap_bonus'] = 0            
            result[discord_uid]['most_damage_bonus'] = 0

            if result[discord_uid]['is_alive']:
                #TODO: Races finished streak
                result[discord_uid]['finish_a_race_bonus'] = Racing.finish_a_race_bonus
                if not first_in_class_found[result[discord_uid]['class']]:
                    first_in_class_found[result[discord_uid]['class']] = True
                    result[discord_uid]['first_in_class_bonus'] = Racing.first_in_class_bonus
                if result[discord_uid]['position'] <= 3:
                    result[discord_uid]['podium_bonus'] = Racing.podium_bonuses[result[discord_uid]['position'] - 1]

            result[discord_uid]['kill_bonus'] = len(result[discord_uid]['kills']) * Racing.kill_bonus
            result[discord_uid]['disable_bonus'] = len(result[discord_uid]['disables']) * Racing.disable_bonus

            user_best_lap = result[discord_uid]['best_lap']
            if user_best_lap is not None and (best_lap is None or user_best_lap < best_lap):
                best_lap = user_best_lap
                best_lap_uid = discord_uid

            user_damage = result[discord_uid]['hull_damage_dealt'] + result[discord_uid]['shield_damage_dealt']
            if user_damage > 0 and (most_damage is None or user_damage > most_damage):
                most_damage = user_damage
                most_damage_uid = discord_uid

            participation_streak = 1
            finishing_streak = 1 if result[discord_uid]['is_alive'] else 0
            previous_and_current_races_info = await self.get_races_info(2)
            previous_user_results = await self.get_user_race_results(discord_uid)
            if len(previous_and_current_races_info) == 2 and len(previous_user_results) >= 2:
                previous_user_result = previous_user_results[1]
                previous_race_id = previous_and_current_races_info[1]['race_id']
                #if the user took part in the previous race
                if previous_user_result['race_id'] == previous_race_id:
                    participation_streak += previous_user_result['participation_streak']
                    if finishing_streak > 0:
                        finishing_streak += previous_user_result['finishing_streak']

            # The bot doesn't get participation streak bonus as it's automatically registered to all races
            if discord_uid == self.bot_discord_uid:
                result[discord_uid]['participation_streak'] = 0
                result[discord_uid]['participation_streak_bonus'] = 0
            else:
                result[discord_uid]['participation_streak'] = participation_streak
                result[discord_uid]['participation_streak_bonus'] = participation_streak * Racing.participation_streak_bonus

            result[discord_uid]['finishing_streak'] = finishing_streak
            result[discord_uid]['finishing_streak_bonus'] = finishing_streak * Racing.finishing_streak_bonus

        if best_lap_uid is not None:
            result[best_lap_uid]['best_lap_bonus'] = Racing.best_lap_bonus           
        if most_damage_uid is not None:
            result[most_damage_uid]['most_damage_bonus'] = Racing.most_damage_bonus

        for discord_uid in result:
            total_bonus = result[discord_uid]['finish_a_race_bonus'] + \
                         result[discord_uid]['participation_streak_bonus'] + \
                         result[discord_uid]['finishing_streak_bonus'] + \
                         result[discord_uid]['first_in_class_bonus'] + \
                         result[discord_uid]['podium_bonus'] + \
                         result[discord_uid]['kill_bonus'] + \
                         result[discord_uid]['disable_bonus'] + \
                         result[discord_uid]['best_lap_bonus'] + \
                         result[discord_uid]['most_damage_bonus']
            result[discord_uid]['total_bonus'] = total_bonus
            entry_bet_credits = entry_list_dict[discord_uid]['entry_bet_credits']
            result[discord_uid]['entry_bet_credits'] = entry_bet_credits
            jackpot = race_info['jackpot']

            gain_credits = entry_bet_credits * total_bonus / 100
            if result[discord_uid]['is_alive'] and result[discord_uid]['position'] == 1:
                result[discord_uid]['jackpot'] = jackpot
                gain_credits += jackpot
            else:
                result[discord_uid]['jackpot'] = 0
            result[discord_uid]['gain_credits'] = gain_credits

        return best_lap, best_lap_uid, most_damage, most_damage_uid

    async def build_ship_embed(self, user, ship_info, loadout_fields, edit_loadout: bool = False, current_loadout_field_idx: int = 0) -> discord.Embed:
        def build_data_field(embed: discord.Embed, ship_info, title: str, key: str, max_value: int):
            if key == 'primary_weapon_dps':
                dps, weapon_type, range = self.get_primary_weapon_info(ship_info)
                embed.add_field(name=title, value='{} {:,} {}'.format(helper.get_progress_bar(dps, max_value), dps, 
                    '⚡' if weapon_type == 'ion' else ''), inline=False)
            else:
                default, offset, value = self.get_ship_spec(ship_info, key)
                embed.add_field(name=title, value='{} {:,.0f} {}'.format(helper.get_progress_bar(value, max_value, offset), value,
                    '({:+,.0f})'.format(offset) if offset != 0 else ''), inline=False)

        def build_loadout_field(embed: discord.Embed, title: str, value: str):
            embed.add_field(name=title, value=value, inline=False)

        def get_component_bonus_description(component_id: int) -> str:
            component = self.components_info_dict[component_id]
            list_of_strings = []
            if component['primary_weapon_range'] is not None:
                list_of_strings += ['Range: {:,d} m'.format(component['primary_weapon_range'])]
            if component['speed_bonus'] != 0:
                list_of_strings += ['Speed: {:+d}%'.format(component['speed_bonus'])]
            if component['acceleration_bonus'] != 0:
                list_of_strings += ['Acceleration: {:+d}%'.format(component['acceleration_bonus'])]
            if component['maneuverability_bonus'] != 0:
                list_of_strings += ['Maneuverability: {:+d}%'.format(component['maneuverability_bonus'])]
            if component['hull_bonus'] != 0:
                list_of_strings += ['Hull: {:+d}%'.format(component['hull_bonus'])]
            if component['shield_bonus'] is not None and component['shield_bonus'] != 0:
                list_of_strings += ['Shield: {:+d}%'.format(component['shield_bonus'])]
            if component['damage_received_bonus'] != 0:
                list_of_strings += ['Damage received: {:+d}%'.format(component['damage_received_bonus'])]
            if component['shield_regen_bonus'] is not None and component['shield_regen_bonus'] != 0:
                list_of_strings += ['Shield regen: {:+d}%'.format(component['shield_regen_bonus'])]
            if component['sub_type'] == 'unstable':
                list_of_strings += ['Massive explosion on death']
            elif component['sub_type'] == 'overloaded':
                list_of_strings += ['No shield regen if depleted']
            elif component['sub_type'] == 'conversion':
                list_of_strings += ['Automatic emergency shield']
            elif component['sub_type'] == 'ion':
                list_of_strings += ['Ion weapon']
            elif component['sub_type'] == 'guided':
                list_of_strings += ['Auto-aim']
            return '\n'.join(list_of_strings)

        component_title_strings = []
        component_strings = []
        ship_info = dict(ship_info)
        for idx, field in enumerate(loadout_fields):
            component_idx = loadout_fields[field]['current_component_idx']
            if edit_loadout:
                component_title_strings += ['{} ({}/{})'.format(
                    loadout_fields[field]['title'], 
                    component_idx + 1, 
                    len(loadout_fields[field]['component_id_list']))]
            else:
                component_title_strings += [loadout_fields[field]['title']]
            # TODO: 🔒
            component_id = loadout_fields[field]['component_id_list'][component_idx]
            component_string = self.components_info_dict[component_id]['display_name']
            if edit_loadout and idx == current_loadout_field_idx:
                component_bonus = get_component_bonus_description(component_id)
                component_string = '◀ {} ▶\n{}'.format(component_string, component_bonus)
            component_strings += [component_string]

            if edit_loadout:
                ship_info[field] = component_id

        embed = discord.Embed(title=ship_info['display_name'], description=ship_info['description'], colour=user.colour)
        embed.set_author(name=user.display_name, icon_url=user.avatar_url)
        embed.set_thumbnail(url=ship_info['image_url'])
        build_data_field(embed, ship_info, 'Speed', 'speed', Racing.max_speed)
        build_data_field(embed, ship_info, 'Acceleration', 'acceleration', Racing.max_acceleration)
        build_data_field(embed, ship_info, 'Maneuverability', 'maneuverability', Racing.max_maneuverability)
        build_data_field(embed, ship_info, 'Hull', 'hull', Racing.max_hull)
        if ship_info['shield'] > 0:
            build_data_field(embed, ship_info, 'Shield', 'shield', Racing.max_shield)
        build_data_field(embed, ship_info, 'DPS', 'primary_weapon_dps', Racing.max_dps)

        if edit_loadout:
            embed.add_field(name='Loadout', value='Click ✅ to save your changes, ❌ to cancel.', inline=False)
        else:
            embed.add_field(name='Loadout', value='Click 🛠 to customise your ship!', inline=False)

        for idx in range(0, len(component_title_strings)):
            build_loadout_field(embed, component_title_strings[idx], component_strings[idx])

        embed.set_footer(text=f"Ship {ship_info['ship_id'] + 1}/{len(self.ships_info_dict)}")
        return embed

    async def show_hangar(self, ctx, ship_id: int = 0, edit_loadout_only: bool = False, embed: discord.Embed = None):
        emoji_list = ['◀', '▶', '🛠', '🛑']
        edit_loadout_emoji_list = ['◀', '▶', '🔽', '🔼', '✅', '❌']
        user = ctx.author
        ships_info = await self.get_user_hangar_info(user.id)
        current_embed = embed
        embeds = []
        current_index = 0
        current_loadout_field_idx = 0
        loadout_fields = {}
        edit_loadout = edit_loadout_only

        async def refresh_loadout_info(ship_info):
            loadout_fields.clear()
            loadout_fields['engine_component_id'] = {'title': 'Engine'}
            loadout_fields['primary_weapon_component_id'] = {'title': 'Primary weapon'}
            loadout_fields['hull_component_id'] = {'title': 'Hull'}
            if ship_info['shield'] > 0:
                loadout_fields['shield_component_id'] = {'title': 'Shield'}

            for field in loadout_fields:
                field_type = field.replace('_component_id', '')
                loadout_fields[field]['component_id_list'] = []
                for component in self.components_info:
                    if component['type'] == field_type and ship_info['ship_id'] in component['ship_id_list']:
                        loadout_fields[field]['component_id_list'] += [component['component_id']]
                loadout_fields[field]['current_component_idx'] = loadout_fields[field]['component_id_list'].index(ship_info[field])

        async def build_first_screen(current_embed: discord.Embed = None) -> (discord.Embed, list, int, dict):
            embeds = []

            for idx, ship in enumerate(ships_info):
                if ship['ship_id'] == ship_id:
                    current_index = idx
                    ship_info = ship
                    break

            if edit_loadout_only:
                await refresh_loadout_info(ship_info)
                if current_embed is None:
                    current_embed = await ctx.send(embed=await self.build_ship_embed(user, ship_info, loadout_fields, edit_loadout, current_loadout_field_idx))
                else:
                    await current_embed.edit(embed=await self.build_ship_embed(user, ship_info, loadout_fields, edit_loadout, current_loadout_field_idx))
                for e in edit_loadout_emoji_list:
                    await current_embed.add_reaction(e)            
            else:
                for ship_info in ships_info:
                    await refresh_loadout_info(ship_info)
                    embeds += [await self.build_ship_embed(user, ship_info, loadout_fields, edit_loadout)]
                if current_embed is None:
                    current_embed = await ctx.send(embed=embeds[current_index])
                else:
                    await current_embed.edit(embed=embeds[current_index])
                for e in emoji_list:
                    await current_embed.add_reaction(e)
            return current_embed, embeds, current_index, ship_info

        async def reaction_waiter() -> str:
            """Async helper to await for reactions"""

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in emoji_list + edit_loadout_emoji_list \
                       and r.message.id == current_embed.id
            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                return 'Timeout'
            return str(reaction.emoji)

        current_embed, embeds, current_index, ship_info = await build_first_screen(current_embed)
        while True:
            user_input = await reaction_waiter()
            if edit_loadout:
                # Previous component
                if user_input == '◀':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    field = list(loadout_fields)[current_loadout_field_idx]
                    loadout_fields[field]['current_component_idx'] = (loadout_fields[field]['current_component_idx'] - 1) % len(loadout_fields[field]['component_id_list'])
                    await current_embed.edit(embed=await self.build_ship_embed(user, ships_info[current_index], loadout_fields, edit_loadout, current_loadout_field_idx))
                # Next component
                elif user_input == '▶':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    field = list(loadout_fields)[current_loadout_field_idx]
                    loadout_fields[field]['current_component_idx'] = (loadout_fields[field]['current_component_idx'] + 1) % len(loadout_fields[field]['component_id_list'])
                    await current_embed.edit(embed=await self.build_ship_embed(user, ships_info[current_index], loadout_fields, edit_loadout, current_loadout_field_idx))
                # Previous field
                elif user_input == '🔼':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    current_loadout_field_idx = (current_loadout_field_idx - 1) % len(loadout_fields)
                    await current_embed.edit(embed=await self.build_ship_embed(user, ships_info[current_index], loadout_fields, edit_loadout, current_loadout_field_idx))
                    pass
                # Next field
                elif user_input == '🔽':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    current_loadout_field_idx = (current_loadout_field_idx + 1) % len(loadout_fields)
                    await current_embed.edit(embed=await self.build_ship_embed(user, ships_info[current_index], loadout_fields, edit_loadout, current_loadout_field_idx))
                    pass
                # Cancel
                elif user_input == '❌':
                    if edit_loadout_only:                       
                        await current_embed.clear_reactions()
                        break
                    else:
                        edit_loadout = False
                        await current_embed.clear_reactions()
                        ships_info = await self.get_user_hangar_info(user.id)
                        current_embed, embeds, current_index, ship_info = await build_first_screen(current_embed)
                # Save
                elif user_input == '✅':
                    #Save loadout
                    if edit_loadout_only:
                        ship_info = helper.record_to_dict(ships_info, 'ship_id').get(ship_id)
                        ship_info['ship_id'] = ship_id
                    else:
                        ship_info = dict(ships_info[current_index])
                    for idx, field in enumerate(loadout_fields):
                        component_idx = loadout_fields[field]['current_component_idx']
                        component_id = loadout_fields[field]['component_id_list'][component_idx]
                        ship_info[field] = component_id

                    await self.save_loadout(ship_info)
                    
                    if edit_loadout_only:                       
                        await current_embed.clear_reactions()
                        break
                    else:
                        edit_loadout = False
                        await current_embed.clear_reactions()
                        ships_info = await self.get_user_hangar_info(user.id)
                        current_embed, embeds, current_index, ship_info = await build_first_screen(current_embed)
            else:
                # Previous Page - Loopable
                if user_input == '◀':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    current_index = (current_index - 1) % len(embeds)
                    ship_id = ships_info[current_index]['ship_id']
                    await current_embed.edit(embed=embeds[current_index])
                # Next Page - Loopable
                elif user_input == '▶':
                    await current_embed.remove_reaction(user_input, ctx.author)
                    current_index = (current_index + 1) % len(embeds)
                    ship_id = ships_info[current_index]['ship_id']
                    await current_embed.edit(embed=embeds[current_index])
                # No response or STOP
                elif user_input == '🛠':
                    await current_embed.clear_reactions()
                    current_loadout_field_idx = 0
                    edit_loadout = True
                    await refresh_loadout_info(ships_info[current_index])
                    await current_embed.edit(embed=await self.build_ship_embed(user, ships_info[current_index], loadout_fields, True, current_loadout_field_idx))
                    for e in edit_loadout_emoji_list:
                        await current_embed.add_reaction(e)
                else:
                    await current_embed.clear_reactions()
                    await asyncio.sleep(30)
                    await current_embed.delete()
                    break

    def get_rank(self, idx: int, is_alive: bool) -> str:
        if not is_alive:
            return '💀'
        if idx == 1:
            return '🥇'
        elif idx == 2:
            return '🥈'
        elif idx == 3:
            return '🥉'
        else:
            return '{}.'.format(idx)

    def get_event_string(self, events: dict, lap: int, victim_discord_uid: int) -> str:
        event = events[lap][victim_discord_uid]

        if event['attacker'] is not None:
            attacker = helper.get_member_mention(self.guild, event['attacker'])
        else:
            attacker = None
        victim = helper.get_member_mention(self.guild, victim_discord_uid)

        if event['type'] == 'disable':
            event_string = 'Lap {}: {} ⚡ {}'.format(lap, attacker, victim)
        elif event['type'] == 'disable_kill':
            event_string = 'Lap {}: {} ⚡💥 {}'.format(lap, attacker, victim)
        elif event['type'] == 'pilot_error':
            event_string = 'Lap {}: 💥 {}'.format(lap, victim)
        elif event['type'] == 'kill':
            event_string = 'Lap {}: {} {} {}'.format(lap, attacker, helper.get_config('blaster_emoji'), victim)
        elif event['type'] == 'unstable_kill':
            event_string = 'Lap {}: {} 💥 {}'.format(lap, attacker, victim)
        else:
            event_string = ''

        return event_string

    def get_standing_strings(self, race_result, entry_list_dict) -> list:
        standing = []
        winner_uid = list(race_result.keys())[0]
        winner = helper.get_member_mention(self.guild, winner_uid)
        winner_final_time = race_result[winner_uid]['final_time']
        winner_laps_completed = race_result[winner_uid]['laps_completed']

        for idx, discord_uid in enumerate(race_result):
            name = helper.get_member_mention(self.guild, discord_uid)
            laps_completed = race_result[discord_uid]['laps_completed']
            position = self.get_rank(idx + 1, race_result[discord_uid]['is_alive'])
            if idx == 0:
                time_string = helper.race_time_to_string(winner_final_time)
            elif laps_completed == winner_laps_completed:
                time_string = '+{}'.format(helper.race_time_to_string(race_result[discord_uid]['final_time'] - winner_final_time))
            else:
                time_string = '+{} laps'.format(winner_laps_completed - laps_completed)
            ship_display_name = self.ships_info_dict[entry_list_dict[discord_uid]['ship_id']]['display_name']
            hull_remaining = race_result[discord_uid][laps_completed]['hull'] / race_result[discord_uid]['hull'] * 100
            details_string = '{} pts'.format(race_result[discord_uid]['total_bonus'])
            if not race_result[discord_uid]['is_alive']:
                details_string += ', {}'.format(ship_display_name)
            elif race_result[discord_uid]['shield'] > 0:
                shield_remaining = race_result[discord_uid][laps_completed]['shield'] / race_result[discord_uid]['shield'] * 100
                details_string += ', {}, hull: {:.0f}%, shield: {:.0f}%'.format(ship_display_name, 
                    hull_remaining, shield_remaining)
            else:
                details_string += ', {}, hull: {:.0f}%'.format(ship_display_name, hull_remaining)
            
            standing += ['{} {}: {}\n󠀠󠀠{}'.format(position, name, time_string, details_string)]

        return standing

    async def build_race_result_embed(self, race_info, race_result, events, entry_list_dict, best_lap, best_lap_uid, 
                                      new_lap_record: bool, most_damage, most_damage_uid, next_race_jackpot: int):
        map_info = self.maps_info[race_info["map_id"]]
        winner_uid = list(race_result.keys())[0]
        winner = helper.get_member_mention(self.guild, winner_uid)
        winner_final_time = race_result[winner_uid]['final_time']
        winner_laps_completed = race_result[winner_uid]['laps_completed']

        events_strings = []
        best_lap_name = None if best_lap_uid is None else helper.get_member_mention(self.guild, best_lap_uid)
        most_damage_name = None if most_damage_uid is None else helper.get_member_mention(self.guild, most_damage_uid)

        # Get standing
        standing = self.get_standing_strings(race_result, entry_list_dict)

        # Get events
        for lap in range(1, race_info['laps'] + 1):
            for victim_discord_uid in events[lap]:
                events_strings += [self.get_event_string(events, lap, victim_discord_uid)]

        if winner_laps_completed == race_info['laps']:
            jackpot = race_info['jackpot']
            winner_bet = entry_list_dict[winner_uid]['entry_bet_credits']
            winner_bonus = race_result[winner_uid]['total_bonus']
            embed = discord.Embed(title='Race result', description=f'Congratulations to {winner} for winning '
                f'the {race_info["laps"]} laps of {map_info["display_name"]}!\n'
                f'{winner} wins {winner_bonus}% of the entry bet '
                f'and the {helper.credits_to_string(jackpot)} jackpot '
                f'for a total of {helper.credits_to_string(winner_bonus * winner_bet / 100 + jackpot)}!\n'
                f'Registration is now open for the next race with a {helper.credits_to_string(next_race_jackpot)} jackpot!',
                color=map_info['color'])
            embed.add_field(name='Standing', value='\n'.join(standing), inline=False)
        else:
            embed = discord.Embed(title='Race result', description=f'The race is over... And everybody died!\n'
                f'Registration is now open for the next race with a {helper.credits_to_string(next_race_jackpot)} jackpot!', color=map_info['color'])

        if events_strings:
            embed.add_field(name='Events', value='\n'.join(events_strings), inline=False)
        if best_lap is not None:
            embed.add_field(name='Best lap', value='{}: {}{}'.format(best_lap_name, helper.lap_time_to_string(best_lap),
                                                                    ' (NEW RECORD)' if new_lap_record else ''), inline=False)
        if most_damage is not None:
            embed.add_field(name='Most damage dealt', value='{}: {:,.0f}'.format(most_damage_name, most_damage), inline=False)
        embed.set_footer(text='Time: {}'.format(datetime.utcnow().strftime('%Y-%b-%d %H:%M')))
        embed.set_thumbnail(url=self.maps_info[race_info['map_id']]['image_url'])
        return embed

    async def build_personal_race_result_embed(self, user, race_info, result, events, entry_list_dict):
        map_info = self.maps_info[race_info["map_id"]]
        winner_uid = list(result.keys())[0]
        winner = helper.get_member_mention(self.guild, winner_uid)
        winner_final_time = result[winner_uid]['final_time']
        winner_laps_completed = result[winner_uid]['laps_completed']

        bonus_strings = []
        events_strings = []
        laps_strings = []
        user_avg_lap_time = None
        user_position = result[user.id]['position'] 
        user_jackpot = result[user.id]['jackpot']
        user_bet = result[user.id]['entry_bet_credits']
        user_bonus = result[user.id]['total_bonus']
        user_gain = result[user.id]['gain_credits']
        user_laps_completed = result[user.id]["laps_completed"]
        user_kills = len(result[user.id]['kills'])
        user_disables = len(result[user.id]['disables'])

        # Get standing
        standing = self.get_standing_strings(result, entry_list_dict)

        # Generate events and laps
        for lap in range(1, race_info['laps'] + 1):
            if lap <= user_laps_completed:
                lap_time = result[user.id][lap]['lap_time']
                if user_avg_lap_time is None:
                    user_avg_lap_time = lap_time
                else:
                    # Compute the sum of the lap times first
                    user_avg_lap_time += lap_time
                laps_strings += ['Lap {}: {}'.format(lap, helper.lap_time_to_string(lap_time))]

            for victim_discord_uid in events[lap]:
                event = events[lap][victim_discord_uid]
                if victim_discord_uid == user.id or \
                    (event['attacker'] is not None and event['attacker'] == user.id):
                    events_strings += [self.get_event_string(events, lap, victim_discord_uid)]

        # Compute the average
        if user_laps_completed > 0:
            user_avg_lap_time /= user_laps_completed

        if result[user.id]['finish_a_race_bonus'] > 0:
            bonus_strings += ['Finishing the race: {} pts'.format(result[user.id]['finish_a_race_bonus'])]
        if result[user.id]['podium_bonus'] > 0:
            bonus_strings += ['P{}: {} pts'.format(user_position, result[user.id]['podium_bonus'])]
        if result[user.id]['first_in_class_bonus'] > 0:
            bonus_strings += ['First in class ({}): {} pts'.format(self.ships_info_dict[entry_list_dict[user.id]['ship_id']]['class'], 
                                                                   result[user.id]['first_in_class_bonus'])]
        if user_kills > 0:
            bonus_strings += ['Kills ({} x {}): {} pts'.format(user_kills, Racing.kill_bonus, result[user.id]['kill_bonus'])]
        if user_disables > 0:
            bonus_strings += ['Disables ({} x {}): {} pts'.format(user_disables, Racing.disable_bonus, result[user.id]['disable_bonus'])]
        if result[user.id]['best_lap_bonus'] > 0:
            bonus_strings += ['Best lap: {} pts'.format(result[user.id]['best_lap_bonus'])]
        if result[user.id]['most_damage_bonus'] > 0:
            bonus_strings += ['Most damage: {} pts'.format(result[user.id]['most_damage_bonus'])]
        if result[user.id]['finishing_streak_bonus'] > 0:
            bonus_strings += ['Finishing streak ({} x {}): {} pts'.format(result[user.id]['finishing_streak'], 
                                                                          Racing.finishing_streak_bonus,
                                                                          result[user.id]['finishing_streak_bonus'])]
        bonus_strings += ['Participation streak ({} x {}): {} pts'.format(result[user.id]['participation_streak'], 
                                                                          Racing.participation_streak_bonus,
                                                                           result[user.id]['participation_streak_bonus'])]
        if len(bonus_strings) > 1:
            bonus_strings += ['TOTAL: {} pts'.format(result[user.id]['total_bonus'])]
        elif not bonus_strings:
            bonus_strings += ['0 pts']

        title = 'Personal race report'
        if winner_laps_completed == race_info['laps']:
            if result[user.id]['is_alive']:
                if user_position == 1:
                    embed = discord.Embed(title=title, description=f'You have won the race, congratulations!', color=map_info['color'])
                else:
                    embed = discord.Embed(title=title, description=f'You have finished the race P{user_position}!', color=map_info['color'])
            else:
                embed = discord.Embed(title=title, description=f'You died on lap {user_laps_completed + 1}.', 
                    color=map_info['color'])
        else:
            embed = discord.Embed(title=title, description=f'Everybody died!', color=map_info['color'])

        embed.add_field(name='Standing', value='\n'.join(standing), inline=False)
        if events_strings:
            embed.add_field(name='Your events', value='\n'.join(events_strings), inline=False)
        if laps_strings:
            embed.add_field(name='Your lap times', value='\n'.join(laps_strings), inline=False)
        if result[user.id]['best_lap'] is not None:
            embed.add_field(name='Your best lap', value='{}'.format(helper.lap_time_to_string(result[user.id]['best_lap'])), inline=False)
        if user_avg_lap_time is not None:
            embed.add_field(name='Your average lap time', value='{}'.format(helper.lap_time_to_string(user_avg_lap_time)), inline=False)
        if result[user.id]['shield_damage_dealt'] > 0:
            embed.add_field(name='Your shield damage dealt', value='{:,.0f}'.format(result[user.id]['shield_damage_dealt']), inline=False)
        if result[user.id]['hull_damage_dealt'] > 0:
            embed.add_field(name='Your hull damage dealt', value='{:,.0f}'.format(result[user.id]['hull_damage_dealt']), inline=False)    
        if result[user.id]['ioning_damage_dealt'] > 0:
            embed.add_field(name='Your ion damage dealt', value='{:,.0f}'.format(result[user.id]['ioning_damage_dealt']), inline=False)    
        embed.add_field(name='Your bonus', value='\n'.join(bonus_strings), inline=False)
        embed.add_field(name='Your gain', value='{} x {:.0f} / 100{} = {}'.format(
            helper.credits_to_string(user_bet),
            user_bonus,
            ' + {}'.format(helper.credits_to_string(user_jackpot)) if user_position == 1 else '',
            helper.credits_to_string(user_gain)
            ), inline=False)
        embed.add_field(name='Net gain', value='{} - {} = {}'.format(
            helper.credits_to_string(user_gain), 
            helper.credits_to_string(user_bet), 
            helper.credits_to_string(user_gain - user_bet)), inline=False)
        embed.set_footer(text='If you don\'t want to receive this message for the next races, type "$race_report unsubscribe".')
        embed.set_thumbnail(url=self.maps_info[race_info['map_id']]['image_url'])
        return embed


    async def create_next_race(self, jackpot: int):
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                utcnow = datetime.utcnow()
                next_race_date_time = datetime.combine(utcnow.date() + timedelta(days=1), Racing.race_time_utc)

                # Can the first race be today?
                if next_race_date_time - utcnow > timedelta(days=1, hours=6):
                    next_race_date_time -= timedelta(days=1)
                map_id = random.choice(self.maps_info)['map_id']
                await connection.execute("""INSERT INTO gray.racing_races (timestamp, map_id, jackpot, laps)
                                            VALUES ($1, $2, $3, $4)""",
                                         next_race_date_time, map_id, jackpot, random.randint(5, 10))

        # Register the bot with a random ship
        self.race_reminder_sent = False
        race_info = await self.get_race_info()
        await self.race_registration(race_info['race_id'], self.bot_discord_uid, 1000, random.choice(list(self.ships_info_dict)))

    async def start_race(self):
        race_info = await self.get_race_info()
        entry_list = await self.get_race_result(race_info['race_id'])
        entry_list_dict = helper.record_to_dict(entry_list, 'discord_uid')

        for map_info_entry in self.maps_info:
            if map_info_entry['map_id'] == race_info['map_id']:
                map_info = map_info_entry
                break

        # Simulate race
        result, events = await self.simulate_race(race_info, entry_list_dict, map_info)

        # Compute bonuses and gains
        best_lap, best_lap_uid, most_damage, most_damage_uid = await self.compute_bonuses(result, entry_list_dict, race_info)

        # Check if best_lap is a new record
        new_lap_record = False
        if map_info['lap_record'] is None or map_info['lap_record'] > best_lap:
            await self.set_lap_record(map_info['map_id'], best_lap, best_lap_uid)
            new_lap_record = True
            # Refresh map info
            self.maps_info = await self.get_maps_info()
            self.maps_info_dict = helper.record_to_dict(self.maps_info, 'map_id')

        # Pay and send personal results in PM
        next_race_jackpot = Racing.base_jackpot
        for discord_uid in result:
            if discord_uid != self.bot_discord_uid:
                # Entry bet is added to the next race jackpot if you died
                if not result[discord_uid]['is_alive']:
                    next_race_jackpot += result[discord_uid]['entry_bet_credits']

                await self.economy.change_credits(discord_uid, result[discord_uid]['gain_credits'])
                if await self.is_user_subscribed_to_race_report(discord_uid):
                    user = self.guild.get_member(discord_uid)
                    if user is not None:
                        await user.send(embed=await self.build_personal_race_result_embed(user, race_info, result, events, entry_list_dict))

        # Send results to the channel
        await self.racing_channel.send(embed=await self.build_race_result_embed(race_info, result, events, entry_list_dict, best_lap, best_lap_uid, new_lap_record, most_damage, most_damage_uid, next_race_jackpot))

        await self.save_result_in_db(race_info['race_id'], result)

        await self.create_next_race(next_race_jackpot)

    @tasks.loop(minutes=1, reconnect=True)
    async def race_task(self):
        await self.load_fixed_data()
        race_info = await self.get_race_info()

        if race_info:
            current_time = datetime.utcnow()
            if current_time > race_info['timestamp']:
                await self.start_race()
            elif current_time > race_info['timestamp'] - timedelta(hours=1) \
                and not self.race_reminder_sent:
                await self.race(None)
                self.race_reminder_sent = True
        else:
            # First race creation
            await self.create_next_race(Racing.base_jackpot)

    # Commands
    @commands.command()
    @commands.has_role('Droid Engineer')
    async def race_now(self, ctx):
        await self.start_race()

    @race_now.error
    async def race_now_error(self, ctx, error):
        if isinstance(error, commands.MissingRole):
            await ctx.send('You are not a Droid Engineer!')
        else:
            await helper.bot_log(self.client, error, ctx.message)
            
    # Commands
    @commands.command()
    async def race(self, ctx, *, arg: str = ''):
        """Get on the cockpit and join the race!

        You can specify the amount of the entry bet as argument.
        Use "$race" if you just want to see the race info and entry list.

        Arguments:
        - Amount of the entry bet: This is how much you pay to enter the race. 
          At the end of the race, you will win this entry bet multiplied by your bonus who will depend on how good you performed.

        Examples:
        - $race
        Shows information about the race and the entry list, without changing anything to your current registration.

        - $race 500k
        Enter the race with 500 kC (500'000 C) of entry bet.
        If you are already registered, this will update your entry bet and let you change your ship if needed.
        """
        emoji_list = ['🔍', '🔽', '🔼', '🛠', '✅', '🛑']

        entry_bet_credits = 0
        previous_entry_bet_credits = 0
        race_info = await self.get_race_info()
        entry_list = await self.get_race_result(race_info['race_id'])
        entry_list_dict = helper.record_to_dict(entry_list, 'discord_uid')
        map_info = self.maps_info[race_info['map_id']]
        current_index = 0

        info_only = not arg and ctx is not None
        reminder = (ctx is None)

        if not reminder:
            ships_info = await self.get_user_hangar_info(ctx.author.id)
            already_registered = entry_list_dict.get(ctx.author.id) is not None
            if already_registered:
                previous_entry_bet_credits = entry_list_dict[ctx.author.id]['entry_bet_credits']
                for idx, ship in enumerate(ships_info):
                    if ship['ship_id'] == entry_list_dict.get(ctx.author.id).get('ship_id'):
                        current_index = idx
                        break

        if not info_only and not reminder:
            try:
                entry_bet_credits = helper.parse_amount(arg.replace(' ', ''))
            except ValueError:
                await ctx.send(f'Invalid argument: {arg}\nType "$help race" for more info.')
                return

            if entry_bet_credits < Racing.min_entry_bet_credits:
                await ctx.send("You need to bet at least {} to race.".format(helper.credits_to_string(Racing.min_entry_bet_credits)))
                return

            user_credit_total = await self.economy.get_credits(ctx.author.id)

            if (entry_bet_credits - previous_entry_bet_credits) > user_credit_total:
                await ctx.send('Sorry, you do not have enough money. Try to type "hope" to get {}!'.format(helper.credits_to_string(100)))
                return


        time_left = race_info['timestamp'] - datetime.utcnow()
        if not info_only and not reminder and time_left < timedelta(minutes=1):
            await ctx.send("Sorry, it's too late to register, the race has almost started. Try again in a couple minutes!")
            return
            

        async def build_race_registration_embed() -> discord.Embed:
            race_info_string = 'Starts in: {}\nMap: {}\nLaps: {}\nLength: {:,} m\nJackpot: {}'.format(
                                    'Starting...' if time_left < timedelta(0) else str(time_left).split('.')[0],
                                    map_info['display_name'] if reminder else '{} (Click "🔍" for more info)'.format(map_info['display_name']),
                                    race_info['laps'],
                                    self.get_map_lap_length(map_info) * race_info['laps'],
                                    helper.credits_to_string(race_info['jackpot']))

            if reminder:
                description = 'The race is starting soon, don\'t forget to register by typing "$race" followed by your entry bet!'
            elif already_registered and info_only:
                description = 'You are already registered for this race but you can update your bet and your ship by typing "$race" followed by your new bet.'
                race_info_string += '\nYour bet: {}'.format(helper.credits_to_string(entry_list_dict[ctx.author.id]['entry_bet_credits']))
            elif already_registered: # not info_only
                description = 'You are already registered for this race but you can update your bet and your ship.'
                race_info_string += '\nCurrent bet: {}\nNew bet: {}'.format(
                                    helper.credits_to_string(previous_entry_bet_credits),
                                    helper.credits_to_string(entry_bet_credits))
            elif info_only: # Not already_registered
                description = 'You are not registered for this race.\nType "$race" followed by your bet to sign in!'
            else: # not registered and not info_only
                description = 'Select a ship to take part in the next race with a {} bet on yourself!'.format(helper.credits_to_string(entry_bet_credits))
                race_info_string += '\nYour bet: {}'.format(helper.credits_to_string(entry_bet_credits))

            if reminder:
                embed = discord.Embed(title='Race reminder', description=description, color=map_info['color'])
            elif info_only:
                embed = discord.Embed(title='Race info', description=description, color=map_info['color'])
            else:
                embed = discord.Embed(title='Race registration', description=description, color=map_info['color'])

            if not reminder:
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
            embed.set_thumbnail(url=map_info['image_url'])            
            embed.add_field(name='Info', value=race_info_string, inline=False)
            if entry_list:
                embed.add_field(name='Entry list', value='\n'.join('{}. {}: {}'.format(
                    idx + 1, 
                    helper.get_member_display_name(self.guild, entry['discord_uid']),
                    helper.credits_to_string(entry['entry_bet_credits']))
                    for idx, entry in enumerate(entry_list)), inline=False)

            if not info_only and not reminder:
                ships_list = []
                for idx, ship_info in enumerate(ships_info):
                    if idx == current_index:
                        ships_list += ['▶ {}'.format(ship_info['display_name'])]
                    else:
                        ships_list += [ship_info['display_name']]
                embed.add_field(name='Ship', value='\n'.join(ships_list), inline=False)
            return embed

        async def add_reactions():
            if info_only:
                await current_embed.add_reaction('🔍')
                await current_embed.add_reaction('🛑')
            else:
                for e in emoji_list:
                    await current_embed.add_reaction(e)

        if reminder:
            await self.racing_channel.send(embed=await build_race_registration_embed())
            return

        current_embed = await ctx.send(embed=await build_race_registration_embed())
        await add_reactions()

        async def reaction_waiter() -> str:
            """Async helper to await for reactions"""

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in emoji_list \
                       and r.message.id == current_embed.id
            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=30)
            except asyncio.TimeoutError:
                return 'Timeout'
            return str(reaction.emoji)

        while True:
            user_input = await reaction_waiter()
            # Open ship view
            if user_input == '🛠':
                await current_embed.clear_reactions()
                await self.show_hangar(ctx, ships_info[current_index]['ship_id'], True, current_embed)
                await current_embed.edit(embed=await build_race_registration_embed())
                await add_reactions()
            if user_input == '🔍':
                await current_embed.clear_reactions()
                await self.show_maps(ctx, race_info['map_id'], True, current_embed)
                await current_embed.edit(embed=await build_race_registration_embed())
                await add_reactions()
            # Previous Page - Loopable
            elif user_input == '🔼':
                await current_embed.remove_reaction(user_input, ctx.author)
                current_index = (current_index - 1) % len(ships_info)
                await current_embed.edit(embed=await build_race_registration_embed())
            # Next Page - Loopable
            elif user_input == '🔽':
                await current_embed.remove_reaction(user_input, ctx.author)
                current_index = (current_index + 1) % len(ships_info)
                await current_embed.edit(embed=await build_race_registration_embed())
            # Validation
            elif user_input == '✅':
                user_credit_total = await self.economy.get_credits(ctx.author.id)
                if user_credit_total >= (entry_bet_credits - previous_entry_bet_credits):
                    await self.economy.change_credits(ctx.author.id, -(entry_bet_credits - previous_entry_bet_credits))
                    await self.race_registration(race_info['race_id'], ctx.author.id, entry_bet_credits, ships_info[current_index]['ship_id'], already_registered)
                    await ctx.send(f"{ctx.author.mention} has successfully registered for the race!")
                    await current_embed.clear_reactions()
                    await asyncio.sleep(3)
                    await current_embed.delete()
                    break
                else:
                    await current_embed.remove_reaction(user_input, ctx.author)
                    await ctx.send("Sorry, you do not have enough money.")
            # No response or STOP
            elif user_input == '🛑' or user_input == 'Timeout':
                await current_embed.clear_reactions()
                await current_embed.delete()
                break
    '''
    @race.error
    async def race_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)
    '''
    # Commands
    @commands.command()
    async def race_practice(self, ctx, ship_argument: str = '', map_argument: str = '', laps: int = -1):
        """Free practice session with selected ship, map and number of laps.

        You can either use this command to practice for the current race with the ship you are registered with
        by giving no arguments, practice for the current race with a specified ship (one argument), or select the ship,
        the map and the number of laps (3 arguments). See the examples below.

        Arguments:
        Ship:
        - a, aw, awing, a-wing: A-wing
        - x, xw, xwing, x-wing: X-wing
        - y, yw, ywing, y-wing: Y-wing
        - i, ti, tiein, tieinterceptor: TIE/IN Interceptor
        - f, tf, tieln, tiefighter: TIE/LN Fighter
        - b, tb, tiesa, tiebomber: TIE/SA Bomber
        Map:
        - f, fostar, fostarhaven: Fostar Haven
        - y, yavin, yavinprime: Yavin Prime
        - e, esseles: Esseles
        - n, nadiri, nadiridockyard, nadiridockyards: Nadiri Dockyards
        - s, sissubo:  Sissubo
        - g, galitan:  Galitan
        - z, zavian, zavianabyss: Zavin Abyss
        Laps:
        - Enter a number of laps between 5 and 10

        Examples:
        - $race_practice
        Practice for the current race map and laps with the ship you are registered with.
        This command only works if you are registered for the race.

        - $race_practice x
        Practice for the current race map and laps with the X-Wing

        - $race_practice a e 10
        Practice with the A-Wing at Esseles for 10 laps
        """

        ship_id = helper.parse_input_arg_ships(ship_argument)
        map_id = helper.parse_input_arg_maps(map_argument)
        if ship_id < 0 or map_id < 0 or laps > 10 or laps < 5:
            race_info = await self.get_race_info()
            entry_list = await self.get_race_result(race_info['race_id'])
            entry_list_dict = helper.record_to_dict(entry_list, 'discord_uid')
            entry = entry_list_dict.get(ctx.author.id)
            already_registered = entry is not None

            if map_id >= 0 and laps < 0:
                await ctx.send('Invalid arguments.\n'
                               'Type "$help race_practice" for more info.')
                return     

            if already_registered and ship_id < 0:
                ship_id = entry['ship_id']
            if map_id < 0:
                map_id = race_info['map_id']
            if laps < 0:
                laps = race_info['laps']  

            if ship_id < 0:
                await ctx.send('You need to specify a ship as you are not registered for the next race.\n'
                               'Type "$help race_practice" for more info.')
                return          

        map_info = self.maps_info_dict[map_id]
        user_hangar_dict = helper.record_to_dict(await self.get_user_hangar_info(ctx.author.id), 'ship_id')
        ship_info = user_hangar_dict.get(ship_id)
        sector_time, _ = self.simulate_sector(map_info, ship_info)
        ideal_lap_time = sector_time * map_info['corners']
        lap_times = []
        lap_strings = []
        for lap in range(1, laps + 1):
            lap_time = ideal_lap_time + random.uniform(0.0, ideal_lap_time * 0.1)
            lap_times += [lap_time]
            lap_strings += ['Lap {}: {}'.format(lap, helper.lap_time_to_string(lap_time))]
        best_lap = min(lap_times)
        avg_lap = sum(lap_times) / laps

        embed = discord.Embed(title='Practice session report', description='{}\n{}\n{}'.format(
            ship_info['display_name'],
            self.components_info_dict[ship_info['engine_component_id']]['display_name'],
            self.components_info_dict[ship_info['hull_component_id']]['display_name']), color=map_info['color'])
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
        embed.set_thumbnail(url=map_info['image_url'])            
        embed.add_field(name='Session info', value='Map: {}\nLaps: {}'.format(map_info['display_name'], laps), inline=False)
        embed.add_field(name='Your lap times', value='\n'.join(lap_strings), inline=False)
        embed.add_field(name='Your best lap', value='{}'.format(helper.lap_time_to_string(best_lap)), inline=False)
        embed.add_field(name='Your average lap time', value='{}'.format(helper.lap_time_to_string(avg_lap)), inline=False)
        await ctx.author.send(embed=embed)
        await ctx.send('Practice session done, check your PM to see the report.', delete_after=10)

    @race_practice.error
    async def race_practice_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) or \
           isinstance(error, commands.TooManyArguments) or \
           isinstance(error, commands.BadArgument):
            await ctx.send('Invalid arguments. Type "$help race_practice" for more info.')
        else:
            await ctx.send("Something went wrong while running the command!", delete_after=10)
            await helper.bot_log(self.client, error, ctx.message)
    
    async def show_maps(self, ctx, map_id: int = 0, only_show_one_map: bool = False, embed: discord.Embed = None):
        await self.load_fixed_data()
        current_index = 0
        current_embed = embed
        for idx, map_info in enumerate(self.maps_info):
            if map_info['map_id'] == map_id:
                current_index = idx

        if only_show_one_map:
            emoji_list = ['↩']
        else:
            emoji_list = ['◀', '▶', '🛑']

        async def build_race_maps_embed(map_info) -> discord.Embed:
            def build_data_field(embed: discord.Embed, title: str, value: int, max_value: int):
                embed.add_field(name=title, value='{} {}'.format(helper.get_progress_bar(value, max_value), value), inline=False)

            lap_length = self.get_map_lap_length(map_info)
            embed = discord.Embed(title=map_info['display_name'], description=map_info['description'], color=map_info['color'])
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)
            embed.set_thumbnail(url=map_info['image_url'])
            embed.add_field(name='Length', value='{:,} m'.format(lap_length), inline=False)
            embed.add_field(name='Corners', value='{}'.format(map_info['corners']), inline=False)
            if map_info['lap_record'] is None:
                embed.add_field(name='Lap record', value='N/A', inline=False)
            else:
                embed.add_field(name='Lap record', value='{}: {}'.format(
                    helper.get_member_mention(self.guild, map_info['lap_record_uid']),
                    helper.lap_time_to_string(map_info['lap_record'])), inline=False)
            build_data_field(embed, 'Speed', map_info['speed_factor'], 10)
            build_data_field(embed, 'Twistiness', map_info['maneuverability_factor'], 10)
            build_data_field(embed, 'Crash probability', map_info['pe_factor'], 10)
            build_data_field(embed, 'Kill probability', map_info['kill_factor'], 10)
            embed.set_footer(text=f'Page {list(self.maps_info).index(map_info) + 1}/{len(self.maps_info)}')
            return embed

        embeds = [await build_race_maps_embed(map_info) for map_info in self.maps_info]
        if current_embed is None:
            current_embed = await ctx.send(embed=embeds[current_index])
        else:
            await current_embed.edit(embed=embeds[current_index])

        for e in emoji_list:
            await current_embed.add_reaction(e)

        async def reaction_waiter() -> str:
            """Async helper to await for reactions"""

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in emoji_list \
                       and r.message.id == current_embed.id
            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                return 'Timeout'
            return str(reaction.emoji)

        while True:
            user_input = await reaction_waiter()
            # Previous Page - Loopable
            if user_input == '◀':
                await current_embed.remove_reaction(user_input, ctx.author)
                current_index = (current_index - 1) % len(embeds)
                await current_embed.edit(embed=embeds[current_index])
            # Next Page - Loopable
            elif user_input == '▶':
                await current_embed.remove_reaction(user_input, ctx.author)
                current_index = (current_index + 1) % len(embeds)
                await current_embed.edit(embed=embeds[current_index])
            # No response or STOP
            else:
                await current_embed.clear_reactions()
                if not only_show_one_map:
                    await asyncio.sleep(30)
                    await current_embed.delete()
                break

    # Commands
    @commands.command(aliases=['map'])
    async def maps(self, ctx, map_argument: str = 'fostarhaven'):
        """Shows information about the maps.

        You can specify the map as argument to avoid scrolling through the maps.

        Arguments:
        - f, fostar, fostarhaven: Shows Fostar Haven first
        - y, yavin, yavinprime: Shows Yavin Prime first
        - e, esseles: Shows Esseles first
        - n, nadiri, nadiridockyard, nadiridockyards: Shows Nadiri Dockyards first
        - s, sissubo:  Shows Sissubo first
        - g, galitan:  Shows Galitan first
        - z, zavian, zavianabyss: Shows Zavin Abyss first

        Examples:
        - $maps
        Shows the maps       

        - $maps nadiri
        Shows Nadiri Dockyards first
        """
        map_id = helper.parse_input_arg_maps(map_argument)
        if map_id < 0:
            await ctx.send(f'Invalid argument: {map_argument}\nType "$help maps" for more info.')
            return            

        await self.show_maps(ctx, map_id)

    @maps.error
    async def maps_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)

    # Commands
    @commands.command(aliases=['ship', 'ships'])
    async def hangar(self, ctx, ship_argument: str = 'a-wing'):
        """Shows your ships and lets you edit the loadouts

        You can specify the ship as argument to avoid scrolling through the hangar.

        Arguments:
        - a, aw, awing, a-wing: Shows the A-wing first
        - x, xw, xwing, x-wing: Shows the X-wing first
        - y, yw, ywing, y-wing: Shows the Y-wing first
        - i, ti, tiein, tieinterceptor: Shows the TIE/IN Interceptor first
        - f, tf, tieln, tiefighter: Shows the TIE/LN Fighter first
        - b, tb, tiesa, tiebomber: Shows the TIE/SA Bomber first

        Examples:
        - $hangar
        Shows your ships

        - $hangar xw
        Shows the X-wing first
        """
        ship_id = helper.parse_input_arg_ships(ship_argument)
        if ship_id < 0:
            await ctx.send(f'Invalid argument: {ship_argument}\nType "$help hangar" for more info.')
            return

        await self.show_hangar(ctx, ship_id)

    @hangar.error
    async def hangar_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)

    @commands.command()
    async def race_lb(self, ctx):
        """Shows the race leaderboard"""
        leaderboard = await self.get_leaderboard()
        if leaderboard:
            menu = menus.MenuPages(source=RaceLb(self, ctx, leaderboard), clear_reactions_after=True)
            await menu.start(ctx)
            await ctx.message.delete()
        else:
            await ctx.send('Leaderboard is empty, come back after the first race!')

    @race_lb.error
    async def race_lb_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)

    @commands.command(aliases=['race_stat'])
    async def race_stats(self, ctx, user: discord.Member = None):
        """$race_stats @user"""
        emoji_list = ['◀', '▶', '🛑']
        sent_embed = None
        current_page_idx = 0
        pages = []

        if user is None:
            user = ctx.author

        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                all_kills_disables = await connection.fetch(
                    """SELECT kills, disables FROM gray.racing_results
                    WHERE discord_uid = $1 AND position IS NOT NULL""",
                    user.id)

                avg_sum_results = await connection.fetchrow(
                    """SELECT discord_uid, 
                    COUNT(race_id) AS participation_count,
                    SUM(is_alive::int) AS finished_count,
                    AVG(position) AS avg_position, 
                    SUM(CASE position WHEN 1 THEN 1 ELSE 0 END) AS wins, 
                    SUM(CASE WHEN position<4 AND is_alive=1 THEN 1 ELSE 0 END) AS podiums, 
                    SUM(is_first_in_class::int) AS class_wins,
                    SUM(is_race_best_lap::int) AS race_best_laps_count,
                    MAX(participation_streak) AS max_participation_streak, 
                    MAX(finishing_streak) AS max_finishing_streak, 

                    AVG(entry_bet_credits) AS avg_entry_bet_credits, MAX(entry_bet_credits) AS max_entry_bet_credits, 
                    AVG(bonus) AS avg_bonus, MAX(bonus) AS max_bonus, 
                    AVG(jackpot) AS avg_jackpot, MAX(jackpot) AS max_jackpot,
                    AVG(gain_credits) AS avg_gain, MAX(gain_credits) AS max_gain,
                    AVG(gain_credits - entry_bet_credits) AS avg_net_gain, MAX(gain_credits - entry_bet_credits) AS max_net_gain,

                    AVG(shield_damage_dealt) AS avg_shield_damage_dealt, MAX(shield_damage_dealt) AS max_shield_damage_dealt, 
                    AVG(hull_damage_dealt) AS avg_hull_damage_dealt, MAX(hull_damage_dealt) AS max_hull_damage_dealt, 
                    AVG(ioning_damage_dealt) AS avg_ioning_damage_dealt, MAX(ioning_damage_dealt) AS max_ioning_damage_dealt, 
                    SUM(is_race_most_damage::int) AS race_most_damage_count

                    FROM gray.racing_results
                    WHERE discord_uid = $1 AND position IS NOT NULL
                    GROUP BY discord_uid""",
                    user.id)

                most_used_ship = await connection.fetchrow(
                    """SELECT ship_id, 
                    COUNT(ship_id) AS ship_id_count
                    FROM gray.racing_results
                    WHERE discord_uid = $1 AND position IS NOT NULL
                    GROUP BY ship_id 
                    ORDER BY ship_id_count DESC
                    LIMIT 1""",
                    user.id)

                current_streaks = await connection.fetchrow(
                    """SELECT participation_streak AS current_participation_streak,
                    finishing_streak AS current_finishing_streak
                    FROM gray.racing_results
                    WHERE discord_uid = $1 AND position IS NOT NULL
                    ORDER BY race_id DESC
                    LIMIT 1""",
                    user.id)

                all_kills = []
                all_disables = []
                most_kills = 0
                most_disables = 0
                for kills_disables in all_kills_disables:
                    all_kills += kills_disables['kills']
                    if len(kills_disables['kills']) > most_kills:
                        most_kills = len(kills_disables['kills'])

                    all_disables += kills_disables['disables']
                    if len(kills_disables['disables']) > most_disables:
                        most_disables = len(kills_disables['disables'])

                async def generate_racing_stats_embed(participation_count: int, finished_count: int, class_wins: int, wins: int,
                                                      podiums: int, avg_position: float, race_best_laps_count: int, 
                                                      most_used_ship_name: str, most_used_ship_count: int, 
                                                      current_participation_streak: int, max_participation_streak: int,
                                                      current_finishing_streak: int, max_finishing_streak: int,) -> discord.Embed:
                    embed = discord.Embed(title='Racing Stats', description='', colour=user.colour)
                    embed.set_author(name=user.display_name, icon_url=user.avatar_url)
                    embed.add_field(name='Races finished', value='{} / {} ({:.1f}%)'.format(finished_count, participation_count, 
                                                                                            finished_count / participation_count * 100), inline=True)
                    embed.add_field(name='Wins', value='{} / {} ({:.1f}%)'.format(wins, participation_count, 
                                                                                  wins / participation_count * 100), inline=True)
                    embed.add_field(name='Class wins', value='{} / {} ({:.1f}%)'.format(class_wins, participation_count, 
                                                                                  class_wins / participation_count * 100), inline=True)
                    embed.add_field(name='Podiums', value='{} / {} ({:.1f}%)'.format(podiums, participation_count, 
                                                                                     podiums / participation_count * 100), inline=True)
                    embed.add_field(name='Average position', value='{:.2f}'.format(avg_position), inline=True)
                    embed.add_field(name='Race best laps', value='{} / {} ({:.1f}%)'.format(race_best_laps_count, participation_count, 
                                                                                       race_best_laps_count / participation_count * 100), inline=True)
                    embed.add_field(name='Most used ship', value='{}\n{} races'.format(most_used_ship_name,
                                                                                        most_used_ship_count), inline=True)
                    embed.add_field(name='Participation streak', value='Current: {}\nBest: {}'.format(current_participation_streak,
                                                                                                      max_participation_streak), inline=True)
                    embed.add_field(name='Finishing streak', value='Current: {}\nBest: {}'.format(current_finishing_streak,
                                                                                                  max_finishing_streak), inline=True)
                    embed.set_footer(text='Page 1/3')
                    return embed

                async def generate_credits_stats_embed(avg_entry_bet_credits: int, max_entry_bet_credits: int, 
                                                       avg_bonus: int, max_bonus: int,
                                                       avg_jackpot: int, max_jackpot: int, 
                                                       avg_gain: str, max_gain: int, 
                                                       avg_net_gain: int, max_net_gain: int) -> discord.Embed:

                    def build_avg_max_field(embed: discord.Embed, title: str, avg_value: int, max_value: int):
                        embed.add_field(name=title, value='Average: {}\nMax: {}'.format(helper.credits_to_string(avg_value), 
                                                                                        helper.credits_to_string(max_value)), inline=True)
                    embed = discord.Embed(title='Credits Stats', description='', colour=user.colour)
                    embed.set_author(name=user.display_name, icon_url=user.avatar_url)
                    build_avg_max_field(embed, 'Entry Bet', avg_entry_bet_credits, max_entry_bet_credits)
                    build_avg_max_field(embed, 'Bonus',avg_bonus, max_bonus)
                    build_avg_max_field(embed, 'Jackpot',avg_jackpot, max_jackpot)
                    build_avg_max_field(embed, 'Gain',avg_gain, max_gain)
                    build_avg_max_field(embed, 'Net Gain', avg_net_gain, max_net_gain)
                    embed.set_footer(text='Page 2/3')
                    return embed

                async def generate_damage_stats_embed(avg_shield_damage_dealt: int, max_shield_damage_dealt: int, 
                                                       avg_hull_damage_dealt: int, max_hull_damage_dealt: int,
                                                       avg_ioning_damage_dealt: int, max_ioning_damage_dealt: int, 
                                                       avg_kills: float, max_kills: int, 
                                                       avg_disables: float, max_disables: int, 
                                                       race_most_damage_count: int, participation_count: int) -> discord.Embed:

                    def build_avg_max_field(embed: discord.Embed, title: str, avg_value: int, max_value: int, presicion:int = 0):
                        embed.add_field(name=title, value='Average: {0:,.{2}f}\nMax: {1:,.0f}'.format(avg_value, 
                                                                                        max_value,
                                                                                        presicion), 
                                                                                        inline=True)
                    embed = discord.Embed(title='Damage Stats', description='', colour=user.colour)
                    embed.set_author(name=user.display_name, icon_url=user.avatar_url)
                    build_avg_max_field(embed, 'Shield damage dealt', avg_shield_damage_dealt, max_shield_damage_dealt)
                    build_avg_max_field(embed, 'Hull damage dealt', avg_hull_damage_dealt, max_hull_damage_dealt)
                    build_avg_max_field(embed, 'Ion damage dealt', avg_ioning_damage_dealt, max_ioning_damage_dealt)
                    build_avg_max_field(embed, 'Kills', avg_kills, max_kills, 2)
                    build_avg_max_field(embed, 'Disables', avg_disables, max_disables, 2)
                    embed.add_field(name='Race most damage dealt', value='{} / {} ({:.1f}%)'.format(race_most_damage_count, participation_count, 
                                                                                       race_most_damage_count / participation_count * 100), inline=True)
                    embed.set_footer(text='Page 3/3')
                    return embed

                pages = [await generate_racing_stats_embed(avg_sum_results['participation_count'], 
                                                            avg_sum_results['finished_count'], 
                                                            avg_sum_results['class_wins'], 
                                                            avg_sum_results['wins'], 
                                                            avg_sum_results['podiums'], 
                                                            avg_sum_results['avg_position'], 
                                                            avg_sum_results['race_best_laps_count'], 
                                                            self.ships_info_dict[most_used_ship['ship_id']]['display_name'], 
                                                            most_used_ship['ship_id_count'],
                                                            current_streaks['current_participation_streak'],
                                                            avg_sum_results['max_participation_streak'], 
                                                            current_streaks['current_finishing_streak'],
                                                            avg_sum_results['max_finishing_streak']),
                          await generate_credits_stats_embed(avg_sum_results['avg_entry_bet_credits'], 
                                                             avg_sum_results['max_entry_bet_credits'], 
                                                             avg_sum_results['avg_bonus'], 
                                                             avg_sum_results['max_bonus'], 
                                                             avg_sum_results['avg_jackpot'], 
                                                             avg_sum_results['max_jackpot'], 
                                                             avg_sum_results['avg_gain'], 
                                                             avg_sum_results['max_gain'], 
                                                             avg_sum_results['avg_net_gain'], 
                                                             avg_sum_results['max_net_gain']),
                          await generate_damage_stats_embed(avg_sum_results['avg_shield_damage_dealt'], 
                                                            avg_sum_results['max_shield_damage_dealt'], 
                                                            avg_sum_results['avg_hull_damage_dealt'], 
                                                            avg_sum_results['max_hull_damage_dealt'], 
                                                            avg_sum_results['avg_ioning_damage_dealt'], 
                                                            avg_sum_results['max_ioning_damage_dealt'], 
                                                            len(all_kills) / avg_sum_results['participation_count'], 
                                                            most_kills,
                                                            len(all_disables) / avg_sum_results['participation_count'], 
                                                            most_disables,
                                                            avg_sum_results['race_most_damage_count'], 
                                                            avg_sum_results['participation_count'])]

        sent_embed = await ctx.send(embed=pages[current_page_idx])
        for e in emoji_list:
            await sent_embed.add_reaction(e)

        async def reaction_waiter() -> str:
            """Async helper to await for reactions"""

            def check(r, u):
                # R = Reaction, U = User
                return u == ctx.author \
                       and str(r.emoji) in emoji_list \
                       and r.message.id == sent_embed.id

            try:
                reaction, _ = await self.client.wait_for('reaction_add', check=check, timeout=60)
            except asyncio.TimeoutError:
                return 'Timeout'
            return str(reaction.emoji)

        while True:
            user_input = await reaction_waiter()
            # Previous Page - Loopable
            if user_input == '◀':
                await sent_embed.remove_reaction(user_input, ctx.author)
                current_page_idx = (current_page_idx - 1) % len(pages)
                await sent_embed.edit(embed=pages[current_page_idx])
            # Next Page - Loopable
            elif user_input == '▶':
                await sent_embed.remove_reaction(user_input, ctx.author)
                current_page_idx = (current_page_idx + 1) % len(pages)
                await sent_embed.edit(embed=pages[current_page_idx])
            # No response or STOP
            else:
                await sent_embed.clear_reactions()
                await asyncio.sleep(30)
                await sent_embed.delete()
                return

    @race_stats.error
    async def race_stats_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)

    @commands.command()
    async def race_report(self, ctx, argument):
        """Subscribe or unsubscribe to the personal race report."""
        argLowerCase = argument.lower()
        if argLowerCase == 'subscribe':
            subscribe = True
        elif argLowerCase == 'unsubscribe':
            subscribe = False
        else:
            await ctx.send('Invalid argument. Use either "$race_report subscribe" or "$race_report unsubscribe".')
            return

        current_subscription = await self.is_user_subscribed_to_race_report(ctx.author.id)
        if subscribe == current_subscription:
            if subscribe:
                await ctx.send('You are already subscribed to the personal race report.\n')
            else:
                await ctx.send('You are already unsubscribed from the personal race report.')
        else:
            await self.save_user_subscription_to_race_report(ctx.author.id, subscribe)
            if subscribe:
                await ctx.send('You have been successfully subscribed to the personal race report.\n')
            else:
                await ctx.send('You have been successfully unsubscribed from the personal race report.\n')

    @race_report.error
    async def race_report_error(self, ctx, error):
        await ctx.send("Something went wrong while running the command!", delete_after=10)
        await helper.bot_log(self.client, error, ctx.message)

class RaceLb(menus.ListPageSource):
    def __init__(self, racing, ctx, data):
        self.ctx = ctx
        self.racing = racing
        super().__init__(data, per_page=10)

    async def write_page(self, offset, fields=None):
        if fields is None:
            fields = []
        len_data = len(self.entries)
        embed = discord.Embed(title="Racing Leaderboard", description="Fastest and deadliest pilots in the galaxy!", colour=self.ctx.author.colour)
        embed.set_thumbnail(url='https://media.discordapp.net/attachments/800431166997790790/840009740855934996/gray_squadron_logo.png')
        embed.set_footer(text=f"{offset:,} - {min(len_data, offset+self.per_page-1):,} of {len_data:,}.")
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
        return embed

    async def format_page(self, menu, entries):
        def get_rank(idx: int) -> str:
            if idx == 1:
                return '🥇'
            elif idx == 2:
                return '🥈'
            elif idx == 3:
                return '🥉'
            else:
                return '{}'.format(idx)

        offset = (menu.current_page * self.per_page) + 1
        fields = []
        table = "\n".join(f"{get_rank(idx+offset)}. {helper.get_member_display_name(self.racing.guild, entry[0])} - {entry[1]:,} pts" for idx, entry in enumerate(entries))
        fields.append(("Rank", table))
        return await self.write_page(offset, fields)

def setup(client):
    client.add_cog(Racing(client))