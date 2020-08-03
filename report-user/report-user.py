import discord
import asyncio
from datetime import datetime
from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class ReportUser(commands.Cog):
    """
    Reporta un usuario al staff
    """

    def __init__(self, bot):
        self.bot: discord.Client = bot
        self.db = bot.plugin_db.get_partition(self)
        self.blacklist = []
        self.channel = None
        self.message = "Gracias por reportar, nuestro staff va a investigar el caso. Recuerda que usar mal este comando puede conllevar una sanción."
        self.current_case = 1
        asyncio.create_task(self._set_config())

    async def _set_config(self):
        config = await self.db.find_one({"_id": "config"})
        if config is None:
            return
        else:
            self.blacklist = config.get("blacklist", [])
            self.channel = config.get("channel", None)
            self.current_case = config.get("case", 1)
            self.message = config.get(
                "message", "Gracias por reportar, nuestro staff va a investigar el caso. Recuerda que usar mal este comando puede conllevar una sanción."
            )

    async def update(self):
        await self.db.find_one_and_update(
            {"_id": "config"},
            {
                "$set": {
                    "blacklist": self.blacklist,
                    "chanel": self.channel,
                    "message": self.message,
                    "case": self.current_case,
                }
            },
            upsert=True,
        )

    @commands.group()
    async def ru(self, ctx: commands.Context):
        """
        Report User Staff Commands
        """
        return

    @ru.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def blacklist(self, ctx, member: discord.Member):
        """
        Blacklist or blacklist a user
        """
        if member.id not in self.blacklist:
            self.blacklist.append(member.id)
            updated = False
        else:
            self.blacklist.pop(member.id)
            updated = True
        await self.update()

        await ctx.send(f"{'Un' if updated else ''}Blacklisted!")

    @ru.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set A reports Channel
        """
        await self.db.find_one_and_update(
            {"_id": "config"}, {"$set": {"channel": str(channel.id)}}, upsert=True
        )
        self.channel = str(channel.id)
        await ctx.send("Done!")

    @ru.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def message(self, ctx, *, msg: str):
        """
        Customise the message that will be sent to user
        """
        await self.db.find_one_and_update(
            {"_id": "config"}, {"$set": {"message": msg}}, upsert=True
        )
        self.message = msg
        await ctx.send("¡Hecho!")

    @commands.command()
    async def report(
        self, ctx: commands.Context, member: discord.Member, *, reason: str
    ):
        """
        Report a user
        """
        if ctx.author.id in self.blacklist:
            await ctx.message.delete()
            return

        if self.channel is None:
            await ctx.message.delete()
            await ctx.author.send("Reports Channel for the guild has not been set.")
            return
        else:
            channel: discord.TextChannel = self.bot.get_channel(int(self.channel))
            embed = discord.Embed(
                color=discord.Colour.red(), timestamp=datetime.utcnow()
            )
            embed.set_author(
                name=f"{ctx.author.name}#{ctx.author.discriminator}",
                icon_url=ctx.author.avatar_url,
            )
            embed.title = "Reporte"
            embed.add_field(
                name="Contra",
                value=f"{member.name}#{member.discriminator}",
                inline=False,
            )
            embed.add_field(name="Razón", value=reason, inline=False)
            embed.set_footer(text=f"Caso {self.current_case}")
            m: discord.Message = await channel.send(embed=embed)
            await ctx.author.send(self.message)
            await ctx.message.delete()
            await m.add_reaction("\U00002705")
            await self.db.insert_one(
                {
                    "case": self.current_case,
                    "author": str(ctx.author.id),
                    "against": str(member.id),
                    "reason": reason,
                    "resolved": False,
                }
            )
            self.current_case = self.current_case + 1
            await self.update()
            return

    @ru.command()
    @checks.has_permissions(PermissionLevel.MOD)
    async def info(self, ctx: commands.Context, casen: int):
        case = await self.db.find_one({"case": casen})

        if case is None:
            await ctx.send(f"Case `#{casen}` dose'nt exist")
            return
        else:
            user1: discord.User = await self.bot.fetch_user(int(case["author"]))
            user2: discord.User = await self.bot.fetch_user(int(case["against"]))
            embed = discord.Embed(color=discord.Colour.red())
            embed.add_field(
                name="By", value=f"{user1.name}#{user1.discriminator}", inline=False
            )
            embed.add_field(
                name="Ha reportado a:",
                value=f"{user2.name}#{user2.discriminator}",
                inline=False,
            )
            embed.add_field(name="Razón", value=case["reason"], inline=False)
            embed.add_field(name="Resolved", value=case["resolved"], inline=False)
            embed.title = "Log de reportes"
            await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if (
            str(payload.channel_id) != str(self.channel)
            or str(payload.emoji.name) != "✅"
        ):
            return

        channel: discord.TextChannel = self.bot.get_channel(payload.channel_id)
        msg: discord.Message = await channel.fetch_message(payload.message_id)

        if not msg.embeds or msg.embeds[0] is None:
            return

        if msg.embeds[0].footer.text is None:
            return

        case = int(msg.embeds[0].footer.text[5:])

        casedb = await self.db.find_one({"case": case})

        if casedb is None:
            return

        if casedb["resolved"] is True:
            await channel.send(f"El reporte `#{case}` ya ha sido resuelto.")
            return

        def check(messge: discord.Message):
            return (
                payload.user_id == messge.author.id
                and payload.channel_id == messge.channel.id
            )

        await channel.send("Escribe el mensaje que vamos a enviar a la persona que ha reportado")
        reportr = await self.bot.wait_for("message", check=check)
        user1 = self.bot.get_user(int(casedb["author"]))
        await user1.send(f"**Respuesta del staff:**\n{reportr.content}")
        await channel.send("¡Enviado por mensaje directo!")
        await self.db.find_one_and_update({"case": case}, {"$set": {"resolved": True}})
        return


def setup(bot):
    bot.add_cog(ReportUser(bot))
