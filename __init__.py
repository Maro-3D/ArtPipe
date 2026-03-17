bl_info = {
    "name": "ArtPipe",
    "author": "Marek Hanzelka",
    "description": "Adds an ArtPipe sidebar panel with asset settings.",
    "blender": (5, 0, 0),
    "version": (1, 0, 0),
    "location": "View3D > Sidebar > ArtPipe",
    "warning": "",
    "category": "3D View",
}

import bpy
import re
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Object, Operator, Panel, Scene


def _artpipe_is_asset_collection(collection):
    asset_name = collection.name
    child_names = {child.name for child in collection.children}
    return (
        _artpipe_collection_name("wip", asset_name) in child_names
        and _artpipe_collection_name("export", asset_name) in child_names
    )


def _artpipe_asset_items(self, context):
    items = []
    if context is not None:
        for collection in context.scene.collection.children:
            if _artpipe_is_asset_collection(collection):
                items.append((collection.name, collection.name, "ArtPipe asset collection"))

    items.sort(key=lambda item: item[1].lower())
    if not items:
        items.append(("NONE", "None", "No ArtPipe assets found"))
    return items


def artpipe_armature_poll(self, obj):
    try:
        return obj is not None and getattr(obj, "type", None) == "ARMATURE"
    except Exception:
        return False


def _artpipe_ui_state(context):
    scene = context.scene
    asset_name = scene.artpipe_asset_name
    if asset_name == "NONE":
        asset_name = ""
    asset_collection = bpy.data.collections.get(asset_name) if asset_name else None
    return {
        "scene": scene,
        "asset_name": asset_name,
        "asset_collection": asset_collection,
    }


def _artpipe_set_collection_color(collection, color_tag):
    try:
        if hasattr(collection, "color_tag"):
            collection.color_tag = color_tag
    except Exception:
        pass


def _artpipe_collection_name(base_name, asset_name):
    return f"{base_name}_{asset_name}"


def _artpipe_ensure_child_collection(parent, child_name, color_tag="NONE"):
    child = None
    for existing in parent.children:
        if existing.name == child_name:
            child = existing
            break

    if child is None:
        child = bpy.data.collections.new(child_name)

    already_linked = any(existing == child for existing in parent.children)
    if not already_linked:
        parent.children.link(child)

    _artpipe_set_collection_color(child, color_tag)
    return child


def _artpipe_create_asset_setup(context, asset_name):
    root_collection = bpy.data.collections.get(asset_name)
    if root_collection is None:
        root_collection = bpy.data.collections.new(asset_name)

    if not any(existing == root_collection for existing in context.scene.collection.children):
        context.scene.collection.children.link(root_collection)

    wip_collection = _artpipe_ensure_child_collection(
        root_collection, _artpipe_collection_name("wip", asset_name), "COLOR_05"
    )
    _artpipe_ensure_child_collection(
        root_collection,
        _artpipe_collection_name("export", asset_name),
        "COLOR_04",
    )

    _artpipe_ensure_child_collection(
        wip_collection,
        _artpipe_collection_name("high_poly", asset_name),
        "COLOR_05",
    )
    _artpipe_ensure_child_collection(
        wip_collection,
        _artpipe_collection_name("low_poly", asset_name),
        "COLOR_05",
    )
    _artpipe_ensure_child_collection(
        wip_collection,
        _artpipe_collection_name("substance", asset_name),
        "COLOR_06",
    )
    _artpipe_ensure_child_collection(
        wip_collection,
        _artpipe_collection_name("substance_cage", asset_name),
        "COLOR_06",
    )


class ARTPIPE_OT_setup_collections(Operator):
    bl_idname = "artpipe.setup_collections"
    bl_label = "Setup Collections"
    bl_description = "Create the ArtPipe collection hierarchy for the current asset"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        asset_name = getattr(self, "asset_name", "") or context.scene.artpipe_asset_name
        asset_name = asset_name.strip()
        if not asset_name:
            self.report({"ERROR"}, "Enter an asset name first.")
            return {"CANCELLED"}

        if re.fullmatch(r"[a-z0-9_]+", asset_name) is None:
            self.report({"ERROR"}, "Asset name must use snake_case.")
            return {"CANCELLED"}

        _artpipe_create_asset_setup(context, asset_name)
        self.report({"INFO"}, f"Created collection setup for '{asset_name}'.")
        context.scene.artpipe_asset_name = asset_name
        return {"FINISHED"}


class ARTPIPE_OT_add_asset(Operator):
    bl_idname = "artpipe.add_asset"
    bl_label = "Add Asset"
    bl_description = "Create a new ArtPipe asset collection"
    bl_options = {"REGISTER", "UNDO"}

    asset_name: StringProperty(
        name="Asset name",
        description="snake_case only: lowercase, digits and underscores",
        default="",
    )

    def invoke(self, context, event):
        current_asset = context.scene.artpipe_asset_name
        if current_asset != "NONE":
            self.asset_name = current_asset
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        row = layout.row()
        row.alert = bool(self.asset_name) and re.fullmatch(r"[a-z0-9_]+", self.asset_name) is None
        row.prop(self, "asset_name", text="Asset name")

        if self.asset_name and re.fullmatch(r"[a-z0-9_]+", self.asset_name) is None:
            warning = layout.row()
            warning.alert = True
            warning.label(
                text="Use snake_case: lowercase letters, numbers, underscores.",
                icon="ERROR",
            )

    def execute(self, context):
        name = (self.asset_name or "").strip()
        if not name:
            self.report({"ERROR"}, "Enter an asset name first.")
            return {"CANCELLED"}

        if re.fullmatch(r"[a-z0-9_]+", name) is None:
            self.report({"ERROR"}, "Asset name must use snake_case.")
            return {"CANCELLED"}

        existing = bpy.data.collections.get(name)
        if existing is not None:
            if _artpipe_is_asset_collection(existing):
                self.report({"ERROR"}, f"Collection '{name}' already exists.")
                context.scene.artpipe_asset_name = name
                return {"CANCELLED"}

            self.report(
                {"ERROR"},
                f"Collection '{name}' exists but is not an ArtPipe asset collection.",
            )
            return {"CANCELLED"}

        _artpipe_create_asset_setup(context, name)
        context.scene.artpipe_asset_name = name
        self.report({"INFO"}, f"Created collection setup for '{name}'.")
        return {"FINISHED"}


class ARTPIPE_PT_main_panel(Panel):
    bl_label = "ArtPipe"
    bl_idname = "ARTPIPE_PT_main_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ArtPipe"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False


class ARTPIPE_PT_asset_settings(Panel):
    bl_label = "Asset & Collections"
    bl_idname = "ARTPIPE_PT_asset_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ArtPipe"
    bl_parent_id = "ARTPIPE_PT_main_panel"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        state = _artpipe_ui_state(context)
        scene = state["scene"]
        asset_name = state["asset_name"]

        row = layout.row(align=True)
        row.prop(scene, "artpipe_asset_name", text="Asset")
        row.operator("artpipe.add_asset", text="", icon="ADD")

        row = layout.row()
        row.prop(scene, "artpipe_armature_obj", text="Armature")

        if not asset_name:
            info = layout.row()
            info.label(text="Add an asset to create its collection setup.", icon="INFO")


classes = (
    ARTPIPE_OT_add_asset,
    ARTPIPE_OT_setup_collections,
    ARTPIPE_PT_main_panel,
    ARTPIPE_PT_asset_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(Scene, "artpipe_asset_name"):
        Scene.artpipe_asset_name = EnumProperty(
            name="Asset",
            description="Choose the active ArtPipe asset",
            items=_artpipe_asset_items,
        )
    if not hasattr(Scene, "artpipe_armature_obj"):
        Scene.artpipe_armature_obj = PointerProperty(
            name="Armature",
            description="Armature associated with this asset",
            type=Object,
            poll=artpipe_armature_poll,
        )


def unregister():
    if hasattr(Scene, "artpipe_armature_obj"):
        del Scene.artpipe_armature_obj
    if hasattr(Scene, "artpipe_asset_name"):
        del Scene.artpipe_asset_name

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
