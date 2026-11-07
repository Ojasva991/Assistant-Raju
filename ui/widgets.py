"""
ui/widgets.py
Small custom widgets: MicButton (painted by hand, pulse ring), chat bubbles,
ChatView (scrolling list of bubbles) and StatusPill.
"""

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ui import theme

MAX_BUBBLES = 200          # the chat keeps the last 200 messages (spec)


class MicButton(QAbstractButton):
    """Round 56 px mic button. While listening a ring grows and fades around it.
    States: idle (green), listening (green + pulse), busy (grey, click is ignored)."""
    SIZE = 56
    BOX = 88   # the widget is bigger than the circle so the ring has room

    def __init__(self, tokens: theme.Tokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._t = tokens
        self._listening = False
        self._busy = False
        self._hover = False
        self._phase = 0.0        # 0..1, position of the pulse ring
        self.setFixedSize(self.BOX, self.BOX)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # keyboard focus ring (accessibility)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Listen (Ctrl+M)")
        self.setAccessibleName("Listen")
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(1400)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_phase)

    # ---- state ----
    def set_tokens(self, tokens: theme.Tokens) -> None:
        self._t = tokens
        self.update()

    def set_listening(self, on: bool) -> None:
        if on == self._listening:
            return
        self._listening = on
        if on:
            self._anim.start()
        else:
            self._anim.stop()
            self._phase = 0.0
        self.update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.update()

    def is_listening(self) -> bool:
        return self._listening

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.BOX, self.BOX)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    # ---- painting ----
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.SIZE / 2
        accent = QColor(self._t.accent)

        if self._listening:   # the pulse ring: grows from the circle edge and fades out
            ring_r = r + (self.BOX / 2 - r - 2) * self._phase
            ring = QColor(accent)
            ring.setAlphaF(max(0.0, 0.55 * (1.0 - self._phase)))
            p.setPen(QPen(ring, 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, ring_r, ring_r)

        if self._busy and not self._listening:
            fill, icon = QColor(self._t.raised), QColor(self._t.muted)
        else:
            fill = QColor(self._t.accent_hover if self._hover else self._t.accent)
            icon = QColor("#FFFFFF")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawEllipse(c, r, r)
        if self._busy and not self._listening:   # thin border so the grey circle is visible
            p.setPen(QPen(QColor(self._t.border), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r, r)

        # microphone icon: capsule, holder arc, stem
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(icon)
        p.drawRoundedRect(QRectF(c.x() - 6, c.y() - 15, 12, 20), 6, 6)
        p.setPen(QPen(icon, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(c.x() - 10, c.y() - 11, 20, 20), 200 * 16, 140 * 16)
        p.drawLine(QPointF(c.x(), c.y() + 9), QPointF(c.x(), c.y() + 15))
        p.drawLine(QPointF(c.x() - 5, c.y() + 15), QPointF(c.x() + 5, c.y() + 15))

        if self.hasFocus():   # visible focus ring
            p.setPen(QPen(QColor(self._t.text), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r + 4, r + 4)
        p.end()


class StatusPill(QLabel):
    """Small rounded label with the status text. The text carries the meaning;
    the border colour is only an extra hint."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("Idle", parent)
        self.setObjectName("pill")
        self.setProperty("state", "idle")
        self.setAccessibleName("Status")

    def set_status(self, text: str, state: str = "idle") -> None:
        self.setText(text)
        self.setProperty("state", state)
        self.style().unpolish(self)   # make Qt re-read the stylesheet for the new property
        self.style().polish(self)


class Bubble(QFrame):
    """One chat message. role is 'raju' or 'user' (set as a property for the stylesheet)."""

    def __init__(self, text: str, role: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("bubble")
        self.setProperty("role", role)
        self.role = role
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9)
        lay.addWidget(self.label)

    def text(self) -> str:
        return self.label.text()

    def fit(self, max_width: int) -> None:
        """Sets the label to the width of its text (up to max_width) and the matching height.
        A word-wrapped QLabel alone guesses its height badly and clips the text."""
        self.label.ensurePolished()      # use the stylesheet font when measuring
        inner_max = max(120, max_width - 28)
        fm = self.label.fontMetrics()
        flags = int(Qt.TextFlag.TextWordWrap)
        wanted = fm.boundingRect(0, 0, 100000, 100000, 0, self.label.text()).width() + 6
        width = min(inner_max, wanted)
        self.label.setFixedWidth(width)
        height = fm.boundingRect(0, 0, width, 100000, flags, self.label.text()).height() + 4
        self.label.setFixedHeight(height)


class ChatView(QScrollArea):
    """Scrolling list: Raju bubbles on the left, user bubbles on the right,
    muted system lines in the middle. Keeps the last MAX_BUBBLES messages."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._lay = QVBoxLayout(body)
        self._lay.setContentsMargins(4, 8, 12, 8)
        self._lay.setSpacing(8)
        self._lay.addStretch(1)          # pushes messages to the bottom when there are few
        self.setWidget(body)
        self._rows = []                  # (row widget, inner widget)
        self._stick = True               # follow new messages unless the user scrolled up
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range)
        bar.valueChanged.connect(lambda v: setattr(self, "_stick", v >= bar.maximum() - 6))

    def count(self) -> int:
        return len(self._rows)

    def messages(self):
        """[(role, text)] for tests and for the offscreen check."""
        out = []
        for _, inner in self._rows:
            if isinstance(inner, Bubble):
                out.append((inner.role, inner.text()))
            else:
                out.append(("system", inner.text()))
        return out

    def add_message(self, text: str, role: str) -> None:
        if role == "system":
            inner = QLabel(text)
            inner.setObjectName("sysline")
            inner.setWordWrap(True)
            inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            inner = Bubble(text, role)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            h.addStretch(1)
            h.addWidget(inner)
        elif role == "raju":
            h.addWidget(inner)
            h.addStretch(1)
        else:
            h.addWidget(inner, 1)
        self._lay.addWidget(row)
        self._rows.append((row, inner))
        self._limit_width(inner)
        while len(self._rows) > MAX_BUBBLES:
            old, _ = self._rows.pop(0)
            self._lay.removeWidget(old)
            old.deleteLater()
        self._stick = True

    def clear(self) -> None:
        for row, _ in self._rows:
            self._lay.removeWidget(row)
            row.deleteLater()
        self._rows = []

    # bubbles never get wider than 72 percent of the view, so long text wraps
    def _limit_width(self, inner) -> None:
        if isinstance(inner, Bubble):
            inner.fit(max(260, int(self.viewport().width() * 0.72)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        for _, inner in self._rows:
            self._limit_width(inner)

    def _on_range(self, _min, maximum) -> None:
        if self._stick:
            self.verticalScrollBar().setValue(maximum)
