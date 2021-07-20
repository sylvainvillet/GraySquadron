import json


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
