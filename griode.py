#!/usr/bin/env python3
import logging
import os
import mido
import subprocess
import sys
import time

logging.basicConfig(level=os.environ.get("LOG_LEVEL"))

import colors
from fluidsynth import Fluidsynth
from gridgets import ColorPicker, InstrumentPicker, NotePicker, ScalePicker
import notes
from persistence import persist_fields
import scales


@persist_fields(key=notes.C, scale=scales.MAJOR)
class Griode(object):

    def __init__(self):
        self.synth = Fluidsynth()
        self.devicechains = [DeviceChain(self, i) for i in range(16)]
        self.grids = []
        for port_name in mido.get_ioport_names():
            if "Launchpad Pro MIDI 2" in port_name:
                self.grids.append(LaunchpadPro(self, port_name))
            if "Launchpad MK2" in port_name:
                self.grids.append(LaunchpadMK2(self, port_name))

class LaunchPad(object):

    def __init__(self, griode, port_name):
        self.griode = griode
        self.port_name = port_name
        logging.info("Opening grid device {}".format(port_name))
        self.grid_in = mido.open_input(port_name)
        self.grid_out = mido.open_output(port_name)
        for message in self.setup:
            self.grid_out.send(message)
        self.surface = LPSurface(self)
        self.active_gridget = None # Gridget currently in the foreground
        self.colorpicker = ColorPicker(self)
        self.notepickers = [NotePicker(self, i) for i in range(16)]
        self.instrumentpickers = [InstrumentPicker(self, i) for i in range(16)]
        self.scalepicker = ScalePicker(self)
        self.grid_in.callback = self.process_message
        self.focus(self.notepickers[0])

    def focus(self, gridget):
        # De-focus the current active gridget
        if self.active_gridget:
            self.active_gridget.surface.parent = None
        # Set active gridget
        self.active_gridget = gridget
        # Focus the new active gridget
        gridget.surface.parent = self.surface
        # Now draw the gridget on us
        for led in gridget.surface:
            self.surface[led] = gridget.surface[led]

    def process_message(self, message):
        logging.debug("{} got message {}".format(self, message))

        # If there is no active gridget, ignore the message
        if self.active_gridget is None:
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

        if isinstance(led, tuple):
            row, column = led
            self.active_gridget.pad_pressed(row, column, velocity)
        elif isinstance(led, str):
            # Only emit button_pressed when the button is pressed
            # (i.e. not when it is released, which corresponds to value=0)
            if message.value == 127:
                self.active_gridget.button_pressed(led)


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
    for row in range(1,9):
        for column in range(1,9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i,button in enumerate("UP DOWN LEFT RIGHT BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4".split()):
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

    for row in range(1,9):
        for column in range(1,9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i,button in enumerate("UP DOWN LEFT RIGHT BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4".split()):
        control = 104 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = []


class DeviceChain(object):

    def __init__(self, griode, channel):
        self.griode = griode
        self.channel = channel
        #FIXME persistence
        # These variables indicate which instrument is currently selected.
        # Note: perhaps this instrument does not exist. In that case, the
        # `instrument` property below will fallback to an (existing) one.
        self.font_index = 0
        self.group_index = 0
        self.instr_index = 0
        self.bank_index = 0

    @property
    def instrument(self):
        fonts = self.griode.synth.fonts
        groups = fonts.get(self.font_index, fonts[0])
        instrs = groups.get(self.group_index, groups[0])
        banks = instrs.get(self.instr_index, instrs[0])
        instrument = banks.get(self.bank_index, banks[0])
        return instrument

    def send(self, message):
        self.griode.synth.send(message)

def main():
    griode = Griode()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()

##############################################################################

class BeatClock(object):

    def __init__(self, callback):
        self.bpm = 120
        self.tick = 0 # 24 ticks per quarter note
        self.next = time.time()
        self.callback = callback

    def loop(self):
        now = time.time()
        if now < self.next:
            return self.next - now
        self.tick += 1
        self.callback(self.tick)
        # Compute when we're due next
        self.next += 60.0 / self.bpm / 24
        if now > self.next:
            print("We're running late by {} seconds!".format(self.next-now))
            return 0
        return self.next - now

