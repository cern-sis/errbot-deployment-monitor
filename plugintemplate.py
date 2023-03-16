from errbot import BotPlugin, botcmd


class PluginTemplate(BotPlugin):
    @botcmd
    def whereami(self, msg, args):
        stream = msg._from._room._id
        topic = msg._from._room._subject
        return f"You are in #{stream}>{topic}"
