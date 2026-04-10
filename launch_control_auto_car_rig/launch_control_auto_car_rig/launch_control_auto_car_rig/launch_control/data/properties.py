import bpy
import math
from bpy.types import Object



from .commands import *



from ..globals import ANIMATIONS, ANIMATIONS_DEFAULT, HEADLIGHTS, HEADLIGHTS_DEFAULT, PHYSICS, PHYSICS_DEFAULT, PHYSICS_DEFAULT_VALUES
from ..operators.append import append_lc_car_callback
from ..operators.custom_anim_presets import anim_preset_categories_callback


# Detect and Save License Type
is_pro_license = False

lc_addon_path = get_addon_path()
pro_path = os.path.join(lc_addon_path, "pro_features")
if os.path.isdir(pro_path):
    is_pro_license = True

if is_pro_license:
    from ...pro_features.link_pro import link_lc_car_callback


def get_vehicle_source_items(self, context):
    if is_pro_license:
        source_items = [
            ('local', 'Local', 'Rig any 3D vehicle model inside the Blender Scene', 'HOME', 0),
            ('gallery', 'Gallery', 'Add one of the Vehicles from the LC Gallery', 'IMAGE_PLANE', 1),
            ('append', '', 'Append (Copy) an already Rigged LC Vehicle from another Blend File', 'APPEND_BLEND', 2),
            ('link', '', 'Link an already Rigged LC Vehicle from another Blend File. You can afterwards make a Library Override on the Linked Rig if you wish', 'LINK_BLEND', 3),
        ]
    else:
        source_items = [
            ('local', 'Local', 'Rig any 3D vehicle model inside the Blender Scene', 'HOME', 0),
            ('gallery', 'Gallery', 'Add one of the Vehicles from the LC Gallery', 'IMAGE_PLANE', 1),
            ('append', 'Append', 'Append (Copy) an already Rigged LC Vehicle from another Blend File', 'APPEND_BLEND', 2),
        ]

    return source_items


# UI TYPES



class GlobalSettings(bpy.types.PropertyGroup):
    # rig settings
    rig_help: bpy.props.BoolProperty(
        name="Rigging Help", description="Need help to rig your vehicle?", default=False
    )

    quick_tag: bpy.props.BoolProperty(
        name="Quick Tag", description="Need to quickly rename Car Parts to support Launch Control?", default=False
    )

    cad_setup: bpy.props.BoolProperty(
        name="CAD Setup", description="Setup process optimized for datasets of Production Vehicles", default=False
    )
    
    show_setup_rig: bpy.props.BoolProperty(
        name="Show Rig Setup Controls",
        description="legacy",
        update=reveal_setup_controls,
        default=0,
        options=set(),
    )

    mode: bpy.props.EnumProperty(
        name="Switch Mode",
        description="In Garage/Setup Mode, you can rearrange and attach new meshes to your vehicle and rescale the rig. Any animation will be saved and disabled until Race Mode will be entered",
        items=[
            ('race_mode', 'Race Mode', '', '', 0),
            ('garage_mode', 'Garage Mode', '', '', 1)  
        ],
        update=switch_mode,
        default='race_mode',
        options=set(),
    )

    vehicle_source: bpy.props.EnumProperty(
        name="Vehicle Source",
        description="Vehicles can be added to Launch Control in multiple ways. Pick the one that suits your workflow",
        items=get_vehicle_source_items,
        default=1,
        options=set(),
    )

    export_all_cars: bpy.props.BoolProperty(
        name="Export all cars in the scene",
        description="Export all cars in the scene",
        default=False,
        options=set(),
    )

    include_ground_for_all: bpy.props.BoolProperty(
        name="Include ground detection for all cars",
        description="Include all Ground Colliders in each exported file",
        default=False,
        options=set(),
    )

    include_anim: bpy.props.BoolProperty(
        name = "Include Animations", 
        description="Export Animations - If disabled only meshes and the armature will be exported. Designed for UE workflow, where you later on can export animations only to improve import/export speed", 
        default=True, 
        update=update_anim_export,
        options=set(),
    )
    
    export_anim_only: bpy.props.BoolProperty(
        name = "Only Animations", 
        description="Export animations only - ignore the meshes and materials. Designed for UE workflow, where a skeletal mesh of the car has already been set up", 
        default=False,
        options=set(),
    )

    subframes: bpy.props.IntProperty(
        name="Export Subframes",
        description="How many sub-steps each frame of Blender Animation has. Increases animation quality, but takes longer to export. Increasing this can avoid opposite-spinning wheels, when the vehicle is at a high speed",
        default=3,
        soft_max=20,
        max = 50,
        min = 1,
        options=set(),
    )

    use_imperial_copy: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=False,
    )

    edit_all_mode: bpy.props.BoolProperty(
        name="Multi-Edit",
        description="Adjustments will be applied to all Vehicles. Some adjustments are not available when 'Multi-Edit' is active. Depending on the amount of vehicles, some functions can take long, so please be patient :)",
        default=False,
        update=toggle_edit_all_mode,
        options=set(),
    )

    draw_ui: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=True,
    )

    show_rigged_coll_only: bpy.props.BoolProperty(
        name="Filter: Rigged Only",
        description="Show only already rigged LC cars in the dropdown",
        default=False,
        options=set(),
    )

    physics_use_warm_up: bpy.props.BoolProperty(
        name="Use Warm Up",
        description="Add extra frames before the actual animation when Physics are baked. This resolves 'popping' in the physics when the animation starts. For BAKED Physics only",
        default=True,
        update=update_warm_up
    )

    physics_warm_up_frames: bpy.props.IntProperty(
        name="Frames",
        description="Add extra frames before the actual animation when Physics are baked. This resolves 'popping' in the physics when the animation starts. For BAKED Physics only!",
        default=20,
        min=0,
        soft_max=50,
        update=update_warm_up
    )

    physics_restore_start_frame: bpy.props.IntProperty(
        name="internal",
        description="internal",
        default=0,
    )

    physics_restore_end_frame: bpy.props.IntProperty(
        name="internal",
        description="internal",
        default=0,
    )

    confirm_bake_state: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=False
    )

    bake_running: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=False
    )

    link_tire_settings: bpy.props.BoolProperty(
        name="Link Tire Settings", 
        description="Use the same Tire Settings for both the front and rear tires", 
        default=True,
        update=update_link_tire,
        options=set(),
    )

    tire_width: bpy.props.IntProperty(
        name="Tire Width", 
        description="The width in Millimeters of the rear tires of the car", 
        default=205,
        min=150, 
        soft_min=190, 
        soft_max=220, 
        max=250,
        options=set(),
    )

    tire_ratio: bpy.props.IntProperty(
        name="Tire Aspect Ratio", 
        description="The aspect ratio between width/height of the rear tires of the car", 
        default=55,
        min=30, 
        soft_min=45, 
        soft_max=65, 
        max=80,
        options=set(),
    )

    rim_diameter: bpy.props.IntProperty(
        name="Rim Diameter", 
        description="The diameter in Inches of the rim in the rear of the car", 
        default=16,
        min=10, 
        soft_min=12, 
        soft_max=22, 
        max=30,
        options=set(),
    )

    tire_width_front: bpy.props.IntProperty(
        name="Front Tire Width", 
        description="The width in Millimeters of the rear tires of the car", 
        default=205,
        min=150, 
        soft_min=190, 
        soft_max=220, 
        max=250,
        options=set(),
    )

    tire_ratio_front: bpy.props.IntProperty(
        name="Front Tire Aspect Ratio", 
        description="The aspect ratio between width/height of the rear tires of the car", 
        default=55,
        min=30, 
        soft_min=45, 
        soft_max=65, 
        max=80,
        options=set(),
    )

    rim_diameter_front: bpy.props.IntProperty(
        name="Front Rim Diameter", 
        description="The diameter in Inches of the rim in the rear of the car", 
        default=16,
        min=10, 
        soft_min=12, 
        soft_max=22, 
        max=30,
        options=set(),
    )

    tire_width_rear: bpy.props.IntProperty(
        name="Rear Tire Width", 
        description="The width in Millimeters of the rear tires of the car", 
        default=205,
        min=150, 
        soft_min=190, 
        soft_max=220, 
        max=250,
        options=set(),
    )

    tire_ratio_rear: bpy.props.IntProperty(
        name="Rear Tire Aspect Ratio", 
        description="The aspect ratio between width/height of the rear tires of the car", 
        default=55,
        min=30, 
        soft_min=45, 
        soft_max=65, 
        max=80,
        options=set(),
    )

    rim_diameter_rear: bpy.props.IntProperty(
        name="Rear Rim Diameter", 
        description="The diameter in Inches of the rim in the rear of the car", 
        default=16,
        min=10, 
        soft_min=12, 
        soft_max=22, 
        max=30,
        options=set(),
    )

    wheel_size_rear: bpy.props.FloatProperty(
        name="Wheel Diameter Rear", 
        description="The diameter in Meters of the tire in the rear of the car. Calculate this value using the input fields above or input it manually", 
        default=0.631901,
        min=0.20, 
        soft_min=0.50, 
        soft_max=1.20, 
        max=2.00,
        subtype = 'DISTANCE',
        options=set(),
    )

    wheel_size_front: bpy.props.FloatProperty(
        name="Wheel Diameter Front", 
        description="The diameter in Meters of the tire in the front of the car. Calculate this value using the input fields above or input it manually", 
        default=0.631901,
        min=0.20, 
        soft_min=0.50, 
        soft_max=1.20, 
        max=2.00,
        subtype = 'DISTANCE',
        options=set(),
    )
    
    wheel_camber: bpy.props.FloatProperty(
        name="Wheel Camber Amount", 
        description="The amount of camber in degrees on the wheels in rest position", 
        default=-0.0174533, 
        min=-0.0872665, 
        soft_min=-0.0523599, 
        soft_max=0, 
        max=0.0872665,
        subtype = 'ANGLE',
        options=set(),
    )
    
    emulated_body_weight: bpy.props.FloatProperty(
        name="Emulated Body Weight", 
        description="Automatically drop the body of the vehicle slightly to immitate the weight of the car, which will compress the springs", 
        default=0.01, 
        min=0, 
        soft_max=0.03, 
        max=0.05,
        subtype = 'DISTANCE',
        options=set(),
    )
    
    speed_segments_running: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=False,
    )

    speed_segments_kill: bpy.props.BoolProperty(
        name="Disable Segments",
        description="Remove the Speed Segment Tool from the viewport. Animations stay active and the tool can be brought back whenever you need it",
        default=False,
        update=update_speed_segment_state,
    )

    # Not yet implemented
    ui_update_timer: bpy.props.FloatProperty(
        name="internal",
        description="internal",
        default=0,
        update=ui_update_timer,
    )

    append_version_control: bpy.props.BoolProperty(
        name="Version Control",
        description="Secures that the LC rig version of the appending vehicle matches the installed add-on version. Disable to bypass this security check",
        default=True,
        options=set(),
    )

    append_file_path: bpy.props.StringProperty(
        name="Append Path",
        description="Filepath for the file you want to append from",
        subtype="FILE_PATH",
        default="//",
    )

    append_lc_car_names: bpy.props.EnumProperty(
        name="Append Vehicles",
        description="Pick the Vehicle from the file you want to append into the scene",
        items=append_lc_car_callback,
        options=set(),
    )

    if is_pro_license:
        link_lc_car_names: bpy.props.EnumProperty(
            name="Link Vehicles",
            description="Pick the Vehicle from the file you want to link into the scene",
            items=link_lc_car_callback,
            options=set(),
        )
    else: #Maybe we should instead not define at all!
        link_lc_car_names: bpy.props.EnumProperty(
            name="Link Vehicles",
            description="Pick the Vehicle from the file you want to link into the scene",
            items=[],
            options=set(),
        )
    

    append_path: bpy.props.StringProperty(
        name="Append Path",
        description="Locate the .blend file you wish to append an LC rigged Vehicle from",
        subtype="FILE_PATH",
        default="",
    )


    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="Format to export into",
        items=[
            (
                "abc",
                "Alembic (.abc)",
                "Optimized for C4D, Maya, Max, Houdini",
            ),
            (
                "FBX",
                "FBX Generic (.fbx)",
                "Optimized for C4D, Maya, Max, Houdini",
            ),
            (
                "USD",
                "Universal Scene Description (.usd)",
                "Optimized for Unreal Engine and Blender",
            ),
            (
                "glb",
                "glTF 2.0 (.glb)",
                "Optimized for web-based apps such as three-js",
            ),
            (
                "glTF",
                "glTF 2.0 (.gltf)",
                "Optimized for web-based apps such as three-js",
            ),
            (
                "UE_FBX",
                "UE5 FBX (.fbx)",
                "Optimized for Unreal Engine 5",
            ),
            (
                "udatasmith",
                "UE5 Datasmith (.udatasmith)",
                "Optimized for Unreal Engine 5",
            ),
            (
                "blend",
                "Keyframe Baked Blend (.blend)",
                "Optimized for Export to Render Farms running Blender without Launch Control installed",
            ),
        ],
        options=set(),
    )

    show_bridge_tool_settings:  bpy.props.BoolProperty(
        name="Export Settings",
        description="Reveal extra settings for custom exports",
        default=False,
        options=set(),
    )

    bridge_quality:  bpy.props.EnumProperty(
        name="Quality",
        description="The quality at which the vehicle will be exported.",
        items=[
            (
                "proxy",
                "Proxy",
                "Export In Proxy Quality (Generate a proxy version before doing this)",
            ),
            (
                "full",
                "Full Mesh",
                "Export in Full Quality with all the vehicle meshes",
            ),
        ],
        default="full",
        options=set(),
    )

    bridge_quality_dummy:  bpy.props.EnumProperty(
        name="Quality",
        description="The quality at which the vehicle will be exported.",
        items=[
            (
                "proxy",
                "Proxy",
                "Export In Proxy Quality (Generate a proxy version before doing this)",
            ),
            (
                "full",
                "Full Mesh",
                "Export in Full Quality with all the vehicle meshes",
            ),
        ],
        default="full",
        options=set(),
    )


    bridge_include:  bpy.props.EnumProperty(
        name="Include",
        description="The elements to include in the export",
        items=[
            (
                "active_only",
                "Vehicle Only",
                "Export only the Active Vehicle(s) and all objects inside the 'ExportObjects' Collection",
            ),
            (
                "full_scene",
                "Full Scene",
                "Export all objects, visible in the scene",
            ),
        ],
        options=set(),
    )

    bridge_unreal_asset:  bpy.props.EnumProperty(
        name="Unreal Asset",
        description="Decide what will be packed into the UE5 supported fbx file. Avoid exporting the mesh to save time and data.",
        items=[
            (
                "skeletal_mesh",
                "Animated Skeletal Mesh",
                "Export both the meshes of the vehicle as well as the animation as a Skeletal Mesh",
            ),
            (
                "anim_only",
                "Animation Only",
                "Export only the animation data without any mesh data to save time. This requires an existing Skeletal Mesh of the same armature inside Unreal Engine",
            ),
            (
                "static_mesh",
                "Static Mesh",
                "Export a Static Mesh with no animation data for connecting to a Skeletal Mesh using the LP to HP workflow",
            ),
        ],
        options=set(),
    )

    bridge_apply_transforms: bpy.props.BoolProperty(
        name="Apply Transforms On Export",
        description="Apply Rotation and Scale before exporting. This can resolve object offsets and scaling and rotation issues. Using this will make any Instanced Data Unique",
        default=True,
        options=set(),
    )

    filter_anim_presets: bpy.props.EnumProperty(
        name = "Animation Preset Filter",
        description = "Pick which Animation Presets you want to show in the Gallery",
        items=anim_preset_categories_callback,
        options=set(),
        update=update_filter_anim_preset,
    )

    anim_preset_name: bpy.props.StringProperty(
        name="New Animation Preset Name",
        description="The name of the new Custom animation Preset",
        default="New Preset",
    )


    file_linking_state: bpy.props.BoolProperty(
        name="internal",
        description="internal",
        default=False
    )


    physics_bake_target:  bpy.props.EnumProperty(
        name="Physics Bake Target",
        description="Where to store the baked Physics Data",
        items=[
            (
                "PACKED",
                "Packed",
                "Pack the baked data into the .blend file",
            ),
            (
                "DISK",
                "Disk",
                "Store the baked data in a directory on disk",
            ),
        ],
        default="PACKED",
        options=set(),
    )



class UISettings(bpy.types.PropertyGroup):
    # physics settings
    show_custom_physics: bpy.props.BoolProperty(
        name="Custom Sliders",
        description="Reveal sliders to adjust the physics settings manually.",
        default=False,
        options=set(),
    )

    show_acc_viz: bpy.props.BoolProperty(
        name="Show Acceleration Visualizer",
        description="Reveal an arrow and digits above the car showing the direction and the amount of the acceleration",
        update=reveal_acc_viz,
        default=False,
        options=set(),
    )

    show_acc_viz_override: bpy.props.BoolProperty(
        name="internal",
        update=reveal_acc_viz,
        default=True
    )

    show_vel_viz: bpy.props.BoolProperty(
        name="Show Velocity Visualizer",
        description="Reveal an arrow and digits above the car showing the direction and the amount of the velocity",
        update=reveal_vel_viz,
        default=False,
        options=set(),
    )

    # export settings
    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Use a custom export path or leave blank to export in the folder of the .blend file",
        subtype="FILE_PATH",
        default="//",
    )

    apply_transforms: bpy.props.BoolProperty(
        name="Apply Transforms On Export",
        description="If transforms or scales are wrong in the FBX, try turnig this on.",
        default=False,
    )

    include_ground: bpy.props.BoolProperty(
        name="Include Ground Detection Meshes",
        description="Includes all objects inside the collection 'GroundDetection' in the export",
        default=False,
    )

    # headlights settings
    link_beams: bpy.props.BoolProperty(
        name="Link Beam Settings",
        description="Use linked Temperature, Intensity and Spread values for High and Low Beam",
        update=update_beam_connected,
        default=True,
        options=set(),
    )

    low_beam_visibility: bpy.props.BoolProperty(
        name="Low Beam",
        description="Toggle Low Beam",
        update=update_beam,
        default=False,
        options=set(),
    )

    high_beam_visibility: bpy.props.BoolProperty(
        name="High Beam",
        description="Toggle High Beam",
        update=update_beam,
        default=False,
        options=set(),
    )

    # skidmark settings
    enable_skidmarks: bpy.props.BoolProperty(
        name = "Enable Skidmark Generator",
        description="Generates skidmarks from the tires on the fly. Go to Frame 0 to reset the skidmarks", 
        update=toggle_skidmarks,
        default=False,
        options=set(),
    )

    # animation settings
    show_extra_animation_controls: bpy.props.BoolProperty(
        name="legacy",
        description="legacy",
        default=False,
    )

    ui_view_elements: bpy.props.EnumProperty(
        name="Floating UI Complexity",
        description="Reveal more or less Animation and Setup Controls in the viewport, floating above the vehicle",
        items=[
            (
                "OP1",
                "Minimal UI",
                "Show only the Speed, Balance and Drift handle.",
            ),
            (
                "OP2",
                "Standard UI",
                "Show Speed, Balance and Drift handles along with Animation and setup Sliders above the vehicle",
            ),
            (
                "OP3",
                "Expanded UI",
                "Show all available sliders and handles. (Previously called 'Extra Animation Handles')",
            ),
        ],
        update=update_ui_view_elements,
        default="OP2",
        options=set(),
    )

    show_camera_hooks: bpy.props.BoolProperty(
        name="Show Camera Hooks",
        description="Reveal Hooks/Bones in the rig which cameras can be parented to or aimed at",
        update=reveal_camera_hooks,
        default=False,
        options=set(),
    )

    snap_path: bpy.props.BoolProperty(
        name="Snap Driving Path",
        description="Automatically snap the Control Points of the Driving Path to the Ground Detection Meshes",
        update=update_path_snap,
        default=False,
        options=set(),
    ) 

    speedometer: bpy.props.BoolProperty(
        name="Show Speedometer",
        description="Reveal a speedometer to check the speed of the car",
        update=reveal_speedometer,
        default=False,
        options=set(),
    )

    limit_sliders: bpy.props.BoolProperty(
        name="Limit Animation Sliders",
        description="Have the Animations sliders in the viewport be limited to a certain range",
        update=lock_sliders,
        default=True,
        options=set(),
    )

    # path & jump settings
    use_true_ground: bpy.props.BoolProperty(
        name="Use True Ground",
        description="Due to a bug in Blender 4.1, flat shaded meshes are not supported for this feature. Use the actual objects inside the collection 'GroundDetection', instead of a projected grid. This can be useful for complex loops or twisting roads built of ONE solid mesh, but will generally give a visually worse result and can introduce 'flickering' detection on 'layered' surfaces.",
        default=False,
        update=update_true_ground,
        options=set(),
    )

    legacy_ground_detection: bpy.props.BoolProperty(
        name="Legacy Ground Detection",
        description="Use Legacy Ground Detection Setup. That setup had issues with banked surfaces and very erratic bumps and was renewed, but could handle individual 'bottom out height' for the front and the rear wheels",
        default=False,
        update=update_legacy_ground_detection,
        options=set(),
    )

    show_ground_grid: bpy.props.BoolProperty(
        name="Visualize Grid",
        description="Want to visualize Ground Detection?",
        default=False,
        update=toggle_ground_grid,
        options=set(),
    )

    grid_resolution: bpy.props.IntProperty(
        name="Detection Resolution",
        description="Resolution of the grid that determines the floor from the objects inside collection: 'GroundDetection'",
        default=1,
        min=0,
        max=6,
        update=update_ground,
        options=set(),
    )

    enable_deform: bpy.props.BoolProperty(
        name="Enable Auto Deform",
        description="Automatic deformation of tires for when pressure is applied to them either by simulated data, by the weight of the car or by manual body animation. WARNING: Activating property slows down viewport performance significantly! "
        # default=Falseupdate=enable_tire_deform
    )

    deform_factor: bpy.props.FloatProperty(
        name="Deform Factor",
        description="Change the factor of how much the tire is deforming",
        update=update_deform_factor,
        default=100,
        min=0,
        soft_max=200,
        subtype="PERCENTAGE",
    )

    show_jump_help: bpy.props.BoolProperty(
        name="Jump Help", description="Need help to create jump?", default=False,
        options=set(),
    )

    jump_speed: bpy.props.FloatProperty(
        name="Jump Speed",
        precision=0,
        description="Speed of the vehicle as it enters the jump",
        default=50,
        min=0,
        soft_max=350,
        options=set(),
    )

    use_rest_pos: bpy.props.BoolProperty(
        name="Use Rest Pos",
        description="To adjust wobbly wheels set the rig to the 'Rest Position' and line that stuff up!",
        update=swap_pos,
        default=0,
    )

    restore_settings: bpy.props.FloatVectorProperty(
        name="Restore Setting",
        description="Temporarily saved settings for the rig while the user is in Rig Setup mode",
        size=32,
        default=(
            0.1,
            0.65,
            1.8,
            0,
            0,
            0,    #not used!
            0,
            0,
            0,
            0,
            0.3,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
    )
    restore_settings_02: bpy.props.FloatVectorProperty(
        name="Restore Settings",
        description="Temporarily saved settings for the rig while the user is in Rig Setup mode",
        size=20,
        default=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,),
    )



class UIProperties(bpy.types.PropertyGroup):
    # animations
    animation_preset: bpy.props.EnumProperty(
        items=[(key, key, "") for key in ANIMATIONS],
        default=ANIMATIONS_DEFAULT,
    )
    shake_frequency: bpy.props.FloatProperty(
        name="Speed of Continuous Shake",
        description="The phase at which the wheel and body of the car is constantly shaking (When activated in the viewport)",
        update=update_shaking_frequency,
        default=1.8,
        min=0,
        soft_max=3,
        options=set(),
    )

    # physics
    physics_presets: bpy.props.EnumProperty(
        items=[(key, key, "") for key in PHYSICS],
        default=PHYSICS_DEFAULT,
        update=update_physics_presets,
        options=set(),
    )

    physics_tightness: bpy.props.FloatProperty(
        name="Spring Hardness",
        description="The 'Tightness/Hardness' of the Spring. Increase this to have the Spring be harder and respond faster (Feeling of a light vehicle or road/track vehicle), decrease this to make the Spring respond slower and feel softer (Feeling of a heavy offroad vehicle).",
        default=40,
        min=5,
        soft_min=20,
        soft_max=60,
        max=90,
        subtype="PERCENTAGE",
        update=update_live_physics,
    )

    physics_dampening: bpy.props.FloatProperty(
        name="Spring Dampenig",
        description="How quickly the spring stops moving after an impact. A low value makes the spring wobble for a long time after an impulse.",
        default=35,
        soft_min=20,
        soft_max=90,
        min=0,
        max=95,
        subtype="PERCENTAGE",
        update=update_live_physics,
    )

    physics_softness: bpy.props.FloatProperty(
        name="Spring Smoothing",
        description="Adds extra smoothing to the ride. Makes the response slower and dampens more of the forces. Equivilant to Decreasing 'Hardness' and Increasing 'Dampening' at the same time.",
        default=0,
        min=0,
        max=75,
        subtype="PERCENTAGE",
        update=update_live_physics,
    ) 

    physics_multiplier: bpy.props.FloatProperty(
        name="Force Multiplier",
        description="Multiplies for input forces. Overdrives or decreses the overall intensity of the movements .",
        default=100,
        min=0,
        soft_max=200,
        subtype="PERCENTAGE",
        update=update_live_physics,
    )

    use_gravity: bpy.props.BoolProperty(
        name="Simulate Gravity",
        description="Let the physics take care of the Gravity when the vehicle is in the air. When 'ON' the vehicle might deviate more from the Driving Path during jumps. When 'OFF' the car will stick 'tightly' to the path, even if it would be physically impossible - This is useful for making the car do loops or running over a bumpy road in a controlled manner",
        default=True,
        update=update_live_physics,
    )

    auto_level: bpy.props.FloatProperty(
        name="Auto Level",
        description="During airtime, the vehicle can start to nose-dive or pitch backwards. Using Auto Level, you can bias the physics toward keeping the vehicle level rather than pitching or rolling.",
        default=0,
        min=0,
        soft_max=100,
        max=250,
        subtype="PERCENTAGE",
        update=update_live_physics,
    )

    spring_offset: bpy.props.FloatProperty(
        name="Spring Offset",
        description="WARNING! When set too high, the car will keep bouncing. Fine-tune the physics Suspension Height. This is only affecting the car when physics are turned on.",
        default=0,
        soft_min=0,
        soft_max=0.15,
        max = 0.3,
        min=-0.2,
        update=update_live_physics,
    )

    mass: bpy.props.FloatProperty(
        name="Vehicle Mass (Tons)",
        description="Similar to 'Spring Hardness', affects how much the car is affected by impacts from the road. Increase this to make the bumps and landings have less impact on the body motion of the vehicle and vice-versa.",
        default=1.5,
        min = 0.1,
        soft_min=1,
        soft_max=2.5,
        max = 5,
        update=update_live_physics,
    )

    physics_baked_tightness: bpy.props.FloatProperty(
        name="Spring Hardness",
        description="internal",
    )
    physics_baked_dampening: bpy.props.FloatProperty(
        name="Spring Damping",
        description="internal",
        subtype="PERCENTAGE",
    )
    physics_baked_softness: bpy.props.FloatProperty(
        name="Spring Softness",
        description="internal",
        subtype="PERCENTAGE",
    )
    physics_baked_multiplier: bpy.props.FloatProperty(
        name="Force Multiplier",
        description="internal",
        subtype="PERCENTAGE",
    )

    baked_use_gravity: bpy.props.BoolProperty(
        name="Simulate Gravity",
        description="internal"
    )

    baked_auto_level: bpy.props.FloatProperty(
        name="Auto Level",
        description="internal"
    )

    baked_spring_offset: bpy.props.FloatProperty(
        name="Spring Offset",
        description="internal"
    )

    baked_mass: bpy.props.FloatProperty(
        name="Vehicle Mass",
        description="internal"
    )

    baked_frame_start: bpy.props.IntProperty(
        name="Frame Start",
        description="internal"
    )

    baked_frame_end: bpy.props.IntProperty(
        name="Frame End",
        description="internal"
    )

    needs_bake: bpy.props.BoolProperty(default=False)

    baked_physics: bpy.props.BoolProperty(default=False)

    mute_physics: bpy.props.BoolProperty(default=False)

    overdrive_pitch: bpy.props.FloatProperty(
        name="Rotational Influence",
        description="Overdrive the Pitch during acceleration and braking.",
        #update=update_postFX,
        default=(100),
        min=0,
        soft_max=400,
        max=1000,
        subtype="PERCENTAGE",
    )
    overdrive_yaw: bpy.props.FloatProperty(
        name="Rotational Influence",
        description="Overdrive the Yaw during Turns and Drifts",
        #update=update_postFX,
        default=(100),
        min=0,
        soft_max=400,
        max=1000,
        subtype="PERCENTAGE",
    )
    overdrive_roll: bpy.props.FloatProperty(
        name="Rotational Influence",
        description="Overdrive the Roll during Turns and Drifts",
        #update=update_postFX,
        default=(100),
        min=0,
        soft_max=400,
        max=500,
        subtype="PERCENTAGE",
    )
    overdrive_location: bpy.props.FloatProperty(
        name="Locational Influence",
        description="Overdrive the Body Up/Down Wobble - Mostly visible during jumps.",
        #update=update_postFX,
        default=(100),
        min=0,
        soft_max=200,
        max=333,
        subtype="PERCENTAGE",
    )
    overdrive_wheel_location: bpy.props.FloatProperty(
        name="Wheel Locational Influence",
        description="Influence the amount of Ground Impact. This cannot be overdriven, only reduced. During jumps, this is best left at either 0% or 100%",
        #update=update_postFX,
        default=(100),
        min=0,
        max=100,
        subtype="PERCENTAGE",
    )
    overdrive_wheel_pressure: bpy.props.FloatProperty(
        name="Tire Pressure",
        description="Influence how much the tires are allowed to 'clip' into the ground during Ground Impacts",
        #update=update_tire_pressure,
        default=95,
        soft_min=80,
        min=0,
        max=100,
        subtype="PERCENTAGE",
    )
    overdrive_wheel_impact: bpy.props.FloatProperty(
        name="Ground detection impact",
        description="Blends between the two simulation methods used in the rig. At 0% the movement is fully calculated based on the movemnt of the body. At 100% the movement is fully calculated based on the impacts from the wheels. For acceleration, turns and braking keep this value low. For bumpy roads keep it high. For jumps, find a good compromise. :)",
        #update=update_postFX,
        default=30,
        min=0,
        max=100,
        subtype="PERCENTAGE",
    )

    # headlights
    headlights_presets: bpy.props.EnumProperty(
        items=[(key, key, "") for key in HEADLIGHTS],
        default=HEADLIGHTS_DEFAULT,
        update=update_headlights_presets,
        options=set(),
    )

    low_beam_temperature: bpy.props.FloatProperty(
        name="Temperature",
        description="Temperature of the Headlights in Kilo-kelvin (kK)",
        update=update_headlight,
        default=7,
        soft_min=2.7,
        soft_max=18,
        options=set(),
    )
    low_beam_intensity: bpy.props.FloatProperty(
        name="Intensity",
        description="Intensity for the Headlights in Kilo-Lumen (klm)",
        update=update_headlight,
        default=0.7,
        soft_min=0.05,
        soft_max=4,
        options=set(),
    )
    low_beam_spread: bpy.props.FloatProperty(
        name="Spread",
        description="How much the Headlights spread the light (Approximate angle)",
        update=update_headlight,
        default=(155 * (math.pi / 180)),
        soft_min=(80 * (math.pi / 180)),
        soft_max=(177 * (math.pi / 180)),
        unit="ROTATION",
        options=set(),
    )
    low_beam_sharpness: bpy.props.FloatProperty(
        name="Sharpness",
        description="How soft/sharp the light beam looks. Affected by the distance of the light ray",
        update=update_headlight,
        default=1,
        min=0.01,
        soft_max=5,
        options=set(),
    )

    high_beam_temperature: bpy.props.FloatProperty(
        name="Temperature",
        description="Temperature of the Headlights in Kilo-kelvin (kK)",
        update=update_headlight,
        default=7,
        soft_min=2.7,
        soft_max=18,
        options=set(),
    )
    high_beam_intensity: bpy.props.FloatProperty(
        name="Intensity",
        description="Intensity for the Headlights in Kilo-Lumen (klm))",
        update=update_headlight,
        default=1.2,
        soft_min=0.05,
        soft_max=4,
        options=set(),
    )
    high_beam_spread: bpy.props.FloatProperty(
        name="Spread",
        description="How much the Headlights spread the light (Approximate angle)",
        update=update_headlight,
        default=(155 * (math.pi / 180)),
        soft_min=(80 * (math.pi / 180)),
        soft_max=(177 * (math.pi / 180)),
        unit="ROTATION",
        options=set(),
    )
    high_beam_sharpness: bpy.props.FloatProperty(
        name="Sharpness",
        description="How soft/sharp the light beam looks. Affected by the distance of the light ray",
        update=update_headlight,
        default=1,
        min=0.01,
        soft_max=5,
        options=set(),
    )

    # skidmark settings
    skidmarks_mul: bpy.props.FloatProperty(
        name = "Skidmark Intensity",
        description="Similar to Multiplier of skidmark amount", 
        update=update_skidmarks,
        default=1,
        min=0.01,
        soft_max=5,
        options=set(),
    )

    skidmarks_var: bpy.props.FloatProperty(
        name = "Skidmark Variance",
        description="Similar to Contrast of skidmark amount", 
        update=update_skidmarks,
        default=1,
        min=0.01,
        soft_max=5,
        options=set(),
    )

    # custom path settings
    custom_path: bpy.props.PointerProperty(
        type = Object,
        name = "Or select your own Driving Path. [OPTIONAL] - (Will override any selected Animation Presets)", 
        poll = driving_path_poll,
        update = update_user_path,
    )

    frame_custom_path_start: bpy.props.IntProperty(
        name='Start',
        description = "User Path Animation Start Frame",
        default=0,
        min=0,
        update = update_user_path_range,
        options=set(),
    )

    frame_custom_path_end: bpy.props.IntProperty(
        name='End',
        description = "User Path Animation End Frame",
        default=250,
        min=0,
        update = update_user_path_range,
        options=set(),
    )

    # color tag
    color_tag: bpy.props.StringProperty(
        name="Color Tag",
        description="Color Tag of the Vehicle",
        default="",
    )

    # user path interpolation
    path_anim_intpl: bpy.props.EnumProperty(
        name = "Animation Interpolation",
        description = "Interpolation Type used for the new animated created for the user path",
        items=[
            ("AUTO_CLAMPED", "", "Ease in and Ease out animation, with a static start and end", "HANDLE_ALIGNED", 0),
            ("VECTOR", "", "Linear animation with a constant speed all the way through", "HANDLE_VECTOR", 1),
        ]
    )

    # lc version
    lc_version: bpy.props.StringProperty(
        name="LC Vehicle Version",
        description="Which version of Launch Control the Selected Vehicle is rigged with",
        default="0.0.0",
    )

    interpolation_mode: bpy.props.EnumProperty(
        name = "Interpolation",
        description = "Interpolation Mode to use for the Speed Segments",
        items=[   
            ('auto', 'Automatic', 'Let LC do all the interpolation for you - You just set the speeds you want', 'HANDLE_AUTO', 0),
            ('use_offset_time', 'Offset Time', 'Manually set "Offset Time" between Speed Keyframes to adjust accelerations', 'TIME', 1),
            ('free', 'Free', 'Take full control - LC wont mess with the interpolation', 'HANDLE_FREE', 2),
        ]
    )

    auto_fit_frame_range: bpy.props.BoolProperty(
        name = "Auto-fit Frames",
        description = "Adjust the scene frame range automatically to fit the created Speed Keyframes",
        default = True,
        options=set(),
    )

    settings_speed_segments: bpy.props.BoolProperty(
        name = "Settings",
        description = "Reveal settings for the speed segment tool",
        default = False,
        options=set(),
    )

    timecode_type: bpy.props.EnumProperty(
        name = "Timecode",
        description = "Select the timecode to show above the Speed Keyframes",
        items=[
            ("SEC","Seconds","",),
            ("FRAME", "Frames", ""),
        ],
        options=set(),
    )
    
    units_type: bpy.props.EnumProperty(
        name = "Speed",
        description = "Change the global units for Launch Control inside the add-on preferences",
        items=[
            ("UNIT","In Preferences","",),
        ],
        options=set(),
    )

    graph_enable: bpy.props.BoolProperty(
        name = "Visible",
        description = "Show the interactive Speed Graph (Heavy on Performance)",
        default = True,
        options=set(),
    )
    
    speed_graph_resolution: bpy.props.IntProperty(
        name='Graph Resolution',
        description = "Amount of interpolated speed points on the graph. Higher Resolutions = Bigger Performance Impact.",
        default=64,
        min=16,
        soft_max=512,
        max=2048,
        options=set(),
    )

    graph_scale: bpy.props.FloatProperty(
        name='Graph Scale',
        description = "Height of the Speed Graph. Increase this to get a better view of speed changes",
        default=1,
        soft_min=0.5,
        soft_max=4,
        options=set(),
    )

    graph_color: bpy.props.FloatVectorProperty(
        name='Graph Color',
        description = "Change the color of the graph to make it more visible",
        default=(0.5, 0.5, 0.5, 1),
        size=4,
        subtype='COLOR_GAMMA',
        min = 0.0,
        max = 1.0,
        options=set(),
    )

    type_speed: bpy.props.FloatProperty(
        name='Input Speed',
        description = "Type in the desired Speed for the selected Speed Keyframe for more accurate manipulation",
        default=80,
        subtype="UNSIGNED",
        min = 0,
        options=set(),
    )

    type_offset_time_frame: bpy.props.IntProperty(
        name='Input Offset Time',
        description = "Type in the desired Offset Time for the selected Speed Keyframe for more accurate manipulation",
        default=50,
        min = 1,
        options=set(),
    )

    type_offset_time_sec: bpy.props.FloatProperty(
        name='Input Offset Time',
        description = "Type in the desired Offset Time for the selected Speed Keyframe for more accurate manipulation",
        default=2,
        subtype="TIME",
        min = 0.1,
        options=set(),
    )

    model_quality:  bpy.props.EnumProperty(
        name="Model Quality",
        description="The quality at which the vehicle will be shown in the viewport.",
        items=[
            (
                "proxy",
                "Proxy",
                "Show only the Proxy version of the model",
                "ALIASED",
                0,
            ),
            (
                "full",
                "Full Mesh",
                "Show only the Full Mesh version of the model",
                "ANTIALIASED",
                1,
            ),
            (
                "overlay",
                "Overlay",
                "Show both the Full Mesh and the Proxy version of the model",
                "OVERLAY",
                2,
            ),
        ],
        default="overlay",
        options=set(),
        update=update_proxy,
    )

    cad_wheel_size_rear: bpy.props.FloatProperty(
        name="internal", 
        default=0.631901,
    )

    cad_wheel_size_front: bpy.props.FloatProperty(
        name="internal", 
        default=0.631901,
    )

    has_lib_override: bpy.props.BoolProperty(
        name = "internal",
        default = False,
    )

    garage_mode_loc: bpy.props.FloatVectorProperty(
        name='internal',
        default=(0, 0, 0),
        size=3
    )

    garage_mode_rot_z: bpy.props.FloatProperty(
        name='internal',
        default=0,
    )




    
