# Class for defining kit ops synth specific objects.
import bpy
import bmesh
from math import radians
from bpy.types import PropertyGroup, EnumProperty
from bpy.props import *
from bpy.utils import register_class, unregister_class
from kitops.addon.utility import insert
from kitops.addon.utility import update as kitops_update
from kitops.addon.utility import addon as kitops_addon
from . utility import addon, update, distributors
import hashlib


def generate_insert_map_key(obj, face_id_list=None):
    """Returns a key for managing a selection set of INSERTs"""
    if face_id_list is None:
        face_id_list = generate_face_id_list(obj)
    key = '-'.join(map(str, face_id_list))
    return key

def generate_face_id_list(obj):
    """Returns selected face ids on object"""
    bm = bmesh.new()
    if obj.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(obj.data)
    elif obj.mode == 'OBJECT':
        bm.from_mesh(obj.data)


    face_id_list = []
    for f in bm.faces:
        if f.select:
            face_id_list.append(f.index)
    face_id_list.sort()
    if obj.mode != 'EDIT':
        bm.free()
    return face_id_list


class synth_face_ref(PropertyGroup):
    face_id : IntProperty(default=-1)

class synth_layer_face_map(PropertyGroup):
    face_ids: CollectionProperty(type=synth_face_ref)

class synth_object_ref(PropertyGroup):
    insert_obj :  PointerProperty(type=bpy.types.Object)

class synth_layer_ref(PropertyGroup):
    inserts: CollectionProperty(type=synth_object_ref)

class synth_insert_map(PropertyGroup):
    layers: CollectionProperty(type=synth_layer_ref)

class kitops_placement(PropertyGroup):
    direction : FloatVectorProperty()
    position : FloatVectorProperty()
    size: FloatVectorProperty()

def _convert_to_number(string):
    '''Attempt to create a unique integer for a string.  Cannot guarantee complete uniqueness'''
    return int(str(int(hashlib.md5(string.encode('utf-8')).hexdigest(), 16))[0:7]) # This is 7 because enums seem to error above this value

kitops_enum_cats = []
def get_kitops_categories(self, context):
    global kitops_enum_cats
    kitops_enum_cats = []
    option = addon.option()

    if len(option.kpack.categories):
        for index, category in enumerate(option.kpack.categories):
            if not option.filter or option.kpack.active_index == index or re.search(option.filter, category.name, re.I):
                number = _convert_to_number(category.name)
                kitops_enum_cats.append((category.name, category.name, '', category.blends[category.active_index].icon_id, number))

    return kitops_enum_cats

kitops_enum_items = []
def get_kitops_items(self, context):
    global kitops_enum_items
    kitops_enum_items = []
    option = addon.option()
    for index, category in enumerate(option.kpack.categories):
        if category.name == self.category:
            if index < len(option.kpack.categories):
                category = option.kpack.categories[index]
                if getattr(category, 'folder', None ) is not None and category.folder in insert.thumbnails:
                    image_items = insert.thumbnails[category.folder].images[:]
                    # Change the index to an generated number from the image name...
                    for i in range(len(image_items)):
                        image_item = image_items[i]
                        number = _convert_to_number(image_item[0])
                        image_items[i] = (image_item[0], image_item[1], image_item[2], image_item[3], number)
                    kitops_enum_items.extend(image_items)
                    break

    return kitops_enum_items

def inserts_redo_all(self, context):
    """Run redo"""
    if update.poll_add_random_inserts(context) and self.auto_update:
        bpy.ops.ko.synth_add_random_inserts('INVOKE_DEFAULT', layer_id='')

    return None

def inserts_redo(self, context, layer=None):
    """Run redo"""
    if update.poll_add_random_inserts(context):
        if layer == None:
            bpy.ops.ko.synth_add_random_inserts('INVOKE_DEFAULT', layer_id='')
        else:
            old_active = context.active_object
            bpy.ops.ko.synth_clear_layer('INVOKE_DEFAULT', layer_id = layer.name)
            if layer.is_enabled:
                bpy.ops.ko.synth_add_random_inserts('INVOKE_DEFAULT', layer_id=layer.name)
            context.view_layer.objects.active = old_active

    return None

def reload_kpacks(context):
    kitops_update.kpack(None, context)

def inserts_redo_update(self, context):
    """Run redo only if auto update is on"""
    preference = context.scene.kitopssynth
    if preference.auto_update:
        inserts_redo(self, context)
    return None

def switch_categories(self, context):
    self.error_message = ''
    # kitops_update.kpack(None, context) TODO consider introducing this if there are issues with reloading KPACKS
    option = addon.option()
    for index, category in enumerate(option.kpack.categories):
        if category.name == self.category:
            if index < len(option.kpack.categories):
                category = option.kpack.categories[index]
                if category.folder in insert.thumbnails:
                    self.insert_name = insert.thumbnails[category.folder].images[0][0]
                return None
    return None

class kitops_synth_insert_entry(PropertyGroup):

    is_expanded : BoolProperty(default=False)

    is_enabled : BoolProperty(default=False, update=inserts_redo_update, name='Enable', description='Enable INSERT')

    category : EnumProperty(items=get_kitops_categories, update=switch_categories)#, default=0, update=switch_categories)

    insert_name: EnumProperty(items=get_kitops_items, update=inserts_redo_update)#, default=0, update=switch_thumbnail)

    proportionality : FloatProperty(
            name='Cover',
            description='Amount of INSERTs to place on the pattern',
            min=0,
            max=100,
            default=100,
            precision=0,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    scale : FloatProperty(
            name='Scale',
            description='Scale of INSERT',
            soft_min=0,
            soft_max=100,
            default=100,
            precision=0,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    use_once : BoolProperty(
        name = 'Use Once',
        description = 'Only use this INSERT at most once in the layout',
        default = False,
        update=inserts_redo_update
        )

    do_not_scale : BoolProperty(
        name = 'Don\'t Scale',
        description = 'The insert should not be scaled. If it doesn\'t fit, then don\'t use it',
        default = False,
        update=inserts_redo_update
        )

    maintain_aspect_ratio: BoolProperty(
        name = 'Maintain Aspect Ratio',
        description = 'Maintain the aspect ratio of the insert',
        default = True,
        update=inserts_redo_update
        )

    def clear_error(self, context):
        if self.clear_error_message == True:
            self.error_message = ''
            self.clear_error_message = False

    error_message : StringProperty(default='')
    clear_error_message : BoolProperty(default=False, update=clear_error)



class kitops_synth_layer(PropertyGroup):

    index : IntProperty(default=0)

    layer_name : StringProperty(default="Untitled")

    is_enabled : BoolProperty(default=True, name='Enable', description='Enable Layer')

    inserts : CollectionProperty(name='KIT OPS SYNTH Objects', type=kitops_synth_insert_entry)

    thumbnail_labels: BoolProperty(
        name = 'Thumbnail labels',
        description = 'Displays names of INSERTs under the thumbnails in the preview popup',
        default = True)

    frequency : FloatProperty(
            name='Frequency',
            description='Amount of INSERTs to place on the pattern',
            min=0,
            soft_max=100,
            default=100,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    distribution : EnumProperty(items= distributors.distribution_method_items,
                                                    name = "Distribution Type", update=inserts_redo_update)

    seed : IntProperty(
            name='Random Seed',
            description='Seed Value for generating and placing INSERTs',
            min=0,
            default=0,
            update=inserts_redo_update
            )

    rows : IntProperty(
            name='Rows',
            description='Number of rows',
            min=1,
            soft_max=10,
            default=3,
            update=inserts_redo_update
            )

    cols : IntProperty(
            name='Cols',
            description='Number of columns',
            min=1,
            soft_max=10,
            default=3,
            update=inserts_redo_update
            )

    row_placement : bpy.props.EnumProperty(items= (      ('0', 'Top', ''),
                                                         ('2', 'Middle', ''),
                                                         ('1', 'Bottom', ''),
                                                         ),
                                                         name = "Placement", default='2',
                                                        update=inserts_redo_update)


    col_placement : bpy.props.EnumProperty(items= (      ('1', 'Left', ''),
                                                         ('2', 'Center', ''),
                                                         ('0', 'Right', ''),
                                                         ),
                                                         name = "Placement", default='2',
                                                        update=inserts_redo_update)

    grid_rows : IntProperty(
            name='Rows',
            description='Number of rows',
            min=1,
            soft_max=10,
            default=1,
            update=inserts_redo_update
            )

    grid_cols : IntProperty(
            name='Cols',
            description='Number of columns',
            min=1,
            soft_max=10,
            default=1,
            update=inserts_redo_update
            )

    grid_row_placement : bpy.props.EnumProperty(items= (      ('0', 'Top', ''),
                                                         ('2', 'Middle', ''),
                                                         ('1', 'Bottom', ''),
                                                         ),
                                                         name = "Placement", default='2',
                                                        update=inserts_redo_update)

    grid_col_placement : bpy.props.EnumProperty(items= (      ('1', 'Left', ''),
                                                         ('2', 'Center', ''),
                                                         ('0', 'Right', ''),
                                                         ),
                                                         name = "Placement", default='2',
                                                        update=inserts_redo_update)

    edge_randomness : FloatProperty(
            name='Randomness',
            description='Amount of randomness to introduce into the placements',
            min=0,
            max=1,
            default=1,
            precision=3,
            step=1,
            update=inserts_redo_update
            )

    use_boundary : BoolProperty(
        name = 'Use Boundary',
        description = 'Fill Boundaries with INSERTs',
        default = False,
        update=inserts_redo_update)


    boundary_deviation : FloatProperty(
            name='Offset',
            description='Offset of boundary',
            soft_min=-100,
            soft_max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    edge_boundary_deviation : FloatProperty(
            name='Offset',
            description='Offset of boundary',
            soft_min=-10,
            soft_max=10,
            default=0,
            precision=3,
            step=1,
            update=inserts_redo_update
            )

    edge_limit_mode : EnumProperty(items= (('NONE', 'None', ''),
                                                     ('X', 'X Only', ''),
                                                     ('Y', 'Y Only', '')),
                                                     name = "Limit By", default='NONE',
                                                     update=inserts_redo_update)

    boundary_randomness : FloatProperty(
            name='Randomness',
            description='Amount of randomness to introduce into the placements',
            min=0,
            max=1,
            default=1,
            precision=3,
            step=1,
            update=inserts_redo_update
            )

    row_height_deviation : FloatProperty(
            name='Row Variation',
            description='Deviation of row heights',
            min=0,
            max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    row_insert_width_deviation : FloatProperty(
            name='Width Variation',
            description='Deviation of insert widths in a row',
            min=0,
            max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

            
    col_width_deviation : FloatProperty(
            name='Col Variation',
            description='Deviation of column widths',
            min=0,
            max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
    )

    col_insert_height_deviation : FloatProperty(
            name='Height Variation',
            description='Deviation of insert heights in a column',
            min=0,
            max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    grid_row_height_deviation : FloatProperty(
                name='Row Variation',
                description='Deviation of row heights',
                min=0,
                max=100,
                default=0,
                precision=1,
                step=1,
                subtype='PERCENTAGE',
                update=inserts_redo_update
                )

    grid_col_width_deviation : FloatProperty(
            name='Col Variation',
            description='Deviation of column widths',
            min=0,
            max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
    )

    random_amount : IntProperty(
            name='Amount',
            description='Amount of INSERTs to add randomly',
            min=0,
            default=5,
            update=inserts_redo_update
            )

    width_placement : bpy.props.EnumProperty(items= (('JUSTIFY', 'Justify', ''),
                                                         ('LEFT', 'Left', ''),
                                                         ('RIGHT', 'Right', ''),
                                                         ('CENTER', 'Center', ''),
                                                         ),
                                                         name = "Width Placement", default='JUSTIFY',
                                                        update=inserts_redo_update)


    height_placement : bpy.props.EnumProperty(items= (('JUSTIFY', 'Justify', ''),
                                                         ('TOP', 'Top', ''),
                                                         ('BOTTOM', 'Bottom', ''),
                                                         ('MIDDLE', 'Middle', ''),
                                                         ),
                                                         name = "Width Placement", default='JUSTIFY',
                                                        update=inserts_redo_update)

    padding_v : FloatProperty(
            name='Padding V',
            description='Vertical Padding for Insert',
            soft_min=0,
            soft_max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    padding_h : FloatProperty(
            name='Padding H',
            description='Horizontal Padding for Insert',
            soft_min=0,
            soft_max=100,
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    height_scale : FloatProperty(
            name='Height %',
            description='Height percentage for Insert',
            min=1,
            soft_max=200,
            default=100,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    padding : FloatProperty(
            name='Padding',
            description='Minimum padding around insert',
            soft_min=0,
            soft_max=100,
            default=0.5,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    maintain_aspect_ratio: BoolProperty( #TODO remove
        name = 'Maintain Aspect Ratio',
        description = 'Maintain the aspect ratio of the insert',
        default = True,
        update=inserts_redo_update
        )

    rotation : FloatProperty(
            name='Rotate +-',
            description=' Rotation of INSERT in degrees',
            default=0,
            subtype='ANGLE',
            update=inserts_redo_update
            )

    rotation_respect_borders : BoolProperty ( 
        name = 'Respect Borders when rotating',
        description = 'Attempt to keep an INSERT within bounds when rotating',
        default = False,
        update=inserts_redo_update
        )

    rotation_deviation : FloatProperty(
            name='Rotate Offset',
            description='Variation of rotation to be applied randomly',
            min=radians(0),
            default=radians(0),
            max=radians(360),
            precision=1,
            step=1,
            subtype='ANGLE',
            update=inserts_redo_update
            )

    z_position : FloatProperty(
            name='Z Position +-',
            description='Z Position offset',
            default=0,
            precision=3,
            step=1,
            update=inserts_redo_update
            ) 

    scale_x_deviation : FloatProperty(
            name='Scale X +-',
            description='Variation of scale for X dimension',
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    scale_y_deviation : FloatProperty(
            name='Scale Y +-',
            description='Variation of scale for Y dimension',
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    scale_z_deviation : FloatProperty(
            name='Scale Z +-',
            description='Variation of scale for Z dimension',
            default=0,
            precision=1,
            step=1,
            subtype='PERCENTAGE',
            update=inserts_redo_update
            )

    boolean_solver: EnumProperty(
        name='Solver',
        description='',
        items=[
            ('FAST', 'Fast', 'fast solver for booleans'),
            ('EXACT', 'Exact', 'exact solver for booleans')],
        default='FAST',
        update=inserts_redo_update)


class kitops_synth_message(PropertyGroup):
    text : StringProperty()

class kitops_synth(PropertyGroup):

    is_initialized : BoolProperty(
        name = 'Is Initialized',
        description = 'Flag to determine if initialization of the scene has taken place',
        default = False)


    auto_update : BoolProperty(
        name = 'Auto Update',
        description = 'Automatically update a previously ran INSERT operation',
        default = False)

    preview_mode : BoolProperty( 
        name = 'Preview Mode',
        description = 'Only apply INSERTs without adding boolean modifiers and place them all in wireframe mode',
        default = False,
        update=inserts_redo_all
        )

    layer_index : IntProperty(name = "Index for layers", default = 0)

    edit_description : BoolProperty(
                        name = 'Edit Description Link',
                        description = 'Edit the description',
                        default=True)

    def check_http(self, context):
        if self.description.startswith('http'):
            self.edit_description = False

    description : StringProperty( 
        name="Description", 
        description="Text description", 
        default="< Enter a description > ",
        update=check_http)

    seed : IntProperty(
            name='Master Random Seed',
            description='Seed Value for generating and placing INSERTs',
            min=0,
            default=0,
            update=inserts_redo_update
            )

    layers : CollectionProperty(name='KIT OPS SYNTH Layers', type=kitops_synth_layer)

    messages : CollectionProperty(type=kitops_synth_message)

class kitops_synth_iterator(PropertyGroup):

    file_path: StringProperty(
            name = 'Folder Path',
            description = 'Folder Output Path',
            subtype = 'DIR_PATH',
            default = '/tmp\\')


    start_seed : IntProperty(
            name='Start Random Seed',
            description='Seed Value for generating and placing INSERTs',
            min=0,
            default=0
            )

    end_seed : IntProperty(
            name='End Random Seed',
            description='Seed Value for generating and placing INSERTs',
            min=0,
            default=0
            )


def get_synt_key_name(index, entry):
    return entry.name

classes = [synth_object_ref, 
            synth_layer_ref, 
            synth_insert_map, 
            kitops_synth_insert_entry, 
            kitops_placement, 
            kitops_synth_layer, 
            kitops_synth_message, 
            kitops_synth, 
            synth_face_ref, 
            synth_layer_face_map, 
            kitops_synth_iterator]

def register():

    for cls in classes:
        register_class(cls)

    bpy.types.Scene.kitopssynth_target_obj = PointerProperty(name='Current selected target object for SYNTH', type=bpy.types.Object)

    bpy.types.Object.kitopssynth_insert_map = CollectionProperty(name='KIT OPS SYNTH INSERT entries', type=synth_insert_map)

    bpy.types.Scene.kitopssynth = PointerProperty('KIT OPS SYNTH Scene properties', type=kitops_synth)

    bpy.types.Scene.kitopssynth_layer_face_map = CollectionProperty(name='KIT OPS SYNTH Layer Face Map', type=synth_layer_face_map)

    bpy.types.Scene.kitopssynth_iterator = PointerProperty(name='SYNTH Iterator', type=kitops_synth_iterator)


def unregister():

    for cls in classes:
        unregister_class(cls)
    
    del bpy.types.Scene.kitopssynth_iterator
    del bpy.types.Scene.kitopssynth_layer_face_map
    del bpy.types.Scene.kitopssynth    
    del bpy.types.Object.kitopssynth_insert_map
    del bpy.types.Scene.kitopssynth_target_obj
    
