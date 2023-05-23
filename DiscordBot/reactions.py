from typing import Callable

class EmojiOption:
    def __init__(self, emoji: str, option_str: str = None, action: Callable = None, post_action_message: str = None):
        self.emoji = emoji
        self.option_str = option_str
        self.action = action
        self.post_action_message = post_action_message