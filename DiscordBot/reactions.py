from typing import Callable

class ModeratorAction(Enum):
    REMOVE_POST = auto()
    MODIFY_POST_WITH_DISCLAIMER_AND_RESOURCES = auto()
    NOTIFY_POSTER_OF_TRANSGRESSION = auto()
    TEMPORARILY_MUTE_USER = auto()
    PERMANENTLY_REMOVE_USER = auto()
    NOTIFY_GROUP_OF_TRANSGRESSIONS = auto()

class EmojiOption:
    def __init__(self, emoji: str, option_str: str = None, action: ModeratorAction = None, post_action_message: str = None):
        self.emoji = emoji
        self.option_str = option_str
        self.action = action
        self.post_action_message = post_action_message