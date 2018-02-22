from notes import *

MAJOR = (C, D, E, F, G, A, B)
MINOR = (C, D, Eflat, F, G, Aflat, B)

def greek_mode(n):
    scale = MAJOR[n:] + tuple(note+12 for note in MAJOR[:n])
    scale = tuple(note - scale[0] for note in scale)
    return scale

IONIAN = greek_mode(0)  # aka the major scale :-)
DORIAN = greek_mode(1)
PHRYGIAN = greek_mode(2)
LYDIAN = greek_mode(3)
MIXOLYDIAN = greek_mode(4)
AEOLIAN = greek_mode(5)
LOCRIAN = greek_mode(6)

BLUES = (C, Eflat, F, Fsharp, G, Bflat)

# double harmonic major, aka flamenco, aka arabic
ARABIC = (C, Dflat, E, F, G, Aflat, B)

# double harmonic minor aka hungarian minor
HUNGARIAN_MINOR = (C, D, Eflat, Fsharp, G, Aflat, B)

# hungarian
HUNGARIAN = (C, D, Eflat, Fsharp, G, Aflat, Bflat)

# phrygian dominant aka altered phrygian aka freygish
FREYGISH = (C, Dflat, E, F, G, Aflat, Bflat)

palette = (
    (MINOR, ARABIC, HUNGARIAN_MINOR, HUNGARIAN, FREYGISH, BLUES),
    (MAJOR, DORIAN, PHRYGIAN, LYDIAN, MIXOLYDIAN, AEOLIAN, LOCRIAN),
)
