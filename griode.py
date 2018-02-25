#!/usr/bin/env python3
import logging
import os
import mido
import resource
import time

logging.basicConfig(level=os.environ.get("LOG_LEVEL"))

from arpeggiator import ArpConfig, Arpeggiator
import colors
from fluidsynth import Fluidsynth
from looper import Looper, LoopController
from gridgets import MENU, Menu, Mixer
import notes
from persistence import persistent_attrs, persistent_attrs_init
from pickers import ColorPicker, DrumPicker, InstrumentPicker, NotePicker, ScalePicker
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
        self.beatclock = BeatClock(self)
        self.looper = Looper(self)
        from launchpad import LaunchpadMK2, LaunchpadPro, LaunchpadS
        for port_name in mido.get_ioport_names():
            if "Launchpad Pro MIDI 2" in port_name:
                self.grids.append(LaunchpadPro(self, port_name))
            if "Launchpad MK2" in port_name:
                self.grids.append(LaunchpadMK2(self, port_name))
            if "Launchpad S" in port_name:
                self.grids.append(LaunchpadS(self, port_name))
        # FIXME: probably make this configurable somehow (env var...?)
        #from termpad import ASCIIGrid
        #self.grids.append(ASCIIGrid(self, 0, 1))

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
        self.drumpickers = [DrumPicker(self, i) for i in range(16)]
        self.notepickers = [NotePicker(self, i) for i in range(16)]
        self.instrumentpickers = [InstrumentPicker(self, i) for i in range(16)]
        self.scalepicker = ScalePicker(self)
        self.arpconfigs = [ArpConfig(self, i) for i in range(16)]
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
        self.arpeggiator.send(message)

##############################################################################

@persistent_attrs(bpm=120)
class BeatClock(object):

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.tick = 0  # 24 ticks per quarter note
        self.next = time.time()

    def callback(self):
        for devicechain in self.griode.devicechains:
            devicechain.arpeggiator.tick(self.tick)
        for grid in self.griode.grids:
            grid.loopcontroller.tick(self.tick)
        self.griode.looper.tick(self.tick)
        self.griode.cpu.tick(self.tick)

    def poll(self):
        now = time.time()
        if now < self.next:
            return self.next - now
        self.tick += 1
        self.callback()
        # Compute when we're due next
        self.next += 60.0 / self.bpm / 24
        if now > self.next:
            print("We're running late by {} seconds!".format(self.next-now))
            # If we are late by more than 1 second, catch up.
            if now > self.next + 1.0:
                print("Catching up (deciding that next tick = now).")
                self.next = now
            return 0
        return self.next - now

    def once(self):
        time.sleep(self.poll())

##############################################################################

class CPU(object):
    # Keep track of our CPU usage.

    def __init__(self, griode):
        self.griode = griode
        self.last_usage = 0
        self.last_time = 0
        self.last_shown = 0

    def tick(self, tick):
        r = resource.getrusage(resource.RUSAGE_SELF)
        new_usage = r.ru_utime + r.ru_stime
        new_time = time.time()
        if new_time > self.last_shown + 1.0:
            percent = (new_usage-self.last_usage)/(new_time-self.last_time)
            logging.debug("CPU usage: {:.2%}".format(percent))
            self.last_shown = new_time
        self.last_usage = new_usage
        self.last_time = new_time

##############################################################################

def main():
    griode = Griode()
    try:
        while True:
            griode.beatclock.once()
    except KeyboardInterrupt:
        for grid in griode.grids:
            for led in grid.surface:
                if led == (1, 1):
                    grid.surface[led] = colors.PINK
                else:
                    grid.surface[led] = colors.BLACK


if __name__ == "__main__":
    main()
