import bpy
import os
from pathlib import Path
from ..logger import log_error, log_info, log_debug
from ..ui.utils import show_message_box
import re
from math import atan, radians
from mathutils import Vector

from ..globals import GEONODE_SKIDMARK, PHYSICS_BODY, PHYSICS_WHEELS, SPEED_CALC


def get_scene_collections(scene):
    return scene.collection.children

def get_collection_by_name(name, root_collection):
    if root_collection.name == name:
        return root_collection

    for child_collection in root_collection.children:
        found_collection = get_collection_by_name(name, child_collection)
        if found_collection is not None:
            return found_collection

    return None

def get_all_children_collections(collection):
    children = []
    for child in collection.children:
        children.append(child)
        children += get_all_children_collections(child)
    return children

#Needs a list of the children, since "scene.collection.children" does not return a list
def get_children_list(collection):
    collection_children_list = []
    for child in collection.children:
        collection_children_list.append(child)
    return collection_children_list

def unlink_collection(collection_to_unlink, parent_collection):   
    if collection_to_unlink in get_children_list(parent_collection):
        parent_collection.children.unlink(collection_to_unlink)

def unlink_collection_all(collection_to_unlink):
    for coll in bpy.context.scene.collection.children_recursive:
        if collection_to_unlink and coll:
            unlink_collection(collection_to_unlink, coll)
    
    #and for the scene collection
    #if coll in get_children_list(bpy.context.scene.collection):
        #bpy.context.scene.collection.children.unlink(collection_to_unlink)

def link_collection(collection_to_link, parent_collection):
    if collection_to_link not in get_children_list(parent_collection):
        parent_collection.children.link(collection_to_link)

def clear_orphans():
    '''Deletes all orphaned data blocks in the active Blender scene.'''
    
    found_orphans = True
    while found_orphans:
        found_orphans = False

        for block_type in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                        bpy.data.lights,  bpy.data.images, bpy.data.cameras, bpy.data.collections, bpy.data.textures,
                        bpy.data.lattices, bpy.data.sounds, bpy.data.actions, bpy.data.armatures,
                        bpy.data.fonts, bpy.data.grease_pencils, bpy.data.libraries, bpy.data.linestyles,
                        bpy.data.movieclips, bpy.data.cache_files, bpy.data.node_groups, bpy.data.screens, bpy.data.shape_keys,
                        bpy.data.speakers, bpy.data.texts, bpy.data.worlds):

            # Get a list of all blocks that have zero users.
            orphan_blocks = [block for block in block_type if block.users == 0]
            for block in orphan_blocks:
                block.use_extra_user = False
                block_type.remove(block)
                found_orphans = True
    
    return True

def find_driver_index(drivers, target_data_path):
    for n, dr in enumerate(drivers):
        if dr.data_path == target_data_path:
            return n
    
    return 0


def get_driver_indices_by_expression(drivers, expression):
    index_list = []
    for n, dr in enumerate(drivers):
        if dr.driver.expression == expression:
            index_list.append(n)
    
    return index_list

def setup_driver(
        target_obj,                     # Object with Driver
        target_data_path,               # The name of the field where the Driver should be active
        driver_field_index,             # For Vectors, where to place driver
        expression,                     # Expression
        *argv,                          # Any number of variables to create
    ):
        # Base setup
        target_obj.driver_add(target_data_path, driver_field_index)

        # Find driver ID created:
        index = find_driver_index(target_obj.animation_data.drivers, target_data_path)

        if index != -1:
            target_driver = target_obj.animation_data.drivers[index].driver
            target_driver.expression = expression

            # First remove all variables
            for var in target_driver.variables:
                target_driver.variables.remove(var)

            # Variables
            for i, var in enumerate(argv):
                target_driver.variables.new()
                target_driver.variables[i].name = var[0]
                target_driver.variables[i].type = var[1]
                target_driver.variables[i].targets[0].id = var[2]
                try:
                    target_driver.variables[i].targets[0].bone_target = var[3]
                except:
                    pass
                target_driver.variables[i].targets[0].transform_type = var[4]
                target_driver.variables[i].targets[0].transform_space = var[5]
        else:
            log_error("Could not add driver.", "Setup Driver")


def apply_all_transforms(ob):
    matrix = ob.matrix_world.copy()
    for vert in ob.data.vertices:
        vert.co = matrix @ vert.co
    ob.matrix_world.identity()

def get_mesh_path_length(ob):
    if ob.type == 'MESH':
        vert = ob.data.vertices
        dd = len = 0
        for i in ob.data.edges:
            dd = vert[i.vertices[0]].co - vert[i.vertices[1]].co
            len += dd.length
        len = round(len,4)

        return len
    
    else:
        return -1

def get_active_curve_length(ob):

    if ob.type == 'CURVE':
        restore_bevel_depth = ob.data.bevel_depth
        ob.data.bevel_depth = 0
        mesh = bpy.data.meshes.new_from_object(ob)
        mesh_line = bpy.data.objects.new(ob.name, mesh)
        mesh_line.matrix_world = ob.matrix_world
        bpy.context.collection.objects.link(mesh_line)
        ob.data.bevel_depth = restore_bevel_depth

        apply_all_transforms(mesh_line)

        curve_len = get_mesh_path_length(mesh_line)

        bpy.data.objects.remove(mesh_line, do_unlink=True)

        return curve_len
    
    else:
        return -1
    
def find_area(area_type):
        try:
            for a in bpy.data.window_managers[0].windows[0].screen.areas:
                if a.type == area_type:
                    return a
            return None
        except:
            return None


def get_addon_path():
    addons_dir = bpy.utils.user_resource("EXTENSIONS", path="user_default")
    addons_path = os.path.join(addons_dir, "launch_control_auto_car_rig")

    if not Path(addons_path).exists():
        log_debug("Didn't find add-on in default location. Will try user paths", "get_addon_path")

        for user_file_path in bpy.context.preferences.extensions.repos:
            addons_dir = user_file_path.directory
            addons_path = os.path.join(addons_dir, "launch_control_auto_car_rig")

            log_debug(f"Trying path: {addons_path}", "get_addon_path")
            if not Path(addons_path).exists():
                addons_path = None

    return addons_path


def get_addon_version():

    lc_addon_path = get_addon_path()

    file = os.path.join(lc_addon_path, "blender_manifest.toml")

    regexp = re.compile(r'version.*?([0-9.-]+)')
    with open(file, 'r') as f:
        for line in f:
            match = regexp.match(line)
            if match:
                addon_version_str = str(match.group(1))
                return addon_version_str

    return None

def get_blender_min_version():
    lc_addon_path = get_addon_path()

    file = os.path.join(lc_addon_path, "blender_manifest.toml")

    regexp = re.compile(r'blender_version_min.*?([0-9.-]+)')
    with open(file, 'r') as f:
        for line in f:
            match = regexp.match(line)
            if match:
                blender_min_version_str = str(match.group(1))
                return blender_min_version_str

    return None

def force_update_geo_nodes(active_car):
    geo_node_groups = []
    geo_node_groups.append(bpy.data.node_groups[(PHYSICS_BODY + "_" + active_car.collection.name)])
    geo_node_groups.append(bpy.data.node_groups[(PHYSICS_WHEELS + "_" + active_car.collection.name)])
    geo_node_groups.append(bpy.data.node_groups[SPEED_CALC])
    geo_node_groups.append(bpy.data.node_groups[(GEONODE_SKIDMARK + "_" + active_car.collection.name)])
    
    
    for node_group in geo_node_groups:
        tree = node_group.interface.items_tree[0]
        tree.hide_value = not tree.hide_value

    return None


def get_speed_rotate_fcurve(rig_object):
            
    # Retrieve the specific F-Curve
    data_path = 'pose.bones["bone_Speed_Rotate"].rotation_euler'
    array_index = 2
    fc = rig_object.animation_data.action.fcurves.find(data_path, index=array_index)

    if fc:
        return fc
    
    else:
        return None

def get_speed_rotate_keyframes(rig_object):

    fc = get_speed_rotate_fcurve(rig_object)

    if fc:
        keyframes = fc.keyframe_points
        return keyframes
    
    else:
        return None
    
def file_exists(file):

    return os.path.isfile(file)


def cad_align_to_ground(body, wheel_RL, wheel_RR, wheel_FL, wheel_FR, brake_RL, brake_RR, brake_FL, brake_FR):
    scene = bpy.context.scene

    wheel_RL_vec = wheel_RL.matrix_world.to_translation()
    wheel_FL_vec = wheel_FL.matrix_world.to_translation()

    

    tire_bottom_RL_vec = wheel_RL_vec - Vector((0, 0, scene.settings.wheel_size_rear/2))
    tire_bottom_FL_vec = wheel_FL_vec - Vector((0, 0, scene.settings.wheel_size_front/2))

    tire_bottom_z_delta = tire_bottom_FL_vec[2] - tire_bottom_RL_vec[2]


    print("tire_bottom_z_delta: ", tire_bottom_z_delta)

    if abs(tire_bottom_z_delta) < 0.001:
        # Just skip the rest and go directly to rigging
        return True
    
    if wheel_RL not in body.children_recursive:
        text = 'Could not align vehicle to ground. Please align manually inside "Garage Mode" using the "Wheel Radius Handles" or make sure to use the top null/empty as the "Body Assembly" in the UI before rigging'
        show_message_box(text, "CAD rigging", "INFO")
        log_info(text, "cad_align_to_ground")
        return False
    
    dist_x = tire_bottom_FL_vec[0] - tire_bottom_RL_vec[0]
    dist_y = tire_bottom_FL_vec[1] - tire_bottom_RL_vec[1]

    print("dist_x", dist_x)
    print("dist_y", dist_y)

    if abs(dist_x) > abs(dist_y):
        dist = dist_x
        orient_axis = 'Y'
    else:
        dist = dist_y
        orient_axis = 'X'
    

    wheelbase = abs(dist)

    print("wheelbase", wheelbase)
    
    deg = atan((tire_bottom_z_delta/wheelbase))

    print("deg", deg)

    cursor_loc_restore = scene.cursor.location
    pivot_point_restore = scene.tool_settings.transform_pivot_point
    scene.tool_settings.transform_pivot_point = 'CURSOR'

    bpy.ops.object.select_all(action="DESELECT")
    wheel_RL.select_set(True)
    bpy.ops.view3d.snap_cursor_to_selected()
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)

    bpy.ops.transform.rotate(value=-deg, orient_axis=orient_axis, orient_type='GLOBAL')

    scene.cursor.location = cursor_loc_restore
    scene.tool_settings.transform_pivot_point = pivot_point_restore

    return True


def enum_members_from_type(rna_type, prop_str):
    prop = rna_type.bl_rna.properties[prop_str]
    return [e.identifier for e in prop.enum_items]


def enum_members_from_instance(rna_item, prop_str):
    return enum_members_from_type(type(rna_item), prop_str)


# ---------From Copy attributes script-----------

def rotcopy(item, mat):
    """Copy rotation to item from matrix mat depending on item.rotation_mode"""
    if item.rotation_mode == 'QUATERNION':
        item.rotation_quaternion = mat.to_3x3().to_quaternion()
    elif item.rotation_mode == 'AXIS_ANGLE':
        rot = mat.to_3x3().to_quaternion().to_axis_angle()    # returns (Vector((x, y, z)), w)
        axis_angle = rot[1], rot[0][0], rot[0][1], rot[0][2]  # convert to w, x, y, z
        item.rotation_axis_angle = axis_angle
    else:
        item.rotation_euler = mat.to_3x3().to_euler(item.rotation_mode)

def world_to_basis(active, ob, context):
    """put world coords of active as basis coords of ob"""
    local = ob.parent.matrix_world.inverted() @ active.matrix_world
    P = ob.matrix_basis @ ob.matrix_local.inverted()
    mat = P @ local
    return(mat)

def obVisLoc(ob, active, context):
    if ob.parent:
        mat = world_to_basis(active, ob, context)
        ob.location = mat.to_translation()
    else:
        ob.location = active.matrix_world.to_translation()
    return('INFO', "Object location copied")


def obVisRot(ob, active, context):
    if ob.parent:
        mat = world_to_basis(active, ob, context)
        rotcopy(ob, mat.to_3x3())
    else:
        rotcopy(ob, active.matrix_world.to_3x3())
    return('INFO', "Object rotation copied")


def obVisSca(ob, active, context):
    if ob.parent:
        mat = world_to_basis(active, ob, context)
        ob.scale = mat.to_scale()
    else:
        ob.scale = active.matrix_world.to_scale()
    return('INFO', "Object scale copied")

    # ---------From Copy attributes script-----------