import logging
import mido

import colors
from gridgets import ARROWS, MENU
from griode import Grid


class LaunchPad(Grid):

    def __init__(self, griode, port_name):
        logging.info("Opening grid device {}".format(port_name))
        self.grid_in = mido.open_input(port_name)
        self.grid_out = mido.open_output(port_name)
        for message in self.setup:
            self.grid_out.send(message)
        self.surface = LPSurface(self)
        Grid.__init__(self, griode, port_name)
        self.grid_in.callback = self.process_message

    def process_message(self, message):
        logging.debug("{} got message {}".format(self, message))

        # OK this is a hack to use fluidsynth directly with the Launchpad Pro
        if getattr(message, "channel", None) == 8:
            self.griode.synth.send(message)
            return

        # Ignore aftertouch messages for now
        if message.type == "polytouch":
            return

        # Let's try to find out if the performer pressed a pad/button
        led = None
        velocity = None
        if message.type == "note_on":
            led = self.message2led.get(("NOTE", message.note))
            velocity = message.velocity
        elif message.type == "control_change":
            led = self.message2led.get(("CC", message.control))

        if led is None:
            logging.warning("Unhandled message: {}".format(message))
            return

        gridget = self.surface_map.get(led)
        if gridget is None:
            logging.warning("Button {} is not routed to any gridget.".format(led))
            return

        if isinstance(led, tuple):
            row, column = led
            gridget.pad_pressed(row, column, velocity)
        elif isinstance(led, str):
            # Only emit button_pressed when the button is pressed
            # (i.e. not when it is released, which corresponds to value=0)
            if message.value == 127:
                gridget.button_pressed(led)

    def tick(self, tick):
        # This is a hack to work around a bug on the Raspberry Pi.
        # Sometimes, when no message has been sent for a while (a
        # few seconds), outgoing MIDI messages seem to be delayed,
        # causing a perceptible lag in visual feedback. It doesn't
        # happen if we keep sending messages continuously.
        self.grid_out.send(mido.Message("active_sensing"))


class LPSurface(object):

    def __init__(self, launchpad):
        self.launchpad = launchpad

    def __iter__(self):
        return self.launchpad.led2message.__iter__()

    def __setitem__(self, led, color):
        if isinstance(color, int):
            logging.warning("Raw color used: launchpad[{}] = {}".format(led, color))
        else:
            color = color[self.launchpad.palette]
        message_type, parameter = self.launchpad.led2message[led]
        if message_type == "NOTE":
            message = mido.Message("note_on", note=parameter, velocity=color)
        elif message_type == "CC":
            message = mido.Message("control_change", control=parameter, value=color)
        self.launchpad.grid_out.send(message)


class LaunchpadPro(LaunchPad):

    palette = "RGB"
    message2led = {}
    led2message = {}
    for row in range(1, 9):
        for column in range(1, 9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 91 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = [
        # This SysEx message switches the LaunchPad Pro to "programmer" mode
        mido.Message("sysex", data=[0, 32, 41, 2, 16, 44, 3]),
        # And this one sets the front/side LED
        mido.Message("sysex", data=[0, 32, 41, 2, 16, 10, 99, colors.WHITE]),
    ]


class LaunchpadMK2(LaunchPad):

    palette = "RGB"
    message2led = {}
    led2message = {}

    for row in range(1, 9):
        for column in range(1, 9):
            note = 10*row + column
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 104 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = []


class LaunchpadS(LaunchPad):

    palette = "RG"
    message2led = {}
    led2message = {}

    for row in range(1, 9):
        for column in range(1, 9):
            note = 16*(8-row) + column-1
            message2led["NOTE", note] = row, column
            led2message[row, column] = "NOTE", note
    for i, button in enumerate(ARROWS + MENU):
        control = 104 + i
        message2led["CC", control] = button
        led2message[button] = "CC", control

    setup = []
