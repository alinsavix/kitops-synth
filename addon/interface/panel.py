# Main user interface for the add-on.
import bpy

from bpy.types import Panel, UIList, Menu
from bpy.utils import register_class, unregister_class
from .. import property
from .. utility import addon, distributors, inserts
from kitops.addon.utility import insert
from bpy.props import BoolProperty


def get_current_layer(context):
    if context.scene.kitopssynth.layer_index >= 0 and context.scene.kitopssynth.layer_index < len(context.scene.kitopssynth.layers):
        return context.scene.kitopssynth.layers[context.scene.kitopssynth.layer_index]
    return None

class KO_SYNTH_LAYER_ENTRY_UL_List(UIList): 
    """Demo UIList.""" 
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index): 
        self.use_filter_show = False

        layer_icon = 'RIGHTARROW_THIN' if index == context.scene.kitopssynth.layer_index else 'BLANK1'
        
        # Make sure your code supports all 3 layout types 
        if self.layout_type in {'DEFAULT', 'COMPACT'}: 
            row = layout.row(align=True)
           
            row.label(text="", icon = layer_icon, icon_value=1)

            props = row.operator('ko.synth_activate_deactivate_layer', icon="CHECKBOX_HLT" if item.is_enabled else "CHECKBOX_DEHLT", text='')
            props.item_index_to_activate_deactivate = index

            row.prop(item, 'layer_name', text='') 

            layer = context.scene.kitopssynth.layers[index]


            props = row.operator("ko.synth_select_layer_faces", icon="SELECT_INTERSECT", text='')
            props.layer_index = index

            props = row.operator('ko.synth_clear_layer', icon='BRUSH_DATA', text='')
            props.layer_uid = layer.name
            props.delete_all = True
            
            props = row.operator('ko.synth_reset_layer', icon='DECORATE_OVERRIDE', text='')
            props.index_to_reset = index

            props = row.operator('ko.synth_delete_layer', icon='X', text='')
            props.item_index_to_delete = index

        elif self.layout_type in {'GRID'}: 
            layout.alignment = 'CENTER' 
            layout.label(text="", icon = layer_icon, icon_value=1)


class KO_PT_SYNTH_UI_PT_MainPanel(Panel):
    """Main panel"""
    bl_idname = "KITOPSSYNTH_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_label = 'KIT OPS SYNTH'
    bl_region_type = 'UI'
    bl_category = 'SYNTH'

    def draw(self, context):

        layout = self.layout
        col = layout.column()
        col.alert = True
        # display any messages
        if len (context.scene.kitopssynth.messages) > 0:
            col.label(text='Messages:')
        for message in context.scene.kitopssynth.messages:
            col.label(text=message.text)
        if len (context.scene.kitopssynth.messages) > 0:
            col =layout.column()
            col.operator('ko.synth_clear_messages', icon='CANCEL', text='CLEAR MESSAGES')

    def draw_header_preset(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("ko.synth_open_help_url", icon='QUESTION', text="").url = "http://cw1.me/synthdocs"
        
        row.separator()

class KO_PT_SYNTH_UI_PT_ActionsPanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Actions"
    bl_label = "Actions"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):
                
                box = layout.box()

                col = box.column(align=True)
                col = col.column()
                row = col.row()
                row.alignment='CENTER'
                row.prop(context.scene.kitopssynth, 'preview_mode', text="Preview")

                # row = col.row()
                # row.alignment='CENTER'
                row.prop(context.scene.kitopssynth, 'auto_update',  text='Auto Update')          

                col = box.column(align=True)
                row = col.row(align=True)
                
                if distributors.is_complex(context):
                    col = row.column(align=True)
                    col.alert = True
                    col.operator('ko.synth_add_random_inserts_confirm', text="DO IT")
                else:
                    props = row.operator('ko.synth_add_random_inserts', text="DO IT")
                    props.layer_id = ''
                row.operator('ko.synth_clear', text="CLEAR")

                col = box.column(align=True)
                col.prop(context.scene.kitopssynth, 'seed', text="Main Seed")


class KO_PT_SYNTH_UI_PT_IteratorPanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Iterator"
    bl_label = "Iterator"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):

                col = layout.column()
                col.label(text='Seed Range')#
                row = col.row(align=True)
                row.prop(context.scene.kitopssynth_iterator, 'start_seed', text="")
                row.prop(context.scene.kitopssynth_iterator, 'end_seed', text="")
                col.prop(context.scene.kitopssynth_iterator, 'file_path', text="")
                col.operator('ko.synth_iterator', text='Start')



class KO_PT_SYNTH_UI_PT_InsertToolsPanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Tools"
    bl_label = "Tools"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):

                col = layout.column(align=True)
                col.operator('ko.synth_bake', text="Bake Object", icon='EXPERIMENTAL')
                col.operator('ko.remove_wire_inserts', text='Remove Unused Wire INSERTs', icon='MESH_ICOSPHERE')
                col.operator('ko.synth_refresh_kpacks', text='Refresh KIT OPS KPACKS', icon='FILE_REFRESH')
                # col.operator('ko.synth_recalc_normals', text='Recalculate Normals', icon='NORMALS_FACE') TODO recalculate normals may still be introduced
                col.operator('ko.synth_reset_all', text='Reset SYNTH Settings', icon='DECORATE_OVERRIDE')

class KO_PT_SYNTH_UI_PT_InsertLayersPanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Insert_Layers"
    bl_label = "Layers"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):

                main_col = layout.column(align=True)

                col = main_col.column(align=True)
                col.template_list("KO_SYNTH_LAYER_ENTRY_UL_List", "The_List", scene.kitopssynth, "layers", scene.kitopssynth, "layer_index", type='DEFAULT')

                row = col.row(align=True)
                row.operator("ko.synth_add_layer", text="Add")
                row.operator("ko.synth_duplicate_layer" , text="Duplicate")
                row.operator("ko.synth_move_layer", icon="TRIA_UP", text='').direction = 'UP' 
                row.operator("ko.synth_move_layer", icon="TRIA_DOWN", text='').direction = 'DOWN'



class KO_PT_SYNTH_UI_PT_InsertsPanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Inserts"
    bl_label = "INSERTs"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return

        option = addon.option()

        if insert.authoring():
            if not smart_enabled:
                layout.label(icon='ERROR', text='Purchase KIT OPS PRO')
                layout.label(icon='BLANK1', text='To use these features')

            if context.scene.kitops.factory:
                column = layout.column()
                column.enabled = smart_enabled
                column.label(text='INSERT name')
                column.prop(option, 'insert_name', text='')

            column = layout.column()
            column.enabled = smart_enabled
            column.label(text='Author')
            column.prop(option, 'author', text='')


        col = layout.column()
        i = 0
        for insert_entry in preference.inserts:
            box = col.box()

            if insert_entry.error_message != '':
                row_error = box.row()
                row_error.alert = True
                row_error.label(text=insert_entry.error_message)
                row_error.prop(insert_entry, 'clear_error_message', icon="CANCEL", icon_only=True)


            row1 = box.row(align=True)
            row1.scale_x = 1
            row1.scale_y = .75
            row2 = row1.row(align=True)
            row2.alignment='LEFT'
            
            insert_display_name = insert_entry.insert_name if hasattr(insert_entry, 'insert_name') and insert_entry.insert_name != 'A ' else ''

            row2.prop(insert_entry, 'is_expanded', text="#" + str(i+1) + ': ' + insert_display_name, icon='TRIA_DOWN' if insert_entry.is_expanded else 'TRIA_RIGHT', icon_only=True, emboss=False)
            row2 = row1.row(align=True)
            row2.alignment='RIGHT'
            row2.prop(insert_entry, 'is_enabled',icon="CHECKBOX_HLT" if insert_entry.is_enabled else "CHECKBOX_DEHLT", icon_only=True, emboss=False)
            i+=1

            if insert_entry.is_expanded:

                row = box.row()
                col1 = row.column()
                col1.enabled = insert_entry.is_enabled
                col1.template_icon_view(insert_entry, 'insert_name', show_labels=True, scale=2)
                col1.prop(insert_entry, "maintain_aspect_ratio", icon="MOD_EDGESPLIT", icon_only=True)

                col1 = row.column()
                col2 = col1.column()
                row2 = col2.row(align=True)
                row3 = row2.row(align=True)
                row3.enabled = insert_entry.is_enabled
                row3.prop(insert_entry, 'category', text="")
                props = row3.operator("ko.synth_fill_cats", icon="PASTEDOWN", text='')
                props.category = insert_entry.category
                props.layer_index = context.scene.kitopssynth.layer_index


                row = col1.row()

                col1 = row.column(align=True)

                row1 = col1.row(align=True)
                row1.enabled = insert_entry.is_enabled
                row2 = row1.row(align=True)
                row2.enabled = not insert_entry.do_not_scale
                row2.prop(insert_entry, 'scale')

                row3 = row1.row(align=True)
                row3.prop(insert_entry, 'do_not_scale', icon='OBJECT_HIDDEN', text='', icon_only=True)

                row1 = col1.row(align=True)
                row1.enabled = insert_entry.is_enabled
                row2 = row1.row(align=True)
                row2.enabled = not insert_entry.use_once
                row2.prop(insert_entry, 'proportionality')
                row3 = row1.row(align=True)
                row3.prop(insert_entry, 'use_once', icon='SNAP_FACE_CENTER', text='', icon_only=True)

            
class KO_PT_SYNTH_UI_PT_PlacementStylePanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_PlacementStyle"
    bl_label = "Placement Style"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return
        option = addon.option()


        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            #Display INSERTS and randomisation options if KIT OPS categories are present.
            if len(option.kpack.categories):
                #Begin randomisation parameters.
                box = layout.box()                
                
                col = box.column()
                col.label(text='Seed')
                col.prop(preference, 'seed', text='Seed Value', slider=False)

                box = layout.box()     
                row = box.row()
                row.prop(preference, 'distribution', expand=True)

                # draw distribution settings.
                distribution_class_name = preference.distribution
                distributor = getattr(distributors, distribution_class_name)
                distributor.draw(preference, box.column())


class KO_PT_SYNTH_UI_PT_PlacementSizePanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Size"
    bl_label = "Transformation"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):
                box = layout.box()
                box.column().label(text='Size')
                col = box.column()
                # col.prop(preference, 'maintain_aspect_ratio') #TODO hidden for now, remove completely if maintain aspect ratio approach in each individual insert approach is agreed.
                if preference.maintain_aspect_ratio:
                    col.prop(preference, 'padding', slider=False)
                    col.separator()
                else:
                    col.prop(preference, 'padding_h', text='Padding H')
                    col.prop(preference, 'padding_v', text='Padding V')
                    col.prop(preference, 'height_scale', text='Height %')

                col.separator()
                col.prop(preference, 'z_position', slider=False)

                col.separator()
                col.prop(preference, 'scale_x_deviation', slider=False)
                col.prop(preference, 'scale_y_deviation', slider=False)
                col.prop(preference, 'scale_z_deviation', slider=False)

                box = layout.box()
                
                box.column().label(text='Rotation')
                col = box.column()
                row = col.row(align=True)
                row.prop(preference, 'rotation', slider=False)
                row.prop(preference, 'rotation_respect_borders', icon='DRIVER_ROTATIONAL_DIFFERENCE', icon_only=True)
                col.prop(preference, 'rotation_deviation', slider=False)


class KO_PT_SYNTH_UI_PT_OptimizePanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_Optimize"
    bl_label = "Optimizations"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):
                if bpy.app.version[1] > 90:
                    box = layout.box()
                    box.column().label(text='Optimize')
                    row = box.row()
                    row.prop(preference, 'boolean_solver', expand=True)

    

class KO_PT_SYNTH_UI_PT_LoadSavePanel(bpy.types.Panel):
    """Properties panel for add-on operators."""
    bl_idname = "KITOPSSYNTH_PT_Panel_LoadSave"
    bl_label = "Recipes"
    bl_category = "SYNTH"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_parent_id = 'KITOPSSYNTH_PT_Panel'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        """Draw all options for the user to input to."""
        layout = self.layout
        scene = context.scene
        preference = get_current_layer(context)
        if preference == None:
            layout.label(text="No Layer Selected")
            return
        option = addon.option()
        if not insert.authoring() and not context.scene.kitops.thumbnail: # TODO wrong place?
            if len(option.kpack.categories):
                
                box = layout.box()
                col = box.column()
                row = col.row(align=True)
                row.operator('ko.synth_open_filebrowser', text='LOAD RECIPE')

                box = layout.box()
                col = box.column(align=True)
                col.alignment='CENTER'

                # description handling if starts with http.
                description = context.scene.kitopssynth.description
                edit_description = context.scene.kitopssynth.edit_description
                row = col.row(align=True)
                # split = row.split(factor=0.8, align=True)
                if not description.startswith('http') or edit_description:
                    row.prop(context.scene.kitopssynth, 'description', text='')
                else:

                    row.operator("ko.synth_open_help_url", icon='LINKED', text="Click Link").url = description
                    row.prop(context.scene.kitopssynth, 'edit_description', icon='GREASEPENCIL', text='', toggle=False)

                col.operator('ko.synth_save_filebrowser', text='SAVE RECIPE')

                

classes = [KO_SYNTH_LAYER_ENTRY_UL_List,
            KO_PT_SYNTH_UI_PT_MainPanel, 
            KO_PT_SYNTH_UI_PT_ActionsPanel,
            KO_PT_SYNTH_UI_PT_IteratorPanel,
            KO_PT_SYNTH_UI_PT_InsertToolsPanel,
            KO_PT_SYNTH_UI_PT_InsertLayersPanel,
            KO_PT_SYNTH_UI_PT_InsertsPanel, 
            KO_PT_SYNTH_UI_PT_PlacementStylePanel, 
            KO_PT_SYNTH_UI_PT_PlacementSizePanel,
            KO_PT_SYNTH_UI_PT_OptimizePanel,
            KO_PT_SYNTH_UI_PT_LoadSavePanel]

def register():
    for cls in classes:
        if cls == KO_PT_SYNTH_UI_PT_OptimizePanel and bpy.app.version[1] <= 90:
            continue
        register_class(cls)


def unregister():
    for cls in classes:
        if cls == KO_PT_SYNTH_UI_PT_OptimizePanel and bpy.app.version[1] <= 90:
            continue
        unregister_class(cls)
