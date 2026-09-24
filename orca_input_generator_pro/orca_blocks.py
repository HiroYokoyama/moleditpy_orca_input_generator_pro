"""Reading ORCA ``%`` blocks the way ORCA does.

Shared by the main dialog's block consolidation and the keyword builder's
round-trip check, so both agree on where a block starts and ends.
"""

import re

# %-directives that take one argument on their own line and have no "end".
SINGLE_LINE_DIRECTIVES = {"moinp", "maxcore", "base", "pointcharges", "id"}

# Keywords that open a sub-block closed by its own "end" inside a %-block.
# Known ones are matched regardless of indentation; an unknown sub-block
# still works when its "end" is indented (see read_block).
SUBBLOCK_KEYWORDS = {
    "constraints",
    "scan",
    "coords",
    "modify_internal",
    "fragments",
    "connectfragments",
    "newgto",
    "addgto",
    "newecp",
    "newauxjgto",
    "newauxcgto",
    "newauxjkgto",
    "newblock",
    "ptsettings",
}

_BOUNDARY_PREFIXES = ("%", "*", "!", "$")


def block_name(stripped):
    """'scf' for '%scf ...', else None."""
    m = re.match(r"^%(\w+)", stripped)
    return m.group(1).lower() if m else None


def is_single_line_directive(stripped):
    """True for '%moinp "x.gbw"', '%maxcore 3000', '%compound "a.cmp"' ...

    A '%name' followed by one quoted or numeric argument and no 'end' is a
    directive, not the start of a block; reading on to the next 'end' would
    swallow whatever block follows it.
    """
    name = block_name(stripped)
    if name is None:
        return False
    rest = stripped[len(name) + 1 :].strip()
    if name in SINGLE_LINE_DIRECTIVES:
        return True
    if not rest or re.search(r"\bend\s*$", rest, re.I):
        return False
    return rest[0] in "\"'" or re.match(r"^[+-]?\d", rest) is not None


def one_liner_body(stripped):
    """'maxiter 200' for '%scf maxiter 200 end', else None."""
    m = re.match(r"^%\w+\s+(.*?)\s+end\b(.*)$", stripped, re.I | re.S)
    if not m:
        return None
    return m.group(1)


def _is_end(line):
    return line.strip().lower() == "end"


def _opens_subblock(line):
    s = line.strip()
    if not s:
        return False
    first = s.split()[0].lower()
    if first not in SUBBLOCK_KEYWORDS:
        return False
    # "NewGTO "def2-SVP" end" opens and closes on one line.
    return re.search(r"\bend\s*$", s, re.I) is None


def _later_unindented_end(lines, start):
    """True when an unindented 'end' follows before the next top-level item."""
    for line in lines[start:]:
        s = line.strip()
        if s.startswith(_BOUNDARY_PREFIXES):
            return False
        if _is_end(line) and not line[:1].isspace():
            return True
    return False


def read_block(lines, start):
    """Read the multi-line block whose header is lines[start].

    Returns (next_index, body_lines) with the closing 'end' consumed and
    excluded. Sub-blocks keep their own 'end' lines in the body.
    """
    body = []
    depth = 0
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if _is_end(line):
            if depth > 0:
                depth -= 1
                body.append(line)
                i += 1
                continue
            # An indented 'end' with an unindented one still to come closes
            # a sub-block this module does not know by name.
            if line[:1].isspace() and _later_unindented_end(lines, i + 1):
                body.append(line)
                i += 1
                continue
            return i + 1, body
        if _opens_subblock(line):
            depth += 1
        body.append(line)
        i += 1
    return i, body


def body_units(body_lines):
    """Group a block body into top-level units: single lines and sub-blocks."""
    units = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.strip():
            i += 1
            continue
        if _opens_subblock(line):
            unit = [line]
            depth = 1
            i += 1
            while i < len(body_lines) and depth > 0:
                inner = body_lines[i]
                unit.append(inner)
                if _is_end(inner):
                    depth -= 1
                elif _opens_subblock(inner):
                    depth += 1
                i += 1
            units.append(unit)
            continue
        units.append([line])
        i += 1
    return units


def iter_blocks(text):
    """Yield (name, header_line, units) for every %-block/directive in *text*.

    For a single-line directive *units* is None and *header_line* is the
    whole directive.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        name = block_name(s)
        if name is None:
            i += 1
            continue
        if is_single_line_directive(s):
            yield name, lines[i], None
            i += 1
            continue
        inline = one_liner_body(s)
        if inline is not None:
            yield name, lines[i], [[inline]]
            i += 1
            continue
        header = lines[i]
        i, body = read_block(lines, i)
        yield name, header, body_units(body)


def unit_key(unit):
    """Whitespace- and case-insensitive identity of a block unit."""
    return re.sub(r"\s+", "", "\n".join(unit)).lower()
