import logging
import mido

import colors
import notes
import scales


color_key = colors.GREEN_HI
color_scale = colors.WHITE
color_other = colors.BLACK
color_played = colors.RED


class Grid(object):
    """Represents an I/O surface like a LaunchPad or Monome."""

    def led(self, row, column, color):
        note = 10*row + column
        message = mido.Message('note_on', note=note, velocity=color)
        self.grid_out.send(message)

    def synth(self, message):
        self.synth_out.send(message)

    def __init__(self, grid_in, grid_out, synth_out, instruments):
        self.grid_in = grid_in
        self.grid_out = grid_out
        self.synth_out = synth_out
        self.gridget = None
        self.note_picker = NotePicker()
        self.instrument_picker = InstrumentPicker(instruments)
        self.color_picker = ColorPicker()
        self.scale_picker = ScalePicker(self.note_picker)
        self.arpeggiator = Arpeggiator(self.synth)
        combo_map = {}
        for row in range(1, 4):
            for column in range (1, 9):
                combo_map[row, column] = self.note_picker
        for row in range(4, 9):
            for column in range (1, 9):
                combo_map[row, column] = self.instrument_picker
        self.combo_picker = ComboLayout(combo_map)
        # This SysEx message switches the LaunchPad Pro to "programmer" mode
        self.grid_out.send(mido.Message("sysex", data=[0, 32, 41, 2, 16, 44, 3]))
        self.focus(self.note_picker)
        self.grid_in.callback = self.process_message

    def focus(self, gridget):
        self.gridget = gridget
        self.gridget.led = self.led
        self.gridget.synth = self.arpeggiator.synth
        self.gridget.show()

    def process_message(self, message):

        logging.debug(message)

        if message.type == "polytouch":
            return

        if message.type == "control_change" and message.value == 127:
            if message.control == 91:
                self.gridget.up()
            if message.control == 92:
                self.gridget.down()
            if message.control == 93:
                self.gridget.left()
            if message.control == 94:
                self.gridget.right()
            if message.control == 95: # session
                self.focus(self.scale_picker)
            if message.control == 96: # note
                self.focus(self.note_picker)
            if message.control == 97: # device
                self.focus(self.combo_picker)
            if message.control == 98: # user
                #self.focus(self.color_picker)
                self.focus(self.arpeggiator)
            # FIXME: add button messages

        if message.type == "note_on":
            row, column = message.note//10, message.note%10
            velocity = message.velocity
            self.gridget.pad(row, column, velocity)

    def tick(self, tick):
        color = colors.WHITE if tick%24<4 else colors.BLACK
        self.grid_out.send(mido.Message("control_change", control=98, value=color))
        self.arpeggiator.tick(tick)


class Layout(object):
    """Base layout for gridgets."""

    def pad(self, row, column, velocity):
        """"This method gets called when a pad is pressed or released.

        Row and column start at 1, where (1,1) is the lower left corner.
        Most of the code in griode assumes that the input grid is 8x8.
        The velocity is the pressure. This is a MIDI value, meaning that
        it ranges from 0 to 127. 0 means that the pad was actually
        released (this is part of the MIDI standard: a "NOTE ON"
        event with a velocity of 0 is like a "NOTE OFF" event).
        """

    def button(self, number):
        """This method gets called when a side button is pressed."""


    def left(self):
        pass

    def right(self):
        pass

    def up(self):
        pass

    def down(self):
        pass

    def show(self):
        """When this method is called, the gridget must draw itself."""

    def tick(self, tick):
        """This is called every tick to let the gridget track time.

        The gridget doesn't have to implement this method; but it can
        do it to keep track of elapsed time. This method will be called
        every tick (per MIDI standard, there are 24 ticks per quarter
        note). The argument is an absolute tick number. If the gridget
        needs a better accuracy (while handling a button or pad press,
        for instance) it can call time.time() as well.
        """

    def led(self, row, column, color):
        """The gridget should call this method to light up the grid.

        This method will be provided by the container of the gridget.
        Rows and columns start at 1. Color is a constant from the
        `colors` module, e.g. colors.BLACK.
        """

    def synth(self, message):
        """The gridget should call this method to play sounds.

        This method will be provided by the container of the gridget.
        The message should be a MIDI message constructed with the
        mido package, e.g.:
        `mido.Message("note_on", note=64, velocity=64)`
        """


class ComboLayout(Layout):

    def __init__(self, gridget_map):
        self.gridget_map = gridget_map

    def pad(self, row, column, velocity):
        self.gridget_map[row, column].pad(row, column, velocity)

    def show(self):
        for gridget in set(self.gridget_map.values()):
            gridget.synth = self.synth
            gridget.led = self.led_by_gridget(gridget)
            gridget.show()

    def led_by_gridget(self, gridget):
        def led(row, column, color):
            if self.gridget_map[row, column] == gridget:
                self.led(row, column, color)
        return led


class NotePicker(Layout):

    def __init__(self, key=notes.C, scale=scales.MAJOR, shift=5):
        self.key = key
        self.scale = scale
        self.shift = shift
        self.root = key+48 # root is the lowest note (bottom-left corner)

    def rowcol2note(self, row, column):
        note = self.root + (column-1) + self.shift*(row-1)
        return note

    def note2rowcols(self, note):
        # Convert actual note into a list of row+col positions
        # (There can be more than one)
        rowcols = []
        # For each row, check on which column the note would fall
        # If it falls within [1..8] keep it in the set
        for row in range(8):
            column = note - self.root - self.shift*row
            if column>=0 and column<=7:
                rowcols = rowcols + [(row+1, column+1)]
        return rowcols

    def is_key(self, note):
        return note%12 == self.key%12

    def is_in_scale(self, note):
        scale = [ (self.key + n)%12 for n in self.scale ]
        return note%12 in scale

    def note2color(self, note):
        if self.is_key(note):
            return color_key
        if self.is_in_scale(note):
            return color_scale
        return color_other

    def show(self):
        for row in range (1, 9):
            for column in range (1, 9):
                note = self.rowcol2note(row, column)
                color = self.note2color(note)
                self.led(row, column, color)

    def up(self):
        self.root += 12

    def down(self):
        self.root -= 12

    def left(self):
        self.root -= 1
        self.show()

    def right(self):
        self.root += 1
        self.show()

    def pad(self, row, column, velocity):
        note = self.rowcol2note(row, column)
        if velocity > 0:
            velocity = 63 + velocity//2
            color = colors.RED
        else:
            color = self.note2color(note)
        for row,column in self.note2rowcols(note):
            self.led(row, column, color)
        self.synth(mido.Message('note_on', note=note, velocity=velocity))


class OnOffPicker(Layout):
    """Helper class to build gridgets allowing to turn things on/off."""

    def color(self, row, column, on_off):
        """Return the color of the corresponding row/column/state."""

    def lights_on(self):
        """Return a list of (row,colum) pairs that should be lit."""

    def switch(self, row, column):
        """Called by the helper when a specific pad is pressed."""

    def show(self):
        for row in range(1, 9):
            for column in range(1, 9):
                self.led(row, column, self.color(row, column, False))
        for r,c in self.lights_on():
            self.led(r, c, self.color(r, c, True))

    def pad(self, row, column, velocity):
        # Only deal with "push" events (not "release")
        if velocity==0:
            return
        # Get current LED state
        old = self.lights_on()
        # Dispatch event
        self.switch(row, column)
        # Get new LED state
        new = self.lights_on()
        # FIXME: for now, deliberately turn everything off then on
        for (r, c) in old:
            self.led(r, c, self.color(r, c, False))
        for (r, c) in new:
            self.led(r, c, self.color(r, c, True))


def classify(list_of_things, get_key):
    """Transform a `list_of_things` into a `dict_of_things`.

    Each thing will be put in dict_of_things[k] where k
    is obtained by appling the function `get_key` to the thing.
    """
    dict_of_things = {}
    for thing in list_of_things:
        key = get_key(thing)
        if key not in dict_of_things:
            dict_of_things[key] = []
        dict_of_things[key].append(thing)
    return dict_of_things


class InstrumentPicker(OnOffPicker):

    def __init__(self, instruments):

        def get_font(i):
            if i.bank<100:
                return ("1_melo", i.font)
            else:
                return ("2_drum", i.font)
        def get_group(i):
            return i.program//8
        def get_instr(i):
            return i.program%8
        def get_bank(i):
            return i.bank

        self.fonts = classify(instruments, get_font)
        for font, instruments in self.fonts.items():
            groups = classify(instruments, get_group)
            for group, instruments in groups.items():
                instrs = classify(instruments, get_instr)
                for instr, instruments in instrs.items():
                    banks = classify(instruments, get_bank)
                    instrs[instr] = sorted(banks.items())
                groups[group] = instrs
            self.fonts[font] = groups
        self.fonts = sorted(self.fonts.items())

        # OK, self.fonts is a weird structure!
        # self.fonts[0..N] = (("X_melodrum", font_num), font)
        # then in a font you have: font[0..15][0..7] = list of (bank, instrument)

        self.font = 0       # Index in self.fonts (unrelated to ifluidsynth)
        self.group = 0      # General Midi group (0=piano, 1=chroma perc...)
        self.instrument = 0 # Instrument in group (0 to 7)
        self.variation = 0  # Instrument variation

    def change(self):
        # Send the relevant program change message
        font = self.fonts[self.font][1]
        instrument = font[self.group][self.instrument][self.variation][1][0]
        for message in instrument.messages():
            self.synth(message)

    def color(self, row, col, on_off):
        if on_off:
            return colors.RED
        if row == 8:
            if col in range(1, 1+len(self.fonts)):
                return colors.ROSE
        if row == 6 or row == 7:
            return colors.AMBER_YELLOW
        if row == 5:
            return colors.LIME_GREEN
        if row == 4:
            font = self.fonts[self.font][1]
            instrument = font[self.group][self.instrument]
            if col in range(1, 1+len(instrument)):
                return colors.CYAN_SKY
        return colors.BLACK

    def lights_on(self):
        # Which leds are supposed to be ON for the current instrument
        return [(8, 1+self.font),
                (7-(self.group//8), 1+self.group%8),
                (5, 1+self.instrument),
                (4, 1+self.variation)]


    def switch(self, row, col):
        if row==8:
            self.font = col-1
        if row==7:
            self.group = col-1
        if row==6:
            self.group = 8+col-1
        if row==5:
            self.instrument = col-1
        if row==4:
            self.variation = col -1
        # OK, now check that we didn't end up with an invalid combination
        font = self.fonts[self.font][1]
        if self.group not in font:
            self.group = 0
        if self.instrument not in font[self.group]:
            self.instrument = 0
        if self.variation >= len(font[self.group][self.instrument]):
            self.variation = 0
        # Also, update the variation row
        for c in range(1, 9):
            self.led(4, c, self.color(4, c, False))
        # Switch to new instrument
        self.change()


class ColorPicker(Layout):

    def show(self):
        for row in range(1, 9):
            for col in range(1, 9):
                color = (row-1)*8 + col-1
                self.led(row, col, color)

    def pad(self, row, column, velocity):
        if velocity > 0:
            print("Color #{}".format((row-1)*8 + column-1))


class ScalePicker(OnOffPicker):
    """
    ##.###.. # of the key below
    CDEFGAB. pick key
    ........
    ##.###.. # of the key below
    CDEFGAB. keys in scale
    ........
    XXXXXXXX modes
    XXXXXXXX scales
    """

    def __init__(self, note_picker):
        self.note_picker = note_picker

    def color(self, row, column, on_off):
        if on_off:
            return colors.RED
        if row == 8 and column in [1, 2, 4, 5, 6]:
            return colors.MAGENTA_PINK
        if row == 7 and column != 8:
            return colors.MAGENTA_PINK
        if row == 5 and column in [1, 2, 4, 5, 6]:
            return colors.BLUE_ORCHID
        if row == 4 and column != 8:
            return colors.BLUE_ORCHID
        if row == 2 or row == 1:
            try:
                scales.palette[row-1][column-1]
                return colors.SKY_OCEAN
            except:
                pass
        return colors.BLACK

    def lights_on(self):
        # return row,col that should be ON
        lights = []

        key = self.note_picker.key

        row, column = note2piano[key]
        lights.append((row+6, column))

        scale = self.note_picker.scale
        for note in scale:
            row, column = note2piano[note]
            lights.append((row+3, column))

        for row,line in enumerate(scales.palette):
            for column,scale in enumerate(line):
                if scale == self.note_picker.scale:
                    lights.append((row+1, column+1))

        return lights

    def switch(self, row, column):
        # Change the key in which we're playing
        if row in [7, 8]:
            note = piano2note.get((row-6, column))
            if note is not None:
                self.note_picker.key = note

        # Pick a scale from the palette
        if row in [1, 2]:
            try:
                scale = scales.palette[row-1][column-1]
                self.note_picker.scale = scale
            except IndexError:
                pass


# Maps notes to a pseudo-piano layout
# (with black keys on the top row and white keys on the bottom row)

note2piano = [
    (1, 1), (2, 1), (1, 2), (2, 2), (1, 3),
    (1, 4), (2, 4), (1, 5), (2, 5), (1, 6), (2, 6), (1, 7)
    ]

piano2note = { (r,c): n for (n, (r,c)) in enumerate(note2piano) }

class Arpeggiator(Layout):

    def __init__(self, synth):
        self.interval = 6 # 24 = quarter note, 12 = eight note, etc.
        self.steps = [
                [4, 3], [2, 3], [2, 2], [4, 2],
                [1, 2], [3, 1], [3, 1], [3, 2]
                ]
        self.next_step = 0
        self.last_tick = 0
        self.next_tick = 0
        self.multi_notes = [0, 12]
        self.number_of_steps = len(self.steps)
        self.notes = []
        self.playing = []
        self.real_synth = synth

    def color(self, row, column):
        if column > self.number_of_steps:
            if row == 1:
                return colors.GREEN_LO
            else:
                return colors.BLACK
        velocity, gate = self.steps[column-1]
        if row == 1:
            return colors.GREEN_HI
        if row in [2, 3, 4]:
            if gate > row-2:
                return colors.SPRING
        if row in [5, 6, 7, 8]:
            if velocity > row-5:
                return colors.LIME
        return colors.BLACK

    def show(self):
        for row in range(1, 9):
            for column in range(1, 9):
                self.led(row, column, self.color(row, column))

    def pad(self, row, column, velocity):
        if velocity == 0:
            return
        if row == 1:
            self.number_of_steps = column
            while len(self.steps) < self.number_of_steps:
                self.steps.append([1,1])
        if row in [2, 3, 4]:
            self.steps[column-1][1] = row-1
        if row in [5, 6, 7, 8]:
            self.steps[column-1][0] = row-4
        self.show()
        # FIXME: redraw only what's necessary

    def tick(self, tick):
        self.last_tick = tick
        # OK, first, let's see if some notes have "expired" and should be stopped
        for note,deadline in self.playing:
            if tick > deadline:
                self.real_synth(mido.Message("note_on", note=note, velocity=0))
                self.playing.remove((note, deadline))
        # Then, is it time to spell out the next note?
        if tick < self.next_tick:
            return
        # OK, is there any note in the buffer?
        if self.notes == []:
            return
        # Yay we have notes to play!
        velocity, gate = self.steps[self.next_step]
        velocity = velocity*31
        duration = gate*2
        self.real_synth(mido.Message("note_on", note=self.notes[0], velocity=velocity))
        self.playing.append((self.notes[0], tick+duration))
        self.notes = self.notes[1:] + [self.notes[0]]
        self.next_tick += self.interval
        self.next_step += 1
        if self.next_step >= self.number_of_steps:
            self.next_step = 0

    def synth(self, message):
        if message.type == "note_on":
            if message.velocity > 0:
                if self.notes == []:
                    self.next_tick = self.last_tick + 1
                    self.next_step = 0
                for i, offset in enumerate(self.multi_notes):
                    insert_position = i + i*len(self.notes)//len(self.multi_notes)
                    self.notes.insert(insert_position, message.note+offset)
            else:
                if message.note in self.notes:
                    for offset in self.multi_notes:
                        self.notes.remove(message.note+offset)
        else:
            self.real_synth(message)

