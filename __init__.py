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


def _artpipe_get_wip_collection(asset_name):
    if not asset_name:
        return None

    root_collection = bpy.data.collections.get(asset_name)
    if root_collection is None:
        return None

    wip_name = _artpipe_collection_name("wip", asset_name)
    for child in root_collection.children:
        if child.name == wip_name:
            return child
    return None


def _artpipe_get_wip_child_collection(asset_name, base_name):
    wip_collection = _artpipe_get_wip_collection(asset_name)
    if wip_collection is None:
        return None

    child_name = _artpipe_collection_name(base_name, asset_name)
    for child in wip_collection.children:
        if child.name == child_name:
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


def _artpipe_configure_collection_exporter(
    collection,
    export_type,
    export_path,
    preset_ident="DEFAULT",
    property_overrides=None,
):
    type_config = {
        "FBX": {"handlers": ("IO_FH_fbx", "IO_FH_FBX")},
        "GLTF": {"handlers": ("IO_FH_gltf", "IO_FH_GLTF", "IO_FH_gltf2", "IO_FH_GLTF2")},
    }
    config = type_config.get(export_type)
    if config is None:
        raise RuntimeError(f"Unsupported export type: {export_type}")

    exporters = getattr(collection, "exporters", None)
    if exporters is None:
        raise RuntimeError("Collection Exporters API is not available on this collection.")

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
        raise RuntimeError(f"Failed to add {export_type} collection exporter.")

    exporter = getattr(exporters, "active", None)
    if exporter is None and len(exporters) > 0:
        exporter = exporters[0]
    if exporter is None:
        raise RuntimeError("Could not access the collection exporter.")

    props = getattr(exporter, "export_properties", None)
    if props is None:
        raise RuntimeError("Exporter has no export_properties.")

    if preset_ident and preset_ident != "DEFAULT":
        _artpipe_apply_preset_to_props(props, preset_ident)

    if hasattr(props, "filepath"):
        props.filepath = export_path
    else:
        setattr(props, "path", export_path)

    if property_overrides:
        for name, value in property_overrides.items():
            if hasattr(props, name):
                try:
                    setattr(props, name, value)
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


def _artpipe_export_collection(
    context,
    collection,
    export_type,
    export_path,
    preset_ident="DEFAULT",
    property_overrides=None,
):
    if not hasattr(bpy.ops.collection, "export_all"):
        raise RuntimeError("This feature requires Blender with Collection Exporters.")

    layer_collection = _artpipe_find_layer_collection(
        context.view_layer.layer_collection,
        collection,
    )
    if layer_collection is None:
        raise RuntimeError("Could not find the target LayerCollection.")

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

        _artpipe_configure_collection_exporter(
            collection,
            export_type,
            export_path,
            preset_ident,
            property_overrides,
        )
        bpy.ops.collection.export_all()
    finally:
        for attr, value in original_flags.items():
            try:
                setattr(layer_collection, attr, value)
            except Exception:
                pass


def _artpipe_find_substance_texture_files(texture_root):
    import os

    if not texture_root:
        return {}

    if not os.path.isdir(texture_root):
        return {}

    texture_map = {
        "base_color": ("basecolor", "base_color", "albedo", "diffuse", "color"),
        "roughness": ("roughness",),
        "metallic": ("metallic", "metalness"),
        "normal": ("normal",),
        "ao": ("ambientocclusion", "ambient_occlusion", "ao"),
        "height": ("height", "displacement", "disp"),
        "emission": ("emissive", "emission"),
        "opacity": ("opacity", "alpha"),
    }
    image_exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".tga", ".bmp", ".exr"}
    found = {}

    for root, _, files in os.walk(texture_root):
        for file_name in files:
            ext = os.path.splitext(file_name)[1].lower()
            if ext not in image_exts:
                continue
            lowered = os.path.splitext(file_name)[0].lower()
            compact = lowered.replace(" ", "").replace("-", "_")
            for key, aliases in texture_map.items():
                if key in found:
                    continue
                if any(alias in compact for alias in aliases):
                    found[key] = os.path.join(root, file_name)
                    break

    return found


def _artpipe_iter_substance_material_folders(asset_name):
    import os

    if not asset_name or not bpy.data.is_saved:
        return []

    blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
    export_root = os.path.join(blend_dir, "substance", asset_name, "export")
    if not os.path.isdir(export_root):
        return []

    material_folders = []
    for entry in os.scandir(export_root):
        if not entry.is_dir():
            continue

        material_name = entry.name.strip()
        if not material_name:
            continue

        texture_paths = _artpipe_find_substance_texture_files(entry.path)
        if texture_paths:
            material_folders.append((material_name, entry.path, texture_paths))

    return sorted(material_folders, key=lambda item: item[0].lower())


def _artpipe_load_image(texture_path, colorspace):
    import os

    abs_path = os.path.abspath(texture_path)
    image = None
    for existing in bpy.data.images:
        try:
            if os.path.abspath(bpy.path.abspath(existing.filepath)) == abs_path:
                image = existing
                break
        except Exception:
            pass

    if image is None:
        image = bpy.data.images.load(abs_path)
    else:
        try:
            image.reload()
        except Exception:
            pass

    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    return image


def _artpipe_build_substance_material(material, texture_paths):
    material.use_nodes = True
    node_tree = material.node_tree
    if node_tree is None:
        raise RuntimeError("Material has no node tree.")

    # Blender 4.2+ uses surface_render_method; older APIs use blend_method.
    if hasattr(material, "surface_render_method"):
        try:
            material.surface_render_method = "DITHERED"
        except (TypeError, ValueError):
            pass

    nodes = node_tree.nodes
    links = node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (900, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (600, 0)
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-800, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-550, 0)
    links.new(tex_coord.outputs["UV"], mapping.inputs["Vector"])

    def add_image_node(key, label, y_pos, colorspace):
        path = texture_paths.get(key)
        if not path:
            return None
        image = _artpipe_load_image(path, colorspace)
        node = nodes.new("ShaderNodeTexImage")
        node.name = f"ARTPIPE_{key.upper()}"
        node.label = label
        node.image = image
        node.location = (-250, y_pos)
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    base_node = add_image_node("base_color", "Base Color", 250, "sRGB")
    if base_node is not None:
        links.new(base_node.outputs["Color"], principled.inputs["Base Color"])

    roughness_node = add_image_node("roughness", "Roughness", 50, "Non-Color")
    if roughness_node is not None:
        links.new(roughness_node.outputs["Color"], principled.inputs["Roughness"])

    metallic_node = add_image_node("metallic", "Metallic", -150, "Non-Color")
    if metallic_node is not None:
        links.new(metallic_node.outputs["Color"], principled.inputs["Metallic"])

    ao_node = add_image_node("ao", "Ambient Occlusion", 450, "Non-Color")
    if ao_node is not None and base_node is not None:
        mix_node = nodes.new("ShaderNodeMixRGB")
        mix_node.blend_type = "MULTIPLY"
        mix_node.inputs["Fac"].default_value = 1.0
        mix_node.location = (180, 280)
        links.new(base_node.outputs["Color"], mix_node.inputs["Color1"])
        links.new(ao_node.outputs["Color"], mix_node.inputs["Color2"])
        links.new(mix_node.outputs["Color"], principled.inputs["Base Color"])

    normal_node = add_image_node("normal", "Normal", -350, "Non-Color")
    if normal_node is not None:
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (180, -350)
        links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

    height_node = add_image_node("height", "Height", -550, "Non-Color")
    if height_node is not None:
        displacement = nodes.new("ShaderNodeDisplacement")
        displacement.location = (180, -550)
        links.new(height_node.outputs["Color"], displacement.inputs["Height"])
        links.new(displacement.outputs["Displacement"], output.inputs["Displacement"])

    emission_node = add_image_node("emission", "Emission", -750, "sRGB")
    if emission_node is not None:
        links.new(emission_node.outputs["Color"], principled.inputs["Emission Color"])

    opacity_node = add_image_node("opacity", "Opacity", -950, "Non-Color")
    if opacity_node is not None:
        links.new(opacity_node.outputs["Color"], principled.inputs["Alpha"])
        if hasattr(material, "surface_render_method"):
            try:
                material.surface_render_method = "DITHERED"
            except (TypeError, ValueError):
                pass
        elif hasattr(material, "blend_method"):
            material.blend_method = "HASHED"


def _artpipe_create_or_refresh_substance_materials(asset_name):
    material_folders = _artpipe_iter_substance_material_folders(asset_name)
    if not material_folders:
        raise RuntimeError(
            "No Substance material folders with textures were found in the asset export folder."
        )

    materials = []
    for material_name, _, texture_paths in material_folders:
        material = bpy.data.materials.get(material_name)
        if material is None:
            material = bpy.data.materials.new(name=material_name)

        _artpipe_build_substance_material(material, texture_paths)
        materials.append(material)

    return materials


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

        try:
            _artpipe_export_collection(
                context,
                export_collection,
                export_type,
                export_path,
                preset_ident,
            )
            self.report({"INFO"}, f"Exported {export_type} to: {export_path}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Collection export failed: {exc}")
            return {"CANCELLED"}


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


class ARTPIPE_OT_open_substance_texture_path(Operator):
    bl_idname = "artpipe.open_substance_texture_path"
    bl_label = "Open Substance Texture Path"
    bl_description = "Open the Substance texture folder in the system file browser"
    bl_options = {"REGISTER"}

    mode: bpy.props.EnumProperty(
        items=(
            ("ROOT", "Root", "Open the asset Substance folder"),
            ("EXPORT", "Export", "Open the Substance export folder"),
            ("IMPORT", "Import", "Open the Substance import folder"),
            ("IMPORT_CAGE", "Import Cage", "Open the Substance cage import folder"),
        ),
        default="ROOT",
        options={"HIDDEN"},
    )

    @staticmethod
    def _resolve_target(asset_name):
        import os

        blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
        substance_dir = os.path.join(blend_dir, "substance", asset_name)
        return {
            "ROOT": substance_dir,
            "EXPORT": os.path.join(substance_dir, "export"),
            "IMPORT": os.path.join(substance_dir, "import"),
            "IMPORT_CAGE": os.path.join(substance_dir, "import_cage"),
        }

    def execute(self, context):
        import os
        import platform
        import subprocess

        scene = context.scene
        asset_name = scene.artpipe_asset_name
        if not asset_name or asset_name == "NONE":
            self.report({"ERROR"}, "Choose an asset first.")
            return {"CANCELLED"}

        if not bpy.data.is_saved:
            self.report({"ERROR"}, "Save the blend file first.")
            return {"CANCELLED"}

        target = self._resolve_target(asset_name).get(self.mode, self._resolve_target(asset_name)["ROOT"])

        if not os.path.isdir(target):
            try:
                os.makedirs(target, exist_ok=True)
            except Exception:
                self.report({"ERROR"}, f"Substance folder does not exist: {target}")
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


class ARTPIPE_OT_copy_substance_texture_path(Operator):
    bl_idname = "artpipe.copy_substance_texture_path"
    bl_label = "Copy Substance Texture Path"
    bl_description = "Copy the Substance folder path to the clipboard"
    bl_options = {"REGISTER"}

    mode: bpy.props.EnumProperty(
        items=(
            ("ROOT", "Root", "Copy the asset Substance folder path"),
            ("EXPORT", "Export", "Copy the Substance export folder path"),
            ("IMPORT", "Import", "Copy the Substance import folder path"),
            ("IMPORT_CAGE", "Import Cage", "Copy the Substance cage import folder path"),
        ),
        default="ROOT",
        options={"HIDDEN"},
    )

    def execute(self, context):
        import os

        scene = context.scene
        asset_name = scene.artpipe_asset_name
        if not asset_name or asset_name == "NONE":
            self.report({"ERROR"}, "Choose an asset first.")
            return {"CANCELLED"}

        if not bpy.data.is_saved:
            self.report({"ERROR"}, "Save the blend file first.")
            return {"CANCELLED"}

        target = ARTPIPE_OT_open_substance_texture_path._resolve_target(asset_name).get(
            self.mode,
            ARTPIPE_OT_open_substance_texture_path._resolve_target(asset_name)["ROOT"],
        )

        try:
            os.makedirs(target, exist_ok=True)
        except Exception:
            pass

        context.window_manager.clipboard = target
        self.report({"INFO"}, f"Copied path: {target}")
        return {"FINISHED"}


class ARTPIPE_OT_export_substance(Operator):
    bl_idname = "artpipe.export_substance"
    bl_label = "Exp. Substance"
    bl_description = "Export the substance collection to the Substance import folder as GLTF"
    bl_options = {"REGISTER", "UNDO"}

    cage: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context):
        import os

        scene = context.scene
        asset_name = scene.artpipe_asset_name
        if not asset_name or asset_name == "NONE":
            self.report({"ERROR"}, "Choose an asset first.")
            return {"CANCELLED"}

        if not bpy.data.is_saved:
            self.report({"ERROR"}, "Save the blend file first.")
            return {"CANCELLED"}

        base_name = "substance_cage" if self.cage else "substance"
        target_collection = _artpipe_get_wip_child_collection(asset_name, base_name)
        if target_collection is None:
            self.report({"ERROR"}, f"Missing collection '{_artpipe_collection_name(base_name, asset_name)}'.")
            return {"CANCELLED"}

        blend_dir = os.path.dirname(bpy.path.abspath(bpy.data.filepath))
        substance_dir = os.path.join(blend_dir, "substance", asset_name)
        export_dir = os.path.join(substance_dir, "export")
        import_dir_name = "import_cage" if self.cage else "import"
        import_dir = os.path.join(substance_dir, import_dir_name)

        try:
            os.makedirs(export_dir, exist_ok=True)
            os.makedirs(import_dir, exist_ok=True)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to create Substance folders: {exc}")
            return {"CANCELLED"}

        file_stem = f"{asset_name}_cage" if self.cage else asset_name
        export_path = os.path.join(import_dir, f"{file_stem}.glb")

        try:
            _artpipe_export_collection(
                context,
                target_collection,
                "GLTF",
                export_path,
                "DEFAULT",
                {
                    "export_apply": True,
                },
            )
            label = "Substance Cage" if self.cage else "Substance"
            self.report({"INFO"}, f"Exported {label} to: {export_path}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, f"Substance export failed: {exc}")
            return {"CANCELLED"}


class ARTPIPE_OT_load_substance_textures(Operator):
    bl_idname = "artpipe.load_substance_textures"
    bl_label = "Load Textures from Substance"
    bl_description = "Create or refresh Blender materials from textures found in the asset's Substance export folders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        asset_name = context.scene.artpipe_asset_name
        if not asset_name or asset_name == "NONE":
            self.report({"ERROR"}, "Choose an asset first.")
            return {"CANCELLED"}

        if not bpy.data.is_saved:
            self.report({"ERROR"}, "Save the blend file first.")
            return {"CANCELLED"}

        try:
            materials = _artpipe_create_or_refresh_substance_materials(asset_name)
            material_names = ", ".join(material.name for material in materials[:5])
            if len(materials) > 5:
                material_names += ", ..."
            self.report(
                {"INFO"},
                f"Loaded {len(materials)} Substance material(s): {material_names}",
            )
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
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
    bl_label = "Export Subatnce"
    bl_idname = "ARTPIPE_PT_export_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ArtPipe"
    bl_parent_id = "ARTPIPE_PT_main_panel"
    bl_order = 20

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        state = _artpipe_ui_state(context)
        scene = state["scene"]
        asset_name = state["asset_name"]

        row = layout.row(align=True)
        row.enabled = bool(asset_name)
        row.operator("artpipe.export_substance", text="Exp. Substance")
        copy_import = row.operator("artpipe.copy_substance_texture_path", text="", icon="COPYDOWN")
        copy_import.mode = "IMPORT"
        open_import = row.operator("artpipe.open_substance_texture_path", text="", icon="FOLDER_REDIRECT")
        open_import.mode = "IMPORT"

        row = layout.row(align=True)
        row.enabled = bool(asset_name)
        cage_op = row.operator("artpipe.export_substance", text="Exp. Substance Cage")
        cage_op.cage = True
        copy_import_cage = row.operator("artpipe.copy_substance_texture_path", text="", icon="COPYDOWN")
        copy_import_cage.mode = "IMPORT_CAGE"
        open_import_cage = row.operator("artpipe.open_substance_texture_path", text="", icon="FOLDER_REDIRECT")
        open_import_cage.mode = "IMPORT_CAGE"

        row = layout.row(align=True)
        row.enabled = bool(asset_name)
        row.operator("artpipe.load_substance_textures", text="Load Textures from Substance")
        open_export = row.operator("artpipe.copy_substance_texture_path", text="", icon="COPYDOWN")
        open_export.mode = "EXPORT"
        open_export = row.operator("artpipe.open_substance_texture_path", text="", icon="FOLDER_REDIRECT")
        open_export.mode = "EXPORT"

        if not asset_name:
            warning = layout.row()
            warning.alert = True
            warning.label(text="Choose an asset to export Substance files.", icon="INFO")


class ARTPIPE_PT_standard_export_settings(Panel):
    bl_label = "Export Engine"
    bl_idname = "ARTPIPE_PT_standard_export_settings"
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
    ARTPIPE_OT_copy_substance_texture_path,
    ARTPIPE_OT_open_substance_texture_path,
    ARTPIPE_OT_export_substance,
    ARTPIPE_OT_load_substance_textures,
    ARTPIPE_PT_main_panel,
    ARTPIPE_PT_asset_settings,
    ARTPIPE_PT_export_settings,
    ARTPIPE_PT_standard_export_settings,
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
