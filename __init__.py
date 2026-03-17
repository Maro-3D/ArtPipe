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


def _artpipe_export_preset_items(self, context):
    import os

    items = [("DEFAULT", "Default", "Use Blender's default export settings")]
    type_map = {
        "FBX": "export_scene.fbx",
        "GLTF": "export_scene.gltf",
    }

    try:
        from bpy.utils import preset_paths

        for type_key, folder_name in type_map.items():
            for base in preset_paths("operator"):
                preset_dir = os.path.join(base, folder_name)
                if not os.path.isdir(preset_dir):
                    continue
                for file_name in sorted(os.listdir(preset_dir)):
                    if not file_name.lower().endswith(".py"):
                        continue
                    ident_raw = os.path.splitext(file_name)[0]
                    full_ident = f"{type_key}__{ident_raw}"
                    readable = ident_raw.replace("_", " ").title()
                    items.append(
                        (
                            full_ident,
                            f"{type_key} - {readable}",
                            f"{type_key} preset: {ident_raw}",
                        )
                    )
    except Exception:
        pass

    seen = set()
    unique_items = []
    for item in items:
        if item[0] in seen:
            continue
        seen.add(item[0])
        unique_items.append(item)
    return unique_items


def _artpipe_find_preset_path(ident):
    import os

    if not ident or ident == "DEFAULT" or "__" not in ident:
        return None

    type_key, name = ident.split("__", 1)
    type_map = {
        "FBX": "export_scene.fbx",
        "GLTF": "export_scene.gltf",
    }
    folder_name = type_map.get(type_key)
    if not folder_name:
        return None

    try:
        from bpy.utils import preset_paths

        for base in preset_paths("operator"):
            preset_dir = os.path.join(base, folder_name)
            if not os.path.isdir(preset_dir):
                continue
            candidate = os.path.join(preset_dir, f"{name}.py")
            if os.path.isfile(candidate):
                return candidate
    except Exception:
        pass
    return None


def _artpipe_apply_preset_to_props(props, ident):
    import ast

    path = _artpipe_find_preset_path(ident)
    if not path:
        return False

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line.startswith("op.") or "=" not in line:
                    continue
                try:
                    lhs, rhs = line.split("=", 1)
                except ValueError:
                    continue
                lhs = lhs.strip()
                rhs = rhs.strip()
                if not lhs.startswith("op."):
                    continue
                name = lhs[3:].strip()
                if not name.replace("_", "").isalnum():
                    continue
                try:
                    value = ast.literal_eval(rhs)
                except Exception:
                    value = rhs.strip()
                try:
                    if hasattr(props, name):
                        setattr(props, name, value)
                except Exception:
                    pass
        return True
    except Exception:
        return False


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
    export_collection = _artpipe_get_export_collection(asset_name)
    return {
        "scene": scene,
        "asset_name": asset_name,
        "asset_collection": asset_collection,
        "export_collection": export_collection,
    }


def _artpipe_get_asset_value(asset_name, key, default=""):
    if not asset_name:
        return default
    asset_collection = bpy.data.collections.get(asset_name)
    if asset_collection is None:
        return default
    try:
        return asset_collection.get(key, default)
    except Exception:
        return default


def _artpipe_set_asset_value(asset_name, key, value):
    if not asset_name:
        return
    asset_collection = bpy.data.collections.get(asset_name)
    if asset_collection is None:
        return
    try:
        asset_collection[key] = value
    except Exception:
        pass


def _artpipe_on_asset_changed(self, context):
    asset_name = self.artpipe_asset_name
    if not asset_name or asset_name == "NONE":
        self.artpipe_export_preset = "DEFAULT"
        self.artpipe_export_path = ""
        return

    self.artpipe_export_preset = _artpipe_get_asset_value(
        asset_name,
        "artpipe_export_preset",
        "DEFAULT",
    )
    self.artpipe_export_path = _artpipe_get_asset_value(
        asset_name,
        "artpipe_export_path",
        "",
    )


def _artpipe_on_export_preset_changed(self, context):
    asset_name = self.artpipe_asset_name
    if not asset_name or asset_name == "NONE":
        return
    _artpipe_set_asset_value(asset_name, "artpipe_export_preset", self.artpipe_export_preset)


def _artpipe_on_export_path_changed(self, context):
    asset_name = self.artpipe_asset_name
    if not asset_name or asset_name == "NONE":
        return
    _artpipe_set_asset_value(asset_name, "artpipe_export_path", self.artpipe_export_path)


def _artpipe_set_collection_color(collection, color_tag):
    try:
        if hasattr(collection, "color_tag"):
            collection.color_tag = color_tag
    except Exception:
        pass


def _artpipe_collection_name(base_name, asset_name):
    return f"{base_name}_{asset_name}"


def _artpipe_get_export_collection(asset_name):
    if not asset_name:
        return None

    root_collection = bpy.data.collections.get(asset_name)
    if root_collection is None:
        return None

    export_name = _artpipe_collection_name("export", asset_name)
    for child in root_collection.children:
        if child.name == export_name:
            return child
    return None


def _artpipe_find_layer_collection(layer_collection, target_collection):
    try:
        if layer_collection.collection == target_collection:
            return layer_collection
        for child in layer_collection.children:
            result = _artpipe_find_layer_collection(child, target_collection)
            if result is not None:
                return result
    except Exception:
        pass
    return None


def _artpipe_remap_user_in_path(path):
    try:
        if not path:
            return path

        import getpass
        import os
        import re as re_module

        normalized = os.path.expandvars(path).replace("/", os.sep).replace("\\", os.sep)
        if os.name == "nt":
            parts = re_module.split(r"[\\/]+", normalized)
            users_idx = None
            for index, part in enumerate(parts):
                if part and part.lower() == "users":
                    users_idx = index
                    break
            if users_idx is not None and users_idx + 1 < len(parts):
                current_user = os.environ.get("USERNAME") or getpass.getuser() or ""
                if current_user and parts[users_idx + 1].lower() != current_user.lower():
                    parts[users_idx + 1] = current_user
                    return os.sep.join(parts)
        else:
            parts = re_module.split(r"/+", normalized)
            lowered = [part.lower() for part in parts]
            for anchor in ("users", "home"):
                if anchor in lowered:
                    index = lowered.index(anchor)
                    if index + 1 < len(parts):
                        current_user = getpass.getuser() or ""
                        if current_user and parts[index + 1] != current_user:
                            parts[index + 1] = current_user
                            return "/".join(parts)
    except Exception:
        pass
    return path


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


class ARTPIPE_OT_export_preset_file(Operator):
    bl_idname = "artpipe.export_preset_file"
    bl_label = "Export Preset File"
    bl_description = "Save the selected preset to a file"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext: StringProperty(default=".py", options={"HIDDEN"})
    filter_glob: StringProperty(default="*.py", options={"HIDDEN"})

    def invoke(self, context, event):
        import os

        asset_name = context.scene.artpipe_asset_name
        ident = _artpipe_get_asset_value(asset_name, "artpipe_export_preset", "DEFAULT")
        path = _artpipe_find_preset_path(ident)
        if not path:
            self.report({"ERROR"}, "No valid preset selected (or Default is selected).")
            return {"CANCELLED"}

        self.filepath = os.path.basename(path)
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        asset_name = context.scene.artpipe_asset_name
        ident = _artpipe_get_asset_value(asset_name, "artpipe_export_preset", "DEFAULT")
        src_path = _artpipe_find_preset_path(ident)
        if not src_path:
            self.report({"ERROR"}, "Preset not found.")
            return {"CANCELLED"}

        export_type = "FBX"
        if "__" in ident:
            export_type = ident.split("__")[0]

        try:
            with open(src_path, "r", encoding="utf-8") as handle:
                content = handle.read()

            header = f"# ArtPipe: {export_type}\n"
            if not content.startswith("# ArtPipe:"):
                content = header + content

            with open(self.filepath, "w", encoding="utf-8") as handle:
                handle.write(content)
            self.report({"INFO"}, f"Preset saved to: {self.filepath}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to save preset: {exc}")
            return {"CANCELLED"}


class ARTPIPE_OT_import_preset_file(Operator):
    bl_idname = "artpipe.import_preset_file"
    bl_label = "Import Preset File"
    bl_description = "Import a preset file into Blender's user presets"
    bl_options = {"REGISTER"}

    filepath: StringProperty(subtype="FILE_PATH")
    filename_ext: StringProperty(default=".py", options={"HIDDEN"})
    filter_glob: StringProperty(default="*.py", options={"HIDDEN"})
    preset_type: EnumProperty(
        name="Preset Type",
        description="Type of the preset being imported",
        items=[
            ("FBX", "FBX", "FBX Export Preset"),
            ("GLTF", "GLTF", "GLTF Export Preset"),
        ],
        default="FBX",
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        import os
        import shutil

        if not os.path.isfile(self.filepath):
            self.report({"ERROR"}, "File not found.")
            return {"CANCELLED"}

        detected_type = None
        try:
            with open(self.filepath, "r", encoding="utf-8") as handle:
                first_line = handle.readline()
                if first_line.startswith("# ArtPipe:"):
                    raw_type = first_line.split(":", 1)[1].strip()
                    if raw_type in ("FBX", "GLTF"):
                        detected_type = raw_type
        except Exception:
            pass

        final_type = detected_type if detected_type else self.preset_type
        target_map = {
            "FBX": "export_scene.fbx",
            "GLTF": "export_scene.gltf",
        }
        folder_name = target_map.get(final_type)
        if not folder_name:
            return {"CANCELLED"}

        user_path = bpy.utils.user_resource("SCRIPTS", path="presets/operator", create=True)
        target_dir = os.path.join(user_path, folder_name)
        os.makedirs(target_dir, exist_ok=True)

        filename = os.path.basename(self.filepath)
        dest_path = os.path.join(target_dir, filename)
        try:
            shutil.copy2(self.filepath, dest_path)
            self.report({"INFO"}, f"Imported {final_type} preset: {filename}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to import preset: {exc}")
            return {"CANCELLED"}


class ARTPIPE_OT_export(Operator):
    bl_idname = "artpipe.export"
    bl_label = "Export"
    bl_description = "Prepare export directories and export the active asset's EXPORT collection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import os

        scene = context.scene
        asset_name = scene.artpipe_asset_name
        if not asset_name or asset_name == "NONE" or re.fullmatch(r"[a-z0-9_]+", asset_name) is None:
            self.report({"ERROR"}, "Select a valid snake_case asset first.")
            return {"CANCELLED"}

        base_path = (_artpipe_get_asset_value(asset_name, "artpipe_export_path", "") or "").strip()
        if not base_path:
            self.report({"ERROR"}, "Export Path is empty.")
            return {"CANCELLED"}

        try:
            abs_base = bpy.path.abspath(base_path)
        except Exception:
            abs_base = base_path

        try:
            remapped = _artpipe_remap_user_in_path(abs_base)
            if remapped:
                abs_base = remapped
        except Exception:
            pass

        asset_dir = os.path.join(abs_base, asset_name)
        preset_ident = _artpipe_get_asset_value(asset_name, "artpipe_export_preset", "DEFAULT") or "DEFAULT"
        export_type = "FBX"
        if "__" in preset_ident:
            export_type = preset_ident.split("__")[0]

        type_config = {
            "FBX": {"ext": ".fbx", "handlers": ("IO_FH_fbx", "IO_FH_FBX")},
            "GLTF": {"ext": ".glb", "handlers": ("IO_FH_gltf", "IO_FH_GLTF", "IO_FH_gltf2", "IO_FH_GLTF2")},
        }
        config = type_config.get(export_type, type_config["FBX"])
        export_path = os.path.join(asset_dir, f"{asset_name}{config['ext']}")

        try:
            os.makedirs(asset_dir, exist_ok=True)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to create export directory: {exc}")
            return {"CANCELLED"}

        export_collection = _artpipe_get_export_collection(asset_name)
        if export_collection is None:
            self.report({"ERROR"}, "Missing export collection. Create the asset setup first.")
            return {"CANCELLED"}

        if not hasattr(bpy.ops.collection, "export_all"):
            self.report({"ERROR"}, "This feature requires Blender with Collection Exporters.")
            return {"CANCELLED"}

        layer_collection = _artpipe_find_layer_collection(
            context.view_layer.layer_collection,
            export_collection,
        )
        if layer_collection is None:
            self.report({"ERROR"}, "Could not find the export LayerCollection.")
            return {"CANCELLED"}

        original_flags = {}
        visibility_attrs = ("exclude", "hide_viewport", "holdout", "indirect_only")
        try:
            for attr in visibility_attrs:
                try:
                    original_flags[attr] = getattr(layer_collection, attr)
                except Exception:
                    pass
            for attr in visibility_attrs:
                try:
                    setattr(layer_collection, attr, False)
                except Exception:
                    pass
            try:
                context.view_layer.active_layer_collection = layer_collection
            except Exception:
                pass
        except Exception:
            pass

        try:
            exporters = getattr(export_collection, "exporters", None)
            if exporters is None:
                self.report({"ERROR"}, "Collection Exporters API is not available on the export collection.")
                return {"CANCELLED"}

            try:
                while len(exporters) > 0:
                    exporters.remove(exporters[0])
            except Exception:
                pass

            added = False
            for handler_name in config["handlers"]:
                try:
                    bpy.ops.collection.exporter_add(name=handler_name)
                    added = True
                    break
                except Exception:
                    continue
            if not added:
                self.report({"ERROR"}, f"Failed to add {export_type} collection exporter.")
                return {"CANCELLED"}

            try:
                exporter = getattr(exporters, "active", None)
                if exporter is None and len(exporters) > 0:
                    exporter = exporters[0]
            except Exception:
                exporter = None
            if exporter is None:
                self.report({"ERROR"}, "Could not access the export collection exporter.")
                return {"CANCELLED"}

            props = getattr(exporter, "export_properties", None)
            if props is None:
                self.report({"ERROR"}, "Exporter has no export_properties.")
                return {"CANCELLED"}

            if preset_ident and preset_ident != "DEFAULT":
                try:
                    _artpipe_apply_preset_to_props(props, preset_ident)
                except Exception:
                    pass

            if hasattr(props, "filepath"):
                try:
                    props.filepath = export_path
                except Exception:
                    pass
            else:
                try:
                    setattr(props, "path", export_path)
                except Exception:
                    pass

            if preset_ident and preset_ident != "DEFAULT":
                for attr in ("preset", "preset_name"):
                    if hasattr(exporter, attr):
                        try:
                            setattr(exporter, attr, preset_ident)
                            break
                        except Exception:
                            pass

            try:
                bpy.ops.collection.export_all()
                self.report({"INFO"}, f"Exported {export_type} to: {export_path}")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, f"Collection export failed: {exc}")
                return {"CANCELLED"}
        finally:
            try:
                for attr, value in original_flags.items():
                    try:
                        setattr(layer_collection, attr, value)
                    except Exception:
                        pass
            except Exception:
                pass


class ARTPIPE_OT_open_export_path(Operator):
    bl_idname = "artpipe.open_export_path"
    bl_label = "Open Export Path"
    bl_description = "Open the Export Path in the system file browser"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import os
        import platform
        import subprocess

        scene = context.scene
        asset_name = scene.artpipe_asset_name
        path = (_artpipe_get_asset_value(asset_name, "artpipe_export_path", "") or "").strip()
        if not path:
            self.report({"ERROR"}, "Export Path is empty.")
            return {"CANCELLED"}

        try:
            abs_path = bpy.path.abspath(path)
        except Exception:
            abs_path = path

        try:
            remapped = _artpipe_remap_user_in_path(abs_path)
            if remapped:
                abs_path = remapped
        except Exception:
            pass

        target = abs_path
        if os.path.isfile(target):
            target = os.path.dirname(target) or target

        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except Exception:
                self.report({"ERROR"}, f"Directory does not exist: {target}")
                return {"CANCELLED"}

        try:
            bpy.ops.wm.path_open(filepath=target)
            return {"FINISHED"}
        except Exception:
            pass

        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(target)
            elif system == "Darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to open path: {exc}")
            return {"CANCELLED"}


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


class ARTPIPE_PT_export_settings(Panel):
    bl_label = "Export Settings"
    bl_idname = "ARTPIPE_PT_export_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ArtPipe"
    bl_parent_id = "ARTPIPE_PT_main_panel"
    bl_order = 30

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        state = _artpipe_ui_state(context)
        scene = state["scene"]
        asset_name = state["asset_name"]
        export_collection = state["export_collection"]

        row = layout.row(align=True)
        row.prop(scene, "artpipe_export_preset", text="Export Preset")
        row.operator("artpipe.export_preset_file", text="", icon="EXPORT")
        row.operator("artpipe.import_preset_file", text="", icon="IMPORT")

        row = layout.row(align=True)
        row.prop(scene, "artpipe_export_path", text="Export Path")
        row.operator("artpipe.open_export_path", text="", icon="FOLDER_REDIRECT")

        export_ready = (
            bool(asset_name)
            and bool(scene.artpipe_export_path)
            and export_collection is not None
            and hasattr(bpy.ops.collection, "export_all")
        )
        row = layout.row(align=True)
        row.enabled = export_ready
        row.operator("artpipe.export", icon="EXPORT", text="Export")

        if not export_ready:
            warning = layout.column(align=True)
            warning.alert = True
            warning.label(text="Export prerequisites:", icon="INFO")
            if not asset_name:
                warning.label(text="- Choose an asset")
            if not scene.artpipe_export_path:
                warning.label(text="- Choose an Export Path")
            if export_collection is None:
                warning.label(text="- Asset is missing its export collection")
            if not hasattr(bpy.ops.collection, "export_all"):
                warning.label(text="- Requires Blender with Collection Exporters")


classes = (
    ARTPIPE_OT_add_asset,
    ARTPIPE_OT_setup_collections,
    ARTPIPE_OT_export_preset_file,
    ARTPIPE_OT_import_preset_file,
    ARTPIPE_OT_export,
    ARTPIPE_OT_open_export_path,
    ARTPIPE_PT_main_panel,
    ARTPIPE_PT_asset_settings,
    ARTPIPE_PT_export_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    if not hasattr(Scene, "artpipe_asset_name"):
        Scene.artpipe_asset_name = EnumProperty(
            name="Asset",
            description="Choose the active ArtPipe asset",
            items=_artpipe_asset_items,
            update=_artpipe_on_asset_changed,
        )
    if not hasattr(Scene, "artpipe_armature_obj"):
        Scene.artpipe_armature_obj = PointerProperty(
            name="Armature",
            description="Armature associated with this asset",
            type=Object,
            poll=artpipe_armature_poll,
        )
    if not hasattr(Scene, "artpipe_export_preset"):
        Scene.artpipe_export_preset = EnumProperty(
            name="Export Preset",
            description="Choose export preset (FBX, GLTF)",
            items=_artpipe_export_preset_items,
            update=_artpipe_on_export_preset_changed,
        )
    if not hasattr(Scene, "artpipe_export_path"):
        Scene.artpipe_export_path = StringProperty(
            name="Export Path",
            description="Pick the directory where the asset should be exported",
            subtype="DIR_PATH",
            default="",
            update=_artpipe_on_export_path_changed,
        )


def unregister():
    if hasattr(Scene, "artpipe_export_path"):
        del Scene.artpipe_export_path
    if hasattr(Scene, "artpipe_export_preset"):
        del Scene.artpipe_export_preset
    if hasattr(Scene, "artpipe_armature_obj"):
        del Scene.artpipe_armature_obj
    if hasattr(Scene, "artpipe_asset_name"):
        del Scene.artpipe_asset_name

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
