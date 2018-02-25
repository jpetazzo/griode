import enum
import logging
import mido

import colors
from gridgets import Gridget, Surface, channel_colors, on_off_colors
from persistence import persistent_attrs, persistent_attrs_init

"""
The arpeggiator config has multiple screens.

You scroll between the different screens with UP/DOWN.

ARPSETUP:
E......T -> Enable/disable arp; tempo monitor
........
BBBBBBBB -> watch arp steps (to monitor speed); change speed/interval
........
.X...X.. \
...X...X  \ note order (use LEFT/RIGHT to change order)
X...X...  /
..X...X. /

MOTIFSETUP:
....X... \
..X..X..  } when in scale mode, use first/lowest/highest/last note played
...X.... /  as the root of the scale (use LEFT/RIGHT to change)
........
XX.XXXX.
XXXXXXXS -> Select scale mode
........
X.X.X.XS -> Select "notes played" mode

VELOGATE: assign velocity and gate values.
VVVVVVVV \
VVVVVVVV  \ Configure velocity level of each step
VVVVVVVV  /
VVVVVVVV /
GGGGGGGG \
GGGGGGGG  } Configure gate (note length) for each step
GGGGGGGG /
EEEEEEEE -> Enable or disable steps

MOTIF: configure a melodic motif.
........
........
........
........
........ = ...
........ = 3rd
........ = 2nd
........ = root note (selected by default)
"""


class Page(enum.Enum):
    MOTIFSETUP = 1
    ARPSETUP = 2
    VELOGATE = 3
    MOTIF = 4


class NoteOrder(enum.Enum):  # When a note is added, it should be played ...
    FIRST = 1                # - as soon as possible
    LAST = 2                 # - after all other notes
    ASCENDING = 3            # - in ascending order (playing upward arpeggio)
    DESCENDING = 4           # - in descending order (downward arpeggio)
    BOUNCING = 5             # - we're playing up-then-down-then-up arpeggio


class MotifMode(enum.Enum):
    DISABLED = 1  # Do not use the motif, just spell out notes in buffer
    SCALE = 2     # Use the motif, mapping steps to the current scale
    BUFFER = 3    # Use the motif, mapping steps to the notes buffer


class ScaleKey(enum.Enum):  # Which note will be the root of the scale?
    FIRST = 1               # - the first note in the buffer
    LAST = 2                # - the last note in the buffer
    LOWER = 3               # - the lowest note in the buffer
    HIGHER = 4              # - the highest note in the buffer
    NEXT = 5                # - the next note in the buffer


@persistent_attrs(
    enabled=False, interval=6, pattern_length=4,
    pattern=[[4, 3, [0]], [1, 2, [0]], [3, 1, [0]], [1, 2, [0]]],
    note_order=NoteOrder.FIRST,
    motif_mode=MotifMode.DISABLED,
    scale_key=ScaleKey.FIRST,
)
class Arpeggiator(object):

    def __init__(self, devicechain):
        self.devicechain = devicechain
        persistent_attrs_init(self, str(devicechain.channel))
        self.notes = []
        self.next_note = 0  # That's a position in self.notes
        self.direction = 1  # Always 1, except when in BOUNCING mode
        self.latch_notes = set()
        self.playing = []
        self.next_step = 0  # That's a position in self.pattern
        self.next_tick = 0  # Note: next_tick==0 also means "NOW!"

    def tick(self, tick):
        # OK, first, let's see if some notes are currently playing,
        # but should be stopped.
        for note, deadline in self.playing:
            if tick > deadline:
                self.output(mido.Message("note_on", note=note, velocity=0))
                self.playing.remove((note, deadline))

        # If we're disabled, stop right there
        if not self.enabled:
            self.notes.clear()
            return
        # If it's not time yet to spell out the next note, stop right there
        if tick < self.next_tick:
            return
        # If there are no notes in the buffer (=pressed), stop right there
        if self.notes == []:
            return
        # If we just got "woken up" set next_tick to the correct value
        if self.next_tick == 0:
            self.next_tick = tick

        # Yay it's time to spell out the next note(s)!
        logging.debug("next_step={} -> {}"
                      .format(self.next_step, self.pattern[self.next_step]))
        velocity, gate, motif = self.pattern[self.next_step]
        velocity = velocity*31
        duration = gate*self.interval//3
        if self.motif_mode == MotifMode.DISABLED:
            # Do not use a scale, or rather, use a one-note scale.
            # (This way, Motif will trigger octaves.)
            scale = [self.notes[self.next_note]]
        if self.motif_mode == MotifMode.BUFFER:
            # Use the buffer as a scale to play from.
            scale = self.notes
        if self.motif_mode == MotifMode.SCALE:
            # OK, we want to use the current (global) scale.
            # But we have to determine the root note.
            if self.scale_key == ScaleKey.FIRST:
                key = self.notes[0]
            if self.scale_key == ScaleKey.LAST:
                key = self.notes[-1]
            if self.scale_key == ScaleKey.LOWER:
                key = min(self.notes)
            if self.scale_key == ScaleKey.HIGHER:
                key = max(self.notes)
            if self.scale_key == ScaleKey.NEXT:
                key = self.notes[self.next_note]
            scale = [key+note for note in self.devicechain.griode.scale]

        logging.debug("computed scale: {}".format(scale))
        # OK, now we have a scale. Let's map the motif to the scale.
        for step in motif:
            octave = 0
            # If the step is too high, jump as many octaves higher as necessary
            while step >= len(scale):
                octave += 1
                step -= len(scale)
            # If the step is too low (i.e. negative), jump a few octaves down
            while step < 0:
                octave -= 1
                step += len(scale)
            note = scale[step] + 12*octave
            # Make sure that the note stays within the MIDI range
            while note > 127:
                note -= 12
            while note < 0:
                note += 12
            logging.debug("playing note={} velo={} duration={}"
                          .format(note, velocity, duration))
            self.output(mido.Message("note_on", note=note, velocity=velocity))
            self.playing.append((note, tick+duration))

        # Cycle to the next position in the notes buffer.
        self.next_note += self.direction
        # If we are past the beginning of the buffer...
        # (This happens only in BOUNCING mode.)
        if self.next_note < 0:
            # Just go back the other way.
            self.next_note = 1
            self.direction = 1
        # If we are past the end of the buffer...
        if self.next_note >= len(self.notes):
            # Special case for bouncing mode: go back down!
            if self.note_order == NoteOrder.BOUNCING:
                self.direction = -1
                self.next_note -= 2
                # Handle the case where there is only one note in the buffer
                if self.next_note < 0:
                    self.next_note = 0
            else:
                self.next_note = 0

        # Update displays
        for grid in self.devicechain.griode.grids:
            arpconfig = grid.arpconfigs[self.devicechain.channel]
            arpconfig.current_step = self.next_step
            arpconfig.draw()
        # And prepare for next step
        self.next_tick += self.interval
        self.next_step += 1
        if self.next_step >= self.pattern_length:
            self.next_step = 0

    def send(self, message):
        if message.type == "note_on" and self.enabled:
            if message.velocity > 0:
                # If this is the first note played, "wake up" the arpeggiator.
                if self.notes == []:
                    self.next_tick = 0
                    self.next_step = 0
                    self.notes.append(message.note)
                else:
                    # Add the note.
                    # The position where we add it depends of NoteOrder.
                    if self.note_order == NoteOrder.FIRST:
                        self.notes.insert(self.next_note, message.note)
                    if self.note_order == NoteOrder.LAST:
                        if self.next_note == 0:
                            self.notes.append(message.note)
                        else:
                            self.notes.insert(self.next_note-1)
                    if self.note_order == NoteOrder.ASCENDING:
                        self.notes.append(message.note)
                        self.notes.sort()
                        # FIXME fix up self.next_note
                    if self.note_order == NoteOrder.DESCENDING:
                        self.notes.append(message.note)
                        self.notes.sort()
                        self.notes.reverse()
                        # FIXME fix up self.next_note
                    if self.note_order == NoteOrder.BOUNCING:
                        self.notes.append(message.note)
                        self.notes.sort()
                        if self.direction == -1:
                            self.notes.reverse()
                        # FIXME fix up self.next_note
            else:
                if message.note in self.notes:
                    index = self.notes.index(message.note)
                    if self.next_note > index:
                        self.next_note -= 1
                    self.notes.remove(message.note)
                    if self.next_note >= len(self.notes):
                        self.next_note = 0
        else:
            self.output(message)

    def output(self, message):
        message = message.copy(channel=self.devicechain.channel)
        self.devicechain.griode.synth.send(message)


class ArpConfig(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.current_step = 0
        self.display_offset = 0  # Step shown on first column
        self.page = Page.VELOGATE
        self.surface = Surface(grid.surface)
        self.surface["UP"] = channel_colors[self.channel]
        self.surface["DOWN"] = channel_colors[self.channel]
        self.surface["LEFT"] = channel_colors[self.channel]
        self.surface["RIGHT"] = channel_colors[self.channel]
        self.draw()

    @property
    def arpeggiator(self):
        return self.grid.griode.devicechains[self.channel].arpeggiator

    def draw(self):
        if self.page in [Page.MOTIF, Page.VELOGATE]:
            self.draw_steps()
        if self.page == Page.ARPSETUP:
            self.draw_arpsetup()
        if self.page == Page.MOTIFSETUP:
            self.draw_motifsetup()

    def draw_arpsetup(self):
        for led in self.surface:
            if isinstance(led, tuple):
                color = colors.BLACK
                if led == (8, 1):
                    color = on_off_colors[self.arpeggiator.enabled]
                row, column = led
                def color_enum(klass, column, value):
                    if column == value:
                        return colors.PINK_HI
                    if column in [e.value for e in klass]:
                        return colors.ROSE
                    return colors.BLACK
                if row == 6:
                    color = color_enum(NoteOrder, column, self.arpeggiator.note_order.value)
                if row == 4:
                    color = color_enum(MotifMode, column, self.arpeggiator.motif_mode.value)
                if row == 2:
                    color = color_enum(ScaleKey, column, self.arpeggiator.scale_key.value)
                self.surface[led] = color

    def draw_steps(self):
        for led in self.surface:
            if isinstance(led, tuple):
                color = colors.BLACK
                row, column = led
                step = column - 1 + self.display_offset
                if step >= self.arpeggiator.pattern_length:
                    if row == 1:
                        color = colors.GREEN_LO
                else:
                    velocity, gate, harmonies = self.arpeggiator.pattern[step]
                    if self.page == Page.VELOGATE:
                        if row == 1:
                            if step == self.current_step:
                                color = colors.AMBER
                            else:
                                color = colors.GREEN_HI
                        if row in [2, 3, 4]:
                            if gate > row-2:
                                if harmonies:
                                    color = colors.SPRING
                                else:
                                    color = colors.GREY_LO
                        if row in [5, 6, 7, 8]:
                            if velocity > row-5:
                                if harmonies:
                                    color = colors.LIME
                                else:
                                    color = colors.GREY_LO
                    if self.page == Page.MOTIF:
                        if row-1 in harmonies:
                            if step == self.current_step:
                                color = colors.AMBER
                            else:
                                if velocity < 2:
                                    color = colors.GREY_LO
                                else:
                                    color = colors.GREEN
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        step = column - 1 + self.display_offset
        if self.page == Page.VELOGATE:
            if row == 1:
                while len(self.arpeggiator.pattern) <= step:
                    self.arpeggiator.pattern.append([1, 1, [0]])
                self.arpeggiator.pattern_length = step+1
            if row in [2, 3, 4]:
                self.arpeggiator.pattern[step][1] = row-1
            if row in [5, 6, 7, 8]:
                self.arpeggiator.pattern[step][0] = row-4
        if self.page == Page.MOTIF:
            harmony = row-1
            if harmony in self.arpeggiator.pattern[step][2]:
                self.arpeggiator.pattern[step][2].remove(harmony)
            else:
                self.arpeggiator.pattern[step][2].append(harmony)
        if self.page == Page.ARPSETUP:
            if (row, column) == (8, 1):
                self.arpeggiator.enabled = not self.arpeggiator.enabled
            if row == 6:
                self.arpeggiator.note_order = NoteOrder(column)
            if row == 4:
                self.arpeggiator.motif_mode = MotifMode(column)
            if row == 2:
                self.arpeggiator.scale_key = ScaleKey(column)
            if row == 1:
                self.arpeggiator.interval = [None, 24, 16, 12, 8, 6, 4, 3, 2][column]

            self.draw()

    def button_pressed(self, button):
        # FIXME: don't go up/down if we're already all the way up/down
        if button == "UP":
            self.page = Page(self.page.value-1)
            self.draw()
        if button == "DOWN":
            self.page = Page(self.page.value+1)
            self.draw()
        if button == "LEFT":
            if self.display_offset > 0:
                self.display_offset -= 1
                self.draw()
        if button == "RIGHT":
            if self.display_offset < self.arpeggiator.pattern_length - 2:
                self.display_offset += 1
                self.draw()
