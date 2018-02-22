#!/usr/bin/env python3
import logging
import os
import mido
import time

logging.basicConfig(level=os.environ.get("LOG_LEVEL"))

from arpeggiator import ArpConfig, Arpeggiator
import colors
from fluidsynth import Fluidsynth
from looper import Looper, LoopController
from gridgets import Menu, Mixer
import notes
from persistence import persistent_attrs, persistent_attrs_init
from pickers import ColorPicker, DrumPicker, InstrumentPicker, NotePicker, ScalePicker
import scales

# Work around a persistence bug (this should eventually be removed)
from looper import Note


ARROWS = "UP DOWN LEFT RIGHT".split()
MENU = "BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4".split()


@persistent_attrs(key=notes.C, scale=scales.MAJOR)
class Griode(object):

    def __init__(self):
        persistent_attrs_init(self)
        self.synth = Fluidsynth()
        self.devicechains = [DeviceChain(self, i) for i in range(16)]
        self.grids = []
        self.beatclock = BeatClock(self)
        self.looper = Looper(self)
        for port_name in mido.get_ioport_names():
            if "Launchpad Pro MIDI 2" in port_name:
                self.grids.append(LaunchpadPro(self, port_name))
            if "Launchpad MK2" in port_name:
                self.grids.append(LaunchpadMK2(self, port_name))
            if "Launchpad S" in port_name:
                self.grids.append(LaunchpadS(self, port_name))


@persistent_attrs(channel=0)
class LaunchPad(object):

    def __init__(self, griode, port_name):
        persistent_attrs_init(self, port_name)
        self.griode = griode
        self.port_name = port_name
        logging.info("Opening grid device {}".format(port_name))
        self.grid_in = mido.open_input(port_name)
        self.grid_out = mido.open_output(port_name)
        for message in self.setup:
            self.grid_out.send(message)
        self.surface = LPSurface(self)
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
        self.grid_in.callback = self.process_message
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

    def process_message(self, message):
        logging.debug("{} got message {}".format(self, message))

        # OK this is a hack to use fluidsynth directly with the Launchpad Pro
        if getattr(message, "channel", None) == 8:
            self.griode.synth.send(message)
            return

        # Ignore aftertouch messages for now
        if message.type == "polytouch":
            return

        # Let's try to find out if the performer pressed a pad/button
        led = None
        velocity = None
        if message.type == "note_on":
            led = self.message2led.get(("NOTE", message.note))
            velocity = message.velocity
        elif message.type == "control_change":
            led = self.message2led.get(("CC", message.control))

        if led is None:
            logging.warning("Unhandled message: {}".format(message))
            return

        gridget = self.surface_map.get(led)
        if gridget is None:
            logging.warning("Button {} is not routed to any gridget.".format(led))
            return

        if isinstance(led, tuple):
            row, column = led
            gridget.pad_pressed(row, column, velocity)
        elif isinstance(led, str):
            # Only emit button_pressed when the button is pressed
            # (i.e. not when it is released, which corresponds to value=0)
            if message.value == 127:
                gridget.button_pressed(led)


class LPSurface(object):

    def __init__(self, launchpad):
        self.launchpad = launchpad

    def __iter__(self):
        return self.launchpad.led2message.__iter__()

    def __setitem__(self, led, color):
        message_type, parameter = self.launchpad.led2message[led]
        if message_type == "NOTE":
            message = mido.Message("note_on", note=parameter, velocity=color)
        elif message_type == "CC":
            message = mido.Message("control_change", control=parameter, value=color)
        self.launchpad.grid_out.send(message)


class LaunchpadPro(LaunchPad):

    message2led = {}
    led2message = {}
    for row in range(1, 9):
        for column in range(1, 9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 91 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = [
        # This SysEx message switches the LaunchPad Pro to "programmer" mode
        mido.Message("sysex", data=[0, 32, 41, 2, 16, 44, 3]),
        # And this one sets the front/side LED
        mido.Message("sysex", data=[0, 32, 41, 2, 16, 10, 99, colors.WHITE]),
    ]


class LaunchpadMK2(LaunchPad):

    message2led = {}
    led2message = {}

    for row in range(1, 9):
        for column in range(1, 9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 104 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = []


class LaunchpadS(LaunchPad):

    message2led = {}
    led2message = {}

    for row in range(1, 9):
        for column in range(1, 9):
            note = 16*(8-row) + column-1
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 104 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = []

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
                print("Cactching up (deciding that next tick = now).")
                self.next = now
            return 0
        return self.next - now

    def once(self):
        time.sleep(self.poll())

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
