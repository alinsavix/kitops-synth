# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    'name': 'KIT OPS SYNTH',
    'author': 'Chipp Walters, MX2, Mark Kingsnorth',
    "blender" : (2, 80, 0),
    "version" : (1, 0, 0),
    'location': 'View3D > Toolshelf (T)',
    'description': 'Add multiple KIT OPS INSERTS to your mesh',
    'wiki_url': '',
    'category': '3D View'}

try: import kitops
except ModuleNotFoundError: pass
if "kitops" not in globals():
    message = ("\n\n"
        "This addon depends on kitops.\n"
        "Visit https://www.kit-ops.com/ for details")
    raise Exception(message)

import bpy
import os
from bpy.app.handlers import persistent


# from . addon.utility import addon, update
from . addon import preference, property
from . addon.interface import operator, panel
import uuid

@persistent
def depsgraph_update_pre_handler(dummy):  
    if bpy.context.scene.kitopssynth.is_initialized == False:
        bpy.context.scene.kitopssynth.is_initialized = True
        layers = bpy.context.scene.kitopssynth.layers
        layers.clear()
        layer = layers.add()
        layer.name = str(uuid.uuid4())
        layer.layer_name = "Default Layer"
        operator.init_layer(layer)
        
def register():
    
    property.register()
    preference.register()
    operator.register()
    panel.register()
    bpy.app.handlers.depsgraph_update_pre.append(depsgraph_update_pre_handler)


def unregister():

    property.unregister()
    panel.unregister()
    operator.unregister()
    preference.unregister()
    bpy.app.handlers.depsgraph_update_pre.remove(depsgraph_update_pre_handler)
    


    
    