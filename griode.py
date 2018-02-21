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
from gridgets import ArpConfig, ColorPicker, DrumPicker, InstrumentPicker, LoopController, Menu, Mixer, NotePicker, ScalePicker
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
        self.surface_map = dict() # maps leds to gridgets
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


class LaunchpadS(LaunchPad):

    message2led = {}
    led2message = {}

    for row in range(1,9):
        for column in range(1,9):
            note = 16*(8-row) + column-1
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

    def send(self, message):
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

    def output(self, message):
        message = message.copy(channel = self.devicechain.channel)
        self.devicechain.griode.synth.send(message)

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

class Note(object):
    def __init__(self, note, velocity, duration):
        self.note = note
        self.velocity = velocity
        self.duration = duration

@persistent_attrs(notes={}, channel=0, tick_in=0, tick_out=0)
class Loop(object):
    def __init__(self, looper, cell):
        logging.info("Loop.__init__()")
        self.looper = looper
        persistent_attrs_init(self, "{},{}".format(*cell))
        self.next_tick = 0 # next "position" to be played in self.notes
        self.looper.looprefs.add(cell)

@persistent_attrs(beats_per_bar=4, looprefs=set())
class Looper(object):

    Loop = Loop

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.playing = False
        self.last_tick = 0           # Last (=current) tick
        self.loops_playing = set()   # Contains instances of Loop
        self.loops_recording = set() # Also instances of Loop
        self.notes_recording = {}    # note -> (Note(), tick_when_started)
        self.notes_playing = []      # (stop_tick, channel, note)
        self.loops = {}
        for cell in self.looprefs:
            self.loops[cell] = Loop(self, cell)

    def send(self, message):
        if self.playing and message.type=="note_on":
            #import pdb;pdb.set_trace()
            for loop in self.loops_recording:
                if loop.channel == message.channel:
                    if message.velocity>0: # beginning of a note
                        logging.debug("Recording new note START")
                        note = Note(message.note, message.velocity, 0)
                        if loop.next_tick not in loop.notes:
                            loop.notes[loop.next_tick] = []
                        loop.notes[loop.next_tick].append(note)
                        self.notes_recording[message.note] = (note, self.last_tick)
                    else: # end of a note
                        logging.debug("Recording new note END")
                        note, tick_started = self.notes_recording.pop(message.note)
                        note.duration = self.last_tick - tick_started
        # No matter what: let the message through the chain
        self.output(message)

    def output(self, message):
        channel = message.channel
        devicechain = self.griode.devicechains[channel]
        devicechain.send(message)

    def tick(self, tick):
        self.last_tick = tick
        # First, check if there are notes that should be stopped.
        notes_to_stop = [note for note in self.notes_playing if note[0]<=tick]
        for note in notes_to_stop:
            message = mido.Message(
                    "note_on", channel=note[1], note=note[2], velocity=0)
            self.output(message)
            self.notes_playing.remove(note)
            # Light off notepickers
            for grid in self.griode.grids:
                grid.notepickers[note[1]].send(message, self)
        # Only play stuff if we are really playing (i.e. not paused)
        if not self.playing:
            return
        # OK now, for each loop that is playing...
        for loop in self.loops_playing:
            # Figure out which notes should be started *now*
            for note in loop.notes.get(loop.next_tick, []):
                self.notes_playing.append(
                        (tick+note.duration, loop.channel, note.note))
                message = mido.Message(
                        "note_on", channel=loop.channel,
                        note=note.note, velocity=note.velocity)
                self.output(message)
                # Light up notepickers
                for grid in self.griode.grids:
                    grid.notepickers[loop.channel].send(message, self)
        # Advance each loop that is currently playing or recording
        for loop in self.loops_playing | self.loops_recording:
            loop.next_tick += 1
            # If we're past the end of the loop, jump to begin of loop
            if loop.tick_out > 0 and loop.next_tick >= loop.tick_out:
                loop.next_tick = loop.tick_in

##############################################################################

def main():
    griode = Griode()
    try:
        while True:
            griode.beatclock.once()
    except KeyboardInterrupt:
        for grid in griode.grids:
            for led in grid.surface:
                grid.surface[led] = colors.PINK if led==(1,1) else colors.BLACK


if __name__ == "__main__":
    main()
