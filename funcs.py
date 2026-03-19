# Copyright (C) 2021 Clemens Beute

# ##### BEGIN GPL LICENSE BLOCK #####
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import numpy
import mathutils
import gpu
import math
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader

from . import vars


def draw_circle_2d_compat(position, color, radius, segments=32):
    """Draw a 2D circle using the GPU module (replaces removed gpu_extras.presets.draw_circle_2d)"""
    coords = []
    for i in range(segments + 1):
        angle = 2 * math.pi * i / segments
        x = position[0] + radius * math.cos(angle)
        y = position[1] + radius * math.sin(angle)
        coords.append((x, y))
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def get_active_brush():
    """Get the active brush for the current paint mode"""
    ts = bpy.context.tool_settings
    if vars.mode == 'VERTEX_PAINT':
        return ts.vertex_paint.brush
    elif vars.mode in ('2D_PAINT', '3D_PAINT'):
        return ts.image_paint.brush
    return None


def _get_paint_settings():
    """Get the paint settings for the current paint mode (Blender 5.0+).
    In Blender 5.0, unified_paint_settings moved from tool_settings to each paint mode."""
    ts = bpy.context.tool_settings
    if vars.mode == 'VERTEX_PAINT':
        return getattr(ts.vertex_paint, 'unified_paint_settings', None)
    elif vars.mode in ('2D_PAINT', '3D_PAINT'):
        return getattr(ts.image_paint, 'unified_paint_settings', None)
    return None


def get_paint_color():
    """Get the current paint brush color"""
    ups = _get_paint_settings()
    if ups is not None and hasattr(ups, 'color'):
        return ups.color
    brush = get_active_brush()
    if brush is not None:
        return brush.color
    return (0.5, 0.5, 0.5)


def set_paint_color(color):
    """Set the current paint brush color"""
    # Set on unified_paint_settings (Blender 5.0+ reads color from here)
    ups = _get_paint_settings()
    if ups is not None and hasattr(ups, 'color'):
        ups.color = color
    # Also set on brush for visual feedback and compatibility
    brush = get_active_brush()
    if brush is not None:
        brush.color = color


def get_paint_size():
    """Get the current paint brush size"""
    ups = _get_paint_settings()
    if ups is not None and hasattr(ups, 'size'):
        return ups.size
    brush = get_active_brush()
    if brush is not None:
        return brush.size
    return 50


def lerp(mix, a, b):
    """linear interpolation"""

    return (b - a) * mix + a


def remove_temp_obj():
    """removes the temp object and data if it exists"""

    if bpy.data.meshes.get("FLOWMAP_temp_mesh"):
        bpy.data.meshes.remove(bpy.data.meshes["FLOWMAP_temp_mesh"])
    if bpy.data.objects.get("FLOWMAP_temp_obj"):
        bpy.data.objects.remove(bpy.data.objects["FLOWMAP_temp_obj"])
    return None


def triangulate_object(obj):
    """triangulate incoming object and return it as a temporary copy"""

    template_ob = obj

    # first remove temp stuff, if it exists already
    remove_temp_obj()

    ob = template_ob.copy()
    ob.data = ob.data.copy()
    ob.modifiers.new("triangulate", 'TRIANGULATE')

    # need to be in scnene, for depsgraph to work apparently
    bpy.context.collection.objects.link(ob)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    object_eval = ob.evaluated_get(depsgraph)
    mesh_from_eval = bpy.data.meshes.new_from_object(object_eval)
    ob.data = mesh_from_eval

    new_ob = bpy.data.objects.new(name="FLOWMAP_temp_obj", object_data=mesh_from_eval)
    bpy.context.collection.objects.link(new_ob)
    new_ob.matrix_world = template_ob.matrix_world

    # remove the depsgraph object
    bpy.data.objects.remove(ob, do_unlink=True)

    # hide temp obj
    new_ob.hide_set(True)

    return new_ob


def _obj_ray_cast(context, area_pos, obj, matrix):
    """Wrapper for ray casting that moves the ray into object space"""

    # get the context arguments
    region = context.region
    rv3d = context.region_data
    coord = area_pos[0], area_pos[1]

    # get the ray from the viewport and mouse
    view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    ray_target = ray_origin + view_vector

    # get the ray relative to the object
    matrix_inv = matrix.inverted()
    ray_origin_obj = matrix_inv @ ray_origin
    ray_target_obj = matrix_inv @ ray_target
    ray_direction_obj = ray_target_obj - ray_origin_obj

    # cast the ray
    success, location, normal, face_index = obj.ray_cast(
        origin=ray_origin_obj,
        direction=ray_direction_obj,
        distance=bpy.context.scene.flowmap_painter_props.trace_distance
    )

    if success:
        return location, normal, face_index
    return None, None, None


def line_trace_for_pos(context, area_pos):
    """Trace at given position. Return hit in object and world space."""
    obj = bpy.context.active_object
    matrix = obj.matrix_world.copy()
    hit_world = None
    if obj.type == 'MESH':
        hit, normal, face_index = _obj_ray_cast(context=context, area_pos=area_pos, obj=vars.tri_obj, matrix=matrix)
        if hit is not None:
            hit_world = matrix @ hit
            return hit, hit_world
        else:
            return None, None


def get_uv_space_direction_color(context, area_pos, area_prev_pos):
    """combine area_pos and previouse linetrace into direction color"""

    def line_trace_for_uv(context, area_pos):
        """line trace into the scene, to find uv coordinates at the brush location at the object """

        def pos_to_uv_co(obj, matrix_world, world_pos, face_index):
            """translate 3D postion on a mesh into uv coordinates"""

            face_verts = []
            uv_verts = []

            # uv"s are stored in loops
            face = obj.data.polygons[face_index]
            for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                uv_coords = obj.data.uv_layers.active.data[loop_idx].uv

                face_verts.append(matrix_world @ obj.data.vertices[vert_idx].co)
                uv_verts.append(uv_coords.to_3d())

                # print(f'face idx {face.index}, vert idx {vert_idx}, vert coords {ob.data.vertices[vert_idx].co},uv coords {uv_coords.x} {uv_coords.y}')

            # print("world_pos: ", world_pos)
            # print("face_verts: ", face_verts[0], face_verts[1], face_verts[2])
            # print("uv_verts: ", uv_verts[0], uv_verts[1], uv_verts[2])

            # point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3
            uv_co = mathutils.geometry.barycentric_transform(
                world_pos, face_verts[0], face_verts[1], face_verts[2], uv_verts[0], uv_verts[1], uv_verts[2]
            )

            return uv_co

        obj = bpy.context.active_object
        matrix = obj.matrix_world.copy()
        uv_co = None
        hit = None
        hit_world = None
        if obj.type == 'MESH':
            hit, normal, face_index = _obj_ray_cast(context=context, area_pos=area_pos, obj=vars.tri_obj, matrix=matrix)
            if hit is not None:
                hit_world = matrix @ hit
                # enable for debug:
                # bpy.context.scene.cursor.location = hit_world
                uv_co = pos_to_uv_co(
                    obj=vars.tri_obj, matrix_world=obj.matrix_world, world_pos=hit_world, face_index=face_index
                )

        return uv_co, hit

    # finally get the uv coordinates
    uv_pos, hit_world = line_trace_for_uv(context, area_pos)
    uv_prev_pos, _ = line_trace_for_uv(context, area_prev_pos)

    if uv_pos is None or uv_prev_pos is None:
        return None, None

    # convert to numpy array for further math
    uv_pos = numpy.array([uv_pos[0], uv_pos[1]])
    uv_prev_pos = numpy.array([uv_prev_pos[0], uv_prev_pos[1]])

    # calculate direction vector and normalize it
    uv_direction_vector = uv_pos - uv_prev_pos
    norm_factor = numpy.linalg.norm(uv_direction_vector)
    if norm_factor == 0:
        return None, None

    norm_uv_direction_vector = uv_direction_vector / norm_factor

    # map the range to the color range, so 0.5 ist the middle
    color_range_vector = (norm_uv_direction_vector + 1) * 0.5
    direction_color = [color_range_vector[0], color_range_vector[1], 0]

    # enable for uv position debug:
    # print([uv_pos[0], uv_pos[1], 0])
    return direction_color, hit_world


def get_obj_space_direction_color(context, area_pos, area_prev_pos):
    """get the normalized vector color from brush and previous location in object space"""

    # get world hit and previus
    location, hit_world = line_trace_for_pos(context=context, area_pos=area_pos)
    _, prev_hit_world = line_trace_for_pos(context=context, area_pos=area_prev_pos)

    if hit_world is None or prev_hit_world is None:
        return None, None
    else:

        obj = bpy.context.scene.flowmap_painter_props.object
        if obj is None:
            obj = bpy.context.active_object

        matrix = obj.matrix_world.inverted().copy()
        hit_obj = matrix @ hit_world
        prev_hit_obj = matrix @ prev_hit_world

        # convert to numpy array for further math
        obj_pos = numpy.array([hit_obj[0], hit_obj[1], hit_obj[2]])
        obj_prev_pos = numpy.array([prev_hit_obj[0], prev_hit_obj[1], prev_hit_obj[2]])

        # calculate direction vector and normalize it
        world_direction_vector = obj_pos - obj_prev_pos
        norm_factor = numpy.linalg.norm(world_direction_vector)
        if norm_factor == 0:
            return None, None

        norm_world_direction_vector = world_direction_vector / norm_factor

        # map the range to the color range, so 0.5 ist the middle
        color_range_vector = (norm_world_direction_vector + 1) * 0.5
        # color_range_vector = norm_world_direction_vector #debug original color
        direction_color = [color_range_vector[0], color_range_vector[1], color_range_vector[2]]

        return direction_color, location


def get_world_space_direction_color(context, area_pos, area_prev_pos):
    """get the normalized vector color from brush and previous location in world space"""

    # get world hit and previus
    location, hit_world = line_trace_for_pos(context=context, area_pos=area_pos)
    _, prev_hit_world = line_trace_for_pos(context=context, area_pos=area_prev_pos)

    if hit_world is None or prev_hit_world is None:
        return None, None
    else:
        # convert to numpy array for further math
        world_pos = numpy.array([hit_world[0], hit_world[1], hit_world[2]])
        world_prev_pos = numpy.array([prev_hit_world[0], prev_hit_world[1], prev_hit_world[2]])

        # calculate direction vector and normalize it
        world_direction_vector = world_pos - world_prev_pos
        norm_factor = numpy.linalg.norm(world_direction_vector)
        if norm_factor == 0:
            return None, None

        norm_world_direction_vector = world_direction_vector / norm_factor

        # map the range to the color range, so 0.5 ist the middle
        color_range_vector = (norm_world_direction_vector + 1) * 0.5
        # color_range_vector = norm_world_direction_vector #debug original color
        direction_color = [color_range_vector[0], color_range_vector[1], color_range_vector[2]]

        return direction_color, location


def paint_a_dot(context, area_type, mouse_position, event, location=None):
    """paint one dot | works 2D, as well as 3D and also for vertex paint"""

    if context.area.type != area_type:
        return None

    area_position_x = bpy.context.area.x
    area_position_y = bpy.context.area.y

    # get the active brush
    if vars.mode == 'VERTEX_PAINT':
        brush = bpy.context.tool_settings.vertex_paint.brush
    elif vars.mode == '2D_PAINT' or vars.mode == '3D_PAINT':
        brush = bpy.context.tool_settings.image_paint.brush
    else:
        return None

    if brush is None:
        return

    # pressure and dynamic pen pressure
    pressure = brush.strength
    if getattr(brush, 'use_pressure_strength', False) is True:
        pressure = pressure * event.pressure

    # size and dynamic pen pressure size
    size = brush.size
    if getattr(brush, 'use_pressure_size', False) is True:
        size = size * event.pressure

    if location is None:
        loc = (0, 0, 0)
    else:
        loc = location

    stroke = [
        {
            "name": "test",
            "is_start": True,
            "location": loc,
            "mouse": (mouse_position[0] - area_position_x, mouse_position[1] - area_position_y),
            "mouse_event": (mouse_position[0] - area_position_x, mouse_position[1] - area_position_y),
            "pressure": pressure,
            "size": size,
            "time": 1,
            "x_tilt": 0,
            "y_tilt": 0,
        }
    ]

    if vars.mode == '2D_PAINT' or vars.mode == '3D_PAINT':
        bpy.ops.paint.image_paint(stroke=stroke, mode='NORMAL')

    elif vars.mode == 'VERTEX_PAINT':
        if location:
            bpy.ops.paint.vertex_paint(stroke=stroke, mode='NORMAL')

    return None


def modal_paint_three_d(self, context, event):
    """The internal of the modal 3D operators. Its used for 3D_PAINT and VERTEX_PAINT."""

    context.area.tag_redraw()

    # track left mouse press state
    if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
        # set first position of stroke
        self.furthest_position = numpy.array([event.mouse_x, event.mouse_y])
        vars.pressing = True

    if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
        vars.pressing = False

    if event.type == 'MOUSEMOVE' or event.type == 'LEFTMOUSE':
        # get mouse positions
        mouse_position = numpy.array([event.mouse_x, event.mouse_y])

        # get area position
        area_position_x = bpy.context.area.x
        area_position_y = bpy.context.area.y

        # get area mouse positions
        area_pos = (mouse_position[0] - area_position_x, mouse_position[1] - area_position_y)
        area_prev_pos = (self.mouse_prev_position[0] - area_position_x, self.mouse_prev_position[1] - area_position_y)

        # if mouse has traveled enough distance, update color and paint
        distance = numpy.linalg.norm(self.furthest_position - mouse_position)
        if distance >= bpy.context.scene.flowmap_painter_props.brush_spacing:
            # reset threshold
            self.furthest_position = mouse_position

            # finding the direction vector, from UV Coordinates, from 3D location | object space | world space
            direction_color = None
            location = None
            if bpy.context.scene.flowmap_painter_props.space_type == "uv_space":
                direction_color, location = get_uv_space_direction_color(context, area_pos, area_prev_pos)
            elif bpy.context.scene.flowmap_painter_props.space_type == "object_space":
                direction_color, location = get_obj_space_direction_color(context, area_pos, area_prev_pos)
            elif bpy.context.scene.flowmap_painter_props.space_type == "world_space":
                direction_color, location = get_world_space_direction_color(context, area_pos, area_prev_pos)

            # set paint brush color, but check for nan first
            if direction_color is not None:
                if not any(numpy.isnan(val) for val in direction_color):
                    set_paint_color(direction_color)

            if vars.pressing:
                # paint the actual dots with the selected brush spacing
                # if mouse moved more than double of the brush_spacing -> draw substeps
                substeps_float = distance / bpy.context.scene.flowmap_painter_props.brush_spacing
                substeps_int = int(substeps_float)
                if distance > 2 * bpy.context.scene.flowmap_painter_props.brush_spacing:
                    substep_count = substeps_int
                    while substep_count > 0:
                        lerp_mix = 1 / (substeps_int) * substep_count
                        lerp_paint_position = numpy.array(
                            [
                                lerp(lerp_mix, self.mouse_prev_position[0], mouse_position[0]),
                                lerp(lerp_mix, self.mouse_prev_position[1], mouse_position[1])
                            ]
                        )
                        paint_a_dot(
                            context,
                            area_type='VIEW_3D',
                            mouse_position=lerp_paint_position,
                            event=event,
                            location=location
                        )
                        substep_count = substep_count - 1

                else:
                    paint_a_dot(
                        context, area_type='VIEW_3D', mouse_position=mouse_position, event=event, location=location
                    )

            self.mouse_prev_position = mouse_position

        # remove circle
        if vars.circle:
            bpy.types.SpaceView3D.draw_handler_remove(vars.circle, 'WINDOW')
            vars.circle = None

        vars.circle_pos = (event.mouse_region_x, event.mouse_region_y)

        # draw circle
        def draw():
            pos = vars.circle_pos
            brush_col = get_paint_color()
            col = (brush_col[0], brush_col[1], brush_col[2], 1)
            size = get_paint_size()

            draw_circle_2d_compat(pos, col, size)

        vars.circle = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')

        return {'RUNNING_MODAL'}

    if event.type == 'ESC':
        # reset brush color
        set_paint_color((0.5, 0.5, 0.5))
        # remove circle
        if vars.circle:
            bpy.types.SpaceView3D.draw_handler_remove(vars.circle, 'WINDOW')
            context.area.tag_redraw()
            vars.circle = None
        context.area.tag_redraw()
        remove_temp_obj()
        return {'FINISHED'}

    return {'PASS_THROUGH'}
