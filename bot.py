import os
import re
import discord
from discord.ext import commands

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com|facebook\.com|fb\.watch)/[^\s<>]+',
    re.IGNORECASE
)

def convert_url(url: str) -> str:
    url = re.sub(
        r'https?://(?:www\.)?(?:x\.com|twitter\.com)/',
        'https://fixupx.com/',
        url,
        flags=re.IGNORECASE
    )

    url = re.sub(
        r'https?://(?:www\.)?facebook\.com/',
        'https://fixacebook.com/',
        url,
        flags=re.IGNORECASE
    )

    url = re.sub(
        r'https?://(?:www\.)?fb\.watch/',
        'https://fixacebook.com/',
        url,
        flags=re.IGNORECASE
    )

    return url

def get_service_name(url: str) -> str:
    if re.search(r'(x\.com|twitter\.com)', url, re.IGNORECASE):
        return "X/Twitter"

    if re.search(r'(facebook\.com|fb\.watch)', url, re.IGNORECASE):
        return "Facebook"

    return "link"

@bot.event
async def on_ready():
    print(f'Bot działa jako {bot.user} ({bot.user.id})')

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.webhook_id is not None:
        return

    urls = [match.group(0) for match in URL_PATTERN.finditer(message.content)]
    if not urls:
        return

    responses = []
    seen = set()
    username = message.author.display_name

    for url in urls:
        fixed = convert_url(url)

        if fixed in seen:
            continue

        seen.add(fixed)

        service = get_service_name(url)
        responses.append(f"{username} wysyła link do {service}:\n{fixed}")

    await message.reply("\n\n".join(responses), mention_author=False)

    try:
        await message.delete()
    except discord.Forbidden:
        print("Brak uprawnień do usuwania wiadomości.")
    except discord.HTTPException:
        print("Nie udało się usunąć wiadomości.")

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Ustaw zmienną środowiskową TOKEN z tokenem bota.")
    bot.run(TOKEN)
