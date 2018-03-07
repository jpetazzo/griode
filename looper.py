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


@persistent_attrs(notes={}, channel=None, tick_in=0, tick_out=0)
class Loop(object):
    def __init__(self, looper, cell):
        self.looper = looper
        persistent_attrs_init(self, "{},{}".format(*cell))
        self.next_tick = 0  # next "position" to be played in self.notes


class Flash(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)

    def flash(self, color):
        for led in self.surface:
            if isinstance(led, tuple):
                self.surface[led] = color
        self.grid.focus(self)
        time.sleep(0.3)
        self.grid.focus(self.grid.notepickers[self.grid.channel])


class Teacher(object):

    def __init__(self, looper):
        self.looper = looper
        self.teacher_loop = None
        self.student_loop = Loop(looper, "student")
        self.phase = "STOP"     # "TEACHER" "STUDENT"

    def select(self, loop):
        self.teacher_loop = loop
        self.student_loop.channel = loop.channel
        for grid in self.looper.griode.grids:
            grid.channel = loop.channel
            grid.focus(grid.notepickers[grid.channel])
            grid.flash = Flash(grid)  # FIXME
        self.tick_interval = 8 * 24  # Two bars
        self.tick_in = 0
        self.tick_out = self.tick_in + self.tick_interval
        loop.tick_in = 0
        loop.tick_out = 0       # Do not loop that!
        self.flash(colors.YELLOW)
        self.teacher()

    def flash(self, color):
        for grid in self.looper.griode.grids:
            grid.flash.flash(color)

    def stop(self):
        self.phase = "STOP"
        logging.debug("phase=STOP")
        self.looper.playing = False
        self.looper.loops_playing.clear()
        self.looper.loops_recording.clear()

    def teacher(self):
        self.phase = "TEACHER"
        logging.debug("phase=TEACHER")
        self.looper.playing = False
        self.looper.loops_recording.clear()
        self.looper.loops_playing.clear()
        self.looper.loops_playing.add(self.teacher_loop)
        self.teacher_loop.next_tick = self.tick_in
        self.teacher_notes = []
        for tick in range(self.tick_in, self.tick_out):
            for note in self.teacher_loop.notes.get(tick, []):
                self.teacher_notes.append(note.note)
        if self.teacher_notes == []:
            # A silence long enough will be interpreted as end of song
            self.stop()
        else:
            self.flash(colors.BLACK)
            self.looper.playing = True

    def student(self):
        self.phase = "STUDENT"
        logging.debug("phase=STUDENT")
        self.looper.playing = False
        self.student_loop.notes.clear()
        self.student_loop.next_tick = 0
        self.looper.loops_recording.add(self.student_loop)
        self.looper.loops_playing.clear()
        self.flash(colors.YELLOW)
        self.looper.playing = True

    def tick(self, tick):
        if self.phase == "TEACHER":
            if self.teacher_loop.next_tick >= self.tick_out:
                self.student()
        if self.phase == "STUDENT":
            # Once per beat, check how we did in this loop
            if tick%24 == 0:
                student_notes = []
                for tick in self.student_loop.notes:
                    for note in self.student_loop.notes.get(tick, []):
                        if note.duration > 0:
                            student_notes.append(note.note)
                if student_notes == self.teacher_notes:
                    # Yay!
                    logging.info("Got the right notes!")
                    self.flash(colors.GREEN)
                    self.tick_in += self.tick_interval
                    self.tick_out += self.tick_interval
                    self.teacher()
                elif (any(x!=y for x, y in zip(self.teacher_notes, student_notes))
                      or
                      len(student_notes) > len(self.teacher_notes)
                      or
                      self.student_loop.next_tick >= 2*self.tick_interval):
                    # Bzzzt wrong
                    logging.info("Bzzzt try again!")
                    logging.info("Teacher notes: {}"
                                 .format(self.teacher_notes))
                    logging.info("Student notes: {}"
                                 .format(student_notes))
                    self.flash(colors.RED)
                    self.teacher()


@persistent_attrs(beats_per_bar=4)
class Looper(object):

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
        self.teacher = Teacher(self)
        for row in range(1, 9):
            for column in range(1, 9):
                self.loops[row, column] = Loop(self, (row, column))

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
        # FIXME force a sync of loop data but spread that over time
        row = tick % 10
        column = tick//10 % 10
        loop = self.loops.get((row, column))
        if loop is not None:
            if loop.channel is not None:
                logging.debug("Syncing loop {},{} ({} ticks)"
                              .format(row, column, len(loop.notes)))
                loop.db.sync()
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
        # Teacher logic
        self.teacher.tick(tick)

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
        self.stepsequencer = StepSequencer(grid)
        self.mode = "LEARN"  # or "REC" or "PLAY"
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
                loop = self.looper.loops[led]
                if loop.channel is not None:
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
                self.loopeditor.loop = loop
                self.grid.focus(self.loopeditor)
                break
        self.draw()
        self.loopeditor.draw()
        self.stepsequencer.draw()

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
            loop = self.looper.loops[row, column]
            # Does that loop actually exist?
            if loop.channel is not None:
                if loop in self.looper.loops_playing:
                    self.looper.loops_playing.remove(loop)
                else:
                    self.looper.loops_playing.add(loop)

        if self.mode == "REC":
            loop = self.looper.loops[row, column]
            # If we tapped an empty cell, create a new loop
            if loop.channel is None:
                loop.channel = self.grid.channel
            if loop in self.looper.loops_recording:
                self.looper.loops_recording.remove(loop)
            else:
                self.looper.loops_recording.add(loop)
                # FIXME: stop recording other loops on the same channel

        if self.mode == "LEARN":
            loop = self.looper.loops[row, column]
            if loop.channel is not None:
                self.looper.teacher.select(loop)

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
                    # OK, this is hackish.
                    # We can't easily wipe out an object from the persistence
                    # system, so we re-initialize it to empty values instead.
                    loop = self.looper.loops[cell]
                    loop.channel = None
                    loop.tick_in = loop.tick_out = 0
                    loop.notes.clear()
                    self.looper.loops_playing.discard(loop)
                    self.looper.loops_recording.discard(loop)
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


class CellPicker(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.ticks_per_cell = 12
        self._loop = None

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value):
        self._loop = value
        self.draw()

    def rc2cell(self, row, column):
        # Map row,column to a cell number (starting at zero)
        return (8-row)*8 + column-1

    def rc2ticks(self, row, column):
        # Return list of ticks in a given cell
        cell = self.rc2cell(row, column)
        return range(cell*self.ticks_per_cell, (cell+1)*self.ticks_per_cell)


class LoopEditor(CellPicker):

    def __init__(self, grid):
        super().__init__(grid)
        self.action = None

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
            if self.loop.tick_out == 0 and 0 in ticks:
                logging.info("Action is now SET_TICK_OUT (initial)")
                self.action = "SET_TICK_OUT"
            elif self.loop.tick_out-1 in ticks:
                logging.info("Action is now SET_TICK_OUT")
                self.action = "SET_TICK_OUT"
            elif self.loop.tick_in in ticks:
                logging.info("Action is now SET_TICK_IN")
                self.action = "SET_TICK_IN"
            else:
                for tick in ticks:
                    for note in self.loop.notes.get(tick, []):
                        # FIXME: Send note_off message when the pad is released
                        message = mido.Message(
                            "note_on", channel=self.loop.channel,
                            note=note.note, velocity=note.velocity)
                        self.grid.griode.synth.send(message)
                        self.grid.griode.synth.send(message.copy(velocity=0))
        self.draw()

    def button_pressed(self, button):
        if button == "UP":
            self.grid.focus(self.grid.loopcontroller)
        if button == "DOWN":
            self.grid.loopcontroller.stepsequencer.loop = self.loop  # FIXME urgh
            self.grid.focus(self.grid.loopcontroller.stepsequencer)

class StepSequencer(CellPicker):

    def __init__(self, grid):
        super().__init__(grid)
        self.note = None

    @property
    def notepicker(self):
        return self.grid.notepickers[self.grid.channel]

    def draw(self):
        if self.loop is None:
            return
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if row in [1, 2, 3, 4]:
                    color = self.notepicker.surface[led]
                    if self.note is not None:
                        if self.note == self.notepicker.led2note[row, column]:
                            color = colors.PINK_HI
                else:
                    color = colors.BLACK
                    ticks = self.rc2ticks(row, column)
                    # Show if there are notes in this cell
                    has_first = bool(self.loop.notes.get(ticks[0]))
                    has_other = any(bool(self.loop.notes.get(tick))
                                    for tick in ticks[1:])
                    if has_first and has_other:
                        color = colors.GREY_LO
                    if has_first and not has_other:
                        color = colors.WHITE
                    if not has_first and has_other:
                        color = colors.GREY_LO
                    # And now, override that color if the current note is there
                    for note in self.loop.notes.get(ticks[0], []):
                        if note.note == self.note:
                            color = colors.PINK_HI
                    # But override even more to show the current play position
                    if self.loop.looper.playing:
                        if self.loop in (self.loop.looper.loops_playing |
                                         self.loop.looper.loops_recording):
                            if self.loop.next_tick in ticks:
                                color = colors.AMBER_HI
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if row in [1, 2, 3, 4]:
            self.notepicker.pad_pressed(row, column, velocity)
            self.note = self.notepicker.led2note[row, column]
            self.draw()
        else:
            if velocity == 0:
                return
            if self.note is None:
                return
            ticks = self.rc2ticks(row, column)
            for note in self.loop.notes.get(ticks[0], []):
                if note.note == self.note:
                    self.loop.notes[ticks[0]].remove(note)
                    break
            else:
                if ticks[0] not in self.loop.notes:
                    self.loop.notes[ticks[0]] = []
                self.loop.notes[ticks[0]].append(
                    Note(note=self.note, velocity=velocity, duration=self.ticks_per_cell))

    def button_pressed(self, button):
        if button == "UP":
            self.grid.focus(self.grid.loopcontroller.loopeditor)
