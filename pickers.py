import collections
import enum
import logging
import mido

import scales
from gridgets import Gridget, Surface
from palette import palette
from persistence import persistent_attrs, persistent_attrs_init


DRUMKIT_MAPPINGS = dict(
    FOUR_FOUR = [
        [55, 49, 56, 57],
        [41, 43, 47, 50],
        [40, 38, 46, 53],
        [37, 36, 42, 51],
    ],
    FOUR_EIGHT = [
        [49, 57, 55, 52, 53, 59, 51, None],
        [50, 48, 47, 45, 43, 41, None, 46],
        [40, 38, 37, None, 39, 54, None, 42],
        [36, 35, None, None, 75, 56, None, 44],
    ],
)


class Melodic(enum.Enum):
    CHROMATIC = 1
    DIATONIC = 2
    MAGIC = 3


Drumkit = enum.Enum("Drumkit", list(DRUMKIT_MAPPINGS.keys()))



@persistent_attrs(root=48,
                  drumkit_mapping=Drumkit.FOUR_EIGHT,
                  melodic_mapping=Melodic.CHROMATIC)
class NotePicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.surface = Surface(grid.surface)
        for button in "UP DOWN LEFT RIGHT".split():
            self.surface[button] = palette.CHANNEL[channel]
        self.channel = channel
        persistent_attrs_init(self, "{}__{}".format(self.grid.grid_name, channel))
        self.led2note = {}
        self.note2leds = collections.defaultdict(list)
        devicechain = self.grid.griode.devicechains[self.grid.channel]
        if devicechain.instrument.is_drumkit:
            self.mapping = self.drumkit_mapping
        else:
            self.mapping = self.melodic_mapping
        self.switch()

    @property
    def key(self):
        return self.grid.griode.key

    @property
    def scale(self):
        return self.grid.griode.scale

    def mode(self, is_drumkit):
        if is_drumkit:
            self.mapping = self.drumkit_mapping
        else:
            self.mapping = self.melodic_mapping
        self.switch()

    def cycle(self):
        m = self.mapping
        try:
            self.mapping = m.__class__(m.value+1)
        except ValueError:
            self.mapping = m.__class__(1)
        self.switch()

    def switch(self):
        # If we are in diatonic mode, we force the root key to be the root
        # of the scale, otherwise the whole screen will be off.
        # FIXME: allow to shift the diatonic mode.
        if self.mapping == Melodic.DIATONIC:
            root = self.root//12 * 12 + self.grid.griode.key
        else:
            root = self.root
        self.led2note.clear()
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if self.mapping == Melodic.CHROMATIC:
                    shift = 5
                    note = shift*(row-1) + (column-1)
                    note += root
                elif self.mapping == Melodic.DIATONIC:
                    shift = 3
                    note = shift*(row-1) + (column-1)
                    octave = note//len(self.scale)
                    step = note%len(self.scale)
                    note = root + 12*octave + self.scale[step]
                elif self.mapping == Melodic.MAGIC:
                    note = (column-1)*7 - (column-1)//2*12
                    note += (row-1)*4
                    note += root
                elif isinstance(self.mapping, Drumkit):
                    padmap = DRUMKIT_MAPPINGS[self.mapping.name]
                    try:
                        note = padmap[::-1][row-1][column-1]
                    except IndexError:
                        note = None
                self.led2note[led] = note
        self.note2leds.clear()
        for led, note in self.led2note.items():
            if note not in self.note2leds:
                self.note2leds[note] = []
            self.note2leds[note].append(led)
        self.draw()

    def is_key(self, note):
        return note%12 == self.key%12

    def is_in_scale(self, note):
        scale = [ (self.key + n)%12 for n in self.scale ]
        return note%12 in scale

    def note2color(self, note):
        # For drumkit, just show which notes are mapped.
        if isinstance(self.mapping, Drumkit):
            if note is not None:
                return palette.CHANNEL[self.channel]
            else:
                return palette.BLACK

        # For other layouts, properly show notes that are in scale.
        if self.is_key(note):
            return palette.CHANNEL[self.channel]
        if self.is_in_scale(note):
            return palette.INSCALE[self.channel]
        return palette.BLACK

    def draw(self):
        for led in self.surface:
            if led in self.led2note:
                note = self.led2note[led]
                color = self.note2color(note)
                self.surface[led] = color

    def button_pressed(self, button):
        # FIXME allow to change layout for DRUMKIT? Or?
        if button == "UP":
            self.root += 12
        elif button == "DOWN":
            self.root -= 12
        elif button == "LEFT":
            self.root -= 1
        elif button == "RIGHT":
            self.root += 1
        self.switch()

    def pad_pressed(self, row, column, velocity):
        note = self.led2note[row, column]
        if note is None:
            return
        # Velocity curve (this is kind of a hack for now)
        # FIXME this probably should be moved to the devicechains
        if velocity > 0:
            velocity = 63 + velocity//2
        # Send that note to the message chain
        message = mido.Message(
            "note_on", channel=self.channel,
            note=note, velocity=velocity)
        self.grid.griode.devicechains[self.channel].send(message)
        # Then light up all instrumentpickers
        for grid in self.grid.griode.grids:
            picker = grid.notepickers[self.channel]
            picker.send(message, self)

    def send(self, message, source_object):
        if message.type == "note_on":
            if message.velocity == 0:
                color = self.note2color(message.note)
            elif source_object == self:
                color = palette.PLAY[0]
            else:
                color = palette.PLAY[1]
            leds = self.note2leds[message.note]
            for led in leds:
                self.surface[led] = color

##############################################################################

class InstrumentPicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.surface = Surface(grid.surface)
        self.surface["UP"] = palette.CHANNEL[channel]
        self.surface["DOWN"] = palette.CHANNEL[channel]
        if channel > 0:
            self.surface["LEFT"] = palette.CHANNEL[channel-1]
        if channel < 15:
            self.surface["RIGHT"] = palette.CHANNEL[channel+1]
        self.draw()

    @property
    def devicechain(self):
        return self.grid.griode.devicechains[self.channel]

    @property
    def fonts(self):
        return self.grid.griode.synth.fonts

    @property
    def groups(self):
        return self.fonts.get(self.devicechain.font_index, self.fonts[None])

    @property
    def instrs(self):
        return self.groups.get(self.devicechain.group_index, self.groups[None])

    @property
    def banks(self):
        return self.instrs.get(self.devicechain.instr_index, self.instrs[None])

    def draw(self):
        leds = self.get_leds()
        for led in self.surface:
            if led in leds:
                self.surface[led] = leds[led]
            elif isinstance(led, tuple):
                color = palette.BLACK
                row, column = led
                if row == 8:
                    font_index = column-1
                    if font_index in self.fonts:
                        color = palette.BANK[0]
                if row in [6, 7]:
                    color = palette.GROUP[0]
                if row == 5:
                    color = palette.INSTR[0]
                if row == 4:
                    bank_index = column-1
                    if bank_index in self.banks:
                        color = palette.VAR[0]
                if row in [1, 2, 3]:
                    color = self.grid.notepickers[self.channel].surface[led]
                self.surface[led] = color

    def get_leds(self):
        # Which leds are supposed to be ON for the current instrument
        leds = {}
        instrument = self.devicechain.instrument
        group_index = instrument.program//8
        instr_index = instrument.program%8
        for led in [
                (8, 1+instrument.font_index),
                (7-(group_index//8), 1+group_index%8),
                (5, 1+instr_index),
                (4, 1+instrument.bank_index)]:
            leds[led] = palette.ACTIVE
        return leds

    def pad_pressed(self, row, col, velocity):
        current_is_drumkit = self.devicechain.instrument.is_drumkit
        if row in [1, 2, 3]:
            self.grid.notepickers[self.channel].pad_pressed(row, col, velocity)
            return
        if velocity == 0:
            return
        if self.surface[row, col] == palette.BLACK:
            return
        if row==8:
            self.devicechain.font_index = col-1
        if row==7:
            self.devicechain.group_index = col-1
        if row==6:
            self.devicechain.group_index = 8+col-1
        if row==5:
            self.devicechain.instr_index = col-1
        if row==4:
            self.devicechain.bank_index = col -1
        # Switch to new instrument
        self.devicechain.program_change()
        # Repaint
        self.draw()
        # If we switched from melodic to rhythmic, update NotePicker
        new_is_drumkit = self.devicechain.instrument.is_drumkit
        if current_is_drumkit != new_is_drumkit:
            self.grid.notepickers[self.channel].mode(new_is_drumkit)

    def button_pressed(self, button):
        if button == "LEFT" and self.channel>0:
            self.grid.channel = self.channel-1
            self.grid.focus(self.grid.instrumentpickers[self.channel-1])
        if button == "RIGHT" and self.channel<15:
            self.grid.channel = self.channel+1
            self.grid.focus(self.grid.instrumentpickers[self.channel+1])
        if button in ["UP", "DOWN"]:
            instruments = self.grid.griode.synth.instruments
            instrument_index = instruments.index(self.devicechain.instrument)
            if button == "UP":
                instrument_index -= 1
            else:
                instrument_index += 1
            if instrument_index < 0:
                instrument = instruments[-1]
            elif instrument_index >= len(instruments):
                instrument = instruments[0]
            else:
                instrument = instruments[instrument_index]
                self.devicechain.font_index = instrument.font_index
                self.devicechain.group_index = instrument.program//8
                self.devicechain.instr_index = instrument.program%8
                self.devicechain.bank_index = instrument.bank_index
            self.devicechain.program_change()
            self.draw()


##############################################################################

class ScalePicker(Gridget):
    """
    ##.###.. sharp of the key below
    CDEFGAB. pick key
    ........
    ##.###.. sharp of the key below
    CDEFGABX keys in scale; X = play the scale
    ........
    XXXXXXXX modes
    XXXXXXXX scales
    """

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.draw()

    def draw(self):
        leds = self.get_leds()
        for led in self.surface:
            if led in leds:
                self.surface[led] = leds[led]
            elif isinstance(led, tuple):
                row, column = led
                color = palette.BLACK
                if row == 8 and column in [1, 2, 4, 5, 6]:
                    color = palette.SCALEROOT
                if row == 7 and column != 8:
                    color = palette.SCALEROOT
                if row == 5 and column in [1, 2, 4, 5, 6]:
                    color = palette.SCALENOTES
                if row == 4 and column != 8:
                    color = palette.SCALENOTES
                if row == 4 and column == 8:
                    color = palette.TRIG
                if row == 2 or row == 1:
                    try:
                        scales.palette[row-1][column-1]
                        color = palette.SCALEPICK
                    except IndexError:
                        pass
                self.surface[led] = color

    def get_leds(self):
        leds = {}

        key = self.grid.griode.key

        row, column = note2piano[key]
        leds[row+6, column] = palette.ACTIVE

        current_scale = self.grid.griode.scale
        for note in current_scale:
            row, column = note2piano[note]
            leds[row+3, column] = palette.ACTIVE

        for row, line in enumerate(scales.palette):
            for column, scale in enumerate(line):
                if scale == tuple(current_scale):
                    leds[row+1, column+1] = palette.ACTIVE

        return leds

    def cue(self, notes):
        duration = 12  # In ticks
        send = self.grid.griode.synth.send
        cue = self.grid.griode.clock.cue
        for i, note in enumerate(notes):
            message = mido.Message("note_on", channel=self.grid.channel,
                                   note=48+note, velocity=96)
            cue(duration*i, send, (message, ))
            cue(duration*(i+1), send, (message.copy(velocity=0), ))

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return

        # Change the key in which we're playing
        if row in [7, 8]:
            note = piano2note.get((row-6, column))
            if note is not None:
                self.cue([note])
                self.grid.griode.key = note

        # Manually tweak the scale
        if row in [4, 5]:
            note = piano2note.get((row-3, column))
            if note is not None:
                self.cue([note+self.grid.griode.key])
                if note != 0:  # Do not remove the first note of the scale!
                    if note in self.grid.griode.scale:
                        self.grid.griode.scale.remove(note)
                    else:
                        self.grid.griode.scale.append(note)
                        self.grid.griode.scale.sort()

        # Play the current scale
        if (row, column) == (4, 8):
            scale = [self.grid.griode.key + n
                     for n in self.grid.griode.scale + [12]]
            self.cue(scale)

        # Pick a scale from the palette
        if row in [1, 2]:
            try:
                scale = scales.palette[row-1][column-1]
                self.grid.griode.scale = list(scale)
            except IndexError:
                pass

        self.draw()
        for grid in self.grid.griode.grids:
            for notepicker in grid.notepickers:
                notepicker.draw()


# Maps notes to a pseudo-piano layout
# (with black keys on the top row and white keys on the bottom row)

note2piano = [
    (1, 1), (2, 1), (1, 2), (2, 2), (1, 3),
    (1, 4), (2, 4), (1, 5), (2, 5), (1, 6), (2, 6), (1, 7)
]

piano2note = { (r, c): n for (n, (r, c)) in enumerate(note2piano) }

##############################################################################

class ColorPicker(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                color = (row-1)*8 + column-1
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity > 0:
            color = (row-1)*8 + column-1
            print("Color #{}".format(color))
