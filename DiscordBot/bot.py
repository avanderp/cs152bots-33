# bot.py
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import Report
from response import Response
import pdb
from collections import defaultdict


# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']



PERSONAL_GROUP_NUMBER_STR = "33"


class ModBot(discord.Client):
    

    def __init__(self): 
        intents = discord.Intents.default()
        intents.messages = True
        intents.reactions = True
        intents.dm_reactions = True
        intents.guild_reactions = True
        super().__init__(command_prefix='.', intents=intents, max_messages = 1000)
        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.moderator_responses = {} # Map from moderator ID to the state of their moderator report response
        self.report_id_to_report = {} # Map from report IDs to the Report class instance
        self.next_report_id = 0
        self.next_moderator_response_id = 0
        self.user_id_to_number_of_removed_posts = defaultdict(int) # Map from user IDs to the number of the user's report that the ModBot has removed (default 0)

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel

                    if self.group_num == PERSONAL_GROUP_NUMBER_STR:
                        self.personal_mod_channel = channel   

    async def on_raw_reaction_add(self, payload):
        print(f"We've entered on_raw_reaction_add.")  

        # extract the contents of the reaction and metadata; see https://stackoverflow.com/questions/59854340/how-do-i-use-on-raw-reaction-add-in-discord-py 
        print(f"Extracting the contents of the reaction payload.")
        channel = self.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = self.get_user(payload.user_id)
        if not user:
            user = await self.fetch_user(payload.user_id)

        emoji = str(payload.emoji)

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_reaction(message, emoji, user)
        else:
            await self.handle_dm_reaction(message, emoji, user)  


    async def handle_channel_reaction(self, message, emoji, user):
        moderator_id = user.id

        # TODO: first check that the reaction is in the group-33-mod
        if message.channel.name != f'group-{self.group_num}-mod':
            return

        # Let the moderator Response class handle this message; forward all the reactions to the responses
        responses = await self.moderator_responses[moderator_id].handle_reaction(message, emoji, user)
        for r in responses:
            await message.channel.send(r)


    async def handle_dm_reaction(self, message, emoji, user):
        print(f"We've entered handle_dm_reaction.")

        # Get the id of the person the Bot sent the react-request message to (the user who reported)
        report_author_id = user.id

        # If we don't currently have an active report for this user
        if report_author_id not in self.reports:
            # reply =  "You do not have any currently active reports. Please start a new report by typing `report`.\n"
            # await message.channel.send(reply) 
            return

        # Let the report class handle this message; forward all the reactions to the report
        responses = await self.reports[report_author_id].handle_reaction(message, emoji, user)
        for r in responses:
            await message.channel.send(r)


    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is cancelled, remove it from our map
        if self.reports[author_id].report_cancelled():
            self.reports.pop(author_id)
        
        # If the report is finished, initiate the moderator reporting flow
        if self.reports[author_id].report_finished():
            # associate this report with a report id
            self.report_id_to_report[self.next_report_id] = self.reports[author_id]

            # Send the report summary to the moderator channel
            report_summary = self.reports[author_id].generate_summary(report_id = self.next_report_id)

            # move to the next report id
            self.next_report_id += 1

            await self.personal_mod_channel.send(report_summary)

            

    async def handle_channel_message(self, message):  
        # Only handle messages sent in the "group-#" channel
        if message.channel.name == f'group-{self.group_num}':
            # pass along to the automated flagging logics

            # TODO: check if the normal channel message has a AUTO_FLAG keyword
            # if so, create a "automatically flagged report" and send to moderator channel
            return

        if str(message.channel.name) == f"group-{self.group_num}-mod":
            await self.handle_moderator_channel_message(message)

        # Forward the message to the mod channel
        # mod_channel = self.mod_channels[message.guild.id]
        # await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        # scores = self.eval_text(message.content)
        # await mod_channel.send(self.code_format(scores))

    
    async def handle_moderator_channel_message(self, message):
        print("In handle_moderator_channel_message")
        # Handle a help message
        if message.content == Response.HELP_KEYWORD:
            reply =  "Use the `start` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            await message.channel.send(reply)
            return

        moderator_id = message.author.id
        responses = []

        # Only respond to non-start messages if the moderator already has an existing response flow
        if moderator_id not in self.moderator_responses and not message.content.startswith(Response.START_KEYWORD):
            return

        
        # If we don't currently have an active report response for this moderator, add one
        if moderator_id not in self.moderator_responses:
            print("Creating a new report!")
            self.moderator_responses[moderator_id] = Response(self)  # our bot is the client

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.moderator_responses[moderator_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is cancelled, remove it from our map
        if self.moderator_responses[moderator_id].report_cancelled():
            self.moderator_responses.pop(moderator_id)
        
        # NOTE: we may not need this next portion
        # If the report is finished, initiate the moderator reporting flow
        if self.moderator_responses[moderator_id].report_finished():
            pass


    def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel, 
        insert your code here! This will primarily be used in Milestone 3. 
        '''
        return message

    
    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been 
        evaluated, insert your code here for formatting the string to be 
        shown in the mod channel. 
        '''
        return "Evaluated: '" + text+ "'"


client = ModBot()
client.run(discord_token)