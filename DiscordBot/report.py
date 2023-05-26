from enum import Enum, auto
import discord
import re
from reactions import EmojiOption
from collections import defaultdict


class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_STARTED = auto()
    SCALE_IDENTIFIED = auto()
    GENERAL_CATEGORY_IDENTIFIED = auto()
    DISINFO_CATEGORY_IDENTIFIED = auto()
    SEVERITY_IDENTIFIED_CONFUSING = auto()
    SEVERITY_IDENTIFIED_OTHER = auto()
    ASK_FOR_FEED_MODIFICATIONS = auto()
    THANK_FOR_REPORTING = auto()
    REPORT_CANCELLED = auto()
    REPORT_FINISHED = auto()

STATE_TO_MESSAGE_PREFIX = {
    State.REPORT_STARTED: "First, we'd like to know who your post affects.",
    State.SCALE_IDENTIFIED: "What category of abuse would this fall under?",
    State.GENERAL_CATEGORY_IDENTIFIED: "What category of disinformation would this fall under?",  # TODO: see comment on reporting flow... when do we narrow down to covid disinfo?
    State.DISINFO_CATEGORY_IDENTIFIED: "What is the severity?",
    State.SEVERITY_IDENTIFIED_CONFUSING: "Thank you! We’ll review your report and look into removing the person’s post, as well as temporarily muting their account.",
    State.SEVERITY_IDENTIFIED_OTHER: "Thank you! We’ll review your report and look into banning this person’s account.",
    State.ASK_FOR_FEED_MODIFICATIONS: "How would you like to update your feed going forward?",
    State.THANK_FOR_REPORTING: "Thank you for your report! We appreciate your help in keeping our platform safe for our community."
} 

# If the state has only one next state to transition into
STATE_TO_SINGLE_NEXT_STATE =  {
    State.MESSAGE_IDENTIFIED: State.REPORT_STARTED,
    State.REPORT_STARTED: State.SCALE_IDENTIFIED,
    State.SCALE_IDENTIFIED: State.GENERAL_CATEGORY_IDENTIFIED,
    State.GENERAL_CATEGORY_IDENTIFIED: State.DISINFO_CATEGORY_IDENTIFIED,
    State.DISINFO_CATEGORY_IDENTIFIED: State.SEVERITY_IDENTIFIED_CONFUSING, # TODO: this is a placeholder, but the DISINFO_CATEGORY_IDENTIFIED state has multiple next states
    State.SEVERITY_IDENTIFIED_CONFUSING: State.ASK_FOR_FEED_MODIFICATIONS,
    State.SEVERITY_IDENTIFIED_OTHER: State.ASK_FOR_FEED_MODIFICATIONS,
    State.ASK_FOR_FEED_MODIFICATIONS: State.THANK_FOR_REPORTING
}

DEFAULT_REQUEST_EMOJI_RESPONSE_STR = " React to this message with the emoji corresponding to the correct category / categories.\n"


STATE_TO_EMOJI_OPTIONS = {
    State.REPORT_STARTED: {
        "👤": EmojiOption(emoji = "👤", option_str = "Individual"),
        "👥": EmojiOption(emoji = "👥", option_str = "Local Community"),
        "🌐": EmojiOption(emoji = "🌐", option_str = "Nationwide")
    },
    State.SCALE_IDENTIFIED: { #past tense -- we've already done the scale -- copy the general -- change option fro there
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "False Information"),
        "2️⃣": EmojiOption(emoji = "2️⃣", option_str = "Spam"),
        "3️⃣": EmojiOption(emoji = "3️⃣", option_str = "Nudity"),
        "4️⃣": EmojiOption(emoji = "4️⃣", option_str = "Hate Speech"),
        "5️⃣": EmojiOption(emoji = "5️⃣", option_str = "Bullying and/or Harassment"),
        "6️⃣": EmojiOption(emoji = "6️⃣", option_str = "Scam or Fraud"),
        "7️⃣": EmojiOption(emoji = "7️⃣", option_str = "Threats of Violence"),
        "8️⃣": EmojiOption(emoji = "8️⃣", option_str = "IP Violation"),
        "9️⃣": EmojiOption(emoji = "9️⃣", option_str = "Self-Harm or Suicide"),
        "🔟": EmojiOption(emoji = "🔟", option_str = "Something Else")
    },
    State.GENERAL_CATEGORY_IDENTIFIED: {
        #Should we change these to MISinformation?
        # Added descriptions based on youtube's distinctions https://support.google.com/youtube/answer/9891785?hl=en&ref_topic=10833358&sjid=12927046454796501180-NA
        "🔴": EmojiOption(emoji = "🔴", option_str = "Medical Disinformation: Politicizing Medical Response. Content that allows COVID-19 information or news to become political in nature (e.g., using CDC guidelines to criticize a  agendas"),
        "🟠": EmojiOption(emoji = "🟠", option_str = "Medical Disinformation: Treatment. Content tat encourages the use of home remedies, prayer, or rituals in place of consulting a doctor (e.g., recommends use of Ivermectin or Hydroxychloroquine for prevention of COVID-19)"), 
        "🟡": EmojiOption(emoji = "🟡", option_str = "Medical Disinformation: Prevention. Content that promotes prevention information that contradicts health authorities (e.g., claiming that COVID-19 vaccines do not reduce risk of serious injury or death"),
        "🟢": EmojiOption(emoji = "🟢", option_str = "Medical Disinformation: Diagnostic. Content that promotes diagnostic information that contradicts health authorities (e.g., Claims that COVID-19 tests are ineffective/dangerous)"),
        "🔵": EmojiOption(emoji = "🔵", option_str = "Medical Disinformation: Transmission. Content that provides inaccurate information about transmission (e.g., that COVID-19 is less transmissible than common cold"),
        "🟣": EmojiOption(emoji = "🟣", option_str = "Medical Disinformation: Denies Existence. Content that denies the existence of COVID-19 (e.g., claiming symptoms of COVID-19 are never severe)"),
        "⚪": EmojiOption(emoji = "⚪", option_str = "Attacks against health officials, organizations, or the government."),
        "⚫": EmojiOption(emoji = "⚫", option_str = "Conspiracy Theories (e.g., the COVID-19 vaccine has tracking chips"), #TODO definition here
        "🟤": EmojiOption(emoji = "🟤", option_str = "Other")
        # SEE https://emojicombos.com/color for more circle emojis USE THIS!!!!
    },
    State.DISINFO_CATEGORY_IDENTIFIED: { #this is severity
        "🟥": EmojiOption(emoji = "🟥", option_str = "Purposefully Confusing / Untrue Content"),
        "🟧": EmojiOption(emoji = "🟧", option_str = "Misinterpreting/Distorting/Disobeying Official Government Health Orders/Advisories"),
        "🟨": EmojiOption(emoji = "🟨", option_str = "Public Health Risk"),
        "🟩": EmojiOption(emoji = "🟩", option_str = "Targeted Danger Towards Specific Individual/Group")
    },
    State.ASK_FOR_FEED_MODIFICATIONS: {
        "🧹": EmojiOption(emoji = "🧹", option_str = "Remove Post From Feed"),
        "❌": EmojiOption(emoji = "❌", option_str = "Block User"),
        "💬": EmojiOption(emoji = "💬", option_str = "Temporarily Mute User")
    }  
}

DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX = "Once you're done selecting, please type `continue`. Type `cancel` to cancel the report at any point."

MESSAGE_THEN_CONTINUE = set([State.SEVERITY_IDENTIFIED_CONFUSING, State.SEVERITY_IDENTIFIED_OTHER])

NO_CONTINUE_STATES = set([State.THANK_FOR_REPORTING])

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"
    CONTINUE_KEYWORD = "continue"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None

        # tracking the options chosen (we will use these for the moderator reporting flow)
        # this will store EmojiOption instances
        self.state_to_selected_emoji_options = defaultdict(set)  

    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_CANCELLED
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.MESSAGE_IDENTIFIED
            return ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
                    "Thank you for creating a report! We'll be asking you a few questions to gather extra details about the report. \n " \
                    "Type `continue` to continue the report, and say `cancel` to cancel at any point."]
        


        # START OF OUR CUSTOM REPORTING STATES
        # Next, we progress through our own states that are outlined in our user reporting flow diagram
        if message.content == self.CONTINUE_KEYWORD:

            # the user has said `continue` after responding to the previous state
            # we now progress to the next state
            if self.state in STATE_TO_SINGLE_NEXT_STATE:
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

            # TODO: add logic for non 1-to-1 transitions

            reply_list = []

            if self.state in MESSAGE_THEN_CONTINUE:
                reply_list.append(STATE_TO_MESSAGE_PREFIX[self.state])
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

            # start with the message prefix for that state if there is one
            reply = STATE_TO_MESSAGE_PREFIX[self.state] if self.state in STATE_TO_MESSAGE_PREFIX else ""


            # state that prompts the user for multiple options
            if self.state in STATE_TO_EMOJI_OPTIONS:
                reply += DEFAULT_REQUEST_EMOJI_RESPONSE_STR
                for emoji, emoji_option in STATE_TO_EMOJI_OPTIONS[self.state].items():
                    reply += f"{emoji}: {emoji_option.option_str}\n"


            if self.state not in NO_CONTINUE_STATES:
                reply += f"{DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX}"     

            # mark as finished if we are thanking the user for reporting
            if self.state == State.THANK_FOR_REPORTING:
                self.state = State.REPORT_FINISHED

            reply_list.append(reply)

            return reply_list

        return []


    async def handle_reaction(self, message, emoji, user):

        # check this is a state with valid emoji reaction options
        if self.state in STATE_TO_EMOJI_OPTIONS:

            # only store the emoji option as a response if the emoji is one associated with the sate
            if emoji in STATE_TO_EMOJI_OPTIONS[self.state]:

                emoji_option = STATE_TO_EMOJI_OPTIONS[self.state][emoji]

                print(f"The user reacted with option {emoji} during state {self.state}")
                self.state_to_selected_emoji_options[self.state].add(emoji_option)

        # we don't need to print a message to the user immediately upon reacting
        return []

    def report_cancelled(self):
        return self.state == State.REPORT_CANCELLED 

    def report_finished(self):
        return self.state == State.REPORT_FINISHED

    # TODO
    def generate_summary(self, report_id):  # there may be additional parameters to add in the metadata (user id, etc.) to the report summary
        # based on the contents of self.state_to_selected_emoji_options (the options selected at each state by the user)
        # format a string that will be sent to the moderator channel to describe the report

        return f"Placeholder Report Summary for Report {report_id}!"

    

class AutomatedReport:
    def __init__(self, client, message, disinfo_prob: float, automated_report_id: int, very_high_disinfo_prob: bool):
        self.client = client
        self.message = message
        self.disinfo_prob = disinfo_prob
        self.automated_report_id = automated_report_id
        self.very_high_disinfo_prob = very_high_disinfo_prob
        self.alert_alert_moderator_to_high_report_user = False

        # TODO: use this set of actions to only display to the moderator not-already-automatically-taken options in thier reporting flow
        # aka when we ask the moderator to select actions, only utilize the EmojiOptions whose actions aren't already stored here
        self.set_of_actions_taken = set()  # this will contain

    async def act_on_very_high_disinfo_message(self):
        # TODO: fill in the function calls here to the modbot action functions once debugged / moved by Shai

        print(f"Removing the message {self.message.content} from the general channel.")
        #self.client.remove_message(self.message)

        print(f"Notifying the poster of the message, {self.message.author.name} to their transgression.")
        #self.client.notify_poster_of_transgression(self.message)

        # does the poster have a high count of existing reported posts?
        if self.client.user_id_to_number_of_removed_posts[self.message.author.id] > self.client.USER_HIGH_REPORT_AMOUNT_THRESHOLD:

            # this flag is utilized in generate_summary
            self.alert_moderator_to_high_report_user = True

            print(f"Temporarily muting the poster {self.message.author.name}.")
            #self.client.temporarily_mute_user(self.message.author.id)

    # TODO
    def generate_summary(self):  # there may be additional parameters to add in the metadata (user id, etc.) to the report summary
        # based on the contents of self.state_to_selected_emoji_options (the options selected at each state by the user)
        # format a string that will be sent to the moderator channel to describe the report

        return f"Placeholder Automated Report Summary for Report {self.automated_report_id}! This automated report has disinformation probability of {self.disinfo_prob}."

        # TODO: if alert_moderator_to_high_report_user is true, then also add another string to the msg like "user {name} is also known to have a high number of reported posts, with {self.client.user_id_to_number_of_removed_posts[message.author.id]} of their posts being reported"


        # TODO: if very_high_disinfo prob is true, note that we took the actions indicated in our moderator reporting flow




