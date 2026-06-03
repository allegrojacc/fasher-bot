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

# Lista kanałów, na których bot przetwarza promocje z PS Store
PROMO_CHANNELS = [
    1321787613522427964,  # Główny kanał promek
    1508226473176334366   # Nowy kanał testowy bota
]

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

def convert_url(url: str) -> str:
    url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.vxinstagram.com/', url, flags=re.IGNORECASE)
    return url

# ZAKTUALIZOWANA FUNKCJA: Ściąga prawidłowe ceny dla produktów z trialem i ignoruje tekst "Wersja próbna gry"
async def get_ps_game_details(url: str) -> tuple[str, dict]:
    nazwa = "Gra PlayStation"
    detale = {
        "cena_reg": "Sprawdź w sklepie",
        "cena_plus": None,
        "image_url": None,
        "description": "Brak opisu gry."
    }
    
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
                    
                    # 1. Tytuł gry z tagu <title>
                    if soup.title and soup.title.string:
                        title_str = soup.title.string
                        if "|" in title_str:
                            title_str = title_str.split('|')[0].strip()
                        nazwa = title_str

                    # 2. Opis (sztywne ucięcie do 160 znaków) i obrazek z JSON-LD
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
                        except:
                            pass

                    # 3. Precyzyjne wyciąganie cen TYLKO dla aktywnej, głównej edycji gry
                    cena_standardowa = None
                    cena_promocyjna_plus = None
                    active_cta_id = None

                    # KROK A: Szukamy activeCtaId głównego produktu, żeby odciąć boczne edycje
                    for script in soup.find_all("script"):
                        if script.string and "activeCtaId" in script.string:
                            cta_match = re.search(r'"activeCtaId"\s*:\s*"([^"]+)"', script.string)
                            if cta_match:
                                active_cta_id = cta_match.group(1)
                                break

                    # KROK B: Parsujemy ceny należące wyłącznie do aktywnego boku zakupowego
                    for script in soup.find_all("script"):
                        if script.string and "ctaWithPrice" in script.string:
                            text_content = script.string
                            
                            if active_cta_id and active_cta_id not in text_content:
                                continue  # Pomijamy śmieci z innych edycji
                            
                            # Ignorujemy skrypty wersji próbnych (Trial) na poziomie struktury Next.js
                            if "UPSELL_PS_PLUS_TRIAL" in text_content or "game_trial" in text_content:
                                continue

                            base_match = re.search(r'"basePrice"\s*:\s*"([^"]+)"', text_content)
                            discount_match = re.search(r'"discountedPrice"\s*:\s*"([^"]+)"', text_content)
                            
                            if base_match:
                                temp_base = base_match.group(1).replace("zl", "zł").strip()
                                # Odrzucamy tekstową cenę triala, ale pozwalamy na kwotę cyfrową
                                if "Wersja" not in temp_base and "próbna" not in temp_base:
                                    cena_standardowa = temp_base
                                    
                            if discount_match:
                                stan_ceny = discount_match.group(1).replace("zl", "zł").strip()
                                if "Wersja" not in stan_ceny and "próbna" not in stan_ceny:
                                    if "UPSELL_PS_PLUS_DISCOUNT" in text_content or '"isTiedToSubscription":true' in text_content:
                                        cena_promocyjna_plus = stan_ceny
                                    else:
                                        cena_standardowa = stan_ceny
                            
                            # Przerywamy pętlę tylko wtedy, gdy udało się wyciągnąć prawdziwą kwotę standardową
                            if active_cta_id and cena_standardowa:
                                break

                    # 4. Przypisywanie przefiltrowanych danych
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

    # Najpierw usuwamy wiadomość użytkownika, który wpisał komendę !uw
    try:
        await ctx.message.delete()
    except:
        pass

    if not message_ids:
        # Wysyłanie w trybie silent (bez pingu)
        await ctx.send("Podaj ID wiadomości do usunięcia. Przykład: `!uw 123456789012345678`", delete_after=8, silent=True)
        return

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
            await ctx.send("Wystąpił błąd.", delete_after=5, silent=True)
            return

    # Raport końcowy również wysyłany jest w trybie silent
    await ctx.send(f"Usunięto: {deleted} | Nie znaleziono: {not_found}", delete_after=5, silent=True)


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

    seen = set()

    for url in urls:
        url_lower = url.lower()
        
        # 1. Obsługa PlayStation Store (Własny estetyczny Embed)
        if "store.playstation.com" in url_lower:
            if message.channel.id not in PROMO_CHANNELS:
                continue
                
            if url not in seen:
                seen.add(url)
                
                try:
                    await message.delete()
                except:
                    pass
                
                nazwa_gry, detale = await get_ps_game_details(url)
                
                embed = discord.Embed(
                    title=nazwa_gry,
                    url=url,
                    description=detale["description"],
                    color=0x00439C  # Oficjalny niebieski kolor PlayStation
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

        # 2. Obsługa Social Mediów (Twitter/X, Insta, Facebook)
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
                    await message.channel.send(
                        f"{hyperlink}\n"
                        f"> ⚠️ *Niestety, aby zobaczyć zawartość tego linku, wymagane jest zalogowanie do serwisu Facebook.*"
                    )
                    try: await message.delete()
                    except: pass
            else:
                fixed = convert_url(url)
                if fixed not in seen:
                    seen.add(fixed)
                    hyperlink = f"> [**{message.author.display_name} wysyła link do** ***{platforma}***]({fixed})"
                    await message.channel.send(hyperlink)
                    try: await message.delete()
                    except: pass


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
