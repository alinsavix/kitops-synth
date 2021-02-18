# Functions to apply random scale and rotation to the INSERTs
import bpy
from mathutils import Vector, Matrix
from sys import maxsize
import bmesh
from .. import property
from . import addon, randomness, distributors, inserts, messages
import datetime


def inserts_init(prop, context):
    """Add inserts and handle display options."""
    if prop.init_active is not None:
        context.scene.kitopssynth_target_obj = prop.init_active


def inserts_add(prop, context):
    """Add inserts and set up placement information."""
    preference = context.scene.kitopssynth
    layers = preference.layers

    if context.active_object:
        bpy.ops.ko.synth_clear('INVOKE_DEFAULT')

    new_insert_ids = []

    i = 0
    for layer in layers:
        layer.index = i
        if layer.is_enabled:
            inserts_add_layer(prop, context, layer, new_insert_ids)
        i+=1
            
    if len(new_insert_ids) == 0:
        messages.add_message(context, "No INSERTs were added.")


def inserts_add_layer(prop, context, layer, new_insert_ids):
    # see if there is an existing reference to INSERTS in this selection.  If not, create a new one.
    target_obj = context.scene.kitopssynth_target_obj
    insert_entry_map = None
    face_id_list = property.generate_face_id_list(target_obj)

    no_faces_selected = False
    if len(face_id_list):
        # register the layer -> face id mapping
        layer_id = layer.name
        if layer_id not in context.scene.kitopssynth_layer_face_map:
            face_map_ref = context.scene.kitopssynth_layer_face_map.add()
            face_map_ref.name = layer_id
        face_ids = context.scene.kitopssynth_layer_face_map[layer_id].face_ids
        face_ids.clear()
        for face_id in face_id_list:
            face_ids.add().face_id = face_id
    else:
        no_faces_selected = True
        old_active = context.active_object
        obj = target_obj
        layer_id = layer.name
        if layer_id in context.scene.kitopssynth_layer_face_map:
            face_ids = context.scene.kitopssynth_layer_face_map[layer_id].face_ids
            bm = bmesh.new()
            if obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.from_mesh(obj.data)
            bm.faces.ensure_lookup_table()
            for face_id_entry in face_ids:
                face_id = face_id_entry.face_id
                face_id_list.append(face_id_entry.face_id)
                bm.faces[face_id].select_set(True)

            if obj.mode == 'EDIT':
                bmesh.update_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.to_mesh(obj.data)
                bm.free()

            if context.active_object:
                bpy.ops.ko.synth_clear_layer('INVOKE_DEFAULT', layer_uid=layer.name)
                

    key = property.generate_insert_map_key(target_obj, face_id_list)

    # just create a new entry for target objects -> inserts.
    insert_entry_map = target_obj.kitopssynth_insert_map[key] if key in target_obj.kitopssynth_insert_map else target_obj.kitopssynth_insert_map.add()
    insert_entry_map.name = key

    # intitialise points and cache them.
    distribution_class_name = layer.distribution
    distributor = getattr(distributors, distribution_class_name)()
    new_insert_ids_to_add = distributor.distribute(prop, context, layer)
    new_insert_ids.extend(new_insert_ids_to_add)

    layer_to_update = insert_entry_map.layers[layer.name] if layer.name in insert_entry_map.layers else insert_entry_map.layers.add()
    layer_to_update.name = layer.name

    for insert_obj in new_insert_ids_to_add:
        if insert_obj is not None:
            layer_to_update.inserts.add().insert_obj = insert_obj

    if no_faces_selected:
        # reset the selection for next time.
        context.view_layer.objects.active = old_active
        obj = target_obj
        bm = bmesh.new()
        if obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(obj.data)
        elif obj.mode == 'OBJECT':
            bm.from_mesh(obj.data)
        for f in bm.faces:
            f.select_set(False)
        if obj.mode == 'EDIT':
            bmesh.update_edit_mesh(obj.data)
        elif obj.mode == 'OBJECT':
            bm.to_mesh(obj.data)
            bm.free()





def poll_add_random_inserts(context):
    return (context.active_object and context.active_object.select_get() and \
            ((context.active_object.type == 'MESH' and \
            context.active_object.mode == 'OBJECT') or \
            (context.active_object.type == 'MESH' and \
            context.active_object.mode == 'EDIT' and \
            context.scene.tool_settings.mesh_select_mode[2])))