import os
import json
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")
DATA_FILE = "reaction_roles.json"

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.reactions = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


reaction_data = load_data()


def user_can_manage(ctx):
    if ctx.guild is None:
        return False
    return (
        ctx.author.id == ctx.guild.owner_id
        or ctx.author.guild_permissions.administrator
        or ctx.author.guild_permissions.manage_guild
    )


@bot.event
async def on_ready():
    print(f"Zalogowano jako {bot.user} (ID: {bot.user.id})")


@bot.command(name="ustawrole")
async def ustawrole(ctx, message_id: int, *args):
    """
    Użycie:
    !ustawrole ID_WIADOMOSCI 🎮 111111111111111111 🎵 222222222222222222
    """
    if not user_can_manage(ctx):
        await ctx.send("Nie masz uprawnień do tej komendy.")
        return

    if len(args) < 2 or len(args) % 2 != 0:
        await ctx.send(
            "Błędny format.\n"
            "Użycie:\n"
            "`!ustawrole ID_WIADOMOSCI 🎮 ID_ROLI 🎵 ID_ROLI 📢 ID_ROLI`"
        )
        return

    channel = ctx.channel

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        await ctx.send("Nie znalazłem wiadomości o takim ID na tym kanale.")
        return
    except discord.Forbidden:
        await ctx.send("Nie mam dostępu do tej wiadomości.")
        return
    except discord.HTTPException:
        await ctx.send("Nie udało się pobrać wiadomości.")
        return

    guild_id = str(ctx.guild.id)
    message_id_str = str(message_id)

    if guild_id not in reaction_data:
        reaction_data[guild_id] = {}

    if message_id_str not in reaction_data[guild_id]:
        reaction_data[guild_id][message_id_str] = {}

    added_pairs = []

    for i in range(0, len(args), 2):
        emoji = args[i]
        role_id_raw = args[i + 1]

        try:
            role_id = int(role_id_raw)
        except ValueError:
            await ctx.send(f"`{role_id_raw}` nie jest poprawnym ID roli.")
            return

        role = ctx.guild.get_role(role_id)
        if role is None:
            await ctx.send(f"Nie znalazłem roli o ID `{role_id}`.")
            return

        if role >= ctx.guild.me.top_role:
            await ctx.send(
                f"Nie mogę nadać roli `{role.name}`, bo jest wyżej lub na równi z rolą bota."
            )
            return

        reaction_data[guild_id][message_id_str][emoji] = role_id
        added_pairs.append(f"{emoji} → {role.name}")

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(f"Nie udało się dodać reakcji {emoji}.")
            return

    save_data(reaction_data)

    summary = "\n".join(added_pairs)
    await ctx.send(
        f"Ustawiono reaction roles dla wiadomości `{message_id}`:\n{summary}"
    )


@bot.command(name="pokazrole")
async def pokazrole(ctx, message_id: int):
    if not user_can_manage(ctx):
        await ctx.send("Nie masz uprawnień do tej komendy.")
        return

    guild_id = str(ctx.guild.id)
    message_id_str = str(message_id)

    if guild_id not in reaction_data or message_id_str not in reaction_data[guild_id]:
        await ctx.send("Dla tej wiadomości nie ma ustawionych reaction roles.")
        return

    lines = []
    for emoji, role_id in reaction_data[guild_id][message_id_str].items():
        role = ctx.guild.get_role(role_id)
        role_name = role.name if role else f"usunięta rola ({role_id})"
        lines.append(f"{emoji} → {role_name}")

    await ctx.send("\n".join(lines))


@bot.command(name="usunrolemape")
async def usunrolemape(ctx, message_id: int, emoji: str):
    if not user_can_manage(ctx):
        await ctx.send("Nie masz uprawnień do tej komendy.")
        return

    guild_id = str(ctx.guild.id)
    message_id_str = str(message_id)

    if guild_id not in reaction_data or message_id_str not in reaction_data[guild_id]:
        await ctx.send("Ta wiadomość nie ma ustawionych reaction roles.")
        return

    if emoji not in reaction_data[guild_id][message_id_str]:
        await ctx.send("Ta emotka nie jest przypisana do żadnej roli.")
        return

    del reaction_data[guild_id][message_id_str][emoji]

    if not reaction_data[guild_id][message_id_str]:
        del reaction_data[guild_id][message_id_str]

    if not reaction_data[guild_id]:
        del reaction_data[guild_id]

    save_data(reaction_data)
    await ctx.send(f"Usunięto przypisanie dla emotki {emoji}.")


@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None:
        return

    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id not in reaction_data:
        return

    if message_id not in reaction_data[guild_id]:
        return

    if emoji not in reaction_data[guild_id][message_id]:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role_id = reaction_data[guild_id][message_id][emoji]
    role = guild.get_role(role_id)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            return

    try:
        await member.add_roles(role, reason="Reaction role")
    except discord.Forbidden:
        print("Brak uprawnień do nadania roli.")
    except discord.HTTPException as e:
        print(f"Błąd przy dodawaniu roli: {e}")


@bot.event
async def on_raw_reaction_remove(payload):
    if payload.guild_id is None:
        return

    if payload.user_id == bot.user.id:
        return

    guild_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    emoji = str(payload.emoji)

    if guild_id not in reaction_data:
        return

    if message_id not in reaction_data[guild_id]:
        return

    if emoji not in reaction_data[guild_id][message_id]:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role_id = reaction_data[guild_id][message_id][emoji]
    role = guild.get_role(role_id)
    if role is None:
        return

    try:
        member = await guild.fetch_member(payload.user_id)
    except discord.NotFound:
        return

    try:
        await member.remove_roles(role, reason="Reaction role")
    except discord.Forbidden:
        print("Brak uprawnień do usunięcia roli.")
    except discord.HTTPException as e:
        print(f"Błąd przy usuwaniu roli: {e}")


bot.run(TOKEN)