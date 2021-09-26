import re
import random
import typing
import contextlib
from dataclasses import dataclass, field as dataclass_field
import asyncio
import discord
from discord.ext import commands


BOT_QUOTES_CHANNEL_NAME = "bot-quotes"
QUOTE_EDIT_ROLES = "Commander", "Captain", "Lieutenant"


def without_url_brackets(url: str) -> str:
    """Strip <> brackets from url if present."""
    has_brackets = len(url) > 2 and url[0] == "<" and url[-1] == ">"
    return url[1:-1] if has_brackets else url


def with_url_brackets(url: str) -> str:
    """Add <> brackets to url if not present."""
    has_brackets = len(url) > 2 and url[0] == "<" and url[-1] == ">"
    return url if has_brackets else f"<{url}>"


async def get_bot_quotes_channel(bot: commands.Bot) -> discord.TextChannel:
    """Locate or create bot-quotes channel on server (assuming bot is registered to a single server)."""
    guild: discord.Guild = bot.guilds[0]
    channel: discord.TextChannel = \
        discord.utils.get(guild.text_channels, name=BOT_QUOTES_CHANNEL_NAME) \
        or await guild.create_text_channel(BOT_QUOTES_CHANNEL_NAME)
    return channel


@dataclass
class QuoteTopic:
    name: str
    urls: typing.List[str]
    backing_message: discord.Message

    RE_DEFINITION: typing.ClassVar[re.Pattern] = re.compile(r"QuoteTopic\s+(\w+)((?:\s+[^\s]+)*)")

    @staticmethod
    def from_message(message: discord.Message) -> typing.Optional["QuoteTopic"]:
        """Parse stored quote topic from discord message (return None on fail)."""
        m = QuoteTopic.RE_DEFINITION.match(message.content)
        if not m:
            return None
        name, urls = m.groups()
        urls = [without_url_brackets(u) for u in urls.split()]
        return QuoteTopic(name, urls, message)

    def serialize(self) -> str:
        formatted_urls = "\n".join(with_url_brackets(u) for u in self.urls)
        return f"""QuoteTopic {self.name}\n{formatted_urls}"""


@dataclass
class QuoteCollection:
    topics: typing.MutableMapping[str, QuoteTopic]
    backing_channel: discord.TextChannel
    channel_lock: asyncio.Lock = dataclass_field(default_factory=asyncio.Lock)

    def topic_names(self) -> typing.Sequence[str]:
        """Return list of topics that contain at least one quote."""
        return [t.name for t in self.topics.values() if len(t.urls) > 0]

    async def add_quote(self, name: str, url: str):
        """Add new quote to named topic and store changes on discord."""
        url = without_url_brackets(url)
        async with self.channel_lock:
            # Create empty topic if there is no entry for given topic name
            if name not in self.topics:
                backing_message = await self.backing_channel.send(content="...")
                self.topics[name] = QuoteTopic(
                    name=name, urls=[], backing_message=backing_message)
            # Add url to topic and store changes
            topic = self.topics[name]
            if url not in topic.urls:
                topic.urls.append(url)
                await topic.backing_message.edit(content=topic.serialize())

    async def remove_quote(self, name: str, url: str):
        """Remove quote from named topic and store changes on discord."""
        url = without_url_brackets(url)
        async with self.channel_lock:
            topic = self.topics.get(name, None)
            # Verify that the url to be removed exists
            if topic is None or url not in topic.urls:
                return
            # Remove url from topic and store changes
            topic.urls.remove(url)
            if len(topic.urls) > 0:
                await topic.backing_message.edit(content=topic.serialize())
            else:
                await topic.backing_message.delete()
                del self.topics[name]


async def load_quotes_from_discord(bot: commands.Bot) -> QuoteCollection:
    """Load quote collection from the bot-quotes channel on discord."""
    # Parse quotes from bot history, add '🤖' reaction to imported messages
    topics = {}
    backing_channel = await get_bot_quotes_channel(bot)
    async for message in backing_channel.history(limit=500, oldest_first=True):
        message: discord.Message = message
        if message.author != bot.user:
            continue
        await message.remove_reaction("🤖", bot.user)
        topic = QuoteTopic.from_message(message)
        if topic is not None:
            topics[topic.name] = topic
            await message.add_reaction("🤖")
    # Return parsed quotes as collection
    return QuoteCollection(topics=topics, backing_channel=backing_channel)


class Quotes(commands.Cog):

    def __init__(self, bot: commands.Bot):
        assert isinstance(bot, commands.Bot), "Require bot instance as client"
        self.bot = bot
        self.stack = contextlib.ExitStack()
        self.quote_collection: typing.Optional[QuoteCollection] = None

        init_task = asyncio.get_running_loop().create_task(self._initialize())
        self.stack.callback(init_task.cancel)

    def cog_unload(self):
        self.stack.close()

    async def _initialize(self):
        try:
            self.quote_collection = await load_quotes_from_discord(self.bot)
        except Exception as e:
            print(f"Failed initializing quotes: {e}")

    @commands.command(aliases=["q"])
    async def quote(
            self, ctx: commands.context.Context,
            name: typing.Optional[str] = None,
            pick: typing.Optional[int] = None,
    ):
        """Post quote for given topic."""
        topic = self.quote_collection and self.quote_collection.topics.get(name, None)
        if not topic or not topic.urls:
            await self.list_quotes(ctx)
        else:
            urls = topic.urls
            url = random.choice(urls) if pick is None else urls[pick % len(urls)]
            await ctx.send(url)

    @commands.command()
    async def list_quotes(self, ctx: commands.context.Context):
        """List available quotes."""
        topic_names = self.quote_collection and self.quote_collection.topic_names()
        if not topic_names:
            await ctx.send(f"No quotes available")
        else:
            await ctx.send(f"Available quotes:\n{', '.join(topic_names)}")

    @commands.command()
    @commands.has_any_role(*QUOTE_EDIT_ROLES)
    async def add_quote(self, ctx: commands.context.Context, name: str, url: str):
        """Add a new quote."""
        if self.quote_collection is None:
            return
        await self.quote_collection.add_quote(name, url)
        await ctx.send(f"Added quote to topic '{name}'")

    @commands.command()
    @commands.has_any_role(*QUOTE_EDIT_ROLES)
    async def remove_quote(self, ctx: commands.context.Context, name: str, url: str):
        """Remove an existing quote."""
        if self.quote_collection is None:
            return
        await self.quote_collection.remove_quote(name, url)
        await ctx.send(f"Removed quote from topic '{name}'")


def setup(client):
    client.add_cog(Quotes(client))

