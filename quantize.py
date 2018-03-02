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
        return tick-offset
    else:
        return tick-offset+QUANTIZE

def move(src, dst):
    print("{} -> {}".format(src, dst))
    if dst not in notes:
        notes[dst] = []
    notes[dst].extend(notes[src])
    del notes[src]

ticks = list(notes.keys())
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
