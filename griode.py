#!/usr/bin/env python
import logging
import mido
import subprocess
import sys
import time

import gridgets


def open_input_matching(string):
    return open_port_matching(
            string,
            "input",
            mido.get_input_names,
            mido.open_input)

def open_output_matching(string):
    return open_port_matching(
            string,
            "output",
            mido.get_output_names,
            mido.open_output)

def open_port_matching(string, in_or_out, get_port_names, open_port):
    port_names = get_port_names()
    for port_name in port_names:
        if string in port_name:
            print("Using {} for {}.".format(port_name, in_or_out))
            return open_port(port_name)

    print("Could not find any {} port matching {}."
            .format(in_or_out, string))

fluidsynth = subprocess.Popen(
        ["fluidsynth", "-a", "pulseaudio", "-r", "8", "-c", "8", "-p", "griode", "default.sf2"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

class Instruments(object):

    def __init__(self):
        self.fonts = []

    def add_font(self, number, name):
        self.melodic = (number, name, {})
        self.drumkits = (number, name, {})

    def add(self, program, bank, name):
        if bank<100:
            category = self.melodic
        else:
            category = self.drumkits
        # We only want non-empty fonts, so we only add a font to the top-level list
        # when we add the first instrument in that font
        if category not in self.fonts:
            self.fonts.append(category)
        # OK now do we already have that program?
        programs = category[2]
        if program not in programs:
            programs[program] = {}
        # Add the specific variation (bank in MIDI parlance) to that program
        programs[program][bank] = name

instruments = Instruments()
while fluidsynth.stdout.peek() != b"> ":
    fluidsynth.stdout.readline()
instruments.add_font(1, "default")
fluidsynth.stdin.write(b"inst 1\n")
fluidsynth.stdin.flush()
fluidsynth.stdout.readline()
while fluidsynth.stdout.peek() != b"> ":
    line = fluidsynth.stdout.readline()
    bank_prog, program_name = line.split(b" ", 1)
    bank, prog = [int(x) for x in bank_prog.split(b"-")]
    name = program_name.decode("ascii").strip()
    logging.debug("Adding instrument {} -> {} -> {}".format(prog, bank, name))
    instruments.add(prog, bank, name)

synth_port = None
while synth_port is None:
    synth_port = open_output_matching("griode")
    if synth_port is None:
        logging.info("Could not connect to fluidsynth, retrying...")
        time.sleep(1)
logging.info("Connected to fluidsynth.")

class DummyIO(object):

    def send(self, message):
        print(message)

grid = gridgets.Grid(
        grid_in=open_input_matching("MIDI 2") or DummyIO(),
        grid_out=open_output_matching("MIDI 2") or DummyIO(),
        synth_out=synth_port)


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


beatclock = BeatClock(grid.tick)

while True:
    time.sleep(beatclock.loop())

