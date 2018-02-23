import colorama
import os

import colors
from gridgets import ARROWS, MENU
from griode import Grid


class ASCIIGrid(Grid):

    def __init__(self, griode, fd_in, fd_out):
        self.fd_in = fd_in
        self.fd_out = fd_out
        self.surface = ASCIISurface(self)
        Grid.__init__(self, griode, "tty")


class ASCIISurface(object):

    def __init__(self, grid):
        self.grid = grid
        self.write(colorama.ansi.clear_screen())

    def __iter__(self):
        return (ARROWS + MENU + [(row, column)
                                 for row in range(1, 9)
                                 for column in range(1, 9)]).__iter__()

    def write(self, s):
        os.write(self.grid.fd_out, s.encode("utf-8"))
    
    def __setitem__(self, led, color):
        # This is a janky map but it will do for now
        char = {
            colors.BLACK:   " ",
            colors.PINK_HI: "X",
            colors.ROSE:    ".",
            colors.GREY_LO: ".",
        }.get(color, "o")
        if isinstance(led, tuple):
            row, column = led
        else:
            row = 10
            column = (ARROWS+MENU).index(led) + 1
        pos = colorama.Cursor.POS(column*2, 11-row)
        bottom = colorama.Cursor.POS(1, 12)
        self.write(pos + char + bottom)
