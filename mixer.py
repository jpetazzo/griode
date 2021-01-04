import enum
import logging
import mido

from gridgets import Gridget, Surface
from palette import palette
from persistence import persistent_attrs, persistent_attrs_init


class Page(enum.Enum):
    VOLUME = 1
    CHORUS = 2
    REVERB = 3


@persistent_attrs(volume=16*[96], chorus=16*[0], reverb=16*[0])
class Mixer(object):

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        # FIXME don't duplicate the CC mappings
        for cc, array in [
            (7, self.volume),
            (91, self.chorus),
            (93, self.reverb),
        ]:
            for channel, value in enumerate(array):
                m = mido.Message("control_change", control=cc, value=value)
                self.griode.devicechains[channel].send(m)


class Faders(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.page = Page.VOLUME
        self.first_channel = 0
        self.draw()

    @property
    def mixer(self):
        return self.grid.griode.mixer

    @property
    def array(self):
        if self.page == Page.VOLUME:
            return self.mixer.volume
        if self.page == Page.CHORUS:
            return self.mixer.chorus
        if self.page == Page.REVERB:
            return self.mixer.reverb

    @property
    def cc(self):
        if self.page == Page.VOLUME:
            return 7
        if self.page == Page.CHORUS:
            return 91
        if self.page == Page.REVERB:
            return 93

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                channel = self.first_channel + column - 1
                value = self.array[channel]
                n_leds = (value+16)//16
                color = palette.BLACK
                if row <= n_leds:
                    color = palette.CHANNEL[channel]
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        channel = self.first_channel + column - 1
        value = 127*(row-1)//7
        self.array[channel] = value
        logging.info("Setting {} for channel {} to {}"
                     .format(self.page, channel, value))
        message = mido.Message(
            "control_change", channel=channel,
            control=self.cc, value=value)
        self.grid.griode.synth.send(message)
        self.draw()

    def button_pressed(self, button):
        logging.debug("button: {}".format(button))
        if button == "LEFT":
            self.first_channel = 0
        if button == "RIGHT":
            self.first_channel = 8
        if button == "UP":
            self.page = Page(self.page.value-1)
        if button == "DOWN":
            self.page = Page(self.page.value+1)
        self.draw()
