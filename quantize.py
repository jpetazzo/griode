#!/usr/bin/env python3

import shelve
import sys

# 24 = quantize on quarter note
# 12 = quantize on eigth note
# etc.
QUANTIZE = 6

db = shelve.open(sys.argv[1])

notes = db["notes"]

def quantize(tick):
    offset = tick % QUANTIZE
    if offset < QUANTIZE/2:
        new_tick = tick-offset
    else:
        new_tick = tick-offset+QUANTIZE
    if tick != new_tick:
        print("Quantizing {} to {}".format(tick, new_tick))
    return new_tick

def move(src, dst):
    print("{} -> {}".format(src, dst))
    if dst not in notes:
        notes[dst] = []
    notes[dst].extend(notes[src])
    del notes[src]

ticks = sorted(notes.keys())
for tick, next_tick in zip(ticks, ticks[1:]):
    for note in notes[tick]:
        bar = tick//24//4
        beat = tick/24%4
        print("{bar:3}.{beat:3} | {note.note:3} | {note.velocity:3} | {note.duration:3}"
              .format(bar=bar, beat=beat, note=note))
        note.duration = quantize(note.duration)
        if note.duration == 0:
            note.duration = quantize(next_tick - tick)
for note in notes[ticks[-1]]:
    if note.duration == 0:
        note.duration = 24
       
ticks = sorted(notes.keys())
for src in ticks:
    dst = quantize(src)
    if src != dst:
        move(src, dst)

ticks = sorted(notes.keys())
first = ticks[0]
if first > 0:
    for tick in ticks:
        move(tick, tick-first)

db["notes"] = notes

db.close()
