import mido

from gridgets import Surface
from palette import palette
from persistence import persistent_attrs, persistent_attrs_init


@persistent_attrs(enabled=False)
class Latch(object):

    def __init__(self, devicechain):
        self.devicechain = devicechain
        persistent_attrs_init(self, str(devicechain.channel))
        self.notes = set()

    def send(self, message):
        if self.enabled and message.type == "note_on":
            note = message.note
            if message.velocity > 0:
                if note not in self.notes:
                    self.notes.add(note)
                    self.output(message)
                else:
                    self.notes.remove(note)
                    self.output(message.copy(velocity=0))
            else:
                pass
        else:
            self.output(message)

    def stop_all(self):
        for note in self.notes:
            message=mido.Message("note_on", channel=self.devicechain.channel,
                                 note=note, velocity=0)
            self.output(message)
        self.notes.clear()

    def output(self, message):
        self.devicechain.arpeggiator.send(message)


class LatchConfig(object):

    def __init__(self, grid, channel):
        self.grid = grid
        self.channel = channel
        self.surface = Surface(grid.surface)
        self.draw()

    @property
    def latch(self):
        return self.grid.griode.devicechains[self.channel].latch

    def draw(self):
        self.surface[7, 2] = palette.SWITCH[self.latch.enabled]

    def pad_pressed(self, row, column, velocity):
        if velocity == 0:
            return
        if (row, column) == (7, 2):
            if self.latch.enabled:
                self.latch.stop_all()
            self.latch.enabled = not self.latch.enabled
            self.draw()
