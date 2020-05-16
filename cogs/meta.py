import discord
from discord.ext import commands, menus

from datetime import datetime as d
from string import Formatter
import traceback
import codecs
import os
import pathlib
import json
import sys
import asyncio
import inspect

from .utils.utils import wait_for_deletion
from .utils import db
from .utils.utils import hover_link
from .utils.checks import has_manage_guild


def strfdelta(tdelta, fmt):
    """
    Similar to strftime from datetime.datetime
    Returns formatted string of a timedelta
    """
    f = Formatter()
    d = {}
    lang = {"D": 86400, "H": 3600, "M": 60, "S": 1}
    k = map(lambda x: x[1], list(f.parse(fmt)))
    rem = int(tdelta.total_seconds())

    for i in ("D", "H", "M", "S"):
        if i in k and i in lang.keys():
            d[i], rem = divmod(rem, lang[i])

    return f.format(fmt, **d)


class HelpPages(menus.ListPageSource):
    def __init__(self, data, embed, prefix, more_info):
        self.embed_base = embed
        self.original_description = embed.description
        self.prefix = prefix
        self.more_info = more_info
        super().__init__(data, per_page=10)

    async def format_page(self, menu, entries):
        offset = menu.current_page * self.per_page
        em = self.embed_base
        em.description = self.original_description
        em.set_footer(text=f"Page {menu.current_page + 1}/{self.get_max_pages()}")
        command_info = []
        for i, command in enumerate(entries, start=offset):
            command_help = f"**`{self.prefix}"
            command_help += f"{command.parent} " if command.parent is not None else ""
            command_help += command.name
            command_help += (
                f" {command.usage}`**" if command.usage is not None else "`**"
            )
            if command.description:
                command_help += f" - {command.description}"
            command_info.append(command_help)
        formatted = "\n".join(command_info)
        em.description += f"\n\n{formatted}\n\n{self.more_info}"
        return em


class ClamHelpCommand(commands.HelpCommand):
    def i_category(self, ctx):
        return (
            "For **more info** on a **specific category**, "
            f"use: **`{self.context.bot.guild_prefix(self.context.guild)}help [category]`‍**"
        )

    def i_cmd(self, ctx):
        return (
            "For **more info** on a **specific command**, "
            f"use: **`{self.context.bot.guild_prefix(self.context.guild)}help [command]`‍**"
        )

    def arg_help(self):
        return "**Key:** `[required]` `<optional>`\n**Remove `[]` and `<>` when using the command.**"

    def get_base_embed(self):
        ctx = self.context
        bot = ctx.bot
        em = discord.Embed(
            title=f"Help for {bot.user.name}", color=0xFF95B0, timestamp=d.utcnow(),
        )
        em.set_thumbnail(url=ctx.bot.user.avatar_url)
        return em

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        em = self.get_base_embed()
        em.description = (
            f"{bot.description}\n\n"
            f"**Default Prefix: `{bot.guild_prefix(ctx.guild)}`** "
            f"Ex: `{bot.guild_prefix(ctx.guild)}help`\n"
            f"Use `{bot.guild_prefix(ctx.guild)}prefixes` to view all prefixes for this server.\n"
            f"{self.i_category(ctx)}\n"
        )

        cog_names = []
        for cog in bot.ordered_cogs:
            if hasattr(cog, "hidden") or cog.qualified_name == "Jishaku":
                if ctx.author.id != bot.owner_id:
                    continue

            if hasattr(cog, "emoji"):
                cog_names.append(f"{cog.emoji} {cog.qualified_name}")
            else:
                cog_names.append(cog.qualified_name)
        em.add_field(name="Categories", value="\n".join(cog_names), inline=True)

        dev = bot.get_user(224513210471022592)
        em.add_field(
            name=":information_source: Technical Info",
            value=(
                f"Developed by - {dev}\n"
                "Programming Language - Python\n"
                "Framework - discord.py commands"
            ),
            inline=True,
        )

        await ctx.send(embed=em)

    async def send_cog_help(self, cog):
        ctx = self.context
        bot = ctx.bot
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        em = self.get_base_embed()

        if hasattr(cog, "emoji"):
            em.description = f"**{cog.emoji} {cog.qualified_name}**"
        else:
            em.description = f"**{cog.qualified_name}**"

        if cog.description:
            em.description += f"\n{cog.description}"

        more_info = f"{self.arg_help()}\n{self.i_cmd(ctx)}"

        pages = menus.MenuPages(
            source=HelpPages(filtered, em, bot.guild_prefix(ctx.guild), more_info),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    async def send_group_help(self, group):
        ctx = self.context
        bot = ctx.bot
        filtered = await self.filter_commands(group.commands, sort=True)
        em = self.get_base_embed()
        em.description = f"**`{bot.guild_prefix(ctx.guild)}{group.name}"
        em.description += f" {group.usage}`**" if group.usage is not None else "`**"
        if group.description:
            em.description += f" - {group.description}"
        if group.help:
            em.description += "\n" + group.help
        if group.aliases:
            formatted_aliases = []
            for alias in group.aliases:
                formatted_alias = f"`{bot.guild_prefix(ctx.guild)}"
                formatted_alias += (
                    f"{group.parent} " if group.parent is not None else ""
                )
                formatted_alias += alias + "`"
                formatted_aliases.append(formatted_alias)
            em.description += f"\nAliases: {', '.join(formatted_aliases)}"
        em.description += f"\n\n**Subcommands ({len(filtered)} total):**"

        more_info = f"{self.arg_help()}\n{self.i_cmd(ctx)}"

        pages = menus.MenuPages(
            source=HelpPages(filtered, em, bot.guild_prefix(ctx.guild), more_info),
            clear_reactions_after=True,
        )
        await pages.start(ctx)

    async def send_command_help(self, command):
        ctx = self.context
        bot = ctx.bot
        em = self.get_base_embed()
        em.description = f"**`{bot.guild_prefix(ctx.guild)}"
        em.description += f"{command.parent} " if command.parent is not None else ""
        em.description += command.name
        em.description += f" {command.usage}`**" if command.usage is not None else "`**"
        if command.description:
            em.description += f" - {command.description}"
        if command.help:
            em.description += "\n" + command.help
        if command.aliases:
            formatted_aliases = []
            for alias in command.aliases:
                formatted_alias = f"`{bot.guild_prefix(ctx.guild)}"
                formatted_alias += (
                    f"{command.parent} " if command.parent is not None else ""
                )
                formatted_alias += alias + "`"
                formatted_aliases.append(formatted_alias)
            em.description += f"\nAliases: {', '.join(formatted_aliases)}"
        await ctx.send(embed=em)


class Meta(commands.Cog):
    """Everything to do with the bot itself."""

    def __init__(self, bot):
        self.bot = bot
        self.emoji = ":gear:"
        self.log = self.bot.log

        with open("prefixes.json", "r") as f:
            self.bot.guild_prefixes = json.load(f)

        self._original_help_command = bot.help_command
        bot.help_command = ClamHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    def i_category(self, ctx):
        return (
            "For **more info** on a **specific category**, "
            f"use: **`{self.bot.guild_prefix(ctx.guild)}help [category]`‍**"
        )

    def i_cmd(self, ctx):
        return (
            "For **more info** on a **specific command**, "
            f"use: **`{self.bot.guild_prefix(ctx.guild)}help [command]`‍**"
        )

    @commands.Cog.listener("on_message")
    async def on_mention_msg(self, message):
        content = message.content
        id = self.bot.user.id
        if content == f"<@{id}>" or content == f"<@!{id}>":
            await message.channel.send(
                "Hey there! I'm a bot. :robot:\n"
                "To find out more about me, type:"
                f" `{self.bot.guild_prefix(message.guild)}help`"
            )

    # @commands.Cog.listener("on_error")
    # async def _dm_dev(self, event):
    #     e = sys.exc_info()
    #     full =''.join(traceback.format_exception(type(e), e, e.__traceback__, 1))
    #     owner = self.bot.get_user(self.bot.owner_id)
    #     await owner.send(f"Error in {event}:```py\n{full}```")

    @commands.Cog.listener("on_command_error")
    async def _send_error(self, ctx, e: commands.CommandError):
        error = "".join(traceback.format_exception(type(e), e, e.__traceback__, 1))
        print("Ignoring exception in command {}:".format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)
        self.bot.previous_error = e
        if isinstance(e, commands.errors.CommandNotFound):
            return
        if isinstance(e, commands.errors.MissingPermissions):
            return
        if isinstance(e, commands.errors.BotMissingPermissions):
            perms = ""
            for perm in e.missing_perms:
                perms += f"\n  - {perm}"
            return await ctx.send(
                f"**:x: The bot is missing some permissions:**{perms}"
            )
        if isinstance(e, commands.errors.CheckFailure):
            return
        if isinstance(e, commands.errors.NotOwner):
            return
        if isinstance(e, commands.errors.BadArgument):
            return await ctx.send(f"**:x: You provided a bad argument.**")
        if isinstance(e, commands.errors.MissingRequiredArgument):
            return await ctx.send(
                f"**:x: Missing a required argument: `{e.param.name}`**"
            )
        if isinstance(e, commands.CommandOnCooldown):
            return await ctx.send(
                f"**You are on cooldown.** Try again after {e.retry_after} seconds."
            )
        em = discord.Embed(
            title=":warning: Unexpected Error",
            color=discord.Color.gold(),
            timestamp=d.utcnow(),
        )
        description = (
            "An unexpected error has occured:"
            f"```py\n{e}```\n The developer has been notified."
        )
        em.description = description
        em.set_footer(icon_url=self.bot.user.avatar_url)
        await ctx.send(embed=em)
        # await self.dev.send("Error occured on one of your commands.")

    def get_guild_prefixes(self, guild):
        if not guild:
            return "`c.` or when mentioned"
        guild = guild.id
        if str(guild) in self.bot.guild_prefixes.keys():
            prefixes = [f"`{p}`" for p in self.bot.guild_prefixes.get(str(guild))]
            prefixes.append("or when mentioned")
            return ", ".join(prefixes)
        return " ".join(self.bot.prefixes)

    async def get_lines_of_code(self):
        total = 0
        file_amount = 0
        for path, subdirs, files in os.walk("."):
            for name in files:
                if name.endswith(".py"):
                    file_amount += 1
                    with codecs.open(
                        "./" + str(pathlib.PurePath(path, name)), "r", "utf-8"
                    ) as f:
                        for i, l in enumerate(f):
                            if (
                                l.strip().startswith("#") or len(l.strip()) == 0
                            ):  # skip commented lines.
                                pass
                            else:
                                total += 1
        return f"I am made of {total:,} lines of Python, spread across {file_amount:,} files!"

    @commands.command(
        name="stats",
        description="Display statistics about the bot",
        aliases=["statistics", "about", "info"],
    )
    async def stats(self, ctx):
        em = discord.Embed(title="Statistics", color=0xFF95B0, timestamp=d.utcnow())
        em.set_thumbnail(url=self.bot.user.avatar_url)
        em.set_footer(
            text=f"Requested by {str(ctx.author)}", icon_url=self.bot.user.avatar_url
        )

        dev = self.bot.get_user(224513210471022592)
        up = d.now() - self.bot.startup_time
        em.add_field(name=":gear: Developer", value=dev.mention)
        em.add_field(name=":adult: User Count", value=len(self.bot.users))
        em.add_field(name=":family: Server Count", value=len(self.bot.guilds))
        em.add_field(
            name=":speech_balloon: Channel Count",
            value=len(list(self.bot.get_all_channels())),
        )
        em.add_field(
            name="<:online:649270802088460299> Uptime",
            value=strfdelta(up, "`{D}D {H}H {M}M {S}S`"),
        )
        em.add_field(name=":page_facing_up: Code", value=await self.get_lines_of_code())

        await ctx.send(embed=em)

    @commands.command(name="ping", description="Ping command; replies with 'Pong!'")
    async def ping_command(self, ctx):
        start = d.timestamp(d.now())
        msg = await ctx.send("Pinging")

        ping = (d.timestamp(d.now()) - start) * 1000
        await msg.edit(content=f"Pong!\nOne message round-trip took {ping}ms.")

    @commands.command(
        name="uptime",
        description="Uptime command; replies with the uptime",
        aliases=["up"],
    )
    async def uptime(self, ctx):
        up = d.now() - self.bot.startup_time
        up = strfdelta(up, "`{D}D {H}H {M}M {S}S`")

        msg = "<:online:649270802088460299> " f"I have been **online** for {up}"
        # Attach :02 to a time (Ex: {D:02}) to add the second 0
        await ctx.send(msg)

    @commands.command(name="invite", description="Invite me to your server")
    async def invite_command(self, ctx):
        invite = "https://discordapp.com/api/oauth2/authorize?client_id=639234650782564362&permissions=470150358&scope=bot"
        await ctx.send(f"Invite:\n{invite}")
        self.log.info(f"{str(ctx.author)} used the invite command")

    @commands.group(
        description="View your prefixes.",
        invoke_without_command=True,
        aliases=["prefixes"],
    )
    @commands.guild_only()
    async def prefix(self, ctx):
        if str(ctx.guild.id) not in self.bot.guild_prefixes.keys():
            return await ctx.send("Prefix:\n`c.`")
        prefixes = self.bot.guild_prefixes[str(ctx.guild.id)]
        msg = "Prefixes:"
        for i, prefix in enumerate(prefixes):
            msg += f"\n{i+1}. **`{prefix}`**"
        await ctx.send(msg)

    @prefix.command(name="add", description="Add a prefix.", usage="[prefix]")
    @commands.guild_only()
    @has_manage_guild()
    async def _add_prefix(self, ctx, prefix: str):
        if str(ctx.guild.id) not in self.bot.guild_prefixes.keys():
            prefixes = ["c."]
        else:
            prefixes = self.bot.guild_prefixes[str(ctx.guild.id)]
        if prefix in prefixes:
            return await ctx.send("You already have that prefix registered.")
        prefixes.append(prefix)
        self.bot.guild_prefixes[str(ctx.guild.id)] = prefixes
        with open("prefixes.json", "w") as f:
            json.dump(
                self.bot.guild_prefixes,
                f,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            )
        await ctx.send("Added prefix.")

    @prefix.command(name="remove", description="Remove a prefix.", usage="[prefix]")
    @commands.guild_only()
    @has_manage_guild()
    async def _remove_prefix(self, ctx, prefix):
        if str(ctx.guild.id) not in self.bot.guild_prefixes.keys():
            prefixes = ["c."]
        else:
            prefixes = self.bot.guild_prefixes[str(ctx.guild.id)]
        try:
            prefix_num = int(prefix)
        except ValueError:
            prefix_num = 100
        if prefix not in prefixes and prefix_num > len(prefixes):
            return await ctx.send("You don't have that prefix registered.")
        try:
            int(prefix)
            prefixes.pop(int(prefix) - 1)
        except ValueError:
            prefixes.remove(prefix)
        self.bot.guild_prefixes[str(ctx.guild.id)] = prefixes
        with open("prefixes.json", "w") as f:
            json.dump(
                self.bot.guild_prefixes,
                f,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            )
        await ctx.send("Removed prefix.")

    @prefix.command(
        name="default", description="Set a default prefix.", usage="[prefix]"
    )
    @commands.guild_only()
    @has_manage_guild()
    async def _default_prefix(self, ctx, prefix):
        if str(ctx.guild.id) not in self.bot.guild_prefixes.keys():
            prefixes = ["c."]
        else:
            prefixes = self.bot.guild_prefixes[str(ctx.guild.id)]
        try:
            prefix_num = int(prefix)
        except ValueError:
            prefix_num = 100
        if prefix not in prefixes and prefix_num > len(prefixes):
            prefixes_ = [prefix]
            prefixes_.extend(prefixes)
            prefixes = prefixes_
            self.bot.guild_prefixes[str(ctx.guild.id)] = prefixes
            with open("prefixes.json", "w") as f:
                json.dump(
                    self.bot.guild_prefixes,
                    f,
                    sort_keys=True,
                    indent=4,
                    separators=(",", ": "),
                )
            return await ctx.send(f"Set default prefix to `{prefix}`")
        try:
            int(prefix)
            prefixes.pop(int(prefix) - 1)
            prefixes_ = [prefix]
            prefixes_.extend(prefixes)
            prefixes = prefixes_
        except ValueError:
            prefixes.remove(prefix)
            prefixes_ = [prefix]
            prefixes_.extend(prefixes)
            prefixes = prefixes_
        self.bot.guild_prefixes[str(ctx.guild.id)] = prefixes
        with open("prefixes.json", "w") as f:
            json.dump(
                self.bot.guild_prefixes,
                f,
                sort_keys=True,
                indent=4,
                separators=(",", ": "),
            )
        await ctx.send(f"Set default prefix to `{prefix}`")

    @prefix.command(
        name="reset", description="Reset prefixes to default.", usage="[prefix]"
    )
    @commands.guild_only()
    @has_manage_guild()
    async def _reset_prefix(self, ctx):
        def check(reaction, user):
            return (
                reaction.message.id == bot_message.id
                and reaction.emoji in ["✅", "❌"]
                and user.id == ctx.author.id
            )

        if str(ctx.guild.id) not in self.bot.guild_prefixes.keys():
            return await ctx.send("This server is already using the default prefixes.")

        bot_message = await ctx.send(
            "Are you sure you want to reset your server's prefixes?\n"
            "**This change is irreversible.**"
        )

        await bot_message.add_reaction("✅")
        await bot_message.add_reaction("❌")

        try:
            reaction, user = await self.bot.wait_for(
                "reaction_add", check=check, timeout=120.0
            )

            if reaction.emoji == "✅":
                self.bot.guild_prefixes[str(ctx.guild.id)].pop()
                with open("prefixes.json", "w") as f:
                    json.dump(
                        self.bot.guild_prefixes,
                        f,
                        sort_keys=True,
                        indent=4,
                        separators=(",", ": "),
                    )
                await bot_message.edit(content="**Reset prefixes**")
                await bot_message.remove_reaction("✅", ctx.guild.me)
                await bot_message.remove_reaction("❌", ctx.guild.me)
                return

            await bot_message.edit(content="**Canceled**")
            await bot_message.remove_reaction("✅", ctx.guild.me)
            await bot_message.remove_reaction("❌", ctx.guild.me)

        except asyncio.TimeoutError:
            await bot_message.edit(content="**Canceled**")
            await bot_message.remove_reaction("✅", ctx.guild.me)
            await bot_message.remove_reaction("❌", ctx.guild.me)

    @commands.command()
    async def source(self, ctx, *, command: str = None):
        """Displays my full source code or for a specific command.
        To display the source code of a subcommand you can separate it by
        periods, e.g. tag.create for the create subcommand of the tag command
        or by spaces.
        """
        source_url = "https://github.com/Fyssion/Clam"
        branch = "master"
        if command is None:
            return await ctx.send(source_url)

        if command == "help":
            src = type(self.bot.help_command)
            module = src.__module__
            filename = inspect.getsourcefile(src)
        else:
            obj = self.bot.get_command(command.replace(".", " "))
            if obj is None:
                return await ctx.send("Could not find command.")

            # since we found the command we're looking for, presumably anyway, let's
            # try to access the code itself
            src = obj.callback.__code__
            module = obj.callback.__module__
            filename = src.co_filename

        lines, firstlineno = inspect.getsourcelines(src)
        if not module.startswith("discord"):
            # not a built-in command
            location = os.path.relpath(filename).replace("\\", "/")
        else:
            location = module.replace(".", "/") + ".py"
            source_url = "https://github.com/Rapptz/discord.py"
            branch = "master"

        final_url = f"<{source_url}/blob/{branch}/{location}#L{firstlineno}-L{firstlineno + len(lines) - 1}>"
        await ctx.send(final_url)

    @commands.command(name="backup_reload")
    @commands.is_owner()
    async def _reload(self, ctx, cog="all"):
        if cog == "all":
            msg = ""

            for ext in self.bot.cogs_to_load:
                try:
                    self.bot.reload_extension(ext)
                    msg += (
                        f"**<a:cool_ok_sign:699837382433701998> Reloaded** `{ext}`\n\n"
                    )
                    self.log.info(f"Extension '{cog.lower()}' successfully reloaded.")

                except Exception as e:
                    traceback_data = "".join(
                        traceback.format_exception(type(e), e, e.__traceback__, 1)
                    )
                    msg += (
                        f"**:warning: Extension `{ext}` not loaded.**\n"
                        f"```py\n{traceback_data}```\n\n"
                    )
                    self.log.warning(
                        f"Extension 'cogs.{cog.lower()}' not loaded.\n"
                        f"{traceback_data}"
                    )
            return await ctx.send(msg)

        try:
            self.bot.reload_extension(cog.lower())
            await ctx.send(
                f"**<a:cool_ok_sign:699837382433701998> Reloaded** `{cog.lower()}`"
            )
            self.log.info(f"Extension '{cog.lower()}' successfully reloaded.")
        except Exception as e:
            traceback_data = "".join(
                traceback.format_exception(type(e), e, e.__traceback__, 1)
            )
            await ctx.send(
                f"**:warning: Extension `{cog.lower()}` not loaded.**\n```py\n{traceback_data}```"
            )
            self.log.warning(
                f"Extension 'cogs.{cog.lower()}' not loaded.\n{traceback_data}"
            )


def setup(bot):
    bot.add_cog(Meta(bot))
