# file for implementing the class representing a moderator response
from enum import Enum, auto
import discord
import re
from reactions import EmojiOption, ModeratorAction, ACTION_TO_POST_ACTION_MESSAGE
from collections import defaultdict
from typing import Set
from report import AutomatedReport

class State(Enum):
    RESPONSE_START = auto()
    AWAITING_MESSAGE = auto()
    REPORT_IDENTIFIED = auto()
    ASK_FOR_POST_ACTIONS = auto()
    ASK_FOR_USER_ACTIONS = auto()
    ASK_FOR_GROUP_ACTIONS = auto() 
    ASK_FOR_REASON_FOR_ELEVATING = auto()
    ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS = auto()
    GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS = auto()
    THANK_MODERATOR = auto()
    RESPONSE_FINISHED = auto()
    RESPONSE_CANCELLED = auto()


STATE_TO_MESSAGE_PREFIX = {
    State.ASK_FOR_POST_ACTIONS: "What actions should be taken on the post?",
    State.ASK_FOR_USER_ACTIONS: "What actions should be taken on the user who created the post?",
    State.ASK_FOR_GROUP_ACTIONS: "What actions should be taken on the group in which the post was made?",
    State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS: "Would you like to flag this report for advanced moderators to review?",
    State.ASK_FOR_REASON_FOR_ELEVATING: "Why should this report be forwarded to advanced moderators?",
    State.THANK_MODERATOR: "Thank you for responding to the report! Begin a new response at any time by typing `respond`.",
    State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS: "Thank you for responding to the report! Begin a new response at any time by typing `respond`."  # handle_message will generate the advanced moderator summary
}

# If the state has only one next state to transition into
STATE_TO_SINGLE_NEXT_STATE =  {
    State.REPORT_IDENTIFIED: State.ASK_FOR_POST_ACTIONS,
    State.ASK_FOR_POST_ACTIONS: State.ASK_FOR_USER_ACTIONS,
    State.ASK_FOR_USER_ACTIONS: State.ASK_FOR_GROUP_ACTIONS,
    State.ASK_FOR_GROUP_ACTIONS: State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS,
    # more complex transition for elevating to advanced mods
    State.ASK_FOR_REASON_FOR_ELEVATING: State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS,
}

DEFAULT_REQUEST_EMOJI_RESPONSE_STR = " React to this message with the emoji corresponding to the correct category / categories.\n"


# see ModeratorAction enum in reactions.py for different actions to assign to emoji options
STATE_TO_EMOJI_OPTIONS = {
    State.ASK_FOR_POST_ACTIONS: { 
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Add disclaimer for users and link reliable resources (ex: CDC, WHO)",  action = ModeratorAction.MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES),
        "2️⃣": EmojiOption(emoji = "2️⃣", option_str = "Remove post", action = ModeratorAction.REMOVE_POST)
    }, 
    State.ASK_FOR_USER_ACTIONS: { 
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Notify user of transgression", action = ModeratorAction.NOTIFY_POSTER_OF_TRANSGRESSION),
        "2️⃣": EmojiOption(emoji = "2️⃣", option_str = "Temporarily mute or block", action = ModeratorAction.TEMPORARILY_MUTE_USER),
        "3️⃣": EmojiOption(emoji = "3️⃣", option_str = "Remove user permanently", action = ModeratorAction.PERMANENTLY_REMOVE_USER)
    },
    State.ASK_FOR_GROUP_ACTIONS: { 
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Notify group of high number of high number of COVID disinformation transgressions.", action = ModeratorAction.NOTIFY_GROUP_OF_TRANSGRESSIONS),
        "2️⃣": EmojiOption(emoji = "2️⃣", option_str = "Increment group transgression count", action = ModeratorAction.INCREMENT_GROUP_TRANSGRESSION_COUNTER),
    },
    State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS: {
        "👍": EmojiOption(emoji = "👍", option_str = "Yes", action = ModeratorAction.FLAG_TO_ADVANCED_MODERATORS),
        "👎": EmojiOption(emoji = "👎", option_str = "No")
    },
    State.ASK_FOR_REASON_FOR_ELEVATING: { 
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Severity of the post"),
        "2️⃣": EmojiOption(emoji = "2️⃣", option_str = "High Profile user (wider reach)")
    }
}

YES_ELEVATE_TO_ADVANCED_MODERATORS_ACTION = STATE_TO_EMOJI_OPTIONS[State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS]["👍"]

DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX = "Once you're done selecting, please type `continue`. Type `cancel` to cancel the report at any point."

MESSAGE_THEN_CONTINUE = set([])

NO_CONTINUE_STATES = set([State.THANK_MODERATOR, State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS])

ACTION_TAKEN_BY_AUTOMATED_REPORT_TAG = "[Action already taken by automated reporting!] "

class Response:
    START_KEYWORD = "start"
    REPORT_ID_REGEX = "[0-9]+"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"
    CONTINUE_KEYWORD = "continue"


    def __init__(self, client):
        self.state = State.RESPONSE_START
        self.client = client
        self.report_id = None # this is set in handle_message
        self.report = None  # this is set in handle_messages
        self.reported_message = None # discord's Message object for the reported message, also set in handle_message

        self.elevate_to_advanced_moderators = False  # whether the report is flagged to be evaluated by advanced moderators

        # tracking the options chosen by the user in their flow
        # this will store EmojiOption instances
        self.user_report_state_to_selected_emoji_options = defaultdict(set)

        # trakcing the options chosen by the moderator in this flow
        # this will store EmojiOption instances
        self.moderator_state_to_selected_emoji = defaultdict(set) 

        self.set_of_previous_actions_taken = set()  # this will contain ModeratorActions, set in handle_message


    async def handle_message(self, message):
        '''
        This function makes up the meat of the moderator reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.RESPONSE_CANCELLED
            return ["Report response cancelled."]
        
        if self.state == State.RESPONSE_START:
            reply =  "Thank you for responding to report. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please type the ID number of the report you would like to respond to.\n"
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search(self.REPORT_ID_REGEX, message.content)
            if not m:
                return ["I'm sorry, I couldn't read the report number. Please try again or say `cancel` to cancel."]

            report_id = int(m.group())

            # use the client mapping from report id to report to get discord's Message object of the reported message
            self.report_id = report_id
            self.report = self.client.report_id_to_report[report_id]

            # store any previous actions taken by an automated report
            if isinstance(self.report, AutomatedReport):
                self.set_of_previous_actions_taken = self.report.set_of_actions_taken

            self.reported_message = self.client.report_id_to_report[report_id].message
            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.REPORT_IDENTIFIED
            return [f"Thank you for beginning a response to report number {report_id}!", \
                    "We'll be asking you a few questions to gather your full response to the report. \n" \
                    "Type `continue` to continue the response, and say `cancel` to cancel at any point."]

        # START OF OUR CUSTOM REPORTING STATES
        # Next, we progress through our own states that are outlined in our user reporting flow diagram
        if message.content == self.CONTINUE_KEYWORD:

            # the moderator has said `continue` after responding to the previous state
            reply_list = []

            # check to see if we are in an emoji-actionable state
            if self.state in STATE_TO_EMOJI_OPTIONS:

                # take the actions associated with the options the moderator chose in the previous state
                # get the emoji options selected for the current state
                current_state_emoji_options = self.moderator_state_to_selected_emoji[self.state]
                await self.take_actions(current_state_emoji_options)

                # special case for flagging for advanced moderator review
                if self.state == State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS and YES_ELEVATE_TO_ADVANCED_MODERATORS_ACTION in current_state_emoji_options:
                    self.elevate_to_advanced_moderators = True

                # generate a message to the moderator of a summary of the actions taken (if any)
                if self.state in STATE_TO_EMOJI_OPTIONS and len(current_state_emoji_options):
                    actions = [emoji_option.action for emoji_option in current_state_emoji_options if emoji_option.action]


                    if len(actions):
                        reply = "We have taken the following actions based on your responses: \n"
                        for action in actions:
                            reply += f"·    {ACTION_TO_POST_ACTION_MESSAGE[action]}\n"

                        reply_list.append(reply)


            # TRANSITIONS
            # we now progress to the next state
            self.handle_transitions()

            # MESSAGING
            if self.state in MESSAGE_THEN_CONTINUE:
                reply_list.append(STATE_TO_MESSAGE_PREFIX[self.state])
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

            # start with the message prefix for that state if there is one
            reply = STATE_TO_MESSAGE_PREFIX[self.state] if self.state in STATE_TO_MESSAGE_PREFIX else ""

            # add the message to the moderator channel to alert advanced moderators if needed
            if self.state == State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS:
                reply_list.append(reply)
                reply_list.append(self.generate_summary_for_advanced_moderators())
                self.state = State.RESPONSE_FINISHED
                return reply_list

            # state that prompts the user for multiple options
            if self.state in STATE_TO_EMOJI_OPTIONS:
                reply += DEFAULT_REQUEST_EMOJI_RESPONSE_STR
                for emoji, emoji_option in STATE_TO_EMOJI_OPTIONS[self.state].items():

                    # add a note if the automated response flow has already taken the relevant action
                    action_taken_by_automated_report = emoji_option.action in self.set_of_previous_actions_taken
                    option_prefix = ACTION_TAKEN_BY_AUTOMATED_REPORT_TAG if action_taken_by_automated_report else ""

                    reply += f"{emoji}: {option_prefix}{emoji_option.option_str}\n"

            if self.state not in NO_CONTINUE_STATES:
                reply += f"{DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX}"     

            # mark as finished if we are thanking the user for reporting
            if self.state == State.THANK_MODERATOR:
                self.state = State.RESPONSE_FINISHED

            reply_list.append(reply)

            return reply_list

        return []


    def handle_transitions(self):
        # process simple 1-to-1 transitions
        if self.state in STATE_TO_SINGLE_NEXT_STATE:
            self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]
            return

        # handling advanced transitions
        if self.state == State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS:
            self.state = State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS if self.elevate_to_advanced_moderators else State.THANK_MODERATOR  
            return


    async def take_actions(self, moderator_emojis: Set[ModeratorAction]):
        for emoji in moderator_emojis:
            if emoji.action == ModeratorAction.REMOVE_POST:
                await self.client.remove_reported_post(self.reported_message)
            elif emoji.action == ModeratorAction.MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES:
                await self.client.modify_post_with_disclaimer_and_reliable_resources(self.reported_message)
            elif emoji.action == ModeratorAction.NOTIFY_POSTER_OF_TRANSGRESSION:
                await self.client.notify_poster_of_transgression(self.reported_message)
            elif emoji.action == ModeratorAction.TEMPORARILY_MUTE_USER:
                await self.client.temporarily_mute_user(self.reported_message)
            elif emoji.action == ModeratorAction.PERMANENTLY_REMOVE_USER:
                await self.client.permanently_remove_user(self.reported_message)
            elif emoji.action == ModeratorAction.NOTIFY_GROUP_OF_TRANSGRESSIONS:
                await self.client.notify_group_of_transgressions(self.reported_message)
            elif emoji.action == ModeratorAction.INCREMENT_GROUP_TRANSGRESSION_COUNTER:
                await self.client.increment_group_transgression_counter(self.reported_message)

    
    async def handle_reaction(self, message, emoji, user):

        # check this is a state with valid emoji reaction options
        if self.state in STATE_TO_EMOJI_OPTIONS:

            # only store the emoji option as a response if the emoji is one associated with the sate
            if emoji in STATE_TO_EMOJI_OPTIONS[self.state]:

                emoji_option = STATE_TO_EMOJI_OPTIONS[self.state][emoji]

                self.moderator_state_to_selected_emoji[self.state].add(emoji_option)

        # we don't need to print a message to the user immediately upon reacting
        return []

    # TODO 
    def generate_summary_for_advanced_moderators(self):
        # Generate a message that summarizes the options selected during both the user and baseline moderator reporting flows
        # use the self.report object to access the self.report.state_to_selected_emoji_options or invoke self.report.generate_summary(self.report_id)

        # send this summary to the moderator

        # TODO: include the message metadata string
        reply = [self.report.generate_summary(self.report_id)]
        reply.append("\nBASELINE MODERATOR REPORT SUMMARY:" )
        reply.append("Here are the moderator's answers to the following questions:")
        for state in self.moderator_state_to_selected_emoji:
            text = " AND ".join([f"{emoji_option.emoji}: {emoji_option.option_str}" for emoji_option in self.moderator_state_to_selected_emoji[state]])
            reply.append(f"{STATE_TO_MESSAGE_PREFIX[state]} -> {text}")
            # reply.append(f"{STATE_TO_MESSAGE_PREFIX[state]} -> {self.moderator_state_to_selected_emoji[state].emoji}: {self.moderator_state_to_selected_emoji[state].option_str}")
        return "\n".join(reply)

        # TODO: include the summaries from both the user/automated and moderator report flows

        # return "Placeholder summary for advanced moderators."

    def response_cancelled(self):
        return self.state == State.RESPONSE_CANCELLED 

    def response_finished(self):
        return self.state == State.RESPONSE_FINISHED




    

