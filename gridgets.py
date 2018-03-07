import logging

import colors

##############################################################################

# And first, a few constants

ARROWS = "UP DOWN LEFT RIGHT".split()
MENU = "BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4".split()

channel_colors = [
    colors.RED_HI,
    colors.AMBER_HI,
    colors.YELLOW_HI,
    colors.GREEN_HI,
    colors.SKY_HI,
    colors.BLUE_HI,
    colors.ORCHID_HI,
    colors.MAGENTA_HI,
    colors.RED_LO,
    colors.AMBER_LO,
    colors.YELLOW_LO,
    colors.GREEN_LO,
    colors.SKY_LO,
    colors.BLUE_LO,
    colors.ORCHID_LO,
    colors.MAGENTA_LO,
]

on_off_colors = {True: colors.PINK_HI, False: colors.ROSE}

##############################################################################

class Surface(object):

    def __init__(self, parent):
        # Initialize our "framebuffer"
        self.leds = {}
        for led in parent:
            self.leds[led] = colors.BLACK
        # Setup the masked surface
        # (By default, it filters out all display)
        self.parent = MaskedSurface(parent)

    def __iter__(self):
        return self.leds.__iter__()

    def __getitem__(self, led):
        return self.leds[led]

    def __setitem__(self, led, color):
        if led not in self.leds:
            logging.error("LED {} does not exist!".format(led))
        else:
            current_color = self.leds[led]
            if color != current_color:
                self.leds[led] = color
                if self.parent:
                    self.parent[led] = color

##############################################################################

class MaskedSurface(object):

    def __init__(self, parent):
        self.parent = parent
        self.mask = set()  # leds that are ALLOWED

    def __iter__(self):
        return self.mask.__iter__()

    def __setitem__(self, led, color):
        if led in self.mask:
            self.parent[led] = color

##############################################################################

class Gridget(object):

    def pad_pressed(self, row, column, velocity):
        pass

    def button_pressed(self, button):
        pass

##############################################################################

class Menu(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.menu = dict(
            BUTTON_1 = [
                self.grid.loopcontroller,
                self.grid.scalepicker,
            ],
            BUTTON_2 = [
                self.grid.notepickers,
            ],
            BUTTON_3 = [
                self.grid.instrumentpickers,
                self.grid.arpconfigs,
                self.grid.latchconfigs,
            ],
            BUTTON_4 = [
                self.grid.colorpicker,
                self.grid.faders,
                self.grid.bpmsetter,
            ],
        )
        self.current = "BUTTON_2"
        self.draw()

    def draw(self):
        for button in self.menu:
            if button == self.current:
                self.surface[button] = colors.PINK_HI
            else:
                self.surface[button] = colors.ROSE

    def button_pressed(self, button):
        entries = self.menu[button]
        if button == self.current:
            # Cycle through the entries of one menu
            entries.append(entries.pop(0))
            cycle = True
        else:
            # Switch to another menu
            self.current = button
            cycle = False
        entry = entries[0]
        # Resolve the exact gridget
        if isinstance(entry, list):
            gridget = entry[self.grid.channel]
        else:
            gridget = entry
        # Special case for the notepicker
        if len(entries) == 1 and cycle:
            gridget.cycle()
        else:
            self.grid.focus(gridget)
            self.draw()
