import bpy
import math, mathutils

def get_midpoint(p1, p2):
    return (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, (p1[2] + p2[2]) / 2

def get_2Drotation(p1, p2, radians=True):
    """Get the rotation in radians between two 2D points."""
    dirVecX = p1[0] - p2[0]
    dirVecY = p1[1] - p2[1]

    try:
        radians = math.atan(dirVecY / dirVecX)
    except:
        radians = -math.pi / 2

    # Rotate in case car is flipped
    if (dirVecX <= 0 and dirVecY >= 0) or (dirVecX < 0 and dirVecY < 0):
        radians = radians - math.pi

    return radians

def get_rear_axle(wheels):
    ''' Calculates the center location of the rear axle. '''
    
    loc_Raxle = mathutils.Vector(get_midpoint(wheels.wheel_RL.location, wheels.wheel_RR.location))
    loc_Faxle = mathutils.Vector(get_midpoint(wheels.wheel_FL.location, wheels.wheel_FR.location))
    loc_Raxle_floor = loc_Raxle

    scene = bpy.context.scene
    # get wheel Radius
    if scene.settings.cad_setup:
        wheelR_radius = loc_Raxle_floor[2] - (scene.settings.wheel_size_rear/2)
    else:
        wheelR_radius = loc_Raxle_floor[2] - wheels.wheel_RR.dimensions[2] / 2

    loc_Raxle_floor[2] = wheelR_radius  # set REAR wheel Radius

    return loc_Raxle_floor, loc_Raxle, loc_Faxle

def set_wheels_lattice(scene, wheel_RR, wheel_FR, wheels_list, list_order, rig_scale):
    wheel_dims = [
        wheel_RR.dimensions[2],
        wheel_RR.dimensions[2],
        wheel_FR.dimensions[2],
        wheel_FR.dimensions[2],
    ]
    tire_width = wheel_RR.dimensions[0]

    lattice_names = ["lattice." + achro for achro in list_order]
    lattices = [scene.objects[name] for name in lattice_names]

    scale_factors = [dim / (0.96 * rig_scale) for dim in wheel_dims]
    for lattice, scale_factor in zip(lattices, scale_factors):
        lattice.scale *= scale_factor

    for i, (wheel, lattice) in enumerate(zip(wheels_list, lattices)):
        offsetDir = 1 if i in [1, 3] else -1

        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = wheel
        bpy.ops.view3d.snap_cursor_to_selected()
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = lattice
        bpy.ops.view3d.snap_selected_to_cursor(use_offset=False)

        lattice.location[0] += (tire_width / 2.3) * offsetDir


def create_matrix(posx, posy, posz, rotx, roty, rotz, scax, scay, scaz):
    # create a location matrix
    mat_loc = mathutils.Matrix.Translation((posx, posy, posz))

    # create an identitiy matrix
    mat_scax = mathutils.Matrix.Scale(scax, 4, (1, 0, 0))
    mat_scay = mathutils.Matrix.Scale(scay, 4, (0, 1, 0))
    mat_scaz = mathutils.Matrix.Scale(scaz, 4, (0, 0, 1))

    # create a rotation matrix
    mat_rotx = mathutils.Matrix.Rotation(math.radians(rotx), 4, 'X')
    mat_roty = mathutils.Matrix.Rotation(math.radians(roty), 4, 'Y')
    mat_rotz = mathutils.Matrix.Rotation(math.radians(rotz), 4, 'Z')

    # combine transformations
    mat_rot = mat_rotz @ mat_roty @ mat_rotx
    mat_sca = mat_scax @ mat_scay @ mat_scaz
    mat_out = mat_loc @ mat_rot @ mat_sca

    return mat_out