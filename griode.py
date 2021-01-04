#!/usr/bin/env python3
import logging
import mido
import os
import time
import getpass
import signal

from arpeggiator import ArpConfig, Arpeggiator
from clock import BPMSetter, Clock, CPU
from fluidsynth import Fluidsynth
from latch import Latch, LatchConfig
from looper import Looper, LoopController
from gridgets import MENU, Menu
from mixer import Faders, Mixer
import notes
from palette import palette
from persistence import cache, persistent_attrs, persistent_attrs_init
from pickers import ColorPicker, InstrumentPicker, NotePicker, ScalePicker
import scales


log_format = "[%(levelname)s] %(filename)s:%(lineno)d %(funcName)s() -> %(message)s"

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=log_level, format=log_format)
logging.debug("User: {}".format(getpass.getuser()))



def handler(signum, frame):
    global scale
    scale=scales.MAJOR
    logging.debug("signum {} frame  {} scale {}".
                  format(signum, frame, scale))

signal.signal(signal.SIGUSR2, handler)
    
#@persistent_attrs(key=notes.C, scale=scales.MAJOR)
@persistent_attrs(key=notes.C)
class Griode(object):

    def __init__(self):
        persistent_attrs_init(self)
        self.synth = Fluidsynth()

        # 16 channels.  One DeviceChain for each channel.  Each
        # DeviceChain has a `Latch` and `Arpeggiator`
        self.devicechains = [DeviceChain(self, i) for i in range(16)]

        self.grids = []
        self.scale = [0, 3, 6, 7, 10]
        self.cpu = CPU(self)
        self.clock = Clock(self)
        self.looper = Looper(self)
        self.mixer = Mixer(self)
        self.detect_devices()
        # FIXME: probably make this configurable somehow (env var...?)
        if False:
            from termpad import ASCIIGrid
            self.grids.append(ASCIIGrid(self, 0, 1))

    def theScale(self):
        # logging.debug("scale: {}".format(scale))
        return self.scale
        
    def setScale(self, scale):
        # logging.debug("scale: {}".format(scale))
        self.scale = scale
        
    def tick(self, tick):
        pass

    def detect_devices(self, initial=True):
        from launchpad import LaunchpadMK2, LaunchpadPro, LaunchpadS, LaunchpadX
        from keyboard import Keyboard
        logging.debug("Enumerating MIDI ports...")
        configured_ports = { grid.grid_name for grid in self.grids }
        try:
            detected_ports = set(mido.get_ioport_names())
        except:
            logging.exception("Error while enumerating MIDI ports")
            detected_ports = set()
        for port_name in detected_ports - configured_ports:
            # Detected a new device! Yay!
            klass = None
            if "Launchpad Pro MIDI 2" in port_name:
                klass = LaunchpadPro
            if "Launchpad MK2" in port_name:
                klass = LaunchpadMK2
            if "Launchpad S" in port_name:
                klass = LaunchpadS
            if "Launchpad X" in port_name:
                logging.debug("Got X")
                klass = LaunchpadX
            if "Launchpad Mini" in port_name:
                klass = LaunchpadS
            if "reface" in port_name:
                klass = Keyboard
            if klass is not None:
                # FIXME find a better way than this for hotplug!
                if not initial:
                    logging.info("Detected hotplug of new device: {}".format(port_name))
                    time.sleep(4)
                self.grids.append(klass(self, port_name))

        logging.debug("klass: {}".format(klass))
        for port_name in configured_ports - detected_ports:
            # Removing a device
            logging.info("Device {} is no longer plugged. Removing it."
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
        self.faders = Faders(self)
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

    def tick(self, tick):
        pass

##############################################################################

# What is a DeviceChain for?
@persistent_attrs(font_index=0, group_index=0, instr_index=0, bank_index=0)
class DeviceChain(object):

    def __init__(self, griode, channel):
        self.griode = griode
        self.channel = channel
        persistent_attrs_init(self, str(channel))
        self.latch = Latch(self)
        self.arpeggiator = Arpeggiator(self)
        self.program_change()

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

    def program_change(self):
        self.program_change_instrument(self.instrument)
        
    def program_change_instrument(self, instrument):
        logging.info("Channel {} switching to instrument B{} P{}: {}"
                     .format(self.channel, instrument.bank,
                             instrument.program, instrument.name))
        for message in instrument.messages():
            logging.debug("Instrument message: {}".format(message))
            self.send(message.copy(channel=self.channel))

    def send(self, message):
        self.latch.send(message)

##############################################################################

PATTERN_SAVING = [(1, 1), (1, 2), (2, 1), (2, 2)]
PATTERN_DONE = [(1, 1)]

def show_pattern(griode, pattern, color_on, color_off):
    for grid in griode.grids:
        for led in grid.surface:
            if led in pattern:
                grid.surface[led] = color_on
            else:
                grid.surface[led] = color_off


def main():
    logging.debug("")
    griode = Griode()
    try:
        while True:
            griode.clock.once()
    except KeyboardInterrupt:
        show_pattern(griode, PATTERN_SAVING, palette.ACTIVE, palette.BLACK)
        for db in cache.values():
            db.close()
        show_pattern(griode, PATTERN_DONE, palette.ACTIVE, palette.BLACK)



if __name__ == "__main__":
    main()
