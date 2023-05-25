# file for implementing the class representing a moderator response

from enum import Enum, auto
import discord
import re
from reactions import EmojiOption
from collections import defaultdict


class State(Enum):
    RESPONSE_START = auto()
    AWAITING_MESSAGE = auto()
    REPORT_IDENTIFIED = auto()
    ASK_FOR_POST_ACTIONS = auto()
    ASK_FOR_USER_ACTIONS = auto()
    ASK_FOR_GROUP_ACTIONS = auto() 
    ASK_FOR_REASON_FOR_ELEVATING = auto()
    GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS = auto()
    THANK_MODERATOR = auto()
    RESPONSE_FINISHED = auto()
    RESPONSE_CANCELLED = auto()


STATE_TO_MESSAGE_PREFIX = {
    State.ASK_FOR_POST_ACTIONS: "What actions should be taken on the post?",
    State.ASK_FOR_USER_ACTIONS: "What actions should be taken on the user who created the post?",
    State.ASK_FOR_GROUP_ACTIONS: "What actions should be taken on the group in which the post was made?",
    State.ASK_FOR_REASON_FOR_ELEVATING: "Why should this report be forwarded to advanced moderators?",
    State.THANK_MODERATOR: "Thank you for responding to the report! Begin a new response at any time by typing `respond`"
    State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS: "[ADVANCED MODERATOR REPORT NOTIFICATION]"  # TODO: handle_message will handle generating the report summary for the advanced moderators to act on
}

# If the state has only one next state to transition into
STATE_TO_SINGLE_NEXT_STATE =  {
    State.REPORT_IDENTIFIED: State:ASK_FOR_POST_ACTIONS,
    State.ASK_FOR_POST_ACTIONS: State:ASK_FOR_USER_ACTIONS,
    State.ASK_FOR_USER_ACTIONS: State.ASK_FOR_GROUP_ACTIONS,
    State.ASK_FOR_REASON_FOR_ELEVATING: State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS,
}

DEFAULT_REQUEST_EMOJI_RESPONSE_STR = " React to this message with the emoji corresponding to the correct category / categories.\n"




STATE_TO_EMOJI_OPTIONS = {
    State.ASK_FOR_POST_ACTIONS: {
        # TODO: fill in the "action" component to indicate we'll want to call the Response class's remove_reported_post function
        "❌": EmojiOption(emoji = "❌", option_str = "Remove post", post_action_message = "The reported post has been removed."),

    },
    State.ASK_FOR_POST_ACTIONS: {
        "⚠️": EmojiOption(emoji = "⚠️", option_str = "Add disclaimer for users and link reliable resources (ex: CDC, WHO)", post_action_message = "A disclaimer has been added to the post alongside links to reliable sources on COVID-19."),

    }, 
    State.ASK_FOR_GROUP_ACTIONS: {
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Notify user of transgression", post_action_message = "The user who created the post has been notified of the transgression."),

    }
    State.ASK_FOR_REASON_FOR_ELEVATING: {
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Severity of the post"),

    }
}

DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX = "Once you're done selecting, please type `continue`. Type `cancel` to cancel the report at any point."

MESSAGE_THEN_CONTINUE = set([State.SEVERITY_IDENTIFIED_CONFUSING, State.SEVERITY_IDENTIFIED_OTHER])

NO_CONTINUE_STATES = set([State.THANK_MODERATOR])

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


    async def handle_message(self, message):
        '''
        This function makes up the meat of the moderator reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.RESPONSE_CANCELLED
            return ["Report response cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for responding to report. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please type the ID number of the report you would like to respond to.\n"
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search(REPORT_ID_REGEX, message.content)
            if not m:
                return ["I'm sorry, I couldn't read the report number. Please try again or say `cancel` to cancel."]

            report_id = m.group()

            # use the client mapping from report id to report to get discord's Message object of the reported message
            self.report_id = report_id

            self.report = self.client.report_id_to_report[report_id]
            self.reported_message = self.client.report_id_to_report[report_id].message

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.REPORT_IDENTIFIED
            return [f"Thank you for beginning a response to report number {report_id}!", \
                    "We'll be asking you a few questions to gather your full response to the report. \n" \
                    "Type `continue` to continue the response, and say `cancel` to cancel at any point."]
        
        

        # NOTE: FROM HERE ON IN THIS FUNCTION HAS NOT YET BEEN EDITED FOR THE MODERATOR FLOW


        # START OF OUR CUSTOM REPORTING STATES
        # Next, we progress through our own states that are outlined in our user reporting flow diagram
        if message.content == self.CONTINUE_KEYWORD:

            # the moderator has said `continue` after responding to the previous state
            # TODO: take the actions associated with the options the moderator chose in the previous state

            reply_list = []

            # TODO: generate a message to the moderator of a summary of the actions taken

            # we now progress to the next state
            if self.state in STATE_TO_SINGLE_NEXT_STATE:
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

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
            if self.state == State.THANK_MODERATOR:
                self.state = State.RESPONSE_FINISHED

            reply_list.append(reply)

            return reply_list

        return []


    # TODO
    async def remove_reported_post(self):
        # use the discord py Message object stored in self.reported_message to get the info necessary to remove the reported message
        raise NotImplementedError()

    # TODO
    async def modify_post_with_disclaimer_and_reliable_resources(self):
        raise NotImplementedError()

    # TODO
    async def notify_poster_of_transgression(self):
        # notify user of transgression
        # state which post in which channel was the reason
        raise NotImplementedError()

    # TODO
    async def temporarily_mute_user(self):
        # see https://stackoverflow.com/questions/62436615/how-do-i-temp-mute-someone-using-discord-py#:~:text=mute%20command%20so%20it's%20possible,and%20y%20is%20for%20years.
        # make sure to message the user when they have been muted/unmuted
        raise NotImplementedError()

    # TODO
    async def permanently_remove_user(self):
        # since we don't actually want to remove any users, send a message to the channel saying "user {user_name} has been removed from this channel!"
        # make sure to message the user when they have been removed
        raise NotImplementedError()

    # TODO
    async def notify_group_of_transgressions(self):
        # Notify users in group or joining group about the high volume of misinformation
        raise NotImplementedError()

    # TODO 
    def generate_summary_for_advanced_moderators(self):
        # Generate a message that summarizes the options selected during both the user and baseline moderator reporting flows
        # use the self.report object to access the self.report.state_to_selected_emoji_options or invoke self.report.generate_summary(self.report_id)
        
        return "Placeholder summary for advanced moderators."






    

