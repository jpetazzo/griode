import logging

from palette import palette

##############################################################################

# And first, a few constants

ARROWS = "UP DOWN LEFT RIGHT".split()
MENU = "BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4".split()

##############################################################################

class Surface(object):

    # What is a surface?
    
    def __init__(self, parent):
        # Initialize our "framebuffer"
        self.leds = {}
        for led in parent:
            self.leds[led] = palette.BLACK
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
        logging.debug("Here")
        for button in self.menu:
            if button == self.current:
                self.surface[button] = palette.MENU[1]
            else:
                self.surface[button] = palette.MENU[0]

    def button_pressed(self, button):
        logging.debug("button: {}".format(button))
        entries = self.menu[button]
        logging.debug("entries: {}".format(entries))
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
        logging.debug("self: {}".format(self))
        if len(entries) == 1 and cycle:
            logging.debug("Special case for the notepicker")
            gridget.cycle()
        else:
            self.grid.focus(gridget)
            self.draw()
