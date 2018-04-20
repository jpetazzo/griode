#!/usr/bin/env python3

import mido
import sys

from looper import Loop, Note

# Syntax: mid2loop <foo.mid> <row> <col> <bars_to_loop>

midi_file = mido.MidiFile(filename=sys.argv[1])
cell = sys.argv[2:4]
bars = int(sys.argv[4])

loop = Loop(looper=None, cell=cell)

loop.notes.clear()
loop.channel = 3

def quantize(t, q):
	return q*round(t/q)

def time2tick(t):
	return quantize(24 * t / tempo * 1000000, 6)

now = 0
tempo = 0 # microseconds per quarter note
notes = {} # note -> start_time
for message in midi_file:
	now += message.time
	if message.type == "time_signature":
		print("# time signature: {}/{}".format(message.numerator, message.denominator))
		loop.teach_interval = bars * 24 * message.numerator
	if message.type == "set_tempo":
		tempo = message.tempo
	if message.type == "note_on" and message.velocity > 0:
		notes[message.note] = now
	elif message.type in ("note_on", "note_off"):
		start_time = notes.pop(message.note, None)
		if start_time is None:
			print("# unmatched note: {}".format(message.note))
		else:
			duration = now - start_time
			start_tick = time2tick(start_time)
			duration_tick = time2tick(duration)
			print(message.note, start_tick, duration_tick)
			if start_tick not in loop.notes:
				loop.notes[start_tick] = []
			loop.notes[start_tick].append(Note(message.note, 108, duration_tick))

from persistence import cache
for db in cache.values():
	db.close()

