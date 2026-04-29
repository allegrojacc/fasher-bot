import os
import re
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

DELETE_ROLE_ID = 1494687052975968306

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

active_role_messages = {}

URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com|facebook\.com|fb\.watch|instagram\.com|instagr\.am)/[^\s<>]+',
    re.IGNORECASE
)

def convert_url(url: str) -> str:
    url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?facebook\.com/', 'https://fixacebook.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?fb\.watch/', 'https://fixacebook.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.vxinstagram.com/', url, flags=re.IGNORECASE)
    return url

def has_delete_role():
    async def predicate(ctx):
        return any(role.id == DELETE_ROLE_ID for role in ctx.author.roles)
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f'Bot działa jako {bot.user}')

# KOMENDA DO TWORZENIA RANG
@bot.command()
@commands.has_permissions(manage_roles=True)
async def setup_roles(ctx, title: str, *args):
    """Przykład: !setup_roles "Wybierz Role" 🎮 @Gracz 🎨 @Artysta"""
    if len(args) % 2 != 0:
        await ctx.send("Podaj pary: Emotka i Rola!")
        return

    role_data = {}
    desc = "Zareaguj, aby otrzymać rangę:\n"

    for i in range(0, len(args), 2):
        emoji = args[i]
        role_mention = args[i + 1]
        role_id = int(re.sub(r'[<@&>]', '', role_mention))
        role_data[emoji] = role_id
        desc += f"{emoji} - {role_mention}\n"

    embed = discord.Embed(title=title, description=desc, color=0x00ff00)
    msg = await ctx.send(embed=embed)

    for emoji in role_data.keys():
        await msg.add_reaction(emoji)

    active_role_messages[msg.id] = role_data

# USUWANIE WIADOMOŚCI PO ID
@bot.command(name="uw")
@has_delete_role()
@commands.bot_has_permissions(manage_messages=True)
async def usun_wiadomosci(ctx, *message_ids: int):
    """Użycie: !uw ID ID ID"""
    deleted = 0
    not_found = 0

    if not message_ids:
        await ctx.send("Podaj ID wiadomości do usunięcia. Przykład: `!uw 123456789012345678`", delete_after=8)
        return

    for msg_id in message_ids:
        try:
            msg = await ctx.channel.fetch_message(msg_id)
            await msg.delete()
            deleted += 1

        except discord.NotFound:
            not_found += 1

        except discord.Forbidden:
            await ctx.send("Brak uprawnień do usuwania wiadomości.", delete_after=5)
            return

        except discord.HTTPException:
            await ctx.send("Wystąpił błąd podczas usuwania wiadomości.", delete_after=5)
            return

    await ctx.send(
        f"Usunięto: {deleted} | Nie znaleziono: {not_found}",
        delete_after=5
    )

# OBSŁUGA LINKÓW
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    urls = [match.group(0) for match in URL_PATTERN.finditer(message.content)]
    if not urls:
        return

    responses = []
    seen = set()

    for url in urls:
        fixed = convert_url(url)
        if fixed not in seen:
            seen.add(fixed)
            responses.append(f"{message.author.display_name} wysyła link:\n{fixed}")

    if responses:
        await message.reply("\n\n".join(responses), mention_author=False)
        try:
            await message.delete()
        except:
            pass

# REAKCJE DAWANIE ROLI
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    if payload.message_id in active_role_messages:
        role_id = active_role_messages[payload.message_id].get(str(payload.emoji))
        if role_id:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(role_id)

            if role:
                await payload.member.add_roles(role)

# REAKCJE ODBIERANIE ROLI
@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id in active_role_messages:
        role_id = active_role_messages[payload.message_id].get(str(payload.emoji))
        if role_id:
            guild = bot.get_guild(payload.guild_id)
            role = guild.get_role(role_id)
            member = await guild.fetch_member(payload.user_id)

            if role and member:
                await member.remove_roles(role)

if __name__ == "__main__":
    bot.run(TOKEN)
