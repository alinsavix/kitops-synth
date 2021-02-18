
# Class that defines all the distributors.
from math import ceil, radians, degrees, sin, cos
import hashlib
from kitops.addon.utility import math
from . import addon, randomness, inserts, messages
import bmesh
import bpy
from bpy.props import *
import numpy as np
from mathutils import Vector, Matrix, geometry
from copy import deepcopy as copy
import sys
import importlib



# Use this to abstract class implement new classes below.  Must be in same module.
class AbstractDistributor:
    """Distribute a numnber of a number of points for an object."""

    def distribution_name():
        pass

    def distribute(self, prop=None, context=None, layer=None):
        return []

    def draw(preference, layout):
        pass

    def is_complex(self, layer):
        return False
        
    def encode(self, layer):
        return {}

    def decode(self, parametersJSON, layer):
        pass

def calc_dimensions(matrix_world, local_center, local_normal, all_verts, padding_percentage):
    """Method for calculated all required dimensions for row/col.grid calculation."""

    # center face insert paterns to the middle of the face, and generate a quaternion that aligns the objects to the face normal.
    location = matrix_world @ local_center

    # determine direction of face in world space.
    mx_inv = matrix_world.inverted()
    mx_norm = mx_inv.transposed().to_3x3()
    direction = mx_norm @ local_normal

    track_quaternion = direction.to_track_quat('Z', 'Y')

    # set up a matrix to align the objects to to generate a grid that maps to the bounds extents of the face.
    matrix = track_quaternion.to_matrix().to_4x4()

    #As the matrix will have only included orientation, also map the transllation to the position of the face.
    matrix.translation = location
    #The inverted matrix helps us map face vertices to a 'flat' space so we can generate the grid.
    inverted_matrix = matrix.inverted()

    #calculate bounds of face when converted to same space as a grid would be.  This is to calculate the grid to be projected.
    inverted_cos = [inverted_matrix @ (matrix_world @  v.co)  for v in all_verts]
    inverted_x_cos = [co.x for co in inverted_cos]
    inverted_y_cos = [co.y for co in inverted_cos]

    inverted_x_min = min(inverted_x_cos)
    inverted_x_max = max(inverted_x_cos)
    inverted_y_min = min(inverted_y_cos)
    inverted_y_max = max(inverted_y_cos)

    inverted_face_dim_x = (inverted_x_max - inverted_x_min)
    inverted_face_dim_y = (inverted_y_max - inverted_y_min)

    # calculate padding amount.
    padding = inverted_face_dim_x * padding_percentage * 0.01
    inverted_face_dim_x -= padding
    inverted_face_dim_y -= padding
    inverted_x_min += padding / 2
    inverted_x_max -= padding / 2 
    inverted_y_min += padding / 2
    inverted_y_max -= padding / 2

    return matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding


def find_edge_groups(edges):
    """Finds groups of linked edges"""
    # We use quite a bit of recursion so we lift the recursion limit here.
    limit_temp = sys.getrecursionlimit()
    sys.setrecursionlimit(10**6) 
    try:
        edge_groups = []
        for e in edges:
            potential_edge_group = []
            calc_edge_groups(e, potential_edge_group)
            if len(potential_edge_group) > 0:
                edge_groups.append(potential_edge_group)
    finally:
        sys.setrecursionlimit(limit_temp) 

    return edge_groups

def calc_edge_groups(e, potential_edge_group):
    """Recursive function to find groups of linked edges"""
    if not e.select or e.tag:
        return
    
    e.tag = True
    potential_edge_group.append(e)

    linked_edges = []
    for v in e.verts:
        v_linked_edges = v.link_edges
        for v_linked_edge in v_linked_edges:
            if v_linked_edge  != e:
                linked_edges.append(v_linked_edge)

    for linked_edge in linked_edges:
        calc_edge_groups(linked_edge, potential_edge_group)

    return potential_edge_group


def lerp(a, b, f):
    return a + f * (b - a)

def find_face_groups(bm):
    """Finds groups of linked faces"""

    # delete all non selected faces
    bmesh.ops.delete(bm, geom = [f for f in bm.faces if not f.select], context="FACES")
    # dissolve edges that aren't on the boundary
    bmesh.ops.dissolve_edges(bm, edges = [e for e in bm.edges if not e.is_boundary])

    for f in bm.faces:
        f.select_set(True)

    # We use quite a bit of recursion so we lift the recursion limit here.
    limit_temp = sys.getrecursionlimit()
    sys.setrecursionlimit(10**6) 
    try:
        face_groups = []
        for f in bm.faces:
            potential_face_group = []
            calc_face_groups(f, potential_face_group)
            if len(potential_face_group) > 0:
                face_groups.append(potential_face_group)
    finally:
        sys.setrecursionlimit(limit_temp) 

    return face_groups

def calc_face_groups(f, potential_face_group):
    """Recursive function to find groups of linked faces/"""
    if not f.select or f.tag:
        return
    
    f.tag = True
    potential_face_group.append(f)

    link_faces = [linked_face for e in f.edges
            for linked_face in e.link_faces if linked_face is not f]

    for link_face in link_faces:
        calc_face_groups(link_face, potential_face_group)

    return potential_face_group

def is_intersect_face_group(face_group, co):
    for f in face_group:
        if bmesh.geometry.intersect_face_point(f, co):
            return True
    return False

def calc_face_group_center(face_group):
    face_center_totals = Vector((0,0,0))
    for f in face_group:
        face_center = f.calc_center_median()
        face_center_totals += face_center
    return Vector(( face_center_totals[0] / len(face_group) , face_center_totals[1] / len(face_group), face_center_totals[2] / len(face_group)))

def calc_face_group_normal(face_group):
    face_normal_totals = Vector((0,0,0))
    for f in face_group:
        face_normal_totals += f.normal
    return Vector(( face_normal_totals[0] / len(face_group) , face_normal_totals[1] / len(face_group), face_normal_totals[2] / len(face_group))).normalized()

def assign_pre_scale(insert_ids, layer, padding, custom_scale_multiplier = 1):
    """Assign some pre scale calculations before layouts are applied"""
    preference = layer
    for insert_entry in insert_ids:
        insert_props = insert_entry[1]
        if insert_props.do_not_scale:
            continue
        main = insert_entry[0]

        init_hide = copy(main.hide_viewport)
        main.hide_viewport = False
        main.scale = main.kitopssynth.original_scale
        insert_dimensions = main.kitopssynth.original_dimensions

        if Vector(insert_dimensions).magnitude > 0:

            intended_size = main.kitopssynth.intended_size
            intended_x_length = intended_size[0] - padding if intended_size[0] - padding > 0 else 0
            intended_y_length = intended_size[1] - padding if intended_size[1] - padding > 0 else 0


            if preference.maintain_aspect_ratio: #TODO remove if maintain aspect ratio by insert is approved.
                scale_x = (intended_x_length / insert_dimensions[0]) if insert_dimensions[0] != 0 else 0
                scale_y = (intended_y_length / insert_dimensions[1]) if insert_dimensions[1] != 0 else 0

                if scale_x == 0 or scale_y == 0:
                    scale_z = scale_x if scale_x != 0 else scale_y
                elif scale_x < scale_y:
                    scale_y = scale_x
                    scale_z = scale_x
                else:
                    scale_x = scale_y
                    scale_z = scale_y

                setattr(main.scale, 'x', getattr(main.scale, 'x') * scale_x * custom_scale_multiplier)
                setattr(main.scale, 'y', getattr(main.scale, 'y') * scale_y * custom_scale_multiplier)
                setattr(main.scale, 'z', getattr(main.scale, 'z') * scale_z * custom_scale_multiplier)
            else:
                # determine relative scale passed on the bounds of the original
                scale_x = (intended_x_length / insert_dimensions[0]) * (((100 - preference.padding_v) / 100))
                scale_y = (intended_y_length / insert_dimensions[1]) * (((100 - preference.padding_h) / 100))
                scale_z = preference.height_scale / 100

                setattr(main.scale, 'x', getattr(main.scale, 'x') * scale_x * custom_scale_multiplier)
                setattr(main.scale, 'y', getattr(main.scale, 'y') * scale_y * custom_scale_multiplier)
                setattr(main.scale, 'z', getattr(main.scale, 'z') * scale_z * custom_scale_multiplier)



            main.hide_viewport = init_hide


def assign_post_scale(insert_ids, layer):
    """Assign some post scale changes"""
    preference = layer
    for insert_entry in insert_ids:
        insert_props = insert_entry[1]
        if insert_props.do_not_scale:
            continue
        main = insert_entry[0]

        init_hide = copy(main.hide_viewport)
        main.hide_viewport = False
        insert_dimensions = main.kitopssynth.original_dimensions

        if Vector(insert_dimensions).magnitude > 0:
            # set up specific x/y/z deviations.
            global _all_axes
            for a in _all_axes:

                # apply x/y/z deviation stretches.
                scale_deviation = getattr(preference, 'scale_' + a + '_deviation') * 0.01
                scale_axis = getattr(main.scale, a)
                adjusted_scale = scale_axis + (scale_axis * scale_deviation)

                # over scale outside the bounds if necessary.
                scale_multiplier = 1
                if abs(insert_props.scale) > 100:
                    scale_multiplier = insert_props.scale * 0.01

                adjusted_scale = adjusted_scale * scale_multiplier
                setattr(main.scale, a, adjusted_scale)

            main.hide_viewport = init_hide


def assign_rotation(insert_ids, layer):
    """Apply random rotations to selected inserts."""
    preference = layer
    
    for insert_entry in insert_ids:
        insert_props = insert_entry[1]
        main = insert_entry[0]

        # get the cached euler location and reset it so we can apply the euler seperately.
        
        main.rotation_euler = main.kitopssynth.original_rotation_euler
        main.rotation_euler.rotate_axis("Z", main.kitopssynth.intended_rotation)

# set up random proportions
def get_proportions(rng, divisions, deviation_percentage, length):
    """Get length proportions for a row or column"""
    proportions = []
    denominator = 0
    for i in range(0, divisions):
        numerator = 1 + (rng.choice([-1,1]) * deviation_percentage * 0.01)
        proportions.append(numerator)
        denominator+=numerator

    #if all proportions turned out the same, vary just one to always show variation.
    if len(proportions) > 1:
        unique_proportions = list(set(proportions))
        if len (unique_proportions) == 1:
            random_proportion_index = rng.choice(range(0, len(proportions)))
            proportion_to_deviate = proportions[random_proportion_index]
            denominator -= proportion_to_deviate
            multiplier = -1 if proportion_to_deviate > 1 else 1
            proportions[random_proportion_index] = 1 + (multiplier * deviation_percentage * 0.01)
            denominator += proportions[random_proportion_index]

    for i in range(0, divisions):
        proportions[i] = proportions[i] / denominator

    length_proportions = []
    for i in range(0, divisions):
        random_length = length * proportions[i]
        length_proportions.append(random_length)

    return length_proportions

def get_proportion_list(num_of_portions, rng, rng_extent):
    """Get a list containing random amounts that all add up to 1. rng_extend, 1 = most random, 0 = not random."""
    denominator = 0
    proportions = []
    for i in range(0, num_of_portions):
        numerator = rng.uniform(1- rng_extent, 1)
        denominator += numerator
        proportions.append(numerator)
    
    for i in range(0, len(proportions)):
        numerator = proportions[i]
        proportions[i] = numerator / denominator

    return proportions


def get_edge_position(point_along_edges, ordered_edge_tuples):
    total_length_so_far = 0
    for edge_tuple in ordered_edge_tuples:
        edge = edge_tuple[0]
        vertA= edge_tuple[1]
        vertB= edge_tuple[2]

        edge_length = edge.calc_length()

        total_length_so_far+=edge_length

        if point_along_edges <= total_length_so_far:
            # this is the edge where the point is at.
            point_on_this_edge = point_along_edges - (total_length_so_far - edge_length)
            factor = point_on_this_edge / edge_length
            position = vertA.co.lerp(vertB.co, factor)
            return position, edge
        

    return None

def delete_synth_entry(obj, entry):
    i = 0
    key = entry.name
    index_to_delete = -1
    for entry_map in  obj.kitopssynth_insert_map:
        if entry_map.name == key:
            index_to_delete = i
            break
        i+=1
    if index_to_delete >= 0:
        insert_entry_map = obj.kitopssynth_insert_map.remove(index_to_delete)


def adjust_dimensions_for_rotation(insert_dimensions, rotation):
    '''Adjust dimensions based on rotation'''
    abs_sin = abs(sin(rotation))
    abs_cos = abs(cos(rotation))
    # abs_cos = 1 - abs_sin

    height = insert_dimensions[0]
    width = insert_dimensions[1]

    bound_w = width * abs_sin + height * abs_cos
    bound_h = width * abs_cos + height * abs_sin
    insert_dimensions[0] = bound_w
    insert_dimensions[1] = bound_h

def set_rotation(insert_obj, preference, rng):
    rotation = preference.rotation
    if preference.rotation_deviation > 0:
        rotation += (preference.rotation_deviation * rng.randint(ceil(360 / degrees(preference.rotation_deviation) )) )
    insert_obj.kitopssynth.intended_rotation = rotation

def set_up_insert(insert_obj, preference, matrix, rng):
    insert_bounds = [Vector(point[:]) for point in insert_obj.bound_box[:]]
    insert_dimensions = math.coordinates_dimension(insert_bounds)
    set_rotation(insert_obj, preference, rng)
    if preference.rotation_respect_borders:
        adjust_dimensions_for_rotation(insert_dimensions, insert_obj.kitopssynth.intended_rotation)

    insert_obj.matrix_world = matrix
    insert_obj.kitopssynth.original_scale = insert_obj.scale
    insert_obj.kitopssynth.original_rotation_euler = insert_obj.rotation_euler
    insert_obj.kitopssynth.original_dimensions = insert_dimensions

def stretch_insert_to_bounds(insert_obj, bound_width, bound_height, insert_width, insert_height, x_index=0, y_index=1):

    rotation = insert_obj.kitopssynth.intended_rotation
    abs_sin = abs(sin(rotation))
    abs_cos = abs(cos(rotation))

    multiplier = abs_sin * 2 if abs_sin < 0.5 else (abs_sin - 0.5) * 2

    start = insert_obj.scale[x_index] * (bound_width / insert_width)
    end = insert_obj.scale[y_index] * (bound_height / insert_height )

    scale_x = lerp(start, end, multiplier)
    scale_y = lerp(end, start, multiplier)

    insert_obj.scale[x_index] = scale_x
    insert_obj.scale[y_index] = scale_y


_all_axes = [a for a in 'xyz']


# ###
# ### New Distributors go below.
# ###
class RowDistributor(AbstractDistributor):
    """"Distribute inserts uniformly in a grid driven by a seed value."""

    def distribution_name():
        return 'Rows'

    def _get_dimension_calc(self, matrix_world, local_center, local_normal, face_group_verts, padding):
        """"Calculate the inverted dimensions of the face group bounds."""
        return calc_dimensions(matrix_world, local_center, local_normal, face_group_verts, padding)

    def _get_rows_preference(self, preference):
        """Get the preference used to control the rows."""
        return preference.rows

    def _get_rows_height_deviation_preference(self, preference):
        """Get the preference for the row height deviation."""
        return preference.row_height_deviation

    def _get_row_insert_width_deviation_preference(self, preference):
        """Get the preference for the row height deviation."""
        return preference.row_insert_width_deviation

    def _get_dimension_x_index(self):
        """Get index lookup key for the x dimension."""
        return 0

    def _get_dimension_y_index(self):
        """Get index lookup key for the y dimension."""
        return 1

    
    def _calc_position(self, preference, matrix, inverted_row_x_pos, inverted_insert_width, inverted_row_y_pos):
        """Calculate the position of the INSERT."""
        return matrix @ (Vector((inverted_row_x_pos  + (inverted_insert_width / 2), 
                                inverted_row_y_pos, 
                                preference.z_position)))

    def _get_actual_row_width(context, matrix, inverted_row_width):
        """Calculate the actual row height of the INSERT."""
        return (matrix @ Vector((0, 0, 0)) - matrix @ Vector((inverted_row_width, 0, 0))).magnitude

    def _get_actual_row_height(context, matrix, inverted_row_height):
        """Calculate the actual row height of the INSERT."""
        return (matrix @ Vector((0, 0, 0)) - matrix @ Vector((0, inverted_row_height, 0))).magnitude


    def _get_left_right_vector(self, matrix):
        """Get the vector running across the INSERT layout."""
        return (matrix @ Vector((1, 0, 0)) - matrix @ Vector((0, 0, 0))).normalized()

    def _get_top_bottom_vector(self, matrix):
        """Get the vector running up the INSERT layout."""
        return (matrix @ Vector((0, 1, 0)) - matrix @ Vector((0, 0, 0))).normalized()

    def _get_size(self, size_x, size_y):
        """Get the sizing for the INSERT."""
        size = Vector((1,1,1))
        size.x = size_x
        size.y = size_y
        return size

    def _get_placement(self, preference):
        """Return placement settings"""
        return preference.row_placement

    def distribute(self, prop, context, layer):
        """Distribute INSERTS across an object."""
        
        preference = layer

        rng = randomness.random_generator(context, layer)

        # entry.name = self.__class__.distribution_name() + " Layout"
        
        bm = bmesh.new()

        target_obj = context.scene.kitopssynth_target_obj

        insert_frame_cache = inserts.InsertFrameCache(prop, context, layer, target_obj)

        insert_ids_to_return = []
        matrix = None
        try:
            preference_rows = self._get_rows_preference(preference)
            if not preference.use_boundary:
                no_of_rows = preference_rows
            else:
                no_of_rows = preference_rows - 1

            if no_of_rows == 0:
                return []

            me = target_obj.data
            bm.from_mesh(me)

            local_center = None
            local_normal = None

            # First, get all groups of selected faces.  Then, iterate over each group and overlay a set of rows.
            face_groups = find_face_groups(bm)
            overall_insert_name_ignore_list = []

            #make an overall list to only permit 'use once' insert selections on certain rows.
            use_once_inserts = [insert for insert in layer.inserts if insert.use_once and insert.is_enabled]
            use_many_inserts = [insert for insert in layer.inserts if not insert.use_once and insert.is_enabled]

            face_group_row_map = {}
            for face_group_index in range(len(face_groups)):
                insert_row_map = {}
                for row_index in range(0, no_of_rows):
                    insert_row_map[row_index] = use_many_inserts[:]
                face_group_row_map[face_group_index] = insert_row_map

            for use_once_insert in use_once_inserts:
                random_face_group_index = rng.choice(range(len(face_group_row_map)))
                random_row_index = rng.choice(range(no_of_rows))
                face_group_row_map[random_face_group_index][random_row_index].append(use_once_insert)

          
            for face_group_index in range(len(face_groups)):
                face_group = face_groups[face_group_index]
                local_center = calc_face_group_center(face_group)
                local_normal = calc_face_group_normal(face_group)
                

                face_group_verts = []
                for f in face_group:
                    face_group_verts.extend(f.verts)

                face_group_verts = list(set(face_group_verts))

                # Determine the inverted bounds and matrix for converting between this 'inverted' space 
                # (that is, the flattened space where the grid lies) and the 'actual' space (essentially the world space where the INSERTs need to be.)
                matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding = self._get_dimension_calc(target_obj.matrix_world, local_center, local_normal, face_group_verts, preference.padding)

                # set up horizontal and vertical vectors.
                left_right_vector = self._get_left_right_vector(matrix)
                top_bottom_vector = self._get_top_bottom_vector(matrix)

                # set up further parameters using helper methods - the column distribution overrides these methods as it performs very similar logic in laying out columns.
                x_index = self._get_dimension_x_index()
                y_index = self._get_dimension_y_index()
    
                inverted_row_width = inverted_face_dim_x
                actual_row_width = self._get_actual_row_width(matrix, inverted_row_width)

                # knoble the row width by the frequency.
                actual_row_width_cut = actual_row_width * (preference.frequency * 0.01)

                
                if not preference.use_boundary:
                    row_height_proportions = get_proportions(rng, no_of_rows, self._get_rows_height_deviation_preference(preference), inverted_face_dim_y)
                else:
                    row_height_proportions = get_proportions(rng, no_of_rows+1, self._get_rows_height_deviation_preference(preference), inverted_face_dim_y)

                inverted_height_so_far = 0

                for row_index in range(0, no_of_rows):

                    if not preference.use_boundary:
                        inverted_row_height = row_height_proportions[row_index]
                        if inverted_row_height == 0:
                            continue
                        # calculate the scale of the insert to the height of the row.
                        actual_row_height = self._get_actual_row_height(matrix, inverted_row_height)

                        inverted_row_y_pos = inverted_y_max - inverted_height_so_far -  (inverted_row_height / 2)
                        inverted_height_so_far += inverted_row_height
                    else:
                        inverted_row_height = row_height_proportions[row_index]
                    
                    inverted_row_x_pos = inverted_x_min

                    # Fill row with inserts until we reach the end.
                    actual_total_width_so_far = 0

                    row_insert_ids = []
                    # faces = []
                    total_inserts_width = 0
                    insert_name_ignore_list = []
                    insert_name_ignore_list.extend(overall_insert_name_ignore_list)
                    unique_inserts = list(set([insert_prop.insert_name for insert_prop in layer.inserts]))

                    while (actual_total_width_so_far < actual_row_width_cut):

                        # create an insert.
                        inserts_for_row = face_group_row_map[face_group_index][row_index]
                        insert_obj, insert_props = inserts.add_random_insert(prop, context, layer, inserts_for_row, insert_frame_cache, rng, insert_name_ignore_list)
                        if insert_obj is None:
                            break # exit out of everything because we could not randomly retrieve an insert.


                        # if the scale is zero, move along.
                        if insert_props.scale == 0:
                            insert_name_ignore_list.append(insert_props.insert_name)
                            continue
                        
                        set_up_insert(insert_obj, preference, matrix, rng)
                        insert_dimensions = insert_obj.kitopssynth.original_dimensions
                        # if insert_dimensions[x_index] == 0 or insert_dimensions[y_index] == 0:
                        #     messages.add_message(context, 'INSERT detected with zero x or y dimensions, cannot place in row/column layout')
                        #     insert_name_ignore_list.append(insert_props.insert_name)
                        #     overall_insert_name_ignore_list.append(insert_props.insert_name)
                        #     continue
                        if insert_dimensions[x_index] == 0:
                            insert_dimensions[x_index] = 0.1
                        if insert_dimensions[y_index] == 0:
                            insert_dimensions[y_index] = 0.1


                        scale_multiplier = 1
                        if abs(insert_props.scale) <= 100:
                            scale_multiplier = insert_props.scale * 0.01

                        shrink_required = False
                        if not preference.use_boundary:

                            if insert_props.do_not_scale:
                                shrink_required = insert_dimensions[y_index] >= inverted_row_height
                                size = self._get_size(insert_dimensions[x_index], insert_dimensions[y_index])
                                inverted_insert_width = insert_dimensions[x_index]
                                actual_insert_width = inverted_insert_width
                            else:                       
                                inverted_insert_width = (insert_dimensions[x_index] / insert_dimensions[y_index]) * inverted_row_height * scale_multiplier
                                actual_insert_width = (insert_dimensions[x_index] / insert_dimensions[y_index]) * actual_row_height * scale_multiplier
                                size = self._get_size(actual_insert_width, actual_row_height)
                            
                            insert_obj.kitopssynth.intended_size = size
                        else:
                            if insert_props.do_not_scale:
                                size = self._get_size(insert_dimensions[x_index], insert_dimensions[y_index])
                                inverted_insert_width = insert_dimensions[x_index]
                            else:
                                size = self._get_size(insert_dimensions[x_index] * scale_multiplier, insert_dimensions[y_index] * scale_multiplier)
                                inverted_insert_width = insert_dimensions[x_index] * scale_multiplier

                            actual_insert_width = size[x_index]
                            actual_row_height = size[y_index]

                            insert_obj.kitopssynth.intended_size = size
                            assign_pre_scale([(insert_obj, insert_props)], layer, padding)

                            

                            row_y_offset = 0
                            row_h_index = 0
                            while row_h_index <= row_index:
                                row_y_offset+=row_height_proportions[row_h_index]
                                row_h_index+=1

                            inverted_row_y_pos = inverted_y_max - row_y_offset
                            inverted_row_y_pos = inverted_row_y_pos + (inverted_row_height * preference.boundary_deviation * 0.01)

                        actual_total_width_so_far += actual_insert_width


                        # commit to adding the insert if it is with the length of the actual row.
                        is_insert_valid = False
                        if (actual_total_width_so_far < actual_row_width_cut):
                            # we have not yet spilled over the row, continue.
                            is_insert_valid = True
                        elif (actual_total_width_so_far >= actual_row_width_cut) and not insert_props.maintain_aspect_ratio:
                            # even though we splled over the row, we will add this any way as it should stretch to the length of the row.
                            is_insert_valid = True

                        # if scale is required but we should not scale, this is invalid.
                        if shrink_required and insert_props.do_not_scale:
                            is_insert_valid = False

                        if is_insert_valid:

                                total_inserts_width += actual_insert_width

                                position = self._calc_position(preference, matrix, inverted_row_x_pos, inverted_insert_width, inverted_row_y_pos)

                                inverted_row_x_pos += inverted_insert_width
                                insert_obj.location = position
                                insert_obj.kitopssynth.intended_position = position
                                
                                
                                row_insert_ids.append((insert_obj, insert_props, size, actual_row_height, inverted_insert_width))
                                

                                # add to ignore if use once.
                                if insert_props.use_once:
                                    overall_insert_name_ignore_list.append(insert_props.insert_name)
                                    insert_name_ignore_list.append(insert_props.insert_name)

                        else:

                            # rollback as we spilled over the row or otherwise invalid.
                            
                            
                            # if we can, try the other INSERT in the layer by going back round the loop.
                            if len(insert_name_ignore_list) < len(unique_inserts):
                                #roolback width check.
                                actual_total_width_so_far -= actual_insert_width
                                # add thre current type of INSERT to the ignore list.
                                insert_name_ignore_list.append(insert_props.insert_name)
                                continue

                    if not preference.use_boundary:
                        assign_pre_scale(row_insert_ids, layer, padding)

                    # randomly shuffle the 'row' of inserts to ensure randomness.
                    rng.shuffle(row_insert_ids)
                    inverted_row_x_pos = inverted_x_min
                    # reposition INSERTs now they are shuffled.
                    for insert_entry in row_insert_ids:
                        insert_props = insert_entry[1]
                        insert_width = insert_entry[2][x_index]
                        insert_height = insert_entry[2][y_index]
                        row_height = insert_entry[3]
                        inverted_insert_width = insert_entry[4]

                        main = insert_entry[0]
                        new_position = Vector(main.kitopssynth.intended_position)
                        inverted_position = matrix.inverted() @ new_position

                        inverted_position[x_index] = inverted_row_x_pos + (inverted_insert_width / 2)
                        inverted_row_x_pos += inverted_insert_width
                        main.kitopssynth.intended_position = matrix @ inverted_position

                    if not preference.use_boundary:
                        randomness_factor = 0
                    else:
                        randomness_factor = preference.boundary_randomness

                    # random variation
                    proportion_list = get_proportion_list(len(row_insert_ids), rng, randomness_factor)

                    # vary the width randomly.
                    remaining_width = actual_row_width - total_inserts_width
                    
                    segment_lengths = []
                    for c in range(len(row_insert_ids)):
                        insert_entry = row_insert_ids[c]
                        proportion = proportion_list[c]
                        insert_width = insert_entry[2][x_index]
                        segment_length = insert_width + (remaining_width * proportion)
                        segment_lengths.append(segment_length)
                        

                    # vary the widths by a proportional variation if necessary.
                    if self._get_row_insert_width_deviation_preference(preference) != 0:
                        proportion_list_variation = get_proportions(rng, len(row_insert_ids), self._get_row_insert_width_deviation_preference(preference), 1)
                        for c in range(len(row_insert_ids)):
                            variation = proportion_list_variation[c]
                            segment_length = segment_lengths[c]
                            segment_lengths[c] = segment_length * variation

                    # normalize segment widths - ensure that no segments are less than their widths if we need to maintain aspect ratio.

                    # divide the inserts between those that should be proportional and those where it does not matter.
                    proportional_segment_lengths = {}
                    non_proportional_segment_lengths = {}
                    for c in range(len(row_insert_ids)):
                        insert_entry = row_insert_ids[c]
                        insert_props = insert_entry[1]
                        insert_width = insert_entry[2][x_index]
                        segment_length = segment_lengths[c] if segment_lengths[c] > 0 else 0
                        if insert_props.maintain_aspect_ratio and (insert_width > segment_length):
                            proportional_segment_lengths[c] = insert_width
                        else:
                            non_proportional_segment_lengths[c] = segment_length
                    
                    # now we have done this, calculate the segment lengths for each set.
                    proportional_segment_length_total = sum(proportional_segment_lengths.values())
                    non_proportional_segment_length_total = sum(non_proportional_segment_lengths.values())
                    # to_fit_total is our 'play room', where we can adjust widths freely.
                    to_fit_total = actual_row_width - proportional_segment_length_total if actual_row_width > proportional_segment_length_total else 0

                    # if there are non proportional inserts, adjust their segment widths to fit.
                    if non_proportional_segment_length_total > 0:
                        for c in non_proportional_segment_lengths:
                            non_proportional_segment_length = non_proportional_segment_lengths[c]
                            non_proportional_segment_lengths[c] = (non_proportional_segment_length / non_proportional_segment_length_total) * to_fit_total

                    # reassign these to the correct positions in the segment list.
                    for c in proportional_segment_lengths:
                        segment_lengths[c] = proportional_segment_lengths[c]
                    for c in non_proportional_segment_lengths:
                        segment_lengths[c] = non_proportional_segment_lengths[c]

                    # finally, make sure the segments definitely fit as a final check.
                    total_segment_length = sum(segment_lengths)
                    for c in range(len(segment_lengths)):
                        segment_length = segment_lengths[c]
                        segment_lengths[c] = (segment_length / total_segment_length) * actual_row_width

                    i=0
                    justification_nudges = 0
                    surviving_insert_ids = []
                    # go through all the inserts and justify align them
                    for insert_entry in row_insert_ids:
                        insert_props = insert_entry[1]
                        insert_width = insert_entry[2][x_index]
                        insert_height = insert_entry[2][y_index]
                        row_height = insert_entry[3]
                        main = insert_entry[0]

                        new_position = Vector(main.kitopssynth.intended_position)

                        size = main.kitopssynth.intended_size

                        insert_dimensions = main.kitopssynth.original_dimensions

                        target_width = segment_lengths[i]
                        for_deletion = False
                        if target_width == 0:
                            for_deletion = True
                        else:
                            # enlargen the insert to fill the space and then re-position.

                            # Only stretch the insert 7if we do not care about mainitaining the aspect ratio
                            if not insert_props.maintain_aspect_ratio and insert_width > 0:
                                # Apply new scale based on target width ratio.
                                if preference.rotation_respect_borders:
                                    stretch_insert_to_bounds(main, target_width, row_height, insert_width, insert_height, x_index, y_index)
                                else:
                                    setattr(main.scale, _all_axes[x_index], getattr(main.scale, _all_axes[x_index]) * (target_width / insert_width))

                                wiggle_room = 0
                            else:
                                # Ensure we are still within the bounds of the row, for now as we will overspill the row later 
                                # (this could have happened because segment variation caused overspill).
                                if insert_width > target_width:
                                    setattr(main, 'scale', getattr(main, 'scale') * (target_width / insert_width))
                                if insert_height > row_height:
                                    setattr(main, 'scale', getattr(main, 'scale') * (row_height / insert_height ))

                                wiggle_room = ((segment_lengths[i] - insert_width) / 2) * randomness_factor
                                wiggle_room = rng.uniform(-wiggle_room, wiggle_room)


                            # shift in x
                            pos_shift_local = ((target_width - insert_width)  / 2)
                            
                            pos_shift = justification_nudges + pos_shift_local + wiggle_room

                            new_position = Vector(new_position) + (left_right_vector * (pos_shift))

                            justification_nudges+=pos_shift_local * 2

                            # shift in y
                            placement = self._get_placement(preference)
                            
                            if placement == '2':
                                # already in middle - do nothing
                                pass
                            elif placement == '0':
                                #top placement
                                adjusted_insert_height = insert_dimensions[y_index] * main.scale[y_index]
                                pos_shift = (row_height - adjusted_insert_height) / 2
                                new_position = Vector(new_position) + (top_bottom_vector * (pos_shift - padding))
                            elif placement == '1':
                                #bottom placement
                                adjusted_insert_height = insert_dimensions[y_index] * main.scale[y_index]
                                pos_shift = (row_height - adjusted_insert_height) / 2
                                new_position = Vector(new_position) - (top_bottom_vector * (pos_shift - padding))

                            if not is_intersect_face_group(face_group, target_obj.matrix_world.inverted() @ new_position):
                                for_deletion = True

                        i+=1
                        
                        if not for_deletion:
                            main.location = new_position
                            surviving_insert_ids.append((main, insert_props))

                    assign_post_scale(surviving_insert_ids, layer)
                    assign_rotation(surviving_insert_ids, layer)

                    for surviving_insert_id in surviving_insert_ids:
                        insert_ids_to_return.append(surviving_insert_id[0])


        finally:
            bm.free()
            insert_frame_cache.clear()

        # if no inserts ended up being added, add some messages to suggest things to the user...
        if len(insert_ids_to_return) == 0:
            # check if 'maintain aspect ratio' selected in all cases.
            active_inserts = [i for i in preference.inserts if i.is_enabled]
            aspect_ratio_always_on = len(active_inserts) > 0
            for layer_insert_props in active_inserts:
                if layer_insert_props.is_enabled:
                    aspect_ratio_always_on &= layer_insert_props.maintain_aspect_ratio
            if aspect_ratio_always_on:
                messages.add_message(context, 'No INSERTs were added for layer \"' + preference.layer_name + '\" but the Maintain Aspect Ratio setting is on in all cases.  This might mean the INSERTs do not fit.  Check set up?')

        
        return [obj.to_object(prop, context, matrix) for obj in insert_ids_to_return]


    def draw(preference, layout):
        row = layout.row()
        row.alignment='CENTER'
        row.prop(preference,'use_boundary')
        if preference.use_boundary:
            col = layout.column()
            col.prop(preference, 'boundary_deviation', slider = False)
            col.prop(preference, 'boundary_randomness', slider = False)

        layout.separator()

        col = layout.column()
        col.prop(preference, 'rows')
        col.prop(preference, 'row_height_deviation', slider = False)
        col.prop(preference, 'row_insert_width_deviation', slider = False)
        if not preference.use_boundary:
            row = col.row()
            row.prop(preference, 'row_placement', expand = True)

        col = layout.column()
        col.label(text='Frequency')
        col.prop(preference, 'frequency', text='', slider=False)


    def encode(self, layer):
        return {
            'frequency' : layer.frequency,
            'rows' : layer.rows,
            'row_height_deviation' : layer.row_height_deviation,
            'row_insert_width_deviation' : layer.row_insert_width_deviation,
            'row_placement' : layer.row_placement,
            'use_boundary' : layer.use_boundary,
            'boundary_deviation' : layer.boundary_deviation,
            'boundary_randomness' : layer.boundary_randomness
        }

    def decode(self, parametersJSON, layer):
        layer.frequency = parametersJSON['frequency']
        layer.rows = parametersJSON['rows']
        layer.row_height_deviation = parametersJSON['row_height_deviation']
        if 'row_insert_width_deviation' in parametersJSON:
            layer.row_insert_width_deviation = parametersJSON['row_insert_width_deviation']
        if 'row_placement' in parametersJSON:
            layer.row_placement = parametersJSON['row_placement']
        layer.use_boundary = parametersJSON['use_boundary']
        layer.boundary_deviation = parametersJSON['boundary_deviation']
        layer.boundary_randomness = parametersJSON['boundary_randomness']

    def is_complex(self, layer):
        if layer.frequency > 80 and layer.rows > 8:
            for insert in layer.inserts:
                if insert.is_enabled and insert.scale < 20:
                    return True
        return False

class ColDistributor(RowDistributor, AbstractDistributor):
    """"Distribute inserts uniformly in a grid driven by a seed value."""

    def distribution_name():
        return 'Cols'

    def _get_dimension_calc(self, matrix_world, local_center, local_normal, face_group_verts, padding):
        matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding = calc_dimensions(matrix_world, local_center, local_normal, face_group_verts, padding)
        return matrix, direction, inverted_face_dim_y, inverted_face_dim_x, inverted_y_min, inverted_y_max, inverted_x_min, inverted_x_max, padding

    def _get_rows_preference(self, preference):
        return preference.cols

    def _get_rows_height_deviation_preference(self, preference):
        return preference.col_width_deviation

    def _get_row_insert_width_deviation_preference(self, preference):
        """Get the preference for the row height deviation."""
        return preference.col_insert_height_deviation

    def _get_dimension_x_index(self):
        return 1

    def _get_dimension_y_index(self):
        return 0

    def _calc_position(self, preference, matrix, inverted_row_x_pos, inverted_insert_width, inverted_row_y_pos):
        return matrix @ (Vector((inverted_row_y_pos, 
                                inverted_row_x_pos  + (inverted_insert_width / 2), 
                                preference.z_position)))

    def _get_actual_row_width(context, matrix, inverted_row_width):
        return (matrix @ Vector((0, 0, 0)) - matrix @ Vector((0, inverted_row_width, 0))).magnitude

    def _get_actual_row_height(context, matrix, inverted_row_height):
        return (matrix @ Vector((0, 0,  0)) - matrix @ Vector((inverted_row_height, 0, 0))).magnitude

    def _get_left_right_vector(self, matrix):
        return (matrix @ Vector((0, 1, 0)) - matrix @ Vector((0, 0, 0))).normalized()

    def _get_top_bottom_vector(self, matrix):
        return (matrix @ Vector((1, 0, 0)) - matrix @ Vector((0, 0, 0))).normalized()

    def _get_size(self, size_x, size_y):
        size = Vector((1,1,1))
        size.x = size_y
        size.y = size_x 
        return size

    def _get_placement(self, preference):
        """Return placement settings"""
        return preference.col_placement

    def draw(preference, layout):
        row = layout.row()
        row.alignment='CENTER'
        row.prop(preference,'use_boundary')
        if preference.use_boundary:
            col = layout.column()
            col.prop(preference, 'boundary_deviation', slider = False)
            col.prop(preference, 'boundary_randomness', slider = False)

        layout.separator()

        col = layout.column()
        col.prop(preference, 'cols')
        col.prop(preference, 'col_width_deviation', slider = False)
        col.prop(preference, 'col_insert_height_deviation', slider = False)
        if not preference.use_boundary:
            row = col.row()
            row.prop(preference, 'col_placement', expand = True)

        col = layout.column()
        col.label(text='Frequency')
        col.prop(preference, 'frequency', text='', slider=False)

    def encode(self, layer):
        return {
            'frequency' : layer.frequency,
            'cols' : layer.cols,
            'col_width_deviation' : layer.col_width_deviation,
            'col_insert_height_deviation' : layer.col_insert_height_deviation,
            'col_placement' : layer.col_placement,
            'use_boundary' : layer.use_boundary,
            'boundary_deviation' : layer.boundary_deviation,
            'boundary_randomness' : layer.boundary_randomness
        }

    def decode(self, parametersJSON, layer):
        layer.frequency = parametersJSON['frequency']
        layer.cols = parametersJSON['cols']
        layer.col_width_deviation = parametersJSON['col_width_deviation']
        if 'col_insert_height_deviation' in parametersJSON:
            layer.col_insert_height_deviation = parametersJSON['col_insert_height_deviation']
        if 'col_placement' in parametersJSON:
            layer.col_placement = parametersJSON['col_placement']
        layer.use_boundary = parametersJSON['use_boundary']
        layer.boundary_deviation = parametersJSON['boundary_deviation']
        layer.boundary_randomness = parametersJSON['boundary_randomness']

    def is_complex(self, layer):
        if layer.frequency > 80 and layer.cols > 8:
            for insert in layer.inserts:
                if insert.is_enabled and insert.scale < 20:
                    return True
        return False
    

def stretch_insert(dim, main, length, padding):
    # stretch the insert if we need to, keep center aligned (the default)
    scale = getattr(main.scale, dim)
    original_dimensions = main.kitopssynth.original_dimensions

    # this is the current size without padding.
    dim_n = scale * original_dimensions[_all_axes.index(dim)]
    # with padding.
    dim_n_padding = dim_n + padding

    # Apply new scale based on target height ratio... TODO when maintain aspect ratio is checked this will be an optional setting.
    setattr(main.scale, dim, getattr(main.scale, dim) * (length/ dim_n_padding))

class GridDistributor(AbstractDistributor):
    """"Distribute inserts uniformly in a grid driven by a seed value."""

    def distribution_name():
        return 'Grid'

    def distribute(self, prop, context, layer): 

        preference = layer

        rng = randomness.random_generator(context, layer)

        target_obj = context.scene.kitopssynth_target_obj

        insert_frame_cache = inserts.InsertFrameCache(prop, context, layer, target_obj)

        insert_ids_to_return = []
        matrix = None

        # Use a bmesh object temporarily create  points can be taken from it easily
        bm = bmesh.new()
        bm_grids = bmesh.new()
        size_x_prop = bm_grids.verts.layers.float.new('size_x_prop')
        size_y_prop = bm_grids.verts.layers.float.new('size_y_prop')
        try:
            me = target_obj.data
            bm.from_mesh(me)

            local_center = None
            local_normal = None
            face_groups = find_face_groups(bm)
            insert_name_ignore_list = []
            for face_group in face_groups:
                local_center = calc_face_group_center(face_group)
                local_normal = calc_face_group_normal(face_group)

                face_group_verts = []
                for f in face_group:
                    face_group_verts.extend(f.verts)

                face_group_verts = list(set(face_group_verts))

                matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding = calc_dimensions(target_obj.matrix_world, local_center, local_normal, face_group_verts, preference.padding)

                row_height_proportions = get_proportions(rng, preference.grid_rows, preference.grid_row_height_deviation, inverted_face_dim_y)
                col_width_proportions = get_proportions(rng, preference.grid_cols, preference.grid_col_width_deviation, inverted_face_dim_x)

                # # create the grid by selecting every odd position on the generated grid.
                new_verts = []

                x_intervals = []
                total_interval_pos = inverted_x_min
                for i in range(0, preference.grid_cols):
                    interval_pos = total_interval_pos + (col_width_proportions[i] / 2)
                    x_intervals.append(interval_pos)
                    total_interval_pos+=col_width_proportions[i]

                y_intervals = []
                total_interval_pos = inverted_y_min
                for i in range(0, preference.grid_rows):
                    interval_pos = total_interval_pos + (row_height_proportions[i] / 2)
                    y_intervals.append(interval_pos)
                    total_interval_pos+=row_height_proportions[i]

                i = 0
                x_index = 0
                for x_interval in x_intervals:
                    col_width_proportion = col_width_proportions[x_index]
                    y_index = 0
                    for y_interval in y_intervals:
                        row_height_proportion = row_height_proportions[y_index]

                        v = bm_grids.verts.new(matrix @ Vector((x_interval, y_interval, preference.z_position)))
                        new_verts.append(v)
                        v.normal = direction
                        v.index = i

                        v[size_x_prop] = col_width_proportion
                        v[size_y_prop] = row_height_proportion

                        i+=1
                        y_index+=1
                    x_index+=1

                # determine the number of points we actially need based on the frequency.
                no_grid_points = len(new_verts)
                frequency = preference.frequency if preference.frequency <= 100 else 100
                no_points_to_get = round(no_grid_points * frequency * 0.01)
                for i in range(0, no_points_to_get):
                    # get a point randomly. 
                    v = rng.choice(new_verts)
                    co = v.co                                       
                    if not v.is_boundary:

                        insert_found = False
                        local_insert_name_ignore_list = []
                        while not insert_found:

                            insert_obj, insert_props = inserts.add_random_insert(prop, context, layer, layer.inserts, insert_frame_cache, rng, insert_name_ignore_list + local_insert_name_ignore_list)
                            if insert_obj is None:
                                insert_found = False
                                break # exit out of everything

                            # if the scale is zero, move along.
                            if insert_props.scale == 0:
                                insert_name_ignore_list.append(insert_props.insert_name)
                                continue

                            set_up_insert(insert_obj, preference, matrix, rng)
                            insert_dimensions = insert_obj.kitopssynth.original_dimensions

                            # before we go any further, check whether the INSERT has to be scaled to fit.
                            shrink_required = False
                            if insert_props.do_not_scale:
                                size = Vector((1,1,1))
                                size.x = insert_dimensions[0]
                                size.y = insert_dimensions[1]
                                shrink_required = (insert_dimensions[0] > v[size_x_prop]) or (insert_dimensions[1] > v[size_y_prop])
                            else:
                                # set intended size for insert
                                size = Vector((1,1,1))
                                size.x = v[size_x_prop]
                                size.y = v[size_y_prop]

                            if insert_props.do_not_scale and shrink_required:
                                insert_found = False
                                local_insert_name_ignore_list.append(insert_props.insert_name)
                            else:
                                insert_found = True

                        if not insert_found:
                            break
                            

                        position = co
                        insert_obj.location = position
                        insert_obj.kitopssynth.intended_position = position

                        left_right_vector = (matrix @ Vector((1, 0, 0)) - 
                                        matrix @ Vector((0, 0, 0))).normalized()
                        
                        top_bottom_vector = (matrix @ Vector((0, 1, 0)) - 
                                        matrix @ Vector((0, 0, 0))).normalized()

                        scale_multiplier = 1
                        if abs(insert_props.scale) <= 100:
                            scale_multiplier = insert_props.scale * 0.01

                        insert_obj.kitopssynth.intended_size = size

                        assign_pre_scale([(insert_obj, insert_props)], layer, padding, scale_multiplier)

                        square_width = v[size_x_prop]
                        square_height = v[size_y_prop]                    
                        new_position = Vector(insert_obj.kitopssynth.intended_position)

                        # stretch the insert if it does not have aspect ratio...
                        if not insert_props.maintain_aspect_ratio:
                            if preference.rotation_respect_borders:
                                rotation = insert_obj.kitopssynth.intended_rotation
                                abs_sin = abs(sin(rotation))

                                width = square_width
                                height = square_height

                                bound_w = height * abs_sin + width * (1 - abs_sin)
                                bound_h = width * abs_sin + height * (1 - abs_sin)

                                stretch_insert('x', insert_obj, bound_w, padding)
                                stretch_insert('y', insert_obj, bound_h, padding)
                            else:
                                stretch_insert('x', insert_obj, square_width, padding)
                                stretch_insert('y', insert_obj, square_height, padding)
                        else:
                            col_placement = preference.grid_col_placement
                            row_placement = preference.grid_row_placement


                            original_dimensions = insert_obj.kitopssynth.original_dimensions

                            if col_placement == '2':
                                pass
                            elif col_placement == '1':
                                # left placement
                                scale_x = getattr(insert_obj.scale, 'x')
                                dim_x = scale_x * original_dimensions[0]
                                new_position = Vector(new_position) + (left_right_vector * ((square_width - dim_x ) / 2) * -1)

                            elif col_placement == '0':
                                # right placement
                                scale_x = getattr(insert_obj.scale, 'x')
                                dim_x = scale_x * original_dimensions[0]
                                new_position = Vector(new_position) + (left_right_vector * ((square_width - dim_x ) / 2))

                            if row_placement == '2':
                                pass
                            elif row_placement == '1':
                                # bottom placement
                                scale_y = getattr(insert_obj.scale, 'y')
                                original_dimensions = insert_obj.kitopssynth.original_dimensions
                                dim_y = scale_y * original_dimensions[1]
                                new_position = Vector(new_position) + (top_bottom_vector * ((square_height - dim_y ) / 2) * -1)
                            elif row_placement == '0':
                                # top placement
                                scale_y = getattr(insert_obj.scale, 'y')
                                original_dimensions = insert_obj.kitopssynth.original_dimensions
                                dim_y = scale_y * original_dimensions[1]
                                new_position = Vector(new_position) + (top_bottom_vector * ((square_height - dim_y ) / 2))


                        if is_intersect_face_group(face_group, target_obj.matrix_world.inverted() @ new_position):
                            insert_obj.location = new_position
                            assign_post_scale([(insert_obj, insert_props)], layer)
                            assign_rotation([(insert_obj, insert_props)], layer)
                            insert_ids_to_return.append(insert_obj)

                            if insert_props.use_once:
                                insert_name_ignore_list.append(insert_props.insert_name)

                    # remove point from list so we don't get it again.
                    new_verts.remove(v)

                bmesh.ops.delete(bm_grids, geom=new_verts)

        finally:
            bm.free()
            bm_grids.free()
            insert_frame_cache.clear()

        return [obj.to_object(prop, context, matrix) for obj in insert_ids_to_return]


    def draw(preference, layout):
        col = layout.column()
        col.prop(preference, 'grid_rows', text='Rows')
        col.prop(preference, 'grid_row_height_deviation', slider = False)
        
        col.separator()
        col.prop(preference, 'grid_cols', text='Cols')
        col.prop(preference, 'grid_col_width_deviation', slider = False)

        col.separator()

        row = col.row()
        row.prop(preference, 'grid_col_placement', expand=True)
        row = col.row()
        row.prop(preference, 'grid_row_placement', expand=True)

        col = layout.column()
        col.label(text='Frequency')
        col.prop(preference, 'frequency', text='', slider=False)

    def encode(self, layer):
        return {
            'frequency' : layer.frequency,
            'rows' : layer.grid_rows,
            'row_height_deviation' : layer.grid_row_height_deviation,
            'cols' : layer.grid_cols,
            'col_width_deviation' : layer.grid_col_width_deviation,
            'grid_col_placement' : layer.grid_col_placement,
            'grid_row_placement' : layer.grid_row_placement,
        }

    def decode(self, parametersJSON, layer):
        layer.frequency = parametersJSON['frequency']
        layer.grid_rows = parametersJSON['rows']
        layer.grid_row_height_deviation = parametersJSON['row_height_deviation']
        layer.grid_cols = parametersJSON['cols']
        layer.grid_col_width_deviation = parametersJSON['col_width_deviation']
        if 'grid_col_placement' in parametersJSON:
            layer.grid_col_placement = parametersJSON['grid_col_placement']
        if 'grid_row_placement' in parametersJSON:
            layer.grid_row_placement = parametersJSON['grid_row_placement']

    def is_complex(self, layer):
        return  layer.frequency > 80 and \
                (layer.grid_rows > 8 or layer.grid_cols > 8)

class EdgeDistributor(AbstractDistributor):
    """"Distribute inserts uniformly in a grid driven by a seed value."""

    def distribution_name():
        return 'Edge'

    def distribute(self, prop, context, layer): 

        preference = layer

        rng = randomness.random_generator(context, layer)

        target_obj = context.scene.kitopssynth_target_obj

        insert_frame_cache = inserts.InsertFrameCache(prop, context, layer, target_obj)

        insert_ids_to_return = []
        matrix = None

        # Use a bmesh object temporarily create  points can be taken from it easily
        bm = bmesh.new()
        try:
            me = target_obj.data
            bm.from_mesh(me)

            # gather up groups of selected faces, inset if necessary according to offset, and then traverse each loop of edges and place INSERTs randomly.
            bmesh.ops.delete(bm, geom = [f for f in bm.faces if not f.select], context="FACES")

            connected_face_groups = find_face_groups(bm)

            face_groups = []
            for connected_face_group in connected_face_groups:
                result = bmesh.ops.split(bm, geom=connected_face_group)
                face_group = []
                for f in result['geom']:
                    if isinstance(f, bmesh.types.BMFace):
                        face_group.append(f)
                face_group = sorted(face_group, key=lambda k: k.index) 
                face_groups.append(face_group)

            insert_name_ignore_list = []
            for face_group in face_groups:
                local_center = calc_face_group_center(face_group)
                local_normal = calc_face_group_normal(face_group)

                if preference.edge_boundary_deviation != 0:
                    result = bmesh.ops.inset_region(bm, faces=face_group, thickness=preference.edge_boundary_deviation, use_even_offset=True, use_boundary=True)
                    bmesh.ops.delete(bm, geom = result['faces'], context="FACES")

                # delete everything but the edge boundaries
                face_group_edges = []
                for f in face_group:
                    if f.is_valid:
                        face_group_edges.extend(f.edges)

                face_group_edges = list(set(face_group_edges))

                non_edge_boundaries = [e for e in face_group_edges if e.is_boundary == False]
                bmesh.ops.delete(bm, geom = non_edge_boundaries, context="EDGES_FACES")

                for e in face_group_edges:
                    if e.is_valid:
                        e.tag = False
                        e.select=True
                edges = [e for e in face_group_edges if e.is_valid]
                edge_groups = find_edge_groups(edges)

                for edge_group in edge_groups:
                    
                    for e in edge_group:
                        e.tag = False
                        e.select = True

                # now we have the groups of edges, each (hopefully!) forming a loop
                for edge_group in edge_groups:
                    if len(edge_group) == 0:
                        continue

                    edge_group_verts = []
                    for e in edge_group:
                        edge_group_verts.extend(e.verts)

                    edge_group_verts = list(set(edge_group_verts))

                    # get the inverted coordinates of the flattened face area to go around in...maybe we don't need this?
                    matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding_redundant = calc_dimensions(target_obj.matrix_world, local_center, local_normal, edge_group_verts, preference.padding)

                    # order the edge group to attempt to get a similar pattern every time.
                    matrix_inverted = matrix.inverted()

                    def sort_edge(k):
                        av_point = (matrix_inverted @ ((k.verts[0].co  + k.verts[1].co) * 0.5)   ) 
                        return  (av_point[0], av_point[1], av_point[2])
                    edge_group.sort(key=sort_edge  ) 
                    
                    first_vert = None
                    current_edge = edge_group[0]
                    verts = current_edge.verts
                    verts = sorted(verts, key=lambda k: (k.co.x, k.co.y, k.co.z)) 
                    current_vert = verts[0]
                    ordered_edge_tuples = []
                    while(current_vert != first_vert):
                        
                        first_vert = verts[0]
                        next_vert = current_edge.other_vert(current_vert)

                        ordered_edge_tuples.append((current_edge, current_vert, next_vert))

                        potential_next_edges = [e for e in next_vert.link_edges if e != current_edge]
                        if len(potential_next_edges) == 0:
                            break
                        next_edge =  potential_next_edges[0]

                        current_edge = next_edge
                        current_vert = next_vert


                    total_edges_length = 0
                    for e in edge_group:
                        total_edges_length += e.calc_length()

                    

                    total_edges_length_cut = total_edges_length * preference.frequency * 0.01
                    current_length_so_far = 0
                    insert_ids = []
                    total_inserts_width = 0
                    while current_length_so_far <= total_edges_length_cut:
                        # create an insert.

                        insert_obj, insert_props = inserts.add_random_insert(prop, context, layer, layer.inserts, insert_frame_cache, rng, insert_name_ignore_list)
                        if insert_obj is None:
                            break # exit out of everything because we could not randomly retrieve an insert.


                        # if the scale is zero, move along.
                        if insert_props.scale == 0:
                            insert_name_ignore_list.append(insert_props.insert_name)
                            continue
                        
                        set_up_insert(insert_obj, preference, matrix, rng)
                        insert_dimensions = insert_obj.kitopssynth.original_dimensions

                        if insert_props.do_not_scale:
                            size = Vector((1,1,1))
                            size.x = insert_dimensions[0]
                            size.y = insert_dimensions[1]
                        else:
                            # scale the bounds if necessary.
                            scale_multiplier = 1
                            if abs(insert_props.scale) <= 100:
                                scale_multiplier = insert_props.scale * 0.01                            
                            size = Vector((1,1,1))
                            size.x = insert_dimensions[0] * scale_multiplier
                            size.y = insert_dimensions[1] * scale_multiplier
                        
                        insert_obj.kitopssynth.intended_size = size
                        padding = size.x * preference.padding * 0.01
                        assign_pre_scale([(insert_obj, insert_props)], layer, padding)

                        insert_width = size.x if size.x >= size.y else size.y 
                        insert_height = size.y if size.y >= size.x else size.x 
                        current_length_so_far += insert_width
                        
                        if current_length_so_far < total_edges_length_cut:

                            total_inserts_width+=insert_width
                            
                            insert_ids.append((insert_obj, insert_props, insert_width, insert_height))

                            if insert_props.use_once:
                                insert_name_ignore_list.append(insert_props.insert_name)

                        else:
                            break
                    
                    if (len(insert_ids) == 0):
                        break

                    # shuffle the inserts to ensure randomness.
                    rng.shuffle(insert_ids)

                    # now, find points distributed along the edge loop.
                    segment_lengths = []
                    # get a set of random proportions to assign.
                    proportion_list = get_proportion_list(len(insert_ids), rng, preference.edge_randomness)
                    # The remaining width will be used to calculate the distribution of the points.
                    remaining_width = total_edges_length - total_inserts_width
                    total_segment_lengths = 0

                    for i in range(len(insert_ids)):
                        proportion = proportion_list[i]
                        insert_props = insert_ids[i][1]
                        insert_width = insert_ids[i][2]
                        insert_height= insert_ids[i][3]
                        insert_obj = insert_ids[i][0]

                        segment_length = insert_width + (remaining_width * proportion)

                        wiggle_room = ((segment_length - insert_width) / 2) * preference.edge_randomness
                        wiggle_room = rng.uniform(-wiggle_room, wiggle_room)
                        point_on_edges, current_edge = get_edge_position(total_segment_lengths + (segment_length / 2) + wiggle_room, ordered_edge_tuples)

                        continue_to_add = False
                        if preference.edge_limit_mode == 'NONE':
                            continue_to_add = True
                        elif preference.edge_limit_mode == 'X' or preference.edge_limit_mode == 'Y':
                            current_edge_vec1 = ((matrix.inverted() @ current_edge.verts[1].co) - (matrix.inverted() @ current_edge.verts[0].co)).normalized()
                            current_edge_vec2 = ((matrix.inverted() @ current_edge.verts[0].co) - (matrix.inverted() @ current_edge.verts[1].co)).normalized()
                            
                            direction = Vector((1,0,0)) if preference.edge_limit_mode == 'X' else Vector((0,1,0))
                            angle1 = degrees(direction.angle(current_edge_vec1))
                            angle2 = degrees(direction.angle(current_edge_vec2))
                            if angle1 < 45 or angle2 < 45:
                                continue_to_add = True

                        total_segment_lengths += segment_length

                        if continue_to_add:

                            insert_ids_to_return.append(insert_obj)
                            point_on_edges += (local_normal * preference.z_position)

                            insert_obj.location = target_obj.matrix_world @ point_on_edges

                            

                            assign_post_scale([(insert_obj, insert_props)], layer)
                            assign_rotation([(insert_obj, insert_props)], layer)

                            # Only stretch the insert if we do not care about mainitaining the aspect ratio
                            if not insert_props.maintain_aspect_ratio:
                                # Apply new scale based on target width ratio...
                                if preference.rotation_respect_borders:
                                    rotation = insert_obj.kitopssynth.intended_rotation
                                    abs_sin = abs(sin(rotation))
                                    
                                    width = insert_width
                                    height = insert_height

                                    bound_w = height * abs_sin + width * (1 - abs_sin)
                                    bound_h = width * abs_sin + height * (1 - abs_sin)

                                    stretch_insert('x', insert_obj, bound_w, padding)
                                    stretch_insert('y', insert_obj, bound_h, padding)
                                else:
                                    # this is the current size without padding.
                                    if insert_width > 0:
                                        setattr(insert_obj.scale, 'x', getattr(insert_obj.scale, 'x') * (segment_length / insert_width))
                                    if insert_height > 0:
                                        setattr(insert_obj.scale, 'y', getattr(insert_obj.scale, 'y') * (segment_length / insert_height))



        finally:
            bm.free()
            insert_frame_cache.clear()
        
        return [obj.to_object(prop, context, matrix) for obj in insert_ids_to_return]

    def draw(preference, layout):
        col = layout.column()
        col.prop(preference, 'edge_boundary_deviation', slider = False)
        col.prop(preference, 'edge_randomness', slider = False)

        col = layout.column()
        col.label(text='Frequency')
        col.prop(preference, 'frequency', text='', slider=False)

        col = layout.column()
        col.label(text='Limit By')
        row = col.row()
        row.prop(preference, 'edge_limit_mode', expand=True)

    def encode(self, layer):
        return {
            'frequency' : layer.frequency,
            'edge_boundary_deviation' : layer.edge_boundary_deviation,
            'edge_randomness' : layer.edge_randomness,
            'edge_limit_mode' : layer.edge_limit_mode
        }

    def decode(self, parametersJSON, layer):
        layer.frequency = parametersJSON['frequency']
        layer.edge_boundary_deviation = parametersJSON['edge_boundary_deviation']
        layer.edge_randomness = parametersJSON['edge_randomness']
        layer.edge_limit_mode = parametersJSON['edge_limit_mode'] if 'edge_limit_mode' in parametersJSON else 'NONE'

    def is_complex(self, layer):
        if layer.frequency > 80:
            for insert in layer.inserts:
                if insert.is_enabled and insert.scale < 20:
                    return True

        return False


class RandomDistributor(AbstractDistributor):
    """"Distribute inserts randomly in a grid driven by a seed value."""

    def distribution_name():
        return 'Random'

    def distribute(self, prop, context, layer): 

        preference = layer

        rng = randomness.random_generator(context, layer)

        target_obj = context.scene.kitopssynth_target_obj

        insert_frame_cache = inserts.InsertFrameCache(prop, context, layer, target_obj)

        insert_ids_to_return = []
        matrix = None

        # Use a bmesh object temporarily create  points can be taken from it easily
        bm = bmesh.new()

        try:
            me = target_obj.data
            bm.from_mesh(me)

            # collate a set of random points.
            num_points = preference.random_amount

            # triangulate to easily get points
            result = bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if f.select], quad_method='FIXED', ngon_method='EAR_CLIP')

            result_faces = result['faces']

            if len(result_faces) == 0:
                return

            insert_name_ignore_list = []
            for i in range(0, num_points):
                # randomly get a face and then a point on that face.
                random_face_index = rng.choice(range(0, len(result_faces)))
                random_face = result_faces[random_face_index]
                if len(random_face.verts) >= 3:
                    verts = random_face.verts
                    random_point = randomness.point_on_triangle(verts[0].co, verts[1].co, verts[2].co, rng)

                    matrix, direction, inverted_face_dim_x, inverted_face_dim_y, inverted_x_min, inverted_x_max, inverted_y_min, inverted_y_max, padding_redundant = calc_dimensions(target_obj.matrix_world, random_face.calc_center_median(), random_face.normal, random_face.verts, preference.padding)

                    # place the insert.
                    insert_obj, insert_props = inserts.add_random_insert(prop, context, layer, layer.inserts, insert_frame_cache, rng, insert_name_ignore_list)
                    if insert_obj is None:
                        break # exit out of everything because we could not randomly retrieve an insert.


                    # if the scale is zero, move along.
                    if insert_props.scale == 0:
                        insert_name_ignore_list.append(insert_props.insert_name)
                        continue

                    set_up_insert(insert_obj, preference, matrix, rng)
                    insert_dimensions = insert_obj.kitopssynth.original_dimensions
                    
                    if insert_props.do_not_scale:
                        size = Vector((1,1,1))
                        size.x = insert_dimensions[0]
                        size.y = insert_dimensions[1]
                    else:
                        # scale the bounds if necessary.
                        scale_multiplier = 1
                        if abs(insert_props.scale) <= 100:
                            scale_multiplier = insert_props.scale * 0.01
                        size = Vector((1,1,1))
                        size.x = insert_dimensions[0] * scale_multiplier
                        size.y = insert_dimensions[1] * scale_multiplier
                    
                    insert_obj.kitopssynth.intended_size = size

                    padding = size.x * preference.padding * 0.01
                    assign_pre_scale([(insert_obj, insert_props)], layer, padding)

                    insert_obj.location = (target_obj.matrix_world @ random_point) + ((random_face.normal * preference.z_position))

                    assign_post_scale([(insert_obj, insert_props)], layer)
                    assign_rotation([(insert_obj, insert_props)], layer)

                    insert_ids_to_return.append(insert_obj)

                    if insert_props.use_once:
                        insert_name_ignore_list.append(insert_props.insert_name)

        finally:
            bm.free()
            insert_frame_cache.clear()

        return [obj.to_object(prop, context, matrix) for obj in insert_ids_to_return]


    def draw(preference, layout):
        col = layout.column()
        col.label(text='Amount')
        col.prop(preference, 'random_amount', slider = False)

    
    def encode(self, layer):
        return {
            'random_amount' : layer.random_amount
        }

    def decode(self, parametersJSON, layer):
        layer.random_amount = parametersJSON['random_amount']

    def is_complex(self, layer):
        if layer.random_amount > 50:
            return True
        return False

def is_complex(context):
    # check whether we need to check...
    addon_preference = addon.preference()
    if not addon_preference.check_for_complexity:
        return False

    for layer in context.scene.kitopssynth.layers:
        # general check - check for any general parameters here.

        #distributor check - check any potential problems here...
        distribution_class_name = layer.distribution
        module = importlib.import_module(__name__)

        distributor = getattr(module, distribution_class_name)()
        if layer.is_enabled and distributor.is_complex(layer):
            return True
    
    return False


def get_distribution_method_items():
    """Get all distribution items"""
    items = []
    i = 0
    for subclass in AbstractDistributor.__subclasses__():
        items.append((subclass.__name__, subclass.distribution_name(),''))
        i+=1
    return items

distribution_method_items  = get_distribution_method_items()