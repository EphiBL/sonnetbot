import discord
import os
import logging
from dotenv import load_dotenv
import anthropic
import asyncio
import utils
import sqlite3
import state
from discord.ext import commands

def init_database():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_settings (
            guild_id INTEGER PRIMARY KEY,
            response_channel_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

if TOKEN is None:
    raise ValueError("No token found. Make sure DISCORD_TOKEN is set in your .env file")
if ANTHROPIC_API_KEY is None:
    raise ValueError("No Sonnet 3.5 api-key found, Make sure to set ANTHROPIC_API_KEY in your .env file")

# Init important variables
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)
bots = {}

@bot.command()
async def set_channel(ctx, id):
    print("set channel triggered")
    bots[ctx.guild].update_response_channel(int(id))
    print(f"{ctx.guild.id}")
    await ctx.send(f"New response channel set")

@bot.command()
async def sonnetlog(ctx):
    print(f'Bots = {bots}')
    
# Privately dm the caller asking for their api key
@bot.command()
async def set_key(ctx):
    try:
        await ctx.author.send("Please enter your API key. For security, never share your API key in public channels.")

        def check(m):
            return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)
        
        msg = await bot.wait_for('message', check=check, timeout=180.0)

        global ANTHROPIC_API_KEY
        ANTHROPIC_API_KEY = msg.content

        # We store the api key securely kappa
        await ctx.author.send("API key received. (In a real scenario, securely store this key)")
    except discord.Forbidden:
        await ctx.send("I couldn't send you a DM. Please check your privacy settings and try again.")
    except asyncio.TimeoutError:
        await ctx.author.send("You didn't respond in time. Please try the command again when you're ready.")

@bot.event
async def on_ready():
    init_database()
    for guild in bot.guilds:
        bot_instance = state.BotServerState(guild)
        bots[guild] = bot_instance
    print(f'We have logged in as {bot.user}')

@bot.event
async def on_thread_delete(thread):
    server_bot = bots[thread.guild]
    if thread.id in server_bot.active_thread_ids:
        server_bot.active_thread_ids.remove(thread.id)
        print(f"Thread {thread.id} has been deleted and removed from active threads.")

@bot.event
async def on_thread_update(before, after):
    server_bot = bots[before.guild]
    if before.id in server_bot.active_thread_ids and after.archived:
        server_bot.active_thread_ids.remove(after.id)
        print(f"Thread {after.id} has been archived and removed from active threads.")

@bot.event
async def on_message(message):
    if message.author == bot.user:
         return
    if message.content.startswith('\\'):
        return

    await bot.process_commands(message)

    if isinstance(message.channel, discord.Thread) and message.channel.id in bots[message.guild].active_thread_ids:
        sys_prompt = await utils.get_system_prompt(message.channel, 'systemprompt.md')
        thread_history = await utils.get_thread_history(bot, message.channel)
        if thread_history and thread_history[0]['role'] == 'assistant':
            thread_history.insert(0, {"role": "user", "content": "Starting conversation"}) # Spoof a message if the first message is from the assistant
        response = await utils.get_claude_response(message.channel, claude_client, thread_history, sys_prompt)
        try:
            bot_message = await utils.send_long_message(message.channel, response)
        except Exception as e:
            await message.channel.send("Bot message failed to send.")


@bot.command()
async def stream(ctx):
    text = """Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia."""

    lines = text.split('\n')
    message = await ctx.send("Streaming...")

    for i in range(len(lines)):
        await asyncio.sleep(0.25)  # Adjust this delay as needed
        await message.edit(content='\n'.join(lines[:i+1]))

    await message.edit(content=f"{text}\n\nStreaming complete!")


@bot.command()
async def chat(ctx, *text, thread_type=discord.ChannelType.public_thread, auto_archive_duration=60):
    msg = ctx.message
    try:
        await ctx.message.delete()
    except discord.errors.NotFound:
        print("Message already deleted or not found.")
    except discord.errors.Forbidden:
        print("Bot doesn't have permission to delete the message.")

    loading_message = await ctx.send("Loading...")

    # Get the chat_title
    command_message = " ".join(text)
    command_message = command_message[0].upper() + command_message[1:]
    header_prompt = await utils.get_system_prompt(ctx.channel, 'headerprompt.md')
    messages = [{"role": "user", "content": command_message}]
    header_response = await utils.get_claude_response(ctx.channel, claude_client, messages, header_prompt)

    # Get the main response
    cleaned_message = msg.content[6:]
    messages = [{"role": "user", "content": cleaned_message}]
    sys_prompt = await utils.get_system_prompt(msg.channel, 'systemprompt.md')
    response = await utils.get_claude_response(ctx.channel, claude_client, messages, sys_prompt)
    full_response =f"**Question: {cleaned_message}**\n\n{response}"

    # Create the converation thread
    bot_instance = bots[ctx.guild]
    response_channel = bot.get_channel(int(bot_instance.response_channel_id))
    if response_channel:
        thread = await response_channel.create_thread(
            name=header_response[:100],
            auto_archive_duration=60, 
            type=discord.ChannelType.public_thread
        )

        try:
            bot_message = await utils.send_long_message(thread, full_response)
        except Exception as e:
            await ctx.channel.send("Bot_message failed to send")

        thread_link = f"https://discord.com/channels/{msg.guild.id}/{thread.id}/{bot_message.id}"
        await msg.channel.send(f"Question: `{command_message}`\nAnswer: {thread_link}")
        bot_instance.add_active_thread(thread.id)

    else:
        await msg.channel.send("Error: Response channel not found, or not set.")
    await loading_message.delete()


@bot.command()
async def q(ctx, *text):
    loading_message = await ctx.channel.send("Loading...")
    command_message = " ".join(text)
    sys_prompt = await utils.get_system_prompt(ctx.channel, 'systemprompt.md')
    messages = [{"role": "user", "content": command_message}]
    response = await utils.get_claude_response(ctx.channel, claude_client, messages, sys_prompt)
    bot_message = await utils.send_long_message(ctx.channel, response)
    await loading_message.delete()


path = utils.get_log_file_path()
utils.clear_log_file(path)
handler = logging.FileHandler(filename=path, encoding='utf-8', mode='w')

print("Attempting to log in...")
bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)