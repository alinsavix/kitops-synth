# This class performs the main randomisation and orchestration for KIT OPS SYNTH
import bpy
import bmesh
from mathutils import Vector
from bpy.utils import register_class, unregister_class
from bpy_extras.io_utils import ImportHelper, ExportHelper
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, PointerProperty, IntProperty
from bpy_extras import mesh_utils
from kitops.addon.utility import insert 
from .. import property
from .. utility import addon, collections, update, inserts, distributors, messages
from .. utility.encoding import RecipeEncoder, decode_recipe
import os
import json
import uuid

class add_random_inserts():
    """Operator definition class for randomly placing inserts on object selected faces"""
    bl_options = {'UNDO'}

    layer_id : StringProperty()

    # these are used for the insert module.
    main = None
    boolean_target = None
    inserts = list()
    init_active = None
    init_selected = list()

    # redundant, to be passed so that the inserts module can operate.
    material: BoolProperty(name='Material', default=False)
    material_link: BoolProperty(name='Link Materials')
    duplicate = None
    import_material = None

    def invoke(self, context, event):
        """Initial set up of an insert"""
        
        messages.clear_messages(context)
        # Check for complexity
        if distributors.is_complex(context):
            messages.add_message(context, 'Complex Set Up detected')
        
        obj = context.active_object

        #if the active object to be operated on is an insert itself and it has a target, operate on that instead.
        if obj.kitops.insert and obj.kitops.insert_target:
            obj.kitops.insert_target.select_set(True)
            context.view_layer.objects.active = obj.kitops.insert_target

        bm = bmesh.new()

        selected_faces = []
        try:
            if obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.from_mesh(obj.data)

            selected_faces.extend([f.select for f in bm.faces if f.select])

        finally:
            if obj.mode == 'OBJECT':
                bm.free()

        # if len(selected_faces) == 0:
        #     messages.add_message(context, 'No Faces selected')
        #     return {'CANCELLED'}

        insert.operator = self

        # get references to currently selected objects for inserts to operate on.
        self.init_active = bpy.data.objects[context.active_object.name] if context.active_object and context.active_object.select_get() else None
        self.init_selected = [bpy.data.objects[obj.name] for obj in context.selected_objects]

        # Ensure we are in object mode.
        if self.init_active and self.init_active.mode != 'OBJECT':
            if bpy.ops.object.mode_set.poll():
                bpy.ops.object.mode_set(mode='OBJECT')

        # set up inserts collection.
        collections.init(context)

        # Determine whether we need booleans for this particular insert.
        if not context.scene.kitopssynth.preview_mode and self.init_active:
            if self.init_active.kitops.insert and self.init_active.kitops.insert_target:
                self.boolean_target = self.init_active.kitops.insert_target
            elif self.init_active.kitops.insert:
                self.boolean_target = None
            elif self.init_active.type == 'MESH':
                self.boolean_target = self.init_active
            else:
                self.boolean_target = None
        else:
            self.boolean_target = None

        # Deselect currently selected objects.
        for obj in context.selected_objects:
            obj.select_set(False)

        self.material_link = not event.ctrl

        return self.execute(context)

    def execute(self, context):
        """Create multiple inserts and add them to random points on the target object"""

        update.inserts_init(self, context)
        if self.layer_id == '':
            update.inserts_add(self, context)
        else:
            layer = context.scene.kitopssynth.layers[self.layer_id]
            update.inserts_add_layer(self, context, layer, [])

        self.exit(context)

        return {'FINISHED'}

    def exit(self, context, clear=False):
        """Performs clean up operations on the static modules used in this operation"""
        for obj in context.selected_objects:
            obj.select_set(False)
        if self.init_active is not None:
            self.init_active.select_set(True)
            context.view_layer.objects.active = self.init_active
        

    @classmethod
    def poll(cls, context):
        return update.poll_add_random_inserts(context)

class KO_OT_synth_add_random_inserts(Operator, add_random_inserts):
    """"Operator class for randomly adding INSERTs"""
    bl_idname = 'ko.synth_add_random_inserts'
    bl_label = 'Add Random INSERT'
    bl_description = 'Run KIT OPS SYNTH'


class KO_OT_synth_ConfirmOperator(Operator):
    """Complex set up detected. Are you sure?"""
    bl_idname = "ko.synth_add_random_inserts_confirm"
    bl_label = "Complex set up detected. Are you sure?"
    bl_options = {'INTERNAL','UNDO'}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        bpy.ops.ko.synth_add_random_inserts('INVOKE_DEFAULT', layer_id='')
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)




class KO_OT_synth_clear(Operator):
    """"Operator class for clearing INSERTs"""
    bl_idname = 'ko.synth_clear'
    bl_label = 'Clear'
    bl_description = 'Clear the INSERTs from the current selection'
    bl_options = {'INTERNAL', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.active_object

    def execute(self, context):
        active_object = context.active_object
        insert_entry_map = None
        key = property.generate_insert_map_key(active_object)
        if key in active_object.kitopssynth_insert_map:
            insert_entry_map = active_object.kitopssynth_insert_map[key]
            layers_to_delete = insert_entry_map.layers
            for layer_to_delete in layers_to_delete:
                inserts_to_delete = layer_to_delete.inserts
                for insert_ref in inserts_to_delete:
                    insert_obj = insert_ref.insert_obj
                    inserts.delete_hierarchy(insert_obj, active_object)
            insert_entry_map.layers.clear()
            distributors.delete_synth_entry(active_object, insert_entry_map)
            inserts.purge_data_blocks()
        else:
            return {'CANCELLED'}
        
        return {'FINISHED'}

class KO_OT_synth_clear_layer(Operator):
    """"Operator class for clearing INSERTs per layer"""
    bl_idname = 'ko.synth_clear_layer'
    bl_label = 'Clear INSERTs for layer'
    bl_description = 'Clear the INSERTs associated with a layer'
    bl_options = {'INTERNAL', 'UNDO'}

    layer_uid : StringProperty()

    delete_all : BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        return context.active_object

    def execute(self, context):
        active_object = context.active_object
        insert_entry_map = None

        maps_to_delete = []
        if self.delete_all:
            maps_to_delete.extend(active_object.kitopssynth_insert_map)
        else:
            key = property.generate_insert_map_key(active_object)
            if key in active_object.kitopssynth_insert_map:
                maps_to_delete.append(active_object.kitopssynth_insert_map[key])


        for insert_entry_map in maps_to_delete:
            if self.layer_uid in insert_entry_map.layers:
                layer_to_delete = insert_entry_map.layers[self.layer_uid]
                inserts_to_delete = layer_to_delete.inserts
                for insert_ref in inserts_to_delete:
                    insert_obj = insert_ref.insert_obj
                    inserts.delete_hierarchy(insert_obj, active_object)
                layer_to_delete.inserts.clear()
                insert_entry_map.layers.remove(insert_entry_map.layers.find(layer_to_delete.name))                

        purge = False
        for insert_entry_map in maps_to_delete:
            if len(insert_entry_map.layers) == 0:
                distributors.delete_synth_entry(active_object, insert_entry_map)
                purge = True
        
        if purge:
            inserts.purge_data_blocks()
        
        return {'FINISHED'}



class KO_OT_synth_bake(Operator):
    """"Operator class for baking INSERTs"""
    bl_idname = 'ko.synth_bake'
    bl_label = 'Bake'
    bl_description = 'Bakes INSERTs onto selected object'
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return update.poll_add_random_inserts(context)

    def execute(self, context): 
        old_update_state = context.scene.kitopssynth.auto_update
        context.scene.kitopssynth.auto_update = False
        try:

            active_object = context.active_object

            if active_object.kitops.id:
                error_message = 'Cannot bake an existing INSERT.'
                self.report({'ERROR'}, error_message)
                return {'CANCELLED'}

            # wipe properties of any available INSERTs.
            key = property.generate_insert_map_key(active_object)
            if key in active_object.kitopssynth_insert_map:
                insert_entry_map = active_object.kitopssynth_insert_map[key]
                layers_to_delete = insert_entry_map.layers
                for layer_to_delete in layers_to_delete:
                    layer_to_delete.inserts.clear()
                insert_entry_map.layers.clear()
            active_object.kitopssynth_insert_map.clear()


            if 'kitops' in context.preferences.addons:
                bpy.ops.ko.convert_to_mesh()
            else:
                bpy.ops.object.convert(target='MESH')

            # set active layers (which should have been baked) to inactive.
            context.scene.kitopssynth.auto_update = False
            for layer in context.scene.kitopssynth.layers:
                if layer.is_enabled:
                    layer.is_enabled = False

            # clear selection and recals normals
            bm = bmesh.new()
            obj = context.active_object
            try:
                if obj.mode == 'EDIT':
                    bm = bmesh.from_edit_mesh(obj.data)
                elif obj.mode == 'OBJECT':
                    bm.from_mesh(obj.data)

                for f in bm.faces:
                    f.select=False

                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

                if context.active_object.mode == 'EDIT':
                    bmesh.update_edit_mesh(obj.data)
                elif context.active_object.mode == 'OBJECT':
                    bm.to_mesh(obj.data)

            finally:
                if obj.mode == 'OBJECT':
                    bm.free()
            
            obj.select_set(False)
        finally:
            context.scene.kitopssynth.auto_update = old_update_state
        
        




        report_message = 'Active Layers have been baked.  Faces have been deselected.'
        self.report({'INFO'}, report_message)

        return{'FINISHED'}

def init_layer(layer):
    option = addon.option()
    for i in range(0,7):
        insert_entry = layer.inserts.add()
        insert_entry.category = option.kpack.categories[option.kpack.active_index].name
    if len(layer.inserts) > 0:
        insert = layer.inserts[0]
        insert.is_expanded = True
        insert.is_enabled = True


class KO_OT_AddLayer(Operator): 
    """Add a layer""" 
    bl_idname = "ko.synth_add_layer" 
    bl_label = "Adds a layer" 
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context): 

        old_update_state = context.scene.kitopssynth.auto_update
        context.scene.kitopssynth.auto_update = False
        try:

            layers = context.scene.kitopssynth.layers

            layer = layers.add()
            layer.name = str(uuid.uuid4())
            init_layer(layer)

            context.scene.kitopssynth.layer_index = len(layers) - 1

        finally:
            context.scene.kitopssynth.auto_update = old_update_state
        
        return{'FINISHED'}

class KO_OT_DuplicateLayer(Operator): 
    """Duplicate the selected layer""" 
    bl_idname = "ko.synth_duplicate_layer" 
    bl_label = "Adds a layer" 
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context): 

        index = context.scene.kitopssynth.layer_index 
        layers = context.scene.kitopssynth.layers

        if index >= 0 and index < len(layers):
            layer_to_copy = layers[index]

            new_layer = layers.add()
            new_layer.name = str(uuid.uuid4())

            for k, v in layer_to_copy.items():
                new_layer[k] = v

            new_layer.name += ' Copy'

            context.scene.kitopssynth.layer_index = len(layers) - 1
        else:
            return {'CANCELLED'}
        
        return{'FINISHED'}


class KO_OT_DeleteLayer(Operator): 
    """Delete the selected layer entry""" 
    bl_idname = "ko.synth_delete_layer" 
    bl_label = "Deletes a layer" 
    bl_options = {'INTERNAL', 'UNDO'}

    item_index_to_delete : IntProperty(default=-1)

    @classmethod 
    def poll(cls, context): 
        return context.scene.kitopssynth.layers

    def execute(self, context): 
        layers = context.scene.kitopssynth.layers
        index = self.item_index_to_delete
        
        layers.remove(index) 
        context.scene.kitopssynth.layer_index  = min(max(0, index - 1), len(layers) - 1) 
        
        return{'FINISHED'}

class KO_OT_ActivateDeactivateLayer(Operator): 
    """Activate the selected later from the list""" 
    bl_idname = "ko.synth_activate_deactivate_layer" 
    bl_label = "Activates or deactivates a layer" 
    bl_options = {'INTERNAL', 'UNDO'}

    item_index_to_activate_deactivate : IntProperty(default=-1)

    @classmethod 
    def poll(cls, context): 
        return context.scene.kitopssynth.layers

    def execute(self, context): 
        layers = context.scene.kitopssynth.layers
        index = self.item_index_to_activate_deactivate
        i=0
        layer_to_change = None
        for layer in layers:
            if i == index:
                layer_to_change = layer
                break
            i+=1

        if layer_to_change != None:
            layer_to_change.is_enabled = not layer_to_change.is_enabled
            if layer_to_change.is_enabled:
                context.scene.kitopssynth.layer_index  = index
        
        return{'FINISHED'}

class KO_OT_MoveLayer(Operator): 
    """Move an item in the layer""" 
    bl_idname = "ko.synth_move_layer" 
    bl_label = "Move layer" 
    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""), ('DOWN', 'Down', ""),)) 
    bl_options = {'INTERNAL', 'UNDO'}

    @classmethod 
    def poll(cls, context): 
        return context.scene.kitopssynth.layers
    
    def move_index(self, context): 
        """ Move index of an item render queue while clamping it. """ 
        index = context.scene.kitopssynth.layer_index 
        list_length = len(context.scene.kitopssynth.layers) - 1 # (index starts at 0) 
        new_index = index + (-1 if self.direction == 'UP' else 1) 
        
        bpy.context.scene.kitopssynth.layer_index = max(0, min(new_index, list_length)) 
        
    def execute(self, context): 
        my_list = context.scene.kitopssynth.layers
        index = context.scene.kitopssynth.layer_index
        neighbor = index + (-1 if self.direction == 'UP' else 1) 
        
        my_list.move(neighbor, index) 
        self.move_index(context) 
        return{'FINISHED'}

class KO_OT_ResetLayer(Operator): 
    """Reset a layer's settings'""" 
    bl_idname = "ko.synth_reset_layer" 
    bl_label = "Reset a layer settings" 
    bl_options = {'INTERNAL', 'UNDO'}

    index_to_reset : IntProperty()

    def execute(self, context): 
        layers = context.scene.kitopssynth.layers
        index = self.index_to_reset

        layer = layers[index]

        old_name = layer.name

        layers.remove(index)

        layer = layers.add()
        layer.name = old_name
        init_layer(layer)

        layers.move(len(layers) - 1, index)
        
        return{'FINISHED'}



class KO_OT_FillCategories(Operator): 
    """Fills the layer with this category""" 
    bl_idname = "ko.synth_fill_cats" 
    bl_label = "Fills a layer with selected category" 
    bl_options = {'INTERNAL', 'UNDO'}

    category : StringProperty()
    layer_index : IntProperty()

    @classmethod 
    def poll(cls, context): 
        return context.scene.kitopssynth.layers

    def execute(self, context): 
        layers = context.scene.kitopssynth.layers
        layer = layers[self.layer_index]
        for insert in layer.inserts:
            if self.category != insert.category:
                insert.category = self.category
        
        return{'FINISHED'}


class KO_OT_OpenFilebrowser(Operator, ImportHelper): 
    bl_idname = "ko.synth_open_filebrowser" 
    bl_label = "LOAD" 
    bl_description = 'Open SYNTH Configuration'
    bl_options = {'INTERNAL', 'UNDO'}

    filter_glob: StringProperty( 
        default='*.json', 
        options={'HIDDEN'} ) 
        
    def execute(self, context): 
        """Do something with the selected file(s)""" 
        filename, extension = os.path.splitext(self.filepath) 
            
        with open(self.filepath) as json_file:
            old_update_state = context.scene.kitopssynth.auto_update
            context.scene.kitopssynth.auto_update = False
            try:
                recipeJSON = json.load(json_file)
                decode_recipe(recipeJSON, context)
                context.area.tag_redraw()
            finally:
                context.scene.kitopssynth.auto_update = old_update_state

        return {'FINISHED'}

class KO_OT_SaveFilebrowser(bpy.types.Operator, ExportHelper):
    bl_idname = "ko.synth_save_filebrowser" 
    bl_label = "SAVE"
    bl_description = 'Save SYNTH Configuration'
    bl_options = {'INTERNAL', 'UNDO'}
    
    filename_ext = ".json"  # ExportHelper mixin class uses this
    def execute(self, context):
        filepath = self.filepath
        print('FILE: ', filepath)

        # encode dict as JSON 
        data = json.dumps(context.scene.kitopssynth, indent=4, cls=RecipeEncoder)

        # write JSON file
        with open(filepath, 'w') as outfile:
            outfile.write(data + '\n')
        return{'FINISHED'}

class KO_OT_OpenHelpURL(Operator):
    bl_idname = "ko.synth_open_help_url" 
    bl_label = "SYNTH Help"
    bl_description = 'Open SYNTH documentation'
    bl_options = {'INTERNAL', 'UNDO'}
    
    url : StringProperty()

    def execute(self, context):
        bpy.ops.wm.url_open(url = self.url)
        return {'FINISHED'}

class KO_OT_ReportMessage(Operator):
    bl_idname = "ko.synth_report_message" 
    bl_label = "SYNTH Help"
    bl_description = 'Open SYNTH documentation'
    bl_options = {'INTERNAL'}
    
    message : StringProperty()
    level : StringProperty(default='INFO')

    def execute(self, context):
        self.report({self.level}, self.message)
        return {'FINISHED'}

class KO_OT_Clear_Messages(Operator):
    bl_idname = "ko.synth_clear_messages" 
    bl_label = "Clear Messages"
    bl_description = 'Clear SYNTH messages'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        context.scene.kitopssynth.messages.clear()
        return {'FINISHED'}


class KO_OT_SelectLayerFaces(Operator): 
    """Select the last set of faces that were selected for this layer""" 
    bl_idname = "ko.synth_select_layer_faces" 
    bl_label = "Select last set of faces for layer" 
    bl_options = {'INTERNAL', 'UNDO'}

    layer_index : IntProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object

    def execute(self, context): 
        layers = context.scene.kitopssynth.layers
        index = self.layer_index

        layer = layers[index]

        layer_id = layer.name

        if layer_id in context.scene.kitopssynth_layer_face_map:
            face_ids = context.scene.kitopssynth_layer_face_map[layer_id].face_ids
            obj = context.active_object
            bm = bmesh.new()
            if obj.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.from_mesh(obj.data)
            
            bm.faces.ensure_lookup_table()
            for f in bm.faces:
                f.select_set(False)
            
            for face_id in face_ids:
                try:
                    bm.faces[face_id.face_id].select_set(True)
                except IndexError:
                    pass

            if obj.mode == 'EDIT':
                 bmesh.update_edit_mesh(obj.data)
            elif obj.mode == 'OBJECT':
                bm.to_mesh(obj.data)
                bm.free()
            return{'FINISHED'}
        
        return{'CANCELLED'}


class KO_OT_RefreshSynthKPACKS(Operator):
    bl_idname = "ko.synth_refresh_kpacks" 
    bl_label = "Refresh KPACKS"
    bl_description = "Refresh KPACK entries"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        property.reload_kpacks(context)
        return {'FINISHED'}

class KO_OT_ResetAll(Operator):
    bl_idname = "ko.synth_reset_all" 
    bl_label = "Reset Settings for all"
    bl_description = "Reset Settings for all"
    bl_options = {'INTERNAL', 'UNDO'}

    def execute(self, context):

        context.scene.kitopssynth.auto_update = False

        layers = context.scene.kitopssynth.layers
        layers.clear()
        layer = layers.add()
        layer.name = str(uuid.uuid4())
        layer.layer_name = "Default Layer"
        init_layer(layer)

        context.scene.kitopssynth.layer_index = 0
        context.scene.kitopssynth.description = "< Enter a description > "
        context.scene.kitopssynth.seed = 0
        context.scene.kitopssynth.messages.clear()

        return {'FINISHED'}

class KO_OT_RecalcNormals(bpy.types.Operator):
    """Recalculate Normals"""
    bl_idname = "ko.synth_recalc_normals"
    bl_label = "Recalculate Normals"
    bl_options = {"INTERNAL", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.active_object

    def execute(self, context):
        bm = bmesh.new()
        try:
            if context.active_object.mode == 'EDIT':
                bm = bmesh.from_edit_mesh(context.active_object.data)
            elif context.active_object.mode == 'OBJECT':
                bm.from_mesh(context.active_object.data)

            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            
            if context.active_object.mode == 'EDIT':
                bmesh.update_edit_mesh(context.active_object.data)
            elif context.active_object.mode == 'OBJECT':
                bm.to_mesh(context.active_object.data)

        finally:
            if context.active_object.mode != 'EDIT':
                bm.free()
            context.active_object.data.update()

        return {'FINISHED'}

class KO_OT_SynthIterator(bpy.types.Operator):
    """SYNTH Iterator"""
    bl_idname = "ko.synth_iterator"
    bl_label = "SYNTH Iterator Run"
    bl_options = {"INTERNAL", "UNDO"}

    @classmethod
    def poll(cls, context):
        return update.poll_add_random_inserts(context)

    def execute(self, context):
        file_path = context.scene.kitopssynth_iterator.file_path
        start_seed = context.scene.kitopssynth_iterator.start_seed
        end_seed = context.scene.kitopssynth_iterator.end_seed

        old_master_seed = context.scene.kitopssynth.seed
        old_auto_update = context.scene.kitopssynth.auto_update
        old_file_path = context.scene.render.filepath

        try:
            context.scene.kitopssynth.auto_update = True

            if not os.path.exists(file_path):
                os.makedirs(file_path)

            ack_path = os.path.join(file_path, 'running.ack')
            open(ack_path, 'a').close()

            for seed in range(start_seed, end_seed + 1):
                # first check if we should abort because the .ack file is no longer there.
                try:
                    f = open (ack_path)
                except IOError:
                    # abort the run if there is an error opening the file.
                    report_message = 'SYNTH ITERATE run aborted.'
                    self.report({'INFO'}, report_message)
                    break
                finally:
                    f.close()

                # perform the next iteraton.
                context.scene.kitopssynth.seed = seed
                context.scene.render.filepath = os.path.join(file_path, 'synth_iterator_' + str(seed))
                bpy.ops.render.render(write_still = True)

        finally:
            context.scene.kitopssynth.seed = old_master_seed
            context.scene.kitopssynth.auto_update = old_auto_update
            context.scene.render.filepath = old_file_path

        return {'FINISHED'}

classes = [KO_OT_synth_add_random_inserts, 
            KO_OT_synth_ConfirmOperator,
            KO_OT_synth_clear,
            KO_OT_synth_clear_layer,
            KO_OT_synth_bake,
            KO_OT_AddLayer,
            KO_OT_DuplicateLayer,
            KO_OT_DeleteLayer,
            KO_OT_ActivateDeactivateLayer,
            KO_OT_MoveLayer,
            KO_OT_ResetLayer,
            KO_OT_FillCategories,
            KO_OT_OpenFilebrowser,
            KO_OT_SaveFilebrowser,
            KO_OT_OpenHelpURL,
            KO_OT_ReportMessage,
            KO_OT_Clear_Messages,
            KO_OT_SelectLayerFaces,
            KO_OT_RefreshSynthKPACKS,
            KO_OT_ResetAll,
            KO_OT_RecalcNormals,
            KO_OT_SynthIterator]

def register():
    for cls in classes:
        register_class(cls)

    try:
        from .. utility import smart
        smart.register()
    except: pass

def unregister():
    for cls in classes:
        unregister_class(cls)

    try:
        from .. utility import smart
        smart.unregister()
    except: pass