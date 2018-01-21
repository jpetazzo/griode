#!/usr/bin/env python
import mido
import subprocess
import sys
import time

import colors
import gridgets
import notes
import scales


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

subprocess.Popen(
        ["fluidsynth", "-a", "pulseaudio", "-p", "griode", "default.sf2"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

synth_port = None
while synth_port is None:
    synth_port = open_output_matching("griode")
    if synth_port is None:
        print("Could not connect to fluidsynth!")
        time.sleep(1)

grid = gridgets.Grid(
        midi_in=open_input_matching("MIDI 2"),
        midi_out=open_output_matching("MIDI 2"))

note = gridgets.Note(grid, synth_port)
prog = gridgets.ProgramChange(grid, synth_port)
palette = gridgets.Palette(grid)

grid.focus(note)

while True:
    event = grid.midi_in.receive()
    print(event)

    if event.type == 'polytouch':
        continue
    
    if event.type == 'control_change' and event.value == 127:
        if event.control == 91:
            grid.up()
        if event.control == 92:
            grid.down()
        if event.control == 93:
            grid.left()
        if event.control == 94:
            grid.right()
        if event.control == 95: # session
            pass
        if event.control == 96: # note
            grid.focus(note)
        if event.control == 97: # device
            grid.focus(prog)
        if event.control == 98: # user
            grid.focus(palette)

    if event.type == 'note_on':
        row, col = event.note//10, event.note%10
        velocity = event.velocity
        grid.touch(row, col, velocity)

