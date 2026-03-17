bl_info = {
    "name": "Guilty Gear 2 Overture Loadlist importer",
    "author": "Brunardo",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import",
    "description": "Uses the loadlist.bin to import full characters with meshes, textures and animations",
    "category": "Import-Export",
}


if "bpy" in locals():
    import importlib
    importlib.reload(config)
    importlib.reload(core_parser)
    importlib.reload(blender_utils)
    importlib.reload(operators)
else:
    import bpy
    from . import config
    from . import core_parser
    from . import blender_utils
    from . import operators


def register():
    operators.register()

def unregister():
    operators.unregister()

if __name__ == "__main__":
    register()