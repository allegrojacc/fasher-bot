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

URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com|facebook\.com|fb\.watch|instagram\.com|instagr\.am|store\.playstation\.com)/[^\s<>]+',
    re.IGNORECASE
)

def convert_url(url: str) -> str:
    url = re.sub(r'https?://(?:www\.)?(?:x\.com|twitter\.com)/', 'https://fixupx.com/', url, flags=re.IGNORECASE)
    url = re.sub(r'https?://(?:www\.)?(?:instagram\.com|instagr\.am)/', 'https://www.vxinstagram.com/', url, flags=re.IGNORECASE)
    return url

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
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "pl-PL,pl;q=0.9"}
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    if soup.title and soup.title.string:
                        nazwa = soup.title.string.split('|')[0].strip()

                    json_ld_tag = soup.find("script", id="mfe-jsonld-tags")
                    if json_ld_tag and json_ld_tag.string:
                        try:
                            data = json.loads(json_ld_tag.string)
                            if "description" in data:
                                full_desc = data["description"].strip()
                                if len(full_desc) > 160:
                                    truncated = full_desc[:160]
                                    if " " in truncated: truncated = truncated.rsplit(" ", 1)[0]
                                    detale["description"] = truncated + "..."
                                else: detale["description"] = full_desc
                            if "image" in data: detale["image_url"] = data["image"]
                        except: pass

                    active_cta_id = None
                    for script in soup.find_all("script"):
                        if script.string and "activeCtaId" in script.string:
                            cta_match = re.search(r'"activeCtaId"\s*:\s*"([^"]+)"', script.string)
                            if cta_match:
                                active_cta_id = cta_match.group(1)
                                break
                    
                    if active_cta_id:
                        for script in soup.find_all("script"):
                            if script.string and active_cta_id in script.string:
                                text_content = script.string
                                if "UPSELL_PS_PLUS_TRIAL" in text_content or "game_trial" in text_content: continue
                                base_match = re.search(r'"basePrice"\s*:\s*"([^"]+)"', text_content)
                                discount_match = re.search(r'"discountedPrice"\s*:\s*"([^"]+)"', text_content)
                                if base_match:
                                    temp_base = base_match.group(1).replace("zl", "zł").strip()
                                    if "Wersja" not in temp_base and "próbna" not in temp_base: detale["cena_reg"] = temp_base
                                if discount_match:
                                    stan_ceny = discount_match.group(1).replace("zl", "zł").strip()
                                    if "Wersja" not in stan_ceny and "próbna" not in stan_ceny:
                                        if "UPSELL_PS_PLUS_DISCOUNT" in text_content or '"isTiedToSubscription":true' in text_content: detale["cena_plus"] = stan_ceny
                                        else: detale["cena_reg"] = stan_ceny
                                break
    except Exception as e: print(f"Błąd: {e}")
    return nazwa, detale

def has_delete_role():
    async def predicate(ctx):
        return any(role.id == DELETE_ROLE_ID for role in ctx.author.roles)
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f'Bot działa jako {bot.user}')
    if not check_youtube.is_running(): check_youtube.start()
    if not change_status.is_running(): change_status.start()

@bot.command()
@commands.has_permissions(manage_roles=True)
async def setup_roles(ctx, title: str, *args):
    if len(args) % 2 != 0:
        await ctx.send("Podaj pary: Emotka i Rola!")
        return
    desc = "Zareaguj, aby otrzymać rangę:\n"
    emojis_to_react = []
    for i in range(0, len(args), 2):
        desc += f"{args[i]} - {args[i+1]}\n"
        emojis_to_react.append(args[i])
    embed = discord.Embed(title=title, description=desc, color=0x00ff00)
    msg = await ctx.send(embed=embed)
    for emoji in emojis_to_react: await msg.add_reaction(emoji)

@bot.command(name="uw")
@has_delete_role()
@commands.bot_has_permissions(manage_messages=True)
async def usun_wiadomosci(ctx, *message_ids: int):
    deleted = 0
    not_found = 0
    if not message_ids:
        await ctx.send("Podaj ID wiadomości.", delete_after=5)
        return
    for msg_id in message_ids:
        try:
            msg = await ctx.channel.fetch_message(msg_id)
            await msg.delete()
            deleted += 1
        except: not_found += 1
    await ctx.send(f"Usunięto: {deleted} | Nie znaleziono: {not_found}", delete_after=5)

@bot.command(name="ew")
@has_delete_role()
async def edytuj_wiadomosc(ctx, message_id: int, *, nowa_tresc: str = None):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        if msg.author == bot.user:
            await msg.edit(content=nowa_tresc)
            await ctx.send("Zaktualizowano.", delete_after=3)
        await ctx.message.delete()
    except: await ctx.send("Błąd.", delete_after=5)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    await bot.process_commands(message)
    urls = [match.group(0) for match in URL_PATTERN.finditer(message.content)]
    if not urls: return
    seen = set()
    for url in urls:
        if "store.playstation.com" in url.lower():
            if message.channel.id not in PROMO_CHANNELS: continue
            if url not in seen:
                seen.add(url)
                try: await message.delete()
                except: pass
                nazwa, detale = await get_ps_game_details(url)
                embed = discord.Embed(title=nazwa, url=url, description=detale["description"], color=0x00439C)
                embed.set_author(name=f"Promka od: {message.author.display_name}", icon_url=message.author.display_avatar.url)
                if detale["cena_plus"]:
                    embed.add_field(name="💰 Cena Standardowa", value=f"~~{detale['cena_reg']}~~", inline=True)
                    embed.add_field(name="🟡 Cena z PS Plus", value=f"**{detale['cena_plus']}**", inline=True)
                else: embed.add_field(name="💰 Cena", value=f"**{detale['cena_reg']}**", inline=True)
                if detale["image_url"]: embed.set_image(url=detale["image_url"])
                await message.channel.send(embed=embed)
        else:
            platforma = "Social Media"
            if "x.com" in url.lower() or "twitter.com" in url.lower(): platforma = "Twitter/X"
            elif "instagram.com" in url.lower(): platforma = "Instagram"
            elif "facebook.com" in url.lower(): platforma = "Facebook"
            if platforma == "Facebook":
                await message.channel.send(f"> [**{message.author.display_name} wysyła link do** ***Facebooka***]({url})\n> ⚠️ Wymagane logowanie.")
            else:
                await message.channel.send(f"> [**{message.author.display_name} wysyła link do** ***{platforma}***]({convert_url(url)})")
            try: await message.delete()
            except: pass

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild or payload.user_id == bot.user.id: return
    channel = guild.get_channel(payload.channel_id)
    try:
        msg = await channel.fetch_message(payload.message_id)
        if msg.author == bot.user and msg.embeds and "Zareaguj, aby otrzymać rangę:" in msg.embeds[0].description:
            for line in msg.embeds[0].description.split('\n'):
                if str(payload.emoji) in line:
                    role_id = int(re.search(r'<@&(\d+)>', line).group(1))
                    member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
                    await member.add_roles(guild.get_role(role_id))
    except: pass

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    guild = bot.get_guild(payload.guild_id)
    if not guild or payload.user_id == bot.user.id: return
    channel = guild.get_channel(payload.channel_id)
    try:
        msg = await channel.fetch_message(payload.message_id)
        if msg.author == bot.user and msg.embeds and "Zareaguj, aby otrzymać rangę:" in msg.embeds[0].description:
            for line in msg.embeds[0].description.split('\n'):
                if str(payload.emoji) in line:
                    role_id = int(re.search(r'<@&(\d+)>', line).group(1))
                    member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
                    await member.remove_roles(guild.get_role(role_id))
    except: pass

if __name__ == "__main__":
    threading.Thread(target=run_http_server, daemon=True).start()
    bot.run(TOKEN)
