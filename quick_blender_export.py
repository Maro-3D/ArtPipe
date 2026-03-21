import os
import re

from PySide6 import QtCore, QtWidgets

import substance_painter.ui
import substance_painter.project
import substance_painter.export
import substance_painter.textureset
import substance_painter.resource
import substance_painter.exception

plugin_widgets = []


def _main_window():
    return substance_painter.ui.get_main_window()


def _candidate_export_preset_urls():
    painter_user_dir = os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "Adobe",
        "Adobe Substance 3D Painter"
    )
    export_presets_dir = os.path.join(painter_user_dir, "assets", "export-presets")

    for preset_name in ("Blender", "blender"):
        preset_path = os.path.join(export_presets_dir, f"{preset_name}.spexp")
        if os.path.isfile(preset_path):
            yield substance_painter.resource.ResourceID(
                context="export-presets",
                name=preset_name
            ).url()

    for preset_name in (
        "Blender (Principled BSDF)",
        "Blender",
    ):
        yield substance_painter.resource.ResourceID(
            context="starter_assets",
            name=preset_name
        ).url()


def _find_working_export_preset(base_export_config):
    for preset_url in _candidate_export_preset_urls():
        export_config = dict(base_export_config)
        export_config["defaultExportPreset"] = preset_url
        try:
            substance_painter.export.list_project_textures(export_config)
            return preset_url
        except Exception:
            continue

    return None


def _ensure_project_is_saved(message_title="Export"):
    project_file = substance_painter.project.file_path()

    if not project_file or not os.path.isfile(project_file):
        QtWidgets.QMessageBox.warning(
            _main_window(),
            message_title,
            "This project has not been saved yet.\n\n"
            "Please save the .spp project manually first, then run the export again."
        )
        return None

    normalized_project_file = os.path.normcase(os.path.normpath(project_file))
    if "starter_assets" + os.sep + "templates" in normalized_project_file:
        QtWidgets.QMessageBox.warning(
            _main_window(),
            message_title,
            "This is a read-only starter template project.\n\n"
            "Please use Save As and save it as your own .spp project first, then run the export again."
        )
        return None

    project_dir = os.path.dirname(project_file)
    if not os.access(project_dir, os.W_OK):
        QtWidgets.QMessageBox.warning(
            _main_window(),
            message_title,
            "The current project folder is not writable.\n\n"
            "Please save the .spp project to a writable folder first, then run the export again."
        )
        return None

    return project_file


def _next_incremental_save_path(project_file):
    project_dir = os.path.dirname(project_file)
    base_name = os.path.splitext(os.path.basename(project_file))[0]
    match = re.match(r"^(.*?)(?:_(\d+))?$", base_name)
    root_name = match.group(1) if match else base_name
    current_index = int(match.group(2)) if match and match.group(2) else 0

    next_index = current_index + 1
    while True:
        candidate_name = f"{root_name}_{next_index}.spp"
        candidate_path = os.path.join(project_dir, candidate_name)
        if not os.path.exists(candidate_path):
            return candidate_path
        next_index += 1


def _project_export_base_name(project_file):
    base_name = os.path.splitext(os.path.basename(project_file))[0]
    return re.sub(r"_\d+$", "", base_name)


def _extract_texture_suffix(file_name):
    name_root, _ = os.path.splitext(os.path.basename(file_name))
    parts = name_root.split("_")
    if len(parts) >= 2:
        return parts[-1]
    return name_root


def _renamed_export_file_name(project_file, file_name):
    _, extension = os.path.splitext(file_name)
    suffix = _extract_texture_suffix(file_name)
    return f"T_{_project_export_base_name(project_file)}_{suffix}{extension}"


def _matching_texture_set_folder(file_name, texture_set_names):
    name_root, _ = os.path.splitext(os.path.basename(file_name))

    for texture_set_name in texture_set_names:
        if name_root == texture_set_name or name_root.startswith(texture_set_name + "_"):
            return texture_set_name

    return None


def _organize_exported_textures(project_file, texture_set_names):
    export_dir = os.path.join(os.path.dirname(project_file), "export")
    export_prefix = f"T_{_project_export_base_name(project_file)}_"
    sorted_texture_set_names = sorted(
        {name for name in texture_set_names if name},
        key=len,
        reverse=True
    )

    for file_name in os.listdir(export_dir):
        source_path = os.path.join(export_dir, file_name)
        if not os.path.isfile(source_path):
            continue

        texture_set_folder = _matching_texture_set_folder(file_name, sorted_texture_set_names)
        target_dir = export_dir
        target_name = file_name

        if texture_set_folder:
            target_dir = os.path.join(export_dir, texture_set_folder)
            os.makedirs(target_dir, exist_ok=True)

        if not file_name.startswith(export_prefix):
            target_name = _renamed_export_file_name(project_file, file_name)

        target_path = os.path.join(target_dir, target_name)

        if (
            os.path.normcase(os.path.normpath(source_path)) ==
            os.path.normcase(os.path.normpath(target_path))
        ):
            continue

        os.replace(source_path, target_path)


def export_blender_textures():
    if not substance_painter.project.is_open():
        QtWidgets.QMessageBox.warning(_main_window(), "Export", "No project is open.")
        return

    project_path = _ensure_project_is_saved("Export")
    if not project_path:
        return

    project_dir = os.path.dirname(project_path)
    export_dir = os.path.join(project_dir, "export")
    os.makedirs(export_dir, exist_ok=True)

    export_list = []
    texture_set_names = []
    for texture_set in substance_painter.textureset.all_texture_sets():
        texture_set_names.append(str(texture_set.name))
        for stack in texture_set.all_stacks():
            export_list.append({
                "rootPath": str(stack)
            })

    config = {
        "exportPath": export_dir,
        "exportList": export_list,
        "exportShaderParams": False,
        "exportParameters": [
            {
                "parameters": {
                    "paddingAlgorithm": "infinite"
                }
            }
        ]
    }

    preset_url = _find_working_export_preset(config)
    if not preset_url:
        QtWidgets.QMessageBox.warning(
            _main_window(),
            "Export",
            "No valid export preset was found.\n\n"
            "Expected either the built-in preset "
            "'Blender (Principled BSDF)' or a user preset named "
            "'Blender.spexp' in Documents/Adobe/Adobe Substance 3D Painter/"
            "assets/export-presets."
        )
        return

    config["defaultExportPreset"] = preset_url

    try:
        result = substance_painter.export.export_project_textures(config)
        if result.status != substance_painter.export.ExportStatus.Success:
            QtWidgets.QMessageBox.warning(
                _main_window(),
                "Export",
                f"Export finished with status: {result.status}\n\n{result.message}"
            )
            return

        _organize_exported_textures(project_path, texture_set_names)
    except Exception as e:
        QtWidgets.QMessageBox.critical(_main_window(), "Export Error", str(e))


def _on_mesh_reloaded(status):
    if status == substance_painter.project.ReloadMeshStatus.SUCCESS:
        return

    QtWidgets.QMessageBox.warning(
        _main_window(),
        "Reimport Mesh",
        "Mesh reimport failed. Check the Painter log for details."
    )


def reimport_mesh():
    if not substance_painter.project.is_open():
        QtWidgets.QMessageBox.warning(_main_window(), "Reimport Mesh", "No project is open.")
        return

    try:
        mesh_path = substance_painter.project.last_imported_mesh_path()
    except substance_painter.exception.ProjectError as exc:
        QtWidgets.QMessageBox.warning(_main_window(), "Reimport Mesh", str(exc))
        return

    if not mesh_path or not os.path.isfile(mesh_path):
        QtWidgets.QMessageBox.warning(
            _main_window(),
            "Reimport Mesh",
            "No previously imported mesh file was found for this project."
        )
        return

    settings = substance_painter.project.MeshReloadingSettings()

    try:
        substance_painter.project.reload_mesh(mesh_path, settings, _on_mesh_reloaded)
    except substance_painter.exception.ProjectError as exc:
        QtWidgets.QMessageBox.warning(_main_window(), "Reimport Mesh", str(exc))
    except Exception as exc:
        QtWidgets.QMessageBox.critical(_main_window(), "Reimport Mesh", str(exc))


def incremental_save():
    if not substance_painter.project.is_open():
        QtWidgets.QMessageBox.warning(_main_window(), "Incremental Save", "No project is open.")
        return

    project_file = _ensure_project_is_saved("Incremental Save")
    if not project_file:
        return

    target_path = _next_incremental_save_path(project_file)
    try:
        substance_painter.project.save_as(target_path)
    except substance_painter.exception.ProjectError as exc:
        QtWidgets.QMessageBox.warning(_main_window(), "Incremental Save", str(exc))
    except Exception as exc:
        QtWidgets.QMessageBox.critical(_main_window(), "Incremental Save", str(exc))


def start_plugin():
    spacer = QtWidgets.QWidget(_main_window())
    spacer.setFixedSize(24, 10)

    app = QtWidgets.QApplication.instance()
    export_button = QtWidgets.QToolButton(_main_window())
    if app is not None:
        export_button.setIcon(app.style().standardIcon(QtWidgets.QStyle.SP_DialogOkButton))
    export_button.setAutoRaise(True)
    export_button.setFixedSize(24, 24)
    export_button.setIconSize(QtCore.QSize(20, 20))
    export_button.setToolTip("Export textures to an 'export' folder next to the .spp file")
    export_button.clicked.connect(export_blender_textures)

    reimport_button = QtWidgets.QToolButton(_main_window())
    if app is not None:
        reimport_button.setIcon(app.style().standardIcon(QtWidgets.QStyle.SP_BrowserReload))
    reimport_button.setAutoRaise(True)
    reimport_button.setFixedSize(24, 24)
    reimport_button.setIconSize(QtCore.QSize(20, 20))
    reimport_button.setToolTip("Reimport the current project mesh")
    reimport_button.clicked.connect(reimport_mesh)

    incremental_save_button = QtWidgets.QToolButton(_main_window())
    if app is not None:
        incremental_save_button.setIcon(app.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton))
    incremental_save_button.setAutoRaise(True)
    incremental_save_button.setFixedSize(24, 24)
    incremental_save_button.setIconSize(QtCore.QSize(20, 20))
    incremental_save_button.setToolTip("Incremental save: project_1.spp, project_2.spp, ...")
    incremental_save_button.clicked.connect(incremental_save)

    substance_painter.ui.add_plugins_toolbar_widget(spacer)
    substance_painter.ui.add_plugins_toolbar_widget(export_button)
    substance_painter.ui.add_plugins_toolbar_widget(reimport_button)
    substance_painter.ui.add_plugins_toolbar_widget(incremental_save_button)
    plugin_widgets.append(spacer)
    plugin_widgets.append(export_button)
    plugin_widgets.append(reimport_button)
    plugin_widgets.append(incremental_save_button)


def close_plugin():
    for widget in plugin_widgets:
        substance_painter.ui.delete_ui_element(widget)
    plugin_widgets.clear()
