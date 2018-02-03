#!/usr/bin/env python
import logging
import os
import mido
import subprocess
import sys
import time

import gridgets


logging.basicConfig(level=os.environ.get("LOG_LEVEL"))


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


class Instrument(object):

    def __init__(self, font, program, bank, name):
        self.font = font        # fluidsynth font number (starts at 1)
        self.program = program  # MIDI program number [0..127]
        self.bank = bank        # bank [0..127] I think
        self.name = name        # string (not guaranteed to be unique!)

    def messages(self):
        """Generate MIDI messages to switch to that instrument."""
        # FIXME: deal with font
        return [
                mido.Message("control_change", control=0, value=self.bank),
                mido.Message("program_change", program=self.program),
                ]


instruments = []
while fluidsynth.stdout.peek() != b"> ":
    fluidsynth.stdout.readline()
fluidsynth.stdin.write(b"inst 1\n")
fluidsynth.stdin.flush()
fluidsynth.stdout.readline()
while fluidsynth.stdout.peek() != b"> ":
    line = fluidsynth.stdout.readline()
    bank_prog, program_name = line.split(b" ", 1)
    bank, prog = [int(x) for x in bank_prog.split(b"-")]
    name = program_name.decode("ascii").strip()
    logging.debug("Adding instrument {} -> {} -> {}".format(prog, bank, name))
    instruments.append(Instrument(1, prog, bank, name))

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
        synth_out=synth_port,
        instruments=instruments,
        )


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

