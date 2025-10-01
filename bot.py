import discord
from discord.ext import commands, tasks
import os
import aiohttp
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from config import RADIO_STREAM_URL
import asyncio

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
api_connection_failed = False
radio_status = {}

async def fetch_radio_metadata():
    """Fetch WSM 650 AM metadata from Icecast status endpoint and cache details"""
    global current_song, listener_count, api_connection_failed, radio_status
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://stream01048.westreamradio.com/status-json.xsl') as response:
                if response.status == 200:
                    data = await response.json()
                    icestats = data.get('icestats', {}) or {}
                    source = icestats.get('source', {})
                    if isinstance(source, list) and source:
                        preferred = None
                        for item in source:
                            listenurl = item.get('listenurl', '') or ''
                            name = item.get('server_name', '') or ''
                            if 'wsm-am-mp3' in listenurl or 'WSM-AM' in name:
                                preferred = item
                                break
                        source = preferred or source[0]

                    audio_info = source.get('audio_info', '') or ''
                    bitrate_kbps = None
                    for part in audio_info.split(','):
                        part = part.strip()
                        if part.startswith('bitrate='):
                            try:
                                bitrate_kbps = int(part.split('=', 1)[1])
                            except Exception:
                                bitrate_kbps = None

                    radio_status = {
                        'icestats': {
                            'admin': icestats.get('admin'),
                            'host': icestats.get('host'),
                            'location': icestats.get('location'),
                            'server_id': icestats.get('server_id'),
                            'server_start': icestats.get('server_start'),
                            'server_start_iso8601': icestats.get('server_start_iso8601'),
                            'source': {
                                'audio_info': source.get('audio_info'),
                                'bitrate_kbps': bitrate_kbps,
                                'genre': source.get('genre'),
                                'listener_peak': source.get('listener_peak'),
                                'listeners': source.get('listeners'),
                                'listenurl': source.get('listenurl'),
                                'server_description': source.get('server_description'),
                                'server_name': source.get('server_name'),
                                'server_type': source.get('server_type'),
                                'server_url': source.get('server_url'),
                                'stream_start': source.get('stream_start'),
                                'stream_start_iso8601': source.get('stream_start_iso8601'),
                                'title': source.get('title'),
                                'yp_currently_playing': source.get('yp_currently_playing')
                            }
                        }
                    }

                    preferred_title = source.get('yp_currently_playing') or source.get('title') or 'WSM 650 AM'
                    current_song = preferred_title
                    listener_count = source.get('listeners', 0) or 0
                    api_connection_failed = False
                else:
                    raise RuntimeError(f"HTTP {response.status}")
    except Exception as e:
        logger.error(f"Error fetching radio metadata: {e}")
        current_song = "WSM 650 AM"
        listener_count = 0
        radio_status = {}
        api_connection_failed = True

async def update_bot_presence():
    """Update bot Rich Presence"""
    if api_connection_failed:
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="WSM 650 AM",
            details="Radio streaming is temporarily unavailable",
            state="🌐 Radio streaming is temporarily unavailable"
        )
    else:
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

@bot.tree.command(name="play", description="Play WSM 650 AM radio")
async def play_wsm(interaction: discord.Interaction):
    if interaction.user.voice is None:
        await interaction.response.send_message("You must join a voice channel first!", ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if voice_client is None:
        try:
            await voice_channel.connect(timeout=20.0, reconnect=True)
        except Exception as e:
            await interaction.response.send_message("❌ Failed to connect to the voice channel (timeout). Please try again.", ephemeral=True)
            logger.error(f"Failed to connect to voice: {e}")
            return
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
        
    except asyncio.TimeoutError:
        await interaction.edit_original_response(content="❌ Voice connection timed out. Please try again or switch a region.")
        logger.error("Voice connect/play timed out")
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
    embed.add_field(
        name="/info",
        value="Show current station info",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name="info", description="Show current station info")
async def info(interaction: discord.Interaction):
    await fetch_radio_metadata()
    
    start_time = interaction.created_at.timestamp()
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="📻 WSM 650 AM — Now Playing",
        description="Live track and station status",
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
        name="🎵 Title",
        value=f"{radio_status.get('icestats', {}).get('source', {}).get('title', 'N/A')}",
        inline=True
    )
    embed.add_field(
        name="🎼 Genre",
        value=f"{radio_status.get('icestats', {}).get('source', {}).get('genre', 'N/A')}",
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
        try:
            if not discord.opus.is_loaded():
                discord.opus.load_opus('opus')
                logger.info("Loaded Opus library")
        except Exception as e:
            logger.warning(f"Opus may not be loaded: {e}")
        logger.info("Starting WSM 650 AM Radio Bot...")
        bot.run(BOT_TOKEN)
