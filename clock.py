import logging
import resource
import time

# For reading commands
import select 
import os
import errno

from gridgets import Gridget, Surface
from palette import palette
from persistence import persistent_attrs, persistent_attrs_init
from fluidsynth import Instrument

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
        logging.debug("Opening command pipe");
        self.commands = open(".commands", 'r')
        self.commandPoll = select.poll()
        self.polledFiles = dict()
        self.commandPoll.register(self.commands, select.POLLIN)
        self.polledFiles[self.commands.fileno()] = self.commands
        
        logging.debug("Poll registered for command pipe.  Flag: {}".format(select.POLLIN));        
        logging.debug("pollin: {} pollpri {} pollout {}".
                      format(select.POLLIN, select.POLLPRI, select.POLLOUT));
        
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
            grid.tick(self.tick)
        for grid in self.griode.grids:
            grid.loopcontroller.tick(self.tick)
            self.griode.looper.tick(self.tick)
            self.griode.cpu.tick(self.tick)
            self.griode.tick(self.tick)

        # Check for commands from the Lord and Master
        for fd, event in  self.commandPoll.poll():
            # Got something
            if event == select.POLLIN:
                # A command to read
                N = os.fstat(fd).st_size
                try:
                    commandment = os.read(fd, 1024)
                except OSError as err:
                    if err.errno == errno.EAGAIN or err.errno == errno.EWOULDBLOCK:
                        commandment = None
                    else:
                        raise

                logging.debug("commandment: {}".format(commandment))

                # Break the commandment into two sections: Command and
                # data.  The command is the commandment from its start
                # to teh first space, the data is everything else
                command, data = self.decodeCommandment(commandment)
                logging.debug("command: {} data {}".format(command, data))
                if command == b"scale":
                    logging.debug("Setting scale.  Was: {}".
                                  format(self.griode.theScale()))
                    #set the scale
                    try:
                        scale = eval(data)
                        self.griode.setScale(scale)
                        logging.debug("Set scale.  Is: {}".
                                      format(self.griode.theScale()))
                    except:
                        logging.info("data: '{}' invalid".format(data))
                    
                elif command == b"draw":
                    # Redraw the screen
                    for g in self.griode.grids:
                        logging.debug("g: {}".format(g))
                        g.focus(g.notepickers[g.channel])
                        g.notepickers[g.channel].draw()

                elif command == b"instrument":
                    # Adding a instrument
                    args = data.split()
                    instrument = Instrument(int(args[0]),
                                            int(args[1]), int(args[2]),
                                            str(args[3]))
                    for device in self.griode.devicechains:
                        device.program_change_instrument(instrument)
                    
                else:
                    logging.debug("Did not understand commandment: {}".
                                 format(commandment))

    def decodeCommandment(self, commandment):
        # Split into words.  Command is first word, data is everything
        # else
        commandments = commandment.split()
        command = commandments.pop(0)
        data = b" ".join(commandments)
        return command, data
    
    # Return how long it is until the next tick.
    # (Or zero if the next tick is due now, or overdue.)
    def poll(self):
        now = time.time()
        if now < self.next:
            return self.next - now

        self.tick += 1
        self.callback()

        # Compute when we're due next
        self.next += 60.0 / self.bpm / 24
        if now > self.next:
            logging.warning("We're running late by {} seconds!"
                            .format(now - self.next))
            # If we are late, should we try to stay aligned, or skip?
            margin = 0.0  # Put 1.0 for pseudo-realtime
            if now > self.next + margin:
                logging.warning("Catching up (deciding that next tick = now).")
                self.next = now
            return 0
        return self.next - now

    # Wait until next tick is due.
    def once(self):
        sleepTime = self.poll()
        # logging.debug("Sleep: {}".format(sleepTime)) 
        time.sleep(sleepTime)

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
            # logging.debug("CPU usage: {:.2%}".format(percent))
            self.last_shown = new_time
        self.last_usage = new_usage
        self.last_time = new_time

##############################################################################

class BPMSetter(Gridget):

    def __init__(self, grid):
        self.grid = grid
        self.surface = Surface(grid.surface)
        self.surface[1, 1] = palette.DIGIT[0]
        self.surface[1, 3] = palette.DIGIT[0]
        self.surface[1, 6] = palette.DIGIT[0]
        self.surface[1, 8] = palette.DIGIT[0]
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
                    self.surface[row, column] = palette.BLACK
            self.draw_digit(d2, 3, 2, palette.DIGIT[2])
            self.draw_digit(d3, 3, 5, palette.DIGIT[3])
        else:
            self.draw_digit(d1, 3, 1, palette.DIGIT[1])
            self.draw_digit(d2, 3, 3, palette.DIGIT[2])
            self.draw_digit(d3, 3, 6, palette.DIGIT[3])

    def draw_digit(self, digit, row, column, color):
        for line in range(5):
            three_dots = NUMBERS[line][4*digit:4*digit+3]
            for dot in range(3):
                if three_dots[dot] == "#":
                    draw_color = color
                else:
                    draw_color = palette.BLACK
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
