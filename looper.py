import logging
import mido
import time

import colors
from gridgets import Gridget, Surface, channel_colors, on_off_colors
from persistence import persistent_attrs, persistent_attrs_init


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
        self.next_tick = 0  # next "position" to be played in self.notes
        self.looper.looprefs.add(cell)


@persistent_attrs(beats_per_bar=4, looprefs=set())
class Looper(object):

    Loop = Loop

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.playing = False
        self.last_tick = 0            # Last (=current) tick
        self.loops_playing = set()    # Contains instances of Loop
        self.loops_recording = set()  # Also instances of Loop
        self.notes_recording = {}     # note -> (Note(), tick_when_started)
        self.notes_playing = []       # (stop_tick, channel, note)
        self.loops = {}
        for cell in self.looprefs:
            self.loops[cell] = Loop(self, cell)

    def send(self, message):
        if self.playing and message.type == "note_on":
            for loop in self.loops_recording:
                if loop.channel == message.channel:
                    if message.velocity > 0:
                        logging.info("Recording new note START")
                        note = Note(message.note, message.velocity, 0)
                        if loop.next_tick not in loop.notes:
                            loop.notes[loop.next_tick] = []
                        loop.notes[loop.next_tick].append(note)
                        self.notes_recording[message.note] = (note, self.last_tick)
                    else:
                        logging.info("Recording new note END")
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
        notes_to_stop = [note for note in self.notes_playing if note[0] <= tick]
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


class LoopController(Gridget):

    """
    ^ v < >  = PLAY REC REWIND PLAY/PAUSE
    Then the 64 pads are available for loops

    Press more than 1 second on a pad to edit it
    Press less than 1 second to select/deselect it for play/rec
    """

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.loopeditor = LoopEditor(grid)
        self.mode = "PLAY"   # or "REC"
        self.pads_held = {}  # maps pad to time when pressed
        self.draw()

    @property
    def looper(self):
        return self.grid.griode.looper

    def blink(self, color, play, rec):
        tick = self.looper.last_tick
        # If play: slow blink (once per quarter note)
        # If rec: fast blink (twice per quarter note)
        # If play and rec: alternate slow and fast blink
        if play and rec:
            if tick % 48 > 24:
                rec = False
            else:
                play = False
        if play:
            if tick % 24 > 18:
                return colors.BLACK
            else:
                return color
        if rec:
            if tick % 12 > 4:
                return colors.BLACK
            else:
                return color
        return color

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                color = colors.GREY_LO
                if led in self.looper.loops:
                    # If there is a loop in that cell, light it up
                    loop = self.looper.loops[led]
                    color = channel_colors[loop.channel]
                    # If that loop is selected for play or rec, show it
                    # (With fancy blinking)
                    color = self.blink(
                        color,
                        loop in self.looper.loops_playing,
                        loop in self.looper.loops_recording)
                self.surface[led] = color
        # UP = playback, DOWN = record
        self.surface["UP"] = on_off_colors[self.mode == "PLAY"]
        self.surface["DOWN"] = on_off_colors[self.mode == "REC"]
        self.surface["UP"] = self.blink(
            self.surface["UP"], self.looper.loops_playing, False)
        self.surface["DOWN"] = self.blink(
            self.surface["DOWN"], False, self.looper.loops_recording)
        # LEFT = rewind all loops (but keep playing if we're playing)
        # (but also used to delete a loop!)
        self.surface["LEFT"] = on_off_colors[bool(self.pads_held)]
        # RIGHT = play/pause
        self.surface["RIGHT"] = on_off_colors[self.looper.playing]

    def tick(self, tick):
        for cell, time_pressed in self.pads_held.items():
            if time.time() > time_pressed + 1.0:
                self.pads_held.clear()
                # Enter edit mode for that pad
                loop = self.looper.loops[cell]
                self.loopeditor.edit(loop)
                self.grid.focus(self.loopeditor)
                break
        self.draw()
        self.loopeditor.draw()

    def pad_pressed(self, row, column, velocity):
        # We don't act when the pad is pressed, but when it is released.
        # (When the pad is pressed, we record the time, so we can later
        # detect when a pad is held more than 1s to enter edit mode.)
        if velocity > 0:
            self.pads_held[row, column] = time.time()
            return
        # When pad is released, if "something" removed it from the
        # pads_held dict, ignore the action.
        if (row, column) not in self.pads_held:
            return
        del self.pads_held[row, column]
        if self.mode == "PLAY":
            # Did we tap a loop that actually exists?
            loop = self.looper.loops.get((row, column))
            if loop:
                if loop in self.looper.loops_playing:
                    self.looper.loops_playing.remove(loop)
                else:
                    self.looper.loops_playing.add(loop)
        if self.mode == "REC":
            # If we tapped an empty cell, create a new loop
            if (row, column) not in self.looper.loops:
                loop = self.looper.Loop(self.looper, (row, column))
                loop.channel = self.grid.channel
                self.looper.loops[row, column] = loop
            else:
                loop = self.looper.loops[row, column]
            if loop in self.looper.loops_recording:
                self.looper.loops_recording.remove(loop)
            else:
                self.looper.loops_recording.add(loop)
                # FIXME: stop recording other loops on the same channel
        # Update all loopcontrollers to show new state
        for grid in self.grid.griode.grids:
            grid.loopcontroller.draw()

    def button_pressed(self, button):
        if button == "UP":
            self.mode = "PLAY"
        if button == "DOWN":
            self.mode = "REC"
        if button == "LEFT":
            if self.pads_held:
                # Delete!
                for cell in self.pads_held:
                    loop = self.looper.loops.get(cell)
                    if not loop:
                        continue
                    # OK, this is hackish.
                    # We can't easily wipe out an object from the persistence
                    # system, so we re-initialize it to empty values instead.
                    loop.tick_in = loop.tick_out = 0
                    loop.notes.clear()
                    self.looper.loops_playing.discard(loop)
                    self.looper.loops_recording.discard(loop)
                    self.looper.looprefs.discard(cell)
                    del self.looper.loops[cell]
                self.pads_held.clear()
            else:
                # Rewind
                for loop in self.looper.loops_playing:
                    loop.next_tick = loop.tick_in
                for loop in self.looper.loops_recording:
                    loop.next_tick = loop.tick_in
                # FIXME should we also undo the last recording?
        if button == "RIGHT":
            # I'm not sure that this logic should be here,
            # but it should be somewhere, so here we go...
            # When stopping, if any loop doesn't have a
            # tick_out point, add one. (By rounding up to
            # the end of the bar.)
            if self.looper.playing:
                for loop in self.looper.loops_recording:
                    if loop.tick_out == 0:
                        loop.tick_out = 24 * ((loop.tick_out + 23) // 24)
            # And then toggle the playing flag.
            self.looper.playing = not self.looper.playing
        for grid in self.grid.griode.grids:
            grid.loopcontroller.draw()


class LoopEditor(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.loop = None
        self.ticks_per_cell = 12
        self.action = None

    def edit(self, loop):
        self.loop = loop
        self.draw()

    def rc2cell(self, row, column):
        # Map row,column to a cell number (starting at zero)
        return (8-row)*8 + column-1

    def rc2ticks(self, row, column):
        # Return list of ticks in a given cell
        cell = self.rc2cell(row, column)
        return range(cell*self.ticks_per_cell, (cell+1)*self.ticks_per_cell)

    def draw(self):
        if self.loop is None:
            return
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                color = colors.BLACK
                ticks = self.rc2ticks(row, column)
                for tick in ticks:
                    if tick in self.loop.notes:
                        color = colors.GREY_LO
                if self.loop.looper.playing:
                    if self.loop in (self.loop.looper.loops_playing |
                                     self.loop.looper.loops_recording):
                        if self.loop.next_tick in ticks:
                            color = channel_colors[self.loop.channel]
                if self.loop.tick_in in ticks:
                    color = colors.PINK_HI
                if self.loop.tick_out-1 in ticks:
                    color = colors.PINK_HI
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        if self.action == "SET_TICK_IN":
            tick = self.rc2ticks(row, column)[0]
            logging.info("Moving tick_in for loop {} to {}"
                         .format(self.loop, tick))
            self.loop.tick_in = tick
            self.action = None
        elif self.action == "SET_TICK_OUT":
            tick = self.rc2ticks(row, column)[-1] + 1
            logging.info("Moving tick_out for loop {} to {}"
                         .format(self.loop, tick))
            self.loop.tick_out = tick
            self.action = None
        else:
            ticks = self.rc2ticks(row, column)
            if self.loop.tick_out-1 in ticks:
                logging.info("Action is now SET_TICK_OUT")
                self.action = "SET_TICK_OUT"
            elif self.loop.tick_in in ticks:
                logging.info("Action is now SET_TICK_IN")
                self.action = "SET_TICK_IN"
            else:
                for tick in ticks:
                    for note in self.loop.notes.get(tick, []):
                        # FIXME: Send node_off message when the pad is released
                        message = mido.Message(
                            "note_on", channel=self.loop.channel,
                            note=note.note, velocity=note.velocity)
                        self.grid.griode.synth.send(message)
                        self.grid.griode.synth.send(message.copy(velocity=0))
        self.draw()
