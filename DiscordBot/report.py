from enum import Enum, auto
import discord
import re
from reactions import EmojiOption, ModeratorAction, ACTION_TO_POST_ACTION_MESSAGE
from collections import defaultdict


class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_STARTED = auto()
    SCALE_IDENTIFIED = auto()  # ask general category
    ASK_IF_COVID_DISINFO = auto()
    CONFIRMED_COVID_DISINFO = auto()
    NOT_COVID_DISINFO_THANK_USER = auto()
    DISINFO_CATEGORY_IDENTIFIED = auto()
    SEVERITY_IDENTIFIED_MODERATE = auto()
    SEVERITY_IDENTIFIED_HIGH = auto()
    ASK_FOR_FEED_MODIFICATIONS = auto()
    THANK_FOR_REPORTING = auto()
    REPORT_CANCELLED = auto()
    REPORT_FINISHED = auto()

STATE_TO_MESSAGE_PREFIX = {
    State.REPORT_STARTED: "First, we'd like to know who your post affects.",
    State.SCALE_IDENTIFIED: "What category of abuse would this fall under?",
    State.ASK_IF_COVID_DISINFO: "Is this disinformation related to COVID-19?",
    State.NOT_COVID_DISINFO_THANK_USER: "Thank you for your report. However, we are currently focusing our efforts on disinformation related to COVID-19 and will cancel your report. Start a new report by typing `report`.",
    State.CONFIRMED_COVID_DISINFO: "What category of COVID-19 disinformation would this fall under?",
    State.DISINFO_CATEGORY_IDENTIFIED: "What is the severity?",
    State.SEVERITY_IDENTIFIED_MODERATE: "Thank you! We’ve labelled this report as moderate severity. We’ll review your report and look into next steps. This may involve removing or adding disclaimers to the post and temporarily muting or banning the user from the group.",
    State.SEVERITY_IDENTIFIED_HIGH: "Thank you! We’ve labelled this report as high severity. We’ll review your report and look into next steps. This may involve removing or adding disclaimers to the post and temporarily muting or banning the user from the group.",
    State.ASK_FOR_FEED_MODIFICATIONS: "How would you like to update your feed going forward?",
    State.THANK_FOR_REPORTING: "Thank you for your report! We appreciate your help in keeping our platform safe for our community."
} 

# If the state has only one next state to transition into
STATE_TO_SINGLE_NEXT_STATE =  {
    State.MESSAGE_IDENTIFIED: State.REPORT_STARTED,
    State.REPORT_STARTED: State.SCALE_IDENTIFIED,
    # scale identified transition is more advanced
    # ask if covid disinfo transition is more advanced
    State.CONFIRMED_COVID_DISINFO: State.DISINFO_CATEGORY_IDENTIFIED,
    # from disinfo category identified is more advanced
    State.SEVERITY_IDENTIFIED_MODERATE: State.ASK_FOR_FEED_MODIFICATIONS,
    State.SEVERITY_IDENTIFIED_HIGH: State.ASK_FOR_FEED_MODIFICATIONS,
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
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Disinformation"),
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
    State.ASK_IF_COVID_DISINFO: {
        "👍": EmojiOption(emoji = "👍", option_str = "Yes"),
        "👎": EmojiOption(emoji = "👎", option_str = "No")
    },
    State.CONFIRMED_COVID_DISINFO: {
        # Added descriptions based on youtube's distinctions https://support.google.com/youtube/answer/9891785?hl=en&ref_topic=10833358&sjid=12927046454796501180-NA
        "🔴": EmojiOption(emoji = "🔴", option_str = "Medical Disinformation: Politicizing Medical Response. Content that allows COVID-19 information or news to become political in nature (e.g., using CDC guidelines to criticize a  agendas"),
        "🟠": EmojiOption(emoji = "🟠", option_str = "Medical Disinformation: Treatment. Content tat encourages the use of home remedies, prayer, or rituals in place of consulting a doctor (e.g., recommends use of Ivermectin or Hydroxychloroquine for prevention of COVID-19)"), 
        "🟡": EmojiOption(emoji = "🟡", option_str = "Medical Disinformation: Prevention. Content that promotes prevention information that contradicts health authorities (e.g., claiming that COVID-19 vaccines do not reduce risk of serious injury or death"),
        "🟢": EmojiOption(emoji = "🟢", option_str = "Medical Disinformation: Diagnostic. Content that promotes diagnostic information that contradicts health authorities (e.g., Claims that COVID-19 tests are ineffective/dangerous)"),
        "🔵": EmojiOption(emoji = "🔵", option_str = "Medical Disinformation: Transmission. Content that provides inaccurate information about transmission (e.g., that COVID-19 is less transmissible than common cold"),
        "🟣": EmojiOption(emoji = "🟣", option_str = "Medical Disinformation: Denies Existence. Content that denies the existence of COVID-19 (e.g., claiming symptoms of COVID-19 are never severe)"),
        "⚪": EmojiOption(emoji = "⚪", option_str = "Attacks against health officials, organizations, or the government."),
        "⚫": EmojiOption(emoji = "⚫", option_str = "Conspiracy Theories (e.g., the COVID-19 vaccine has tracking chips"),
        "🟤": EmojiOption(emoji = "🟤", option_str = "Other")
        # SEE https://emojicombos.com/color for more circle emojis USE THIS!!!!
    },
    State.DISINFO_CATEGORY_IDENTIFIED: { #this is severity
        "🟩": EmojiOption(emoji = "🟩", option_str = "Purposefully Confusing / Untrue Content"),
        "🟨": EmojiOption(emoji = "🟨", option_str = "Misinterpreting/Distorting/Disobeying Official Government Health Orders/Advisories"),
        "🟧": EmojiOption(emoji = "🟧", option_str = "Public Health Risk"),
        "🟥": EmojiOption(emoji = "🟥", option_str = "Targeted Danger Towards Specific Individual/Group")
    },
    State.ASK_FOR_FEED_MODIFICATIONS: {
        "❌": EmojiOption(emoji = "❌", option_str = "Block User", action = ModeratorAction.BLOCK_POSTER_TO_REPORTER),
        "💬": EmojiOption(emoji = "💬", option_str = "Temporarily Mute Posts from the User", action = ModeratorAction.MUTE_POSTER_TO_REPORTER)
    }  
}


HIGH_SEVERITY_EMOJI_OPTIONS = set([
    STATE_TO_EMOJI_OPTIONS[State.DISINFO_CATEGORY_IDENTIFIED]["🟧"],
    STATE_TO_EMOJI_OPTIONS[State.DISINFO_CATEGORY_IDENTIFIED]["🟥"]
])

DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX = "Once you're done selecting, please type `continue`. Type `cancel` to cancel the report at any point."

MESSAGE_THEN_CONTINUE = set([State.SEVERITY_IDENTIFIED_MODERATE, State.SEVERITY_IDENTIFIED_HIGH])

NO_CONTINUE_STATES = set([State.THANK_FOR_REPORTING, State.NOT_COVID_DISINFO_THANK_USER])

CANCEL_REPORT_STATES = set([State.NOT_COVID_DISINFO_THANK_USER])

DISINFO_CATEGORY_EMOJI_OPTION = STATE_TO_EMOJI_OPTIONS[State.SCALE_IDENTIFIED]["1️⃣"]

YES_COVID_DISINFO_EMOJI_OPTION = STATE_TO_EMOJI_OPTIONS[State.ASK_IF_COVID_DISINFO]["👍"]

MODERATE_PRIORITY_TAG = "[⚠️ MODERATE PRIORITY ⚠️]"

HIGH_PRIORITY_TAG = "[🚨 HIGH PRIORITY 🚨]"

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

        self.high_severity = False  # moderate otherwise

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
            self.message = message
            return ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
                    "Thank you for creating a report! We'll be asking you a few questions to gather extra details about the report. \n " \
                    "Type `continue` to continue the report, and say `cancel` to cancel at any point."]
        


        # START OF OUR CUSTOM REPORTING STATES
        # Next, we progress through our own states that are outlined in our user reporting flow diagram
        if message.content == self.CONTINUE_KEYWORD:

            # the user has said `continue` after responding to the previous state
            reply_list = []

            # check to see if we are in an emoji-actionable state
            if self.state in STATE_TO_EMOJI_OPTIONS:

                # take the actions associated with the options the moderator chose in the previous state
                # get the emoji options selected for the current state
                current_state_emoji_options = self.state_to_selected_emoji_options[self.state]
                reply = self.update_actions(current_state_emoji_options)

                # check for non-trivial reply
                if reply:
                    reply_list.append(reply)

            # TRANSITIONS
            self.make_state_transitions()

            # MESSAGING
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

            if self.state in CANCEL_REPORT_STATES:
                self.state = State.REPORT_CANCELLED

            reply_list.append(reply)

            return reply_list

        return []

    def make_state_transitions(self):
        # handling advanced transitions
        # check to see if the general category is selected is disinformation, otherwise thank the user and close the report
        if self.state == State.SCALE_IDENTIFIED:
            self.state = State.ASK_IF_COVID_DISINFO if DISINFO_CATEGORY_EMOJI_OPTION in self.state_to_selected_emoji_options[self.state] else State.NOT_COVID_DISINFO_THANK_USER
            return
        
        # only continue the full reporting flow if the disinfo is COVID-19 related, otherwise thank the user and close the report
        elif self.state == State.ASK_IF_COVID_DISINFO:
            self.state = State.CONFIRMED_COVID_DISINFO if YES_COVID_DISINFO_EMOJI_OPTION in self.state_to_selected_emoji_options[self.state] else State.NOT_COVID_DISINFO_THANK_USER
            return


        elif self.state == State.DISINFO_CATEGORY_IDENTIFIED:

            for emoji_option in self.state_to_selected_emoji_options[self.state]:
                if emoji_option in HIGH_SEVERITY_EMOJI_OPTIONS:
                    self.high_severity = True
                    self.state = State.SEVERITY_IDENTIFIED_HIGH
                    return

            # if we haven't transitioned to the high-severity response already, transition to the moderate-severity response
            self.state = State.SEVERITY_IDENTIFIED_MODERATE
            return


        # handling 1-to-1 transitions
        if self.state in STATE_TO_SINGLE_NEXT_STATE:
            self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]


    def update_actions(self, current_state_emoji_options):
        # generate a message to the user of actions that will be taken
        if self.state in STATE_TO_EMOJI_OPTIONS and len(current_state_emoji_options):
            actions = [emoji_option.action for emoji_option in current_state_emoji_options if emoji_option.action]

            if len(actions):
                reply = "We have taken the following actions based on your responses: \n"
                for action in actions:
                    reply += f"·    {ACTION_TO_POST_ACTION_MESSAGE[action]}\n" # TODO: What is this???

                return reply
        
        return ""

    async def handle_reaction(self, message, emoji, user):

        # check this is a state with valid emoji reaction options
        if self.state in STATE_TO_EMOJI_OPTIONS:

            # only store the emoji option as a response if the emoji is one associated with the sate
            if emoji in STATE_TO_EMOJI_OPTIONS[self.state]:

                emoji_option = STATE_TO_EMOJI_OPTIONS[self.state][emoji]

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

        # TODO: start with HIGH_PRIORITY_TAG if self.high_severity is true otherwise MODERATE_PRIORITY_TAG
        reply = []
        if self.high_severity:
            reply.append(HIGH_PRIORITY_TAG)
        else:
            reply.append(MODERATE_PRIORITY_TAG)

        reply.append(f"Report ID: {report_id}")
        reply.append(self.client.generate_message_metadata_summary(self.message))
        reply.append("\nUSER REPORT SUMMARY:\n" )
        reply.append("Here are the reporter's answers to the following questions:")
        for state in self.state_to_selected_emoji_options:
            text = " AND ".join([f"{emoji_option.emoji}: {emoji_option.option_str}" for emoji_option in self.state_to_selected_emoji_options[state]])
            reply.append(f"{STATE_TO_MESSAGE_PREFIX[state]} -> {text}")
        return "\n".join(reply)
        # TODO: include the message metadata string

        # return f"Placeholder Report Summary for Report {report_id}!"

    

class AutomatedReport:
    def __init__(self, client, message, disinfo_prob: float, report_id: int, very_high_disinfo_prob: bool):
        self.client = client
        self.message = message
        self.disinfo_prob = disinfo_prob
        self.report_id = report_id
        self.very_high_disinfo_prob = very_high_disinfo_prob
        self.alert_alert_moderator_to_high_report_user = False
        self.high_severity = self.very_high_disinfo_prob

        # TODO: use this set of actions to only display to the moderator not-already-automatically-taken options in thier reporting flow
        # aka when we ask the moderator to select actions, only utilize the EmojiOptions whose actions aren't already stored here
        self.set_of_actions_taken = set()  # this will contain ModeratorActions

    async def act_on_very_high_disinfo_message(self):
        print(f"Removing the message {self.message.content} from the general channel.")
        await self.client.remove_reported_post(self.message)
        self.set_of_actions_taken.add(ModeratorAction.REMOVE_POST)

        print(f"Notifying the poster of the message, {self.message.author.name} to their transgression.")
        await self.client.notify_poster_of_transgression(self.message)
        self.set_of_actions_taken.add(ModeratorAction.NOTIFY_POSTER_OF_TRANSGRESSION)

        # does the poster have a high count of existing reported posts?
        if self.client.user_id_to_number_of_reported_posts[self.message.author.id] > self.client.USER_HIGH_REPORT_AMOUNT_THRESHOLD:

            # this flag is utilized in generate_summary
            self.alert_moderator_to_high_report_user = True

            print(f"Temporarily muting the poster {self.message.author.name}.")
            await self.client.temporarily_mute_user(self.message)
            self.set_of_actions_taken.add(ModeratorAction.TEMPORARILY_MUTE_USER)

    # TODO
    def generate_summary(self):
        # based on the contents of self.state_to_selected_emoji_options (the options selected at each state by the user)
        # format a string that will be sent to the moderator channel to describe the report

        # TODO: start with HIGH_PRIORITY_TAG if very_high_disinfo_prob else MODERATE_PRIORITY_TAG

        # return f"Placeholder Automated Report Summary for Report {self.report_id}! This automated report has disinformation probability of {self.disinfo_prob}."
        reply = []
        if self.high_severity:
            reply.append(HIGH_PRIORITY_TAG)
        else:
            reply.append(MODERATE_PRIORITY_TAG)
        reply.append(self.client.generate_message_metadata_summary(self.message))
        reply.append("\AUTOMATED REPORT SUMMARY:\n" )
        reply.append("Here are the set of actions taken by the automated report:")
        for action in self.set_of_actions_taken:
            # text = " AND ".join([f"{emoji_option.emoji}: {emoji_option.option_str}" for emoji_option in self.set_of_actions_taken[state]])
            reply.append(f"{ACTION_TO_POST_ACTION_MESSAGE[action]}")
        

        # TODO: include the message metadata string

        # TODO: if alert_moderator_to_high_report_user is true, then also add another string to the msg like "user {name} is also known to have a high number of reported posts, with {self.client.user_id_to_number_of_removed_posts[message.author.id]} of their posts being reported"
        if self.alert_alert_moderator_to_high_report_user:
            reply.append(f"User {self.message.author.name} is also known to have a high number of reported posts, with {self.client.user_id_to_number_of_removed_posts[self.message.author.id]} of their posts being reported.")
        # TODO: if very_high_disinfo prob is true, note that we took the actions indicated in our moderator reporting flow
        if self.very_high_disinfo_prob:
            reply.append(f"Since this post has a high disinforamtion probability >{self.client.VERY_HIGH_DISINFO_PROB_THRESHOLD}, we took the actions indicated in our moderator reporting flow.")
        return "\n".join(reply)




