import logging
import resource
import time

import colors
from gridgets import Gridget, Surface
from persistence import persistent_attrs, persistent_attrs_init


NUMBERS = """
###  #  ### ### # # ### ### ### ### ###
# #  #    #   # # # #   #     # # # # #
# #  #  ### ### ### ### ###   # ### ###
# #  #  #     #   #   # # #   # # #   #
###  #  ### ###   # ### ###   # ### ###
""".strip().split("\n")


@persistent_attrs(bpm=120)
class Clock(object):

    def __init__(self, griode):
        self.griode = griode
        persistent_attrs_init(self)
        self.tick = 0  # 24 ticks per quarter note
        self.next = time.time()
        self.cues = []

    def cue(self, when, func, args):
        self.cues.append((self.tick+when, func, args))

    def callback(self):
        expired_cues = [cue for cue in self.cues if cue[0] <= self.tick]
        for when, func, args in expired_cues:
            func(*args)
        for cue in expired_cues:
            self.cues.remove(cue)
        for devicechain in self.griode.devicechains:
            devicechain.arpeggiator.tick(self.tick)
        for grid in self.griode.grids:
            grid.loopcontroller.tick(self.tick)
        self.griode.looper.tick(self.tick)
        self.griode.cpu.tick(self.tick)
        self.griode.tick(self.tick)

    def poll(self):
        now = time.time()
        if now < self.next:
            return self.next - now
        self.tick += 1
        self.callback()
        # Compute when we're due next
        self.next += 60.0 / self.bpm / 24
        if now > self.next:
            print("We're running late by {} seconds!".format(self.next-now))
            # If we are late by more than 1 second, catch up.
            if now > self.next + 1.0:
                print("Catching up (deciding that next tick = now).")
                self.next = now
            return 0
        return self.next - now

    def once(self):
        time.sleep(self.poll())

##############################################################################

class CPU(object):
    # Keep track of our CPU usage.

    def __init__(self, griode):
        self.griode = griode
        self.last_usage = 0
        self.last_time = 0
        self.last_shown = 0

    def tick(self, tick):
        r = resource.getrusage(resource.RUSAGE_SELF)
        new_usage = r.ru_utime + r.ru_stime
        new_time = time.time()
        if new_time > self.last_shown + 1.0:
            percent = (new_usage-self.last_usage)/(new_time-self.last_time)
            logging.debug("CPU usage: {:.2%}".format(percent))
            self.last_shown = new_time
        self.last_usage = new_usage
        self.last_time = new_time

##############################################################################

class BPMSetter(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.surface[1, 1] = colors.ROSE
        self.surface[1, 3] = colors.ROSE
        self.surface[1, 6] = colors.ROSE
        self.surface[1, 8] = colors.ROSE
        self.draw()

    @property
    def bpm(self):
        return self.grid.griode.clock.bpm

    @bpm.setter
    def bpm(self, value):
        self.grid.griode.clock.bpm = value

    def draw(self):
        d1 = self.bpm // 100
        d2 = self.bpm // 10 % 10
        d3 = self.bpm % 10
        if d1 == 0:
            for row in range(3, 9):
                for column in [1, 8]:
                    self.surface[row, column] = colors.BLACK
            self.draw_digit(d2, 3, 2, colors.WHITE)
            self.draw_digit(d3, 3, 5, colors.BLUE_HI)
        else:
            self.draw_digit(d1, 3, 1, colors.RED)
            self.draw_digit(d2, 3, 3, colors.WHITE)
            self.draw_digit(d3, 3, 6, colors.BLUE_HI)

    def draw_digit(self, digit, row, column, color):
        for line in range(5):
            three_dots = NUMBERS[line][4*digit:4*digit+3]
            for dot in range(3):
                if three_dots[dot] == "#":
                    draw_color = color
                else:
                    draw_color = colors.BLACK
                draw_row = row + 4 - line
                draw_column = column + dot
                self.surface[draw_row, draw_column] = draw_color

    def pad_pressed(self, row, column, velocity):
        # FIXME: provide visual feedback when these buttons are pressed.
        if velocity == 0:
            return
        if row == 1:
            if column == 1:
                self.bpm -= 10
            if column == 3:
                self.bpm -= 1
            if column == 6:
                self.bpm += 1
            if column == 8:
                self.bpm += 10
            if self.bpm < 50:
                self.bpm = 50
            if self.bpm > 199:
                self.bpm = 199
            self.draw()
