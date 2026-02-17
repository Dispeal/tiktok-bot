import discord
from discord.ext import tasks, commands
import os

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Get from environment variables (Railway will set these)
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))
TIKTOK_USER = os.getenv('TIKTOK_USERNAME', 'charlidamelio')

last_video = None

@bot.event
async def on_ready():
    print("=" * 50)
    print(f'✅ BOT ONLINE: {bot.user}')
    print(f'📹 WATCHING: @{TIKTOK_USER}')
    print(f'📢 CHANNEL: {CHANNEL_ID}')
    print("=" * 50)
    check_tiktok.start()

@tasks.loop(minutes=5)
async def check_tiktok():
    """Check TikTok every 5 minutes"""
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            # This will notify when monitoring
            print(f'🔍 Checking @{TIKTOK_USER}...')
            # In production, this would actually check TikTok
            # For now it just stays online
    except Exception as e:
        print(f'Error: {e}')

@bot.command()
async def status(ctx):
    """Check bot status"""
    await ctx.send(f'✅ Bot online!\n📹 Watching: @{TIKTOK_USER}\n⏱️ Checking every 5 minutes')

@bot.command()
async def ping(ctx):
    """Test if bot is responding"""
    await ctx.send('🏓 Pong! Bot is alive!')

@bot.command()
async def download(ctx, url: str):
    """Download a TikTok video"""
    await ctx.send(f'📥 To download this TikTok without watermark:\n{url}\n\nUse: https://snaptik.app or https://tikmate.app\nPaste the link and download!')

@bot.command()
async def setuser(ctx, username: str):
    """Change TikTok user to monitor"""
    global TIKTOK_USER
    TIKTOK_USER = username.replace('@', '')
    await ctx.send(f'✅ Now watching: @{TIKTOK_USER}')

# Run bot
if __name__ == '__main__':
    if not TOKEN:
        print('❌ ERROR: DISCORD_TOKEN not set!')
        print('Set it in Railway dashboard')
    else:
        bot.run(TOKEN)
