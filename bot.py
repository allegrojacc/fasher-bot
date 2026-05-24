import os
import re
import threading
import discord
from discord.ext import commands, tasks
import aiohttp
import xml.etree.ElementTree as ET
import itertools
from flask import Flask

# --- MINI-SERWER HTTP (DLA RENDER I UPTIMEROBOT) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot działa i ma się dobrze!", 200

def run_http_server():
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


# --- GŁÓWNY KOD BOTA ---
TOKEN = os.getenv("TOKEN")
DELETE_ROLE_ID = 1494687052975968306

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

YOUTUBE_CHANNEL_ID = "UCxwjc3YRZemIrOgUM1EGRDg"
DISCORD_NOTIFICATION_CHANNEL_ID = 1290353850196426844 
LAST_VIDEO_ID = None
IS_LIVE_NOW = False

statuses = itertools.cycle([
    discord.Game("Gram na PlayStation"),
    discord.Activity(type=discord.ActivityType.watching, name="najnowsze filmy PlayStation Polska"),
    discord.Activity(type=discord.ActivityType.listening, name="Twoich linków... to znaczy muzyki"),
    discord.Activity(type=discord.ActivityType.watching, name="redleefox'a przez okno"),
])

@tasks.loop(minutes=2)
async def change_status():
    global IS_LIVE_NOW
    await bot.wait_until_ready()
    
    if IS_LIVE_NOW:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="🔴 LIVE PlayStation Polska"))
    else:
        await bot.change_presence(activity=next(statuses))

@tasks.loop(minutes=2)
async def check_youtube():
    global LAST_VIDEO_ID, IS_LIVE_NOW
    await bot.wait_until_ready()
    
    channel = bot.get_channel(DISCORD_NOTIFICATION_CHANNEL_ID)
    if not channel:
        return

    # Sprawdzanie czy aktualnie trwa stream (wyszukiwanie flagi isLiveNow)
    live_url = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}/live"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(live_url) as live_response:
                if live_response.status == 200:
                    live_text = await live_response.text()
                    is_currently_live = '"isLive":true' in live_text or '"isLive": true' in live_text
                    
                    # Jeśli stream właśnie się zaczął (wcześniej było False, a teraz True)
                    if is_currently_live and not IS_LIVE_NOW:
                        embed = discord.Embed(
                            title="🔴 PlayStation Polska jest NA ŻYWO!",
                            description="Transmisja właśnie się rozpoczęła. Wpadajcie oglądać!",
                            url=live_url,
                            color=0xFF0000 # Czerwony kolor dla LIVE
                        )
                        await channel.send(content="Haloo! Właśnie odpalił się stream! 🎮", embed=embed)
                    
                    IS_LIVE_NOW = is_currently_live
    except Exception as e:
        print(f"Błąd sprawdzania statusu LIVE: {e}")

    # Sprawdzanie RSS dla nowych filmów/powiadomień
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
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
                        
                        if LAST_VIDEO_ID is None:
                            LAST_VIDEO_ID = video_id
                        elif video_id != LAST_VIDEO_ID:
                            LAST_VIDEO_ID = video_id
                            
                            embed = discord.Embed(
                                title=title,
                                url=link,
                                description=f"Nowy materiał na kanale **{author}**!",
                                color=0x003399
                            )
                            embed.set_image(url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")
                            
                            await channel.send(content="Nowy film/stream od PlayStation Polska! 🎮", embed=embed)
    except Exception as e:
        print(f"Błąd podczas sprawdzania YouTube: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def test_yt(ctx):
    """Wymusza pobranie najnowszego filmu w celu przetestowania powiadomień."""
    await ctx.send("Sprawdzam najnowszy film z PlayStation Polska (wymuszenie)...")
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
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


# --- SYSTEM OBSŁUGI I NAPRAWY LINKÓW ---
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com|facebook\.com|fb\.watch|fb\.com|instagram\.com|instagr\.am)/[^\s<>]+',
    re.IGNORECASE
)

async def unshorten_fb_url(url: str) -> str:
    """Rozwija skrócone mobilne linki typu facebook.com/share/ wyciągając URL z kodu HTML."""
    if "/share/" in url.lower() or "fb.com" in url.lower():
        try:
            # Dorzucamy User-Agent, żeby FB nie odrzucił połączenia bota
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        # Pobieramy tylko pierwsze 4000 bajtów kodu, żeby zaoszczędzić RAM/transfer na Renderze
                        html_start = await response.content.read(4000)
                        html_text = html_start.decode('utf-8', errors='ignore')
                        
                        # Szukamy oryginalnego, długiego linku zaszytego w meta tagu og:url
                        match = re.search(r'<meta\s+property="og:url"\s+content="([^"]+)"', html_text)
                        if match:
                            return match.group(1)
                            
                        # Alternatywny regex ratunkowy
                        match_alt = re.search(r'href="([^"]+)"', html_text)
                        if match_alt and "facebook.com/" in match_alt.group(1):
                            return match_alt.group(1)
        except Exception as e:
            print(f"Błąd podczas rozwijania linku FB: {e}")
    return url

def convert_url(url: str) -> str:
    # Wywalamy śmieci śledzące z aplikacji (mibextid, rdid itp.)
    url = re.sub(r'[\?&](?:mibextid|rdid|share_url_user_id|substory_index|ch)=[^&\s]+', '', url)
    
    # Zamiana na domeny generujące poprawne embedy
    url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:facebook\.com|fb\.watch|fb\.com)/', 'https://fixacebook.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.vxinstagram.com/', url, flags=re.IGNORECASE)
    return url


def has_delete_role():
    async def predicate(ctx):
        return any(role.id == DELETE_ROLE_ID for role in ctx.author.roles)
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f'Bot działa jako {bot.user}')
    if not check_youtube.is_running():
        check_youtube.start()
    if not change_status.is_running():
        change_status.start()

# --- KOMENDA DO TWORZENIA RANG ---
@bot.command()
@commands.has_permissions(manage_roles=True)
async def setup_roles(ctx, title: str, *args):
    """Przykład: !setup_roles "Wybierz Role" 🎮 @Gracz 🎨 @Artysta"""
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


# --- USUWANIE WIADOMOŚCI PO ID ---
@bot.command(name="uw")
@has_delete_role()
@commands.bot_has_permissions(manage_messages=True)
async def usun_wiadomosci(ctx, *message_ids: int):
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
            await ctx.send("Wystąpił błąd.", delete_after=5)
            return

    await ctx.send(f"Usunięto: {deleted} | Nie znaleziono: {not_found}", delete_after=5)


# --- OBSŁUGA EVENTU WIADOMOŚCI ---
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
        # 1. Pobieramy początek kodu HTML strony i wyciągamy pełny URL ukryty za /share/
        resolved_url = await unshorten_fb_url(url)
        
        # 2. Czyścimy parametry trackingowe i podmieniamy domenę na fixacebook
        fixed = convert_url(resolved_url)
        
        if fixed not in seen:
            seen.add(fixed)
            responses.append(f"{message.author.display_name} wysyła link:\n{fixed}")

    if responses:
        await message.reply("\n\n".join(responses), mention_author=False)
        try:
            await message.delete()
        except:
            pass


# --- SYSTEM REAKCJI (CZYTANIE Z WIADOMOŚCI) ---
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    
    channel = guild.get_channel(payload.channel_id)
    if not channel: return

    try:
        message = await channel.fetch_message(payload.message_id)
    except:
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
                    member = guild.get_member(payload.user_id)
                    if not member:
                        member = await guild.fetch_member(payload.user_id)
                    await member.add_roles(role)
            break

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild: return
    
    channel = guild.get_channel(payload.channel_id)
    if not channel: return

    try:
        message = await channel.fetch_message(payload.message_id)
    except:
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
                    member = guild.get_member(payload.user_id)
                    if not member:
                        try:
                            member = await guild.fetch_member(payload.user_id)
                        except:
                            return
                    await member.remove_roles(role)
            break


# --- START PROCESÓW ---
if __name__ == "__main__":
    # Serwer pod UptimeRobot i Rendera
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()

    # Odpalenie bota
    bot.run(TOKEN)
