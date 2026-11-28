"""Dialog for recording the selected day's mood."""

from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from desktop_calendar.config.i18n import tr
from desktop_calendar.core.mood import MOOD_CHOICES, MoodStore
from desktop_calendar.ui.theme import ThemeBundle

from .base import make_button_box
from .messages import msg_error, msg_warn

_MOOD_EMOJI = {
    "great": "😄",
    "good": "🙂",
    "okay": "😐",
    "low": "😔",
    "awful": "😣",
}
_MAX_NOTE_LENGTH = 200


class MoodDialog(QDialog):
    def __init__(
        self, store: MoodStore, selected_date: date, parent=None, bundle: ThemeBundle = None
    ):
        super().__init__(parent)
        if bundle is None:
            raise ValueError("MoodDialog 需要 ThemeBundle")
        self._store = store
        self._date = selected_date
        self._record = store.get(selected_date)
        self._scale = bundle.scale_factor

        self.setWindowTitle(tr("mood.title").format(date=selected_date.isoformat()))
        scale = bundle.scale_factor
        self.resize(round(420 * scale), round(360 * scale))
        self.setStyleSheet(bundle.dialog.qss_standard)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            bundle.dialog.margin, bundle.dialog.margin, bundle.dialog.margin, bundle.dialog.margin
        )
        layout.setSpacing(bundle.dialog.spacing)
        layout.addWidget(QLabel(tr("mood.prompt"), self))

        layout.addWidget(QLabel(tr("mood.recent"), self))
        layout.addLayout(self._build_history())

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        mood_row = QHBoxLayout()
        mood_row.setSpacing(6)
        for mood in MOOD_CHOICES:
            button = QPushButton(tr(f"mood.option.{mood}"), self)
            button.setObjectName("mood_choice")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._group.addButton(button)
            self._buttons[mood] = button
            mood_row.addWidget(button, 1)
            if self._record.get("mood") == mood:
                button.setChecked(True)
        layout.addLayout(mood_row)

        self._note = QPlainTextEdit(self)
        self._note.setPlaceholderText(tr("mood.note_placeholder"))
        self._note.setFixedHeight(max(56, round(64 * scale)))
        self._note.setPlainText(self._record.get("note", ""))
        self._note.setTabChangesFocus(True)
        self._note.textChanged.connect(self._on_note_changed)
        layout.addWidget(self._note)

        note_row = QHBoxLayout()
        note_row.addStretch(1)
        self._note_count = QLabel(self)
        self._note_count.setObjectName("mood_note_count")
        note_row.addWidget(self._note_count)
        layout.addLayout(note_row)
        self._update_note_count()

        actions = QHBoxLayout()
        self._delete_button = QPushButton(tr("mood.delete"), self)
        self._delete_button.setEnabled(bool(self._record))
        self._delete_button.clicked.connect(self._delete)
        actions.addWidget(self._delete_button)
        actions.addStretch(1)
        self._button_box = make_button_box(self, self._save)
        actions.addWidget(self._button_box)
        layout.addLayout(actions)

    def _build_history(self) -> QHBoxLayout:
        """最近 7 天：用日期 + emoji 给出这周的情绪脉络。"""
        history = QHBoxLayout()
        history.setSpacing(6)
        for offset in range(6, -1, -1):
            day = self._date - timedelta(days=offset)
            record = self._store.get(day)
            mood = record.get("mood")
            emoji = _MOOD_EMOJI.get(mood, "·")
            label = QLabel(f"{day.month}/{day.day}\n{emoji}", self)
            label.setObjectName("mood_history_day")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setProperty("selected", day == self._date)
            if mood:
                tooltip = tr(f"mood.option.{mood}")
                if record.get("note"):
                    tooltip += f"\n{record['note']}"
            else:
                tooltip = tr("mood.no_record")
            label.setToolTip(tooltip)
            label.setMinimumHeight(max(40, round(44 * self._scale)))
            history.addWidget(label, 1)
        return history

    def _on_note_changed(self) -> None:
        text = self._note.toPlainText()
        if len(text) > _MAX_NOTE_LENGTH:
            cursor = self._note.textCursor()
            position = min(cursor.position(), _MAX_NOTE_LENGTH)
            self._note.blockSignals(True)
            self._note.setPlainText(text[:_MAX_NOTE_LENGTH])
            cursor = self._note.textCursor()
            cursor.setPosition(position)
            self._note.setTextCursor(cursor)
            self._note.blockSignals(False)
            text = text[:_MAX_NOTE_LENGTH]
        self._update_note_count(text)

    def _update_note_count(self, text: str | None = None) -> None:
        if text is None:
            text = self._note.toPlainText()
        self._note_count.setText(
            tr("mood.note_count").format(count=len(text), limit=_MAX_NOTE_LENGTH)
        )

    def _save(self) -> None:
        selected = self._group.checkedButton()
        if selected is None:
            msg_warn(
                self, tr("mood.title").format(date=self._date.isoformat()), tr("mood.choose_first")
            )
            return
        mood = next(key for key, button in self._buttons.items() if button is selected)
        try:
            self._store.save(self._date, mood, self._note.toPlainText())
        except (OSError, ValueError, TypeError) as error:
            msg_error(self, tr("msg.error"), tr("mood.save_failed").format(error=error))
            return
        self.accept()

    def _delete(self) -> None:
        try:
            self._store.delete(self._date)
        except (OSError, ValueError, TypeError) as error:
            msg_error(self, tr("msg.error"), tr("mood.save_failed").format(error=error))
            return
        self.accept()
