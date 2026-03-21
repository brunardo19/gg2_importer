import math
import re
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import IntProperty, StringProperty, BoolProperty, CollectionProperty, EnumProperty
from bpy.types import Operator

from . import config
from . import core_parser
from . import blender_utils

import time


class GG2ImporterPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    gg2_dir: StringProperty(
        name="GG2 Folder Path",
        description="Path to the Guilty Gear 2 Overture installation folder",
        subtype='DIR_PATH',
        default=r"C:\Program Files (x86)\Steam\steamapps\common\GG2"
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "gg2_dir")

def update_config_paths(context):
    prefs = context.preferences.addons.get(__package__)
    if prefs and hasattr(prefs, 'preferences'):
        base_path = prefs.preferences.gg2_dir
    else:
        base_path = r"C:\Program Files (x86)\Steam\steamapps\common\GG2"
        
    config.GG2_PATH = Path(base_path)
    config.LOADTABLE_PATH = config.GG2_PATH / "loadtable.bin"
    config.DATA_PATH = config.GG2_PATH / "data"


class GG2EntryItem(bpy.types.PropertyGroup):
    entry_index: IntProperty()
    internal_name: StringProperty()
    display_name: StringProperty()
    color_number: IntProperty()
    
def code_to_name(code):
    if not isinstance(code, str) or len(code) < 2:
        return code

    try:
        master = config.DISPLAY_NAMES_1[code[0]]
        
        if code[1:3] == "CP":
            return f"{master} Capture {code[3:]}".strip()
            
        if code[1] in {"H", "J", "I"}:
            rank = config.DISPLAY_NAMES_2[code[1]]
            return f"{master} {rank} {code[2:]}".strip()

        rank = config.DISPLAY_NAMES_2[code[1]]
        role = config.DISPLAY_NAMES_3[code[2]]
        return f"{master} {rank} {role} {code[3:]}".strip()

    except (KeyError, IndexError) as e:
        print(f"Warning: Could not parse code '{code}'. Reason: {e}")
        return code
        

# control how the row looks
class GG2_UL_EntryList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.1)
        split.label(text=f"[{item.entry_index}]")
        split.label(text=item.internal_name)
        split.label(text=item.display_name)
        split.label(text=f"Color: {item.color_number}")
            
    def filter_items(self, context, data, propname):
        entries = getattr(data, propname)
        flt_flags = []
        flt_neworder = []

        # Enables filtering by the 'display_name' property
        if self.filter_name:
            flt_flags = bpy.types.UI_UL_list.filter_items_by_name(
                self.filter_name, 
                self.bitflag_filter_item, 
                entries, 
                "display_name", 
                reverse=False
            )
        
        return flt_flags, flt_neworder

def get_entry_items(self, context):
    items = []
    for entry in config.temp_entries:
        if not entry.get_model_name() and not entry.colorVariationSource:
            continue
        
        identifier = str(entry.index)
        display_name = f"[{entry.index}] {entry.name} (Color: {entry.colorNumber})"
        items.append((identifier, display_name, f"Import entry {entry.index}"))
    return items

def get_normal_and_combined_textures(self, context, texture_set, base_path):
    base_path = base_path[:-4] # remove the .xt and the color number
    print(f"Looking for normal and combined textures with base path: {base_path}")
    normal_path = f"{base_path}0N.XT".lower()
    combined_path = f"{base_path}0C.XT".lower()
    
    for entry in config.temp_entries:
        if entry.get_normal_name() and entry.get_normal_name().lower() == normal_path:
            af_path = config.DATA_PATH / f"AF{entry.pkmnumber}.PKM"
            if af_path.exists():
                texture_set[1] = (entry.extract_file_from_pkm(af_path, entry.index + 1204 * 2))
                print(f"Found normal texture: {entry.get_normal_name()} at index {entry.index + 1204 * 2} in {af_path}")
        
        if entry.get_texturec_name() and entry.get_texturec_name().lower() == combined_path:
            af_path = config.DATA_PATH / f"AF{entry.pkmnumber}.PKM"
            if af_path.exists():
                texture_set[2] = (entry.extract_file_from_pkm(af_path, entry.index + 1204))
                print(f"Found combined texture: {entry.get_texturec_name()} at index {entry.index + 1204} in {af_path}")
                
        if texture_set[1] and texture_set[2]:
            break  

def get_texture_items(self, context, texture_list, base_path, color_number=0):
    found_textures = []
    
    base_path = base_path.strip('\x00') + '\\'
    
    target_paths = {}
    for tex in texture_list:
        tex = tex.strip('\x00')
        # In the load table, textures are stored as uppercase and with .XT extension instead of .DDS for some reason
        tex = tex.replace("S.DDS", "C.DDS") # Because fuck this game
        search_tex = tex.upper().replace(".DDS", ".XT")
        search_tex = search_tex.replace("_COLOR", "") # Because fuck this game
        search_tex = search_tex.replace("_00", "") # Because fuck this game
        is_normal_or_comb = search_tex.upper().endswith("N.XT") or search_tex.upper().endswith("C.XT")
        if re.search(r'\d', tex) and not is_normal_or_comb and color_number<6:
            search_tex = re.sub(r'\d', str(color_number), search_tex)
        
            
        full_path = f"{base_path}{search_tex}".lower()
        target_paths[full_path] = search_tex


    print(f"Looking for textures matching: {target_paths.keys()}")
    names = []

    # Scan the entries for matches, maintaining target_paths order
    for target_path_key in list(target_paths.keys()):
        tex_name = target_paths[target_path_key]
        found = False
        
        for i,entry in enumerate(config.temp_entries):
            # Check Diffuse
            if entry.texturename and entry.texturename.lower() == target_path_key:
                td_path = config.DATA_PATH / f"TD{entry.pkmnumber}{entry.colorNumber}.PKM"
                if td_path.exists():
                    texture_set = [None, None, None]
                    texture_set[0] =(entry.extract_file_from_pkm(td_path, entry.index))
                    get_normal_and_combined_textures(self, context, texture_set, target_path_key)
                    names.append(tex_name)
                    found_textures.append(texture_set)
                    found = True
                    break
            
            # Check Combined Data
            if entry.get_texturec_name() and entry.get_texturec_name().lower() == target_path_key:
                #af_path = config.DATA_PATH / f"AF{entry.pkmnumber}.PKM"
                #if af_path.exists():
                    found_textures.append(None)

                    #There are some cases where normal or combined data for some reason doesnt exist in the AFB
                    #But I need to add a placeholder to keep the lists to work with the material index for now

                    #found_textures.append(entry.extract_file_from_pkm(af_path, entry.index + 1204))
                    names.append(tex_name)
                    found = True
                    break
            
            # Check Normal Maps
            if entry.get_normal_name() and entry.get_normal_name().lower() == target_path_key:
                #af_path = config.DATA_PATH / f"AF{entry.pkmnumber}.PKM"
                #if af_path.exists():
                    found_textures.append(None)

                    #There are some cases where normal or combined data for some reason doesnt exist in the AFB
                    #But I need to add a placeholder to keep the lists to work with the material index for now

                    #found_textures.append(entry.extract_file_from_pkm(af_path, entry.index + 1204 * 2))
                    names.append(tex_name)
                    found = True
                    break
        
        if found:
            target_paths.pop(target_path_key)
                
                
    print(f"Found {len(found_textures)} matching textures")

    return found_textures, names
    
class LoadlistImporter(Operator):
    bl_idname = "import_scene.gg2_loadlist"
    bl_label = "Import GG2 Loadlist"
    bl_options = {"PRESET", "UNDO"}

    def execute(self, context):
        try:
            update_config_paths(context)
            config.temp_entries = core_parser.parse_list(config.LOADTABLE_PATH)
        except Exception as e:
            self.report({"ERROR"}, f"Failed to import: {e}")
            return {"CANCELLED"}

        if not config.temp_entries:
            self.report({"ERROR"}, "No entries found in file.")
            return {"CANCELLED"}

        bpy.ops.import_scene.gg2_loadlist_selector("INVOKE_DEFAULT")
        return {"FINISHED"}

class LoadlistEntrySelector(bpy.types.Operator):
    bl_idname = "import_scene.gg2_loadlist_selector"
    bl_label = "Select GG2 Entry"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.gg2_import_entries.clear() # Clear old data
        
        # Populate the CollectionProperty from your parsed config.temp_entries
        for entry in config.temp_entries:
            if not entry.has_model():
                continue
                
            new_item = wm.gg2_import_entries.add()
            new_item.entry_index = entry.index
            new_item.internal_name = entry.name
            new_item.display_name = code_to_name(entry.name)
            new_item.color_number = entry.colorNumber or 0
            new_item.has_model = bool(entry.has_model())
            
        # Call the properties dialog instead of the search popup
        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        
        layout.label(text="Choose an entry to import:", icon='IMPORT')
        
        # template_list(class_name, list_id, dataptr, propname, active_dataptr, active_propname)
        layout.template_list(
            "GG2_UL_EntryList", 
            "", 
            wm, "gg2_import_entries", 
            wm, "gg2_active_entry_index"
        )
    
    def execute(self, context):
        start_time = time.perf_counter()

        wm = context.window_manager
        
        # Get the selected index from the UIList
        if not wm.gg2_import_entries:
            return {'CANCELLED'}
            
        selected_item = wm.gg2_import_entries[wm.gg2_active_entry_index]
        chosen_index = selected_item.entry_index
        
        chosen_entry : core_parser.Entry = next((e for e in config.temp_entries if e.index == chosen_index), None)
        
        if not chosen_entry:
            self.report({"ERROR"}, "Selected entry could not be found.")
            return {"CANCELLED"}

        out = chosen_entry.extract_files()
        print(f"Extracted files: {out.keys()}")

        model_data = out.get("model")
        if not model_data:
            self.report({"ERROR"}, f"No model data found for {chosen_entry.name}.")
            return {"CANCELLED"}

        created_assets = blender_utils.create_blender_mesh_from_afb(chosen_entry.name, data=model_data)
        
        base_path = chosen_entry.get_model_name().rsplit('\\', 1)[0]
        
        textures, texture_names = get_texture_items(self, context, texture_list=created_assets.get("textures", []), base_path=base_path, color_number=chosen_entry.colorNumber)
        

        if created_assets:
            blender_utils.create_and_assign_material(
                meshes=created_assets.get("meshes"),
                material_name=f"{chosen_entry.name}_Mat",
                texture_names= texture_names,
                texture_bytes= textures
            )

            armature = created_assets.get("armature")
            if armature:
                armature.rotation_euler[0] = math.radians(90)
                animations = chosen_entry.get_animations()
                if animations:
                    print(f"Importing {len(animations)} animations for {chosen_entry.name}...")
                    imported_count = 0

                    for slot, anim_bytes in animations:
                        action_name = f"{chosen_entry.name}_Anim_{slot}"
                        motion_data = core_parser.parse_motion_bytes(anim_bytes, action_name)
                        if motion_data:
                            blender_utils.apply_motion_to_armature(armature, motion_data, action_name)
                            imported_count += 1

                    if imported_count > 0 and armature.animation_data:
                        first_action_name = f"{chosen_entry.name}_Anim_{animations[0][0]}"
                        first_action = bpy.data.actions.get(first_action_name)
                        if first_action:
                            armature.animation_data.action = first_action
                            
                    end_time = time.perf_counter()

                    self.report({"INFO"}, f"Successfully imported: {chosen_entry.name} and {imported_count} animations. Execution took {end_time - start_time:.4f} seconds.")
                else:
                    end_time = time.perf_counter()
                    self.report({"INFO"}, f"Successfully imported: {chosen_entry.name} (No animations found). Execution took {end_time - start_time:.4f} seconds.")
            else:
                end_time = time.perf_counter()
                self.report({"INFO"}, f"Successfully imported: {chosen_entry.name}. Execution took {end_time - start_time:.4f} seconds.")
        else:
            self.report({"ERROR"}, f"Failed to import: {chosen_entry.name} model data invalid.")
            return {"CANCELLED"}
        
        end_time = time.perf_counter()

        execution_time = end_time - start_time

        print(f"Execution took {execution_time:.4f} seconds")

        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(LoadlistImporter.bl_idname, text="Guilty Gear 2 Overture Loadlist (.bin)")

classes = (GG2EntryItem, GG2_UL_EntryList, LoadlistEntrySelector, LoadlistImporter, GG2ImporterPreferences)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.WindowManager.gg2_import_entries = CollectionProperty(type=GG2EntryItem)
    bpy.types.WindowManager.gg2_active_entry_index = IntProperty(name="Active Entry Index", default=0)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)