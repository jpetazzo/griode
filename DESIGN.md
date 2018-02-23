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

## Message flow

input → looper → devicechains → arpeggiator → synth

Each "stage" sends messages directly to the next, using the `send()` method.


## Data model

- griode
  - beatclock
  - looper
    - send(message)
    - tick()
    - beats_per_bar💾
    - loops[line,column]
      - next_tick
      - channel💾
      - tick_in💾    } beginning of the loop
      - tick_out💾   } when reaching that tick, rewind to tick_in
      - notes{}💾    } the key is the position the loop (in 24th of qnote)
        - note
        - velocity
        - duration   } this is also in 24th of quarter note
  - synth
    - instruments[]
      - messages()
    - fonts{font_index}{group}{program}{bank_index}
    - send(message)
  - devicechains[]
    - send(message)
    - font_index💾
    - group_index💾
    - instr_index💾
    - bank_index💾
    - arpeggiator
      - enabled💾
      - pattern_length💾
      - interval💾
      - pattern[]💾
        (velocity, gate, [harmonies])
      - tick(tick)
  - scale💾
  - key💾
  - grids[]
    - grid_name
    - channel💾
    - focus(gridget, leds[])
    - surface
    - colorpicker
    - notepickers[]
      - send(message, source_object)
    - instrumentpickers[]
      - change(instrument)
    - scalepicker
      - change(...)
    - arpconfigs[]
      - step(step)
    - loopcontroller
      - tick(tick)


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
