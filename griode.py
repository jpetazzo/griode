#!/usr/bin/env python3
import logging
import os
import mido
import time

logging.basicConfig(level=os.environ.get("LOG_LEVEL"))

from arpeggiator import ArpConfig, Arpeggiator
from clock import BPMSetter, Clock, CPU
import colors
from fluidsynth import Fluidsynth
from latch import Latch, LatchConfig
from looper import Looper, LoopController
from gridgets import MENU, Menu, Mixer
import notes
from persistence import persistent_attrs, persistent_attrs_init
from pickers import ColorPicker, InstrumentPicker, NotePicker, ScalePicker
import scales


# Work around a persistence bug (this should eventually be removed)
from looper import Note


@persistent_attrs(key=notes.C, scale=scales.MAJOR)
class Griode(object):

    def __init__(self):
        persistent_attrs_init(self)
        self.synth = Fluidsynth()
        self.devicechains = [DeviceChain(self, i) for i in range(16)]
        self.grids = []
        self.cpu = CPU(self)
        self.clock = Clock(self)
        self.looper = Looper(self)
        # FIXME: probably make this configurable somehow (env var...?)
        if False:
            from termpad import ASCIIGrid
            self.grids.append(ASCIIGrid(self, 0, 1))

    def tick(self, tick):
        from launchpad import LaunchpadMK2, LaunchpadPro, LaunchpadS
        if tick%100 == 1:
            configured_ports = { grid.grid_name for grid in self.grids }
            detected_ports = set(mido.get_ioport_names())
            for port_name in detected_ports - configured_ports:
                # Detected a new device! Yay!
                klass = None
                if "Launchpad Pro MIDI 2" in port_name:
                    klass = LaunchpadPro
                if "Launchpad MK2" in port_name:
                    klass = LaunchpadMK2
                if "Launchpad S" in port_name:
                    klass = LaunchpadS
                if klass is not None:
                    # FIXME find a better way than this for hotplug!
                    if tick > 1:
                        time.sleep(4)
                    self.grids.append(klass(self, port_name))
            for port_name in configured_ports - detected_ports:
                # Removing a device
                logging.debug("Device {} is no longer plugged. Removing it."
                              .format(port_name))
                self.grids = [g for g in self.grids if g.grid_name != port_name]

##############################################################################

@persistent_attrs(channel=0)
class Grid(object):

    def __init__(self, griode, grid_name):
        self.griode = griode
        self.grid_name = grid_name
        persistent_attrs_init(self, grid_name)
        self.surface_map = {}  # maps leds to gridgets
        self.colorpicker = ColorPicker(self)
        self.mixer = Mixer(self)
        self.bpmsetter = BPMSetter(self)
        self.notepickers = [NotePicker(self, i) for i in range(16)]
        self.instrumentpickers = [InstrumentPicker(self, i) for i in range(16)]
        self.scalepicker = ScalePicker(self)
        self.arpconfigs = [ArpConfig(self, i) for i in range(16)]
        self.latchconfigs = [LatchConfig(self, i) for i in range(16)]
        self.loopcontroller = LoopController(self)
        self.menu = Menu(self)
        self.focus(self.menu, MENU)
        self.focus(self.notepickers[self.channel])

    def focus(self, gridget, leds=None):
        # By default, map the gridget to everything, except MENU
        if leds is None:
            leds = [led for led in self.surface if led not in MENU]
        # For each mapped led ...
        for led in leds:
            # Unmap the widget(s) that was "owning" that led
            if led in self.surface_map:
                self.surface_map[led].surface.parent.mask.remove(led)
            # Update the map
            self.surface_map[led] = gridget
            # Map the new widget
            gridget.surface.parent.mask.add(led)
            # Draw it
            self.surface[led] = gridget.surface[led]

##############################################################################

@persistent_attrs(font_index=0, group_index=0, instr_index=0, bank_index=0)
class DeviceChain(object):

    def __init__(self, griode, channel):
        self.griode = griode
        self.channel = channel
        persistent_attrs_init(self, str(channel))
        for message in self.instrument.messages():
            self.griode.synth.send(message.copy(channel=channel))
        self.latch = Latch(self)
        self.arpeggiator = Arpeggiator(self)

    # The variables `..._index` indicate which instrument is currently selected.
    # Note: perhaps this instrument does not exist. In that case, the
    # `instrument` property below will fallback to an (existing) one.
    @property
    def instrument(self):
        fonts = self.griode.synth.fonts
        groups = fonts.get(self.font_index, fonts[0])
        instrs = groups.get(self.group_index, groups[0])
        banks = instrs.get(self.instr_index, instrs[0])
        instrument = banks.get(self.bank_index, banks[0])
        return instrument

    def send(self, message):
        self.latch.send(message)

##############################################################################

def main():
    griode = Griode()
    try:
        while True:
            griode.clock.once()
    except KeyboardInterrupt:
        for grid in griode.grids:
            for led in grid.surface:
                if led == (1, 1):
                    grid.surface[led] = colors.PINK
                else:
                    grid.surface[led] = colors.BLACK


if __name__ == "__main__":
    main()
