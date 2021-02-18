# Class containing parameters for use throughout the add-on.
from bpy.types import AddonPreferences
from bpy.utils import register_class, unregister_class
from bpy.props import BoolProperty
from . utility import addon

from . utility import addon, distributors

class kitops_synth(AddonPreferences):
    bl_idname = addon.name

    check_for_complexity : BoolProperty(
                                name="Check for complexity",
                                description="Check for the potential complexity of a layout before proceeeding",
                                default=True)

    def draw(self, context):

        layout = self.layout
        
        box = layout.box()
        row = box.row()
        # col.alignment = 'CENTER'
        row.label(text='Check for complexity')
        row.prop(self, 'check_for_complexity', text="")


classes = [kitops_synth]

def register():
    for cls in classes:
        register_class(cls)

    addon.preference()

def unregister():
    for cls in classes:
        unregister_class(cls)
