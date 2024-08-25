from os import path
import aiofiles

def get_log_file_path():
    current_dir = path.dirname(path.abspath(__file__))
    log_file_path = path.join(current_dir, 'discord.log')
    return log_file_path

async def read_file_async(file_path):
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as file:
            content = await file.read()
        return content
    except FileNotFoundError:
        print(f"Error: {file_path} file not found.")
        return None
    except IOError:
        print(f"Error: Unable to read {file_path} file.")
        return None


def clear_log_file(file_path):
    try:
        with open(file_path, 'w') as file:
            file.write('')  # Write an empty string to clear the file
        print(f"Log file cleared: {file_path}")
    except IOError as e:
        print(f"Error clearing log file: {e}")

def split_message(message, limit=1750):  # Using 1900 to leave some room for formatting
    parts = []
    current_part = ""
    
    sentences = message.split('.')
    for sentence in sentences:
        if len(current_part) + len(sentence) + 1 > limit:
            if current_part:
                parts.append(current_part.strip())
            current_part = sentence + '.'
        else:
            current_part += sentence + '.'
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts

async def send_long_message(channel, message):
    message.rstrip('.')
    message = escape_discord_markdown(message)
    parts = split_message(message)
    first_message = None
    for i, part in enumerate(parts):
        sent_message = await channel.send(part)
        if i == 0:
            first_message = sent_message
    return first_message

def escape_discord_markdown(text):
    text = text.rstrip('.')
    # Characters to escape: ` * _ ~ > |
    chars_to_escape = []
    for char in chars_to_escape:
        text = text.replace(char, '\\' + char)
    return text

async def get_thread_history(bot, thread):
    messages = []
    async for msg in thread.history(limit=60, oldest_first=True):
        role = "assistant" if msg.author == bot.user else "user"
        messages.append({"role": role, "content": msg.content})
    return messages

async def get_system_prompt(channel, target_prompt):
    dir = path.dirname(path.abspath(__file__))
    system_prompt_path = path.join(dir, target_prompt)
    sys_prompt = await read_file_async(system_prompt_path)
    if sys_prompt is None:
        await channel.send(f"Error: Unable to read system prompt from {target_prompt}.")
        return
    return sys_prompt

async def get_claude_response(channel, client, messages=[], sys_prompt="", max_tokens=3000):
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=max_tokens,
            system = sys_prompt,
            messages=messages,
        )
        return response.content[0].text.rstrip('.')
    except Exception as e:
        await channel.send(f"An error occurred: {str(e)}")