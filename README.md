# Griode

Griode lets you play music using a LaunchPad or a similar controller.

For short demos and tutorials, check this [YouTube playlist](https://www.youtube.com/playlist?list=PLBAFXs0YjviK9PzKnr3MDsRU6YAJgeH1K).

I gave a few talks about Griode:
- Berlin Hack&Tell at C-Base (May 2018) [🔗](https://berlinhackandtell.rocks/2018-05-29-no61-revolutionary-may-hacks)
- Linux Technologies Berlin (July 2018) [🔗](https://www.meetup.com/linux-technologies-berlin/events/252302070/)
- Python Users Berlin (April 2019) [🔗](https://www.meetup.com/Python-Users-Berlin-PUB/events/258989401/)

[Here are the slides](https://docs.google.com/presentation/d/1G0bdcSyqqoCiD4dK7tq6PZsoMaM_VVexx_n8m4kSYYE/edit#slide=id.p) that I use when presenting Griode.

This [poster](https://drive.google.com/file/d/16wTihPzhnTIVcAFDvHevtFG-0K0qXPPB)
explains how to switch instruments and modes.
The original version of the poster was made by Jérôme Petazzoni to
present at PyCon in 2019; and it was then much improved
by [Elodie Trinh](https://twitter.com/mintismycolor) (thanks Elodie!♥).

There is also a basic (and incomplete) [user manual](MANUAL.md) that
you may (or not) find helpful.


## Quick start

Here are some quick instructions to get you started, assuming that you
have a LaunchPad connected to an Debian/Ubuntu system.

```
git clone git://github.com/jpetazzo/griode
cd griode
sudo apt-get install python3-pip python3-dev libasound2-dev libjack-dev fluidsynth
systemctl --user mask fluidsynth --now
python -m venv .venv
.venv/bin/pip install -r requirements.txt
( cd soundfonts; ./download-soundfonts.sh; )
.venv/bin/python griode.py
```

Your LaunchPad should light up with a red and white pattern, and pressing
pads should make piano sounds.

(Curious about what all these commands and packages are?
Keep reading, we'll explain a bit further!)


### Installing on a Raspberry Pi

If you want to setup Griode on a Raspberry Pi, if you are using Raspberry Pi OS,
you can use the instructions above, since it's basically a Debian system.

You can use the "lite" (text only) or the "desktop" version, it
doesn't matter for Griode.

If you want Griode to start automatically when the Pi is powered on,
see [this paragraph](#Starting-automatically-on-boot).


## Detailed setup instructions

You need:

- Python 3
- FluidSynth (to generate sounds)
- at least one SoundFont (instrument bank used by FluidSynth)
- a LaunchPad or similar MIDI controller


### Installing Python dependencies

On Debian/Ubuntu systems, you will need the following system packages,
so that the `python-rtmidi` Python package can be installed correctly:

```bash
apt-get install python3-dev libasound2-dev libjack-dev
```

You can then create a virtualenv for Griode's dependencies,
and install these dependencies:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Of course, if you want to use another system to manage the virtualenv
and the dependencies (like `uv`), that's perfectly fine.

If you get compilation errors, you might need extra packages (libraries or headers).

Note: if you have problems related to the installation of `python-rtmidi`,
you might be tempted to try to install `rtmidi` instead. DO NOT! The two
packages are slightly incompatible; so after installing `rtmidi`, perhaps
Griode will start, but you will get another bizarre error at a later point.


### Installing FluidSynth

Fluidsynth is a software synthesizer. On Debian/Ubuntu systems, you
can install it with:

```
apt-get install fluidsynth
```

By default, an instance of fluidsynth is started by a systemd user
unit. Griode won't use that instance; it will start its own, so that
it can pass special parameters and manage SoundFonts itself.
That instance of fluidsynth shouldn't interfere with Griode's,
but on resource-constrained systems (like Raspberry Pis) you may
want to stop it; you can do it by masking it:

```bash
systemctl --user mask fluidsynth.service --now
```


### Installing SoundFonts

Griode requires at least one "SoundFont" so that FluidSynth can make
sounds. The easiest way to get started is to go to the `soundfonts/`
subdirectory, and run the script `download-soundfonts.sh`.

Griode will load SoundFonts called `?.sf2` in alphabetical order.
The `download-soundfonts.sh` script will create a symlink `0.sf2`
pointing to the "GeneralUser GS" SoundFont, which contains the
128 instruments of the General MIDI standard, as well as a few
variations, and a few drum kits.

You are welcome to download your own soundfonts, place them in
the `soundfonts/` subdirectory, and create symlinks to these files:
they will be loaded when you start Griode.


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
- [BASSMIDI](https://kode54.net/bassmididrv/BASSMIDI_Driver_Installation_and_Configuration.htm)


### LaunchPad

Griode currently supports the Launchpad Pro, the Launchpad MK2 (aka "RGB"),
and has partial support for the Launchpad S. You can plug multiple
controllers and use them simultaneously.

Griode relies on the name of the MIDI port reported by the `mido` library
to detect your Launchpad(s). This has been tested on Linux, but the port
names might be different on macOS or Windows.


## Debugging

You can set the `LOG_LEVEL` environment variable to any valid `logging`
level, e.g. `DEBUG` or `INFO`:

```
export LOG_LEVEL=DEBUG
./griode.py
```

Note:
- `DEBUG` level is (and will always be) very verbose.
- You can put the log level in lowercase if you want.
- The default log level is `INFO`.


### Persistence

Griode saves all persistent information to the `state/` subdirectory.
If you want to reset Griode (or some of its subsystems) to factory defaults,
you can wipe out this directory (or some of the files therein).


### Starting automatically on boot

If you are using a Raspberry Pi running the Raspbian distribution,
and want to automatically start Griode on boot, you can use the provided
systemd unit (`griode.service`).

After checking out the code in `/home/pi/griode`, and confirming that
it runs correctly, just run:

```
systemctl enable $PWD/griode.service --now
loginctl enable-linger
```

Griode will start, and it will be automatically restarted when the
Pi reboots.

If it doesn't start, or if you want to see what's going on:

```
systemctl --user status griode
journalctl --user -u griode
```


## Setting output interface

Two environment variables can influence which audio interface Griode
will use (or, technically: which audio interface Griode will tell
Fluidsynth to use).

`GRIODE_AUDIO_DRIVER` can be set to `alsa`, `pulse`, or any value
accepted by Fluidsynth. If that variable isn't set, then,
if Griode detects a Pulseaudio socket, it will use Pulseaudio; otherwise, 
it will use `alsa` on Linux, and `coreaudio` on MacOS.

`GRIODE_ALSA_DEVICE` can be set to the name of an ALSA device,
to tell Griode to *prefer* that device. If that device is detected,
Griode will use it; otherwise it will fallback to the default ALSA
device. This is meant to be used on Raspberry Pi with external USB
audio interfaces: if the interface is detected, it will be used;
otherwise, Griode will fallback to the built-in interface.

To find the available names, you can run e.g. `find /proc/asound -type l`
(there is a symbolic link for each sound card, and the name of the
symlink is the name of the card).


## Udev rules

I find it useful to automatically set the volume of ALSA devices
to the max (technically: to 0dB), especially on a Raspberry Pi
when you can't easily run `alsamixer`. If you'd like to do that,
just copy the file `set-pcm-volume.rules` to `/etc/udev/rules.d`.
You don't need to restart or reload udev; but it will only take
action next time an audio interface is detected (USB audio interfaces
can be unplugged/replugged; built-in interfaces will require a reboot).

Also, my RØDE AI-1 interface has a severe bug (I don't know yet if
it's a defect on mine or a bug in their firmware or hardware): when
it's used at 48 or 96 kHz, it generates a very loud digital noise on
its output. To avoid that, I've also written a udev rule that sets
that interface to 44.1 kHz as soon as it's detected. That rule is
in the file `rode-ai-1.rules`.


## Bugs

- If you keep a note pressed while switching to another gridget,
  the note will continue to play. This is almost by design.
- If you keep a note pressed while stopping recording, it might
  record a zero-length notes.
- If a sync is triggered while notes are pressed, it might result
  in zero-length notes.

