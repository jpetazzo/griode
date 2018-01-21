import mido

import colors
import notes
import scales

###

# all modes
# setup (light up all leds accordingly)
# keypress
# keyrelease
# navigation keys?

# note mode

color_key = colors.GREEN_HI
color_scale = colors.WHITE
color_other = colors.BLACK
color_played = colors.RED


class Grid(object):

    def led(self, row, col, color):
        note = 10*row + col
        message = mido.Message('note_on', note=note, velocity=color)
        self.midi_out.send(message)

    def __init__(self, midi_in, midi_out):
        self.midi_in = midi_in
        self.midi_out = midi_out
        self.gridget = None

    def focus(self, gridget):
        self.gridget = gridget
        self.gridget.show()

    def up(self):
        self.gridget.up()

    def down(self):
        self.gridget.down()

    def left(self):
        self.gridget.left()

    def right(self):
        self.gridget.right()

    def touch(self, row, col, velocity):
        self.gridget.touch(row, col, velocity)


class Note(object):

    def __init__(self, 
            grid, synth_port,
            key=notes.C, scale=scales.MAJOR, shift=5):
        self.grid = grid
        self.synth_port = synth_port
        self.key = key
        self.scale = scale
        self.shift = shift
        self.root = key+48 # root is the lowest note (bottom-left corner)

    def led(self, row, col, color):
        self.grid.led(row, col, color)

    def rowcol2note(self, row, col):
        note = self.root + (col-1) + self.shift*(row-1)
        return note

    def note2rowcols(self, note):
        # Convert actual note into a list of row+col positions
        # (There can be more than one)
        rowcols = []
        # For each row, check on which column the note would fall
        # If it falls within [1..8] keep it in the set
        for row in range(8):
            col = note - self.root - self.shift*row
            if col>=0 and col<=7:
                rowcols = rowcols + [(row+1, col+1)]
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
            for col in range (1, 9):
                note = self.rowcol2note(row, col)
                color = self.note2color(note)
                self.led(row, col, color)

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

    def touch(self, row, col, velocity):
        note = self.rowcol2note(row, col)
        if velocity > 0:
            velocity = 63 + velocity//2
            color = colors.RED
        else:
            color = self.note2color(note)
        for row,col in self.note2rowcols(note):
            self.led(row, col, color)
        self.synth_port.send(mido.Message('note_on', note=note, velocity=velocity))


class ProgramChange(object):

    def __init__(self, grid, synth_port):
        self.grid = grid
        self.synth_port = synth_port
        self.font = 0       # Sound font index
        self.group = 0      # General Midi group (0=piano, 1=chroma perc...)
        self.instrument = 0 # Instrument in group (0 to 7)
        self.bank = 0       # General Sound variation

    def change(self):
        # Send the relevant program change event
        program = self.group*8 + self.instrument
        message = mido.Message('program_change', program=program)
        self.synth_port.send(message)
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
            for col in range(1, 9):
                self.grid.led(row, col, self.color(row, col, False))
        for row,col in self.rowcols():
            self.grid.led(row, col, self.color(row, col, True))

    def touch(self, row, col, velocity):
        if velocity == 0:
            return
        # Turn off leds for current instrument
        for r,c in self.rowcols():
            self.grid.led(r, c, self.color(r, c, False))
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
            self.grid.led(r, c, self.color(r, c, True))


class Palette(object):

    def __init__(self, grid):
        self.grid = grid

    def show(self):
        for row in range(1, 9):
            for col in range(1, 9):
                color = (row-1)*8 + col-1
                self.grid.led(row, col, color)


# scale change mode

