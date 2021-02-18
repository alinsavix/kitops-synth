# Addon utility class for looking up preferences and options
import os
import bpy

name = __name__.partition('.')[0]

def preference():
    """Access the main preferences for this addon"""
    preference = bpy.context.preferences.addons[name].preferences
    return preference

#TODO do we need this?
def option():
    "Returns options for use in the UI panel."
    wm = bpy.context.window_manager
    if not hasattr(wm, 'kitops'):
        return False

    option = bpy.context.window_manager.kitops

    if not option.name:
        option.name = 'options'
        update.options()

    # Made this false as we are not auto scaling.
    option.auto_scale = False

    return option