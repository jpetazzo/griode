import glob
import logging
import os
import mido
import re
import subprocess
import sys
import time

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

    def __repr__(self):
        return ("Instrument({0.font}, {0.program}, {0.bank}, {0.name})"
                .format(self))

class Fluidsynth(object):

    def __init__(self):
        soundfonts = sorted(glob.glob("soundfonts/?.sf2"))

        # Pre-flight check
        if not soundfonts:
            print("No soundfont could be found. Fluidsynth cannot start.")
            print("Suggestion: 'cd soundfonts; ./download-soundfonts.sh'")
            exit(1)

        # Try to detect which sound driver to use.
        audio_driver = os.environ.get("GRIODE_AUDIO_DRIVER")
        if audio_driver is None:
            uid = os.getuid()
            pulseaudio_pidfile = "/run/user/{}/pulse/pid".format(uid)
            if os.path.isfile(pulseaudio_pidfile):
                try:
                    pulseaudio_pid = int(open(pulseaudio_pidfile).read())
                except:
                    logging.exception("Could not read pulseaudio PID")
                    pulseaudio_pid = None
                if pulseaudio_pid is not None:
                    if os.path.isdir("/proc/{}".format(pulseaudio_pid)):
                        audio_driver = "pulseaudio"
        if audio_driver is None:
            if sys.platform == "linux":
                audio_driver = "alsa"
            if sys.platform == "darwin":
                audio_driver = "coreaudio"
        if audio_driver is None:
            logging.error("Could not determine audio driver.")
            logging.error("Please set GRIODE_AUDIO_DRIVER.")
            exit(1)
        logging.info("Using audio driver: {}".format(audio_driver))

        popen_args = [
            "fluidsynth", "-a", audio_driver,
            "-o", "synth.midi-bank-select=mma",
            "-o", "synth.sample-rate=44100",
            "-c", "8", "-p", "griode"
        ]

        # Invoke fluidsynth a first time to enumerate instruments
        logging.debug("Invoking fluidsynth to enumerate instruments...")
        self.fluidsynth = subprocess.Popen(
            popen_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        msg = ""
        for i, soundfont in enumerate(soundfonts):
            font_id = i+1
            offset = i*1000
            msg += "load {} 1 {}\n".format(soundfont, offset)
            msg += "inst {}\n".format(font_id)
        self.fluidsynth.stdin.write(msg.encode("ascii"))
        self.fluidsynth.stdin.flush()
        self.fluidsynth.stdin.close()
        logging.debug("...Invoked fluidsynth to enumerate instruments")
        output = self.fluidsynth.stdout.read().decode("ascii")
        instruments = re.findall("\n([0-9]{3,})-([0-9]{3}) (.*)", output)
        self.instruments = []
        for bank, prog, name in instruments:
            bank = int(bank)
            prog = int(prog)
            font_id = bank // 1000
            instrument = Instrument(font_id, prog, bank, name)
            self.instruments.append(instrument)

        self.fonts = build_fonts(self.instruments)

        # Re-order the instruments list
        # (This is used to cycle through instruments in order)
        def get_instrument_order(i):
            return (i.font_index, i.program, i.bank_index)
        self.instruments.sort(key=get_instrument_order)

        # And now, restart fluidsynth but for actual synth use
        logging.debug("Starting fluidsynth as a synthesizer...")
        self.fluidsynth = subprocess.Popen(
            popen_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.fluidsynth.stdin.write(msg.encode("ascii"))
        self.fluidsynth.stdin.flush()

        # Find the MIDI port created by fluidsynth and open it
        logging.debug("Waiting for fluidsynth MIDI port to show up...")
        deadline = time.time() + 5
        while time.time() < deadline:
            port_names = [p for p in mido.get_output_names() if "griode" in p]
            if port_names == []:
                time.sleep(0.1)
                continue
            if len(port_names) > 1:
                logging.warning("Found more than one port for griode")
            self.synth_port = mido.open_output(port_names[0])
            logging.info("Connected to MIDI output {}"
                         .format(port_names[0]))
            break
        else:
            logging.error("Failed to locate the fluidsynth port!")
            exit(1)

    def send(self, message):
        self.synth_port.send(message)


def classify(list_of_things, get_key):
    """Transform a `list_of_things` into a `dict_of_things`.

    Each thing will be put in dict_of_things[k] where k
    is obtained by applying the function `get_key` to the thing.
    """
    dict_of_things = {}
    for thing in list_of_things:
        key = get_key(thing)
        if key not in dict_of_things:
            dict_of_things[key] = []
        dict_of_things[key].append(thing)
    return dict_of_things

def get_dk_and_font(i):

    # Generates a key for fonts dictionary.  Key is of form:
    # (Boolean, Int) The Boolean if True indicates drums
    
    # For 1.sf2 -> Dethmetal.sf2 bank is 1126 but is not drums
    if i.bank%1000 < 100 or i.bank == 1126:
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

    # Build a dictionary with keys: (Boolean, Int) where the boolean
    # indicates drums if True and the int is font (bank / 1000).
    # Values are Instrument objects
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
