# file for implementing the class representing a moderator response
from enum import Enum, auto
import discord
import re
from reactions import EmojiOption, ModeratorAction
from collections import defaultdict
from typing import Set

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
    State.THANK_MODERATOR: "Thank you for responding to the report! Begin a new response at any time by typing `respond`",
    State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS: "[ADVANCED MODERATOR REPORT NOTIFICATION]\n"  # TODO: handle_message will handle generating the report summary for the advanced moderators to act on
}

# If the state has only one next state to transition into
STATE_TO_SINGLE_NEXT_STATE =  {
    State.REPORT_IDENTIFIED: State.ASK_FOR_POST_ACTIONS,
    State.ASK_FOR_POST_ACTIONS: State.ASK_FOR_USER_ACTIONS,
    State.ASK_FOR_USER_ACTIONS: State.ASK_FOR_GROUP_ACTIONS,
    State.ASK_FOR_GROUP_ACTIONS: State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS,
    State.ASK_FOR_REASON_FOR_ELEVATING: State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS,
}

DEFAULT_REQUEST_EMOJI_RESPONSE_STR = " React to this message with the emoji corresponding to the correct category / categories.\n"

# see ModeratorAction enum in reactions.py for different actions to assign to emoji options
STATE_TO_EMOJI_OPTIONS = {
    State.ASK_FOR_POST_ACTIONS: {
        "❌": EmojiOption(emoji = "❌", option_str = "Remove post", action = ModeratorAction.REMOVE_POST, post_action_message = "The reported post has been removed."),
    },
    State.ASK_FOR_USER_ACTIONS: {
        "⚠️": EmojiOption(emoji = "⚠️", option_str = "Add disclaimer for users and link reliable resources (ex: CDC, WHO)", post_action_message = "A disclaimer has been added to the post alongside links to reliable sources on COVID-19."),
    }, 
    State.ASK_FOR_GROUP_ACTIONS: {
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Notify user of transgression", post_action_message = "The user who created the post has been notified of the transgression."),

    },
    State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS: {
        "👍": EmojiOption(emoji = "👍", option_str = "Yes", post_action_message = "After you complete your response to the report, we will forward the report to advanced moderators."),
        "👎": EmojiOption(emoji = "👎", option_str = "No"),
    }
    State.ASK_FOR_REASON_FOR_ELEVATING: {
        "1️⃣": EmojiOption(emoji = "1️⃣", option_str = "Severity of the post"),

    }
}

YES_ELEVATE_TO_ADVANCED_MODERATORS_ACTION = STATE_TO_EMOJI_OPTIONS[State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS]["👍"]

DEFAULT_CONTINUE_SYSTEM_MESSAGE_SUFFIX = "Once you're done selecting, please type `continue`. Type `cancel` to cancel the report at any point."

MESSAGE_THEN_CONTINUE = set([])

NO_CONTINUE_STATES = set([State.THANK_MODERATOR, State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS])

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
                self.take_actions(current_state_emoji_options)

                # special case for flagging for advanced moderator review
                if self.state == State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS and YES_ELEVATE_TO_ADVANCED_MODERATORS_ACTION in current_state_emoji_options:
                    self.elevate_to_advanced_moderators = True

                # generate a message to the moderator of a summary of the actions taken (if any)
                if self.state in STATE_TO_EMOJI_OPTIONS and len(current_state_emoji_actions):
                    post_action_messages = [emoji_action.post_action_message for emoji actions in current_state_emoji_actions if emoji_action.post_action_message]
                    
                    if len(post_action_messages):
                        reply = "We have taken the following actions based on your responses: \n"
                        for post_action_message in post_action_messages:
                            reply += f"·    {post_action_message}\n"

                        reply_list.append(reply)


            # TRANSITIONS
            # we now progress to the next state
            # process simple 1-to-1 transitions
            if self.state in STATE_TO_SINGLE_NEXT_STATE:
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

            # TODO: finish handling advanced transitions here
            if self.state == State.ASK_IF_ELEVATE_TO_ADVANCED_MODERATORS:
                self.state = State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS if self.elevate_to_advanced_moderators else State.THANK_MODERATOR

            # MESSAGING
            if self.state in MESSAGE_THEN_CONTINUE:
                reply_list.append(STATE_TO_MESSAGE_PREFIX[self.state])
                self.state = STATE_TO_SINGLE_NEXT_STATE[self.state]

            # start with the message prefix for that state if there is one
            reply = STATE_TO_MESSAGE_PREFIX[self.state] if self.state in STATE_TO_MESSAGE_PREFIX else ""
        
            # add a summary of the report thussofar if we are alerting the advanced moderators
            if self.state == State.GENERATE_SUMMARY_FOR_ADVANCED_MODERATORS:
                reply += self.generate_summary_for_advanced_moderators()

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

    async def take_actions(moderator_actions: Set[ModeratorAction]):
        for action in moderator_actions:
            if action == ModeratorAction.REMOVE_POST:
                self.remove_reported_post()
            elif action == ModeratorAction.MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES:
                self.modify_post_with_disclaimer_and_reliable_resources()
            elif action == ModeratorAction.NOTIFY_POSTER_OF_TRANSGRESSION:
                self.notify_poster_of_transgression()
            elif action == ModeratorAction.TEMPORARILY_MUTE_USER:
                self.temporarily_mute_user()
            elif action == ModeratorAction.PERMANENTLY_REMOVE_USER:
                self.permanently_remove_user()
            elif action == ModeratorAction.NOTIFY_GROUP_OF_TRANSGRESSIONS:
                self.notify_group_of_transgressions()

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


    async def handle_reaction(self, message, emoji, user):

        # check this is a state with valid emoji reaction options
        if self.state in STATE_TO_EMOJI_OPTIONS:

            # only store the emoji option as a response if the emoji is one associated with the sate
            if emoji in STATE_TO_EMOJI_OPTIONS[self.state]:

                emoji_option = STATE_TO_EMOJI_OPTIONS[self.state][emoji]

                print(f"The moderator reacted with option {emoji} during state {self.state}")
                self.moderator_state_to_selected_emoji[self.state].add(emoji_option)

        # we don't need to print a message to the user immediately upon reacting
        return []

    # TODO 
    def generate_summary_for_advanced_moderators(self):
        # Generate a message that summarizes the options selected during both the user and baseline moderator reporting flows
        # use the self.report object to access the self.report.state_to_selected_emoji_options or invoke self.report.generate_summary(self.report_id)
        
        return "Placeholder summary for advanced moderators."






    

