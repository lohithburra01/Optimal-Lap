### GLOBAL VARIABLES ###

### FILENAMES ###
FILENAME_BLEND = "car_rig.blend"

COLLECTIONNAME_ADDON = "LaunchControl"
COLLECTIONNAME_CARRIG = "CarRig"
COLLECTIONNAME_LIGHTS = "Lights"
COLLECTIONNAME_INTERNAL = "InternalCar"
COLLECTIONNAME_SKIDMARK = "SkidmarkEngine"
COLLECTIONNAME_GROUNDDETECT = "GroundDetection"
COLLECTIONNAME_PROXY = "Proxy"

FILENAME_CARRIG_ARMATURE = "A_CarRig"

OBJECT_HIGHBEAM_L = "high_beam.L"
OBJECT_HIGHBEAM_R = "high_beam.R"
OBJECT_LOWBEAM_L = "low_beam.L"
OBJECT_LOWBEAM_R = "low_beam.R"

FILENAME_L_HIGHBEAM_L = "L_high_beam.L"
FILENAME_L_HIGHBEAM_R = "L_high_beam.R"
FILENAME_L_LOWBEAM_L = "L_low_beam.L"
FILENAME_L_LOWBEAM_R = "L_low_beam.R"

FILENAME_DRIVINGPATH = "driving_path"
FILENAME_CAR_RIG = "car_rig"
FILENAME_LATTICE_FR = "lattice.FR"
FILENAME_LATTICE_FL = "lattice.FL"
FILENAME_LATTICE_RR = "lattice.RR"
FILENAME_LATTICE_RL = "lattice.RL"
FILENAME_SHRINKWRAP = "shrinkwrap_switches"
FILENAME_SHRINKWRAPTOP = "shrinkwrap_switches_top"
FILENAME_WHEELANIMPROPS = "internal_wheel_anim_props" 
FILENAME_SKIDMARK_ENGINE_FL = "skidmark_engine_FL"
FILENAME_SKIDMARK_ENGINE_FR = "skidmark_engine_FR"
FILENAME_SKIDMARK_ENGINE_RL = "skidmark_engine_RL"
FILENAME_SKIDMARK_ENGINE_RR = "skidmark_engine_RR"
FILENAME_SKIDMARK_MEASURE_FL = "skidmark_measure_FL"
FILENAME_SKIDMARK_MEASURE_FR = "skidmark_measure_FR"
FILENAME_SKIDMARK_MEASURE_RL = "skidmark_measure_RL"
FILENAME_SKIDMARK_MEASURE_RR = "skidmark_measure_RR"
FILENAME_GROUND_LOCAL = "ground_detect_remeshed"
FILENAME_GROUND_GLOBAL = "ground_detect_combined"
FILENAME_GROUND_RIG_SETUP = "ground_detect_rig_setup_mode"
FILENAME_COLLIDER_DEFAULT = "col_turn_01"
FILENAME_DUMMY = "dummy"
FILENAME_DUMMY_GROUND = "dummy_ground"
FILENAME_CUSTOM_PROPS = "internal_custom_props"

FILENAME_SIM_BODY = "sim_Body"
FILENAME_SIM_WHEELS = "sim_Wheels"
FILENAME_SIM_ACC_VIZ = "sim_acc_Visulizer"
FILENAME_SIM_VEL_VIZ = "sim_vel_Visulizer"
FILENAME_SIM_TRACK_TO = "sim_TrackTo"
FILENAME_TRACK_WHEEL_FL = "track_wheel_FL"
FILENAME_TRACK_WHEEL_FR = "track_wheel_FR"
FILENAME_TRACK_WHEEL_RL = "track_wheel_RL"
FILENAME_TRACK_WHEEL_RR = "track_wheel_RR"

# Bind Pose Nulls
FILENAME_BIND_POSE_BODY = "bind_pose_body"
FILENAME_BIND_POSE_STEERING = "bind_pose_steering"
FILENAME_BIND_POSE_WHEEL_RL = "bind_pose_wheel.RL"
FILENAME_BIND_POSE_WHEEL_RR = "bind_pose_wheel.RR"
FILENAME_BIND_POSE_WHEEL_FL = "bind_pose_wheel.FL"
FILENAME_BIND_POSE_WHEEL_FR = "bind_pose_wheel.FR"
FILENAME_BIND_POSE_BRAKE_RL = "bind_pose_brake.RL"
FILENAME_BIND_POSE_BRAKE_RR = "bind_pose_brake.RR"
FILENAME_BIND_POSE_BRAKE_FL = "bind_pose_brake.FL"
FILENAME_BIND_POSE_BRAKE_FR = "bind_pose_brake.FR"

FILENAME_SPEEDOMETER = "speedometer"
FILENAME_UNIT = "unit"
FILENAME_UNIT_FLIPPED = "unit_flipped"
FILENAME_SPEED_CALCULATOR = "speed_calculator"

FILENAME_TEMP_CAR_RIG = "temp_CarRig"

# headlight
HEADLIGHT = "headlight"


### MATERIALS ###
M_SKIDMARK_MATERIAL = "mat_skidmark"


### BONES ###
# Switch
B_SWITCH_SETUP = "bone_Switch_Setup"
B_SWITCH_SETUP_DEFAULT_VALUE = 1.8
B_SWITCH_USE_SIMULATION = "bone_Switch_UseSimulationData"
B_SWITCH_AIRBOURNE = "bone_Switch_Airbourne"
B_SWITCH_AIRBOURNE_ROT = "bone_Slider_AirbourneConstrainRot"
B_SWITCH_STEERING_WHEEL = "bone_Switch_SteeringWheelCount"
B_SWITCH_SINGLE_AXLE_FRONT = "bone_Switch_SingleAxle_Front"
B_SWITCH_SINGLE_AXLE_REAR = "bone_Switch_SingleAxle_Rear"

B_BODY_DEFORM = "bone_body_deform"
B_BODY_FOLLOW_PATH = "bone_body_FollowPath"
B_BODY_WHEEL_IMPACT = "bone_body_wheelImpactCTRL"
B_BODY_DRIFT = "bone_body_Drift"
B_BODY_WHEEL_IMPACT_TARGET = "bone_body_wheelImpactTarget"
B_BODY_DRIFT_OFFSET = "bone_body_DriftOffset"
B_WHEEL_DEFORM = "bone_wheel_deform"
B_WHEEL_CALIPER_DEFORM = "bone_wheel_caliperDeform"
B_WHEEL_STEERING_SIMPLE_FR = "bone_wheel_steeringSimple.FR"
B_WHEEL_STEERING_SIMPLE_FL = "bone_wheel_steeringSimple.FL"
B_WHEEL_STEERING_SIMPLE_RR = "bone_wheel_steeringSimple.RR"
B_WHEEL_STEERING_SIMPLE_RL = "bone_wheel_steeringSimple.RL"
B_WHEEL_CAL_AUTO_FR = "bone_wheel_calAuto.FR"
B_WHEEL_CAL_AUTO_FL = "bone_wheel_calAuto.FL"
B_WHEEL_CAL_AUTO_RR = "bone_wheel_calAuto.RR"
B_WHEEL_CAL_AUTO_RL = "bone_wheel_calAuto.RL"
B_WHEEL_SHAKE_RR = "bone_wheelShake.RR"
B_WHEEL_SHAKE_RL = "bone_wheelShake.RL"
B_WHEEL_SHAKE_FL = "bone_wheelShake.FL"
B_WHEEL_SHAKE_FR = "bone_wheelShake.FR"
B_WHEEL_FLOOR_RR = "bone_wheelFloor.RR"
B_WHEEL_FLOOR_RL = "bone_wheelFloor.RL"
B_WHEEL_FLOOR_FL = "bone_wheelFloor.FL"
B_WHEEL_FLOOR_FR = "bone_wheelFloor.FR"
B_WHEEL_CAMBEROFFSET_RR = "bone_wheel_camberOffsetIndividual.RR"
B_WHEEL_CAMBEROFFSET_RL = "bone_wheel_camberOffsetIndividual.RL"
B_WHEEL_CAMBEROFFSET_FL = "bone_wheel_camberOffsetIndividual.FL"
B_WHEEL_CAMBEROFFSET_FR = "bone_wheel_camberOffsetIndividual.FR"
B_WHEEL_ARCH_LIMIT_RR = "bone_limiter_arch_handle_simd.RR"
B_WHEEL_ARCH_LIMIT_RL = "bone_limiter_arch_handle_simd.RL"
B_WHEEL_ARCH_LIMIT_FL = "bone_limiter_arch_handle_simd.FL"
B_WHEEL_ARCH_LIMIT_FR = "bone_limiter_arch_handle_simd.FR"

# Rebase bones
B_BODY_DEFORM_REBASE = "bone_body_deform_rebase"
B_STEERING_DEFORM_REBASE = "bone_steeringWheel_deform_rebase"
B_WHEEL_DEFORM_REBASE_RL = "bone_wheel_deform_rebase.RL"
B_WHEEL_DEFORM_REBASE_RR = "bone_wheel_deform_rebase.RR"
B_WHEEL_DEFORM_REBASE_FL = "bone_wheel_deform_rebase.FL"
B_WHEEL_DEFORM_REBASE_FR = "bone_wheel_deform_rebase.FR"
B_BRAKE_DEFORM_REBASE_RL = "bone_wheel_caliperDeform_rebase.RL"
B_BRAKE_DEFORM_REBASE_RR = "bone_wheel_caliperDeform_rebase.RR"
B_BRAKE_DEFORM_REBASE_FL = "bone_wheel_caliperDeform_rebase.FL"
B_BRAKE_DEFORM_REBASE_FR = "bone_wheel_caliperDeform_rebase.FR"
B_REBASE_COPYTRANSFORMS = "bone_rebase_copyTransforms"


# Deform bones
B_BODY_DEFORM = "bone_body_deform"
B_STEERING_DEFORM = "bone_steeringWheel_deform"
B_WHEEL_DEFORM_RL = "bone_wheel_deform.RL"
B_WHEEL_DEFORM_RR = "bone_wheel_deform.RR"
B_WHEEL_DEFORM_FL = "bone_wheel_deform.FL"
B_WHEEL_DEFORM_FR = "bone_wheel_deform.FR"
B_BRAKE_DEFORM_RL = "bone_wheel_caliperDeform.RL"
B_BRAKE_DEFORM_RR = "bone_wheel_caliperDeform.RR"
B_BRAKE_DEFORM_FL = "bone_wheel_caliperDeform.FL"
B_BRAKE_DEFORM_FR = "bone_wheel_caliperDeform.FR"


B_INTERACTIVE_WHEEL_PAIR = "bone_Interactive_WheelPairTurn"
B_SPEED_ROTATE = "bone_Speed_Rotate"

# Simulations
B_BODY_SIM_WIGGLE = "bone_body_wiggleSimCTRL"
B_BODY_SIM_MASS = "bone_body_massSim"
B_WHEEL_SIM_FR = "bone_wheel_sim.FR"
B_WHEEL_SIM_FL = "bone_wheel_sim.FL"
B_WHEEL_SIM_RR = "bone_wheel_sim.RR"
B_WHEEL_SIM_RL = "bone_wheel_sim.RL"

# Sliders
B_SLIDER_BODY_WEIGHT = "bone_Slider_wheelClipping"
B_SLIDER_BODY_WEIGHT_DEFAULT_VALUE = 0.2
B_SLIDER_CAMBER_TOE = "bone_Slider_CamberToe"
B_SLIDER_CAMBER_TOE_DEFAULT_VALUE = [0, 0, 0]
B_SLIDER_WHEEL_CAMBER = "bone_Slider_WheelCamber"
B_SLIDER_WHEEL_CAMBER_DEFAULT_VALUE = 0.5
B_SLIDER_WHEEL_WOBBLE = "bone_Slider_WheelWobble"
B_SLIDER_WHEEL_SHAKE = "bone_Slider_WheelShake"
B_SLIDER_STEERING_FACTOR = "bone_Slider_SteeringFactor"
B_SLIDER_PIVOT_POS = "bone_Slider_PivotPos"
B_SLIDER_MAX_SUSPENSION_FRONT = "bone_Slider_MaxSuspensionTravel_Front"
B_SLIDER_MAX_SUSPENSION_FRONT_DEFAULT_VALUE = 0.2
B_SLIDER_MAX_SUSPENSION_REAR = "bone_Slider_MaxSuspensionTravel_Rear"
B_SLIDER_MAX_SUSPENSION_REAR_DEFAULT_VALUE = 0.2
B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT = "bone_Slider_bottomOutHeight_Front"
B_SLIDER_BOTTOM_OUT_HEIGHT_FRONT_DEFAULT_VALUE = 0.5
B_SLIDER_BOTTOM_OUT_HEIGHT_REAR = "bone_Slider_bottomOutHeight_Rear"
B_SLIDER_BOTTOM_OUT_HEIGHT_REAR_DEFAULT_VALUE = 0.5
B_SLIDER_SIMPLE_STEERING = "bone_Slider_SimpleSteering"
B_SLIDER_INTERNAL_MUTE = "bone_Slider_INTERNAL_Mute"
B_SLIDER_INTERNAL_MUTE_DEFAULT_VALUE = 1
B_SLIDER_TIRE_DEFORM_FACTOR = "bone_Slider_TireDeformFactor"
B_SLIDER_TURN_LIMIT = "bone_Slider_TurnLimit"
B_SLIDER_BOTTOM_OUT = "bone_Slider_bottomOutHeight"
B_SLIDER_STEERINGACCURACY = "bone_Slider_SteeringAccuracy"
B_SLIDER_STEERINGACCURAC_DEFAULT_VALUE = 0.25


# custom
B_CUSTOM_MASS = "bone_CustomMass_Move"
B_WHEEL_CUSTOM_SUSPENSION_FR = "bone_wheel_customSuspension.FR"
B_WHEEL_CUSTOM_SUSPENSION_FL = "bone_wheel_customSuspension.FL"
B_WHEEL_CUSTOM_SUSPENSION_RR = "bone_wheel_customSuspension.RR"
B_WHEEL_CUSTOM_SUSPENSION_RL = "bone_wheel_customSuspension.RL"
B_WHEEL_CUSTOM_SPIN_FR = "bone_wheel_customSpin.FR"
B_WHEEL_CUSTOM_SPIN_FL = "bone_wheel_customSpin.FL"
B_WHEEL_CUSTOM_SPIN_RR = "bone_wheel_customSpin.RR"
B_WHEEL_CUSTOM_SPIN_RL = "bone_wheel_customSpin.RL"
B_WHEEL_CUSTOM_TURN_FR = "bone_wheel_customTurn.FR"
B_WHEEL_CUSTOM_TURN_FL = "bone_wheel_customTurn.FL"
B_WHEEL_CUSTOM_TURN_RR = "bone_wheel_customTurn.RR"
B_WHEEL_CUSTOM_TURN_RL = "bone_wheel_customTurn.RL"

# Handles
B_BONE_SETUP_WHEEL_BASE_HANDLE_REST_POS = (2.99497127532959, -4.300894260406494, 0)
B_BONE_SETUP_TRACK_WIDTH_HANDLE_REST_POS = (1.0645328760147095, -6.257040023803711, 0)
B_BONE_SETUP_WHEEL_RADIUS_HANDLE_REST_POS = (1.695719838142395, 0, 0.7065216898918152)

# bones that need reference objects
B_BONE_FIND_UP_DIR = "bone_find_up_dir"
B_BONE_SETUP_LENGTH = "bone_setup_parent_Length"
B_BONE_SETUP_REST = "bone_setup_parent_Rest"
B_BONE_UI = "bone_UI_Follow"
B_BONE_GROUND_DETECT_RL = "bone_groundDetect.RL"
B_BONE_GROUND_DETECT_RR = "bone_groundDetect.RR"
B_BONE_GROUND_DETECT_FL = "bone_groundDetect.FL"
B_BONE_GROUND_DETECT_FR = "bone_groundDetect.FR"
B_BONE_GROUND_DETECT_ABS_RL = "bone_groundDetectAbs.RL"
B_BONE_GROUND_DETECT_ABS_RR = "bone_groundDetectAbs.RR"
B_BONE_GROUND_DETECT_ABS_FL = "bone_groundDetectAbs.FL"
B_BONE_GROUND_DETECT_ABS_FR = "bone_groundDetectAbs.FR"

# camera hooks
B_HOOK_CAM_FOLLOW = "bone_cam_follow"
B_HOOK_CAM_MOUNTED = "bone_cam_mounted"

### ARMATURE ###
# Layer visibility
LAYER_VISIBILITY_DEFAULT = (True, True, False, False, False, False, False, False, False, False, False, False,
            False, False, False, False, False, False, False, False, False, False, False, False, False, False,
            False, False, False, False, False, False,)


# ANIMATIONS
# Gravity | End Frame
ANIMATIONS = {
    "Bumps 01": (1, 200),
    "Burnout 01": (1, 280),
    "Burnout 02": (1, 380),
    "Drift 01": (1, 400),
    "Drift 02": (1, 500),
    "Drift 03": (1, 250),
    "Drift 04": (1, 300),
    "Drift 05": (1, 900),
    "Jump 01": (1, 200),
    "Jump 02": (1, 300),
    "Loop 01": (0, 300),
    "Offroad 01": (1, 450),
    "Slalom 01": (1, 200),
    "Slalom 02": (1, 205),
    "Straight 01": (1, 200),
    "Straight 02": (1, 900),
    "Turn 01": (1, 250),
    "Turn 02": (1, 330),
}
ANIMATIONS_DEFAULT = "Turn 01"
ANIMATIONS_DEFAULT_VALUES = (1, 250)

ANIM_INTPL_DEFAULT = "ALIGNED"

# PHYSICS 
# weight | dampening | softness | vehicle mass | spring offset
PHYSICS = {
    "Road Car": (40, 35, 25, 1.5, 0),
    "Heavy Truck": (22, 30, 0, 3.0, 0.09),
    "Race Car": (50, 40, 0, 1.0, 0),
    "Rally Car": (25, 45, 0, 1.5, 0.03),
    "Cartoon Car": (45, 15, 0, 1.5, 0),
    "Active Suspension": (10, 40, 75, 1.0, 0.1),
}
PHYSICS_DEFAULT = "Road Car"
PHYSICS_DEFAULT_VALUES = (40, 35, 25, 1.5, 0)

# HEADLIGHTS
HEADLIGHTS = {
    "Circular": 3,
    "Exotic": 9,
    "LED": 11,
    "Matrix": 15,
    "Prism": 7,
    "Vintage": 2.5,
}
HEADLIGHTS_DEFAULT="Circular"
HEADLIGHTS_DEFAULT_VALUES = ((7.3, 7.3), (.07, .07), (1.0472, 1.0472), (1, 1))


# LABELS
LABELS_OBJECTS = {
    "body": ["body", "hull"],
    "wheel": [
        "tire",
        "wheel",
        "wheels",
        "tires",
        "rad",
        "räder",
        "tyre",
        "tyres",
    ],
    "brake": [
        "brake",
        "brakes",
        "calliper",
        "caliper",
        "callipers",
        "calipers",
        "bremse",
    ],
    "wheelcover": [
        "wheel_cover",
        "wheelcover",
        "skirt",
        "wheel_skirt",
        "wheelskirt",
    ],
    "headlight": [
        "headlight",
        "headlamp",
        "headbulb",
        "front_light",
        "front_lamp",
        "front_bulb",
        "front_emitter",
    ]
}

LABELS_LOCATIONS = {
    "Rear Left": ["RL", "RearLeft", "_BL_", ".BL.", "BkL", "Bk.L", "Bk_L"],
    "Rear Right": ["RR", "RearRight", "_BR_", ".BR.", "BkR", "Bk.R", "Bk_R"],
    "Front Right": ["FR", "FrontRight", "FtR", "Ft.R", "Ft_R"],
    "Front Left": ["FL", "FrontLeft", "FtL", "Ft.L", "Ft_L"],
    "Right": ["R", "right"],
    "Left": ["L", "left"]
}


# DEFAULT COLLIDERS
DEFAULT_GROUNDS = [
            "col_turn_01",
            "col_turn_02",
            "col_bumps_01",
            "col_drift_01",
            "col_drift_02",
            "col_drift_03",
            "col_drift_04",
            "col_jump_01",
            "col_pffroad_01",
            "col_slalom_01",
            "col_slalom_02",
            "col_loop_01"
        ]

# GEO NODE GROUPS
GEONODE_SKIDMARK = "geo_nodes_skidmark_engine"
PHYSICS_BODY = "geo_nodes_sim_body"
PHYSICS_WHEELS = "geo_nodes_sim_wheels"
SPEED_VIZ = "Visualize_Speed"
SPEED_CALC = "geo_nodes_speed"


# GEO NODES CACHE PATHS
SKIDMARK_ENGINE_FL_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_FL"
SKIDMARK_ENGINE_FR_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_FR"
SKIDMARK_ENGINE_RL_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_RL"
SKIDMARK_ENGINE_RR_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_RR"

SKIDMARK_ENGINE_FL_LIFT_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_FL_lift"
SKIDMARK_ENGINE_FR_LIFT_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_FR_lift"
SKIDMARK_ENGINE_RL_LIFT_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_RL_lift"
SKIDMARK_ENGINE_RR_LIFT_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/skidmark_engine_RR_lift"

SIM_BODY_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/sim_body"
SIM_TRACK_TO_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/sim_track_to"
SIM_INIT_POS_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/sim_wheels_initial_pos"
SIM_WHEELS_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/sim_wheels"
SPEED_CALCULATOR_DEFAULTPATH = "//blendcache_Launch_Control/file/lc_car/speed_calculator"


# OBJECT POINTERS
GROUND_DETECT_WRAP_UP = "Wrap_Upwards"
GROUND_DETECT_WRAP_DOWN = "Wrap_Downwards"
GROUND_DETECT_TRUE_GROUND = "True_Ground"