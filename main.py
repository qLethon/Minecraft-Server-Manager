import subprocess
import time
import sys
from threading import Thread
from queue import Queue
import discord
import asyncio
import aiohttp

TOKEN = 'YOUR_TOKEN'
MINECRAFT_CHANNEL = 'YOUR_CHANNEL_NAME'  # The name of the channel used to send command and output server log. (e.g. 'minecraft-server')
LAUNCH_COMMAND = 'YOUR_LAUNCH_COMMAND'  # The command to launch your minecraft server. (e.g. 'java -Xmx1G -Xms1G -jar ./server.jar nogui)

client = discord.Client()
responses = Queue()
commands = Queue()

def start_server():
    return subprocess.Popen(LAUNCH_COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

def read_responses(p):
    for line in p.stdout:
        line = line.decode()
        if 'Fetching addPacket for removed entity' in line:
            continue
        responses.put(line)

def send_command(cmd, p):
    return subprocess.Popen(['python', './commander.py', cmd], stdin=subprocess.PIPE, stdout=p.stdin, stderr=subprocess.PIPE, shell=True)

async def command_list(channel, p):
    send_command('list', p)
    while True:
        time.sleep(0.1)
        if responses.empty():
            continue
        res = responses.get()
        if "There are" in res:
            break
    
    return res

async def get_my_global_ip():
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.ipify.org/') as resp:
            if resp.status != 200:
                return 'ERROR: ' + str(resp.status)
            return await resp.text()

async def main():
    p = start_server()
    r = Thread(target=read_responses, args=(p, ))
    r.start()
    for channel in client.get_all_channels():
        if channel.name == MINECRAFT_CHANNEL:
            minecraft_channel = channel
            break
    while True:
        await asyncio.sleep(0.5)
        
        if p.poll() is None and client.activity is None:
            activity = discord.Game(name='Minecraft Server')
            await client.change_presence(activity=activity)
            client.activity = activity
        elif p.poll() is not None and client.activity is not None:
            await client.change_presence(activity=None)
            client.activity = None

        while not responses.empty():
            res = responses.get()
            await minecraft_channel.send(res)

        while not commands.empty():
            message = commands.get()
            cmd = message.content.split()[1]
            if cmd == 'start':
                if p.poll() is None:
                    await message.channel.send('The server is already running.')
                    continue
                await message.channel.send('Starting a server...')
                p = start_server()
                r = Thread(target=read_responses, args=(p, ))
                r.start()

            elif cmd == 'stop' or cmd == 'reload':
                if p.poll() is not None:
                    await message.channel.send('The server is not runnning.')
                    continue
                res = await command_list(message.channel, p)
                await message.channel.send(res)
                m = await message.channel.send(cmd + ' this?')
                await m.add_reaction('👌')
                await m.add_reaction('💢')
                def check(reaction, user):
                    return user == message.author and str(reaction.emoji) == '👌'
                try:
                    reaction, user = await client.wait_for('reaction_add', timeout=30.0, check=check)
                except asyncio.TimeoutError:
                    await message.channel.send('Canceled')
                    continue
                send_command(cmd, p)
                    
            elif cmd == 'list':
                if p.poll() is not None:
                    await message.channel.send('The server is not runnning.')
                    continue
                res = await command_list(message.channel, p)
                await message.channel.send(res)

            elif cmd == 'ip':
                await message.channel.send(await get_my_global_ip())

            elif cmd == 'help':
                C = ['start', 'stop', 'reload', 'list', 'ip']
                await message.channel.send('\n'.join(['available commands'] + C))

            else:
                M = [cmd + ' not found', "If you use 'help' command, you can see the list of available commands."]
                await message.channel.send('\n'.join(M))

@client.event
async def on_ready():
    asyncio.create_task(main())

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.channel.name != MINECRAFT_CHANNEL:
        return
    if len(message.content.split()) < 2:
        return

    if client.user in message.mentions:
        commands.put(message)

client.run(TOKEN)