bl_info = {
    "name": "ArtPipe",
    "author": "Marek Hanzelka",
    "description": "Adds an ArtPipe sidebar panel with an asset name field.",
    "blender": (5, 0, 0),
    "version": (1, 0, 0),
    "location": "View3D > Sidebar > ArtPipe",
    "warning": "",
    "category": "3D View",
}

import bpy
from bpy.props import StringProperty
from bpy.types import Panel, Scene


class ARTPIPE_PT_main_panel(Panel):
    bl_label = "ArtPipe"
    bl_idname = "ARTPIPE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ArtPipe"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "artpipe_asset_name", text="Asset Name")


classes = (
    ARTPIPE_PT_main_panel,
)


def register():
    Scene.artpipe_asset_name = StringProperty(
        name="Asset Name",
        description="Name of the asset used by ArtPipe",
        default="",
    )

    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del Scene.artpipe_asset_name

