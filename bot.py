import os
import re
import json
import asyncio
import xml.etree.ElementTree as ET
import itertools
import datetime
from urllib.parse import urlparse, urlunparse
from typing import Tuple, Dict, Any

import discord
from discord.ext import commands, tasks
from discord.ext.commands import BadArgument

from dotenv import load_dotenv
load_dotenv()

import aiohttp
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# --- KONFIGURACJA I ZMIENNE ---
TOKEN = os.getenv("TOKEN")
DELETE_ROLE_ID = 1494687052975968306

PROMO_CHANNELS = [
    1321787613522427964,  # Główny kanał promek
    1508226473176334366   # Nowy kanał testowy bota
]

YOUTUBE_CHANNEL_ID = "UCxwjc3YRZemIrOgUM1EGRDg"
DISCORD_NOTIFICATION_CHANNEL_ID = 1290353850196426844

# KANAŁY URODZINOWE
BIRTHDAY_DATABASE_CHANNEL_ID = 1535735325920596030  # ID prywatnego kanału bota
BIRTHDAY_ANNOUNCE_CHANNEL_ID = 1083730752321101857  # Kanał z życzeniami

SEEN_VIDEOS = set()
YOUTUBE_INITIALIZED = False
IS_LIVE_NOW = False

# Pamięć podręczna urodzin: {user_id (int): "DD-MM"}
BIRTHDAYS = {}

# Globalna sesja HTTP
session: aiohttp.ClientSession = None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

statuses = itertools.cycle([
    discord.Game("God of War Laufey"),
    discord.Game("Wolverine"),
    discord.Game("Control Resonant"),
    discord.Game("Grand Theft Auto VI"),
])

# Strefa czasowa dla bota (Polska)
tz_pl = ZoneInfo("Europe/Warsaw")
# Ustawienie godziny 00:00 dla urodzin
bday_time = datetime.time(hour=0, minute=0, tzinfo=tz_pl)

# --- FUNKCJE BAZY DANYCH URODZIN ---
async def load_birthdays():
    """Wczytuje urodziny z pojedynczych wiadomości w prywatnym kanale bota."""
    global BIRTHDAYS
    BIRTHDAYS.clear()

    channel = bot.get_channel(BIRTHDAY_DATABASE_CHANNEL_ID)
    if not channel:
        print("Błąd: Nie znaleziono kanału bazy urodzin!")
        return

    async for msg in channel.history(limit=200):
        if msg.author == bot.user and ":" in msg.content:
            try:
                u_id_str, bday = msg.content.strip().split(":")
                BIRTHDAYS[int(u_id_str)] = bday
            except ValueError:
                continue
    print(f"Wczytano urodziny dla {len(BIRTHDAYS)} użytkowników.")

async def save_user_birthday(user_id: int, bday: str):
    """Usuwa stary wpis użytkownika z kanału bazy i zapisuje nowy."""
    channel = bot.get_channel(BIRTHDAY_DATABASE_CHANNEL_ID)
    if not channel:
        return

    async for msg in channel.history(limit=200):
        if msg.author == bot.user and msg.content.startswith(f"{user_id}:"):
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
            break

    await channel.send(f"{user_id}:{bday}")
    BIRTHDAYS[user_id] = bday

# --- PĘTLE ZADAŃ ---
@tasks.loop(minutes=2)
async def change_status():
    global IS_LIVE_NOW
    await bot.wait_until_ready()

    if IS_LIVE_NOW:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🔴 LIVE PlayStation Polska"))
    else:
        await bot.change_presence(activity=next(statuses))

@tasks.loop(minutes=5)
async def check_youtube():
    global SEEN_VIDEOS, YOUTUBE_INITIALIZED, IS_LIVE_NOW, session
    await bot.wait_until_ready()

    now = datetime.datetime.now(tz_pl)

    # 1. Sprawdzanie LIVE (Tylko w wyznaczonych godzinach)
    if 15 <= now.hour < 20:
        channel = bot.get_channel(DISCORD_NOTIFICATION_CHANNEL_ID)
        if channel:
            live_url = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}/live"
            try:
                async with session.get(live_url, timeout=10) as live_response:
                    if live_response.status == 200:
                        live_text = await live_response.text()
                        has_live_marker = '"isLiveNow":true' in live_text and '"style":"LIVE"' in live_text
                        is_upcoming = '"LAUNCHED_STYLE_UPCOMING"' in live_text or '"isUpcoming":true' in live_text

                        is_currently_live = has_live_marker and not is_upcoming

                        if is_currently_live and not IS_LIVE_NOW:
                            embed = discord.Embed(
                                title="🔴 PlayStation Polska nadaje NA ŻYWO!",
                                description="Transmisja właśnie się rozpoczęła. Zapraszam wszystkich Fasherów!",
                                url=live_url,
                                color=0xFF0000
                            )
                            await channel.send(content="UWAGA!! POTĘŻNY stream właśnie sie odpalił!", embed=embed)

                        IS_LIVE_NOW = is_currently_live
            except Exception as e:
                print(f"Błąd sprawdzania statusu LIVE: {e}")

    # 2. Sprawdzanie RSS dla nowych filmów
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                root = ET.fromstring(text)
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}

                entries = root.findall('atom:entry', ns)
                if not entries:
                    return

                if not YOUTUBE_INITIALIZED:
                    for entry in entries:
                        v_id = entry.find('yt:videoId', ns).text
                        SEEN_VIDEOS.add(v_id)
                    YOUTUBE_INITIALIZED = True
                    return

                channel = bot.get_channel(DISCORD_NOTIFICATION_CHANNEL_ID)
                for entry in reversed(entries):
                    video_id = entry.find('yt:videoId', ns).text

                    if video_id not in SEEN_VIDEOS:
                        SEEN_VIDEOS.add(video_id)
                        title = entry.find('atom:title', ns).text
                        link = entry.find('atom:link', ns).attrib['href']
                        author = entry.find('atom:author/atom:name', ns).text

                        if "stream" not in title.lower():
                            continue

                        if channel:
                            embed = discord.Embed(
                                title=title,
                                url=link,
                                description=f"Nowy materiał na kanale **{author}**!",
                                color=0x003399
                            )
                            embed.set_image(url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")
                            await channel.send(content="Nowy materiał wleciał na kanał PlayStation Polska!", embed=embed)

    except Exception as e:
        print(f"Błąd podczas sprawdzania YouTube: {e}")

@tasks.loop(time=bday_time)
async def check_birthdays():
    await bot.wait_until_ready()

    now = datetime.datetime.now(tz_pl)
    today_str = now.strftime("%d-%m")
    channel = bot.get_channel(BIRTHDAY_ANNOUNCE_CHANNEL_ID)

    if channel:
        for user_id, bday in list(BIRTHDAYS.items()):
            if bday == today_str:
                await channel.send(f"Dzisiaj są urodziny <@{user_id}>! Wszystkiego najlepszego! 🎉")

# --- HELPERY I PARSERY ---
URL_PATTERN = re.compile(
    r'https?://(?:[a-zA-Z0-9-]+\.)?(?:store\.playstation\.com|x\.com|twitter\.com|instagram\.com|instagr\.am)/[^\s<>]+',
    re.IGNORECASE
)

def convert_url(url: str) -> str:
    parsed_url = urlparse(url)
    clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))

    clean_url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', clean_url, flags=re.IGNORECASE)
    clean_url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.oginstagram.com/', clean_url, flags=re.IGNORECASE)

    return clean_url

async def get_ps_game_details(url: str) -> Tuple[str, Dict[str, Any]]:
    nazwa = "Gra PlayStation"
    detale = {
        "cena_reg": "Sprawdź w sklepie",
        "cena_plus": None,
        "image_url": None,
        "description": "Brak opisu gry."
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                html = await response.text()
                soup = await asyncio.to_thread(BeautifulSoup, html, 'html.parser')

                if soup.title and soup.title.string:
                    title_str = soup.title.string
                    if "|" in title_str:
                        title_str = title_str.split('|')[0].strip()
                    nazwa = title_str

                json_ld_tag = soup.find("script", id="mfe-jsonld-tags")
                if json_ld_tag and json_ld_tag.string:
                    try:
                        data = json.loads(json_ld_tag.string)
                        if "description" in data:
                            full_desc = data["description"].strip()
                            if len(full_desc) > 160:
                                truncated = full_desc[:160]
                                if " " in truncated:
                                    truncated = truncated.rsplit(" ", 1)[0]
                                detale["description"] = truncated + "..."
                            else:
                                detale["description"] = full_desc
                        if "image" in data:
                            detale["image_url"] = data["image"]
                    except Exception:
                        pass

                cena_standardowa = None
                cena_promocyjna_plus = None
                active_cta_id = None

                for script in soup.find_all("script"):
                    if script.string and "activeCtaId" in script.string:
                        cta_match = re.search(r'"activeCtaId"\s*:\s*"([^"]+)"', script.string)
                        if cta_match:
                            active_cta_id = cta_match.group(1)
                            break

                for script in soup.find_all("script"):
                    if script.string and "ctaWithPrice" in script.string:
                        text_content = script.string
                        if active_cta_id and active_cta_id not in text_content:
                            continue
                        if "UPSELL_PS_PLUS_TRIAL" in text_content or "game_trial" in text_content:
                            continue

                        base_match = re.search(r'"basePrice"\s*:\s*"([^"]+)"', text_content)
                        discount_match = re.search(r'"discountedPrice"\s*:\s*"([^"]+)"', text_content)

                        if base_match:
                            temp_base = base_match.group(1).replace("zl", "zł").strip()
                            if "Wersja" not in temp_base and "próbna" not in temp_base:
                                cena_standardowa = temp_base

                        if discount_match:
                            stan_ceny = discount_match.group(1).replace("zl", "zł").strip()
                            if "Wersja" not in stan_ceny and "próbna" not in stan_ceny:
                                if "UPSELL_PS_PLUS_DISCOUNT" in text_content or '"isTiedToSubscription":true' in text_content:
                                    cena_promocyjna_plus = stan_ceny
                                else:
                                    cena_standardowa = stan_ceny

                        if active_cta_id and cena_standardowa:
                            break

                if cena_standardowa:
                    detale["cena_reg"] = cena_standardowa

                if cena_promocyjna_plus and cena_promocyjna_plus != cena_standardowa:
                    detale["cena_plus"] = cena_promocyjna_plus
                else:
                    detale["cena_plus"] = None

    except Exception as e:
        print(f"Błąd podczas parsowania danych z PS Store: {e}")

    return nazwa, detale

def has_delete_role():
    async def predicate(ctx):
        return any(role.id == DELETE_ROLE_ID for role in ctx.author.roles)
    return commands.check(predicate)

# --- ZDARZENIA I KOMENDY ---
@bot.event
async def on_ready():
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()

    print(f'Bot działa jako {bot.user}')

    await load_birthdays()

    if not check_youtube.is_running():
        check_youtube.start()
    if not change_status.is_running():
        change_status.start()
    if not check_birthdays.is_running():
        check_birthdays.start()

# --- KOMENDA URODZINOWA ---
@bot.command(name="urodziny", aliases=["dodajurodziny", "edytujurodziny"])
async def ustaw_urodziny(ctx, data: str = None):
    if not data:
        await ctx.send("Podaj datę urodzin w formacie `DD-MM` (np. `!urodziny 08-08` lub `!urodziny 15.05`).", delete_after=10)
        return

    clean_data = data.replace(".", "-").replace("/", "-")
    parts = clean_data.split("-")

    if len(parts) != 2:
        await ctx.send("Błędny format! Użyj formatu `DD-MM`, np. `08-08` dla 8 sierpnia.", delete_after=8)
        return

    try:
        day = int(parts[0])
        month = int(parts[1])
        datetime.datetime(2024, month, day)
        formatted_bday = f"{day:02d}-{month:02d}"
    except ValueError:
        await ctx.send("Podana data nie istnieje! Sprawdź dzień i miesiąc.", delete_after=8)
        return

    await save_user_birthday(ctx.author.id, formatted_bday)
    await ctx.send(f"✅ Zapisano Twoje urodziny na **{formatted_bday}**!", delete_after=8)

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

# --- INNE KOMENDY ---
@bot.command()
@commands.has_permissions(administrator=True)
async def test_yt(ctx):
    await ctx.send("Sprawdzam najnowszy film z PlayStation Polska (wymuszenie)...")
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                text = await response.text()
                root = ET.fromstring(text)
                ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
                entry = root.find('atom:entry', ns)

                if entry is not None:
                    video_id = entry.find('yt:videoId', ns).text
                    title = entry.find('atom:title', ns).text
                    link = entry.find('atom:link', ns).attrib['href']
                    author = entry.find('atom:author/atom:name', ns).text

                    embed = discord.Embed(
                        title=title,
                        url=link,
                        description=f"Nowy materiał na kanale **{author}**! (Wiadomość Testowa)",
                        color=0x003399
                    )
                    embed.set_image(url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")
                    await ctx.send(content="Testowy Embed z nowym filmem! 🎮", embed=embed)
                else:
                    await ctx.send("Nie znaleziono materiałów.")
    except Exception as e:
        await ctx.send(f"Wystąpił błąd: {e}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def setup_roles(ctx, title: str, *args):
    if len(args) % 2 != 0:
        await ctx.send("Podaj pary: Emotka i Rola!")
        return

    desc = "Zareaguj, aby otrzymać rangę:\n"
    emojis_to_react = []

    for i in range(0, len(args), 2):
        emoji = args[i]
        role_mention = args[i + 1]
        desc += f"{emoji} - {role_mention}\n"
        emojis_to_react.append(emoji)

    embed = discord.Embed(title=title, description=desc, color=0x00ff00)
    msg = await ctx.send(embed=embed)

    for emoji in emojis_to_react:
        await msg.add_reaction(emoji)

@bot.command(name="uw")
@has_delete_role()
@commands.bot_has_permissions(manage_messages=True)
async def usun_wiadomosci(ctx, *message_ids: int):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    if not message_ids:
        await ctx.send("Podaj ID wiadomości do usunięcia. Przykład: `!uw 123456789012345678`", delete_after=8, silent=True)
        return

    deleted = 0
    not_found = 0

    for msg_id in message_ids:
        try:
            msg = await ctx.channel.fetch_message(msg_id)
            await msg.delete()
            deleted += 1
        except discord.NotFound:
            not_found += 1
        except discord.Forbidden:
            await ctx.send("Brak uprawnień do usuwania wiadomości.", delete_after=5, silent=True)
            return
        except discord.HTTPException:
            continue

    await ctx.send(f"Usunięto: {deleted} | Nie znaleziono: {not_found}", delete_after=5, silent=True)

@bot.command(name="ew")
@has_delete_role()
async def edytuj_wiadomosc(ctx, message_id: int, *, nowa_tresc: str = None):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass

    if not nowa_tresc:
        await ctx.send("Musisz podać nową treść wiadomości po ID!", delete_after=5)
        return

    try:
        msg = await ctx.channel.fetch_message(message_id)
        if msg.author != bot.user:
            await ctx.send("Mogę edytować wyłącznie wiadomości mojego autorstwa!", delete_after=5)
            return

        await msg.edit(content=nowa_tresc)
        await ctx.send("Wiadomość została zaktualizowana.", delete_after=3)

    except discord.NotFound:
        await ctx.send("Nie znalazłem wiadomości o takim ID na tym kanale.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("Nie mam uprawnień do wykonania tej operacji.", delete_after=5)
    except discord.HTTPException:
        await ctx.send("Wystąpił nieoczekiwany błąd Discorda.", delete_after=5)

@edytuj_wiadomosc.error
async def edytuj_wiadomosc_error(ctx, error):
    if isinstance(error, BadArgument):
        await ctx.send("Błędny format ID. Poprawny wzór: `!ew [ID_wiadomości] [nowy tekst]`", delete_after=6)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

# --- OBSŁUGA WIADOMOŚCI I LINKÓW ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    urls = [match.group(0) for match in URL_PATTERN.finditer(message.content)]
    if not urls:
        return

    seen = set()

    for url in urls:
        url_lower = url.lower()

        # 1. PS Store
        if "store.playstation.com" in url_lower:
            if message.channel.id not in PROMO_CHANNELS:
                continue

            if url not in seen:
                seen.add(url)

                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                nazwa_gry, detale = await get_ps_game_details(url)

                embed = discord.Embed(
                    title=nazwa_gry,
                    url=url,
                    description=detale["description"],
                    color=0x00439C
                )

                embed.set_author(
                    name=f"Promka od: {message.author.display_name}",
                    icon_url=message.author.display_avatar.url
                )

                if detale["cena_plus"]:
                    embed.add_field(name="💰 Cena Standardowa", value=f"~~{detale['cena_reg']}~~", inline=True)
                    embed.add_field(name="🟡 Cena z PS Plus", value=f"**{detale['cena_plus']}**", inline=True)
                else:
                    embed.add_field(name="💰 Cena", value=f"**{detale['cena_reg']}**", inline=True)

                if detale["image_url"]:
                    embed.set_image(url=detale["image_url"])

                await message.channel.send(embed=embed)

        # 2. Social Media (X/Twitter, Instagram)
        else:
            if "x.com" in url_lower or "twitter.com" in url_lower:
                platforma = "Twitter/X"
            elif "instagram.com" in url_lower or "instagr.am" in url_lower:
                platforma = "Instagram"
            else:
                continue

            fixed = convert_url(url)
            if fixed not in seen:
                seen.add(fixed)

                hyperlink = f"> [**{message.author.display_name} wysyła link do** ***{platforma}***]({fixed})"

                await message.channel.send(hyperlink)
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

# --- SYSTEM REAKCJI RÓL ---
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id or not payload.guild_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return

    channel = guild.get_channel(payload.channel_id)
    if not channel: return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    if message.author != bot.user or not message.embeds:
        return

    embed = message.embeds[0]
    if not embed.description or "Zareaguj, aby otrzymać rangę:" not in embed.description:
        return

    emoji_str = str(payload.emoji)
    for line in embed.description.split('\n'):
        if line.startswith(emoji_str):
            match = re.search(r'<@&(\d+)>', line)
            if match:
                role_id = int(match.group(1))
                role = guild.get_role(role_id)
                if role:
                    member = payload.member or await guild.fetch_member(payload.user_id)
                    if member:
                        await member.add_roles(role)
            break

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if not payload.guild_id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return

    channel = guild.get_channel(payload.channel_id)
    if not channel: return

    try:
        message = await channel.fetch_message(payload.message_id)
    except Exception:
        return

    if message.author != bot.user or not message.embeds:
        return

    embed = message.embeds[0]
    if not embed.description or "Zareaguj, aby otrzymać rangę:" not in embed.description:
        return

    emoji_str = str(payload.emoji)
    for line in embed.description.split('\n'):
        if line.startswith(emoji_str):
            match = re.search(r'<@&(\d+)>', line)
            if match:
                role_id = int(match.group(1))
                role = guild.get_role(role_id)
                if role:
                    try:
                        member = await guild.fetch_member(payload.user_id)
                        await member.remove_roles(role)
                    except Exception:
                        return
            break

# --- START BOTA ---
if __name__ == "__main__":
    bot.run(TOKEN)