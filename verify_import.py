import sys
import os
from unittest.mock import MagicMock

# Mock bpy
mock_bpy = MagicMock()
sys.modules['bpy'] = mock_bpy

# Add path
target_path = r"c:\Users\91910\Downloads\cricket\f1_hot_lap\launch_control_auto_car_rig\launch_control_auto_car_rig\launch_control\operators"
sys.path.append(target_path)

try:
    import F1_HiFi_Baker_Pro
    print("Successfully imported F1_HiFi_Baker_Pro")
    
    if hasattr(F1_HiFi_Baker_Pro, 'generate_telemetry_csv'):
        print("Function 'generate_telemetry_csv' exists.")
    else:
        print("ERROR: Function 'generate_telemetry_csv' NOT found.")

    if hasattr(F1_HiFi_Baker_Pro, 'generate_minimap_frames'):
        print("Function 'generate_minimap_frames' exists.")
    else:
        print("ERROR: Function 'generate_minimap_frames' NOT found.")

    if hasattr(F1_HiFi_Baker_Pro, 'generate_multirail_data'):
        print("Function 'generate_multirail_data' exists.")
    else:
        print("ERROR: Function 'generate_multirail_data' NOT found.")
        
except Exception as e:
    print(f"Import failed: {e}")
