from enum import Enum, auto
from typing import Callable

class ModeratorAction(Enum):
    REMOVE_POST = auto()
    MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES = auto()
    NOTIFY_POSTER_OF_TRANSGRESSION = auto()
    TEMPORARILY_MUTE_USER = auto()
    PERMANENTLY_REMOVE_USER = auto()
    NOTIFY_GROUP_OF_TRANSGRESSIONS = auto()
    INCREMENT_GROUP_TRANSGRESSION_COUNTER = auto()
    FLAG_TO_ADVANCED_MODERATORS = auto()
    BLOCK_POSTER_TO_REPORTER = auto()
    MUTE_POSTER_TO_REPORTER = auto()

ACTION_TO_POST_ACTION_MESSAGE = {
    ModeratorAction.NOTIFY_POSTER_OF_TRANSGRESSION: "The user who created the post has been notified of the transgression.",
    ModeratorAction.MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES: "A disclaimer has been added to the post alongside links to reliable sources on COVID-19.",
    ModeratorAction.REMOVE_POST: "The post has been removed.",
    ModeratorAction.TEMPORARILY_MUTE_USER: "The user who created the post has been temporarily muted or blocked.",
    ModeratorAction.PERMANENTLY_REMOVE_USER: "The user who created the post has been permanently removed.",
    ModeratorAction.NOTIFY_GROUP_OF_TRANSGRESSIONS: "The group in which the post was made has been notified of the high volume of COVID disinformation transgressions.",
    ModeratorAction.INCREMENT_GROUP_TRANSGRESSION_COUNTER: "The group transgression count has been updated.",
    ModeratorAction.FLAG_TO_ADVANCED_MODERATORS: "This report has been flagged to advanced moderators.",
    ModeratorAction.BLOCK_POSTER_TO_REPORTER: "The reported poster has been blocked from your account.",
    ModeratorAction.MUTE_POSTER_TO_REPORTER: "The reported poster has been muted and you will no longer see their messages on your feed."
}

class EmojiOption:
    def __init__(self, emoji: str, option_str: str = None, action: ModeratorAction = None):
        self.emoji = emoji
        self.option_str = option_str
        self.action = action