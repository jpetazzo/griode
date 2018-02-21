import collections
import logging
import mido
import shelve
import time

import colors
import notes
from persistence import persistent_attrs, persistent_attrs_init
import scales

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
        # Setup the masked surface
        # (By default, it filters out all display)
        self.parent = MaskedSurface(parent)

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

class MaskedSurface(object):

    def __init__(self, parent):
        self.parent = parent
        self.mask = set() # leds that are ALLOWED

    def __iter__(self):
        return self.mask.__iter__()

    def __setitem__(self, led, color):
        if led in self.mask:
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

class DrumPicker(Gridget):

    # There are some interesting layouts there:
    FOUR_FOUR_MAP = [
            [55, 49, 56, 57],
            [41, 43, 47, 50],
            [40, 38, 46, 53],
            [37, 36, 42, 51],
            ][::-1]
    FOUR_EIGHT_MAP = [
            [49, 57, 55, 52, 53, 59, 51, None],
            [50, 48, 47, 45, 43, 41, None, 46],
            [40, 38, 37, None, 39, 54, None, 42],
            [36, 35, None, None, 75, 56, None, 44],
            ][::-1]

    def __init__(self, grid, channel):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.channel = channel
        self.map = self.FOUR_EIGHT_MAP
        self.draw()

    def rc2note(self, row, column):
        try:
            return self.map[row-1][column-1]
        except IndexError:
            return None

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if self.rc2note(row, column):
                    self.surface[led] = channel_colors[self.channel]

    def pad_pressed(self, row, column, velocity):
        note = self.rc2note(row, column)
        if not note:
            return
        message = mido.Message(
                "note_on", channel=self.channel,
                note=note, velocity=velocity)
        self.grid.griode.looper.send(message)
        self.surface[row, column] = colors.PINK_HI if velocity>0 else channel_colors[self.channel]

##############################################################################

@persistent_attrs(root=48, mapping="CHROMATIC")
class NotePicker(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.surface = Surface(grid.surface)
        for button in "UP DOWN LEFT RIGHT".split():
            self.surface[button] = channel_colors[channel]
        self.channel = channel
        persistent_attrs_init(self, "{}__{}".format(self.grid.port_name, channel))
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
        self.led2note.clear()
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                if mapping == "CHROMATIC":
                    shift = 5
                    note = shift*(row-1) + (column-1)
                    note += self.root
                elif mapping == "DIATONIC":
                    shift = 3
                    note = shift*(row-1) + (column-1)
                    octave = note//len(self.scale)
                    step = note%len(self.scale)
                    note = self.root + 12*octave + self.scale[step]
                elif mapping == "MAGIC":
                    note = (column-1)*7 - (column-1)//2*12
                    note += (row-1)*4
                    note += self.root
                self.led2note[led] = note
        self.note2leds.clear()
        for led,note in self.led2note.items():
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
        if button == "UP":
            self.root += 12
        elif button == "DOWN":
            self.root -= 12
        elif button == "LEFT":
            self.root -= 1
        elif button == "RIGHT":
            self.root += 1
        self.switch()
        # FIXME in diatonic mode, we want to make sure that
        # the root is in the scale.
        # FIXME also there might be something special to do
        # for the magic tone network mode.

    def pad_pressed(self, row, column, velocity):
        note = self.led2note[row, column]
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
                notepicker.draw()

# Maps notes to a pseudo-piano layout
# (with black keys on the top row and white keys on the bottom row)

note2piano = [
    (1, 1), (2, 1), (1, 2), (2, 2), (1, 3),
    (1, 4), (2, 4), (1, 5), (2, 5), (1, 6), (2, 6), (1, 7)
    ]

piano2note = { (r,c): n for (n, (r,c)) in enumerate(note2piano) }

##############################################################################

class ArpConfig(Gridget):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.current_step = 0
        self.display_offset = 0 # Step shown on first column
        self.page = "VELOGATE" # or "MOTIF"
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
        if self.page == "VELOGATE":
            self.surface["UP"] = colors.PINK_HI
        else:
            self.surface["UP"] = channel_colors[self.channel]
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
                    if self.page == "VELOGATE":
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
                    if self.page == "MOTIF":
                        if row-1 in harmonies:
                            if step == self.current_step:
                                color = colors.AMBER
                            else:
                                if velocity<2:
                                    color = colors.GREY_LO
                                else:
                                    color = colors.GREEN
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        step = column - 1 + self.display_offset
        if self.page == "VELOGATE":
            if row == 1:
                while len(self.arpeggiator.pattern) <= step:
                    self.arpeggiator.pattern.append([1,1, [0]]) # FIXME octave
                self.arpeggiator.pattern_length = step+1
            if row in [2, 3, 4]:
                self.arpeggiator.pattern[step][1] = row-1
            if row in [5, 6, 7, 8]:
                self.arpeggiator.pattern[step][0] = row-4
        if self.page == "MOTIF":
            harmony = row-1
            if harmony in self.arpeggiator.pattern[step][2]:
                self.arpeggiator.pattern[step][2].remove(harmony)
            else:
                self.arpeggiator.pattern[step][2].append(harmony)
        self.draw()

    def button_pressed(self, button):
        if self.page == "VELOGATE" and button == "UP":
            self.arpeggiator.enabled = not self.arpeggiator.enabled
        if button == "LEFT":
            if self.display_offset > 0:
                self.display_offset -= 1
                self.draw()
        if button == "RIGHT":
            if self.display_offset < self.arpeggiator.pattern_length - 2:
                self.display_offset += 1
                self.draw()
        if button == "UP":
            self.page = "VELOGATE"
            self.draw()
        if button == "DOWN":
            self.page = "MOTIF"
            self.draw()

##############################################################################

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
                    if self.loop in (self.loop.looper.loops_playing | self.loop.looper.loops_recording):
                        if self.loop.next_tick in ticks:
                            color = channel_colors[self.loop.channel]
                if self.loop.tick_in in ticks:
                    color = colors.PINK_HI
                if self.loop.tick_out in ticks:
                    color = colors.PINK_HI
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity==0:
            return
        if self.action == "SET_TICK_IN":
            tick = self.rc2ticks(row, column)[0]
            logging.info("Moving tick_in for loop {} to {}".format(self.loop, tick))
            self.loop.tick_in = tick
            self.action = None
        elif self.action == "SET_TICK_OUT":
            tick = self.rc2ticks(row, column)[-1] + 1
            logging.info("Moving tick_out for loop {} to {}".format(self.loop, tick))
            self.loop.tick_out = tick
            self.action = None
        else:
            ticks = self.rc2ticks(row, column)
            if self.loop.tick_out in ticks:
                logging.info("Action is now SET_TICK_OUT")
                self.action = "SET_TICK_OUT"
            elif self.loop.tick_in in ticks:
                logging.info("Action is now SET_TICK_IN")
                self.action = "SET_TICK_IN"
            else:
                for tick in ticks:
                    for note in self.loop.notes.get(tick, []):
                        # FIXME: note_on when pad is pressed, note_off when released
                        message = mido.Message(
                                "note_on", channel=self.loop.channel,
                                note=note.note, velocity=note.velocity)
                        self.grid.griode.synth.send(message)
                        self.grid.griode.synth.send(message.copy(velocity=0))
        self.draw()


##############################################################################

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
        self.mode = "REC" # or "PLAY"
        self.pads_held = {} # maps pad to time when pressed
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
            if tick%48 > 24:
                rec=False
            else:
                play=False
        if play:
            if tick%24 > 18:
                return colors.BLACK
            else:
                return color
        if rec:
            if tick%12 > 4:
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
                    tick = self.grid.griode.looper.last_tick
                    color = self.blink(
                            color,
                            loop in self.looper.loops_playing,
                            loop in self.looper.loops_recording)
                self.surface[led] = color
        # UP = playback, DOWN = record
        if self.mode == "REC":
            self.surface["UP"] = colors.ROSE
            self.surface["DOWN"] = colors.PINK_HI
        else:
            self.surface["UP"] = colors.PINK_HI
            self.surface["DOWN"] = colors.ROSE
        self.surface["UP"] = self.blink(
                self.surface["UP"], self.looper.loops_playing, False)
        self.surface["DOWN"] = self.blink(
                self.surface["DOWN"], False, self.looper.loops_recording)
        # LEFT = rewind all loops (but keep playing if we're playing)
        # (but also used to delete a loop!)
        self.surface["LEFT"] = colors.PINK_HI if self.pads_held else colors.ROSE
        # RIGHT = play/pause
        self.surface["RIGHT"] = colors.PINK_HI if self.looper.playing else colors.ROSE

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
                    if not loop: continue
                    # OK this is hackish, but because of the persistence system,
                    # we need to re-initialize the Loop object internal fields.
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
                        loop.tick_out = 24 * ((loop.tick_out+23) // 24)
            # And then toggle the playing flag.
            self.looper.playing = not self.looper.playing
        for grid in self.grid.griode.grids:
            grid.loopcontroller.draw()

##############################################################################

class Menu(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.menu = dict(
                BUTTON_1 = [
                    self.grid.loopcontroller,
                    self.grid.scalepicker,
                ],
                BUTTON_2 = [
                    "CHROMATIC",
                    "DIATONIC",
                    "MAGIC",
                    self.grid.drumpickers,
                ],
                BUTTON_3 = [
                    self.grid.instrumentpickers,
                    self.grid.arpconfigs,
                ],
                BUTTON_4 = [
                    self.grid.colorpicker,
                    self.grid.mixer,
                ],
            )
        self.current = "BUTTON_2"
        self.draw()

    def draw(self):
        for button in self.menu:
            if button == self.current:
                self.surface[button] = colors.PINK_HI
            else:
                self.surface[button] = colors.ROSE

    def focus(self, entry):
        mode = None
        if isinstance(entry, str):
            mode = entry
            entry = self.grid.notepickers
        if isinstance(entry, list):
            gridget = entry[self.grid.channel]
        else:
            gridget = entry
        self.grid.focus(gridget)
        if mode:
            gridget.switch(mode)

    def button_pressed(self, button):
        if button == self.current:
            entries = self.menu[button]
            entries.append(entries.pop(0))
            self.focus(entries[0])
        else:
            self.current = button
            self.focus(self.menu[button][0])
        self.draw()

##############################################################################

class Mixer(Gridget):
    # FIXME this only allows to view/set 8 channels for now

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        # FIXME the volumes probably should be stored somewhere else
        self.volumes = [96]*16
        self.draw()

    def draw(self):
        for led in self.surface:
            if isinstance(led, tuple):
                row, column = led
                color = colors.BLACK
                volume = self.volumes[column-1]
                n_leds = (volume+16)//16
                if row <= n_leds:
                    color = channel_colors[column-1]
                self.surface[led] = color

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        channel = column-1
        volume = 127*(row-1)//7
        self.volumes[channel] = volume
        logging.info("Setting channel {} volume to {}".format(channel, volume))
        message = mido.Message(
                "control_change", channel=channel,
                control=7, value=volume)
        self.grid.griode.synth.send(message)
        self.draw()

