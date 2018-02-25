import collections
import logging
import mido

import colors
import scales
from gridgets import Gridget, Surface, channel_colors
from persistence import persistent_attrs, persistent_attrs_init

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
            print("Color #{} ({})".format(color, colors.by_number[color]))

##############################################################################

FOUR_FOUR_MAP = [
    [55, 49, 56, 57],
    [41, 43, 47, 50],
    [40, 38, 46, 53],
    [37, 36, 42, 51],
]
FOUR_EIGHT_MAP = [
    [49, 57, 55, 52, 53, 59, 51, None],
    [50, 48, 47, 45, 43, 41, None, 46],
    [40, 38, 37, None, 39, 54, None, 42],
    [36, 35, None, None, 75, 56, None, 44],
]

##############################################################################

@persistent_attrs(root=48, mapping="CHROMATIC")
class NotePicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.surface = Surface(grid.surface)
        for button in "UP DOWN LEFT RIGHT".split():
            self.surface[button] = channel_colors[channel]
        self.channel = channel
        persistent_attrs_init(self, "{}__{}".format(self.grid.grid_name, channel))
        self.led2note = {}
        self.note2leds = collections.defaultdict(list)
        self.switch()

    @property
    def key(self):
        return self.grid.griode.key

    @property
    def scale(self):
        return self.grid.griode.scale

    def switch(self, mapping=None):
        logging.info("NotePicker.switch({})".format(mapping))
        if mapping is None:
            mapping = self.mapping
        else:
            self.mapping = mapping
        # If we are in diatonic mode, we force the root key to be the root
        # of the scale, otherwise the whole screen will be off.
        # FIXME: allow to shift the diatonic mode.
        if mapping == "DIATONIC":
            root = self.root//12 * 12 + self.grid.griode.key
        else:
            root = self.root
        self.led2note.clear()
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if mapping == "CHROMATIC":
                    shift = 5
                    note = shift*(row-1) + (column-1)
                    note += root
                elif mapping == "DIATONIC":
                    shift = 3
                    note = shift*(row-1) + (column-1)
                    octave = note//len(self.scale)
                    step = note%len(self.scale)
                    note = root + 12*octave + self.scale[step]
                elif mapping == "MAGIC":
                    note = (column-1)*7 - (column-1)//2*12
                    note += (row-1)*4
                    note += root
                elif mapping == "DRUMKIT":
                    try:
                        note = FOUR_EIGHT_MAP[::-1][row-1][column-1]
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
        if self.mapping == "DRUMKIT":
            if note is not None:
                return channel_colors[self.channel]
            else:
                return colors.BLACK

        # For other layouts, properly show notes that are in scale.
        if self.is_key(note):
            return channel_colors[self.channel]
        if self.is_in_scale(note):
            return colors.GREY_LO
        return colors.BLACK

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
        self.grid.griode.looper.send(message)
        # Then light up all instrumentpickers
        for grid in self.grid.griode.grids:
            picker = grid.notepickers[self.channel]
            picker.send(message, self)

    def send(self, message, source_object):
        if message.type == "note_on":
            if message.velocity == 0:
                color = self.note2color(message.note)
            elif source_object == self:
                color = colors.RED
            else:
                color = colors.AMBER
            leds = self.note2leds[message.note]
            for led in leds:
                self.surface[led] = color

##############################################################################

class InstrumentPicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.surface = Surface(grid.surface)
        self.surface["UP"] = channel_colors[channel]
        self.surface["DOWN"] = channel_colors[channel]
        if channel > 0:
            self.surface["LEFT"] = channel_colors[channel-1]
        if channel < 15:
            self.surface["RIGHT"] = channel_colors[channel+1]
        self.draw()

    @property
    def devicechain(self):
        return self.grid.griode.devicechains[self.channel]

    @property
    def fonts(self):
        return self.grid.griode.synth.fonts

    @property
    def groups(self):
        return self.fonts.get(self.devicechain.font_index, self.fonts[0])

    @property
    def instrs(self):
        return self.groups.get(self.devicechain.group_index, self.groups[0])

    @property
    def banks(self):
        return self.instrs.get(self.devicechain.instr_index, self.instrs[0])

    def draw(self):
        leds = self.get_leds()
        for led in self.surface:
            if led in leds:
                self.surface[led] = leds[led]
            elif isinstance(led, tuple):
                color = colors.BLACK
                row, column = led
                if row == 8:
                    font_index = column-1
                    if font_index in self.fonts:
                        color = colors.ROSE
                if row in [6, 7]:
                    color = colors.AMBER_YELLOW
                if row == 5:
                    color = colors.LIME_GREEN
                if row == 4:
                    bank_index = column-1
                    if bank_index in self.banks:
                        color = colors.CYAN_SKY
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
            leds[led] = colors.RED
        return leds

    def pad_pressed(self, row, col, velocity):
        if row in [1, 2, 3]:
            self.grid.notepickers[self.channel].pad_pressed(row, col, velocity)
            return
        if velocity == 0:
            return
        if self.surface[row, col] == colors.BLACK:
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
        instrument = self.devicechain.instrument
        for message in instrument.messages():
            self.devicechain.send(message)
        # Repaint
        self.draw()

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
                instrument_index += 1
            else:
                instrument_index -= 1
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
            for message in self.devicechain.instrument.messages():
                self.devicechain.send(message)
            self.draw()


##############################################################################

class ScalePicker(Gridget):
    """
    ##.###.. sharp of the key below
    CDEFGAB. pick key
    ........
    ##.###.. sharp of the key below
    CDEFGAB. keys in scale
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
                color = colors.BLACK
                if row == 8 and column in [1, 2, 4, 5, 6]:
                    color = colors.MAGENTA_PINK
                if row == 7 and column != 8:
                    color = colors.MAGENTA_PINK
                if row == 5 and column in [1, 2, 4, 5, 6]:
                    color = colors.BLUE_ORCHID
                if row == 4 and column != 8:
                    color = colors.BLUE_ORCHID
                if row == 2 or row == 1:
                    try:
                        scales.palette[row-1][column-1]
                        color = colors.SKY_OCEAN
                    except IndexError:
                        pass
                self.surface[led] = color

    def get_leds(self):
        leds = {}

        key = self.grid.griode.key

        row, column = note2piano[key]
        leds[row+6, column] = colors.RED

        current_scale = self.grid.griode.scale
        for note in current_scale:
            row, column = note2piano[note]
            leds[row+3, column] = colors.RED

        for row, line in enumerate(scales.palette):
            for column, scale in enumerate(line):
                if scale == tuple(current_scale):
                    leds[row+1, column+1] = colors.RED

        return leds

    def cue(self, note):
        message = mido.Message("note_on", channel=self.grid.channel,
                               note=48+note, velocity=96)
        self.grid.griode.synth.send(message)
        self.grid.griode.synth.send(message.copy(velocity=0))

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return

        # Change the key in which we're playing
        if row in [7, 8]:
            note = piano2note.get((row-6, column))
            if note is not None:
                self.cue(note)
                self.grid.griode.key = note

        # Manually tweak the scale
        if row in [4, 5]:
            note = piano2note.get((row-3, column))
            if note is not None:
                self.cue(note+self.grid.griode.key)
                if note != 0:  # Do not remove the first note of the scale!
                    if note in self.grid.griode.scale:
                        self.grid.griode.scale.remove(note)
                    else:
                        self.grid.griode.scale.append(note)
                        self.grid.griode.scale.sort()

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
