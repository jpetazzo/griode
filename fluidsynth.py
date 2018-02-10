import logging
import mido
import subprocess


class Instrument(object):

    def __init__(self, font, program, bank, name):
        self.font = font        # fluidsynth font number (starts at 1)
        self.program = program  # MIDI program number [0..127]
        self.bank = bank        # bank [0..127] I think
        self.name = name        # string (not guaranteed to be unique!)

    def messages(self):
        """Generate MIDI messages to switch to that instrument."""
        # FIXME: deal with font
        return [
                mido.Message("control_change", control=0, value=self.bank),
                mido.Message("program_change", program=self.program),
                ]


class Fluidsynth(object):

    def __init__(self):

        # Spawn fluidsynth process
        self.fluidsynth = subprocess.Popen(
            ["fluidsynth", "-a", "pulseaudio",
            "-r", "8", "-c", "8", "-p", "griode", "default.sf2"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE
            )

        # Enumerate instruments in the default soundfont
        self.instruments = []
        while self.fluidsynth.stdout.peek() != b"> ":
            self.fluidsynth.stdout.readline()
        self.fluidsynth.stdin.write(b"inst 1\n")
        self.fluidsynth.stdin.flush()
        self.fluidsynth.stdout.readline()
        while self.fluidsynth.stdout.peek() != b"> ":
            line = self.fluidsynth.stdout.readline()
            bank_prog, program_name = line.split(b" ", 1)
            bank, prog = [int(x) for x in bank_prog.split(b"-")]
            name = program_name.decode("ascii").strip()
            logging.debug("Adding instrument {} -> {} -> {}".format(prog, bank, name))
            self.instruments.append(Instrument(1, prog, bank, name))

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

