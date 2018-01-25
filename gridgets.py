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
        self.note_picker = NotePicker()
        self.instrument_picker = InstrumentPicker()
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
                self.focus(self.color_picker)
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
        if on_off:
            return colors.RED
        if row == 8 and col==1:
            return colors.ROSE
        if row == 6 or row == 7:
            return colors.AMBER_YELLOW
        if row == 5:
            return colors.LIME_GREEN
        if row == 4 and col==1:
            return colors.CYAN_SKY
        return colors.BLACK

    def rowcols(self):
        # Which leds are supposed to be ON for the current instrument
        return [(8, 1+self.font),
                (7-(self.group//8), 1+self.group%8),
                (5, 1+self.instrument),
                (4, 1+self.bank)]

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
        if row==8: # FIXME font
            pass
        if row==7:
            self.group = col-1
        if row==6:
            self.group = 8+col-1
        if row==5:
            self.instrument = col-1
        if row==4: # FIXME bank
            pass
        # Switch to new instrument
        self.change()
        # Turn on corresponding leds
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, True))


class ColorPicker(Layout):

    def show(self):
        for row in range(1, 9):
            for col in range(1, 9):
                color = (row-1)*8 + col-1
                self.led(row, col, color)

    def pad(self, row, column, velocity):
        if velocity > 0:
            print("Color #{}".format((row-1)*8 + column-1))


class ScalePicker(Layout):
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

    def rowcols(self): # return row,col that should be ON
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

    def pad(self, row, column, velocity):
        if velocity == 0:
            return
        # Turn off leds for current scale etc.
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, False))

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

        # Turn on corresponding leds
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, True))


    def show(self):
        for row in range(1, 9):
            for column in range(1, 9):
                self.led(row, column, self.color(row, column, False))
        for r,c in self.rowcols():
            self.led(r, c, self.color(r, c, True))

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
                (4, 3), (2, 3), (2, 2), (4, 2),
                (2, 2), (3, 1), (3, 1), (3, 2)
                ]
        self.next_step = 0
        self.last_tick = 0
        self.next_tick = 0
        self.multi_notes = [0, 12]
        self.number_of_steps = len(self.steps)
        self.notes = []
        self.playing = []
        self.real_synth = synth
    
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
        if self.next_step == self.number_of_steps:
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

