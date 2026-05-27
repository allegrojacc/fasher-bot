import os
import re
import threading
import json
import discord
from discord.ext import commands, tasks
from discord.ext.commands import BadArgument
import aiohttp
import xml.etree.ElementTree as ET
import itertools
from flask import Flask
from bs4 import BeautifulSoup

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
PROMO_CHANNEL_ID = 1321787613522427964  # Na tym kanale działają promki z PS Store

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

    # Sprawdzanie czy aktualnie trwa stream (wyszukiwanie flagi isLiveNow i unikanie zapowiedzi)
    live_url = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}/live"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(live_url) as live_response:
                if live_response.status == 200:
                    live_text = await live_response.text()
                    
                    has_live_marker = '"isLiveNow":true' in live_text or '"LAUNCHED_STYLE_LIVE"' in live_text
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
                            
                            await channel.send(content="Nowy materiał wleciał na kanał PlayStation Polska!", embed=embed)
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

# Wyłapuje społecznościówki oraz PlayStation Store
URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com|facebook\.com|fb\.watch|instagram\.com|instagr\.am|store\.playstation\.com)/[^\s<>]+',
    re.IGNORECASE
)

# Wzorzec do czyszczenia standardowych emoji oraz niestandardowych emotek Discorda <:nazwa:id>
EMOJI_PATTERN = re.compile(r'<a?:[a-zA-Z0-9_]+:[0-9]+>|[\u2600-\u27BF]|[\u1F300-\u1F9FF]', re.UNICODE)

def convert_url(url: str) -> str:
    url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.vxinstagram.com/', url, flags=re.IGNORECASE)
    return url

# Zoptymalizowana funkcja pobierająca dane gry oraz ceny (standardową i PS Plus) ze sklepu Sony
async def get_ps_game_details(url: str) -> tuple[str, str]:
    nazwa = "Gra PlayStation"
    cena_finalna = "Sprawdź w sklepie"
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "pl-PL,pl;q=0.9"
            }
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # 1. Wyciągamy tytuł z tagu <title>
                    if soup.title and soup.title.string:
                        title_str = soup.title.string
                        if "|" in title_str:
                            title_str = title_str.split('|')[0].strip()
                        nazwa = title_str

                    # 2. Szukamy wszystkich skryptów konfiguracyjnych JSON
                    cena_reg = None
                    cena_plus = None
                    
                    for script in soup.find_all("script", type="application/json"):
                        if not script.string:
                            continue
                        
                        script_content = script.string
                        # Jeśli skrypt zawiera tablicę cenową SkuPriceDetail
                        if "skuPriceDetail" in script_content:
                            try:
                                json_data = json.loads(script_content)
                                # Szukamy głęboko w pamięci podręcznej (cache) Next.js
                                cache = json_data.get("cache", {})
                                for key, item in cache.items():
                                    if isinstance(item, dict) and "skuPriceDetail" in item:
                                        details = item.get("skuPriceDetail", [])
                                        for d in details:
                                            branding = d.get("offerBranding", "NONE")
                                            formatted_price = d.get("discountPriceFormatted") or d.get("originalPriceFormatted")
                                            
                                            if formatted_price:
                                                # Czyszczenie zapisu ceny ze spacji (np. "77,70 zl" -> "77,70 zł")
                                                formatted_price = formatted_price.replace("zl", "zł").strip()
                                                if branding == "PS_PLUS":
                                                    cena_plus = formatted_price
                                                else:
                                                    cena_reg = formatted_price
                            except Exception:
                                pass

                    # 3. Jeśli nie znaleziono cen w cache, sprawdzamy standardowy tag ogólny ld+json
                    if not cena_reg:
                        json_tag = soup.find("script", id="mfe-jsonld-tags") or soup.find("script", type="application/ld+json")
                        if json_tag:
                            try:
                                data = json.loads(json_tag.string)
                                offers = data.get("offers")
                                if offers:
                                    raw_price = offers.get("price")
                                    if raw_price is not None:
                                        if float(raw_price) == 0:
                                            cena_reg = "Bezpłatne"
                                        else:
                                            cena_reg = f"{float(raw_price):.2f}".replace('.', ',') + " zł"
                            except Exception:
                                pass

                    # Składamy końcowy tekst ceny
                    if cena_reg and cena_plus and cena_reg != cena_plus:
                        cena_finalna = f"{cena_reg} ({cena_plus} z PS Plus ➕)"
                    elif cena_reg:
                        cena_finalna = cena_reg
                    elif cena_plus:
                        cena_finalna = f"{cena_plus} (Zniżka PS Plus ➕)"

    except Exception as e:
        print(f"Błąd podczas parsowania danych z PS Store: {e}")
        
    return nazwa, cena_finalna

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
            await ctx.send("Brak uprawnień do USAwania wiadomości.", delete_after=5)
            return
        except discord.HTTPException:
            await ctx.send("Wystąpił błąd.", delete_after=5)
            return

    await ctx.send(f"Usunięto: {deleted} | Nie znaleziono: {not_found}", delete_after=5)


# --- EDYTOWANIE WIADOMOŚCI BOTA PO ID ---
@bot.command(name="ew")
@has_delete_role()
async def edytuj_wiadomosc(ctx, message_id: int, *, nowa_tresc: str = None):
    if not nowa_tresc:
        await ctx.send("Musisz podać nową treść wiadomości po ID!", delete_after=5)
        try:
            await ctx.message.delete()
        except:
            pass
        return

    try:
        msg = await ctx.channel.fetch_message(message_id)
        
        if msg.author != bot.user:
            await ctx.send("Mogę edytować wyłącznie wiadomości mojego autorstwa!", delete_after=5)
            try:
                await ctx.message.delete()
            except:
                pass
            return

        await msg.edit(content=nowa_tresc)
        await ctx.send("Wiadomość została zaktualizowana.", delete_after=3)
        
        try:
            await ctx.message.delete()
        except:
            pass

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
        except:
            pass


# --- OBSŁUGA LINKÓW ---
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
        url_lower = url.lower()
        
        # 1. Obsługa PlayStation Store (Działa wyłącznie na wyznaczonym kanale promocyjnym)
        if "store.playstation.com" in url_lower:
            if message.channel.id != PROMO_CHANNEL_ID:
                continue  # Ignorujemy link do sklepu na innych kanałach, przechodzimy do kolejnych linków
                
            if url not in seen:
                seen.add(url)
                
                # Pobieramy automatycznie dane (w tym potencjalną podwójną cenę PS Plus)
                nazwa_gry, cena_gry = await get_ps_game_details(url)
                
                # Wzór: nick wysyła promke na nazwa gry w cenie cena
                tekst_promki = f"{message.author.display_name} wysyła promke na {nazwa_gry} w cenie {cena_gry}"
                hyperlink = f"> [**{tekst_promki}**]({url})"
                responses.append(hyperlink)

        # 2. Obsługa Social Mediów (Twitter/X, Insta, Facebook) - Działa na całym serwerze!
        else:
            if "x.com" in url_lower or "twitter.com" in url_lower:
                platforma = "Twitter/X"
            elif "instagram.com" in url_lower or "instagr.am" in url_lower:
                platforma = "Instagram"
            elif "facebook.com" in url_lower or "fb.watch" in url_lower:
                platforma = "Facebook"
            else:
                platforma = "Social Media"

            if platforma == "Facebook":
                if url not in seen:
                    seen.add(url)
                    hyperlink = f"> [**{message.author.display_name} wysyła link do** ***{platforma}***]({url})"
                    responses.append(
                        f"{hyperlink}\n"
                        f"> ⚠️ *Niestety, aby zobaczyć zawartość tego linku, wymagane jest zalogowanie do serwisu Facebook.*"
                    )
            else:
                fixed = convert_url(url)
                if fixed not in seen:
                    seen.add(fixed)
                    hyperlink = f"> [**{message.author.display_name} wysyła link do** ***{platforma}***]({fixed})"
                    responses.append(hyperlink)

    if responses:
        # Bezpieczne wysyłanie jako niezależny tekst bez błędu usuwania
        await message.channel.send("\n\n".join(responses))
        try:
            await message.delete()
        except:
            pass


# --- NOWY SYSTEM REAKCJI (CZYTANIE Z WIADOMOŚCI) ---
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
    server_thread = threading.Thread(target=run_http_server)
    server_thread.daemon = True
    server_thread.start()

    bot.run(TOKEN)
