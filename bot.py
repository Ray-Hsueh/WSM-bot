import discord
from discord.ext import commands, tasks
import os
import aiohttp
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from config import RADIO_STREAM_URL

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()

bot = commands.Bot(command_prefix='!', intents=intents)

current_song = "WSM 650 AM"
listener_count = 0
is_playing = False

async def fetch_radio_metadata():
    """Fetch WSM 650 AM metadata"""
    global current_song, listener_count
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://stream01048.westreamradio.com/status-json.xsl') as response:
                if response.status == 200:
                    data = await response.json()
                    source = data.get('icestats', {}).get('source', {})
                    current_song = source.get('title', 'WSM 650 AM')
                    listener_count = source.get('listeners', 0)
                    logger.info(f"Currently playing: {current_song} | Listeners: {listener_count}")
    except Exception as e:
        logger.error(f"Error fetching radio metadata: {e}")
        current_song = "WSM 650 AM"
        listener_count = 0

async def update_bot_presence():
    """Update bot Rich Presence"""
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name=f"{current_song}",
        details=f"WSM 650 AM",
        state=f"👥 {listener_count} listeners"
    )
    await bot.change_presence(activity=activity)

@tasks.loop(seconds=30)
async def periodic_update():
    """Periodically update radio information"""
    await fetch_radio_metadata()
    await update_bot_presence()

@bot.event
async def on_ready():
    logger.info(f'Bot {bot.user} has successfully logged in!')
    logger.info('------')
    
    try:
        synced = await bot.tree.sync()
        logger.info(f'Synced {len(synced)} slash commands')
    except Exception as e:
        logger.error(f'Error syncing slash commands: {e}')
    
    await fetch_radio_metadata()
    await update_bot_presence()
    periodic_update.start()
    
    for guild in bot.guilds:
        voice_client = discord.utils.get(bot.voice_clients, guild=guild)
        if voice_client and voice_client.is_connected():
            logger.info(f"Reconnecting to voice channel in {guild.name}")
            try:
                source = discord.FFmpegPCMAudio(RADIO_STREAM_URL)
                voice_client.play(source)
                global is_playing
                is_playing = True
                logger.info(f"Resumed playing in {guild.name}")
                
                channel = voice_client.channel
                if channel:
                    try:
                        await channel.send("🔄 **Bot restarted** - Automatically resumed playing WSM 650 AM!")
                    except Exception as e:
                        logger.error(f"Could not send message to {channel.name}: {e}")
                        
            except Exception as e:
                logger.error(f"Error resuming playback in {guild.name}: {e}")

@bot.tree.command(name="play", description="Play WSM 650 AM radio")
async def play_wsm(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("You must join a voice channel first!", ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if voice_client is None:
        await voice_channel.connect()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if voice_client.is_playing():
        voice_client.stop()

    await interaction.response.send_message("🔄 Connecting and playing radio...")
    
    try:
        source = discord.FFmpegPCMAudio(RADIO_STREAM_URL)
            
        voice_client.play(source)
        
        global is_playing
        is_playing = True
        await fetch_radio_metadata()
        await update_bot_presence()
        
        await interaction.edit_original_response(content=f'▶️ Now playing WSM 650 AM in **{voice_channel.name}**')
        
    except Exception as e:
        if "ffmpeg was not found" in str(e):
            await interaction.edit_original_response(content="❌ FFmpeg not found")
        else:
            await interaction.edit_original_response(content=f"Error playing stream: {e}")
        logger.error(f"Error playing stream: {e}")

@bot.tree.command(name="stop", description="Stop playing and leave voice channel")
async def stop(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_connected():
        global is_playing
        is_playing = False
        await voice_client.disconnect()
        await update_bot_presence()
        await interaction.response.send_message("⏹️ Stopped playing and left voice channel.")
    else:
        await interaction.response.send_message("I'm not currently in any voice channel.", ephemeral=True)

@bot.tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Playback paused.")
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

@bot.tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Playback resumed.")
    else:
        await interaction.response.send_message("No audio is currently paused.", ephemeral=True)

@bot.tree.command(name="help", description="Show radio bot help")
async def help_radio(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📻 WSM 650 AM Radio Bot Commands",
        description="Available slash commands:",
        color=0x00ff00
    )
    embed.add_field(
        name="/play",
        value="Play WSM 650 AM radio",
        inline=False
    )
    embed.add_field(
        name="/pause",
        value="Pause playback",
        inline=True
    )
    embed.add_field(
        name="/resume",
        value="Resume playback",
        inline=True
    )
    embed.add_field(
        name="/stop",
        value="Stop playing and leave voice channel",
        inline=False
    )
    embed.add_field(
        name="/help",
        value="Show this help message",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="info", description="Show current playback information")
async def info(interaction: discord.Interaction):
    await fetch_radio_metadata()
    
    start_time = interaction.created_at.timestamp()
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="📻 WSM 650 AM Current Playback Info",
        color=0x00ff00
    )
    embed.add_field(
        name="🎵 Currently Playing",
        value=current_song,
        inline=False
    )
    embed.add_field(
        name="👥 Listeners",
        value=f"{listener_count}",
        inline=True
    )
    embed.add_field(
        name="📡 Playback Status",
        value="Playing" if is_playing else "Not Playing",
        inline=True
    )
    embed.add_field(
        name="🖥️ Server Info",
        value=f"Hosted on Hetzner AX162-R dedicated server\n📍 Helsinki, Finland\n⚡ {latency}ms latency",
        inline=False
    )
    embed.add_field(
        name="⭐ Support Us",
        value="If you're enjoying WSM 650 AM Discord bot, please consider leaving a review on Top.gg!\nhttps://top.gg/bot/1416695100519616532#reviews",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

if __name__ == "__main__":
    BOT_TOKEN = os.getenv('DISCORD_TOKEN')
    if not BOT_TOKEN:
        logger.error("Error: Please set DISCORD_TOKEN in .env file!")
    else:
        logger.info("Starting WSM 650 AM Radio Bot...")
        bot.run(BOT_TOKEN)
