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
from gridgets import ArpConfig, ColorPicker, InstrumentPicker, LoopController, NotePicker, ScalePicker
import notes
from persistence import persistent_attrs, persistent_attrs_init
import scales

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
        self.surface_map = dict() # maps leds to gridgets
        self.colorpicker = ColorPicker(self)
        self.notepickers = [NotePicker(self, i) for i in range(16)]
        self.instrumentpickers = [InstrumentPicker(self, i) for i in range(16)]
        self.scalepicker = ScalePicker(self)
        self.arpconfigs = [ArpConfig(self, i) for i in range(16)]
        self.loopcontroller = LoopController(self)
        self.grid_in.callback = self.process_message
        self.focus(self.notepickers[self.channel])

    def focus(self, gridget, leds=None):
        # By default, map the gridget to everything, except MENU
        if leds is None:
            leds = [led for led in self.surface]
            #leds = [led for led in self.surface if led not in MENU]
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


@persistent_attrs(font_index=0, group_index=0, instr_index=0, bank_index=0)
class DeviceChain(object):

    def __init__(self, griode, channel):
        self.griode = griode
        self.channel = channel
        persistent_attrs_init(self, str(channel))
        for message in self.instrument.messages():
            self.send_to_synth(message)
        self.arpeggiator = Arpeggiator(self)
        self.arpeggiator.output = self.send_to_synth

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

    def send_to_synth(self, message):
        self.griode.synth.send(message.copy(channel=self.channel))

    def send(self, message):
        self.arpeggiator.input(message)

@persistent_attrs(
        enabled=True, interval=6, pattern_length=4,
        pattern=[[4, 3, [0]], [1, 2, [7]], [3, 1, [0]], [1, 2, [7]]],
        )
class Arpeggiator(object):

    def __init__(self, devicechain):
        self.devicechain = devicechain
        persistent_attrs_init(self, str(devicechain.channel))
        self.notes = []
        self.playing = []
        self.next_step = 0
        self.last_tick = 0
        self.next_tick = 0
    
    def tick(self, tick):
        self.last_tick = tick
        # OK, first, let's see if some notes have "expired" and should be stopped
        for note,deadline in self.playing:
            if tick > deadline:
                self.output(mido.Message("note_on", note=note, velocity=0))
                self.playing.remove((note, deadline))
        # If we're disabled, stop right there
        if self.enabled == False:
            self.notes.clear()
            return
        # Then, is it time to spell out the next note?
        if tick < self.next_tick:
            return
        # OK, is there any note in the buffer?
        if self.notes == []:
            return
        # Yay we have notes to play!
        velocity, gate, harmonies = self.pattern[self.next_step]
        velocity = velocity*31
        duration = gate*2
        for harmony in harmonies:
            offset = 0
            scale = self.devicechain.griode.scale
            while harmony >= len(scale):
                offset += 12
                harmony -= len(scale)
            # FIXME allow negative harmony
            note = self.notes[0] + offset + scale[harmony]
            self.output(mido.Message("note_on", note=note, velocity=velocity))
            self.playing.append((note, tick+duration))
        self.notes = self.notes[1:] + [self.notes[0]]
        # Update displays
        for grid in self.devicechain.griode.grids:
            arpconfig = grid.arpconfigs[self.devicechain.channel]
            arpconfig.current_step = self.next_step
            arpconfig.draw()
        # And prepare for next step
        self.next_tick += self.interval
        self.next_step += 1
        if self.next_step >= self.pattern_length:
            self.next_step = 0

    def input(self, message):
        if message.type == "note_on" and self.enabled:
            if message.velocity > 0:
                if self.notes == []:
                    self.next_tick = self.last_tick + 1
                    self.next_step = 0
                self.notes.insert(0, message.note)
            else:
                if message.note in self.notes:
                    self.notes.remove(message.note)
        else:
            self.output(message)

##############################################################################

@persistent_attrs(bpm=120)
class BeatClock(object):

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.tick = 0 # 24 ticks per quarter note
        self.next = time.time()

    def callback(self):
        for devicechain in self.griode.devicechains:
            devicechain.arpeggiator.tick(self.tick)
        for grid in self.griode.grids:
            grid.loopcontroller.tick(self.tick)

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

class Note(object):
    def __init__(self, note, velocity, start, duration):
        self.note = note
        self.velocity = velocity
        self.start = start
        self.duration = duration

class Loop(object):
    def __init__(self, looper, channel):
        self.looper = looper
        self.channel = channel
        self.first_bar = 0
        self.last_bar = 0
        self.notes = []
    def play(self):
        if self not in self.looper.loops:
            self.looper.loops.append(self)
        # FIXME don't do this if other loops are already playing
        self.looper.tick_zero = self.looper.last_tick+1
    def stop(self):
        if self in self.looper.loops:
            self.looper.loops.remove(self)
        # FIXME can we find a way to stop the notes that are playing?
        if self == self.looper.loop_recording:
            self.looper.loop_recording = None
        # FIXME do something with self.looper.notes_recording
    def record(self):
        self.stop()
        self.looper.loop_recording = self
        # FIXME update display too

@persistent_attrs(beats_per_bar=4, loops={})
class Looper(object):

    Loop = Loop

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.tick_zero = None       # At which tick did we hit "play"?
        self.last_tick = 0          # Last (=current) tick
        self.loops_playing = []     # Array of Loop() instances
        self.loop_recording = None  # Which loop (if any) is recording
        self.notes_recording = {}   # note -> Note()
        self.notes_playing = []     # (stop_tick, channel, note)

    def relative_tick(self):
        return self.last_tick - self.tick_zero

    def input(self, message):
        if self.loop_recording and message.type=="note_on":
            if message.channel==self.loop_recording.channel:
                if message.velocity>0: # beginning of a note
                    note = Note(message.note, message.velocity,
                                self.relative_tick, 0)
                    self.loop_recording.notes.append(note)
                    self.notes_recording[message.note] = note
                else: # end of a note
                    note = self.notes_recording.pop(message.note)
                    note.duration = self.relative_tick - note.start
        # No matter what: let the message through the chain
        self.output(message)

    def tick(self, tick):
        self.last_tick = tick
        # First, check if there are notes that should be stopped.
        notes_to_stop = [note for note in self.notes_playing if note[0]<=tick]
        for note in notes_to_stop:
            message = mido.Message(
                    "note_on", channel=note[1], note=note[2], velocity=0)
            self.output(message)
            self.notes_playing.remove(note)
        # OK now, for each loop that is playing...
        for loop in self.loops_playing:
            # Figure out which notes should be started *now*
            notes_to_play = [note for note in loop.notes
                             if notes.start==self.relative_tick]
            # FIXME use first_bar/last_bar
            # FIXME address looping
            for note in notes_to_play:
                self.notes_playing.append(
                        (tick+note.duration, loop.channel, note.note))
                message = mido.Message(
                        "note_on", channel=loop.channel,
                        note=note.note, velocity=note.velocity)
                self.output(message)

##############################################################################

def main():
    griode = Griode()
    while True:
        griode.beatclock.once()


if __name__ == "__main__":
    main()
