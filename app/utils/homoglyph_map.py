"""
Homoglyph mapping tables for URL manipulation.

Each key is a Latin character; values are Unicode look-alikes from
Cyrillic, Greek, and other scripts that render visually identically
(or near-identically) in most fonts.
"""

CYRILLIC_MAP: dict[str, str] = {
    "a": "\u0430",
    "c": "\u0441",
    "d": "\u0501",
    "e": "\u0435",
    "i": "\u0456",
    "j": "\u0458",
    "o": "\u043E",
    "p": "\u0440",
    "s": "\u0455",
    "x": "\u0445",
    "y": "\u0443",
    "A": "\u0391",
    "B": "\u0412",
    "C": "\u0421",
    "E": "\u0415",
    "H": "\u041D",
    "I": "\u0406",
    "J": "\u0408",
    "K": "\u039A",
    "M": "\u041C",
    "O": "\u041E",
    "P": "\u0420",
    "S": "\u0405",
    "T": "\u0422",
    "X": "\u0425",
    "Y": "\u0423",
}

GREEK_MAP: dict[str, str] = {
    "a": "\u03B1",
    "b": "\u03B2",
    "e": "\u03B5",
    "h": "\u03B7",
    "i": "\u03B9",
    "k": "\u03BA",
    "m": "\u03BC",
    "n": "\u03BD",
    "o": "\u03BF",
    "p": "\u03C1",
    "t": "\u03C4",
    "u": "\u03C5",
    "v": "\u03BD",
    "w": "\u03C9",
    "x": "\u03C7",
    "y": "\u03B3",
    "A": "\u0391",
    "B": "\u0392",
    "E": "\u0395",
    "H": "\u0397",
    "I": "\u0399",
    "K": "\u039A",
    "M": "\u039C",
    "N": "\u039D",
    "O": "\u039F",
    "P": "\u03A1",
    "T": "\u03A4",
    "X": "\u03A7",
    "Y": "\u03A5",
    "Z": "\u0396",
}

CHAR_SETS: dict[str, dict[str, str]] = {
    "cyrillic": CYRILLIC_MAP,
    "greek": GREEK_MAP,
}

DIGRAPH_TRICKS: list[tuple[str, str]] = [
    ("rn", "m"),
    ("cl", "d"),
    ("vv", "w"),
    ("nn", "m"),
    ("li", "h"),
    ("lI", "H"),
]

LEET_MAP: dict[str, list[str]] = {
    "a": ["@", "4"],
    "e": ["3"],
    "i": ["1", "!"],
    "l": ["1"],
    "o": ["0"],
    "s": ["$", "5"],
    "t": ["7"],
    "g": ["9"],
    "b": ["8"],
    "A": ["@", "4"],
    "E": ["3"],
    "I": ["1", "!"],
    "O": ["0"],
    "S": ["$", "5"],
    "T": ["7"],
    "B": ["8"],
}
