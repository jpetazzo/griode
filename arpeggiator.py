import mido

import colors
from gridgets import Gridget, Surface, channel_colors
from persistence import persistent_attrs, persistent_attrs_init


@persistent_attrs(
        enabled=True, interval=6, pattern_length=4,
        pattern=[[4, 3, [0]], [1, 2, [0]], [3, 1, [0]], [1, 2, [0]]],
        )
class Arpeggiator(object):

    def __init__(self, devicechain):
        self.devicechain = devicechain
        persistent_attrs_init(self, str(devicechain.channel))
        self.notes = []
        self.playing = []
        self.next_step = 0
        self.last_tick = 0
        self.next_tick = 0

    def tick(self, tick):
        self.last_tick = tick
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
        # Then, is it time to spell out the next note?
        if tick < self.next_tick:
            return
        # OK, is there any note in the buffer?
        if self.notes == []:
            return
        # Yay we have notes to play!
        velocity, gate, harmonies = self.pattern[self.next_step]
        velocity = velocity*31
        duration = gate*2
        for harmony in harmonies:
            offset = 0
            scale = self.devicechain.griode.scale
            while harmony >= len(scale):
                offset += 12
                harmony -= len(scale)
            # FIXME allow negative harmony
            note = self.notes[0] + offset + scale[harmony]
            self.output(mido.Message("note_on", note=note, velocity=velocity))
            self.playing.append((note, tick+duration))
        self.notes = self.notes[1:] + [self.notes[0]]
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
                if self.notes == []:
                    self.next_tick = self.last_tick + 1
                    self.next_step = 0
                self.notes.insert(0, message.note)
            else:
                if message.note in self.notes:
                    self.notes.remove(message.note)
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
        self.page = "VELOGATE"   # or "MOTIF"
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
                                if velocity < 2:
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
                    self.arpeggiator.pattern.append([1, 1, [0]])
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
