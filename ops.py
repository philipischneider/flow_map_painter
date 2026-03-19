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

from . import funcs
from . import vars


class FLOWMAP_OT_FLOW_MAP_PAINT_2D(bpy.types.Operator):
    """Flowmap 2D Paint Mode | A brush tool, wich gets the color from your movement direction"""

    bl_idname = "flowmap.flow_map_paint_two_d"
    bl_label = "Flowmap 2D Paint Mode"

    furthest_position = numpy.array([0, 0])
    mouse_prev_position = (0, 0)

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
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

            # if mouse has traveled enough distance, update color and paint
            distance = numpy.linalg.norm(self.furthest_position - mouse_position)
            if distance >= bpy.context.scene.flowmap_painter_props.brush_spacing:
                # reset threshold
                self.furthest_position = mouse_position

                # calculate direction vector and normalize it
                mouse_direction_vector = mouse_position - self.mouse_prev_position
                norm_factor = numpy.linalg.norm(mouse_direction_vector)
                if norm_factor == 0:
                    norm_mouse_direction_vector = numpy.array([0, 0])
                else:
                    norm_mouse_direction_vector = mouse_direction_vector / norm_factor

                # map the range to the color range, so 0.5 ist the middle
                color_range_vector = (norm_mouse_direction_vector + 1) * 0.5
                direction_color = [color_range_vector[0], color_range_vector[1], 0]

                # set paint brush color, but check for nan first
                if not any(numpy.isnan(val) for val in direction_color):
                    funcs.set_paint_color(direction_color)

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
                                    funcs.lerp(lerp_mix, self.mouse_prev_position[0], mouse_position[0]),
                                    funcs.lerp(lerp_mix, self.mouse_prev_position[1], mouse_position[1])
                                ]
                            )
                            funcs.paint_a_dot(
                                context, area_type='IMAGE_EDITOR', mouse_position=lerp_paint_position, event=event
                            )
                            substep_count = substep_count - 1

                    else:
                        funcs.paint_a_dot(context, area_type='IMAGE_EDITOR', mouse_position=mouse_position, event=event)

                self.mouse_prev_position = mouse_position

            # remove circle
            if vars.circle:
                bpy.types.SpaceImageEditor.draw_handler_remove(vars.circle, 'WINDOW')
                vars.circle = None

            vars.circle_pos = (event.mouse_region_x, event.mouse_region_y)

            # draw circle
            def draw():
                pos = vars.circle_pos
                brush_col = funcs.get_paint_color()
                col = (brush_col[0], brush_col[1], 0, 1)

                size = funcs.get_paint_size() * bpy.context.space_data.zoom[0]

                funcs.draw_circle_2d_compat(pos, col, size)

            vars.circle = bpy.types.SpaceImageEditor.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')

            return {'RUNNING_MODAL'}

        if event.type == 'ESC':
            funcs.set_paint_color((0.5, 0.5, 0.5))
            # remove circle
            if vars.circle:
                bpy.types.SpaceImageEditor.draw_handler_remove(vars.circle, 'WINDOW')
                vars.circle = None
            context.area.tag_redraw()

            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        vars.mode = '2D_PAINT'
        bpy.context.window.cursor_set('PAINT_CROSS')
        return {'RUNNING_MODAL'}


class FLOWMAP_OT_FLOW_MAP_PAINT_3D(bpy.types.Operator):
    """Flowmap 3D Paint Mode | A brush tool, wich gets the color from your movement direction"""

    bl_idname = "flowmap.flow_map_paint_three_d"
    bl_label = "Flowmap 3D Paint Mode"

    furthest_position = numpy.array([0, 0])
    mouse_prev_position = (0, 0)

    def modal(self, context=bpy.types.Context, event=bpy.types.Event):

        ret = funcs.modal_paint_three_d(self=self, context=context, event=event)
        return ret

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        vars.tri_obj = funcs.triangulate_object(obj=bpy.context.active_object)
        vars.mode = '3D_PAINT'
        bpy.context.window.cursor_set('PAINT_CROSS')
        return {'RUNNING_MODAL'}


class FLOWMAP_OT_FLOW_MAP_PAINT_VERTCOL(bpy.types.Operator):
    """Flowmap Vertex Paint Mode | A brush tool, wich gets the color from your movement direction"""

    bl_idname = "flowmap.flow_map_paint_vcol"
    bl_label = "Flowmap Vertex Paint Mode"

    furthest_position = numpy.array([0, 0])
    mouse_prev_position = (0, 0)

    def modal(self, context=bpy.types.Context, event=bpy.types.Event):
        ret = funcs.modal_paint_three_d(self=self, context=context, event=event)
        return ret

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        vars.tri_obj = funcs.triangulate_object(obj=bpy.context.active_object)
        vars.mode = 'VERTEX_PAINT'
        bpy.context.window.cursor_set('PAINT_CROSS')
        return {'RUNNING_MODAL'}
