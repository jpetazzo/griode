# Griode

Griode lets you play music using a LaunchPad or a similar controller.


## Installation and requirements

You need:

- Python 3
- FluidSynth (to generate sounds)
- at least one SoundFont (instrument bank used by FluidSynth)
- a LaunchPad or similar MIDI controller


### Installing Python dependencies

On Debian/Ubuntu systems, you should `apt-get install python3-dev libasound2-dev libjack-dev`.

Then you can `pip install -r requirements.txt`.

If you get compilation errors, you might need extra packages (libraries or headers).

Note: if you have problems related to the installation of `python-rtmidi`,
you might be tempted to try to install `rtmidi` instead. DO NOT! The two
packages are slightly incompatible; so after installing `rtmidi`, perhaps
Griode will start, but you will get another bizarre error at a later point.


### Installing FluidSynth

On Debian/Ubuntu systems, `apt-get install fluidsynth` will do the trick.


### Installing SoundFonts

Go to the `soundfonts` subdirectory, and run the script `download-soundfonts.sh`.

Alternatively, you can download your own soundfonts, place them in this directory,
and create a symlink `default.sf2` pointing to the soundfont you want to use.

Note: Griode only supports one soundfont at a time right now, but this will
change in the future.


#### What are soundfonts?

SoundFonts are instrument banks used by some audio hardware and by FluidSynth
to generate notes of music. The typical extension for SoundFont files is `.sf2`.

There are many SoundFonts available out there.
Some of them are tiny: the Sound Blaster AWE32 (a sound card from the mid-90s)
had 512 KB of RAM to load SoundFonts, and there are SoundFonts of that size
that offer the 100+ instruments of the General Midi standard! And some
SoundFonts are huge: I saw some 1 GB SoundFonts out there with just a couple
of piano instruments in them, but in very high quality (i.e. using different
samples for each note and for different velocity levels.)

Here are a few links to some SF2 files:
- [GeneralUser](http://www.schristiancollins.com/generaluser.php)
- [Fluid SoundFont](https://packages.debian.org/source/sid/fluid-soundfont)
- [Soundfonts4U](https://sites.google.com/site/soundfonts4u/)
- [8bitsf](https://musical-artifacts.com/artifacts/23/8bitsf.SF2)


### Usage

After installing the dependencies as described above and ensuring your Launchpad
is plugged into your machine, run `./griode.py`.

#### Debugging

Set `LOG_LEVEL` environment variable to `DEBUG` for verbose output.

## LaunchPad

I develop Griode with a LaunchPad Pro connected over USB.

I want to support other LaunchPads and possibly other grid-like
instruments as well, but I only have access to a LaunchPad right now.

