import discord
from discord.ext import commands, tasks
import os
import aiohttp
import json
from dotenv import load_dotenv
from config import RADIO_STREAM_URL

load_dotenv()

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
                    print(f"Currently playing: {current_song} | Listeners: {listener_count}")
    except Exception as e:
        print(f"Error fetching radio metadata: {e}")
        current_song = "WSM 650 AM"
        listener_count = 0

async def update_bot_presence():
    """Update bot Rich Presence"""
    if is_playing:
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=f"{current_song}",
            details=f"WSM 650 AM",
            state=f"👥 {listener_count} listeners"
        )
    else:
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="WSM 650 AM",
            details="Radio Station",
            state="Standby"
        )
    await bot.change_presence(activity=activity)

@tasks.loop(seconds=30)
async def periodic_update():
    """Periodically update radio information"""
    if is_playing:
        await fetch_radio_metadata()
        await update_bot_presence()

@bot.event
async def on_ready():
    print(f'Bot {bot.user} has successfully logged in!')
    print('------')
    
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash commands')
    except Exception as e:
        print(f'Error syncing slash commands: {e}')
    
    periodic_update.start()
    await update_bot_presence()

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
        ffmpeg_path = os.path.join(os.getcwd(), 'ffmpeg-master-latest-win64-gpl', 'bin', 'ffmpeg.exe')
        
        if os.path.exists(ffmpeg_path):
            source = discord.FFmpegPCMAudio(RADIO_STREAM_URL, executable=ffmpeg_path)
        else:
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
        print(f"Error playing stream: {e}")

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
    await interaction.response.send_message(embed=embed, ephemeral=False)

if __name__ == "__main__":
    BOT_TOKEN = os.getenv('DISCORD_TOKEN')
    if not BOT_TOKEN:
        print("Error: Please set DISCORD_TOKEN in .env file!")
    else:
        bot.run(BOT_TOKEN)
