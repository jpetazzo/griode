import intervaltree
import logging
import mido
import time

from gridgets import Gridget, Surface
from palette import palette
from persistence import persistent_attrs, persistent_attrs_init


class Sequencer(object):

    def __init__(self, griode):
        self.griode = griode
        self.last_tick = 0            # Last (=current) tick
        self.loopers = [Looper(self, i) for i in range(16)]
        self.playing = False
        self.time_ref = 0             # Initialized when playing starts

    def output(self, message):
        channel = message.channel
        devicechain = self.griode.devicechains[channel]
        devicechain.send(message)

    def tick(self, tick):
        self.last_tick = tick
        if self.playing:
            for looper in self.loopers:
                if looper.playing:
                    loop = looper.loops[looper.loop]
                    relative_tick = (self.last_tick - self.time_ref) % loop.duration
                    # Get all notes that overlap the current tick
                    notes = loop.notes[relative_tick:relative_tick+1]
                    # But only play the ones that actually start now
                    for note in notes:
                        if int(note.begin) == relative_tick:
                            duration = note.end - note.begin
                            deadline = tick + duration
                            looper.notes_playing[note.data.note] = deadline
                            message = mido.Message(
                                "note_on",
                                note=note.data.note,
                                velocity=note.data.velocity
                                )
                            self.output(message)
                    # Also stop notes that should be stopped
                    for note, deadline in looper.notes_playing.items():
                        if deadline > tick:
                            message = mido.Message(
                                "note_on",
                                note=note,
                                velocity=0
                                )
                            self.output(message)


class Looper(object):

    def __init__(self, sequencer, channel):
        self.sequencer = sequencer
        self.channel = channel
        self.playing = False
        self.loop = 0 # Which loop is currently selected / playing
        self.loops = [Loop(self, 0)]
        self.notes_playing = {} # note -> deadline

    def output(self, message):
        message.channel = self.channel
        devicechain = self.sequencer.griode.devicechains[self.channel]
        devicechain.send(message)


@persistent_attrs(notes=intervaltree.IntervalTree(), duration=24*8)
class Loop(object):

    def __init__(self, looper, number):
        self.looper = looper
        persistent_attrs_init(
            self, "C{:02}L{:02}".format(looper.channel, number))


class Note(object):

    def __init__(self, note, velocity):
        self.note = note
        self.velocity = velocity

    def __repr__(self):
        return ("Note(note={}, velocity={})"
                .format(self.note, self.velocity))


class SequencerController(Gridget):

    """
    ^ v < >  = PLAY/PAUSE OPTIONS PREVLOOP NEXTLOOP    
    """

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.surface = Surface(grid.surface)
        self.sequencer = grid.griode.sequencer
        self.looper = self.sequencer.loopers[channel]
        self.notepicker = grid.notepickers[channel]
        self.note = None # int; note that will be added/removed
        self.velocity = None # ditto
        self.ticks_per_step = 6 # 24 ticks per quarter note
        self.draw()

    def tick(self, tick):
    	pass # FIXME: update display?

    def button_pressed(self, button):
        if button == "UP":
            if self.looper.playing:
                # Stop!
                self.looper.playing = False
                # Stop notes currently playing (for the current channel only)
                for note, deadline in self.looper.notes_playing.items():
                    message = mido.Message("note_on", note=note, velocity=0)
                    self.looper.output(message)
                self.looper.notes_playing.clear()
                # Update the global sequencer playing status
                self.sequencer.playing = any(looper.playing for looper in self.sequencer.loopers)
            else:
                # Play!
                self.looper.playing = True
                if not self.sequencer.playing:
                    # Sequencer was not playing, so we need to start it :)
                    self.sequencer.playing = True
                    self.sequencer.time_ref = self.sequencer.last_tick
        if button == "DOWN":
            # options
            FIXME
        if button == "LEFT":
            # select prev loop
            FIXME
        if button == "RIGHT":
            # select next loop
            FIXME
        self.draw()

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if row in [1, 2, 3, 4]:
                    # Lower half of the grid: note picker
                    color = self.notepicker.surface[led]
                    if self.note is not None:
                        if self.note == self.notepicker.led2note[row, column]:
                            color = palette.ACTIVE
                if row in [5, 6, 7, 8]:
                    # Upper half of the grid: sequencer steps
                    color = palette.BLACK
                    # Find out if there are notes overlapping this tick
                    notes = self.rc2notes(row, column)
                    # If there is at least one note, show it
                    if notes:
                        color = palette.TRIG
                    # And if one of these notes is the currently selected one, show it
                    if self.note is not None:
                        for note in notes:
                            if note.data.note == self.note:
                                color = palette.TRIG[1]
                    # FIXME: if current loop is playing, show current play position
                self.surface[led] = color

    @property
    def loop(self):
        return self.looper.loops[self.looper.loop]
    
    @property
    def notes(self):
        return self.loop.notes

    def rc2tick(self, row, column):
        step = 8*(8 - row) + column - 1
        return step * self.ticks_per_step

    def rc2notes(self, row, column):
        begin = self.rc2tick(row, column)
        end = begin + self.ticks_per_step
        return self.notes[begin:end]

    def pad_pressed(self, row, column, velocity):
        if row in [1, 2, 3, 4]:
            # Lower half of the grid: note picker
            self.notepicker.pad_pressed(row, column, velocity)
            if velocity > 0:
                self.note = self.notepicker.led2note[row, column]
                self.velocity = velocity
            self.draw()
        if row in [5, 6, 7, 8]:
            # Upper half of the grid: sequencer steps
            if velocity == 0:
                return
            if self.note is None:
                return
            # If the currently selected note already exists in that step,
            # remove it. Otherwise, add it at the beginning of the step.
            add_note = True
            notes = self.rc2notes(row, column)
            for note in notes:
                if note.data.note == self.note:
                    logging.debug("Removing note: {}".format(note))
                    self.notes.remove(note)
                    add_note = False
            if add_note:
                begin = self.rc2tick(row, column)
                end = begin + self.ticks_per_step
                note = Note(self.note, self.velocity)
                logging.debug(
                    "Adding note: [{}:{}] = {}"
                    .format(begin, end, note))
                self.notes[begin:end] = note
            # Since we changed something, redraw.
            self.draw()
