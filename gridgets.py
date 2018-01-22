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

    def __init__(self, grid_in, grid_out, synth_out):
        self.grid_in = grid_in
        self.grid_out = grid_out
        self.synth_out = synth_out
        self.gridget = None
        self.grid_in.callback = self.process_message
        self.note_picker = NotePicker()
        self.instrument_picker = InstrumentPicker()
        self.color_picker = ColorPicker()
        self.focus(self.note_picker)

    def focus(self, gridget):
        self.gridget = gridget
        self.gridget.led = self.led
        self.gridget.synth = self.synth
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
                pass
            if message.control == 96: # note
                self.focus(self.note_picker)
            if message.control == 97: # device
                self.focus(self.instrument_picker)
            if message.control == 98: # user
                self.focus(self.color_picker)
            # FIXME: add button messages

        if message.type == "note_on":
            row, column = message.note//10, message.note%10
            velocity = message.velocity
            self.gridget.pad(row, column, velocity)

class Layout(object):
    """Base layout for gridgets."""

    def pad(self, row, column, velocity):
        pass

    def button(self, number):
        pass

    def left(self):
        pass

    def right(self):
        pass

    def up(self):
        pass

    def down(self):
        pass

    def show(self):
        pass

    def led(self, row, column, color):
        pass

    def synth(self, message):
        pass


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


class InstrumentPicker(Layout):

    def __init__(self):
        self.font = 0       # Sound font index
        self.group = 0      # General Midi group (0=piano, 1=chroma perc...)
        self.instrument = 0 # Instrument in group (0 to 7)
        self.bank = 0       # Instrument variation

    def change(self):
        # Send the relevant program change message
        program = self.group*8 + self.instrument
        message = mido.Message('program_change', program=program)
        self.synth(message)
        # FIXME: deal with font and bank?

    def color(self, row, col, on_off):
        if row in [7, 8]: # group
            return colors.RED if on_off else colors.YELLOW_LO
        if row in [2]: # instrument
            return colors.RED if on_off else colors.ORCHID_LO
        return colors.BLACK

    def rowcols(self):
        # Which leds are supposed to be ON for the current instrument
        return [(8-(self.group//8), 1+self.group%8),
                (2, 1+self.instrument)]

    def show(self):
        for row in range(1, 9):
            for column in range(1, 9):
                self.led(row, column, self.color(row, column, False))
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, True))

    def pad(self, row, col, velocity):
        if velocity == 0:
            return
        # Turn off leds for current instrument
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, False))
        if row==2:
            self.instrument = col-1
        if row==8:
            self.group = col-1
        if row==7:
            self.group = 8+col-1
        # Switch to new instrument
        self.change()
        # Turn on corresponding leds
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, True))


class ColorPicker(object):

    def show(self):
        for row in range(1, 9):
            for col in range(1, 9):
                color = (row-1)*8 + col-1
                self.led(row, col, color)


# scale change mode

