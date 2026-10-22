"""Conservative input recovery; the complete source remains authoritative."""

import logging
import math
import os
import re

MAX_INPUT_BYTES = 16 * 1024 * 1024
logger = logging.getLogger(__name__)


def read_input(path):
    with open(path, "rb") as handle:
        data = handle.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the 16 MB limit.")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16")
    else:
        text = data.decode("utf-8-sig")
    if "\0" in text:
        raise ValueError("The input appears to be binary.")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _number(value):
    value = float(value.replace("D", "E").replace("d", "e"))
    if not math.isfinite(value):
        raise ValueError("Coordinates must be finite.")
    return value


def cartesian_rows(lines, gaussian=False):
    rows = []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        symbol = parts[0]
        if len(parts) > 1 and parts[1] == ":":
            symbol += ":"
            parts.pop(1)
        if gaussian and len(parts) == 5 and parts[1] in ("0", "-1"):
            parts.pop(1)
        if len(parts) < 4 or not re.fullmatch(
            r"(?:[A-Za-z]{1,3}|\d+)(?::|-Bq)?", symbol
        ):
            raise ValueError("This coordinate format cannot be displayed yet.")
        rows.append((symbol, *(_number(value) for value in parts[1:4])))
    return rows


def internal_rows(lines, variables="", orca_internal=False):
    """Display ordinary Z-matrices without evaluating input as Python code."""
    values = {}
    for line in variables.splitlines():
        match = re.fullmatch(r"\s*([A-Za-z]\w*)\s*(?:=|\s)\s*([-+\d.eEdD]+)\s*", line)
        if match:
            values[match[1].lower()] = _number(match[2])

    def value(token):
        try:
            return _number(token)
        except ValueError:
            sign = -1 if token.startswith("-") else 1
            key = token.lstrip("+-").lower()
            if key not in values:
                raise ValueError(
                    "Unresolved internal-coordinate variable: " + token
                ) from None
            return sign * values[key]

    def subtract(a, b):
        return tuple(x - y for x, y in zip(a, b))

    def cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def unit(vector):
        length = math.sqrt(sum(component * component for component in vector))
        if length < 1e-10:
            raise ValueError("Degenerate internal-coordinate reference plane.")
        return tuple(component / length for component in vector)

    rows, labels = [], {}
    for line in lines:
        parts = line.split("#", 1)[0].replace(",", " ").split()
        if not parts:
            continue
        index = len(rows)
        label = parts[0]
        symbol = re.sub(r"(?<=[A-Za-z])\d+$", "", label)
        if orca_internal:
            if len(parts) != 7:
                raise ValueError("Unsupported ORCA internal-coordinate row.")
            parts = [label] + [
                item for pair in zip(parts[1:4], parts[4:7]) for item in pair
            ]
            parts = parts[: 1 + min(index, 3) * 2]
        if len(parts) != 1 + min(index, 3) * 2:
            raise ValueError("Unsupported Z-matrix row.")
        if index == 0:
            point = (0.0, 0.0, 0.0)
        else:
            refs = []
            for token in parts[1::2]:
                reference = (
                    int(token) - 1 if token.isdecimal() else labels.get(token, -1)
                )
                if reference < 0 or reference >= index or reference in refs:
                    raise ValueError("Invalid Z-matrix reference.")
                refs.append(reference)
            distance = value(parts[2])
            if distance < 0:
                raise ValueError("Negative bond distance.")
            origin = rows[refs[0]][1:]
            if index == 1:
                direction = (0.0, 0.0, 1.0)
            else:
                axis = unit(subtract(rows[refs[1]][1:], origin))
                if index == 2:
                    trial = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
                    normal = unit(cross(axis, trial))
                else:
                    normal = unit(
                        cross(axis, subtract(rows[refs[2]][1:], rows[refs[1]][1:]))
                    )
                tangent = cross(normal, axis)
                angle = math.radians(value(parts[4]))
                dihedral = math.radians(value(parts[6])) if index > 2 else 0.0
                direction = tuple(
                    math.cos(angle) * a
                    + math.sin(angle)
                    * (math.cos(dihedral) * t - math.sin(dihedral) * n)
                    for a, t, n in zip(axis, tangent, normal)
                )
            point = tuple(o + distance * d for o, d in zip(origin, direction))
        labels[label] = index
        rows.append((symbol, *point))
    return rows


def parse_input(text, kind, source_path=""):
    """Recover supported settings and Cartesian geometry, without rewriting text.

    Unsupported coordinate syntax is reported, never replaced with the active
    molecule. Additional jobs and unrecognized instructions stay in source.
    """
    settings = {}
    rows = []
    notes = []
    if kind == "orca":
        jobs = re.split(r"(?im)^\s*\$new_job\s*$", text)
        first = jobs[0]
        route = re.findall(r"(?m)^\s*!\s*(.*)$", first)
        if not route and not re.search(
            r"(?im)^\s*(?:%[a-z]+\b|\*\s*(?:xyz|int|gzmt))", first
        ):
            raise ValueError("No ORCA keywords or coordinate/compound block found.")
        settings.update(
            route="! " + "\n! ".join(route), nproc=1, second_job_enabled=False
        )
        pal = re.search(r"(?is)%pal\b(.*?)\bend\b", first)
        nproc = re.search(r"(?i)\bnprocs\s+(\d+)", pal[1]) if pal else None
        if nproc:
            settings["nproc"] = int(nproc[1])
        mem = re.search(r"(?im)^\s*%maxcore\s+(\d+)", first)
        if mem:
            settings["maxcore"] = int(mem[1])
        comments = re.findall(r"(?m)^\s*#\s*(.*)$", first)
        settings["comment"] = " ".join(comments)
        geometry = re.search(
            r"(?im)^\s*\*\s*(xyzfile|xyz|int|internal|gzmt)\s+(-?\d+)\s+(\d+)([^\n]*)\n?",
            first,
        )
        pre, post = first, ""
        if geometry:
            settings.update(charge=int(geometry[2]), mult=int(geometry[3]))
            pre = first[: geometry.start()]
            if geometry[1].lower() == "xyzfile":
                settings["coord_format"] = "XYZ File (xyzfile)"
                filename = geometry[4].strip().strip("\"'")
                settings["xyzfile"] = filename
                post = first[geometry.end() :]
                if source_path and filename:
                    try:
                        xyz = read_input(
                            os.path.join(os.path.dirname(source_path), filename)
                        )
                        xyz_lines = xyz.splitlines()
                        count = int(xyz_lines[0])
                        if count < 1 or len(xyz_lines[2:]) < count:
                            raise ValueError("Incomplete XYZ file.")
                        rows = cartesian_rows(xyz_lines[2 : 2 + count])
                    except (OSError, ValueError, UnicodeError) as exc:
                        notes.append(f"External geometry was not displayed: {exc}")
            else:
                end = re.search(r"(?m)^\s*\*\s*(?:#.*)?$", first[geometry.end() :])
                if end is None:
                    raise ValueError("The coordinate block has no closing *.")
                body = first[geometry.end() : geometry.end() + end.start()]
                post = first[geometry.end() + end.end() :]
                if geometry[1].lower() == "xyz":
                    try:
                        rows = cartesian_rows(body.splitlines())
                    except ValueError as exc:
                        notes.append(str(exc))
                else:
                    settings["coord_format"] = (
                        "Internal (* gzmt)"
                        if geometry[1].lower() == "gzmt"
                        else "Internal (* int)"
                    )
                    try:
                        rows = internal_rows(
                            body.splitlines(),
                            orca_internal=geometry[1].lower() != "gzmt",
                        )
                    except ValueError as exc:
                        notes.append(f"Internal geometry was retained as text: {exc}")
        else:
            notes.append(
                "No explicit Cartesian geometry was found; the original text is retained."
            )
        pre = re.sub(r"(?is)%pal\b.*?\bend\b", "", pre)
        pre = re.sub(r"(?im)^\s*%maxcore\s+\d+[^\n]*", "", pre)
        pre = re.sub(r"(?m)^\s*[!#][^\n]*", "", pre)
        settings.update(adv=pre.strip(), adv_post=post.strip())
    else:
        jobs = re.split(r"(?im)^\s*--link1--\s*$", text)
        first = jobs[0]
        route = re.search(r"(?m)^\s*#", first)
        if route is None:
            raise ValueError("No Gaussian route section (#) found.")
        sections = re.split(r"\n[ \t]*\n", first[route.start() :].strip(), maxsplit=3)
        settings.update(
            route=sections[0].strip(), nproc=1, chk="", oldchk="", link1_enabled=False
        )
        if len(sections) > 1:
            settings["comment"] = " ".join(sections[1].splitlines())
        for key, value in re.findall(
            r"(?im)^\s*%([a-z0-9]+)\s*=\s*([^\n]+)", first[: route.start()]
        ):
            key, value = key.lower(), value.strip()
            if key in ("chk", "oldchk"):
                settings[key] = value
            elif key in ("nproc", "nprocshared") and value.isdecimal():
                settings["nproc"] = int(value)
            elif key == "mem":
                match = re.fullmatch(
                    r"(\d+)\s*(KB|MB|GB|TB|KW|MW|GW)?", value, re.IGNORECASE
                )
                if match:
                    settings.update(
                        mem_val=int(match[1]), mem_unit=(match[2] or "MW").upper()
                    )
        if len(sections) > 2:
            geometry_lines = sections[2].splitlines()
            charge = re.fullmatch(r"\s*(-?\d+)\s+(\d+)\s*", geometry_lines[0])
            if charge:
                settings.update(charge=int(charge[1]), mult=int(charge[2]))
                try:
                    rows = cartesian_rows(geometry_lines[1:], gaussian=True)
                except ValueError:
                    try:
                        rows = internal_rows(
                            geometry_lines[1:], sections[3] if len(sections) > 3 else ""
                        )
                        settings["coord_format"] = (
                            "Z-Matrix (variables)" if len(sections) > 3 else "Z-Matrix"
                        )
                    except ValueError as exc:
                        notes.append(f"Internal geometry was retained as text: {exc}")
            else:
                notes.append(
                    "Molecular specification was retained as text; no structure was displayed."
                )
        settings["tail"] = sections[3].strip() if len(sections) > 3 else ""
    if len(jobs) > 1:
        notes.append(
            "Additional jobs are preserved in the full text; recovered controls describe Job 1."
        )
    if rows:
        route = settings.get("route", "")
        if kind == "orca":
            bohr = re.search(r"(?i)\bbohrs\b", route)
        else:
            bohr = re.search(r"(?i)\bunits\s*=\s*\(?\s*(?:au|bohr|bohrs)\b", route)
        if bohr:
            rows = [
                (symbol, *(coordinate * 0.529177210903 for coordinate in point))
                for symbol, *point in rows
            ]
    if not rows and not notes:
        notes.append(
            "No Cartesian structure was found (for example, checkpoint-only input)."
        )
    return settings, rows, notes


def molecule_from_rows(rows, charge=0):
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    mol = Chem.RWMol()
    conf = Chem.Conformer(len(rows))
    table = Chem.GetPeriodicTable()
    for index, (label, x, y, z) in enumerate(rows):
        symbol = re.sub(r"(?i)(:|-Bq)$", "", label)
        if symbol.isdecimal():
            atomic_number = int(symbol)
            if not 0 <= atomic_number <= 118:
                raise ValueError(
                    "Unknown atomic number in the molecular specification."
                )
            symbol = table.GetElementSymbol(atomic_number)
        symbol = symbol.title()
        atom = Chem.Atom(0 if symbol in ("X", "Bq") else symbol)
        if label.endswith(":") or label.lower().endswith("-bq"):
            atom.SetProp("xyz_original_symbol", label)
        mol.AddAtom(atom)
        conf.SetAtomPosition(index, (x, y, z))
    mol.AddConformer(conf)
    mol = mol.GetMol()
    try:
        rdDetermineBonds.DetermineConnectivity(mol)
    except (RuntimeError, ValueError):
        pass  # Coordinates are still useful when bonding cannot be inferred.
    mol.SetIntProp("_xyz_charge", charge)
    return mol


class InputLoadingMixin:
    def _input_text_edited(self):
        if not getattr(self, "ui_ready", False):
            return
        text = self.preview_text.toPlainText()
        override = text != getattr(self, "_generated_text", "")
        self._text_override = override
        if self.persistent_settings is not None:
            if override:
                self.persistent_settings["input_text"] = text
            else:
                self.persistent_settings.pop("input_text", None)
        self.input_settings_widget.setEnabled(not override)
        self.input_notice.setVisible(override)
        self._current_content = text
        self._update_title()
        if self.mark_modified is not None:
            try:
                self.mark_modified()
            except (RuntimeError, ValueError, AttributeError):
                logger.exception(
                    "Could not mark the project modified after input editing"
                )

    def _write_generated_preview(self, text):
        from PySide6.QtCore import QSignalBlocker

        self._generated_text = text
        self._text_override = False
        with QSignalBlocker(self.preview_text):
            self.preview_text.setPlainText(text)
        self.input_settings_widget.setEnabled(True)
        self.input_notice.hide()
        if self.persistent_settings is not None:
            self.persistent_settings.pop("input_text", None)

    def refresh_input_preview(self):
        self._text_override = False
        self.input_settings_widget.setEnabled(True)
        self.input_notice.setText(
            "Full input text is authoritative. Edit Preview directly; Reset/Refresh regenerates from settings."
        )
        self.input_notice.hide()
        self.update_preview()

    def recover_input_conditions(self):
        from PySide6.QtWidgets import QMessageBox

        text = self.preview_text.toPlainText()
        try:
            parsed = parse_input(text, self.INPUT_KIND, self.current_inp_file or "")
        except ValueError as exc:
            QMessageBox.warning(self, "Recover Conditions", str(exc))
            return
        self.restore_input_text(text, parsed)

    def load_input_file(self, path=None):
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        if not isinstance(path, str) or not path:
            filters = (
                "ORCA input (*.inp)"
                if self.INPUT_KIND == "orca"
                else "Gaussian input (*.gjf *.com)"
            )
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Input File", "", filters + ";;All files (*)"
            )
        if not path:
            return False
        try:
            text = read_input(path)
            parsed = parse_input(text, self.INPUT_KIND, path)
        except (OSError, ValueError, UnicodeError) as exc:
            QMessageBox.warning(self, "Load Input File", str(exc))
            return False
        if not self._confirm_discard():
            return False
        if self.current_inp_file is None and getattr(self, "_text_override", False):
            reply = QMessageBox.question(
                self,
                "Replace Input Text",
                "Replace the current input text with this file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        self.restore_input_text(text, parsed, path)
        self.current_inp_file = os.path.abspath(path)
        self.filename = path
        self._saved_inp_content = self.preview_text.toPlainText()
        self._update_title()
        return True

    def restore_input_text(self, text, parsed=None, path=""):
        from PySide6.QtCore import QSignalBlocker

        if parsed is None:
            try:
                parsed = parse_input(text, self.INPUT_KIND, path)
            except ValueError:
                parsed = (
                    {},
                    [],
                    [
                        "Unfinished input restored verbatim. Use Preview to continue editing."
                    ],
                )
        settings, rows, notes = parsed
        self._close_builder()
        self.ui_ready = False
        try:
            if rows:
                try:
                    mol = molecule_from_rows(rows, settings.get("charge", 0))
                    if self.display_molecule is not None:
                        self.display_molecule(mol)
                    self.mol = mol
                    from .main_dialog import _charge_signature

                    self._charge_signature = _charge_signature(mol)
                except (RuntimeError, ValueError) as exc:
                    notes.append(f"Structure could not be displayed: {exc}")
            target = self.persistent_settings
            for name, key in (
                ("nproc_spin", "nproc"),
                ("mem_spin", "maxcore" if self.INPUT_KIND == "orca" else "mem_val"),
            ):
                if key in settings:
                    widget = getattr(self, name)
                    widget.setRange(
                        min(widget.minimum(), settings[key]),
                        max(widget.maximum(), settings[key]),
                    )
            if (
                "mem_unit" in settings
                and self.mem_unit.findText(settings["mem_unit"]) < 0
            ):
                self.mem_unit.addItem(settings["mem_unit"])
            self.persistent_settings = dict(settings)
            try:
                self.load_persistent_settings()
            finally:
                self.persistent_settings = target
            if target is not None:
                target.update(
                    {
                        key: value
                        for key, value in settings.items()
                        if key not in ("charge", "mult", "xyzfile")
                    }
                )
            for name, key in (("charge_spin", "charge"), ("mult_spin", "mult")):
                if key in settings:
                    widget = getattr(self, name)
                    widget.setRange(
                        min(widget.minimum(), settings[key]),
                        max(widget.maximum(), settings[key]),
                    )
                    widget.setValue(settings[key])
            if "xyzfile" in settings:
                self.xyzfile_name_edit.setText(settings["xyzfile"])
            self._generated_text = self.generate_input_content()
            with QSignalBlocker(self.preview_text):
                self.preview_text.setPlainText(text)
            self.input_notice.setText(
                "Full input text is authoritative. Edit Preview directly; Reset/Refresh regenerates from settings."
                + ("\n" + "\n".join(notes) if notes else "")
            )
        finally:
            self.ui_ready = True
        self._input_text_edited()
