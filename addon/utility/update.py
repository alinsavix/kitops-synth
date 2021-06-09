# Functions to apply random scale and rotation to the INSERTs
import bpy
from mathutils import Vector, Matrix
from sys import maxsize
import bmesh
from .. import property
from kitops.addon.utility import insert, addon as kitops_addon
from . import addon, randomness, distributors, inserts, messages
import datetime


def inserts_init(prop, context):
    """Add inserts and handle display options."""
    if prop.init_active is not None:
        context.scene.kitopssynth_target_obj = prop.init_active


def cleanup():
    if 'INSERTS' in bpy.data.collections and not bpy.data.collections['INSERTS'].objects and not bpy.data.collections['INSERTS'].children:
        bpy.data.collections.remove(bpy.data.collections['INSERTS'])

    if 'INSERTS' in bpy.data.collections:
        for child in bpy.data.collections['INSERTS'].children:
            if not child.objects and not child.children:
                bpy.data.collections.remove(child)

    insert.show_solid_objects()
    insert.show_cutter_objects()
    insert.show_wire_objects()



def inserts_add(prop, context):
    """Add inserts and set up placement information."""
    preference = context.scene.kitopssynth
    layers = preference.layers

    new_insert_objs = []

    i = 0
    for layer in layers:
        layer.index = i
        if layer.is_enabled:
            inserts_add_layer(prop, context, layer, new_insert_objs, False)
        i+=1
            
    if len(new_insert_objs) == 0:
        messages.add_message(context, "No INSERTs were added.")

    cleanup()


def inserts_add_layer(prop, context, layer, new_insert_objs, cleanup=True):
    '''Main code for handling layout and distribution of INSERTs'''

    #Temporary set to regular mode if SMART mode is set to improve performance.
    kitops_preference = kitops_addon.preference()
    old_mode = kitops_preference.mode
    kitops_preference.mode = 'REGULAR'
    try:
        
        # see if there is an existing reference to INSERTS in this selection.  If not, create a new one.
        target_obj = context.scene.kitopssynth_target_obj
        insert_entry_map = None

        # Is this the active layer?
        is_active_layer = context.scene.kitopssynth.layers[context.scene.kitopssynth.layer_index].name == layer.name
        
        old_active = context.active_object

        layer_id = layer.name
        if layer_id not in target_obj.kitopssynth_layer_face_map:
            face_map_ref = target_obj.kitopssynth_layer_face_map.add()
            face_map_ref.name = layer_id
        face_ids = target_obj.kitopssynth_layer_face_map[layer_id].face_ids

        reset_selection = False
        if is_active_layer or not len(face_ids):
            # update the layer -> face selection mapping from the existing face selection
            face_id_list = property.generate_face_id_list(target_obj)
            face_ids.clear()
            for face_id in face_id_list:
                face_ids.add().face_id = face_id
        else:
            reset_selection = True
            # get the layer -> face selection mapping from the existing layer and set accordingly.
            old_face_selection_ids = []

            obj = target_obj
            bm = bmesh.new()
            if obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.from_mesh(obj.data)

            for f in bm.faces:
                if f.select:
                    old_face_selection_ids.append(f.index)
                f.select_set(False)
            bm.faces.ensure_lookup_table()
            for face_id_entry in face_ids:
                face_id = face_id_entry.face_id
                bm.faces[face_id].select_set(True)

            if obj.mode == 'EDIT':
                bmesh.update_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.to_mesh(obj.data)
                bm.free()

            face_id_list = property.generate_face_id_list(target_obj)
        

        if context.active_object:
            bpy.ops.ko.synth_clear_layer('INVOKE_DEFAULT', layer_uid=layer.name, delete_all=True)

        #if we have no face selections after this, just do nothing.
        if len(face_id_list):
            key = property.generate_insert_map_key(target_obj, face_id_list)

            # just create a new entry for target objects -> inserts.
            insert_entry_map = target_obj.kitopssynth_insert_map[key] if key in target_obj.kitopssynth_insert_map else target_obj.kitopssynth_insert_map.add()
            insert_entry_map.name = key

            # intitialise points and cache them.
            distribution_class_name = layer.distribution
            distributor = getattr(distributors, distribution_class_name)()
        
            new_insert_objs_to_add = distributor.distribute(prop, context, layer)
            new_insert_objs.extend(new_insert_objs_to_add)

            layer_to_update = insert_entry_map.layers[layer.name] if layer.name in insert_entry_map.layers else insert_entry_map.layers.add()
            layer_to_update.name = layer.name

            for insert_obj in new_insert_objs_to_add:
                if insert_obj is not None:
                    layer_to_update.inserts.add().insert_obj = insert_obj

        # reset the selection for next time.
        context.view_layer.objects.active = old_active
        if reset_selection:
            obj = target_obj
            bm = bmesh.new()
            if obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.from_mesh(obj.data)
            for f in bm.faces:
                f.select_set(False)
            bm.faces.ensure_lookup_table()
            for f_index in old_face_selection_ids:
                bm.faces[f_index].select_set(True)
            if obj.mode == 'EDIT':
                bmesh.update_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.to_mesh(obj.data)
                bm.free()

        if cleanup:
            cleanup()
    finally:
        kitops_preference.mode = old_mode



def poll_add_random_inserts(context):
    valid = False
    try:
        valid = (context.active_object and context.active_object.select_get() and \
            ((context.active_object.type == 'MESH' and \
            context.active_object.mode == 'OBJECT') or \
            (context.active_object.type == 'MESH' and \
            context.active_object.mode == 'EDIT' and \
            context.scene.tool_settings.mesh_select_mode[2])))
    except:
        valid = False
    if valid is None: valid = False
    return valid