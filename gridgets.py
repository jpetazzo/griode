import logging
import mido

import colors
import notes
from persistence import persistent_attrs, persistent_attrs_init
import scales
import shelve

##############################################################################

# And first, a few constants

channel_colors = [
        colors.RED_HI,
        colors.AMBER_HI,
        colors.YELLOW_HI,
        colors.GREEN_HI,
        colors.SKY_HI,
        colors.BLUE_HI,
        colors.ORCHID_HI,
        colors.MAGENTA_HI,
        colors.RED_LO,
        colors.AMBER_LO,
        colors.YELLOW_LO,
        colors.GREEN_LO,
        colors.SKY_LO,
        colors.BLUE_LO,
        colors.ORCHID_LO,
        colors.MAGENTA_LO,
]

##############################################################################

class Surface(object):

    def __init__(self, parent):
        # Initialize our "framebuffer"
        self.leds = {}
        for led in parent:
            self.leds[led] = colors.BLACK
        # But don't display ourself on the parent yet
        self.parent = None

    def __iter__(self):
        return self.leds.__iter__()

    def __getitem__(self, led):
        return self.leds[led]

    def __setitem__(self, led, color):
        if led not in self.leds:
            logging.error("LED {} does not exist!".format(led))
        else:
            current_color = self.leds[led]
            if color != current_color:
                self.leds[led] = color
                if self.parent:
                    self.parent[led] = color

##############################################################################

class Gridget(object):

    def pad_pressed(self, row, column, velocity):
        pass

    def button_pressed(self, button):
        pass

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

@persistent_attrs(shift=5, root=48)
class NotePicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.surface["BUTTON_1"] = colors.GREY_LO
        self.surface["BUTTON_2"] = colors.WHITE
        self.surface["BUTTON_3"] = colors.GREY_LO
        for button in "UP DOWN LEFT RIGHT".split():
            self.surface[button] = channel_colors[channel]
        self.channel = channel
        persistent_attrs_init(self, "{}__{}".format(self.grid.port_name, channel))
        self.redraw()

    @property
    def key(self):
        return self.grid.griode.key

    @property
    def scale(self):
        return self.grid.griode.scale

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
            return channel_colors[self.channel]
        if self.is_in_scale(note):
            return colors.GREY_LO
        return colors.BLACK

    def redraw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                note = self.rowcol2note(row, column)
                color = self.note2color(note)
                self.surface[led] = color

    def button_pressed(self, button):
        if button == "UP":
            self.root += 12
        elif button == "DOWN":
            self.root -= 12
        elif button == "LEFT":
            self.root -= 1
            self.redraw()
        elif button == "RIGHT":
            self.root += 1
            self.redraw()
        elif button == "BUTTON_1":
            self.grid.focus(self.grid.scalepicker)
        elif button == "BUTTON_2":
            pass #FIXME we're already in NotePicker so hum... configure it maybe
        elif button == "BUTTON_3":
            self.grid.focus(self.grid.instrumentpickers[self.channel])
        elif button == "BUTTON_4":
            pass #self.parent.focus("ArpSetup")

    def pad_pressed(self, row, column, velocity):
        note = self.rowcol2note(row, column)
        # Velocity curve (this is kind of a hack for now)
        # FIXME this probably should be moved to the devicechains
        if velocity > 0:
            velocity = 63 + velocity//2
        # Send that note to the right devicechain
        message = mido.Message("note_on", note=note, velocity=velocity)
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
                color = colors.RED
            else:
                color = colors.AMBER
            leds = self.note2rowcols(message.note)
            for led in leds:
                self.surface[led] = color

##############################################################################

class InstrumentPicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.surface = Surface(grid.surface)
        self.surface["BUTTON_1"] = colors.GREY_LO
        self.surface["BUTTON_2"] = colors.GREY_LO
        self.surface["BUTTON_3"] = colors.WHITE
        if channel>0:
            self.surface["LEFT"] = channel_colors[channel-1]
        if channel<15:
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
        if button == "BUTTON_1":
            self.grid.focus(self.grid.scalepicker)
        if button == "BUTTON_2":
            self.grid.focus(self.grid.notepickers[self.channel])
        if button == "LEFT" and self.channel>0:
            self.grid.channel = self.channel-1
            self.grid.focus(self.grid.instrumentpickers[self.channel-1])
        if button == "RIGHT" and self.channel<15:
            self.grid.channel = self.channel+1
            self.grid.focus(self.grid.instrumentpickers[self.channel+1])

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
        self.surface["BUTTON_1"] = colors.WHITE
        self.surface["BUTTON_2"] = colors.GREY_LO
        self.surface["BUTTON_3"] = colors.GREY_LO
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
                    except:
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

        for row,line in enumerate(scales.palette):
            for column,scale in enumerate(line):
                if scale == current_scale:
                    leds[row+1, column+1] = colors.RED

        return leds

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return

        # Change the key in which we're playing
        if row in [7, 8]:
            note = piano2note.get((row-6, column))
            if note is not None:
                self.grid.griode.key = note
                message = mido.Message("note_on", note=48+note, velocity=96)
                # FIXME channel #
                self.grid.griode.devicechains[0].send(message)
                self.grid.griode.devicechains[0].send(message.copy(velocity=0))


        # Pick a scale from the palette
        if row in [1, 2]:
            try:
                scale = scales.palette[row-1][column-1]
                self.grid.griode.scale = scale
            except IndexError:
                pass

        self.draw()
        for grid in self.grid.griode.grids:
            for notepicker in grid.notepickers:
                notepicker.redraw()

    def button_pressed(self, button):
        if button == "BUTTON_2":
            self.grid.focus(self.grid.notepickers[0])
        if button == "BUTTON_3":
            self.grid.focus(self.grid.instrumentpickers[0]) #FIXME move channel

# Maps notes to a pseudo-piano layout
# (with black keys on the top row and white keys on the bottom row)

note2piano = [
    (1, 1), (2, 1), (1, 2), (2, 2), (1, 3),
    (1, 4), (2, 4), (1, 5), (2, 5), (1, 6), (2, 6), (1, 7)
    ]

piano2note = { (r,c): n for (n, (r,c)) in enumerate(note2piano) }

##############################################################################

class Layout(object):
    pass

dict(
        interval=6, # 24 = quarter note, 12 = eigth note, etc.
        steps = [[4, 3], [1, 2], [3, 1], [1, 2]],
        number_of_steps=4,
        )
class Arpeggiator(Layout):

    def __init__(self, synth):
        self.next_step = 0
        self.last_tick = 0
        self.next_tick = 0
        self.multi_notes = [0, 12]
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

