# Message methods for handling messages.

def clear_messages(context):
    '''Clear all SYNTH messages'''
    context.scene.kitopssynth.messages.clear()

def add_message(context, message):
    '''Add a SYNTH message'''
    context.scene.kitopssynth.messages.add().text = message