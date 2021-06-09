
import bpy
from kitops.addon.utility import addon as kitops_addon
from kitops.addon.utility import insert, remove, id, regex
import numpy as np
import copy
from . import addon, randomness
from mathutils import Vector, Euler, Matrix, Quaternion
import bmesh
import os


def cleanup(prop, context, clear=False):

    option = addon.option()
    if not option.show_cutter_objects:
        for obj in prop.cutter_objects:
            obj.hide_viewport = True

    insert.operator = None

def set_display_type(uuid, display_type):
    objects_to_set = [obj for obj in bpy.data.objects if obj.kitops.id == uuid]
    for insert_obj in objects_to_set:
        insert_obj.display_type = display_type


def add_random_insert(op, context, layer, inserts, insert_frame_cache, rng = np.random.RandomState(123456), insert_name_ignore_list=[]):
    """Searches for and returns a random INSERT."""

    option = addon.option()

    layer_inserts = [insert for insert in inserts if insert.insert_name not in insert_name_ignore_list]

    # construct probability profile
    p = []
    total = len(layer_inserts)
    total_probabilities = 0
    probabilities = []
    for insert_entry in layer_inserts:
        if insert_entry.is_enabled:
            probability = insert_entry.proportionality
        else:
            probability = 0
        probabilities.append(probability)
        total_probabilities += probability

    if total_probabilities != 0:
        for probability in probabilities:
            p.append(probability / total_probabilities)

        random_insert_index = rng.choice(range(0, len(layer_inserts)), p=p)
        random_insert = layer_inserts[random_insert_index]

        category_name = random_insert.category

        if bpy.app.version[1] > 90:
            kitops_preference = kitops_addon.preference()
            old_boolean_solver_ref = kitops_preference.boolean_solver
        try:
            if bpy.app.version[1] > 90:
                kitops_preference.boolean_solver = layer.boolean_solver

            for index, category in enumerate(option.kpack.categories):
                if category.name == category_name:
                    if index < len(option.kpack.categories):
                        category_item = option.kpack.categories[index]
                        for index, blend in enumerate(category_item.blends):
                            if blend.name == random_insert.insert_name:
                                op.location = blend.location

                                insert_obj = insert_frame_cache.get_insert_frame(op)

                                if insert_obj is None:
                                    # will we ever retrieve an insert?
                                    all_equal = True
                                    for insert_entry in layer_inserts:
                                        if insert_entry.is_enabled and insert_entry.proportionality > 0:
                                            all_equal &= (insert_entry.insert_name ==  random_insert.insert_name)
                                    if all_equal:
                                        return None, None
                                    else:
                                        return add_random_insert(op, context, layer, inserts, insert_frame_cache, rng, insert_name_ignore_list)


                                # cleanup(op, context)
                                return insert_obj, random_insert
        finally:
            if bpy.app.version[1] > 90:
                kitops_preference.boolean_solver = old_boolean_solver_ref
    
    return None, None



def get_insert(id, parents_only=True):
    """Get an insert based on the id."""
    for obj in bpy.data.objects:
        if obj.kitops.id == id:
            if parents_only:
                if obj.parent is None:
                    return obj
            else:
                return obj
    return None


def purge_data_block(blockref):
    for block in getattr(bpy.data, blockref):
        if block.users == 0:
            getattr(bpy.data, blockref).remove(block)

def delete_hierarchy(obj_to_delete, target_obj=None):
    """Delete an object and it's hierarchy.""" #TODO move to helper class.

    if obj_to_delete is None or \
        (target_obj is not None and \
                obj_to_delete.kitops.reserved_target != target_obj): 
        return

    objects_to_delete = [obj for obj in bpy.data.objects if obj is not None and obj.kitops.id == obj_to_delete.kitops.id]

    for obj in objects_to_delete:
        # find any boolean modifiers in all objects and remove the boolean.

        if target_obj is not None:
            for mod in target_obj.modifiers:
                if mod.type == 'BOOLEAN':
                    if mod.object == obj:
                        target_obj.modifiers.remove(mod)

        obj.kitops['insert'] = False
        obj.kitops['insert_target'] = None
        obj.kitops['mirror_target'] = None
        obj.kitops['reserved_target'] = None
        obj.kitops['main_object'] = None

        try:
            remove.object(obj, data=True)
        except: pass     #TODO better error handling needed.


def purge_data_blocks():
    # do a rather aggressive purge.
    purge_data_block('meshes')
    purge_data_block('materials')
    purge_data_block('textures')
    purge_data_block('images')
    purge_data_block('node_groups')
    purge_data_block('curves')
    purge_data_block('fonts')



class SynthObject():

    def __init__(self):
        self.original_dimensions = None
        self.original_scale = None
        self.original_rotation_euler = None
        self.intended_position = None
        self.intended_size = None
        self.intended_rotation = None

def _rotate_around_pivot(pivot_point, point_to_rotate, amount):
    #point which will be rotated around the cursor
    rot_mat = Matrix.Rotation(amount, 3, 'Z')
    v_new = rot_mat @ (point_to_rotate - pivot_point) + pivot_point

    return v_new


def insert_add(op, context, boolean_solver):

    if bpy.app.version[1] > 90:
        kitops_preference = kitops_addon.preference()
        old_boolean_solver_ref = kitops_preference.boolean_solver

    uid = ''

    try:
        if bpy.app.version[1] > 90:
            kitops_preference.boolean_solver = boolean_solver

        uid = insert.add(op, context)

    except OSError:
        report_message = 'Failed to load .blend file for INSERT.'
        op.report({'ERROR'}, report_message)
    finally:
        if bpy.app.version[1] > 90:
            kitops_preference.boolean_solver = old_boolean_solver_ref

    return uid



class InsertFrame():

    def __init__(self, bound_box, matrix_world, scale, rotation_euler, location, hide_viewport, op_location, boolean_solver):

        self.kitopssynth = SynthObject()
        self.bound_box = bound_box
        self.matrix_world = matrix_world
        self.scale = scale
        self.rotation_euler = rotation_euler
        self.location = location
        self.hide_viewport = hide_viewport
        self.op_location = op_location
        self.boolean_solver = boolean_solver

        self.cache_location = self.location.copy()
        self.cache_scale = self.scale.copy()
        self.cache_matrix = self.matrix_world.copy()
        self.cache_euler = self.rotation_euler.copy()

    def to_object(self, op, context, convert_matrix):
        op.location = self.op_location


        if context.scene.kitopssynth.preview_mode and context.scene.kitopssynth.preview_type == 'FAST':
            #we're gonna draw something instead based on object bounding box....
            kitops_preference = kitops_addon.preference()
            basename = os.path.basename(op.location)
            collection_name = regex.clean_name(basename[:-6].title(), use_re=kitops_preference.clean_datablock_names)
            insert_name = collection_name + " Preview"

            me = bpy.data.meshes.new(insert_name)
            insert_obj = bpy.data.objects.new(insert_name, me)
            insert_obj.kitopssynth_insert.is_preview_insert = True
            insert_obj.kitops.id = id.uuid()


            insert_obj.location = self.cache_location
            insert_obj.matrix_world = self.cache_matrix
            insert_obj.scale = self.cache_scale
            insert_obj.rotation_euler = self.cache_euler
            insert_obj.color = context.scene.kitopssynth.preview_color



            bm = bmesh.new()

            i = 0
            for loc in self.bound_box:
                # v = bm.verts.new(insert_obj.matrix_world.inverted() @ Vector(loc))
                v = bm.verts.new(loc)
                v.index = i
                i+=1

            bm.verts.ensure_lookup_table()

            if len(bm.verts) == 8:
                bm.faces.new([bm.verts[0], bm.verts[1], bm.verts[2], bm.verts[3]])
                bm.faces.new([bm.verts[7], bm.verts[6], bm.verts[5], bm.verts[4]])
                bm.faces.new([bm.verts[0], bm.verts[4], bm.verts[5], bm.verts[1]])
                bm.faces.new([bm.verts[5], bm.verts[6], bm.verts[2], bm.verts[1]])
                bm.faces.new([bm.verts[7], bm.verts[4], bm.verts[0], bm.verts[3]])
                bm.faces.new([bm.verts[7], bm.verts[3], bm.verts[2], bm.verts[6]])

            bm.to_mesh(me)
            bm.free()

            
            if 'INSERTS' not in bpy.data.collections:
                context.scene.collection.children.link(bpy.data.collections.new(name='INSERTS'))

            collection_name = regex.clean_name(basename[:-6].title(), use_re=kitops_preference.clean_datablock_names)
            if collection_name not in bpy.data.collections:
                bpy.data.collections['INSERTS'].children.link(bpy.data.collections.new(name=collection_name))

            bpy.data.collections[collection_name].objects.link(insert_obj)

        else:

            uid = insert_add(op, context, self.boolean_solver)

            insert_obj = get_insert(uid)

            if insert_obj == None:
                return None

        insert_obj.kitopssynth_insert.is_preview_insert = context.scene.kitopssynth.preview_mode

        # determine delta between central location and actual center.
        origin = insert_obj.location
        natural_center = 0.125 * sum((Vector(b) for b in insert_obj.bound_box), Vector())
        natural_center = insert_obj.matrix_world @ natural_center
        natural_center[2] = origin[2]
        rotated_origin = _rotate_around_pivot(natural_center, origin, self.kitopssynth.intended_rotation)
        local_vector = (rotated_origin - natural_center) * self.scale
        mx_inv = convert_matrix.inverted()
        mx_norm = mx_inv.transposed().to_3x3()
        delta_vector = mx_norm @ local_vector

        # assign the object's transform properties
        point = self.location + delta_vector
        insert_obj.hide_viewport = self.hide_viewport
        insert_obj.location = point
        insert_obj.matrix_world = self.matrix_world
        insert_obj.matrix_world.translation = point
        insert_obj.rotation_euler.rotate_axis("Z", self.kitopssynth.intended_rotation)
        insert_obj.scale = self.scale

        if context.scene.kitopssynth.preview_mode and context.scene.kitopssynth.preview_type == "WIREFRAME":
            set_display_type(insert_obj.kitops.id, 'WIRE')

        insert.parent_objects(insert_obj, context.scene.kitopssynth_target_obj)

        cleanup(op, context)

        return insert_obj

    def __copy__(self):
        return InsertFrame( self.bound_box[:], 
                            self.matrix_world.copy(), 
                            self.scale.copy(), 
                            self.rotation_euler.copy(), 
                            self.location.copy(), 
                            self.hide_viewport, 
                            self.op_location,
                            self.boolean_solver
                            )

class InsertFrameCache():

    def __init__(self, op, context, layer, target_obj):
        self.insert_frames = {}
        option = addon.option()
        for insert_props in layer.inserts:
            if insert_props.is_enabled:
                category_name = insert_props.category
                for index, category in enumerate(option.kpack.categories):
                    if category.name == category_name:
                        if index < len(option.kpack.categories):
                            category_item = option.kpack.categories[index]
                            for index, blend in enumerate(category_item.blends):
                                if blend.name == insert_props.insert_name:
                                    op.location = blend.location
                                    old_bool_target = op.boolean_target
                                    op.boolean_target = None

                                    # temporarily get insert for sizing purposes
                                    uid = insert_add(op, context, layer.boolean_solver)

                                    if uid is None or uid == '':
                                        continue

                                    op.boolean_target = old_bool_target
                                    insert_obj = get_insert(uid)
                                    if insert_obj != None:
                                        cleanup(op, context)
                                        insert_frame = InsertFrame(
                                            [i[:]for i in insert_obj.bound_box[:]],
                                            insert_obj.matrix_world.copy(),
                                            insert_obj.scale.copy(),
                                            insert_obj.rotation_euler.copy(),
                                            insert_obj.location.copy(),
                                            insert_obj.hide_viewport,
                                            op.location,
                                            layer.boolean_solver)
                                        self.insert_frames[op.location] = insert_frame
                                        delete_hierarchy(insert_obj)

    def get_insert_frame(self, op):
        if op.location in self.insert_frames:
            return copy.copy(self.insert_frames[op.location])
        return None

    def clear(self):
        self.insert_frames.clear()
        purge_data_blocks()


