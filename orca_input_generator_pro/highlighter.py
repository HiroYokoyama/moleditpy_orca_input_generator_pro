from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtCore import QRegularExpression


class OrcaSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # Keywords (!)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#8B0000"))  # Dark Red
        keyword_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"^!.*"), keyword_format))
        # Highlight tokens like B3LYP, Opt, Freq, etc.
        self.rules.append(
            (
                QRegularExpression(
                    r"\b(B3LYP|PBE0|CAM-B3LYP|wB97X-D3|NMR|Opt|OptH|Freq|OptTS|Scan|RelaxedScan|NormalOpt|LooseOpt|TightOpt|VeryTightOpt|COpt|SloppySCF|LooseSCF|NormalSCF|StrongSCF|TightSCF|VeryTightSCF|ExtremeSCF|RIJCOSX|RI|RI-MP2|DLPNO-CCSD|DLPNO-CCSD\(T\))\b",
                    QRegularExpression.CaseInsensitiveOption,
                ),
                keyword_format,
            )
        )

        # Blocks (%)
        block_format = QTextCharFormat()
        block_format.setForeground(QColor("#1976D2"))  # Blue
        block_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"^%.*"), block_format))
        self.rules.append(
            (
                QRegularExpression(
                    r"^\bend\b", QRegularExpression.CaseInsensitiveOption
                ),
                block_format,
            )
        )

        # Coordinates/Title (*)
        coord_format = QTextCharFormat()
        coord_format.setForeground(QColor("#388E3C"))  # Green
        coord_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r"^\*.*"), coord_format))

        # Resource Blocks (%) - Dark Yellow
        res_format = QTextCharFormat()
        # Use explicit hex for Dark Yellow to ensure visibility
        res_format.setForeground(QColor("#B8860B"))  # DarkGoldenRod
        res_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append(
            (
                QRegularExpression(
                    r"^%(pal|maxcore)\b.*", QRegularExpression.CaseInsensitiveOption
                ),
                res_format,
            )
        )

        # Comments (#)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#757575"))  # Grey
        self.rules.append((QRegularExpression(r"#.*"), comment_format))

    def highlightBlock(self, text):
        stripped = text.strip()
        is_route = stripped.startswith("!")

        # We iterate rules. Specific rules (like %pal) are at the end,
        # so they should overwrite general rules (like ^%) if applied later.
        for pattern, format in self.rules:
            p_str = pattern.pattern()

            # 1. Comments: Always
            if "#" in p_str:
                match_it = pattern.globalMatch(text)
                while match_it.hasNext():
                    m = match_it.next()
                    self.setFormat(m.capturedStart(), m.capturedLength(), format)
                continue

            # 2. Block/Coord headers: Always if they match the start of line
            if (
                p_str.startswith("^%")
                or p_str.startswith("^\\*")
                or "end" in p_str.lower()
            ):
                match_it = pattern.globalMatch(text)
                while match_it.hasNext():
                    m = match_it.next()
                    self.setFormat(m.capturedStart(), m.capturedLength(), format)
                continue

            # 3. Keywords: Only on ! lines
            if "\\b(" in p_str:  # Keyword list token matching
                if is_route:
                    match_it = pattern.globalMatch(text)
                    while match_it.hasNext():
                        m = match_it.next()
                        self.setFormat(m.capturedStart(), m.capturedLength(), format)
                continue

            # 4. Keywords line anchor (^!): Only if starts with !
            if p_str.startswith("^!"):
                if is_route:
                    match_it = pattern.globalMatch(text)
                    if match_it.hasNext():
                        m = match_it.next()
                        self.setFormat(m.capturedStart(), m.capturedLength(), format)
                continue
