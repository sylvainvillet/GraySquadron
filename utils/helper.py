import json
import discord


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

def join_with_and(values) -> str:
    """Same as ', '.join() but with ' and ' between the last 2 values"""
    valuesList = list(values)
    length = len(valuesList)

    # value1, value2, value3 and value4
    if length > 2:
        return ', '.join(valuesList[:-1]) + " and " + str(valuesList[-1])
    # value1 and value2
    elif length == 2:
        return ' and '.join(valuesList)
    # value 1
    elif length == 1:
        return valuesList[0]
    # Empty
    return ''

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

async def parse_input_args_filters(ctx, commands, args) -> (discord.Member, bool, list, list, list):
    """Parses the args looking for Discord user, "all", affiliation, rarity and card codes"""
    user = None
    has_all = False
    affiliation_codes = []
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
            elif argLowerCase in ['v', 'villain', 'villains']:
                affiliation_codes.append('villain')
            elif argLowerCase in ['h', 'hero', 'heroes']:
                affiliation_codes.append('hero')
            elif argLowerCase in ['n', 'neutral', 'neutrals']:
                affiliation_codes.append('neutral')
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

    if card_codes and (has_all or affiliation_codes or rarity_codes):
        raise ValueError('Invalid arguments. You can\'t mix card numbers and batch.')
    elif has_all and (affiliation_codes or rarity_codes):
        raise ValueError('Invalid arguments. Use either \"all\" or affiliation/rarity name but not both.')

    return user, has_all, affiliation_codes, rarity_codes, card_codes

def parse_amount(amount: str) -> int:
    """Parses the amount that can be either and integer, or something like "10k", "1.2M", etc..."""
    amountLowerCase = amount.lower()
    exp = 0
    if amountLowerCase.endswith('k'):
        exp = 3
    elif amountLowerCase.endswith('m'):
        exp = 6
    elif amountLowerCase.endswith('b'):
        exp = 9
    elif amountLowerCase.endswith('t'):
        exp = 12
    elif amountLowerCase.endswith('q'):
        exp = 15

    if exp == 0:
        return int(amount)
    else:
        return int(float(amount[:len(amount)-1])*10**exp)
