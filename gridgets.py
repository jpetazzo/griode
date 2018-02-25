import logging
import mido

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
                "CHROMATIC",
                "DIATONIC",
                "MAGIC",
                "DRUMKIT",
            ],
            BUTTON_3 = [
                self.grid.instrumentpickers,
                self.grid.arpconfigs,
                self.grid.latchconfigs,
            ],
            BUTTON_4 = [
                self.grid.colorpicker,
                self.grid.mixer,
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

    def focus(self, entry):
        mode = None
        if isinstance(entry, str):
            mode = entry
            entry = self.grid.notepickers
        if isinstance(entry, list):
            gridget = entry[self.grid.channel]
        else:
            gridget = entry
        self.grid.focus(gridget)
        if mode:
            gridget.switch(mode)

    def button_pressed(self, button):
        if button == self.current:
            entries = self.menu[button]
            entries.append(entries.pop(0))
            self.focus(entries[0])
        else:
            self.current = button
            self.focus(self.menu[button][0])
        self.draw()

##############################################################################

class Mixer(Gridget):
    # FIXME this only allows to view/set 8 channels for now

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        # FIXME the volumes probably should be stored somewhere else
        self.volumes = [96]*16
        self.draw()

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                color = colors.BLACK
                volume = self.volumes[column-1]
                n_leds = (volume+16)//16
                if row <= n_leds:
                    color = channel_colors[column-1]
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        channel = column-1
        volume = 127*(row-1)//7
        self.volumes[channel] = volume
        logging.info("Setting channel {} volume to {}".format(channel, volume))
        message = mido.Message(
            "control_change", channel=channel,
            control=7, value=volume)
        self.grid.griode.synth.send(message)
        self.draw()
