import os
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)


def _f1account():
    """Return FastF1's account module, or None if this FastF1 has no F1 sign-in."""
    try:
        from fastf1.internals import f1account
        return f1account
    except ImportError:
        return None


def get_auth_status():
    """Return (signed_in, description) for the stored F1TV token."""
    account = _f1account()
    if account is None:
        return False, "This FastF1 version does not require sign-in."
    try:
        token = account.token_manager.get_stored()
    except Exception:
        token = None
    if token is None:
        return False, "Not signed in"
    if not token.is_valid():
        return False, "Session expired - please sign in again"
    expiry = datetime.fromtimestamp(token.expires_at)
    return True, f"Signed in (expires {expiry:%Y-%m-%d %H:%M})"


def needs_sign_in():
    """True if this FastF1 requires sign-in and there is no valid token."""
    if _f1account() is None:
        return False
    return not get_auth_status()[0]


SIGN_IN_HINT = ("You are not signed in to F1TV. FastF1 requires an F1TV account "
                "to load session data.")


DISCLAIMER = ("This requirement was introduced by Formula 1 (via FastF1), not by the "
              "F1 Race Replay developers, who had no part in the decision.")


def prompt_sign_in(parent=None):
    """Ask the user to sign in if needed. Returns True if they may proceed."""
    from PySide6.QtWidgets import QMessageBox
    if not needs_sign_in():
        return True
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("F1TV sign-in required")
    box.setText(SIGN_IN_HINT)
    box.setInformativeText(f"{DISCLAIMER}\n\nSign in now? Loading a session without signing in will fail.")
    sign_in = box.addButton("Sign in", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is sign_in:
        F1TVLoginDialog(parent).exec()
    return not needs_sign_in()


class LoginWorker(QThread):
    success = Signal()
    failure = Signal(str)

    def __init__(self, username, password, parent=None):
        super().__init__(parent)
        self.username = username
        self.password = password

    def run(self):
        account = _f1account()
        # FastF1 reads the credentials from these variables; they are only
        # kept for the duration of the sign-in and never written to disk.
        os.environ["F1_USERNAME"] = self.username
        os.environ["F1_PASSWORD"] = self.password
        try:
            account.get_token(force_renew=True, method="password")
            self.success.emit()
        except Exception as e:
            self.failure.emit(str(e) or e.__class__.__name__)
        finally:
            os.environ.pop("F1_USERNAME", None)
            os.environ.pop("F1_PASSWORD", None)
            self.password = None


class F1TVLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("F1TV Sign-in")
        self.setMinimumWidth(380)
        self.worker = None

        layout = QVBoxLayout(self)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("F1 account email")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.returnPressed.connect(self._sign_in)
        layout.addWidget(self.username_edit)
        layout.addWidget(self.password_edit)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        disclaimer = QLabel(DISCLAIMER)
        disclaimer.setWordWrap(True)
        layout.addWidget(disclaimer)

        note = QLabel("Your password is only used to sign in and is not stored. "
                      "FastF1 keeps the resulting session token on this computer.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        self.sign_out_btn = QPushButton("Sign out")
        self.sign_out_btn.clicked.connect(self._sign_out)
        self.sign_in_btn = QPushButton("Sign in")
        self.sign_in_btn.setDefault(True)
        self.sign_in_btn.clicked.connect(self._sign_in)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.sign_out_btn)
        buttons.addStretch()
        buttons.addWidget(self.sign_in_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._refresh_status()

    def _refresh_status(self):
        signed_in, text = get_auth_status()
        self.status_label.setText(f"<b>Status:</b> {text}")
        self.sign_out_btn.setEnabled(signed_in)
        self.sign_in_btn.setEnabled(_f1account() is not None)

    def _set_busy(self, busy):
        for w in (self.username_edit, self.password_edit, self.sign_in_btn):
            w.setEnabled(not busy)

    def _sign_in(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.message_label.setText("Enter your email and password.")
            return
        self.message_label.setText("Signing in...")
        self._set_busy(True)
        self.worker = LoginWorker(username, password, self)
        self.worker.success.connect(self._on_success)
        self.worker.failure.connect(self._on_failure)
        self.worker.start()
        self.password_edit.clear()

    def _on_success(self):
        self._set_busy(False)
        self._refresh_status()
        parent = self.parentWidget()
        self.accept()
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(parent, "F1TV sign-in",
                                "Sign-in successful. You are now signed in to F1TV.")

    def _on_failure(self, message):
        self._set_busy(False)
        self.message_label.setText(f"Sign-in failed: {message}")
        self._refresh_status()

    def _sign_out(self):
        account = _f1account()
        if account is not None:
            account.clear_token()
        self.message_label.setText("Signed out.")
        self._refresh_status()
