MANUAL.md

# Griode user manual

This is a very succint user manual. Its goal is to explain Griode's menu
structure and some of the non-obvious features.


## General concept

Griode separates the Launchpad controls in two categories.

- There are 64 square *pads* arranged in a 8x8 grid. This is the
  main "play area". On the Launchpad Pro, they are pressure sensitive.
- And then there are round *buttons* located around the pads.
  On the Launchpad Pro, there are 8 buttons on each side (32 in total),
  but in the Launchpad S, Mini, and Mk2, there are 8 buttons on top
  and 8 buttons on the right (so 16 total).

Griode has many different "gridgets". There is a gridget to play notes,
a gridget to select an instrument, another to change the scale, etc.
At any given time, only one gridget is shown on the *pads*, and you
can switch to another gridget by using the *buttons*.

If this was confusing, you can think of the gridgets as different
screens, or different apps, each with a different purpose.

Gridget is a porte-manteau between "grid" and "widget"; widget
being here a [GUI widget](https://en.wikipedia.org/wiki/Widget_(GUI)).


## Buttons

Only the 8 buttons on the top row are used by Griode.

The first 4 buttons are UP, DOWN, LEFT, RIGHT. On almost every Launchpad,
there are arrows on these buttons so you can identify them easily;
except on the Launchpad Mini. On the Launchpad Mini, the buttons are
labeled 1 2 3 4 5 6 7 8; so 1 2 3 4 are actually UP DOWN LEFT RIGHT.

The arrows have different purposes in each gridget; for instance,
when playing notes, the arrows can be used to transpose the grid,
but they have different roles in other gridgets.

The 4 next buttons have different labels on different Launchpad models:

- SESSION NOTE DEVICE USER (Launchpad Pro)
- SESSION USER1 USER2 MIXER (Launchpad Mk2 and Launchpad S)
- 5 6 7 8 (Launchpad Mini)

These buttons are used to navigate the Griode menus, and switch
between gridgets.

Internally, they are known as BUTTON_1 BUTTON_2 BUTTON_3 BUTTON_4;
but we will refer to them as SESSION/5, NOTE/USER1/6, DEVICE/USER2/7, USER/MIXER/8.

They are mapped to the same functions; in other words, pressing
DEVICE on the Launchpad Pro is like pressing USER2 on the Launchpad Mk2
and it's like pressing 7 on the Launchpad Mini.


## Menus

The gridgets are organized in 4 menus. In other words, we have
4 menus, and in each menus, we have multiple gridgets. In each
menu, there is one "active" or "current" gridget; and there is
one "active" or "current" menu. At any given time, the gridget
that you see on the grid (and that you can interact with) is
the active gridget in the active menu.

The active menu is shown by a bright pink color. The other 3
menus are shown with a pale pink color. You can change the
active menu by pushing the corresponding button.

For instance, when you start Griode, it defaults to the NOTE/USER1/6
menu, and you can play some notes.
If you push DEVICE/USER2/7, you will then go to that menu
(which should show you the instrument selector). Push again
NOTE/USER1/6, and you're back where you started.

If you push again the button of the currently active menu,
then you cycle through the different grigets in that menu.

That's all!


## Structure

Here is the menu structure:

- SESSION/5
  - loop recorder
  - scale selector
- NOTE/USER1/6
  - chromatic keyboard
  - diatonic keyboard
  - tonnetz keyboard aka magic tone keyboard
- DEVICE/USER2/7
  - instrument selector
  - arpeggiator
  - latch
- USER/MIXER/8
  - rainbow palette
  - volume, chorus, and reverb faders
  - tempo
