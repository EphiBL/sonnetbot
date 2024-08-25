import discord
import os
import logging
from dotenv import load_dotenv
import anthropic
import asyncio
import utils
from discord.ext import commands

async def get_thread_history(thread):
    messages = []
    async for msg in thread.history(limit=60, oldest_first=True):
        role = "assistant" if msg.author == bot.user else "user"
        messages.append({"role": role, "content": msg.content})
    return messages

# Use os package to get our .env file and load our keys
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
APP_ID = os.getenv('APP_ID')
PUBLIC_KEY = os.getenv('PUBLIC_KEY')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
RESPONSE_CHANNEL_ID = int(os.getenv('RESPONSE_CHANNEL_ID'))

# Throw errors if any of the keys are blank
if TOKEN is None:
    raise ValueError("No token found. Make sure DISCORD_TOKEN is set in your .env file")
if APP_ID is None:
    raise ValueError("No App_id found. Make sure APP_ID is set in your .env file")
if PUBLIC_KEY is None:
    raise ValueError("No PUBLIC_KEY found. Make sure PUBLIC_KEY is set in your .env file")
if ANTHROPIC_API_KEY is None:
    raise ValueError("No Sonnet 3.5 api-key found, Make sure to set ANTHROPIC_API_KEY in your .env file")
if RESPONSE_CHANNEL_ID is None:
    raise ValueError("No response channel id found. Make sure to set RESPONSE_CHANNEL_ID in your .env file")

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

active_thread_ids = []

has_api_key = False
has_target_channel_id = False

@bot.command()
async def set_channel(ctx, id):
    global RESPONSE_CHANNEL_ID
    RESPONSE_CHANNEL_ID = id
    ctx.send(f"New response channel set")
    
@bot.command()
async def set_key(ctx):
    # Privately dm the caller asking for their api key
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
    print(f'We have logged in as {bot.user}')

@bot.event
async def on_message(message):
    # This line is necessary to process commands
    if message.author == bot.user:
         return
    # Invoke Commands!
    await bot.process_commands(message)

    if (message.channel.type in [discord.ChannelType.public_thread, discord.ChannelType.private_thread] 
        and message.channel.id in active_thread_ids):

        # Get the system prompt
        current_dir = os.path.dirname(os.path.abspath(__file__))
        system_prompt_path = os.path.join(current_dir, 'systemprompt.md')
        system_prompt = await utils.read_file_async(system_prompt_path)
        if system_prompt is None:
            await message.channel.send("Error: unable to read system prompt.")
            return

        thread_history = await get_thread_history(message.channel)
        full_context = [
            {"role": "system", "content": system_prompt},
            *thread_history,
            {"role": "user", "content": message.content}
        ]

        content = message.content
        try:
            response = claude_client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens = 5000,
                messages=full_context
            )
            response_text = response.content[0].text

            response_message = await utils.send_long_message(message.channel, response_text)

        except Exception as e:
            await message.channel.send(f"An error occurred: {str(e)}")


@bot.event
async def on_thread_delete(thread):
    if thread.id in active_thread_ids:
        active_thread_ids.remove(thread.id)
        print(f"Thread {thread.id} has been deleted and removed from active threads.")

@bot.event
async def on_thread_update(before, after):
    if before.id in active_thread_ids and after.archived:
        active_thread_ids.remove(after.id)
        print(f"Thread {after.id} has been archived and removed from active threads.")

@bot.command()
async def chat(ctx, *text, thread_type=discord.ChannelType.public_thread, auto_archive_duration=60):
    message_copy = ctx.message
    cleaned_message = message_copy.content[6:]
    command_message = " ".join(text)
    command_message = command_message[0].upper() + command_message[1:]

    try:
        await ctx.message.delete()
    except discord.errors.NotFound:
        print("Message already deleted or not found.")
    except discord.errors.Forbidden:
        print("Bot doesn't have permission to delete the message.")

    loading_message = await ctx.send("Loading...")

    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Create the header_message
    header_prompt_path = os.path.join(current_dir, 'headerprompt.md')
    header_prompt = utils.read_file_async(header_prompt_path)
    header_message = f'{header_prompt}/n"{command_message}"'
    if header_prompt is None:
        await ctx.send("Error: Unable to read header prompt")
        return

    # Get the header_response
    try:
        header_response = claude_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=300,
            messages=[
                {"role": "user", "content": header_message}
            ]
        )
        header_text = header_response.content[0].text
    except Exception as e:
        await message_copy.channel.send(f"Error occurred with header request")

    # Get the system prompt
    system_prompt_path = os.path.dirname(os.path.abspath(__file__))
    system_prompt = utils.read_file_async(system_prompt_path)
    if system_prompt is None:
        await message_copy.channel.send(f"Error: Unable to read system prompt.")
        return

    full_message = f"{system_prompt}\n{cleaned_message}"
    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=3000,
            messages=[
                {"role": "user", "content": full_message}
            ]
        )

        # Create the converation thread
        response_channel = bot.get_channel(RESPONSE_CHANNEL_ID)
        if response_channel:
            thread = await response_channel.create_thread(
                name=header_text[:100],
                auto_archive_duration=60, 
                type=discord.ChannelType.public_thread
            )

            # Create the full response with formatting and send it
            full_response =f"""
**Question: {cleaned_message}**

{response.content[0].text}
"""
            first_message = await utils.send_long_message(thread, full_response)
            if first_message:
                thread_link = f"https://discord.com/channels/{message_copy.guild.id}/{thread.id}/{first_message.id}"

                # Post a link to the thread in the original channel
                await message_copy.channel.send(
f"""
Question: `{command_message}`
Answer: {thread_link}
"""
                )
            else:
                await message_copy.send("Error: Failed to send message in the thread.")
                if thread.id:
                    active_thread_ids.append(thread.id)
                else:
                    await message_copy.send("Error: No thread id, could not be added to active threads")
        else:
            await message_copy.channel.send("Error: Specified response channel not found.")
    except Exception as e:
        await message_copy.channel.send(f"An error occurred: {str(e)}")
    await loading_message.delete()


print(f"About to clear the log file")
path = utils.get_log_file_path()
utils.clear_log_file(path)
handler = logging.FileHandler(filename=path, encoding='utf-8', mode='w')
print(f"The log file is cleared")

# Reset active thread IDs
active_thread_ids.clear()
print(f"The active threads are cleared, the bot is about to run")
bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)