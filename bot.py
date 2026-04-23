import os
import re
import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # potrzebne do czytania treści wiadomości

bot = commands.Bot(command_prefix="!", intents=intents)

URL_PATTERN = re.compile(
    r'https?://(?:www\.)?(?:x\.com|twitter\.com)/[^\s<>]+',
    re.IGNORECASE
)

def convert_to_fixupx(url: str) -> str:
    url = re.sub(
        r'https?://(?:www\.)?x\.com/',
        'https://fixupx.com/',
        url,
        flags=re.IGNORECASE
    )
    url = re.sub(
        r'https?://(?:www\.)?twitter\.com/',
        'https://fixupx.com/',
        url,
        flags=re.IGNORECASE
    )
    return url

@bot.event
async def on_ready():
    print(f'Bot działa jako {bot.user} ({bot.user.id})')

@bot.event
async def on_message(message: discord.Message):
    # ignoruj boty i webhooki
    if message.author.bot or message.webhook_id is not None:
        return

    urls = [match.group(0) for match in URL_PATTERN.finditer(message.content)]
    if not urls:
        return

    fixed_urls = []
    for url in urls:
        fixed = convert_to_fixupx(url)
        if fixed not in fixed_urls:
            fixed_urls.append(fixed)

    await message.reply("\n".join(fixed_urls), mention_author=False)

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Ustaw zmienną środowiskową DISCORD_TOKEN z tokenem bota.")
    bot.run(TOKEN)
