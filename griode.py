#!/usr/bin/env python
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
        ["fluidsynth", "-a", "pulseaudio", "-r", "4", "-c", "4", "-p", "griode", "default.sf2"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

programs = {}
while fluidsynth.stdout.peek() != b"> ":
    fluidsynth.stdout.readline()
fluidsynth.stdin.write(b"inst 1\n")
fluidsynth.stdin.flush()
fluidsynth.stdout.readline()
while fluidsynth.stdout.peek() != b"> ":
    line = fluidsynth.stdout.readline()
    bank_prog, program_name = line.split(b" ", 1)
    bank, prog = [int(x) for x in bank_prog.split(b"-")]
    print("{} -> {} -> {}".format(prog, bank, program_name))
    if prog not in programs:
        programs[prog] = {}
    programs[prog][bank] = program_name

synth_port = None
while synth_port is None:
    synth_port = open_output_matching("griode")
    if synth_port is None:
        print("Could not connect to fluidsynth!")
        time.sleep(1)

grid = gridgets.Grid(
        grid_in=open_input_matching("MIDI 2"),
        grid_out=open_output_matching("MIDI 2"),
        synth_out=synth_port)


class BeatClock(object):

    def __init__(self, callback):
        self.bpm = 120
        self.beat = 0
        self.frame = 0 # 24 "frames" or "ticks" per bet
        self.next = time.time()
        self.callback = callback

    def loop(self):
        now = time.time()
        if now < self.next:
            return self.next - now
        self.frame += 1
        if self.frame == 24:
            self.beat += 1
            self.frame = 0
        self.callback(self.beat, self.frame)
        # Compute when we're due next
        self.next += 60.0 / self.bpm / 24
        if now > self.next:
            print("We're running late by {} seconds!".format(self.next-now))
            return 0
        return self.next - now


beatclock = BeatClock(grid.tick)

while True:
    time.sleep(beatclock.loop())

