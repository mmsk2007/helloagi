class ChannelRouter:
    def route(self, channel: str, text: str) -> str:
        return f"[{channel}] {text}"
