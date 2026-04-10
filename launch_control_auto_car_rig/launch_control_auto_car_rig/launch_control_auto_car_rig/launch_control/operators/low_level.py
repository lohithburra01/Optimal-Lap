import bpy

def set_parent_keep_transform(child, parent):
    world_matrix = child.matrix_world.copy()
    child.parent = parent
    child.parent_type = 'OBJECT'
    child.matrix_world = world_matrix


def clear_parent_keep_transform(child):
    world_matrix = child.matrix_world.copy()
    child.parent = None
    child.matrix_world = world_matrix


def set_parent_bone_keep_transform(child, parent_bone, parent):
    ''' Creates a parent-child relationship between a child object and a hub bone in a given input car rig.'''
    """world_matrix = child.matrix_world.copy()
    child.parent = parent 
    child.parent_type = 'BONE'
    child.parent_bone = parent_bone.name
    child.matrix_world = world_matrix """

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")

    child.select_set(True)
    bpy.context.view_layer.objects.active = parent
    bpy.ops.object.mode_set(mode="POSE")

    for bone in parent.data.bones:
        bone.select = False

    parent_bone.select = True
    parent.data.bones.active = parent_bone

    bpy.ops.object.parent_set(type="BONE", keep_transform=True)

    bpy.ops.object.mode_set(mode="OBJECT")


def make_single_user(object=True, obdata=True, material=False, animation=False, obdata_animation=False):
    pass 

def transform_apply(obj, location=True, rotation=True, scale=True, properties=True, isolate_users=False):
    '''Apply the object’s transformation to its data'''
    pass
