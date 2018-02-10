This is the design document for griode internals.

## What's a gridget?

It's a widget for the grid! You can interact with a gridget, anmd it
can display itself.


## What's a "led"?

A `led` can be either a tuple, or a string.

Tuples correspond to pads, used to play notes or interact with a gridget.
The tuple will be `(row, column)` where both numbers start at 1.

Strings correspond to buttons, used to switch modes and macros.
8 strings are pre-defined; these are the "mandatory" buttons that should
be available for griode to be usable.
- LEFT RIGHT UP DOWN
- BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4

The other buttons will be mapped to arbitrary strings, and can be used
as macros or shortcuts. It doesn't matter if there are 0, 8, or 100.


## Data model

- griode
  - synth
    - instruments[]
      - messages()
    - send(message)
  - devicechains[]
    - send(message)
  - scale💾
  - key💾
  - grids[]
    - pads
    - buttons
    - focus(gridget)
    - surface
    - colorpicker
    - notepickers[]
      - send(message, source_object)
    - instrumentpickers[]
      - change(instrument)
    - scalepicker
      - change(...)


## Gridget interface

- pad_pressed(row, column, velocity)
- button_pressed(button)
- surface


## Surface interface

- [row, column]
- [button]
- parent


## Idea for a NLDR-like device chain

```
CH1 
CH2 
CH3
CH4
CH5 note	-> latch device -> fan-out device -> CH6,7,8,9
CH6 drone	-> instrument
CH7 bass	-> riff -> instrument
CH8 pad		-> chord -> instrument
CH9 motif	-> arp -> instrument
```
