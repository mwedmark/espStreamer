#!/usr/bin/env python3
"""Generate and display a Sierpinski Triangle (2D CPU) or a Sierpinski Tetrahedron (3D GPU) in a graphical window using Pygame and PyOpenGL."""

import pygame
from pygame.locals import *
import math
import array
import ctypes
import random

# Try importing PyOpenGL for GPU rendering
try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    opengl_available = True
except ImportError:
    opengl_available = False


class SierpinskiPhysicsPiece:
    """Represents a component tetrahedron in the physics simulation."""
    def __init__(self, pos, vel, color, rot_axis, rot_vel, radius):
        self.pos = list(pos)
        self.vel = list(vel)
        self.color = color
        self.rot_axis = rot_axis
        self.rot_angle = 0.0
        self.rot_vel = rot_vel
        self.radius = radius


class SierpinskiTriangleApp:
    """Application to visualize the Sierpinski Triangle (2D) and Tetrahedron (3D) with CPU and GPU render paths."""
    
    def __init__(self):
        # Initialize Pygame and create window
        pygame.init()
        self.width = 800
        self.height = 600
        self.render_mode = 'cpu'  # 'cpu' or 'gpu'
        self.opengl_available = opengl_available
        self.is_fullscreen = False
        
        # Rotation state
        self.auto_rotate = True
        self.rotation_angle = 0.0
        self.hover_angle = 0.0
        
        # Set initial display mode (always start on CPU, resizable)
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("Sierpinski Triangle Generator")
        
        # Default settings
        self.iterations = 5
        self.color_mode = 'rainbow'
        self.selected_color = 'rainbow'
        self.dragging_slider = False
        
        # Initialize geometry cache (CPU path)
        self.geom_cache_key = None
        self.cached_vertices = []
        self.cached_colors = []
        
        # Initialize 3D shader program (GPU path)
        self.shader_program = None
        
        # Simulation state machine
        self.simulation_state = 'hover'  # 'hover' or 'falling'
        self.hover_frames = 0
        self.stable_frames = 0
        self.physics_pieces = []
        self.physics_piece_scale = 1.0
        self.camera_offset_y = 0.0
        self.lit_list = None
        self.flat_list = None
        
        # Initialize fonts and control buttons
        self.init_fonts()
        
        self.color_buttons = {}
        self.mode_buttons = {}
        self.rotate_button = None
        self.full_button = None
        self.clear_button = None
        self.iter_slider = None
        
    def init_fonts(self):
        """Initialize fonts with the current resolution scale factor."""
        pygame.font.init()
        scale = self.height / 600.0
        self.font = pygame.font.Font(None, int(22 * scale))
        self.title_font = pygame.font.Font(None, int(28 * scale))
        
    def create_controls(self):
        """Create the control panel coordinates in screen space scaled dynamically to the resolution."""
        scale = self.height / 600.0
        ui_height = int(60 * scale)
        ui_y_offset = self.height - ui_height
        btn_y = ui_y_offset + (ui_height - int(30 * scale)) // 2
        
        # Iterations slider bounding box (scaled width and height)
        self.iter_slider = pygame.Rect(int(100 * scale), btn_y, int(110 * scale), int(30 * scale))
        
        # Mode switch buttons (CPU / GPU)
        self.mode_buttons = {
            'cpu': pygame.Rect(int(220 * scale), btn_y, int(35 * scale), int(30 * scale)),
            'gpu': pygame.Rect(int(260 * scale), btn_y, int(35 * scale), int(30 * scale))
        }
        
        # Rotate and Fullscreen buttons
        self.rotate_button = pygame.Rect(int(305 * scale), btn_y, int(50 * scale), int(30 * scale))
        self.full_button = pygame.Rect(int(360 * scale), btn_y, int(50 * scale), int(30 * scale))
        
        # Color mode buttons
        self.color_buttons = {
            'rainbow': pygame.Rect(int(455 * scale), btn_y, int(60 * scale), int(30 * scale)),
            'red': pygame.Rect(int(520 * scale), btn_y, int(35 * scale), int(30 * scale)),
            'blue': pygame.Rect(int(560 * scale), btn_y, int(35 * scale), int(30 * scale)),
            'white': pygame.Rect(int(600 * scale), btn_y, int(45 * scale), int(30 * scale)),
        }
        
        # Reset button (aligned to the right side of the screen)
        self.clear_button = pygame.Rect(self.width - int(85 * scale), btn_y, int(70 * scale), int(30 * scale))
        
    def set_render_mode(self, mode):
        """Toggle between CPU and GPU modes by re-initializing the display context."""
        if mode == self.render_mode:
            return
        if mode == 'gpu' and not self.opengl_available:
            print("OpenGL is not available. Cannot switch to GPU mode.")
            return
            
        self.render_mode = mode
        
        # Reset physics simulation state on mode switch
        self.simulation_state = 'hover'
        self.hover_frames = 0
        self.stable_frames = 0
        self.physics_pieces = []
        
        # Gracefully recreate display mode for OpenGL context switch
        pygame.display.quit()
        pygame.display.init()
        
        if self.render_mode == 'gpu':
            # Setup Depth buffer attribute before set_mode
            pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
            
            flags = pygame.OPENGL | pygame.DOUBLEBUF
            if self.is_fullscreen:
                flags |= pygame.FULLSCREEN
            else:
                flags |= pygame.RESIZABLE
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            
            # Configure initial OpenGL state
            glViewport(0, 0, self.width, self.height)
            glClearColor(0.04, 0.05, 0.06, 1.0)
            self.init_opengl_resources()
        else:
            flags = pygame.FULLSCREEN if self.is_fullscreen else pygame.RESIZABLE
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            
        pygame.display.set_caption("Sierpinski Triangle Generator")
        self.create_controls()
        self.init_fonts()
        self.geom_cache_key = None
        
    def toggle_fullscreen(self):
        """Toggle fullscreen mode with dynamic window size query and scaling."""
        self.is_fullscreen = not self.is_fullscreen
        
        # Recreate display mode
        pygame.display.quit()
        pygame.display.init()
        
        if self.is_fullscreen:
            # Query the desktop screen's native resolution
            info = pygame.display.Info()
            self.width = info.current_w
            self.height = info.current_h
        else:
            self.width = 800
            self.height = 600
            
        # Re-create controls layout matching the resolution size
        self.create_controls()
        self.init_fonts()
        
        # Clear geometry cache so it gets recalculated for the new resolution
        self.geom_cache_key = None
        
        if self.render_mode == 'gpu':
            pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
            flags = pygame.OPENGL | pygame.DOUBLEBUF
            if self.is_fullscreen:
                flags |= pygame.FULLSCREEN
            else:
                flags |= pygame.RESIZABLE
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            
            # Configure OpenGL state
            glViewport(0, 0, self.width, self.height)
            glClearColor(0.04, 0.05, 0.06, 1.0)
            self.init_opengl_resources()
        else:
            flags = pygame.FULLSCREEN if self.is_fullscreen else pygame.RESIZABLE
            self.screen = pygame.display.set_mode((self.width, self.height), flags)
            
        pygame.display.set_caption("Sierpinski Triangle Generator")
        
    def on_color_change(self):
        """Handle color selection change."""
        self.color_mode = self.selected_color
        
    def update_iterations(self, value):
        """Update iteration count from slider."""
        try:
            self.iterations = int(float(value))
            max_iter = 6
            self.iterations = max(1, min(max_iter, self.iterations))
        except ValueError:
            pass
            
    def draw(self):
        """Draw the Sierpinski Triangle (CPU) or Tetrahedron (GPU)."""
        scale = self.height / 600.0
        
        if self.render_mode == 'cpu':
            self.screen.fill((10, 12, 16))  # Premium dark background
            
            # Calculate dynamic bounds based on screen resolution scale for 2D
            margin_y_top = int(80 * scale)
            margin_y_bottom = int(20 * scale)
            ui_height = int(60 * scale)
            draw_height = self.height - ui_height - margin_y_top - margin_y_bottom
            base_width = draw_height * (2.0 / math.sqrt(3))
            center_x = self.width / 2.0
            center_y_bottom = self.height - ui_height - margin_y_bottom
            p1 = (center_x - base_width / 2.0, center_y_bottom)
            p2 = (center_x + base_width / 2.0, center_y_bottom)
            p3 = (center_x, center_y_bottom - draw_height)
            
            # Center of rotation (Centroid of the equilateral triangle)
            cx = (p1[0] + p2[0] + p3[0]) / 3.0
            cy = (p1[1] + p2[1] + p3[1]) / 3.0
            
            # Apply rotation around centroid if active
            if self.rotation_angle != 0.0:
                rad = math.radians(self.rotation_angle)
                cos_r = math.cos(rad)
                sin_r = math.sin(rad)
                
                # Draw rotated triangles
                for i in range(0, len(self.cached_vertices), 3):
                    v1, v2, v3 = self.cached_vertices[i:i+3]
                    c1, c2, c3 = self.cached_colors[i:i+3]
                    
                    rv1 = ( (v1[0] - cx) * cos_r - (v1[1] - cy) * sin_r + cx, (v1[0] - cx) * sin_r + (v1[1] - cy) * cos_r + cy )
                    rv2 = ( (v2[0] - cx) * cos_r - (v2[1] - cy) * sin_r + cx, (v2[0] - cx) * sin_r + (v2[1] - cy) * cos_r + cy )
                    rv3 = ( (v3[0] - cx) * cos_r - (v3[1] - cy) * sin_r + cx, (v3[0] - cx) * sin_r + (v3[1] - cy) * cos_r + cy )
                    
                    pygame.draw.polygon(self.screen, self.parse_color(c1), [rv1, rv2, rv3])
            else:
                # Draw standard triangles
                for i in range(0, len(self.cached_vertices), 3):
                    v1, v2, v3 = self.cached_vertices[i:i+3]
                    c1, c2, c3 = self.cached_colors[i:i+3]
                    pygame.draw.polygon(self.screen, self.parse_color(c1), [v1, v2, v3])
            
        else:
            if self.simulation_state == 'hover':
                # Calculate 3D rotation matrix (orbiting yaw, with pitch constrained to upper hemisphere)
                pitch = 15.0 + 10.0 * math.sin(self.hover_angle)
                rot_matrix = self.get_rotation_matrix(self.rotation_angle, pitch)
                
                # GPU Mode: Raymarch using GLSL fragment shader
                glClearColor(0.04, 0.05, 0.06, 1.0)
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                
                # Draw using raymarching shader program
                if self.shader_program is not None:
                    glUseProgram(self.shader_program)
                    
                    # Send uniforms
                    glUniform2f(self.u_resolution_loc, float(self.width), float(self.height))
                    glUniformMatrix3fv(self.u_rotation_loc, 1, GL_FALSE, rot_matrix)
                    glUniform1i(self.u_iterations_loc, self.iterations)
                    
                    color_idx = 0
                    if self.color_mode == 'red': color_idx = 1
                    elif self.color_mode == 'blue': color_idx = 2
                    elif self.color_mode == 'white': color_idx = 3
                    glUniform1i(self.u_color_mode_loc, color_idx)
                    
                    hover_y = 0.45 + 0.18 * math.sin(self.hover_angle)
                    glUniform1f(self.u_hover_y_loc, hover_y)
                    
                    # Render fullscreen quad
                    glBegin(GL_QUADS)
                    glVertex2f(-1.0, -1.0)
                    glVertex2f(1.0, -1.0)
                    glVertex2f(1.0, 1.0)
                    glVertex2f(-1.0, 1.0)
                    glEnd()
                    
                    glUseProgram(0)
            else:
                # Falling pieces rendering with fixed-function polygon renderer
                # We pass the yaw angle, and draw_physics_scene will dynamically compute pitch and rot_matrix
                self.draw_physics_scene(self.rotation_angle)
            
    def draw_ui(self, surf):
        """Draw the UI overlay and header controls directly to target surface."""
        mouse_pos = pygame.mouse.get_pos()
        scale = self.height / 600.0
        ui_height = int(60 * scale)
        ui_y_offset = self.height - ui_height
        
        # 1. Draw Title Header
        title_text = self.title_font.render("Sierpinski Triangle Generator", True, (255, 255, 255))
        surf.blit(title_text, (int(20 * scale), int(15 * scale)))
        
        mode_str = "GPU Accelerated (3D Tetrahedron)" if self.render_mode == 'gpu' else "CPU Rendered (2D Triangle)"
        sub_text = self.font.render(f"Interactive Generator • {mode_str}", True, (156, 163, 175))
        surf.blit(sub_text, (int(20 * scale), int(42 * scale)))
        
        # 2. Draw control panel background with a sleek top separator
        pygame.draw.rect(surf, (20, 24, 30), (0, ui_y_offset, self.width, ui_height))
        pygame.draw.line(surf, (40, 48, 60), (0, ui_y_offset), (self.width, ui_y_offset), 2)
        
        # 3. Draw Iterations Slider (Iterations: X)
        iter_label = self.font.render(f"Iterations: {self.iterations}", True, (243, 244, 246))
        surf.blit(iter_label, (int(15 * scale), ui_y_offset + int(22 * scale)))
        
        slider_y = ui_y_offset + int(30 * scale)
        slider_x_start = self.iter_slider.x
        slider_width = self.iter_slider.width
        
        max_iter = 6
        active_ratio = (self.iterations - 1) / float(max_iter - 1)
        active_width = int(active_ratio * slider_width)
        
        slider_hovered = self.iter_slider.collidepoint(mouse_pos) or self.dragging_slider
        
        # Track background
        pygame.draw.rect(surf, (55, 65, 81), (slider_x_start, slider_y - 2, slider_width, 4), border_radius=2)
        # Active track fill (blue)
        pygame.draw.rect(surf, (59, 130, 246), (slider_x_start, slider_y - 2, active_width, 4), border_radius=2)
        
        # Handle
        handle_cx = slider_x_start + active_width
        handle_cy = slider_y
        handle_color = (255, 255, 255)
        handle_outline = (59, 130, 246) if slider_hovered else (156, 163, 175)
        
        if self.dragging_slider:
            # Subtle glow
            glow_surf = pygame.Surface((int(24 * scale), int(24 * scale)), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (59, 130, 246, 70), (int(12 * scale), int(12 * scale)), int(12 * scale))
            surf.blit(glow_surf, (handle_cx - int(12 * scale), handle_cy - int(12 * scale)))
            
        pygame.draw.circle(surf, handle_color, (handle_cx, handle_cy), int(7 * scale))
        pygame.draw.circle(surf, handle_outline, (handle_cx, handle_cy), int(7 * scale), width=2)
        
        # 4. Draw Mode Switch Buttons (CPU / GPU)
        mode_label = self.font.render("Mode:", True, (243, 244, 246))
        surf.blit(mode_label, (int(215 * scale), ui_y_offset + int(22 * scale)))
        
        for mode_name, rect in self.mode_buttons.items():
            is_selected = (self.render_mode == mode_name)
            is_hovered = rect.collidepoint(mouse_pos)
            is_disabled = (mode_name == 'gpu' and not self.opengl_available)
            
            if is_disabled:
                bg_color = (25, 25, 30)
                text_color = (75, 75, 85)
            elif is_selected:
                bg_color = (59, 130, 246)  # Blue-600
                text_color = (255, 255, 255)
            else:
                if is_hovered:
                    bg_color = (55, 65, 81)    # Gray-700
                    text_color = (243, 244, 246)
                else:
                    bg_color = (31, 41, 55)    # Gray-800
                    text_color = (156, 163, 175)
            
            pygame.draw.rect(surf, bg_color, rect, border_radius=6)
            
            # Draw borders
            if is_disabled:
                pygame.draw.rect(surf, (40, 40, 45), rect, width=1, border_radius=6)
            elif is_selected:
                pygame.draw.rect(surf, (255, 255, 255), rect, width=2, border_radius=6)
            elif is_hovered:
                pygame.draw.rect(surf, (107, 114, 128), rect, width=1, border_radius=6)
            else:
                pygame.draw.rect(surf, (75, 85, 99), rect, width=1, border_radius=6)
                
            btn_text = self.font.render(mode_name.upper(), True, text_color)
            surf.blit(btn_text, btn_text.get_rect(center=rect.center))
            
        # 5. Draw Rotate Button
        is_rot_hovered = self.rotate_button.collidepoint(mouse_pos)
        if self.auto_rotate:
            rot_bg = (124, 58, 237)       # Violet-600 when active
            rot_text_col = (255, 255, 255)
        else:
            rot_bg = (55, 65, 81) if is_rot_hovered else (31, 41, 55)
            rot_text_col = (243, 244, 246) if is_rot_hovered else (156, 163, 175)
            
        pygame.draw.rect(surf, rot_bg, self.rotate_button, border_radius=6)
        pygame.draw.rect(surf, (255, 255, 255) if self.auto_rotate else (75, 85, 99), self.rotate_button, width=1 if not self.auto_rotate else 2, border_radius=6)
        
        rot_text = self.font.render("Rot", True, rot_text_col)
        surf.blit(rot_text, rot_text.get_rect(center=self.rotate_button.center))
        
        # 6. Draw Fullscreen Button
        is_full_hovered = self.full_button.collidepoint(mouse_pos)
        if self.is_fullscreen:
            full_bg = (59, 130, 246)      # Blue-600 when active
            full_text_col = (255, 255, 255)
        else:
            full_bg = (55, 65, 81) if is_full_hovered else (31, 41, 55)
            full_text_col = (243, 244, 246) if is_full_hovered else (156, 163, 175)
            
        pygame.draw.rect(surf, full_bg, self.full_button, border_radius=6)
        pygame.draw.rect(surf, (255, 255, 255) if self.is_fullscreen else (75, 85, 99), self.full_button, width=1 if not self.is_fullscreen else 2, border_radius=6)
        
        full_text = self.font.render("Full", True, full_text_col)
        surf.blit(full_text, full_text.get_rect(center=self.full_button.center))
        
        # 7. Draw Color Buttons
        color_label = self.font.render("Color:", True, (243, 244, 246))
        surf.blit(color_label, (int(415 * scale), ui_y_offset + int(22 * scale)))
        
        for color_name, rect in self.color_buttons.items():
            is_selected = (self.selected_color == color_name)
            is_hovered = rect.collidepoint(mouse_pos)
            
            if is_selected:
                if color_name == 'rainbow':
                    bg_color = (124, 58, 237)  # Violet-600
                elif color_name == 'red':
                    bg_color = (220, 38, 38)   # Red-600
                elif color_name == 'blue':
                    bg_color = (37, 99, 235)   # Blue-600
                else:  # white
                    bg_color = (243, 244, 246) # Gray-100
                text_color = (17, 24, 39) if color_name == 'white' else (255, 255, 255)
            else:
                if is_hovered:
                    bg_color = (55, 65, 81)    # Gray-700
                    text_color = (243, 244, 246)
                else:
                    bg_color = (31, 41, 55)    # Gray-800
                    text_color = (156, 163, 175)
            
            pygame.draw.rect(surf, bg_color, rect, border_radius=6)
            
            # Draw borders
            if is_selected:
                pygame.draw.rect(surf, (255, 255, 255), rect, width=2, border_radius=6)
            elif is_hovered:
                pygame.draw.rect(surf, (107, 114, 128), rect, width=1, border_radius=6)
            else:
                pygame.draw.rect(surf, (75, 85, 99), rect, width=1, border_radius=6)
                
            display_name = "Rainbow" if color_name == 'rainbow' else color_name.capitalize()
            btn_text = self.font.render(display_name, True, text_color)
            surf.blit(btn_text, btn_text.get_rect(center=rect.center))
            
        # 8. Draw Reset Button
        clear_hovered = self.clear_button.collidepoint(mouse_pos)
        if clear_hovered:
            clear_bg = (220, 38, 38)       # Red-600
            clear_border = (248, 113, 113) # Red-400
        else:
            clear_bg = (31, 41, 55)        # Gray-800
            clear_border = (239, 68, 68)   # Red-500 outline
            
        pygame.draw.rect(surf, clear_bg, self.clear_button, border_radius=6)
        pygame.draw.rect(surf, clear_border, self.clear_button, width=1, border_radius=6)
        
        clear_text = self.font.render("Reset", True, (255, 255, 255))
        surf.blit(clear_text, clear_text.get_rect(center=self.clear_button.center))
        
    def draw_ui_gpu(self, ui_surface):
        """Draw the 2D Pygame UI surface onto the OpenGL viewport as a full-screen quad."""
        # Convert Pygame surface to OpenGL texture
        texture_data = pygame.image.tostring(ui_surface, "RGBA", False)
        
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_DEPTH_TEST)  # Temporarily disable depth test for 2D UI Overlay overlay
        glDisable(GL_LIGHTING)
        glDisable(GL_COLOR_MATERIAL)
        
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width, self.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
        
        # Establish simple 2D view mapping
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        # Render billboard texture
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0); glVertex2f(0, 0)
        glTexCoord2f(1.0, 0.0); glVertex2f(self.width, 0)
        glTexCoord2f(1.0, 1.0); glVertex2f(self.width, self.height)
        glTexCoord2f(0.0, 1.0); glVertex2f(0, self.height)
        glEnd()
        
        # Restore OpenGL state
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_DEPTH_TEST)  # Re-enable depth test for 3D render pipeline
        glDeleteTextures([tex_id])
        
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        
    def init_opengl_resources(self):
        """Initialize all GPU/OpenGL resources (shaders and display lists) under the current context."""
        self.init_shaders()
        self.init_display_lists()

    def init_display_lists(self):
        """Compile display lists for drawing unit tetrahedrons to optimize CPU-GPU throughput."""
        self.lit_list = glGenLists(1)
        glNewList(self.lit_list, GL_COMPILE)
        self.draw_unit_tetrahedron_lit_raw()
        glEndList()

        self.flat_list = glGenLists(1)
        glNewList(self.flat_list, GL_COMPILE)
        self.draw_unit_tetrahedron_flat_raw()
        glEndList()

    def draw_unit_tetrahedron_lit_raw(self):
        """Draw a lit unit tetrahedron with hardcoded, precomputed normals aligned with shader."""
        v0 = (1.0, 1.0, -1.0)
        v1 = (1.0, -1.0, 1.0)
        v2 = (-1.0, 1.0, 1.0)
        v3 = (-1.0, -1.0, -1.0)
        
        inv_sqrt3 = 0.5773502691896257
        
        glBegin(GL_TRIANGLES)
        
        # Face 0 (v0, v2, v1) -> Normal: (inv_sqrt3, inv_sqrt3, inv_sqrt3)
        glNormal3f(inv_sqrt3, inv_sqrt3, inv_sqrt3)
        glVertex3f(*v0); glVertex3f(*v2); glVertex3f(*v1)
        
        # Face 1 (v0, v3, v2) -> Normal: (-inv_sqrt3, inv_sqrt3, -inv_sqrt3)
        glNormal3f(-inv_sqrt3, inv_sqrt3, -inv_sqrt3)
        glVertex3f(*v0); glVertex3f(*v3); glVertex3f(*v2)
        
        # Face 2 (v0, v1, v3) -> Normal: (inv_sqrt3, -inv_sqrt3, -inv_sqrt3)
        glNormal3f(inv_sqrt3, -inv_sqrt3, -inv_sqrt3)
        glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v3)
        
        # Face 3 (v1, v2, v3) -> Normal: (-inv_sqrt3, -inv_sqrt3, inv_sqrt3)
        glNormal3f(-inv_sqrt3, -inv_sqrt3, inv_sqrt3)
        glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3)
        
        glEnd()

    def draw_unit_tetrahedron_flat_raw(self):
        """Draw a flat unit tetrahedron for shadow casting aligned with shader."""
        v0 = (1.0, 1.0, -1.0)
        v1 = (1.0, -1.0, 1.0)
        v2 = (-1.0, 1.0, 1.0)
        v3 = (-1.0, -1.0, -1.0)
        
        glBegin(GL_TRIANGLES)
        glVertex3f(*v0); glVertex3f(*v2); glVertex3f(*v1)
        glVertex3f(*v0); glVertex3f(*v3); glVertex3f(*v2)
        glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v3)
        glVertex3f(*v1); glVertex3f(*v2); glVertex3f(*v3)
        glEnd()

    def init_shaders(self):
        """Compile and link GLSL shader program for GPU Raymarching."""
        vertex_shader_src = """
        #version 120
        void main() {
            gl_Position = vec4(gl_Vertex.xyz, 1.0);
        }
        """
        
        fragment_shader_src = """
        #version 120
        uniform vec2 u_resolution;
        uniform mat3 u_rotation;
        uniform int u_iterations;
        uniform int u_color_mode;
        uniform float u_hover_y;
        
        float deSierpinski(vec3 p, int iterations) {
            float scale = 2.0;
            float offset = 1.3;
            for (int n = 0; n < iterations; n++) {
                if (p.x + p.y < 0.0) p.xy = -p.yx;
                if (p.x + p.z < 0.0) p.xz = -p.zx;
                if (p.y + p.z < 0.0) p.yz = -p.zy;
                p = p * scale - vec3(offset) * (scale - 1.0);
            }
            float md = max(max(p.x + p.y + p.z, p.x - p.y - p.z),
                           max(-p.x + p.y - p.z, -p.x - p.y + p.z));
            return (md - offset) / 1.7320508 * pow(scale, -float(iterations));
        }
        
        vec2 map(vec3 p) {
            float d_plane = p.y - (-1.2);
            float d_tet = deSierpinski(p - vec3(0.0, u_hover_y, 0.0), u_iterations);
            if (d_plane < d_tet) {
                return vec2(d_plane, 1.0);
            } else {
                return vec2(d_tet, 2.0);
            }
        }
        
        vec3 getNormal(vec3 p) {
            vec2 eps = vec2(0.0005, 0.0);
            float d = map(p).x;
            vec3 n = d - vec3(
                map(p - eps.xyy).x,
                map(p - eps.yxy).x,
                map(p - eps.yyx).x
            );
            return normalize(n);
        }
        
        float shadow(vec3 ro, vec3 rd, float mint, float maxt, float k) {
            float res = 1.0;
            float t = mint;
            for (int i = 0; i < 40; i++) {
                float h = map(ro + rd * t).x;
                if (h < 0.001) {
                    return 0.0;
                }
                res = min(res, k * h / t);
                t += clamp(h, 0.01, 0.2);
                if (t > maxt) break;
            }
            return clamp(res, 0.0, 1.0);
        }
        
        vec3 getPlaneColor(vec3 p) {
            float size = 0.5;
            float f = mod(floor(p.x / size) + floor(p.z / size), 2.0);
            if (f < 0.5) {
                return vec3(0.12, 0.16, 0.23);
            } else {
                return vec3(0.20, 0.25, 0.33);
            }
        }
        
        vec3 getTetrahedronColor(vec3 p) {
            if (u_color_mode == 0) {
                vec3 n = clamp((p - vec3(0.0, u_hover_y, 0.0) + vec3(1.3)) / 2.6, 0.0, 1.0);
                return n;
            } else if (u_color_mode == 1) {
                return vec3(0.937, 0.267, 0.267);
            } else if (u_color_mode == 2) {
                return vec3(0.231, 0.510, 0.965);
            } else {
                return vec3(0.953, 0.957, 0.965);
            }
        }
        
        vec3 raymarch(vec3 ro, vec3 rd, out vec2 hit_info) {
            float t = 0.0;
            float max_t = 15.0;
            vec2 res = vec2(-1.0, 0.0);
            for (int i = 0; i < 120; i++) {
                vec3 p = ro + rd * t;
                res = map(p);
                if (res.x < 0.0005 || t > max_t) {
                    break;
                }
                t += res.x;
            }
            if (t > max_t) {
                res.y = 0.0;
            }
            hit_info = vec2(t, res.y);
            return ro + rd * t;
        }
        
        vec3 shade(vec3 p, vec3 rd, vec2 hit) {
            if (hit.y == 0.0) {
                return vec3(0.04, 0.05, 0.06);
            }
            vec3 n = getNormal(p);
            vec3 col = vec3(0.0);
            if (hit.y == 1.0) {
                col = getPlaneColor(p);
            } else {
                col = getTetrahedronColor(p);
            }
            vec3 light_dir = normalize(vec3(1.0, 1.5, -1.0));
            float diff = max(0.0, dot(n, light_dir));
            float sh = shadow(p + n * 0.005, light_dir, 0.01, 6.0, 12.0);
            float amb = 0.2;
            float lighting = amb + diff * 0.8 * sh;
            float fog = exp(-0.15 * hit.x);
            vec3 final_color = col * lighting;
            return mix(vec3(0.04, 0.05, 0.06), final_color, fog);
        }
        
        void main() {
            vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
            vec3 ro = vec3(0.0, 0.0, -5.0);
            vec3 rd = normalize(vec3(uv, 1.0));
            
            // Rotate camera view
            ro = u_rotation * ro;
            rd = u_rotation * rd;
            
            vec2 hit;
            vec3 p = raymarch(ro, rd, hit);
            vec3 col = shade(p, rd, hit);
            
            gl_FragColor = vec4(col, 1.0);
        }
        """
        
        vs = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vs, vertex_shader_src)
        glCompileShader(vs)
        if not glGetShaderiv(vs, GL_COMPILE_STATUS):
            raise RuntimeError(glGetShaderInfoLog(vs).decode())
            
        fs = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(fs, fragment_shader_src)
        glCompileShader(fs)
        if not glGetShaderiv(fs, GL_COMPILE_STATUS):
            raise RuntimeError(glGetShaderInfoLog(fs).decode())
            
        self.shader_program = glCreateProgram()
        glAttachShader(self.shader_program, vs)
        glAttachShader(self.shader_program, fs)
        glLinkProgram(self.shader_program)
        if not glGetProgramiv(self.shader_program, GL_LINK_STATUS):
            raise RuntimeError(glGetProgramInfoLog(self.shader_program).decode())
            
        self.u_resolution_loc = glGetUniformLocation(self.shader_program, "u_resolution")
        self.u_rotation_loc = glGetUniformLocation(self.shader_program, "u_rotation")
        self.u_iterations_loc = glGetUniformLocation(self.shader_program, "u_iterations")
        self.u_color_mode_loc = glGetUniformLocation(self.shader_program, "u_color_mode")
        self.u_hover_y_loc = glGetUniformLocation(self.shader_program, "u_hover_y")

    def get_rotation_matrix(self, yaw_degrees, pitch_degrees):
        """Construct a 3D rotation matrix for yaw (around Y) and pitch (around X) to keep camera above the floor."""
        yaw = math.radians(yaw_degrees)
        pitch = math.radians(pitch_degrees)
        
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)
        
        # Column-major flat array for glUniformMatrix3fv
        r00 = cos_y
        r10 = 0.0
        r20 = -sin_y
        
        r01 = sin_y * sin_p
        r11 = cos_p
        r21 = cos_y * sin_p
        
        r02 = sin_y * cos_p
        r12 = -sin_p
        r22 = cos_y * cos_p
        
        return [r00, r10, r20, r01, r11, r21, r02, r12, r22]

    def draw_physics_scene(self, yaw_degrees):
        """Draw the falling physics pieces, their floor shadows, and the floor plane."""
        # Calculate average position of the falling pieces to track them with the camera
        avg_x = 0.0
        avg_y = 0.0
        avg_z = 0.0
        if len(self.physics_pieces) > 0:
            avg_x = sum(p.pos[0] for p in self.physics_pieces) / len(self.physics_pieces)
            avg_y = sum(p.pos[1] for p in self.physics_pieces) / len(self.physics_pieces)
            avg_z = sum(p.pos[2] for p in self.physics_pieces) / len(self.physics_pieces)
            
        # Define look-at target with smooth offset decay to match raymarching hover
        target_x = avg_x
        target_y = avg_y - self.camera_offset_y
        target_z = avg_z

        # Calculate pitch and clamp it to keep camera eye Y-coordinate above plane_y + 0.3 = -0.9
        # eye_y = target_y + 5 * sin(pitch) >= -0.9 => sin(pitch) >= (-0.9 - target_y) / 5.0
        pitch = 15.0 + 10.0 * math.sin(self.hover_angle)
        min_sin_p = (-0.9 - target_y) / 5.0
        if min_sin_p > 0.0:
            min_pitch = math.degrees(math.asin(min(1.0, min_sin_p)))
            pitch = max(pitch, min_pitch)
            
        # Construct rotation matrix with the adjusted pitch
        rot_matrix = self.get_rotation_matrix(yaw_degrees, pitch)

        # Calculate eye coordinates matching the raymarching camera
        # eye = target + R * (0, 0, -5)
        offset_x = -5.0 * rot_matrix[6]
        offset_y = -5.0 * rot_matrix[7]
        offset_z = -5.0 * rot_matrix[8]

        eye_x = target_x + offset_x
        eye_y = target_y + offset_y
        eye_z = target_z + offset_z

        # Up vector is R * (0, 1, 0)
        up_x = rot_matrix[3]
        up_y = rot_matrix[4]
        up_z = rot_matrix[5]

        # 1. Clear background
        glClearColor(0.04, 0.05, 0.06, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # 2. Setup 3D matrix context
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        fov_y = 2.0 * math.degrees(math.atan(0.5))
        gluPerspective(fov_y, float(self.width) / float(self.height), 0.1, 20.0)
        
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(eye_x, eye_y, eye_z, target_x, target_y, target_z, up_x, up_y, up_z)
        
        # 3. Setup hardware lighting
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_NORMALIZE)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        # Disable default global ambient light to match shader's ambient term of 0.2
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (0.0, 0.0, 0.0, 1.0))
        
        glLightfv(GL_LIGHT0, GL_POSITION, (1.0, 1.5, -1.0, 0.0))  # matching light vector
        glLightfv(GL_LIGHT0, GL_AMBIENT, (0.2, 0.2, 0.2, 1.0))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.8, 0.8, 0.8, 1.0))
        glLightfv(GL_LIGHT0, GL_SPECULAR, (0.0, 0.0, 0.0, 1.0))
        
        # Disable specular highlights on materials to match flat shading in shader
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.0, 0.0, 0.0, 1.0))
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 0.0)
        
        # 4. Draw the checkered plane
        self.draw_checkered_plane_poly()
        
        # 5. Render projected shadows for each piece
        shadow_y = -1.19
        lx, ly, lz = 1.0, 1.5, -1.0
        len_l = math.sqrt(lx**2 + ly**2 + lz**2)
        lx /= len_l; ly /= len_l; lz /= len_l
        
        shadow_matrix = [
            ly, 0.0, 0.0, 0.0,
            -lx, 0.0, -lz, 0.0,
            0.0, 0.0, ly, 0.0,
            lx * shadow_y, ly * shadow_y, lz * shadow_y, ly
        ]
        
        glPushMatrix()
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.05, 0.05, 0.08, 0.6)
        
        glMultMatrixf(shadow_matrix)
        for p in self.physics_pieces:
            glPushMatrix()
            glTranslatef(p.pos[0], p.pos[1], p.pos[2])
            glRotatef(p.rot_angle, p.rot_axis[0], p.rot_axis[1], p.rot_axis[2])
            glScalef(self.physics_piece_scale, self.physics_piece_scale, self.physics_piece_scale)
            glCallList(self.flat_list)
            glPopMatrix()
        glPopMatrix()
        
        glDisable(GL_BLEND)
        glEnable(GL_LIGHTING)
        
        # 6. Render the real physical pieces
        for p in self.physics_pieces:
            glPushMatrix()
            glTranslatef(p.pos[0], p.pos[1], p.pos[2])
            glRotatef(p.rot_angle, p.rot_axis[0], p.rot_axis[1], p.rot_axis[2])
            glScalef(self.physics_piece_scale, self.physics_piece_scale, self.physics_piece_scale)
            glColor3f(p.color[0], p.color[1], p.color[2])
            glCallList(self.lit_list)
            glPopMatrix()
            
        # Restore state
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

    def draw_checkered_plane_poly(self):
        """Draw checkered plane matching the raymarching coordinates."""
        glBegin(GL_QUADS)
        glNormal3f(0.0, 1.0, 0.0)
        
        grid_size = 30
        square_size = 0.5
        half_len = (grid_size * square_size) / 2.0
        plane_y = -1.2
        
        for i in range(grid_size):
            for j in range(grid_size):
                x1 = -half_len + i * square_size
                x2 = x1 + square_size
                z1 = -half_len + j * square_size
                z2 = z1 + square_size
                
                if (i + j) % 2 == 0:
                    glColor3f(0.12, 0.16, 0.23)
                else:
                    glColor3f(0.20, 0.25, 0.33)
                    
                glVertex3f(x1, plane_y, z1)
                glVertex3f(x1, plane_y, z2)
                glVertex3f(x2, plane_y, z2)
                glVertex3f(x2, plane_y, z1)
        glEnd()

    def draw_unit_tetrahedron_flat(self):
        """Draw a flat unit tetrahedron for shadow casting."""
        glBegin(GL_TRIANGLES)
        v0 = (1.0, 1.0, 1.0)
        v1 = (-1.0, -1.0, 1.0)
        v2 = (-1.0, 1.0, -1.0)
        v3 = (1.0, -1.0, -1.0)
        
        glVertex3f(*v0); glVertex3f(*v1); glVertex3f(*v2)
        glVertex3f(*v0); glVertex3f(*v2); glVertex3f(*v3)
        glVertex3f(*v0); glVertex3f(*v3); glVertex3f(*v1)
        glVertex3f(*v1); glVertex3f(*v3); glVertex3f(*v2)
        glEnd()

    def draw_unit_tetrahedron_lit(self):
        """Draw a lit unit tetrahedron with normals."""
        glBegin(GL_TRIANGLES)
        v0 = (1.0, 1.0, 1.0)
        v1 = (-1.0, -1.0, 1.0)
        v2 = (-1.0, 1.0, -1.0)
        v3 = (1.0, -1.0, -1.0)
        
        def draw_face(p0, p1, p2):
            ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            nx = uy * vz - uz * vy
            ny = uz * vx - ux * vz
            nz = ux * vy - uy * vx
            l = math.sqrt(nx**2 + ny**2 + nz**2)
            if l > 0:
                nx /= l; ny /= l; nz /= l
            glNormal3f(nx, ny, nz)
            glVertex3f(*p0)
            glVertex3f(*p1)
            glVertex3f(*p2)
            
        draw_face(v0, v1, v2)
        draw_face(v0, v2, v3)
        draw_face(v0, v3, v1)
        draw_face(v1, v3, v2)
        glEnd()

    def get_sub_tetrahedrons(self, v0, v1, v2, v3, depth):
        """Recursively find the positions of all sub-tetrahedrons at a given depth."""
        if depth == 0:
            center = (
                (v0[0] + v1[0] + v2[0] + v3[0]) / 4.0,
                (v0[1] + v1[1] + v2[1] + v3[1]) / 4.0,
                (v0[2] + v1[2] + v2[2] + v3[2]) / 4.0
            )
            return [center]
            
        m01 = ((v0[0] + v1[0]) / 2.0, (v0[1] + v1[1]) / 2.0, (v0[2] + v1[2]) / 2.0)
        m02 = ((v0[0] + v2[0]) / 2.0, (v0[1] + v2[1]) / 2.0, (v0[2] + v2[2]) / 2.0)
        m03 = ((v0[0] + v3[0]) / 2.0, (v0[1] + v3[1]) / 2.0, (v0[2] + v3[2]) / 2.0)
        m12 = ((v1[0] + v2[0]) / 2.0, (v1[1] + v2[1]) / 2.0, (v1[2] + v2[2]) / 2.0)
        m13 = ((v1[0] + v3[0]) / 2.0, (v1[1] + v3[1]) / 2.0, (v1[2] + v3[2]) / 2.0)
        m23 = ((v2[0] + v3[0]) / 2.0, (v2[1] + v3[1]) / 2.0, (v2[2] + v3[2]) / 2.0)
        
        t0 = self.get_sub_tetrahedrons(v0, m01, m02, m03, depth - 1)
        t1 = self.get_sub_tetrahedrons(m01, v1, m12, m13, depth - 1)
        t2 = self.get_sub_tetrahedrons(m02, m12, v2, m23, depth - 1)
        t3 = self.get_sub_tetrahedrons(m03, m13, m23, v3, depth - 1)
        
        return t0 + t1 + t2 + t3

    def init_physics_pieces(self):
        """Transition to falling state, generating falling physical sub-tetrahedrons."""
        sim_depth = self.iterations
        self.physics_piece_scale = 1.3 * (2.0 ** -sim_depth)
        radius = self.physics_piece_scale * 1.2
        
        size = 1.3
        v0 = (size, size, -size)
        v1 = (size, -size, size)
        v2 = (-size, size, size)
        v3 = (-size, -size, -size)
        
        centers = self.get_sub_tetrahedrons(v0, v1, v2, v3, sim_depth)
        
        pitch = 15.0 + 10.0 * math.sin(self.hover_angle)
        rot_matrix = self.get_rotation_matrix(self.rotation_angle, pitch)
        
        current_hover_y = 0.45 + 0.18 * math.sin(self.hover_angle)
        
        self.physics_pieces = []
        omega = math.radians(1.0)
        
        for center in centers:
            rot_c = self.multiply_mat3_vec3(rot_matrix, center)
            pos = [rot_c[0], rot_c[1] + current_hover_y, rot_c[2]]
            
            vx = -omega * rot_c[2] * 60.0
            vy = 0.0
            vz = omega * rot_c[0] * 60.0
            
            dist_from_axis = math.sqrt(rot_c[0]**2 + rot_c[2]**2)
            if dist_from_axis > 0:
                push_dir = [rot_c[0] / dist_from_axis, 0.0, rot_c[2] / dist_from_axis]
                blast = 0.5 + random.random() * 0.5
                vx += push_dir[0] * blast
                vz += push_dir[2] * blast
            
            vy += (random.random() - 0.2) * 0.5
            
            colors = self.get_colors_for_face_3d_pos(center)
            rgb_color = self.parse_color_float(colors)
            
            rot_axis = [random.random(), random.random(), random.random()]
            l = math.sqrt(rot_axis[0]**2 + rot_axis[1]**2 + rot_axis[2]**2)
            if l > 0:
                rot_axis = [rot_axis[0]/l, rot_axis[1]/l, rot_axis[2]/l]
            rot_vel = 180.0 + random.random() * 360.0
            
            self.physics_pieces.append(
                SierpinskiPhysicsPiece(pos, [vx, vy, vz], rgb_color, rot_axis, rot_vel, radius)
            )
            
        self.simulation_state = 'falling'
        self.stable_frames = 0
        self.camera_offset_y = current_hover_y

    def get_colors_for_face_3d_pos(self, v):
        """Generate a single color for a point in 3D space based on current color mode."""
        if self.color_mode == 'rainbow':
            size = 1.3
            nx = (v[0] + size) / (2.0 * size)
            ny = (v[1] + size) / (2.0 * size)
            nz = (v[2] + size) / (2.0 * size)
            nx = max(0.0, min(1.0, nx))
            ny = max(0.0, min(1.0, ny))
            nz = max(0.0, min(1.0, nz))
            
            r = int(nx * 255)
            g = int(ny * 255)
            b = int(nz * 255)
            return f'#{r:02x}{g:02x}{b:02x}'
        elif self.color_mode == 'red':
            return '#ef4444'
        elif self.color_mode == 'blue':
            return '#3b82f6'
        else:
            return '#f3f4f6'

    def multiply_mat3_vec3(self, m, v):
        """Multiply a column-major 3x3 matrix by a 3D vector."""
        x = m[0] * v[0] + m[3] * v[1] + m[6] * v[2]
        y = m[1] * v[0] + m[4] * v[1] + m[7] * v[2]
        z = m[2] * v[0] + m[5] * v[1] + m[8] * v[2]
        return [x, y, z]

    def update_physics(self):
        """Update rigid-body physics for falling tetrahedrons."""
        dt = 1.0 / 60.0
        g = 3.5
        restitution = 0.5
        friction = 0.8
        air_damping = 0.01
        plane_y = -1.2
        
        # Smoothly decay the camera target offset towards 0.0 to transition target to centroid
        self.camera_offset_y *= 0.96
        if self.camera_offset_y < 0.001:
            self.camera_offset_y = 0.0
            
        num_pieces = len(self.physics_pieces)
        
        for p in self.physics_pieces:
            p.vel[1] -= g * dt
            p.vel[0] *= (1.0 - air_damping)
            p.vel[1] *= (1.0 - air_damping)
            p.vel[2] *= (1.0 - air_damping)
            
            p.pos[0] += p.vel[0] * dt
            p.pos[1] += p.vel[1] * dt
            p.pos[2] += p.vel[2] * dt
            
            p.rot_angle = (p.rot_angle + p.rot_vel * dt) % 360.0
            
            if p.pos[1] - p.radius < plane_y:
                p.pos[1] = plane_y + p.radius
                p.vel[1] = -p.vel[1] * restitution
                p.vel[0] *= friction
                p.vel[2] *= friction
                p.rot_vel *= 0.95
                
                # Add horizontal dispersion when many pieces collide with the floor (bypass pairwise collisions)
                if num_pieces > 256:
                    disp = 0.4
                    p.vel[0] += (random.random() - 0.5) * disp
                    p.vel[2] += (random.random() - 0.5) * disp
                
        # Only perform pairwise sphere-sphere collision checking when count is low
        if num_pieces <= 256:
            for i in range(num_pieces):
                p_i = self.physics_pieces[i]
                for j in range(i + 1, num_pieces):
                    p_j = self.physics_pieces[j]
                    
                    dx = p_j.pos[0] - p_i.pos[0]
                    dy = p_j.pos[1] - p_i.pos[1]
                    dz = p_j.pos[2] - p_i.pos[2]
                    dist_sq = dx**2 + dy**2 + dz**2
                    
                    sum_radii = p_i.radius + p_j.radius
                    if dist_sq < sum_radii**2:
                        dist = math.sqrt(dist_sq)
                        if dist == 0.0:
                            dist = 0.001
                            dx = 0.001
                        nx = dx / dist
                        ny = dy / dist
                        nz = dz / dist
                        
                        pen = sum_radii - dist
                        p_i.pos[0] -= nx * pen * 0.5
                        p_i.pos[1] -= ny * pen * 0.5
                        p_i.pos[2] -= nz * pen * 0.5
                        
                        p_j.pos[0] += nx * pen * 0.5
                        p_j.pos[1] += ny * pen * 0.5
                        p_j.pos[2] += nz * pen * 0.5
                        
                        rvx = p_j.vel[0] - p_i.vel[0]
                        rvy = p_j.vel[1] - p_i.vel[1]
                        rvz = p_j.vel[2] - p_i.vel[2]
                        vel_along_normal = rvx * nx + rvy * ny + rvz * nz
                        
                        if vel_along_normal < 0.0:
                            impulse = -(1.0 + restitution) * vel_along_normal / 2.0
                            p_i.vel[0] -= nx * impulse
                            p_i.vel[1] -= ny * impulse
                            p_i.vel[2] -= nz * impulse
                            
                            p_j.vel[0] += nx * impulse
                            p_j.vel[1] += ny * impulse
                            p_j.vel[2] += nz * impulse
                            
                            p_i.rot_vel, p_j.rot_vel = p_j.rot_vel * 0.8, p_i.rot_vel * 0.8
                            
        stable = True
        for p in self.physics_pieces:
            speed = math.sqrt(p.vel[0]**2 + p.vel[1]**2 + p.vel[2]**2)
            if speed > 0.08 or abs(p.pos[1] - (plane_y + p.radius)) > 0.1:
                stable = False
                break
                
        if stable:
            self.stable_frames += 1
        else:
            self.stable_frames = 0

    def parse_color(self, color):
        """Parse hex color string to RGB tuple (0-255 range)."""
        hex_val = color.lstrip('#')
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
        return (r, g, b)
        
    def parse_color_float(self, color):
        """Parse hex color string to RGB float tuple (0.0-1.0 range)."""
        r, g, b = self.parse_color(color)
        return r / 255.0, g / 255.0, b / 255.0
        
    def generate_sierpinski_geometry(self, p1, p2, p3, depth):
        """Generate Sierpinski triangle geometry recursively (CPU path only)."""
        if depth == 0:
            vertices = [
                (p1[0], p1[1]),
                (p2[0], p2[1]),
                (p3[0], p3[1])
            ]
            colors = self.get_colors_for_triangle(p1, p2, p3)
            return vertices, colors
            
        m1 = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        m2 = ((p2[0] + p3[0]) / 2.0, (p2[1] + p3[1]) / 2.0)
        m3 = ((p3[0] + p1[0]) / 2.0, (p3[1] + p1[1]) / 2.0)
        
        v1, c1 = self.generate_sierpinski_geometry(p1, m1, m3, depth - 1)
        v2, c2 = self.generate_sierpinski_geometry(m1, p2, m2, depth - 1)
        v3, c3 = self.generate_sierpinski_geometry(m3, m2, p3, depth - 1)
        
        return v1 + v2 + v3, c1 + c2 + c3
        

        


    def get_colors_for_triangle(self, p1, p2, p3):
        """Generate colors for a triangle based on mode."""
        if self.color_mode == 'rainbow':
            # Calculate main triangle bounds dynamically to match the current resolution scale
            scale = self.height / 600.0
            margin_y_top = int(80 * scale)
            margin_y_bottom = int(20 * scale)
            ui_height = int(60 * scale)
            draw_height = self.height - ui_height - margin_y_top - margin_y_bottom
            base_width = draw_height * (2.0 / math.sqrt(3))
            center_x = self.width / 2.0
            center_y_bottom = self.height - ui_height - margin_y_bottom
            
            p1_main = (center_x - base_width / 2.0, center_y_bottom)
            p2_main = (center_x + base_width / 2.0, center_y_bottom)
            p3_main = (center_x, center_y_bottom - draw_height)
            
            res = []
            for p in (p1, p2, p3):
                # Normalized coordinates within bounding area
                nx = (p[0] - p1_main[0]) / (p2_main[0] - p1_main[0])
                ny = (p[1] - p3_main[1]) / (p1_main[1] - p3_main[1])
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                
                # Bounded distances to three corners of a unit triangle
                dist_bl = math.sqrt(nx**2 + (1.0 - ny)**2)
                dist_br = math.sqrt((1.0 - nx)**2 + (1.0 - ny)**2)
                dist_top = math.sqrt((0.5 - nx)**2 + ny**2)
                
                # Weight calculations
                w_red = max(0.0, 1.0 - dist_bl / 1.2)
                w_blue = max(0.0, 1.0 - dist_br / 1.2)
                w_green = max(0.0, 1.0 - dist_top / 1.2)
                
                total = w_red + w_green + w_blue
                if total > 0:
                    r = int((w_red / total) * 255)
                    g = int((w_green / total) * 255)
                    b = int((w_blue / total) * 255)
                else:
                    r, g, b = 255, 255, 255
                    
                res.append(f'#{r:02x}{g:02x}{b:02x}')
            return res
        elif self.color_mode == 'red':
            return ['#ef4444', '#ef4444', '#ef4444']
        elif self.color_mode == 'blue':
            return ['#3b82f6', '#3b82f6', '#3b82f6']
        else:  # white
            return ['#f3f4f6', '#f3f4f6', '#f3f4f6']


def main():
    """Main function to run the application."""
    app = SierpinskiTriangleApp()
    app.create_controls()
    
    running = True
    clock = pygame.time.Clock()
    
    while running:
        # Auto-rotate increment (1 degree per frame)
        if app.auto_rotate:
            app.rotation_angle = (app.rotation_angle + 1.0) % 360.0
            
        app.hover_angle = (app.hover_angle + 0.03) % (2.0 * math.pi)
            
        # Determine maximum iterations based on mode
        max_iter = 6
        app.iterations = max(1, min(max_iter, app.iterations))
        
        # Calculate dynamic bounds for rendering (2D CPU path)
        scale = app.height / 600.0
        margin_y_top = int(80 * scale)
        margin_y_bottom = int(20 * scale)
        ui_height = int(60 * scale)
        draw_height = app.height - ui_height - margin_y_top - margin_y_bottom
        base_width = draw_height * (2.0 / math.sqrt(3))
        center_x = app.width / 2.0
        center_y_bottom = app.height - ui_height - margin_y_bottom
        p1 = (center_x - base_width / 2.0, center_y_bottom)
        p2 = (center_x + base_width / 2.0, center_y_bottom)
        p3 = (center_x, center_y_bottom - draw_height)
        
        # Check cache and regenerate geometry if settings changed (CPU path only)
        if app.render_mode == 'cpu':
            cache_key = (app.iterations, app.color_mode, 'cpu')
            if cache_key != app.geom_cache_key:
                app.cached_vertices, app.cached_colors = app.generate_sierpinski_geometry(p1, p2, p3, app.iterations)
                app.geom_cache_key = cache_key
        else:
            # Update GPU simulation state loop
            if app.simulation_state == 'hover':
                app.hover_frames += 1
                if app.hover_frames >= 300:  # 5 seconds at 60 FPS
                    app.init_physics_pieces()
            elif app.simulation_state == 'falling':
                app.update_physics()
                if app.stable_frames >= 120:  # 2 seconds stable
                    app.simulation_state = 'hover'
                    app.hover_frames = 0
                    app.stable_frames = 0
                    app.physics_pieces = []
            
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
                
            elif event.type == VIDEORESIZE:
                # Update window dimensions on drag resizing
                app.width = event.w
                app.height = event.h
                
                # Re-create display mode to update context
                if app.render_mode == 'gpu':
                    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
                    flags = pygame.OPENGL | pygame.DOUBLEBUF
                    if app.is_fullscreen:
                        flags |= pygame.FULLSCREEN
                    else:
                        flags |= pygame.RESIZABLE
                    app.screen = pygame.display.set_mode((app.width, app.height), flags)
                    
                    # Reconfigure OpenGL viewport and projection
                    glViewport(0, 0, app.width, app.height)
                    glClearColor(0.04, 0.05, 0.06, 1.0)
                    app.init_opengl_resources()
                else:
                    flags = pygame.FULLSCREEN if app.is_fullscreen else pygame.RESIZABLE
                    app.screen = pygame.display.set_mode((app.width, app.height), flags)
                    
                # Rebuild controls and font configurations for the new resolution size
                app.create_controls()
                app.init_fonts()
                app.geom_cache_key = None
                
            elif event.type == KEYDOWN:
                if event.key in (K_f, K_F11):
                    app.toggle_fullscreen()
                elif event.key == K_r:
                    app.auto_rotate = not app.auto_rotate
                elif event.key == K_ESCAPE:
                    if app.is_fullscreen:
                        app.toggle_fullscreen()
                        
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                # 1. Check render mode switches (CPU / GPU)
                for mode, rect in app.mode_buttons.items():
                    if rect.collidepoint(event.pos):
                        app.set_render_mode(mode)
                        
                # 2. Check rotate and fullscreen buttons
                if app.rotate_button.collidepoint(event.pos):
                    app.auto_rotate = not app.auto_rotate
                elif app.full_button.collidepoint(event.pos):
                    app.toggle_fullscreen()
                    
                # 3. Check color buttons
                for color, rect in app.color_buttons.items():
                    if rect.collidepoint(event.pos):
                        app.selected_color = color
                        app.on_color_change()
                        
                # 4. Check reset button
                if app.clear_button.collidepoint(event.pos):
                    app.iterations = 5
                    app.selected_color = 'rainbow'
                    app.auto_rotate = False
                    app.rotation_angle = 0.0
                    app.on_color_change()
                    app.simulation_state = 'hover'
                    app.hover_frames = 0
                    app.stable_frames = 0
                    app.physics_pieces = []
                    
                # 5. Check slider
                elif app.iter_slider.collidepoint(event.pos):
                    app.dragging_slider = True
                    x_pos = event.pos[0]
                    relative_x = max(0, min(app.iter_slider.width, x_pos - app.iter_slider.x))
                    app.iterations = int(round(1 + (relative_x / float(app.iter_slider.width)) * (max_iter - 1)))
                    
            elif event.type == MOUSEBUTTONUP and event.button == 1:
                app.dragging_slider = False
                
            elif event.type == MOUSEMOTION:
                if app.dragging_slider:
                    x_pos = event.pos[0]
                    relative_x = max(0, min(app.iter_slider.width, x_pos - app.iter_slider.x))
                    new_iter = int(round(1 + (relative_x / float(app.iter_slider.width)) * (max_iter - 1)))
                    app.iterations = new_iter
                    
        # Render the triangle
        app.draw()
        
        # Render UI controls overlay
        if app.render_mode == 'cpu':
            app.draw_ui(app.screen)
        else:
            # OpenGL UI Overlay context texturing
            ui_surface = pygame.Surface((app.width, app.height), pygame.SRCALPHA)
            app.draw_ui(ui_surface)
            app.draw_ui_gpu(ui_surface)
            
        pygame.display.flip()
        clock.tick(60)
        
    pygame.quit()


if __name__ == "__main__":
    main()
