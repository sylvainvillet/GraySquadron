import json
import discord
import math
from datetime import timedelta


def get_config(key):
    """Get a key value pair in config.json"""
    with open('config.json', 'r') as f:
        configs = json.load(f)
    return configs[str(key)]


def set_value(key: str, value):
    """Set a key value pair in config.json"""
    with open('config.json', 'r+') as f:
        config = json.load(f)
        config[key] = value
        f.seek(0)
        json.dump(config, f, indent=3)
        f.truncate()


async def get_roster(self, column: str, value: int):
    """Return fo or discord_uid given the other value"""
    async with self.client.pool.acquire() as connection:
        async with connection.transaction():
            res = 0
            if column == 'discord_uid':
                res = await connection.fetchval('SELECT discord_uid FROM gray.roster Where fo = $1', value)
            elif column == 'fo':
                res = await connection.fetchval('SELECT fo FROM gray.roster Where discord_uid = $1', value)
            return res


async def set_fo(self, fo: int, discord_uid: int):
    """Set target fo to target discord uid"""
    async with self.client.pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute('UPDATE gray.roster SET discord_uid = $2 WHERE fo = $1', fo, discord_uid)


async def get_whole_roster(self):
    """Get entire roster as a list"""
    async with self.client.pool.acquire() as connection:
        async with connection.transaction():
            roster = await connection.fetch('SELECT * FROM gray.roster ORDER BY fo')
            return roster


def record_to_dict(f_record, key_name: str):
    """Converts a fetched record into a dictionary"""
    return_dict = {}
    for record in f_record:
        key = ''
        for f, v in record.items():
            if f == key_name:
                key = v
            else:
                try:
                    return_dict[key].update({f: v})
                except KeyError:
                    return_dict[key] = {f: v}
    return return_dict

def record_to_list(f_record) -> []:
    """Converts a fetched record into a list"""
    return_list = []
    for record in f_record:
        return_list += record
    return return_list

def get_member_display_name(guild, discord_uid: int) -> str:
    member = guild.get_member(discord_uid)
    if member is None:
        return 'Unknown user'
    else:
        return member.display_name

def get_member_mention(guild, discord_uid: int):
    member = guild.get_member(discord_uid)
    if member is None:
        return 'Unknown user'
    else:
        return member.mention

def join_with_and(values, last_word: str = 'and') -> str:
    """Same as ', '.join() but with ' and ' between the last 2 values"""
    valuesList = list(values)
    length = len(valuesList)

    # value1, value2, value3 and value4
    if length > 2:
        return '{} {} {}'.format(', '.join(valuesList[:-1]), last_word, valuesList[-1])
    # value1 and value2
    elif length == 2:
        return '{} {} {}'.format(valuesList[0], last_word, valuesList[1])
    # value 1
    elif length == 1:
        return valuesList[0]
    # Empty
    return ''

def join_with_or(values) -> str:
    """Same as ', '.join() but with ' and ' between the last 2 values"""
    return join_with_and(values, 'or')

def is_valid_card_number_format(s: str) -> bool:
    # Between 5 and 7 digits, can have a letter at the end
    length = len(s)
    if 5 <= length <= 7:
        try:
            int(s)
            return True
        except ValueError:
            try:
                int(s[:length-1])
                return s[length-1:] in ['A', 'B', 'C', 'D']
            except Exception as e:
                return False
            return False
    else:
        return False

async def parse_input_args_filters(ctx, commands, args) -> (discord.Member, bool, str, list, list, list):
    """Parses the args looking for Discord user, "all", affiliation, rarity and card codes"""
    user = None
    has_all = False
    group_by_key = 'set_code'
    affiliation_names = []
    rarity_codes = []
    card_codes = []

    # Parse all the arguments
    for arg in args:
        # Check if the argument is a user
        try:
            converter = commands.MemberConverter()
            user = await converter.convert(ctx=ctx, argument=arg)
        # Check if the argument is an affiliation
        except commands.errors.MemberNotFound:
            argLowerCase = arg.lower()
            if argLowerCase == 'all':
                has_all = True
            elif argLowerCase in ['a', 'affiliation', 'affiliations']:
                group_by_key = 'affiliation_name'
            elif argLowerCase in ['f', 'faction', 'factions']:
                group_by_key = 'faction_name'
            elif argLowerCase in ['rar', 'rarity']:
                group_by_key = 'rarity_code'
            elif argLowerCase in ['nogroup', 'nogroups']:
                group_by_key = ''
            elif argLowerCase in ['v', 'villain', 'villains']:
                affiliation_names.append('Villain')
            elif argLowerCase in ['h', 'hero', 'heroes']:
                affiliation_names.append('Hero')
            elif argLowerCase in ['n', 'neutral', 'neutrals']:
                affiliation_names.append('Neutral')
            elif argLowerCase in ['s', 'starter', 'starters']:
                rarity_codes.append('S')
            elif argLowerCase in ['c', 'common']:
                rarity_codes.append('C')
            elif argLowerCase in ['u', 'uncommon']:
                rarity_codes.append('U')
            elif argLowerCase in ['r', 'rare']:
                rarity_codes.append('R')
            elif argLowerCase in ['l', 'legendary']:
                rarity_codes.append('L')
            elif is_valid_card_number_format(arg):
                card_codes.append(arg)
            else:
                raise ValueError('Invalid argument: {}'.format(arg))

    if card_codes and (has_all or affiliation_names or rarity_codes):
        raise ValueError('Invalid arguments. You can\'t mix card numbers and batch.')
    elif has_all and (affiliation_names or rarity_codes):
        raise ValueError('Invalid arguments. Use either \"all\" or affiliation/rarity name but not both.')

    return user, has_all, group_by_key, affiliation_names, rarity_codes, card_codes

def parse_input_arg_ships(arg) -> int:
    """Parses the args looking for a ship name
    Returns the ship_id if found, -1 otherwise"""

    ship_id = 0
    argLowerCase = arg.lower()
    if argLowerCase in ['a', 'aw', 'awing', 'a-wing']:
        ship_id = 0
    elif argLowerCase in ['x', 'xw', 'xwing', 'x-wing']:
        ship_id = 1
    elif argLowerCase in ['y', 'yw', 'ywing', 'y-wing']:
        ship_id = 2
    elif argLowerCase in ['i', 'ti', 'tiein', 'tieinterceptor']:
        ship_id = 3
    elif argLowerCase in ['f', 'tf', 'tieln', 'tiefighter']:
        ship_id = 4
    elif argLowerCase in ['b', 'tb', 'tiesa', 'tiebomber']:
        ship_id = 5
    else:
        return -1
    return ship_id

def parse_input_arg_maps(arg) -> int:
    """Parses the args looking for a maps name
    Returns the map_id if found, -1 otherwise"""

    map_id = 0
    argLowerCase = arg.lower()
    if argLowerCase in ['f', 'fostar', 'fostarhaven']:
        map_id = 0
    elif argLowerCase in ['y', 'yavin', 'yavinprime']:
        map_id = 1
    elif argLowerCase in ['e', 'esseles']:
        map_id = 2
    elif argLowerCase in ['n', 'nadiri', 'nadiridockyard', 'nadiridockyards']:
        map_id = 3
    elif argLowerCase in ['s', 'sissubo']:
        map_id = 4
    elif argLowerCase in ['g', 'galitan']:
        map_id = 5
    elif argLowerCase in ['z', 'zavian', 'zavianabyss']:
        map_id = 6
    else:
        return -1
    return map_id

def parse_amount(amount: str) -> int:
    """Parses the amount that can be either and integer, or something like "10k", "1.2M", etc..."""
    amountLowerCase = amount.lower().replace('c', '')

    exp = 0
    if amountLowerCase.endswith('k'):
        exp = 3
    elif amountLowerCase.endswith('m'):
        exp = 6
    elif amountLowerCase.endswith('g'):
        exp = 9
    elif amountLowerCase.endswith('t'):
        exp = 12
    elif amountLowerCase.endswith('p'):
        exp = 15
    elif amountLowerCase.endswith('e'):
        exp = 18
    elif amountLowerCase.endswith('z'):
        exp = 21
    elif amountLowerCase.endswith('y'):
        exp = 24

    if exp == 0:
        return int(amountLowerCase)
    else:
        return int(float(amountLowerCase[:len(amountLowerCase)-1])*10**exp)

def credits_to_string(amount: int, significant_numbers: int = 3) -> str:
    """Returns "XXX'XXX" C if under a million, otherwise "XXX MC" """
    letter = ''
    divider = 1
    absAmount = abs(amount)

    if absAmount >= 10**24:
        letter = 'Y'
        divider = 10**24
    if absAmount >= 10**21:
        letter = 'Z'
        divider = 10**21
    if absAmount >= 10**18:
        letter = 'E'
        divider = 10**18
    elif absAmount >= 10**15:
        letter = 'P'
        divider = 10**15
    elif absAmount >= 10**12:
        letter = 'T'
        divider = 10**12
    elif absAmount >= 10**9:
        letter = 'G'
        divider = 10**9
    elif absAmount >= 10**6:
        letter = 'M'
        divider = 10**6
        
    if divider == 1:
        return '{:,} C'.format(int(amount))
    if amount >= 10**27:
        return '{:,} {}C'.format(int(amount / divider), letter)
    else:
        power_of_10 = max(0,int(math.floor(math.log10(absAmount))))
        precision = significant_numbers - 1 - (power_of_10 % 3)
        return '{1:.{0}f} {2}C'.format(precision,
            math.floor(amount / 10**(power_of_10 - significant_numbers + 1)) / 10**precision, 
            letter)

def credits_to_string_with_exact_value(amount: int, separator: str = ' ', significant_numbers: int = 3) -> str:
    """Returns "XXX'XXX" C if under a million, otherwise "XXX MC (XXX'XXX'XXX C)" """
    if amount >= 10**6:
        return '{}{}({:,} C)'.format(credits_to_string(amount), separator, amount)
    else:
        return '{:,} C'.format(amount)

async def bot_log(client: discord.client, error: str, message: discord.Message = None):
    # Print the error in the console, then in #bot-logs channel if it exists
    error_message = '{}{}'.format(
            '{} in #{}: "{}": '.format(
                message.author.display_name, 
                message.channel,
                message.content) if message is not None else '', 
            error);

    # Console
    print(error_message)

    # Discord channel
    channel_name = 'bot-logs'
    guild = client.get_guild(get_config('guild_id'))
    log_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if log_channel:
        await log_channel.send(error_message)

def race_time_to_string(time: int) -> str:
    '''XX:XX.XXX'''
    return str(timedelta(seconds=time))[2:-3]

def lap_time_to_string(time: int) -> str:
    '''X:XX.XXX'''
    return str(timedelta(seconds=time))[3:-3]

def get_progress_bar(value: int, max_value: int, offset: int = 0) -> str:
    """Value is the actual position, offset = value - base_value"""
    offset = int(round(offset))
    base_value = int(round((value - offset) / max_value * 10))
    if base_value > 10:
        base_value = 10
    elif base_value < 0:
        base_value = 0
    value = value / max_value * 10

    # Force at least one green/red square if offset not 0
    if offset > 0:
        value = int(math.ceil(value))
        if value == base_value:
            value += 1
    elif offset < 0:
        value = int(math.floor(value))
        if value == base_value:
            value -= 1
    else:
        value = int(round(value))

    if value > 10:
        value = 10
    elif value < 0:
        value = 0

    output = ''
    if base_value < value:
        for i in range(0, base_value):
            output += '⬜'
        for i in range(base_value, value):
            output += '🟩'
        for i in range(value, 10):
            output += '⬛'
    elif base_value > value:
        for i in range(0, value):
            output += '⬜'
        for i in range(value, base_value):
            output += '🟥'
        for i in range(base_value, 10):
            output += '⬛'
    else:
        for i in range(0, value):
            output += '⬜'
        for i in range(value, 10):
            output += '⬛'

    return output

def add_splittable_field(embed: discord.Embed, name: str, valuesList: [], inline: bool = False):
    if len('\n'.join(valuesList)) > 1000:
        nbOfValues = len(valuesList)
        splitted_lists = [valuesList[x:x+10 if x+10 <= nbOfValues else nbOfValues] for x in range(0, nbOfValues, 10)]
        for idx, sub_list in enumerate(splitted_lists):
            value = '\n'.join(sub_list);
            embed.add_field(name='{} ({}/{})'.format(name, idx + 1, len(splitted_lists)), 
                value=value, inline=inline)
    else:    
        embed.add_field(name=name, value='\n'.join(valuesList), inline=inline)
