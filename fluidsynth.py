import glob
import logging
import mido
import os
import subprocess

# When we start the fluidsynth process, we use "MMA" bank select mode.
# This is the only mode that allows more than 128 banks (since it uses
# two control change messages to encode the bank number).
#
# For more details, see:
# https://github.com/FluidSynth/fluidsynth/blob/28a794a61cbca3181b21e2781d93c1bffc7c1b97/src/synth/fluid_synth.h#L55


class Instrument(object):

    def __init__(self, font, program, bank, name):
        self.font = font        # fluidsynth font number (starts at 1)
        self.program = program  # MIDI program number [0..127]
        self.bank = bank        # MIDI bank [includes offset, so [0..9128]
        self.name = name        # string (not guaranteed to be unique!)
        # This information is computed once all instruments are loaded
        self.is_drumkit = None  # True for drumkits, False for others
        self.font_index = None  # this is a UI value; starts at 0
        self.bank_index = None  # this is a UI value; starts at 0

    def messages(self):
        """Generate MIDI messages to switch to that instrument."""
        return [
            mido.Message("control_change", control=0, value=self.bank//128),
            mido.Message("control_change", control=32, value=self.bank%128),
            mido.Message("program_change", program=self.program),
        ]


class Fluidsynth(object):

    def __init__(self):
        soundfonts = sorted(glob.glob("soundfonts/?.sf2"))

        # Pre-flight check
        if not soundfonts:
            print("No soundfont could be found. Fluidsynth cannot start.")
            print("Suggestion: 'cd soundfonts; ./download-soundfonts.sh'")
            exit(1)

        # Spawn fluidsynth process
        self.fluidsynth = subprocess.Popen(
            ["fluidsynth", "-a", "pulseaudio",
             "-o", "synth.midi-bank-select=mma",
             "-c", "8", "-p", "griode"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE
        )

        self.instruments = []

        # Wait for fluidsynth prompt
        while self.fluidsynth.stdout.peek() != b"> ":
            self.fluidsynth.stdout.readline()

        # Now load each sound font one by one
        for i, soundfont in enumerate(soundfonts):
            logging.debug("Loading soundfont {} in position {}"
                          .format(soundfont, i))
            font_id = i+1
            offset = i*1000
            self.fluidsynth.stdin.write("load {} 1 {}\n"
                                        .format(soundfont, offset)
                                        .encode("ascii"))
            self.fluidsynth.stdin.flush()
            self.fluidsynth.stdout.readline()
            # Wait for prompt again
            while self.fluidsynth.stdout.peek() != b"> ":
                self.fluidsynth.stdout.readline()
            # Enumerate instruments in the soundfont
            self.fluidsynth.stdin.write("inst {}\n"
                                        .format(font_id)
                                        .encode("ascii"))
            self.fluidsynth.stdin.flush()
            self.fluidsynth.stdout.readline()
            while self.fluidsynth.stdout.peek() != b"> ":
                line = self.fluidsynth.stdout.readline()
                bank_prog, program_name = line.split(b" ", 1)
                bank, prog = [int(x) for x in bank_prog.split(b"-")]
                name = program_name.decode("ascii").strip()
                logging.debug("Adding instrument {} -> {} -> {}"
                              .format(prog, bank, name))
                self.instruments.append(Instrument(font_id, prog, bank, name))

        # Build the fonts structure
        self.fonts = build_fonts(self.instruments)

        # Re-order the instruments list
        # (This is used to cycle through instruments in order)
        def get_instrument_order(i):
            return (i.font_index, i.program, i.bank_index)
        self.instruments.sort(key=get_instrument_order)

        # Find the MIDI port created by fluidsynth and open it
        fluidsynth_ports = [p for p in mido.get_output_names() if "griode" in p]
        if len(fluidsynth_ports) == 0:
            logging.error("Could not connect to fluidsynth!")
            self.synth_port = None
        else:
            if len(fluidsynth_ports) > 1:
                logging.warning("More that one MIDI output named 'griode' found!")
            fluidsynth_port = fluidsynth_ports[0]
            self.synth_port = mido.open_output(fluidsynth_port)
            logging.info("Connected to MIDI output {}".format(fluidsynth_port))

    def send(self, message):
        self.synth_port.send(message)


def classify(list_of_things, get_key):
    """Transform a `list_of_things` into a `dict_of_things`.

    Each thing will be put in dict_of_things[k] where k
    is obtained by appling the function `get_key` to the thing.
    """
    dict_of_things = {}
    for thing in list_of_things:
        key = get_key(thing)
        if key not in dict_of_things:
            dict_of_things[key] = []
        dict_of_things[key].append(thing)
    return dict_of_things


def get_dk_and_font(i):
    if i.bank%1000 < 100:
        return (False, i.font)
    else:
        return (True, i.font)

def get_group(i):
    return i.program // 8

def get_instr(i):
    return i.program % 8

def get_bank(i):
    return i.bank

def build_fonts(instruments):
    fonts = classify(instruments, get_dk_and_font)
    for dk_and_font, instruments in fonts.items():
        groups = classify(instruments, get_group)
        for group, instruments in groups.items():
            instrs = classify(instruments, get_instr)
            for instr, instruments in instrs.items():
                banks = classify(instruments, get_bank)
                banks = sorted(banks.items())
                # Annotate instruments with the bank_index
                for bank_index, (bank_value, instruments) in enumerate(banks):
                    assert len(instruments) == 1
                    instruments[0].bank_index = bank_index
                instrs[instr] = {instruments[0].bank_index: instruments[0]
                                 for (bank_value, instruments) in banks}
            groups[group] = instrs
        fonts[dk_and_font] = groups
    fonts = sorted(fonts.items())

    # We could use enumerate() here, but let's try to be readable a bit...
    for font_index in range(len(fonts)):
        (is_drumkit, fluidsynth_font), font = fonts[font_index]
        for group in font.values():
            for instr in group.values():
                for instrument in instr.values():
                    instrument.font_index = font_index
                    instrument.is_drumkit = is_drumkit

    fonts = [font for ((is_drumkit, fs_font), font) in fonts]
    fonts = dict(enumerate(fonts))
    return fonts

    # fonts[font_index=0..N][group=0..15][program=0..7][bank_index=0..N]
