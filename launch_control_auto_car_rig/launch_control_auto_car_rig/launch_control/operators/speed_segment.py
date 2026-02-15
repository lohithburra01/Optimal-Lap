import bpy
import blf
import gpu
import math
import numpy as np
from mathutils import Vector, Matrix, Euler
from gpu_extras.batch import batch_for_shader

from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_vector_3d

from ..ui.utils import show_message_box
from ..logger import log_error, log_info
from ..utils.functions import get_speed_rotate_keyframes, get_speed_rotate_fcurve
from ..utils.validations import validate_lc_object

def get_slope(p1, p2):
        
    try: slope = (p2[1]-p1[1]) / (p2[0]-p1[0])
    except: slope = 0
            
    return slope
    
def get_speed(slope):  #in m/s
    
    rad_per_frame = slope
    rad_per_sec = (rad_per_frame*25)
    m_per_sec = rad_per_sec*10
    
    return m_per_sec
    

def key_smooth():
    scene = bpy.context.scene
    car = scene.lc.find_selected()
    rig_object = car.rig_object
    car_props = car.properties
    fcurve = get_speed_rotate_fcurve(rig_object)
    keyframe_points = get_speed_rotate_keyframes(rig_object)
    list_len = len(keyframe_points)

    if car_props.interpolation_mode == 'auto' or car_props.interpolation_mode == 'use_offset_time':
        if list_len < 3:
            for key in keyframe_points:
                key.handle_left_type = 'VECTOR'
                key.handle_right_type = 'VECTOR'
            
            fcurve.auto_smoothing = 'CONT_ACCEL'
            
        else:
            # Remove dublicate keyframes
            i = 0
            keys_to_remove = []

            for key in keyframe_points:
                # Avoid if it's the last key
                if key != keyframe_points[list_len-1]:
                    if key.co == keyframe_points[i+1].co:
                        keys_to_remove.append(key)
            
                i += 1

            for remove_key in keys_to_remove:
                rig_object.keyframe_delete(data_path=fcurve.data_path, frame=remove_key.co[0])
            
            list_len = len(keyframe_points)


            # collect points for smoothing
            key_list = []
            i = 0
            for key in keyframe_points:
                
                if i > 0:  # add post key if not id "last +1" or id "-1"
                    key_list.append(key)
                
                i += 1
                            
            
            i = 0
            for key in keyframe_points:
                if key in key_list:
                    
                    # Force handle type
                    key.handle_left_type = 'ALIGNED'
                    key.handle_right_type = 'ALIGNED'
                    
                    
                    # Adjust time offset automatically
                    if car_props.interpolation_mode == 'auto':
                        if key != keyframe_points[0]:
                            
                            frame02 = key.co[0]
                            dist02 = key.co[1]
                            speed_key02 = get_speed(get_slope(    key.co, key.handle_right    ))
                            
                            frame01 = keyframe_points[i-1].co[0]
                            dist01 = keyframe_points[i-1].co[1]
                            speed_key01 = get_speed(get_slope(    keyframe_points[i-1].co, keyframe_points[i-1].handle_right    ))
                        
                            #fps = bpy.context.scene.render.fps
                            fps = 24  #locked fps as LC was developed for this framerate
                            d_dist = (dist02-dist01)*10
                            
                            

                            # Auto in-between time
                            avg_speed = (speed_key02 + speed_key01)/2
                            if avg_speed < 0.1:
                                avg_speed = 0.1


                            d_time = d_dist/avg_speed
                            d_frames = d_time*fps

                            frames_to_offset = d_frames - (frame02 - frame01)

                            id = 0
                            for key_post in keyframe_points:
                                if id >= i:
                                    key_post.co[0] += frames_to_offset
                                    key_post.handle_right[0] += frames_to_offset
                                    key_post.handle_left[0] += frames_to_offset

                                id += 1
                                    
                i += 1
                                
            
            # Calculate Tangents (1/3rd of the distance to post and pre and more cool stuffs)
            i = 0
            
            for key in keyframe_points:
                if key in key_list:

                    
                                                                                
                    # Avoid if it's the last key
                    if key != keyframe_points[list_len-1]:
                        dir_handle_right = key.handle_right - key.co
                        dir_handle_right.normalize()
                        
                        dist_post = (key.co - keyframe_points[i+1].co).length
                        
                        len_right = dist_post/3
                        key.handle_right = key.co + dir_handle_right*len_right
                        
                        # Restrict handle Y loc compared to pre and post key (Auto Clamped behaviour)
                        for n in range(0, 100):
                            if key.handle_right[1] < keyframe_points[i+1].co[1]:
                                break
                            
                            len_right = len_right*0.95
                            key.handle_right = key.co + dir_handle_right*len_right
                        
                        
                    # Avoid if it's the first key
                    if key != keyframe_points[0]:
                        dir_handle_left = key.handle_left - key.co
                        dir_handle_left.normalize()
                        
                        dist_pre = (key.co - keyframe_points[i-1].co).length
                        
                        len_left = dist_pre/3
                        key.handle_left = key.co + dir_handle_left*len_left
                        
                        # Restrict handle Y loc compared to pre and post key (Auto Clamped behaviour)
                        for n in range(0, 100):
                            if key.handle_left[1] > keyframe_points[i-1].co[1]:
                                break
                            
                            len_left = len_left*0.95
                            key.handle_left = key.co + dir_handle_left*len_left
                            
                i += 1
                

    # Set scene frame range
    if car_props.auto_fit_frame_range:
        scene.frame_start = int(keyframe_points[0].co[0])
        scene.frame_end = int(keyframe_points[list_len-1].co[0]+25)

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    max_len = addon_preferences.max_dur_speed_segments
    
    if (scene.frame_end-scene.frame_start) > max_len:
        scene.frame_end = max_len + scene.frame_start

    return None


def draw_callback_2d(self, context):
    font_id = 0  # XXX, need to find out how best to get this.
    scene = bpy.context.scene
    cls = self.__class__

    car = scene.lc.find_selected()
    car_props = car.properties
    emulate_3_buttons = bpy.context.preferences.inputs.use_mouse_emulate_3_button

    addon_root = ".".join(__package__.split(".")[:-2])
    addon_preferences = bpy.context.preferences.addons[addon_root].preferences
    draw_hotkey_tips = addon_preferences.draw_hotkey_tips

    if cls.AREA != bpy.context.area: # draw only modal area
        return
    
    if not self.bypass_draw:
        
        # draw knobs
        for knob in self.knobs:
            knob.draw()        
        
        # draw the 2D texts and boxes behind them
        i = 0
        for key_speed in self.keyframe_speeds:
            
            indices = ((0, 1, 2), (0, 2, 3))
            
            x = self.keyframe_region_x[i] - (40 * self.ui_scale)
            y = self.keyframe_region_y[i] + (15 * self.ui_scale)
            width = 100 * self.ui_scale
            height = 50 * self.ui_scale
            
            # bottom left, top left, top right, bottom right
            vertices = (
                        (x,                    y),
                        (x,                    y + height),
                        (x + width,            y + height),
                        (x + width,            y))
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            batch = batch_for_shader(shader, 'TRIS', {"pos" : vertices}, indices=indices)
            shader.uniform_float("color", (0.0, 0.0, 0.0, 0.6))
            
            batch.draw(shader)
            
            
            blf.position(font_id, self.keyframe_region_x[i] - (30 * self.ui_scale), self.keyframe_region_y[i] + (44 * self.ui_scale), 0)
            blf.size(font_id, 16*self.ui_scale) 
            blf.color(font_id, 0.8, 0.8, 0.8, 1)

            addon_root = ".".join(__package__.split(".")[:-2])
            addon_preferences = context.preferences.addons[addon_root].preferences
            use_imperial = addon_preferences.use_imperial

            val_speed = key_speed
            unit_speed = "kmh"

            if use_imperial:
                val_speed = key_speed*0.621371
                unit_speed = "mph"

            blf.draw(font_id, str(round(val_speed)) +  " " + unit_speed)

            rig_object = car.rig_object
            keys = get_speed_rotate_keyframes(rig_object)
            
            blf.position(font_id, self.keyframe_region_x[i] - (30 * self.ui_scale), self.keyframe_region_y[i] + (25 * self.ui_scale), 0)
            blf.size(font_id, 14*self.ui_scale)
            blf.color(font_id, 0.8, 0.8, 0.8, 0.65)
            #try: blf.draw(font_id, "Frame: " + str(round(keys[i].co[0])))
            #except: pass # if "keyframe_speeds" were not update, just ignore and avoid crash
            
            fps = bpy.context.scene.render.fps
            if car_props.timecode_type == 'FRAME':
                mul = 1
                timecode = "F"
                dec = 0
            else:
                mul = 1/fps
                timecode = "Sec"
                dec = 1
            if i == 0:
                try: blf.draw(font_id, timecode + ": " + str((round(  scene.start*mul  ,   dec   ))))
                except: pass # if "keyframe_speeds" were not update, just ignore and avoid crash
            else:
                try: blf.draw(font_id, timecode + ": +" + str((round((keys[i].co[0]*mul   -   keys[max(i-1, 0)].co[0]*mul), dec   ))))
                except: pass # if "keyframe_speeds" were not update, just ignore and avoid crash
        
            i += 1
    
    
    if draw_hotkey_tips:
        indices = ((0, 1, 2), (0, 2, 3))
        x = 20 * self.ui_scale
        y = 20 * self.ui_scale
        width = 400 * self.ui_scale
        height = 210 * self.ui_scale
        gap = 14 * self.ui_scale
        # bottom left, top left, top right, bottom right
        vertices = (
                    (x,                    y),
                    (x,                    y + height),
                    (x + width,            y + height),
                    (x + width,            y))
        
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        batch = batch_for_shader(shader, 'TRIS', {"pos" : vertices}, indices=indices)
        shader.uniform_float("color", (0.0, 0.0, 0.0, 0.4))
        
        batch.draw(shader)
        
        font_h = 20 * self.ui_scale
        blf.position(font_id, x + gap , y + height - font_h - gap/2, 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Speed Segments - Hotkeys")
        
        font_h = 12 * self.ui_scale
        blf.position(font_id, x + gap , y + height - font_h - gap - (30 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Add Key:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (30 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        if not emulate_3_buttons:
            blf.draw(font_id, "Ctrl + Alt + LMB on a Key")
        else:
            blf.draw(font_id, "Ctrl + Shift + LMB on a Key")

        blf.position(font_id, x + gap , y + height - font_h - gap - (50 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Delete Key:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (50 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        blf.draw(font_id, "RMB on the Key")

        blf.position(font_id, x + gap , y + height - font_h - gap - (70 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Move Key:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (70 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        blf.draw(font_id, "LMB drag")
        
        blf.position(font_id, x + gap , y + height - font_h - gap - (90 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Adjust Speed:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (90 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        blf.draw(font_id, "Ctrl + LMB drag")

        if car_props.interpolation_mode != 'auto':
            blf.position(font_id, x + gap , y + height - font_h - gap - (110 * self.ui_scale), 0)
            blf.size(font_id, font_h) 
            blf.color(font_id, 0.65, 0.65, 0.65, 1)
            blf.draw(font_id, "Offset Time:")
        
            blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (110 * self.ui_scale), 0)
            blf.size(font_id, font_h) 
            blf.color(font_id, 0.8, 0.8, 0.8, 1)
            if not emulate_3_buttons:
                blf.draw(font_id, "Alt + LMB drag")
            else:
                blf.draw(font_id, "Shift + LMB drag")
            
        
        """blf.position(font_id, x + gap , y + height - font_h - gap - (130 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Deselect All:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (130 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        blf.draw(font_id, "Alt + A")"""
        
        if not emulate_3_buttons:
            blf.position(font_id, x + gap , y + height - font_h - gap - (150 * self.ui_scale), 0)
            blf.size(font_id, font_h) 
            blf.color(font_id, 0.65, 0.65, 0.65, 1)
            blf.draw(font_id, "Fine-tune Drag:")
            
            blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (150 * self.ui_scale), 0)
            blf.size(font_id, font_h) 
            blf.color(font_id, 0.8, 0.8, 0.8, 1)
            blf.draw(font_id, "Hold Shift")
        
        blf.position(font_id, x + gap , y + height - font_h - gap - (170 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.65, 0.65, 0.65, 1)
        blf.draw(font_id, "Exit Tool:")
        
        blf.position(font_id, x + gap + (200 * self.ui_scale), y + height - font_h - gap - (170 * self.ui_scale), 0)
        blf.size(font_id, font_h) 
        blf.color(font_id, 0.8, 0.8, 0.8, 1)
        blf.draw(font_id, "ESC")
        

def draw_callback_3d(self, context):
    
    font_id = 0  # XXX, need to find out how best to get this.    
    scene = bpy.context.scene
    car = scene.lc.find_selected()
    car_props = car.properties
    

    # Draw Keyframe Tower
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.5)
    batch = batch_for_shader(shader, 'LINES', {"pos": self.keyframe_coords_to_draw})
    shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
    batch.draw(shader)
    
    
    # Draw Driving Path Interpolation
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": self.interpolated_points})
    shader.uniform_float("color", (0.0, 0.0, 0.0, 1.0))
    batch.draw(shader)
    
    
    # Only draw if there are any points
    if len(self.interpolated_speeds) > 0 and car_props.graph_enable:

        # Draw Driving Path Speed Points
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(1.0)
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": self.interpolated_speeds})
        shader.uniform_float("color", car_props.graph_color)
        batch.draw(shader)
        
        # Draw Driving Path Lines between Interp and Speed points
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.line_width_set(1.0)
        batch = batch_for_shader(shader, 'LINES', {"pos": self.interpolated_p_to_s})
        shader.uniform_float("color", car_props.graph_color)
        batch.draw(shader)
     

    # restore opengl defaults
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


class Drag_Knob:
    
    def __init__(self, x, y, width, height):
        self.id = id
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.drag_offset_x = 0
        self.drag_offset_y = 0
        self.is_drag = False
        self.was_dragged = False
        self.flip_dir = 0
        self.view_to_key_dist = 0
        self.color = (0.75, 0.75, 0.75, 1)
        self.org_key_frame = []
        self.org_key_val = []
        self.org_handle_right = []
        self.org_handle_left = []
        self.org_action = None
        self.drag_start_pos_x = 0
        self.drag_start_pos_y = 0
        self.fwd_dir = Vector((0,0,0))
        self.last_handle_right_delta = Vector((0,0,0))
        self.last_handle_left_delta = Vector((0,0,0))
        self.autosmooth = True
        
    def set_id(self, id):
        self.id = id
        
    def set_fwd_dir(self, fwd_dir):
        self.fwd_dir = fwd_dir
        
    def set_color(self, color):
        self.color = color
        
    def get_slope(self, p1, p2):
        
        try: slope = (p2[1]-p1[1]) / (p2[0]-p1[0])
        except: slope = 0
                
        return slope
        
    def get_speed(self, slope):  #in m/s
        
        rad_per_frame = slope
        rad_per_sec = (rad_per_frame*25)
        m_per_sec = rad_per_sec*10
        
        return m_per_sec
        
    def draw(self):
        self.shader.bind()
        self.shader.uniform_float("color", self.color)        
        self.batch_knob.draw(self.shader)
        
    def update(self, x, y, lock_axis, move_slow):
        # Move keyframes along spline and adjust speed
        scene = bpy.context.scene
        
        self.x = x
        self.y = y

        # reinterp to 0.1 and 1
        move_mul = (1-move_slow)*0.9 + 0.1
        
        car = scene.lc.find_selected()
        rig_object = car.rig_object
        fcurve = get_speed_rotate_fcurve(rig_object)
        keyframe_points = fcurve.keyframe_points
        
                
        ### calc for active key only
        if self.flip_dir == 0:
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':     
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            view_dir = region_2d_to_vector_3d(
                                region,
                                region.data,
                                (region.width / 2.0, region.height / 2.0)
                            )
                                            
            view_left = Vector((    view_dir[0], view_dir[1], 0    ))
            eul = Euler((0, 0, -math.pi/2), 'XYZ')
            view_left.rotate(eul)
            self.fwd_dir = Vector((self.fwd_dir[0],self.fwd_dir[1],0))
            dot = view_left.dot(self.fwd_dir)
            
            if dot > 0:
                self.flip_dir = 1
            else:
                self.flip_dir = -1
        
                    
        
        # Apply the transform
        i = 0
        for key in keyframe_points:
            if key.select_control_point:
                list_len = len(keyframe_points)-1

                # If only 2 keyframes, just offset time instead if changing last point 
                if len(keyframe_points) < 3 and i == list_len and lock_axis == 'Y':
                    self.mouse_move_push_key(x, y, move_slow, True)
                
                if self.view_to_key_dist == 0:
                    try: 
                        for area in bpy.context.screen.areas:
                            if area.type == 'VIEW_3D':     
                                r3d = area.spaces[0].region_3d
                                
                        key_world_pos = bpy.context.scene.objects["LC_Ruler_" + str(i)].matrix_world.to_translation()
                        self.view_to_key_dist = (r3d.view_location-key_world_pos).length
                    except:
                        print("Failed to find Ruler for keyframe. Will not scale mouse input based on distance to key. Not Critical.")
                        self.view_to_key_dist = 1
                
                                
                if lock_axis == 'None':
                    y_sc = 1
                    x_sc = 1 *self.view_to_key_dist/20
                elif lock_axis == 'Y':
                    y_sc = 1
                    x_sc = 0
                elif lock_axis == 'X':
                    y_sc = 0
                    x_sc = 1 *self.view_to_key_dist/20
                

                handle_left_len = (key.co - key.handle_left).length
                handle_right_len = (key.co - key.handle_right).length

                handle_left_delta = key.handle_left - key.co
                handle_right_delta = key.handle_right - key.co

                

                # offset for start and end point
                if i == 0 or i == list_len:
                    
                    key.co[1] =                 (self.x  - self.drag_start_pos_x)/100*self.flip_dir *x_sc   *move_mul    + self.org_key_val[i]

                    # Block first frame from moving negative from start of path
                    if key.co[1] <= 0:
                        key.co[1] = 0
                    
                    # Block last frame from moving negative from end of path
                    driving_path = car.driving_path
                    path_len = driving_path.data.path_duration
                    max_val = path_len/10
                    
                    if key.co[1] >= max_val:
                        key.co[1] = max_val

                    
                    # Restrict value for START and END points
                    threshold = 0.33

                    # first point
                    if key == keyframe_points[0]:
                        if key.co[1] >= keyframe_points[i+1].co[1] - threshold:
                            key.co[1] = keyframe_points[i+1].co[1]
                    
                    # last point
                    if key == keyframe_points[list_len]:
                        if key.co[1] <= keyframe_points[i-1].co[1] + threshold:
                            key.co[1] = keyframe_points[i-1].co[1]
                    
                    # Adjusting handles
                    key.handle_left = key.co  +  handle_left_delta
                    key.handle_right = key.co  +  handle_right_delta


                # offset for intermediate points
                elif x_sc > 0 and y_sc == 0:
                    
                    # Set new frame 
                    new_frame =   self.org_key_frame[i]      +    (self.x  - self.drag_start_pos_x) / 40*self.flip_dir *x_sc   *move_mul

                    # Retrieve the specific F-Curve
                    data_path = 'pose.bones["bone_Speed_Rotate"].rotation_euler'
                    array_index = 2
                    org_action_fcurve = self.org_action.fcurves.find(data_path, index=array_index)

                    new_co = org_action_fcurve.evaluate(new_frame)
                    
                    new_frame = new_frame + (self.y  - self.drag_start_pos_y) / 10 *y_sc   *move_mul
                    
                    dir_key_left = key.co - keyframe_points[i-1].co
                    dir_key_left.normalize()
                    
                    dir_key_right = key.co - keyframe_points[i+1].co
                    dir_key_right.normalize()
                    
                    
                    # Apply the transforms
                    key.co = Vector((new_frame, new_co))

                    # Restrict frame_pos for intermediate points
                    threshold = 4

                    if key.co[0] <= keyframe_points[i-1].co[0] + threshold:
                        key.co = keyframe_points[i-1].co
                        
                    if key.co[0] >= keyframe_points[i+1].co[0] - threshold:
                        key.co = keyframe_points[i+1].co
                    

                    # Adjusting handles
                    key.handle_left = key.co  +  handle_left_delta
                    key.handle_right = key.co  +  handle_right_delta

                    self.last_handle_left_delta = handle_left_delta
                    self.last_handle_right_delta = handle_right_delta
                
                
                # Adjust speed   
                if x_sc == 0 and y_sc == 1:
                    key.handle_left[1] =        self.org_handle_left[i][1]                        -        ((self.y  - self.drag_start_pos_y)*handle_left_len)/2000 *y_sc   *move_mul
                    key.handle_right[1] =       self.org_handle_right[i][1]                       +        ((self.y  - self.drag_start_pos_y)*handle_right_len)/2000 *y_sc   *move_mul
                    
                    if not i == 0:
                        key.co[0] =                 -(self.y  - self.drag_start_pos_y)/15   *move_mul    + self.org_key_frame[i]
                        key.handle_left[0] =        -(self.y  - self.drag_start_pos_y)/15   *move_mul    + self.org_handle_left[i][0]
                        key.handle_right[0] =       -(self.y  - self.drag_start_pos_y)/15   *move_mul    + self.org_handle_right[i][0]
                
                
                # Do not allow negative speeds
                if key.handle_right[1] < key.handle_left[1]:
                    key.handle_right[1] = key.co[1]
                    key.handle_left[1] = key.co[1]
            
            i += 1            
    
    
    def update_push_key(self, x, y, move_slow, invert):
        # (Offset time!)        
        scene = bpy.context.scene        
        
        self.x = x
        self.y = y

        invert_mul = 1
        if invert:
            invert_mul = -5

        # reinterp to 0.1 and 1
        move_mul = ((1-move_slow)*0.9 + 0.1) * invert_mul

        car = scene.lc.find_selected()
        rig_object = car.rig_object
        keyframe_points = get_speed_rotate_keyframes(rig_object)
        
        # Apply the transform - Multi select    
        i = 0
        for key in keyframe_points:
            if key.select_control_point:
                
                id = 0
                
                post_keys = []           
                
                for key_alter in keyframe_points:
                    
                    if id >= i: # Only keys after selected key
                            
                        key_alter.co[0] =                 (self.y  - self.drag_start_pos_y)/10   *move_mul    + self.org_key_frame[id]
                        key_alter.handle_left[0] =        (self.y  - self.drag_start_pos_y)/10   *move_mul    + self.org_handle_left[id][0]
                        key_alter.handle_right[0] =       (self.y  - self.drag_start_pos_y)/10   *move_mul    + self.org_handle_right[id][0]
                        
                        post_keys.append(key_alter)
                            
                    id += 1
                    
                    
                    
                # Logic restrictions - cannot cross other keys or 0 in timeline
                
                if i == 0:     # Selected point was the first point -> limit at frame 0 in timeline
                    if key.co[0] < 0:
                        delta = -key.co[0]
                        
                        for key_alter in post_keys:
                        
                            key_alter.co[0] += delta
                            key_alter.handle_left[0] += delta
                            key_alter.handle_right[0] += delta
                    
                    
                elif key.co[0] < keyframe_points[i-1].co[0]:     # Hitting the point before itself -> Limit
                    delta = key.co[0] - keyframe_points[i-1].co[0]
                    
                    for key_alter in post_keys:
                        
                        key_alter.co[0] -= delta
                        key_alter.handle_left[0] -= delta
                        key_alter.handle_right[0] -= delta
                    
                        
                break  # Makes sure it only happens for the first keyframe point which is selected - all following points will be pushed too!
            i += 1
            
            
            
        
            
    
    def update_view(self, x, y, type):
                
        if type == 'START':
            modifier = 1
        elif type == 'END':
            modifier = 2
        else:
            modifier = 0
        
        indices = ((0, 1, 2), (0, 2, 3))
        
        self.x = x
        self.y = y
        
        # bottom left, top left, top right, bottom right
        if modifier == 0:
            vertices = (
                        (self.x - self.width/2,                    self.y),
                        (self.x,                                   self.y + self.height/2),
                        (self.x + self.width/2,                    self.y),
                        (self.x,                                   self.y - self.height/2))
        
        else:
            width = self.width/1.33
            height = self.height/1.33
            vertices = (
                        (self.x - width/2,                    self.y - height/2),
                        (self.x - width/2,                    self.y + height/2),
                        (self.x + width/2,                    self.y + height/2),
                        (self.x + width/2,                    self.y - height/2))
        
                    
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self.batch_knob = batch_for_shader(self.shader, 'TRIS', {"pos" : vertices}, indices=indices)
        
        
    def handle_event(self, event):
        emulate_3_buttons = bpy.context.preferences.inputs.use_mouse_emulate_3_button

        if not emulate_3_buttons:
            fine_tune_drag = event.shift
        else:
            fine_tune_drag = 0

        if (event.type == 'LEFTMOUSE'):
            
            if (event.ctrl and event.alt and not event.shift) or (emulate_3_buttons and (event.ctrl and event.shift)):
                if (event.value == 'RELEASE'):
                    return self.key_create(event.mouse_region_x, event.mouse_region_y, False)
            
            elif (event.value == 'PRESS'):
                return self.mouse_down(event.mouse_region_x, event.mouse_region_y, fine_tune_drag)            
            
            elif (event.value == 'RELEASE'):
                return self.mouse_up(event.mouse_region_x, event.mouse_region_y, fine_tune_drag)
            
                
        elif (event.type == 'RIGHTMOUSE'):
            if (event.value == 'RELEASE'):
                return self.key_delete(event.mouse_region_x, event.mouse_region_y)
            
        
        elif (event.type == 'MOUSEMOVE') and self.is_drag:
            if (not event.ctrl and event.alt) or (emulate_3_buttons and (not event.ctrl and event.shift)):
                self.mouse_move_push_key(event.mouse_region_x, event.mouse_region_y, fine_tune_drag, False)
                return True
            
            elif (event.ctrl and not event.alt):
                self.mouse_move(event.mouse_region_x, event.mouse_region_y, 'Y', fine_tune_drag)
                return True
            
            else:
                self.mouse_move(event.mouse_region_x, event.mouse_region_y, 'X', fine_tune_drag)
                return True
                
        return False
    
    
    def is_in_rect(self, x, y):
        if (
            ((self.x - self.width) <= x <= (self.x + self.width)) and
            ((self.y - self.height) <= y <= (self.y + self.height))
            ):
            return True
        
        return False
    
    
    def key_create(self, x, y, bypass_mouse_pos):
        scene = bpy.context.scene
        if self.is_in_rect(x,y) or bypass_mouse_pos:
            
            if self.id < 1:
                return False
            
            car = scene.lc.find_selected()
            rig_object = car.rig_object
            fcurve = get_speed_rotate_fcurve(rig_object)
            keyframe = fcurve.keyframe_points[self.id]
            frame = keyframe.co[0]
            previous_key_frame = fcurve.keyframe_points[self.id-1].co[0]
            previous_key = fcurve.keyframe_points[self.id-1]
            
            new_key_frame = (frame - (frame-previous_key_frame)/2)
            new_key_val = (keyframe.co[1]   -   (keyframe.co[1]-previous_key.co[1])/2)
            rig_object.pose.bones["bone_Speed_Rotate"].rotation_euler[2] = new_key_val
            
            rig_object.keyframe_insert(data_path=fcurve.data_path,  index=2, frame = new_key_frame)
            
            new_keyframe = fcurve.keyframe_points[self.id]
            
            new_keyframe.handle_left_type = 'AUTO_CLAMPED'
            new_keyframe.handle_right_type = 'AUTO_CLAMPED'
            
            
            keyframes = get_speed_rotate_keyframes(rig_object)
            
            for key in keyframes:
                key.select_control_point = False
                key.select_right_handle = False
                key.select_left_handle = False
            
            self.key_smooth(0,0)

            if len(keyframes) == 21:
                message = f"Performance might vary for animations with 20+ Speed Keyframes. Consider turning 'Visibility' of 'Graph' OFF or Disableing 'Auto' features in the Settings to improve performance"
                log_info(message, "Speed Segments")
                show_message_box(message, "Performance Warning", "INFO")
    
    
    
    def key_delete(self, x, y):
        scene = bpy.context.scene
        if self.is_in_rect(x,y):
            
            car = scene.lc.find_selected()
            rig_object = car.rig_object
            fcurve = get_speed_rotate_fcurve(rig_object)
            frame = fcurve.keyframe_points[self.id].co[0]
            
            if len(fcurve.keyframe_points) > 2:
                rig_object.keyframe_delete(data_path=fcurve.data_path, frame=frame)
                                
                #bpy.ops.ed.undo_push()
                self.key_smooth(0,0)
                
            else:
                print("Keep minimum 2 keyframes!")
            
        
    def key_smooth(self, x, y):
        scene = bpy.context.scene
        car = scene.lc.find_selected()
        rig_object = car.rig_object
        car_props = car.properties
        fcurve = get_speed_rotate_fcurve(rig_object)
        keyframe_points = get_speed_rotate_keyframes(rig_object)
        list_len = len(keyframe_points)

        if car_props.interpolation_mode == 'auto' or car_props.interpolation_mode == 'use_offset_time':
            
            if self.is_in_rect(x,y) or self.autosmooth:
                
                if list_len < 3:
                    for key in keyframe_points:
                        key.handle_left_type = 'VECTOR'
                        key.handle_right_type = 'VECTOR'
                    
                    fcurve.auto_smoothing = 'CONT_ACCEL'
                    
                elif self.autosmooth:

                    # Remove dublicate keyframes
                    i = 0
                    keys_to_remove = []

                    for key in keyframe_points:
                        # Avoid if it's the last key
                        if key != keyframe_points[list_len-1]:
                            if key.co == keyframe_points[i+1].co:
                                keys_to_remove.append(key)
                    
                        i += 1

                    for remove_key in keys_to_remove:
                        rig_object.keyframe_delete(data_path=fcurve.data_path, frame=remove_key.co[0])
                    
                    list_len = len(keyframe_points)


                    # collect points for smoothing
                    key_list = []
                    i = 0
                    for key in keyframe_points:
                        
                        if i > 0:  # add post key if not id "last +1" or id "-1"
                            key_list.append(key)
                        
                        i += 1
                                  
                    
                    i = 0
                    for key in keyframe_points:
                        if key in key_list:
                            
                            # Force handle type
                            key.handle_left_type = 'ALIGNED'
                            key.handle_right_type = 'ALIGNED'
                            
                            
                            # Adjust time offset automatically
                            if car_props.interpolation_mode == 'auto':
                                if key != keyframe_points[0]:
                                    
                                    frame02 = key.co[0]
                                    dist02 = key.co[1]
                                    speed_key02 = self.get_speed(self.get_slope(    key.co, key.handle_right    ))
                                    
                                    frame01 = keyframe_points[i-1].co[0]
                                    dist01 = keyframe_points[i-1].co[1]
                                    speed_key01 = self.get_speed(self.get_slope(    keyframe_points[i-1].co, keyframe_points[i-1].handle_right    ))
                                
                                    #fps = bpy.context.scene.render.fps
                                    fps = 24  #locked fps as LC was developed for this framerate
                                    d_dist = (dist02-dist01)*10
                                    
                                    

                                    # Auto in-between time
                                    avg_speed = (speed_key02 + speed_key01)/2
                                    if avg_speed < 0.1:
                                        avg_speed = 0.1


                                    d_time = d_dist/avg_speed
                                    d_frames = d_time*fps

                                    frames_to_offset = d_frames - (frame02 - frame01)

                                    id = 0
                                    for key_post in keyframe_points:
                                        if id >= i:
                                            key_post.co[0] += frames_to_offset
                                            key_post.handle_right[0] += frames_to_offset
                                            key_post.handle_left[0] += frames_to_offset

                                        id += 1
                                           
                        i += 1
                                        
                    
                    # Calculate Tangents (1/3rd of the distance to post and pre and more cool stuffs)
                    i = 0
                    
                    for key in keyframe_points:
                        if key in key_list:

                            
                                                                                     
                            # Avoid if it's the last key
                            if key != keyframe_points[list_len-1]:
                                dir_handle_right = key.handle_right - key.co
                                dir_handle_right.normalize()
                                
                                dist_post = (key.co - keyframe_points[i+1].co).length
                                
                                len_right = dist_post/3
                                key.handle_right = key.co + dir_handle_right*len_right
                                
                                # Restrict handle Y loc compared to pre and post key (Auto Clamped behaviour)
                                for n in range(0, 100):
                                    if key.handle_right[1] < keyframe_points[i+1].co[1]:
                                        break
                                    
                                    len_right = len_right*0.95
                                    key.handle_right = key.co + dir_handle_right*len_right
                                
                                
                            # Avoid if it's the first key
                            if key != keyframe_points[0]:
                                dir_handle_left = key.handle_left - key.co
                                dir_handle_left.normalize()
                                
                                dist_pre = (key.co - keyframe_points[i-1].co).length
                                
                                len_left = dist_pre/3
                                key.handle_left = key.co + dir_handle_left*len_left
                                
                                # Restrict handle Y loc compared to pre and post key (Auto Clamped behaviour)
                                for n in range(0, 100):
                                    if key.handle_left[1] > keyframe_points[i-1].co[1]:
                                        break
                                    
                                    len_left = len_left*0.95
                                    key.handle_left = key.co + dir_handle_left*len_left
                                    
                        i += 1
                    

        # Set scene frame range
        if car_props.auto_fit_frame_range:
            scene.frame_start = int(keyframe_points[0].co[0])
            scene.frame_end = int(keyframe_points[list_len-1].co[0]+25)

        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = bpy.context.preferences.addons[addon_root].preferences
        max_len = addon_preferences.max_dur_speed_segments
        
        if (scene.frame_end-scene.frame_start) > max_len:
            scene.frame_end = max_len + scene.frame_start

        #rig_object.animation_data.action.fcurves[0].auto_smoothing = 'CONT_ACCEL' changes speed...
        bpy.ops.ed.undo_push()
                
    
    def deselect_all(self):
        scene = bpy.context.scene

        car = scene.lc.find_selected()
        rig_object = car.rig_object
        keyframes = get_speed_rotate_keyframes(rig_object)
        
        for key in keyframes:
            key.select_control_point = False
            key.select_right_handle = False
            key.select_left_handle = False
            
        #bpy.ops.ed.undo_push()
    
    
    def mouse_move(self, x, y, lock_axis, move_slow):
        self.update(x, y, lock_axis, move_slow)
        self.was_dragged = True
    
    
    def mouse_move_push_key(self, x, y, move_slow, invert):
        self.update_push_key(x, y, move_slow, invert)
        self.was_dragged = True           
            
    
    def mouse_down(self, x, y, extend):
        if self.is_in_rect(x,y):
            scene = bpy.context.scene
            car = scene.lc.find_selected()
            rig_object = car.rig_object
            bpy.context.view_layer.objects.active = rig_object
            rig_object.select_set(True)
            rig_object.data.bones["bone_Speed_Rotate"].select = True
            keyframes = get_speed_rotate_keyframes(rig_object)

            for key in keyframes:
                key.select_control_point = False
                key.select_right_handle = False
                key.select_left_handle = False
            

            keyframe = keyframes[self.id] 

            keyframe.select_control_point = True 
            keyframe.select_right_handle = True 
            keyframe.select_left_handle = True 
               
            self.is_drag = True
            self.drag_start_pos_x = x
            self.drag_start_pos_y = y
            
            i = 0
            for key in keyframes:
                self.org_key_frame.append(keyframes[i].co[0])
                self.org_key_val.append(keyframes[i].co[1])
                self.org_handle_right.append(keyframes[i].handle_right.copy())
                self.org_handle_left.append(keyframes[i].handle_left.copy())
                if key.interpolation != 'BEZIER':
                    key.interpolation = 'BEZIER'
                    
                    
                i += 1
            
            action_copy = rig_object.animation_data.action.copy()
            self.org_action = action_copy
             
            return True
        
        return False

            
    def mouse_up(self, x, y, extend):
        
        if self.was_dragged or self.is_drag:
            scene = bpy.context.scene
            
            car = scene.lc.find_selected()
            rig_object = car.rig_object
            keyframes = get_speed_rotate_keyframes(rig_object)
            
            # check if keyframe still exists before doing anything
            if self.id < len(keyframes):
                keyframe = keyframes[self.id]
            
                if self.is_in_rect(x,y):
                    if not extend and not self.was_dragged:
                        #if shift is NOT pressed and you let go after clicking on an already selected point:
                        if keyframe.select_control_point:
                            for key in keyframes:
                                if key == keyframe:
                                    key.select_control_point = True
                                    key.select_right_handle = True
                                    key.select_left_handle = True
                                else:
                                    key.select_control_point = False
                                    key.select_right_handle = False
                                    key.select_left_handle = False
                
                
                # auto smooth on confirm
                if self.autosmooth:
                    self.key_smooth(0,0)
                
                self.is_drag = False    
                self.was_dragged = False
                self.flip_dir = 0
                self.view_to_key_dist = 0
                self.drag_offset_x = 0
                self.drag_offset_y = 0
                self.org_key_frame.clear()
                self.org_key_val.clear()
                self.org_handle_right.clear()
                self.org_handle_left.clear()
                self.org_action = None
                self.drag_start_pos_x = 0
                self.drag_start_pos_y = 0
                
                if not self.autosmooth:
                    bpy.ops.ed.undo_push()
        
    def update_region(self, x, y, type):
        self.update_view(x -20, y, type)
        


class OBJECT_OT_speed_segment_tool(bpy.types.Operator):
    bl_idname = "view3d.speed_segment_operator"
    bl_label = "Speed Segment Tool"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "For visual people: Use the Speed Segment Tool to alter the vehicle speed over time!"
    
    def kill_segments(self):
        scene = bpy.context.scene
        bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle_3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle_2d, 'WINDOW')
    
        self.draw_handle_2d = None
        self.draw_handle_3d = None
        
        for obj in bpy.data.objects:
            if "LC_Ruler" in obj.name:
                bpy.data.objects.remove(obj, do_unlink=True)
        
        
        scene.settings.speed_segments_running = False
        scene.settings.speed_segments_kill = False

        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
        
        return None
    
    def get_slope(self, p1, p2):
            
            try: slope = (p2[1]-p1[1]) / (p2[0]-p1[0])
            except: slope = 0
            
            return slope
        
    def get_speed(self, slope):
        fps = bpy.context.scene.render.fps

        rad_per_frame = slope
        rad_per_sec = (rad_per_frame*fps)
        m_per_sec = rad_per_sec*10
        kmh = m_per_sec*3.6
        
        return kmh
    
    
    def cubic_bezier_points_extended(self, control_points, t_values):
        # Define the characteristic matrix for cubic Bézier curve
        M = np.array([
            [1, 0, 0, 0],
            [-3, 3, 0, 0],
            [3, -6, 3, 0],
            [-1, 3, -3, 1]
        ])
        
        # Calculate the number of segments based on the control points
        n = (len(control_points) - 1) // 3
        
        # Initialize the list to hold the computed points
        bezier_points = []
        
        for t in t_values:
            # Determine which segment this t value falls into
            segment_index = int(t) 
            if segment_index >= n:
                segment_index = n - 1  # Clamp to the last segment for t values out of range
            
            # Normalize t to the local coordinate system of the current segment [0, 1]
            local_t = t - segment_index
            
            # Select the appropriate control points for the current segment
            cp_index = segment_index * 3
            segment_control_points = control_points[cp_index:cp_index+4]
            
            # Compute the T vector for the cubic Bézier curve
            T = np.array([1, local_t, local_t**2, local_t**3])
            
            # Compute the point on the curve for the current t value
            point = T @ M @ segment_control_points  # Matrix multiplication to get the point
            bezier_points.append(point)
        
        return np.array(bezier_points)

    def numeric_distance_integration(self, control_points, resolution=1024):
        n_segments = (len(control_points) - 1) // 3
        t_values = np.linspace(0, n_segments, resolution+1)
        bezier_points = self.cubic_bezier_points_extended(control_points, t_values)
        distance = np.sqrt(np.sum(np.power(bezier_points[:-1,:] - bezier_points[1:,:],2),axis=-1))
        return distance

    def cubic_bezier_points_equdistant(self, control_points, count=20, resolution=1024):
        n_segments = (len(control_points) - 1) // 3
        x = np.linspace(0, n_segments, resolution)
        y = self.numeric_distance_integration(control_points, resolution=resolution)
        length = np.sum(y)
        t_values_equidistant = np.interp(np.linspace(0, 1, count),y.cumsum()/length,x,)
        return self.cubic_bezier_points_extended(control_points, t_values_equidistant)
    
    def resample_curve(self, obj, count=128):
        if obj.type != 'CURVE':
            raise ValueError("Object is not a curve in custom function `resample_curve()`.")

        spline = obj.data.splines[0]
        control_points = []
        for point_index in range(len(spline.bezier_points)-1):
            a = spline.bezier_points[point_index]
            b = spline.bezier_points[point_index+1]
            if point_index == 0:
                control_points.append(a.co.xyz)
            control_points.extend([
                a.handle_right.xyz,
                b.handle_left.xyz,
                b.co.xyz,
            ])
        control_points = [obj.matrix_world @ p for p in control_points]
        # Convert control points to a numpy array
        control_points = np.array(control_points)
        equidistant_points_np = self.cubic_bezier_points_equdistant(control_points, count=count)
        equidistant_points = [Vector(p) for p in equidistant_points_np]
        return equidistant_points


    def modal(self, context, event):
        self.bypass_draw = False   
        
    
        # Mute all on playback
        if bpy.context.screen.is_animation_playing:
            if not self.bypass_draw:
                context.area.tag_redraw()
                
            self.bypass_draw = True
            return {'PASS_THROUGH'}
            
            
        if context.area:
            context.area.tag_redraw()               

        scene = bpy.context.scene
        car = scene.lc.find_selected()
        rig_object = car.rig_object
        driving_path = car.driving_path
        car_props = car.properties
        settings = car.settings
        
        
        ### Performant Speed Curve Function - Can be disabled in UI ###
        if car_props.graph_enable:
            fcurve = get_speed_rotate_fcurve(rig_object)
            path_len = driving_path.data.path_duration

            step_size = 1
            frame_start = scene.frame_start
            frame_end = scene.frame_end
            step_range = range(frame_start, frame_end, step_size)
            new_calc_points = []
            speed_points = []

            resampled_points = self.resample_curve(driving_path, car_props.speed_graph_resolution)
            
            for interp_step in step_range:
                
                scaled_step = interp_step*step_size
                
                # Calculate coordinates for frame by converting to a percent.
                fcurve_val = fcurve.evaluate(scaled_step)
                eval = (fcurve_val*10 / path_len)
                index = int(eval*len(resampled_points))
                
                if len(speed_points)-1 < index and index < len(resampled_points):  #if point does not exist yet and is in sampled points
                    coord = resampled_points[index]
                    
                    new_calc_points.append(coord)
                    
                    p1 = Vector((   scaled_step,   fcurve_val   ))
                    p2 = Vector((   scaled_step+0.5,   fcurve.evaluate(scaled_step+0.5)   ))
                    slope = self.get_slope(p1, p2)*50 * car_props.graph_scale
                    
                    speed_points.append(slope)
                        
                        
            offset_points = []
            offset_speed_points = []
            offset_p_to_s = []
                    
            n = 0
            for point in new_calc_points:
                
                new_mat = Matrix(((1, 0, 0, point[0]),
                                (0, 1, 0, point[1]), 
                                (0, 0, 1, point[2]), 
                                (0, 0, 0, 1)))
                
                
                offset_mat = new_mat
                world_loc = offset_mat.to_translation()
                offset_points.append( world_loc + Vector((0, 0, -0.01)) )
                
                            
                if 0 <= n < len(speed_points):
                    offset_speed_points.append(   world_loc + Vector((0, 0, speed_points[n]))   )
                    
                    offset_p_to_s.append( world_loc + Vector((0, 0, -0.01)) )
                    offset_p_to_s.append(   world_loc + Vector((0, 0, speed_points[n]))   )
                
                n += 1
                
            self.interpolated_points = offset_points
            self.interpolated_speeds = offset_speed_points
            self.interpolated_p_to_s = offset_p_to_s
                    
        
        # Main Data function (Will execute all the time)
        try:
            if True == True:
                
                key_points = get_speed_rotate_keyframes(rig_object)
                driving_path = car.driving_path
                path_len = driving_path.data.path_duration
                
                
                coords = []
                coords_to_draw = []
                speeds = []
                                
                i = 0
                for key in key_points:
                    
                    ruler_name = "LC_Ruler_" + str(i)
                    
                    if not ruler_name in bpy.context.scene.objects:
                        ruler = bpy.data.objects.new(ruler_name, None)
                        
                        if bpy.data.collections.get('Internal'):
                            col = bpy.data.collections['Internal']
                        else:
                            col = bpy.data.collections.new('Internal')
                            scene.collection.children.link(col)
                                            
                        col.objects.link( ruler )

                        constraint = ruler.constraints.new(type='FOLLOW_PATH')
                        constraint.target = driving_path
                        constraint.use_fixed_location = True
                        ruler.empty_display_size = 0.001
                        
                    else:
                        ruler = bpy.context.scene.objects[ruler_name]
                    
                    ruler_helper_name = "LC_Ruler_Helper_" + str(i)
                    
                    if not ruler_helper_name in bpy.context.scene.objects:
                        ruler_helper = bpy.data.objects.new(ruler_helper_name, None)
                        
                        if bpy.data.collections.get('Internal'):
                            col = bpy.data.collections['Internal']
                        else:
                            col = bpy.data.collections.new('Internal')
                            scene.collection.children.link(col)
                                            
                        col.objects.link( ruler_helper )

                        constraint = ruler_helper.constraints.new(type='FOLLOW_PATH')
                        constraint.target = driving_path
                        constraint.use_fixed_location = True
                        ruler_helper.empty_display_size = 0.001
                        
                    else:
                        ruler_helper = bpy.context.scene.objects[ruler_helper_name]                        
                    
                    eval = ((key.co[1]*10) / path_len)
                    
                    ruler.constraints[0].offset_factor = eval
                    ruler_helper.constraints[0].offset_factor = eval + 0.01   #a small delta to detect fwd dir                
                    
                    vec = ruler.matrix_world.to_translation()
                    vec_lift = vec + Vector((0,0,5))
                    slope = self.get_slope(key.co, key.handle_right)
                    
                    speed = self.get_speed(slope)
                    
                    coords.append(vec)
                    coords_to_draw.append(vec)
                    coords_to_draw.append(vec_lift)
                    speeds.append(speed)
                    
                    
                    # knob stuff!
                    bpy.context.view_layer.update()
                    region = context.region
                    rv3d = context.space_data.region_3d
                    coord = Vector((vec_lift[0], vec_lift[1], vec_lift[2]))
                    
                    try: x, y = location_3d_to_region_2d(region, rv3d, coord)
                    except: x, y = 0, 0
                                    
                    # Create knobs
                    if len(self.knobs) <= i:
                        self.knobs.append(Drag_Knob(25, 25, 24, 24))
                        
                    self.knobs[i].set_id(i)
                    self.knobs[i].set_fwd_dir(ruler_helper.matrix_world.to_translation() - ruler.matrix_world.to_translation())
                    
                    i += 1
                
                    
                # Delete any extra knobs
                while len(self.knobs) > i:
                    del self.knobs[i]
                
                                
                self.keyframe_coords = coords
                self.keyframe_coords_to_draw = coords_to_draw
                self.keyframe_speeds = speeds
                
        except: 
            print("Could not update main function (data) for Speed Segments. Will try to ignore")
            
        
        # Update 3D Space to 2D UI Locations
        try:
            region_x = []
            region_y = []
            i = 0
            for keyframe_coord in self.keyframe_coords:
                region = context.region
                rv3d = context.space_data.region_3d
                coord = Vector((keyframe_coord[0], keyframe_coord[1], keyframe_coord[2]+5.5))
                
                try: x, y = location_3d_to_region_2d(region, rv3d, coord)
                except: x, y = 0, 0
                
                region_x.append(x)
                region_y.append(y)
                
                                
                if len(self.knobs) > i:     
                    if i == 0:
                        type = 'START'
                    elif i == len(self.knobs)-1:
                        type = 'END'
                    else:
                        type = None
                        
                    self.knobs[i].update_region(x+20, y, type)
                    
                    
                # update colors
                keys = get_speed_rotate_keyframes(rig_object)
                try:
                    if keys[i].select_control_point:
                        self.knobs[i].set_color((1.0, 0.75, 0.2, 1.0))
                    else:
                        self.knobs[i].set_color((0.75, 0.75, 0.75, 1.0))
                except:
                    pass
                    # If visual keyframe is deleted by user, this might fail
                
                i += 1
            
            self.keyframe_region_x = region_x
            self.keyframe_region_y = region_y
            
            self.bypass_draw = False
            if (event.type == 'MIDDLEMOUSE'):
                if event.value == 'PRESS':
                    self.bypass_draw = True
                    
                    if context.area:
                        context.area.tag_redraw()
                
                else:
                    context.area.tag_redraw()
                            
            if event.type in {'ESC'} or scene.settings.speed_segments_kill:
                self.kill_segments()

                return {'CANCELLED'}
                
            
            self.user_interaction = False
            # User Iteraction  (will overlay on top of other Blender things)
            if context.area.type == 'VIEW_3D':
                for knob in self.knobs:
                    if knob.handle_event(event):
                        knob.set_color((1.0/2, 0.75/2, 0.2/2, 1.0))
                        self.needs_full_redraw = True
                        self.user_interaction = True                   
                            
                        return {'RUNNING_MODAL'}           
            
            context.area.tag_redraw()   
            return {'PASS_THROUGH'}
        
        except:
            print("Could not update 2D locs, will stop")
            self.report({'INFO'}, "Speed Segments Disabled")
            self.kill_segments()
            return {'CANCELLED'}
    
    
    def invoke(self, context, event):
        cls = self.__class__
        scene = bpy.context.scene
        
        # check if rig armature can be selected
        car = scene.lc.find_selected()
        rig_object = car.rig_object

        if not validate_lc_object(rig_object):
            return {"CANCELLED"}
        
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        bpy.context.view_layer.objects.active = rig_object
        rig_object.select_set(True)
        for bone in rig_object.data.bones:
            bone.select = False
        rig_object.data.bones["bone_Speed_Rotate"].select = True
        
        spline = car.driving_path.data.splines[0]
        if spline.type != 'BEZIER':
            message = f"The Speed Segment Tool does not work with curves of the type '{spline.type}', please change it into a Bezier Curve"
            log_error(message, "Speed Segments")
            show_message_box(message, "Could not enable Speed Segments", "ERROR")
            return {'CANCELLED'}
        
        if spline.use_cyclic_u:
            spline.use_cyclic_u = False
            message = f"Disabled 'Cyclic' for the Driving Path to support the Speed Segment Tool."
            log_info(message, "Speed Segments")
            show_message_box(message, "Driving Path Altered", "INFO")

        rig_object = car.rig_object

        keyframes = get_speed_rotate_keyframes(rig_object)
        if keyframes == None:
            message = f"Could not find Animation Data for the 'Speed_Rotate' handle. Please add 2 keyframes to it or use a 'User Path' and 'Animate Vehicle' to generate a new base animation"
            log_error(message, "Speed Segments")
            show_message_box(message, "Could not enable Speed Segments", "ERROR")
            return {'CANCELLED'}


        if len(keyframes) < 2:
            message = f"Needs at least 2 keyframes on the 'Speed_Rotate' handle to be able to use the Speed Segments. Please add more keyframes or use a 'User Path' and 'Animate Vehicle' to generate a new base animation."
            log_error(message, "Speed Segments")
            show_message_box(message, "Could not enable Speed Segments", "ERROR")
            return {'CANCELLED'}
        

        if scene.frame_end-scene.frame_start > 1000:
            car = scene.lc.find_selected()
            car_props = car.properties

            # Reset user set resolution to avoid performance impact
            car_props.property_unset("speed_graph_resolution")

            message = f"Performance might vary for long animations. Consider reducing 'Graph Resolution' to improve performance"
            log_info(message, "Speed Segments")
            show_message_box(message, "Performance Warning", "INFO")
         

        if context.area.type == 'VIEW_3D':

            view_3D_list =  []
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        view_3D_list.append(area)

            if len(view_3D_list) > 1:
                message = "Multiple 3D Views are open. Speed Segments will only be shown correctly in one of them."
                log_error(message, "Speed Segments")
                show_message_box(message, "Multiple 3D Views", "INFO")
            
            cls.AREA = context.area

            args = (self, context)
            self.register_handlers(args, context)
            
            self.interpolated_points = []
            self.interpolated_speeds = []
            self.interpolated_p_to_s = []
            self.keyframe_coords = []
            self.keyframe_coords_to_draw = []
            self.keyframe_speeds = []
            self.knobs = []
            self.keyframe_region_x = []
            self.keyframe_region_y = []
            self.tower_coords = []
            self.frame_coords = []
            self.frame_speeds = []
            self.bypass_draw = False
            self.needs_full_redraw = True
            self.user_interaction = False
            self.needs_speed_tower_update = False
            self.ui_scale = 1
            
            try:
                self.ui_scale = bpy.context.preferences.view.ui_scale
            except: pass
            
            # Go to Pose mode to lock object selection
            try:
                bpy.ops.object.mode_set(mode='POSE')
            except:
                message = "Could not locate LC car rig. Please make sure it's not hidden or removed."
                log_error(message, "Speed Segments")
                show_message_box(message, "Could not enable Speed Segments", "ERROR")
                return {'CANCELLED'}


            # Turn Timeline into Graph Editor (opt-out)
            addon_root = ".".join(__package__.split(".")[:-2])
            addon_preferences = context.preferences.addons[addon_root].preferences
            if addon_preferences.open_graph_editor_segments:
                graph_editor_found = False
                graph_editor_created = False
                
                for window in bpy.context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'GRAPH_EDITOR':
                            graph_editor_found = True
                
                if not graph_editor_found:
                    for window in bpy.context.window_manager.windows:
                        for area in window.screen.areas:
                            if area.ui_type == 'TIMELINE':
                                area.type = 'GRAPH_EDITOR'
                                graph_editor_created = True
                                
                                break
                
                if graph_editor_found or graph_editor_created:
                    for area in bpy.context.screen.areas:
                        if area.type == "GRAPH_EDITOR":
                            override = bpy.context.copy()
                            override["area"] = area
                            override["region"] = area.regions[-1]
                            with bpy.context.temp_override(**override):
                                bpy.ops.graph.view_all()

                            break
                
            scene.settings.speed_segments_running = True
            
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        
        else:
            message = "Could not find a 3D view. Speed Segments cannot be started"
            log_error(message, "Speed Segments")
            show_message_box(message, "Could not enable Speed Segments", "ERROR")
            return {'CANCELLED'}

        
    def register_handlers(self, args, context):
        self.draw_handle_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, args, 'WINDOW', 'POST_VIEW')
        self.draw_handle_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, args, 'WINDOW', 'POST_PIXEL')  

class OBJECT_OT_speed_segment_apply_speed(bpy.types.Operator):
    bl_idname = "view3d.speed_segment_apply_speed"
    bl_label = "Speed Segment Apply Speed"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Apply the Speed set on the left to the selected Speed Keyframe in the Viewport"
    

    def set_slope(self, rad_per_frame, curr_p0, p1, curr_p2):
        
        #slope = (p2[1]-p1[1]) / (p2[0]-p1[0])
        N = Vector((1,rad_per_frame))

        d0 = (Vector((curr_p0[0], curr_p0[1])) - Vector((p1[0], p1[1]))).length
        d2 = (Vector((p1[0], p1[1])) - Vector((curr_p2[0], curr_p2[1]))).length
        
        p0 = p1 + d0*-N
        p2 = p1 + d2*N
                
        return p0, p2
        

    def execute(self, context):
        scene = bpy.context.scene
        car = scene.lc.find_selected()
        rig_object = car.rig_object
        car_props = car.properties
        keyframe_points = get_speed_rotate_keyframes(rig_object)


        fps = bpy.context.scene.render.fps
        addon_root = ".".join(__package__.split(".")[:-2])
        addon_preferences = context.preferences.addons[addon_root].preferences
        use_imperial = addon_preferences.use_imperial

        if use_imperial:
            new_speed = car_props.type_speed/0.621371
        else:
            new_speed = car_props.type_speed

        new_m_per_sec = new_speed/3.6
        new_rad_per_sec = new_m_per_sec/10
        new_rad_per_frame = new_rad_per_sec/fps


        for key in keyframe_points:
            if key.select_control_point:
                handle_left, handle_right = self.set_slope(new_rad_per_frame, key.handle_left, key.co, key.handle_right)

                key.handle_left = handle_left
                key.handle_right = handle_right

        key_smooth()

        return {'FINISHED'}


class OBJECT_OT_speed_segment_apply_offset_time(bpy.types.Operator):
    bl_idname = "view3d.speed_segment_apply_offset_time"
    bl_label = "Speed Segment Apply Offset Time"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Apply the Offset Time set on the left to the selected Speed Keyframe in the Viewport"
    
    def execute(self, context):
        scene = bpy.context.scene
        car = scene.lc.find_selected()
        rig_object = car.rig_object
        car_props = car.properties
        keyframe_points = get_speed_rotate_keyframes(rig_object)

        fps = bpy.context.scene.render.fps
        if car_props.timecode_type == 'FRAME':
            new_offset_frames = car_props.type_offset_time_frame
        else:
            new_offset_frames = car_props.type_offset_time_sec*fps


        i = 0
        delta = None
        for key in keyframe_points:
            if key.select_control_point and i>0:
                new_key_time = new_offset_frames + keyframe_points[i-1].co[0]
                delta = new_key_time - key.co[0]
            
            if delta != None:
                # Offset key and all following keys
                key.co[0] += delta
                key.handle_left[0] += delta
                key.handle_right[0] += delta
              
            i += 1
        
        key_smooth()
        
        return {'FINISHED'}