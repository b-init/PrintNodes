#PrintNodes addon for Blender 2.80+ to take high quality screenshots of node trees
#Managed by: Binit (aka Yeetus)

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


bl_info = {
    "name" : "PrintNodes",
    "author" : "Binit",
    "description" : "Takes high quality screenshot of a node tree",
    "blender" : (3, 00, 0),
    "version" : (1, 1, 4),
    "location" : "Node Editor > Context Menu (Right Click)",
    "warning" : "",
    "category" : "Node"
}

import bpy
from bpy.types import Operator, AddonPreferences, Menu
from bpy.props import StringProperty, BoolProperty, IntProperty

import time
import os
import sys


if sys.platform == "win32":
    from .PIL_win.PIL import Image, ImageChops
elif sys.platform == "linux":
    from .PIL_linux.PIL import Image, ImageChops
elif sys.platform == "darwin":
    from .PIL_darwin.PIL import Image, ImageChops
else:
    raise RuntimeError(f"Unsupported platform '{sys.platform}'.")

Image.MAX_IMAGE_PIXELS = None # disable max resolution limit from PIL. Comes in the way of screenshotting abnormally huge trees

def MakeDirectory(): # Manage Directory for saving screenshots

    if bpy.data.filepath and bpy.context.preferences.addons[__name__].preferences.force_secondary_dir == False: 
        # save image in the place where the blendfile is saved, in a newly created subfolder (if saved and force_default_directory is set to false)
        Directory = os.path.join(os.path.split(bpy.data.filepath)[0], 'NodesShots')
        
        if os.path.isdir(Directory) == False:
            os.mkdir(Directory)
            bpy.ops.wm
    else:  
        # just use the secondary directory otherwise
        Directory = bpy.context.preferences.addons[__name__].preferences.secondary_save_dir

    return Directory


class PRTND_PT_Preferences(AddonPreferences): # setting up perferences
    bl_idname = __name__

    secondary_save_dir: StringProperty(
        name = "Secondary Directory",
        subtype = 'DIR_PATH',
        default = bpy.context.preferences.filepaths.temporary_directory,
        )

    force_secondary_dir: BoolProperty(
        name = "Always Use Secondary Directory",
        default = False,
        )

    padding_amount: IntProperty(
        name = "Padding Amount (in px)",
        default = 30,
        )

    disable_auto_crop: BoolProperty(
        name = 'Disable Auto Cropping',
        description = 'Check this if something is not working properly',
        default = False,
        )

    def draw(self, context):
        layout = self.layout
        layout.label(text = "A subfolder in the same directory as the blend file will be used to save the images.")
        layout.label(text = "Unless the file is unsaved or 'Always Use Secondary Directory' is checked.")
        layout.label(text = "In which case, the Secondary Directory will be used")
        layout.prop(self, "secondary_save_dir")
        layout.prop(self, "force_secondary_dir")
        layout.separator()
        layout.prop(self, "padding_amount")
        layout.prop(self, "disable_auto_crop")


class PRTND_MT_ContextMenu(Menu): 
    """Context Menu For Print Nodes"""
    bl_idname = "PRTND_MT_context_menu"
    bl_label = "PrintNodes"
    
    def draw(self, context):
        layout = self.layout
        layout.operator(PRTND_OT_ModalScreenshotTimer.bl_idname, text = "Take Screenshot Of Whole Tree", icon = "NODETREE")
        layout.operator(PRTND_OT_ModalScreenshotTimer.bl_idname, text = "Take Screenshot Of Selected Nodes", icon = "SELECT_SET").selection_only = True


def PrintNodesPopUp(message = "", title = "PrintNodes PopUp", icon = ""): # function to display popup message on command

    def draw(self, context):
        self.layout.label(text = message)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


class PRTND_OT_ModalScreenshotTimer(Operator): # modal operator to take parts of the whole shot every at every set interval, while not interrupting the rest of blender's functioning (for the most part)
    """Take screenshot of active node tree. Press RightClick or Esc to cancel during process."""
    bl_idname = "prtnd.modal_ss_timer"
    bl_label = "Take Tree Screenshot"

    selection_only: BoolProperty(default = False)

    _timer = None
    Xmin = Ymin = Xmax = Ymax = 0
    ix = iy = 0
    temp_name = ''
    temp_grid_level = 0
    forced_cancel = False


    def modal(self, context, event): 
        if event.type in {'RIGHTMOUSE', 'ESC'}: # force cancel
            self.forced_cancel = True
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
                  
            tree = context.space_data.edit_tree
            view = context.region.view2d
            area = bpy.context.area
            dx = area.width - 1
            dy = area.height - 1
            
            path = os.path.join(MakeDirectory(), f'Prt_y{self.iy}_x{self.ix}.png')
            bpy.ops.screen.screenshot_area(filepath=path) # take screenshot of current view as a 'tile' to be further stitched and processed

            if tree.view_center[1] > self.Ymax and tree.view_center[0] > self.Xmax: # check if already at the other corner of the tree, if yes, sucessfully terminate
                self.cancel(context)
                return {'CANCELLED'}
            
            if tree.view_center[0] > self.Xmax: # if exceeded rightmost edge, pan all the way back to leftmost edge and pan y up once to prepare for the next 'layer' of tiles
                bpy.ops.view2d.pan(deltax = -(self.ix*dx), deltay=dy)
                self.ix = 0
                self.iy += 1

            else: # just pan to the right if no other condition applies (i.e. we're somewhere in the middle of the tile strip)
                bpy.ops.view2d.pan(deltax = dx, deltay = 0)
                self.ix += 1

        return {'PASS_THROUGH'} # pass for next iteration

    def execute(self, context):

        self.temp_grid_level = context.preferences.themes[0].node_editor.grid_levels
        bpy.context.preferences.themes[0].node_editor.grid_levels = 0 # turn gridlines off, trimming empty space doesn't work otherwise

        if self.selection_only:
            nodes = context.selected_nodes # perform within the selected nodes only
        else:  
            nodes = context.space_data.edit_tree.nodes # perform within the whole tree
        tree = context.space_data.edit_tree

        self.Xmin = self.Xmax = nodes[0].location[0]
        self.Ymin = self.Ymax = nodes[0].location[1]
    

        for i in range(len(nodes)):
            loc = nodes[i].location
            locX = loc[0]
            locY = loc[1]
            
            if locX < self.Xmin:
                self.Xmin = locX
            if locY < self.Ymin:
                self.Ymin = locY

            if locX > self.Xmax:
                self.Xmax = locX
            if locY > self.Ymax:
                self.Ymax = locY

        # co-ords from node.location and tree.view_center are apparently not the same (you could say they don't co-ordinate, haha ha...) so I have to make sure I'm using the right ones 
        node = tree.nodes.new("NodeReroute")
        node.location = self.Xmax, self.Ymax
        for current_node in nodes:
            current_node.select = False
        node.select = True
        bpy.ops.wm.redraw_timer(iterations=1)
        bpy.ops.node.view_selected()
        bpy.ops.wm.redraw_timer(iterations=1)
        self.Xmax, self.Ymax = tree.view_center

        node = tree.nodes.new("NodeReroute")
        node.location = self.Xmin, self.Ymin
        for current_node in nodes:
            current_node.select = False
        node.select = True
        bpy.ops.wm.redraw_timer(iterations=1)
        bpy.ops.node.view_selected() # also align view to the (bottom-left) corner node. As an initial point for the screenshotting process
        bpy.ops.wm.redraw_timer(iterations=1)
        self.Xmin, self.Ymin = tree.view_center

        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.02, window=context.window) # add timer to begin with, for the `modal` process
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def cancel(self, context):

        if self.forced_cancel: 
            PrintNodesPopUp(message = "Process Force Cancelled", icon = "CANCEL")

        else:
            area = bpy.context.area
            StitchTiles(area.width, area.height, self.ix + 1, self.iy + 1) # being the stitching and processing process of the tiles
            PrintNodesPopUp(message = "Screenshot Saved Successfully", icon = "CHECKMARK")

        # revert all the temporary settings back to original
        context.preferences.themes[0].node_editor.grid_levels = self.temp_grid_level

        wm = context.window_manager
        wm.event_timer_remove(self._timer)


def TrimImage(img): # function to trim out empty space from the edges, leaving a padding (as defined in preferences)

    bg_clr = tuple(bpy.context.preferences.themes[0].node_editor.space.back * 255) # get the background color of the shader editor from themes and map from 0-1 to 0-255 for PIL operations
    bg_clr = tuple(map(lambda i: int(i), bg_clr)) # convert float tuple to int tuple (as Image.new(color) expectes Int tuple)

    padding = bpy.context.preferences.addons[__name__].preferences.padding_amount
    padding_tuple = (-padding, -padding, padding, padding) # to subtract padding amount from x_min, y_min and add to x_max, y_max for cropping
    
    img_w, img_h = img.size
    img_size_tuple = (img_w, img_h, img_w, img_h) # tuple of image size in format (x_min, y_min, x_max, y_max) for clamping padding amount, with some 'hacky' elements


    bg = Image.new(img.mode, img.size, bg_clr)
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()

    crop_tuple = tuple(map(lambda i, j: i + j, bbox, padding_tuple)) # offset the co-ords to leave space for padding
    crop_tuple = tuple(map(lambda i, j: max(0, min(i, j)), crop_tuple, img_size_tuple)) # clamp all values to not be outside the image (negative or greater than size of image)

    if bbox:
        return img.crop(crop_tuple)
    else:
        return img


def StitchTiles(tile_width, tile_height, num_x, num_y): # function to stitch multiple tiles to one single image

    folder_path = MakeDirectory()

    out_canvas = Image.new('RGB', (tile_width * num_x, tile_height * num_y))

    for y in range(num_y):
        for x in range(num_x):
            tile_path = os.path.join(folder_path, f'Prt_y{y}_x{x}.png')
            current_tile = Image.open(tile_path)
            out_canvas.paste(current_tile, (tile_width * x, tile_height * (num_y - (y + 1))))
            os.remove(tile_path) #remove used tiles

    if not bpy.context.preferences.addons[__name__].preferences.disable_auto_crop:
        out_canvas = TrimImage(out_canvas)

    timestamp = time.strftime("%y%m%d-%H%M%S")
    out_path = os.path.join(folder_path, f'NodeTreeShot{timestamp}.png')
    out_canvas.save(out_path)



# menu function(s)
def PrintNodes_menu_func(self, context):
    self.layout.menu(PRTND_MT_ContextMenu.bl_idname, icon="FCURVE_SNAPSHOT")

classes = (PRTND_OT_ModalScreenshotTimer, PRTND_PT_Preferences, PRTND_MT_ContextMenu, )

#addon_keymaps = []


def register():

    for current in classes:
        bpy.utils.register_class(current)

    bpy.types.NODE_MT_context_menu.append(PrintNodes_menu_func)

    # wm = bpy.context.window_manager
    # kc = wm.keyconfigs.addon
    # if kc:
    #     km = wm.keyconfigs.addon.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
    #     kmi = km.keymap_items.new(PRTND_OT_ModalScreenshotTimer.bl_idname, 'C', 'PRESS', ctrl=True, shift=True)
    #     addon_keymaps.append((km, kmi))

def unregister():

    for current in classes:
        bpy.utils.unregister_class(current)

    bpy.types.NODE_MT_context_menu.remove(PrintNodes_menu_func)

    # for km, kmi in addon_keymaps:
    #     km.keymap_items.remove(kmi)
    # addon_keymaps.clear()