#!/usr/bin/env python3
"""
TelePrompter — Professional Teleprompter Application
Author  : 𝓐.𝓒.𝓑
Requires: pip install PyQt5
Optional: pip install keyboard sounddevice numpy PyMuPDF
"""

# ── Standard library ──────────────────────────────────────────────────────────
import sys, json, re
from pathlib import Path

# ── PyQt5 ─────────────────────────────────────────────────────────────────────
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QTextEdit, QPushButton, QSlider, QCheckBox, QGroupBox,
    QFileDialog, QColorDialog, QComboBox, QFontComboBox, QInputDialog,
    QProgressBar, QTabWidget, QSpinBox, QMessageBox, QSizeGrip,
)
from PyQt5.QtCore  import Qt, QTimer, QElapsedTimer
from PyQt5.QtGui   import QPainter, QFont, QFontMetrics, QColor, QPen, QPalette

try:
    from PyQt5.QtPrintSupport import QPrinter
    PDF_PRINT_OK = True
except ImportError:
    PDF_PRINT_OK = False

# ── Optional extras ───────────────────────────────────────────────────────────
try:
    import sounddevice as _sd
    import numpy as _np
    MIC_OK = True
except ImportError:
    _sd = _np = None
    MIC_OK = False

try:
    import keyboard as _kb
    HOTKEY_OK = True
except ImportError:
    _kb = None
    HOTKEY_OK = False

try:
    import fitz as _fitz          # PyMuPDF — optional PDF text extraction
    PYMUPDF_OK = True
except ImportError:
    _fitz = None
    PYMUPDF_OK = False

# ── Windows taskbar icon fix ──────────────────────────────────────────────────
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        'ACB.TelePrompter.App'
    )
except Exception:
    pass   # Non-Windows platforms — safe no-op

# ── Constants ─────────────────────────────────────────────────────────────────
SAVE_FILE  = Path.home() / ".teleprompter.json"
_PAUSE_TAG = '[PAUSE]'
_NOTE_RE   = re.compile(r'\[\[(.+?)\]\]')

# Encoding probe order for file loading
_ENCODINGS = ['utf-8-sig', 'utf-8', 'cp1254', 'cp1252', 'cp1250', 'latin-1']

# Alpha fade lookup table: dist (0..511) → alpha (0..255)
# Formula: max(0, 255 - int(dist * 0.75))   clipped at 340 → 0
_ALPHA_LUT: list[int] = [max(0, 255 - int(d * 0.75)) for d in range(512)]

# ── Themes ────────────────────────────────────────────────────────────────────
THEMES: dict[str, dict] = {
    "Dark":          dict(bg=(0,   0,   0  ), text=(255, 255, 255), opacity=0.70),
    "Light":         dict(bg=(235, 235, 230), text=(18,  18,  18 ), opacity=0.92),
    "High Contrast": dict(bg=(0,   0,   0  ), text=(255, 255, 0  ), opacity=0.97),
    "Solarized":     dict(bg=(0,   43,  54 ), text=(253, 246, 227), opacity=0.88),
    "Cinema Blue":   dict(bg=(5,   10,  30 ), text=(180, 215, 255), opacity=0.85),
}

# ─────────────────────────────────────────────────────────────────────────────
#  Persistence
# ─────────────────────────────────────────────────────────────────────────────
def _load_save() -> dict:
    if SAVE_FILE.exists():
        try:
            return json.loads(SAVE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"slots": {}, "last_text": ""}

def _write_save(data: dict) -> None:
    SAVE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
    )

# ─────────────────────────────────────────────────────────────────────────────
#  File helpers
# ─────────────────────────────────────────────────────────────────────────────
def _read_text_file(path: str) -> tuple[str, str | None]:
    """
    Return (text, error_msg).
    Tries multiple encodings so Windows-1252 / Latin-1 / UTF-16 files load cleanly.
    If PyMuPDF is installed, also handles .pdf paths.
    """
    p = Path(path)
    # ── PDF via PyMuPDF ───────────────────────────────────────────────────────
    if p.suffix.lower() == '.pdf':
        if not PYMUPDF_OK:
            return '', (
                "PDF text extraction requires PyMuPDF.\n\n"
                "Install with:  pip install PyMuPDF"
            )
        try:
            doc   = _fitz.open(str(p))
            pages = [page.get_text() for page in doc]
            doc.close()
            return '\n\n'.join(pages).strip(), None
        except Exception as exc:
            return '', f"Could not read PDF:\n{exc}"

    # ── Plain text with encoding probe ────────────────────────────────────────
    raw = p.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc), None
        except (UnicodeDecodeError, LookupError):
            continue
    return '', (
        "Could not decode the file with any known encoding.\n"
        "Please save the file as UTF-8 and try again."
    )

def _line_x(line_w: int, align: int, win_w: int, margin: int = 40) -> int:
    """Compute left x for a line given alignment — inlined for speed."""
    if   align == Qt.AlignHCenter: return max(0, (win_w - line_w) >> 1)
    elif align == Qt.AlignRight:   return max(0, win_w - margin - line_w)
    return margin   # AlignLeft (most common — fastest branch)

# ─────────────────────────────────────────────────────────────────────────────
#  Word x-position helper  (pure function, called only on cache miss)
# ─────────────────────────────────────────────────────────────────────────────
def _word_xs(words: list[str], fm: QFontMetrics,
             sp_w: int, align: int, win_w: int) -> list[tuple[str, int]]:
    total = sum(fm.horizontalAdvance(w) for w in words) + sp_w * (len(words) - 1)
    x0    = _line_x(total, align, win_w)
    out, x = [], x0
    for w in words:
        out.append((w, x))
        x += fm.horizontalAdvance(w) + sp_w
    return out

# ══════════════════════════════════════════════════════════════════════════════
#  Presenter Notes Window
# ══════════════════════════════════════════════════════════════════════════════
class NotesWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Presenter Notes")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.resize(420, 360)
        vl = QVBoxLayout(self)

        hdr = QLabel("Current Note")
        hdr.setFont(QFont("Arial", 10, QFont.Bold)); vl.addWidget(hdr)

        self._cur = QLabel("—")
        self._cur.setWordWrap(True)
        self._cur.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._cur.setFont(QFont("Arial", 16))
        self._cur.setStyleSheet(
            "background:#111a11;color:#b0ffb0;padding:12px;"
            "border-radius:8px;min-height:68px;"
        )
        vl.addWidget(self._cur)

        sep = QLabel(); sep.setFixedHeight(1)
        sep.setStyleSheet("background:#444;"); vl.addWidget(sep)

        sub = QLabel("All notes  (syntax: [[note text]])")
        sub.setFont(QFont("Arial", 9))
        sub.setStyleSheet("color:#888;"); vl.addWidget(sub)

        self._all = QTextEdit()
        self._all.setReadOnly(True)
        self._all.setFont(QFont("Courier New", 11))
        self._all.setStyleSheet("background:#111;color:#ccc;")
        vl.addWidget(self._all)

    def set_current(self, note: str | None) -> None:
        active = bool(note)
        self._cur.setText(note or "—")
        self._cur.setStyleSheet(
            ("background:#0d2d0d;color:#90ff90;" if active else
             "background:#111a11;color:#b0ffb0;")
            + "padding:12px;border-radius:8px;min-height:68px;"
        )

    def set_all(self, note_map: dict, lines: list) -> None:
        if not note_map:
            self._all.setPlainText(
                "(No notes — add [[note text]] anywhere in your script)"
            ); return
        parts = []
        for idx in sorted(note_map):
            ctx = lines[idx][:55] + "…" if idx < len(lines) else ""
            parts.append(f"Line {idx+1}: {ctx}\n  → {note_map[idx]}\n")
        self._all.setPlainText('\n'.join(parts))


# ══════════════════════════════════════════════════════════════════════════════
#  Teleprompter Display Window
# ══════════════════════════════════════════════════════════════════════════════
class TeleprompterWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TelePrompter")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ── Playback state ────────────────────────────────────────────────────
        self.text           : str   = ""
        self.scroll_y       : float = 0.0
        self.is_playing     : bool  = False
        self.speed          : float = 2.0   # logical px per 16.667 ms (60 fps unit)

        # ── Visual settings ───────────────────────────────────────────────────
        self.font_family         : str   = "Arial"
        self.font_size           : int   = 48
        self.text_color          : QColor = QColor(255, 255, 255)
        self.bg_color            : QColor = QColor(0, 0, 0)
        self.bg_opacity          : float  = 0.70
        self.mirror_mode         : bool   = False
        self.word_highlight      : bool   = True
        self.line_spacing_factor : float  = 1.2
        self.focus_ratio         : float  = 0.50
        self.text_align          : int    = Qt.AlignLeft

        # ── Countdown ─────────────────────────────────────────────────────────
        self.countdown_secs : int        = 3
        self._cd_val        : int | None = None
        self._cd_timer      = QTimer(self)
        self._cd_timer.setInterval(1000)
        self._cd_timer.timeout.connect(self._cd_tick)

        # ── Frame-rate-independent scroll ─────────────────────────────────────
        self._elapsed      = QElapsedTimer()
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(16)    # target ~60 fps
        self._scroll_timer.timeout.connect(self._scroll_step)

        # ── Mic auto-speed ────────────────────────────────────────────────────
        self.auto_speed_enabled : bool  = False
        self.mic_threshold      : float = 0.025
        self._mic_smooth        : float = 0.0   # smoothed speed for mic mode
        self._mic_target        : float = 0.0   # set by audio callback
        self._mic_stream        = None

        # ── Caches ────────────────────────────────────────────────────────────
        # Font cache — rebuilt only when font family / size / spacing changes
        self._font_key   : tuple        = ()
        self._f_font     : QFont | None = None
        self._f_fm       : QFontMetrics | None = None
        self._f_asc      : int          = 0
        self._f_line_h   : int          = 1
        self._f_sp_w     : int          = 8

        # Layout cache — rebuilt when text / width / font / align changes
        self._layout_key : tuple        = ()
        self._l_lines    : list[str]    = []
        self._l_word_xs  : list         = []
        self._l_pause    : set          = set()
        self._l_notes    : dict         = {}
        self._l_total    : float        = 0.0

        # Paint color cache — pre-built QColor ARGB ints
        self._c_bg           : QColor = QColor(0, 0, 0, 178)
        self._c_focus_band   : QColor = QColor(255, 255, 255, 20)
        self._c_guide        : QColor = QColor(255, 210, 0, 75)
        self._c_highlight    : QColor = QColor(255, 230, 50)
        self._c_shadow_base  : int    = 0   # RGBA int — shadow alpha computed from LUT
        self._rebuild_color_cache()

        # Progress throttle
        self._prog_frame : int = 0

        # Focus-line tracking (for PAUSE + notes)
        self._last_fl : int = -1

        # Callbacks from ControlPanel
        self._panel_sync    = None
        self._progress_sync = None
        self._wpm_sync      = None

        # Notes window
        self.notes_window = NotesWindow()

        # Drag
        self._drag_pos = None

        self._build_touch_overlay()

        # Resize grip (bottom-right corner) for frameless window
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(22, 22)
        self._grip.setStyleSheet(
            "QSizeGrip{background:rgba(255,255,255,35);border-radius:4px;}"
        )

        self.setMinimumSize(640, 420)
        self.resize(920, 560)

    # ── Color cache ───────────────────────────────────────────────────────────
    def _rebuild_color_cache(self) -> None:
        c = QColor(self.bg_color)
        c.setAlphaF(self.bg_opacity)
        self._c_bg = c

    # ── Font + metric cache ───────────────────────────────────────────────────
    def _ensure_font(self) -> None:
        key = (self.font_family, self.font_size, self.line_spacing_factor)
        if key == self._font_key:
            return
        f  = QFont(self.font_family, self.font_size, QFont.Bold)
        fm = QFontMetrics(f)
        lh = max(1, int(fm.lineSpacing() * self.line_spacing_factor))
        self._f_font   = f
        self._f_fm     = fm
        self._f_asc    = fm.ascent()
        self._f_line_h = lh
        self._f_sp_w   = fm.horizontalAdvance(' ')
        self._font_key = key
        self._layout_key = ()   # font changed → layout invalid

    # ── Layout cache ──────────────────────────────────────────────────────────
    def _ensure_layout(self) -> None:
        self._ensure_font()
        W     = self.width()
        key   = (self.text, W, self._font_key, self.text_align)
        if key == self._layout_key:
            return

        fm    = self._f_fm
        sp_w  = self._f_sp_w
        lh    = self._f_line_h
        align = self.text_align
        mw    = W - 80

        lines : list[str]  = []
        wxs   : list       = []
        pauses: set        = set()
        notes : dict       = {}

        for raw in self.text.split('\n'):
            nm   = _NOTE_RE.search(raw)
            note = nm.group(1).strip() if nm else None
            para = _NOTE_RE.sub('', raw).strip()
            fi   = len(lines)                          # first line index for this para

            if not para:
                lines.append(''); wxs.append([])
            elif para == _PAUSE_TAG:
                pauses.add(len(lines))
                lines.append(_PAUSE_TAG); wxs.append([])
            else:
                cur_w  = 0
                cur_ws : list[str] = []
                for word in para.split():
                    ww     = fm.horizontalAdvance(word)
                    needed = ww if not cur_ws else sp_w + ww
                    if cur_w + needed <= mw:
                        cur_ws.append(word); cur_w += needed
                    else:
                        if cur_ws:
                            lines.append(' '.join(cur_ws))
                            wxs.append(_word_xs(cur_ws, fm, sp_w, align, W))
                        cur_ws, cur_w = [word], ww
                if cur_ws:
                    lines.append(' '.join(cur_ws))
                    wxs.append(_word_xs(cur_ws, fm, sp_w, align, W))

            if note is not None:
                notes[fi] = note

        self._l_lines    = lines
        self._l_word_xs  = wxs
        self._l_pause    = pauses
        self._l_notes    = notes
        self._l_total    = float(len(lines) * lh)
        self._layout_key = key

        # Refresh notes window
        self.notes_window.set_all(notes, lines)

    def invalidate_layout(self) -> None:
        """Call after any setting that affects font or line layout."""
        self._font_key   = ()
        self._layout_key = ()
        self._rebuild_color_cache()
        self.update()

    # ── Touch overlay ─────────────────────────────────────────────────────────
    def _build_touch_overlay(self):
        self._touch_bar = QWidget(self)
        self._touch_bar.setStyleSheet(
            "QWidget{background:rgba(0,0,0,145);border-radius:14px;}")
        bl = QHBoxLayout(self._touch_bar)
        bl.setContentsMargins(14, 9, 14, 9); bl.setSpacing(12)

        def tbtn(lbl, fn, col="#444"):
            b = QPushButton(lbl)
            b.setFont(QFont("Arial", 18, QFont.Bold))
            b.setFixedSize(64, 64)
            b.setStyleSheet(
                f"QPushButton{{background:{col};color:white;border-radius:32px;}}"
                "QPushButton:pressed{background:#666;}")
            b.clicked.connect(fn); return b

        self._tplay_btn = tbtn("▶", self.toggle_play, "#27ae60")
        bl.addWidget(tbtn("⏮", self.reset, "#c0392b"))
        bl.addWidget(self._tplay_btn)
        bl.addWidget(tbtn("−", self._speed_dn, "#555"))
        bl.addWidget(tbtn("+", self._speed_up, "#555"))
        self._touch_bar.adjustSize()
        self._touch_bar.hide()

    def _repos_touch(self):
        bar = self._touch_bar; bar.adjustSize()
        bar.move((self.width() - bar.width()) // 2,
                  self.height() - bar.height() - 20)

    def _sync_touch_play(self):
        self._tplay_btn.setText("⏸" if self.is_playing else "▶")

    def set_touch_controls(self, v: bool):
        (self._touch_bar.show() if v else self._touch_bar.hide())
        if v: self._touch_bar.raise_()

    def _speed_up(self):
        self.speed = min(self.speed + 0.5, 20.0)
        if self._panel_sync: self._panel_sync()

    def _speed_dn(self):
        self.speed = max(self.speed - 0.5, 0.5)
        if self._panel_sync: self._panel_sync()

    # ── Public API ────────────────────────────────────────────────────────────
    def set_text(self, text: str) -> None:
        self.text = text; self.scroll_y = 0.0
        self._layout_key = ()
        self.update()

    def toggle_play(self) -> None:
        if self._cd_val is not None:
            self._cd_timer.stop(); self._cd_val = None
            self.update()
            if self._panel_sync: self._panel_sync()
            return
        if not self.is_playing:
            self._start_countdown() if self.countdown_secs > 0 else self._begin_play()
        else:
            self._do_pause()

    def reset(self) -> None:
        self._cd_timer.stop(); self._cd_val = None
        self.scroll_y = 0.0; self.is_playing = False
        self._last_fl = -1
        self._scroll_timer.stop()
        self._sync_touch_play()
        self.update()
        if self._panel_sync: self._panel_sync()

    # ── Countdown ─────────────────────────────────────────────────────────────
    def _start_countdown(self):
        self._cd_val = self.countdown_secs
        self._cd_timer.start(); self.update()
        if self._panel_sync: self._panel_sync()

    def _cd_tick(self):
        self._cd_val -= 1
        if self._cd_val <= 0:
            self._cd_timer.stop(); self._cd_val = None; self._begin_play()
        self.update()

    def _begin_play(self):
        self.is_playing = True; self._elapsed.start()
        self._scroll_timer.start(); self._sync_touch_play()
        if self._panel_sync: self._panel_sync()

    def _do_pause(self):
        self.is_playing = False; self._scroll_timer.stop()
        self._sync_touch_play()
        if self._panel_sync: self._panel_sync()

    # ── Frame-rate-independent scroll step ────────────────────────────────────
    def _scroll_step(self) -> None:
        dt_ms = max(1, min(self._elapsed.restart(), 100))  # clamp 1–100 ms

        # Mic auto-speed: low-pass smooth toward target
        if self.auto_speed_enabled:
            self._mic_smooth += 0.10 * (self._mic_target - self._mic_smooth)
            eff = max(0.0, self._mic_smooth)
        else:
            eff = self.speed

        self.scroll_y += (eff / 16.667) * dt_ms

        # Ensure layout is current (cheap — cache check only)
        self._ensure_layout()
        lh    = self._f_line_h
        total = self._l_total

        # PAUSE + notes check (only when focus line changes)
        if lh > 0:
            fl = int(self.scroll_y / lh)
            if fl != self._last_fl:
                self._last_fl = fl
                if fl in self._l_pause:
                    self.scroll_y = float(fl * lh)
                    self._do_pause()
                    self.update(); return
                self.notes_window.set_current(self._l_notes.get(fl))

        if self.scroll_y >= total:
            self.scroll_y = total; self.is_playing = False
            self._scroll_timer.stop(); self._sync_touch_play()
            if self._panel_sync: self._panel_sync()

        # Throttle progress + WPM to every 8 frames (~7.5 fps)
        self._prog_frame += 1
        if self._prog_frame >= 8:
            self._prog_frame = 0
            if self._progress_sync: self._progress_sync(self.scroll_y, total)
            if self._wpm_sync:      self._wpm_sync(self._calc_wpm(total))

        self.update()

    # ── WPM estimate ──────────────────────────────────────────────────────────
    def _calc_wpm(self, total_px: float) -> int:
        if total_px <= 0: return 0
        words = len([w for w in self.text.split() if w and '[' not in w])
        return int((self.speed * 60.0 / 16.667 * 60) * (words / total_px))

    # ── Mic ───────────────────────────────────────────────────────────────────
    def start_mic(self):
        if not MIC_OK or self._mic_stream: return
        try:
            thr = self.mic_threshold
            def cb(indata, *_):
                rms = float(_np.sqrt(_np.mean(indata ** 2)))
                self._mic_target = self.speed if rms > thr else 0.0
            self._mic_stream = _sd.InputStream(
                samplerate=16000, channels=1, blocksize=512, callback=cb)
            self._mic_stream.start()
        except Exception as exc:
            print(f"[Mic] {exc}")

    def stop_mic(self):
        if self._mic_stream:
            try: self._mic_stream.stop(); self._mic_stream.close()
            except Exception: pass
            self._mic_stream = None

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        W, H    = self.width(), self.height()
        focus_y = int(H * self.focus_ratio)

        # Background (cached QColor — no new object)
        painter.fillRect(0, 0, W, H, self._c_bg)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRect(0, 0, W - 1, H - 1)

        # ── Countdown overlay ──────────────────────────────────────────────────
        if self._cd_val is not None:
            self._ensure_font()
            painter.setPen(QColor(255, 210, 0, 235))
            painter.setFont(QFont(self._f_font.family(), 110, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, str(self._cd_val))
            return

        # ── Empty hint ─────────────────────────────────────────────────────────
        if not self.text:
            painter.setPen(QColor(150, 150, 150))
            painter.setFont(QFont("Arial", 18))
            painter.drawText(self.rect(), Qt.AlignCenter,
                "Type your script in the control panel\n\n"
                "[PAUSE]         — auto-pause at this point\n"
                "[[note text]]   — private presenter note")
            return

        # ── Ensure caches are current ──────────────────────────────────────────
        self._ensure_layout()
        lines   = self._l_lines
        word_xs = self._l_word_xs
        pauses  = self._l_pause
        lh      = self._f_line_h
        asc     = self._f_asc
        fm      = self._f_fm
        font    = self._f_font
        align   = self.text_align

        painter.setFont(font)

        # Focus band
        painter.fillRect(0, focus_y - lh, W, lh * 2, self._c_focus_band)

        # Focus line index + fractional position
        frac       = self.scroll_y / lh if lh else 0.0
        fl_idx     = int(frac)
        fl_frac    = frac - fl_idx

        if self.mirror_mode:
            painter.scale(-1, 1); painter.translate(-W, 0)

        start_y    = focus_y - int(self.scroll_y)
        # Compute visible range arithmetically — never loop over hidden lines
        first_i    = max(0, (-start_y - lh * 2) // lh)
        last_i     = min(len(lines), first_i + (H + lh * 4) // lh + 1)

        # Cached ARGB components of text_color (avoid attribute lookup in loop)
        tc_r = self.text_color.red()
        tc_g = self.text_color.green()
        tc_b = self.text_color.blue()

        for i in range(first_i, last_i):
            line = lines[i]
            y    = start_y + i * lh
            ay   = y + asc            # baseline y

            dist  = abs(ay - focus_y)
            alpha = _ALPHA_LUT[min(dist, 511)]   # O(1) LUT lookup

            if alpha < 8:
                continue              # fully transparent — skip draw

            # ── PAUSE marker ───────────────────────────────────────────────────
            if i in pauses:
                mid = y + lh // 2
                painter.setPen(QPen(QColor(255, 140, 0, alpha), 1, Qt.DashLine))
                painter.drawLine(60, mid, W - 60, mid)
                if alpha > 30:
                    painter.setPen(QColor(255, 165, 0, alpha))
                    painter.setFont(QFont(self.font_family, 14))
                    painter.drawText(W // 2 - 38, mid + 7, "⏸  PAUSE")
                    painter.setFont(font)
                continue

            # ── Normal line ────────────────────────────────────────────────────
            # Shadow (pre-alpha'd, one draw call for whole line)
            shad_alpha = min(255, alpha >> 1)     # alpha / 2
            painter.setPen(QColor(0, 0, 0, shad_alpha))
            lw   = fm.horizontalAdvance(line)
            lx   = _line_x(lw, align, W)
            painter.drawText(lx + 1, ay + 2, line)

            at_focus = (i == fl_idx)

            if self.word_highlight and at_focus and word_xs[i]:
                # Word-highlight path — positions already cached
                wxl  = word_xs[i]
                n    = len(wxl)
                whi  = min(int(fl_frac * n), n - 1)
                for wi, (word, wx) in enumerate(wxl):
                    if wi == whi:
                        # Extra glow shadow
                        painter.setPen(QColor(0, 0, 0, 180))
                        painter.drawText(wx + 2, ay + 2, word)
                        c = QColor(self._c_highlight); c.setAlpha(alpha)
                    else:
                        c = QColor(tc_r, tc_g, tc_b, alpha)
                    painter.setPen(c)
                    painter.drawText(wx, ay, word)
            else:
                # Fast path: single drawText for whole line
                c = QColor(tc_r, tc_g, tc_b, alpha)
                painter.setPen(c)
                painter.drawText(lx, ay, line)

        # Guide lines (cached QColor)
        painter.setPen(QPen(self._c_guide, 1))
        painter.drawLine(0, focus_y - lh, W, focus_y - lh)
        painter.drawLine(0, focus_y + lh, W, focus_y + lh)

    # ── Keyboard ──────────────────────────────────────────────────────────────
    def keyPressEvent(self, e):
        k = e.key()
        if   k in (Qt.Key_Space, Qt.Key_Return): self.toggle_play()
        elif k == Qt.Key_Up:    self._speed_up()
        elif k == Qt.Key_Down:  self._speed_dn()
        elif k == Qt.Key_Left:  self.scroll_y = max(0.0, self.scroll_y - 80); self.update()
        elif k == Qt.Key_Right: self.scroll_y += 80; self.update()
        elif k in (Qt.Key_R, Qt.Key_Escape): self.reset()

    def wheelEvent(self, e):
        (self._speed_up if e.angleDelta().y() > 0 else self._speed_dn)()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.pos()
    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() == Qt.LeftButton:
            self.move(e.globalPos() - self._drag_pos)
    def mouseReleaseEvent(self, _): self._drag_pos = None

    def resizeEvent(self, _):
        self._layout_key = ()       # width changed → re-wrap (font cache kept)
        self._repos_touch()
        self._repos_grip()
        self.update()

    def showEvent(self, _):
        self._repos_touch()
        self._repos_grip()

    def _repos_grip(self):
        g = self._grip
        g.move(self.width() - g.width() - 4, self.height() - g.height() - 4)
        g.raise_()


# ══════════════════════════════════════════════════════════════════════════════
#  Control Panel
# ══════════════════════════════════════════════════════════════════════════════
class ControlPanel(QWidget):

    def __init__(self, prompter: TeleprompterWindow):
        super().__init__()
        self.prompter   = prompter
        self._save_data = _load_save()

        prompter._panel_sync    = self._sync_play_btn
        prompter._progress_sync = self._sync_progress
        prompter._wpm_sync      = self._sync_wpm

        self.setWindowTitle("TelePrompter — Control Panel")
        self.setMinimumWidth(580)

        # Debounce timer: wait 280 ms after last keystroke before updating prompter
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(280)
        self._debounce.timeout.connect(self._flush_text)

        self._build_ui()
        self._restore_autosave()
        self._setup_global_hotkeys()

    def _flush_text(self):
        self.prompter.set_text(self._editor.toPlainText())

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8); root.setContentsMargins(14, 14, 14, 14)

        title = QLabel("🎬  TelePrompter")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter); root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._tab_script(),   "📝  Script")
        tabs.addTab(self._tab_playback(), "▶  Playback")
        tabs.addTab(self._tab_display(),  "🖥  Display")
        tabs.addTab(self._tab_mic(),      "🎙  Mic / WPM")
        tabs.addTab(self._tab_advanced(), "⚙  Advanced")
        root.addWidget(tabs)

        pg = QGroupBox("Progress"); pl = QVBoxLayout(pg)
        self._prog = QProgressBar()
        self._prog.setRange(0, 1000); self._prog.setValue(0)
        self._prog.setTextVisible(False); self._prog.setFixedHeight(10)
        self._time_lbl = QLabel("Time remaining: —")
        self._time_lbl.setAlignment(Qt.AlignCenter)
        self._time_lbl.setStyleSheet("color:#aaa;font-size:12px;")
        self._wpm_lbl = QLabel("WPM: —")
        self._wpm_lbl.setAlignment(Qt.AlignCenter)
        self._wpm_lbl.setStyleSheet("color:#7ec8e3;font-size:12px;font-weight:bold;")
        hr = QHBoxLayout()
        hr.addWidget(self._time_lbl); hr.addWidget(self._wpm_lbl)
        pl.addWidget(self._prog); pl.addLayout(hr)
        root.addWidget(pg)

        hint = QLabel(
            "⌨  Space/Enter = Play  |  ↑↓ = Speed  |  ←→ = Skip  |  R/Esc = Reset  |  🖱 Wheel = Speed"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#555;font-size:10px;"); root.addWidget(hint)

    # ── Tab: Script ───────────────────────────────────────────────────────────
    def _tab_script(self):
        w = QWidget(); vl = QVBoxLayout(w)

        sr = QHBoxLayout(); sr.addWidget(QLabel("Slot:"))
        self._slot_cb = QComboBox(); self._slot_cb.setMinimumWidth(140)
        self._refresh_slots(); sr.addWidget(self._slot_cb, 1)
        for lbl, fn in [("💾 Save", self._save_slot),
                         ("📂 Load", self._load_slot),
                         ("🗑", self._del_slot)]:
            b = QPushButton(lbl); b.setFixedHeight(30); b.clicked.connect(fn)
            sr.addWidget(b)
        vl.addLayout(sr)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText(
            "Type your script here…\n\n"
            "Special tags:\n"
            "  [PAUSE]         — auto-pause scroll when reached\n"
            "  [[note text]]   — presenter note (visible only in Notes window)"
        )
        self._editor.setMinimumHeight(180)
        self._editor.setUndoRedoEnabled(True)
        # Debounced: don't re-layout on every keystroke
        self._editor.textChanged.connect(self._debounce.start)
        vl.addWidget(self._editor)

        br = QHBoxLayout()
        for lbl, fn in [("↩  Undo",       self._editor.undo),
                         ("↪  Redo",       self._editor.redo),
                         ("📂  Load File", self._load_file)]:
            b = QPushButton(lbl); b.setFixedHeight(30); b.clicked.connect(fn)
            br.addWidget(b)
        vl.addLayout(br)

        tip = QLabel("Ctrl+Z / Ctrl+Y also work for undo / redo")
        tip.setStyleSheet("color:#666;font-size:10px;")
        tip.setAlignment(Qt.AlignCenter); vl.addWidget(tip)
        return w

    # ── Tab: Playback ─────────────────────────────────────────────────────────
    def _tab_playback(self):
        w = QWidget(); vl = QVBoxLayout(w)

        row = QHBoxLayout()
        self._play_btn = QPushButton("▶  Play")
        self._play_btn.setMinimumHeight(50)
        self._play_btn.clicked.connect(self.prompter.toggle_play)
        self._style_btn(self._play_btn, "#27ae60")
        rst = QPushButton("⏮  Reset"); rst.setMinimumHeight(50)
        rst.clicked.connect(self.prompter.reset)
        self._style_btn(rst, "#c0392b")
        row.addWidget(self._play_btn, 3); row.addWidget(rst, 1)
        vl.addLayout(row)

        g = QGroupBox("Settings"); gl = QGridLayout(g); gl.setColumnStretch(1, 1)

        gl.addWidget(QLabel("Scroll Speed:"), 0, 0)
        self._speed_sl = QSlider(Qt.Horizontal)
        self._speed_sl.setRange(1, 40); self._speed_sl.setValue(4)
        self._speed_sl.valueChanged.connect(self._on_speed)
        self._speed_lbl = QLabel("2.0 px/fr"); self._speed_lbl.setFixedWidth(72)
        gl.addWidget(self._speed_sl, 0, 1); gl.addWidget(self._speed_lbl, 0, 2)

        gl.addWidget(QLabel("Countdown (sec):"), 1, 0)
        self._cd_spin = QSpinBox(); self._cd_spin.setRange(0, 10)
        self._cd_spin.setValue(3)
        self._cd_spin.valueChanged.connect(
            lambda v: setattr(self.prompter, 'countdown_secs', v))
        gl.addWidget(self._cd_spin, 1, 1, 1, 2)
        vl.addWidget(g)

        wg = QGroupBox("Display Window"); wl = QHBoxLayout(wg)
        for lbl, fn, col in [
            ("Show",         self.prompter.show,               "#2980b9"),
            ("Hide",         self.prompter.hide,               "#7f8c8d"),
            ("Notes Window", self._show_notes,                 "#8e44ad"),
        ]:
            b = QPushButton(lbl); b.clicked.connect(fn); self._style_btn(b, col)
            wl.addWidget(b)
        vl.addWidget(wg); vl.addStretch()
        return w

    def _show_notes(self):
        self.prompter.notes_window.show()
        self.prompter.notes_window.raise_()

    # ── Tab: Display ──────────────────────────────────────────────────────────
    def _tab_display(self):
        w = QWidget(); g = QGridLayout(w); g.setColumnStretch(1, 1); r = 0

        def add_row(lbl, widget, span=2):
            nonlocal r
            g.addWidget(QLabel(lbl), r, 0)
            g.addWidget(widget, r, 1, 1, span); r += 1

        # Theme
        self._theme_cb = QComboBox()
        self._theme_cb.addItems(list(THEMES))
        self._theme_cb.currentTextChanged.connect(self._apply_theme)
        add_row("Theme:", self._theme_cb)

        # Font family
        self._font_cb = QFontComboBox()
        self._font_cb.setCurrentFont(QFont("Arial"))
        self._font_cb.currentFontChanged.connect(
            lambda f: (setattr(self.prompter, 'font_family', f.family()),
                       self.prompter.invalidate_layout()))
        add_row("Font:", self._font_cb)

        # Font size
        self._font_sl = QSlider(Qt.Horizontal)
        self._font_sl.setRange(16, 120); self._font_sl.setValue(48)
        self._font_sl.valueChanged.connect(self._on_font)
        self._font_lbl = QLabel("48 pt"); self._font_lbl.setFixedWidth(52)
        g.addWidget(QLabel("Font Size:"), r, 0)
        g.addWidget(self._font_sl, r, 1); g.addWidget(self._font_lbl, r, 2); r += 1

        # Line spacing
        self._ls_sl = QSlider(Qt.Horizontal)
        self._ls_sl.setRange(10, 30); self._ls_sl.setValue(12)
        self._ls_sl.valueChanged.connect(self._on_ls)
        self._ls_lbl = QLabel("1.2×"); self._ls_lbl.setFixedWidth(52)
        g.addWidget(QLabel("Line Spacing:"), r, 0)
        g.addWidget(self._ls_sl, r, 1); g.addWidget(self._ls_lbl, r, 2); r += 1

        # Text alignment
        self._align_cb = QComboBox()
        self._align_cb.addItems(["Left", "Center", "Right"])
        self._align_cb.currentIndexChanged.connect(self._on_align)
        add_row("Text Align:", self._align_cb)

        # BG opacity
        self._opa_sl = QSlider(Qt.Horizontal)
        self._opa_sl.setRange(0, 95); self._opa_sl.setValue(70)
        self._opa_sl.valueChanged.connect(self._on_opacity)
        self._opa_lbl = QLabel("70 %"); self._opa_lbl.setFixedWidth(52)
        g.addWidget(QLabel("BG Opacity:"), r, 0)
        g.addWidget(self._opa_sl, r, 1); g.addWidget(self._opa_lbl, r, 2); r += 1

        # Colors
        self._txt_col_btn = QPushButton()
        self._txt_col_btn.clicked.connect(self._pick_text_color)
        self._apply_color_btn(self._txt_col_btn, QColor(255, 255, 255))
        add_row("Text Color:", self._txt_col_btn)

        self._bg_col_btn = QPushButton()
        self._bg_col_btn.clicked.connect(self._pick_bg_color)
        self._apply_color_btn(self._bg_col_btn, QColor(0, 0, 0))
        add_row("BG Color:", self._bg_col_btn)

        # Focus zone
        self._focus_cb = QComboBox()
        self._focus_cb.addItems(["Top (25%)", "Center (50%)", "Bottom (75%)"])
        self._focus_cb.setCurrentIndex(1)
        self._focus_cb.currentIndexChanged.connect(
            lambda i: (setattr(self.prompter, 'focus_ratio', [0.25, 0.50, 0.75][i]),
                       self.prompter.update()))
        add_row("Focus Zone:", self._focus_cb)

        # Checkboxes
        def cb(label, attr, default=True):
            c = QCheckBox(label); c.setChecked(default)
            c.toggled.connect(
                lambda v: (setattr(self.prompter, attr, v), self.prompter.update()))
            return c

        add_row("Word Highlight:", cb("Glow current word", "word_highlight"))
        add_row("Mirror Mode:",    cb("Flip horizontally (for physical mirror glass)",
                                      "mirror_mode", False))

        self._touch_cb = QCheckBox("Show overlay buttons on prompter window")
        self._touch_cb.setChecked(True)
        self._touch_cb.toggled.connect(self.prompter.set_touch_controls)
        self.prompter.set_touch_controls(True)
        add_row("Touch Controls:", self._touch_cb)

        g.setRowStretch(r, 1)
        return w

    # ── Tab: Mic / WPM ────────────────────────────────────────────────────────
    def _tab_mic(self):
        w = QWidget(); vl = QVBoxLayout(w)

        wg = QGroupBox("📊  WPM Tracker"); wl = QVBoxLayout(wg)
        self._wpm_big = QLabel("—")
        self._wpm_big.setFont(QFont("Arial", 38, QFont.Bold))
        self._wpm_big.setAlignment(Qt.AlignCenter)
        self._wpm_big.setStyleSheet("color:#7ec8e3;")
        wl.addWidget(self._wpm_big)
        wl.addWidget(QLabel("Comfortable reading: 120–180 WPM",
                            alignment=Qt.AlignCenter))
        vl.addWidget(wg)

        mg = QGroupBox("🎙  Auto-Speed (Voice Detection)"); ml = QVBoxLayout(mg)
        if MIC_OK:
            self._mic_ck = QCheckBox("Pause scroll when not speaking")
            self._mic_ck.toggled.connect(self._on_mic)
            ml.addWidget(self._mic_ck)
            tr = QHBoxLayout(); tr.addWidget(QLabel("Sensitivity:"))
            self._thr_sl = QSlider(Qt.Horizontal)
            self._thr_sl.setRange(1, 20); self._thr_sl.setValue(5)
            self._thr_lbl = QLabel("0.025"); self._thr_lbl.setFixedWidth(46)
            self._thr_sl.valueChanged.connect(
                lambda v: (setattr(self.prompter, 'mic_threshold', v / 200.0),
                           self._thr_lbl.setText(f"{v/200:.3f}")))
            tr.addWidget(self._thr_sl); tr.addWidget(self._thr_lbl)
            ml.addLayout(tr)
        else:
            ml.addWidget(QLabel(
                "❌  pip install sounddevice numpy", alignment=Qt.AlignCenter))
        vl.addWidget(mg); vl.addStretch()
        return w

    # ── Tab: Advanced ─────────────────────────────────────────────────────────
    def _tab_advanced(self):
        w = QWidget(); vl = QVBoxLayout(w)

        hg = QGroupBox("Global Hotkeys"); hl = QVBoxLayout(hg)
        lbl = QLabel(
            "✅  Active — Space = Play/Pause  |  R = Reset\n"
            "     Works even when window is unfocused." if HOTKEY_OK else
            "❌  pip install keyboard  (Linux may need sudo)"
        )
        lbl.setStyleSheet(f"color:{'#2ecc71' if HOTKEY_OK else '#e74c3c'};")
        lbl.setWordWrap(True); hl.addWidget(lbl); vl.addWidget(hg)

        ag = QGroupBox("Auto-Save"); al = QVBoxLayout(ag)
        al.addWidget(QLabel(f"✅  Saved on close → {SAVE_FILE}"))
        vl.addWidget(ag)

        if PDF_PRINT_OK:
            pg = QGroupBox("📄  Export as PDF"); pl = QVBoxLayout(pg)
            pl.addWidget(QLabel(
                "Exports full script to a printable PDF.\n"
                "PDF text import is handled by the Load File dialog."
            ))
            eb = QPushButton("📄  Export Script as PDF")
            eb.setMinimumHeight(38); eb.clicked.connect(self._export_pdf)
            self._style_btn(eb, "#16a085"); pl.addWidget(eb)
            vl.addWidget(pg)

        og = QGroupBox("Performance"); ol = QVBoxLayout(og)
        ol.addWidget(QLabel(
            "✅  Frame-rate-independent scroll (QElapsedTimer Δt)\n"
            "✅  Alpha fade from 512-entry LUT — no per-line math\n"
            "✅  Font metrics cached until settings change\n"
            "✅  Line layout + word-x positions cached\n"
            "✅  Visible line range by arithmetic — hidden lines skipped\n"
            "✅  Text editor debounced (280 ms) — no relayout per keystroke\n"
            "✅  Progress + WPM throttled to ~7.5 fps\n"
            "✅  Paint QColors pre-built; text color ARGB unpacked before loop"
        ))
        vl.addWidget(og)
        vl.addStretch()
        return w

    # ── Slot helpers ──────────────────────────────────────────────────────────
    def _refresh_slots(self):
        self._slot_cb.clear()
        for n in self._save_data.get("slots", {}): self._slot_cb.addItem(n)

    def _save_slot(self):
        name, ok = QInputDialog.getText(self, "Save Slot", "Slot name:")
        if ok and name.strip():
            self._save_data.setdefault("slots", {})[name.strip()] = \
                self._editor.toPlainText()
            _write_save(self._save_data); self._refresh_slots()
            idx = self._slot_cb.findText(name.strip())
            if idx >= 0: self._slot_cb.setCurrentIndex(idx)

    def _load_slot(self):
        t = self._save_data.get("slots", {}).get(self._slot_cb.currentText())
        if t is not None: self._editor.setPlainText(t)

    def _del_slot(self):
        n = self._slot_cb.currentText()
        if n in self._save_data.get("slots", {}):
            del self._save_data["slots"][n]
            _write_save(self._save_data); self._refresh_slots()

    def _load_file(self):
        is_pymupdf = PYMUPDF_OK
        filt = ("Text & PDF Files (*.txt *.pdf);;Text Files (*.txt);;PDF Files (*.pdf);;All Files (*)"
                if is_pymupdf else
                "Text Files (*.txt);;All Files (*)")
        path, _ = QFileDialog.getOpenFileName(self, "Load Script", "", filt)
        if not path: return
        text, err = _read_text_file(path)
        if err:
            QMessageBox.warning(self, "Load Error", err); return
        self._editor.setPlainText(text)

    def _restore_autosave(self):
        last = self._save_data.get("last_text", "")
        if last:
            self._editor.blockSignals(True)
            self._editor.setPlainText(last)
            self._editor.blockSignals(False)
            self.prompter.set_text(last)

    # ── Global hotkeys ────────────────────────────────────────────────────────
    def _setup_global_hotkeys(self):
        if not HOTKEY_OK: return
        try:
            _kb.add_hotkey("space", self.prompter.toggle_play, suppress=False)
            _kb.add_hotkey("r",     self.prompter.reset,       suppress=False)
        except Exception:
            pass

    # ── Sync callbacks ────────────────────────────────────────────────────────
    def _sync_play_btn(self):
        p = self.prompter
        if p._cd_val is not None:
            self._play_btn.setText("⏹  Cancel Countdown")
            self._style_btn(self._play_btn, "#8e44ad")
        elif p.is_playing:
            self._play_btn.setText("⏸  Pause")
            self._style_btn(self._play_btn, "#e67e22")
        else:
            self._play_btn.setText("▶  Play")
            self._style_btn(self._play_btn, "#27ae60")
        v = int(p.speed * 2)
        self._speed_sl.blockSignals(True)
        self._speed_sl.setValue(v)
        self._speed_sl.blockSignals(False)
        self._speed_lbl.setText(f"{p.speed:.1f} px/fr")

    def _sync_progress(self, sy: float, total: float):
        if total <= 0: return
        self._prog.setValue(int(min(sy / total, 1.0) * 1000))
        secs  = (total - sy) / (self.prompter.speed * 60.0) if self.prompter.speed else 0
        m, s  = divmod(int(secs), 60)
        self._time_lbl.setText(f"Time remaining: {m}:{s:02d}")

    def _sync_wpm(self, wpm: int):
        self._wpm_big.setText(str(wpm)); self._wpm_lbl.setText(f"WPM: {wpm}")
        col = ("#aaa" if wpm < 100 else "#2ecc71" if wpm < 200
               else "#f39c12" if wpm < 280 else "#e74c3c")
        self._wpm_big.setStyleSheet(f"color:{col};")
        self._wpm_lbl.setStyleSheet(f"color:{col};font-size:12px;font-weight:bold;")

    # ── Setting slots ─────────────────────────────────────────────────────────
    def _on_speed(self, v):
        s = v / 2.0; self.prompter.speed = s
        self._speed_lbl.setText(f"{s:.1f} px/fr")

    def _on_font(self, v):
        self.prompter.font_size = v; self._font_lbl.setText(f"{v} pt")
        self.prompter.invalidate_layout()

    def _on_ls(self, v):
        f = v / 10.0; self.prompter.line_spacing_factor = f
        self._ls_lbl.setText(f"{f:.1f}×"); self.prompter.invalidate_layout()

    def _on_opacity(self, v):
        self.prompter.bg_opacity = v / 100.0; self._opa_lbl.setText(f"{v} %")
        self.prompter._rebuild_color_cache(); self.prompter.update()

    def _on_align(self, idx):
        self.prompter.text_align = [Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight][idx]
        self.prompter._layout_key = (); self.prompter.update()

    def _on_mic(self, v):
        self.prompter.auto_speed_enabled = v
        (self.prompter.start_mic if v else self.prompter.stop_mic)()

    def _apply_theme(self, name: str):
        if name not in THEMES: return
        t = THEMES[name]
        bg, tx = QColor(*t["bg"]), QColor(*t["text"])
        self.prompter.bg_color   = bg
        self.prompter.text_color = tx
        self.prompter.bg_opacity = t["opacity"]
        self._apply_color_btn(self._bg_col_btn,  bg)
        self._apply_color_btn(self._txt_col_btn, tx)
        v = int(t["opacity"] * 100)
        self._opa_sl.blockSignals(True); self._opa_sl.setValue(v)
        self._opa_sl.blockSignals(False); self._opa_lbl.setText(f"{v} %")
        self.prompter._rebuild_color_cache(); self.prompter.update()

    def _pick_text_color(self):
        c = QColorDialog.getColor(self.prompter.text_color, self, "Text Color")
        if c.isValid():
            self.prompter.text_color = c
            self._apply_color_btn(self._txt_col_btn, c); self.prompter.update()

    def _pick_bg_color(self):
        c = QColorDialog.getColor(self.prompter.bg_color, self, "Background Color")
        if c.isValid():
            self.prompter.bg_color = c
            self._apply_color_btn(self._bg_col_btn, c)
            self.prompter._rebuild_color_cache(); self.prompter.update()

    # ── PDF Export ────────────────────────────────────────────────────────────
    def _export_pdf(self):
        if not PDF_PRINT_OK: return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export as PDF", "script.pdf", "PDF Files (*.pdf)")
        if not path: return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        pnt = QPainter()
        if not pnt.begin(printer):
            QMessageBox.warning(self, "Export Failed", "Could not create PDF."); return

        PW, PH  = printer.width(), printer.height()
        marg    = int(PW * 0.09)
        mw      = PW - 2 * marg
        bf      = QFont("Arial", 36); bfm = QFontMetrics(bf); lh = bfm.lineSpacing() + 10
        tf      = QFont("Arial", 52, QFont.Bold); tfm = QFontMetrics(tf)
        y       = marg

        pnt.setFont(tf); pnt.setPen(QColor(30, 30, 30))
        pnt.drawText(marg, y + tfm.ascent(), "Script")
        y += tfm.lineSpacing() + lh // 2
        pnt.setPen(QPen(QColor(120, 120, 120), 2))
        pnt.drawLine(marg, y, PW - marg, y); y += lh

        pnt.setFont(bf); sp_w = bfm.horizontalAdvance(' ')
        clean = _NOTE_RE.sub('', self._editor.toPlainText())

        for raw in clean.split('\n'):
            para = raw.strip()
            if not para:
                y += lh // 2; continue
            if y + lh * 2 > PH - marg: printer.newPage(); y = marg

            if para == _PAUSE_TAG:
                mid = y + lh // 2
                pnt.setPen(QPen(QColor(200, 100, 0), 1, Qt.DashLine))
                pnt.drawLine(marg, mid, PW - marg, mid)
                pf = QFont("Arial", 24); pfm = QFontMetrics(pf)
                pnt.setFont(pf); pnt.setPen(QColor(200, 100, 0))
                pnt.drawText(PW // 2 - 38, mid + pfm.ascent() // 2, "⏸ PAUSE")
                pnt.setFont(bf); y += lh; continue

            cur_w, cur = 0, []
            for word in para.split():
                ww = bfm.horizontalAdvance(word)
                needed = ww if not cur else sp_w + ww
                if cur_w + needed <= mw:
                    cur.append(word); cur_w += needed
                else:
                    if cur:
                        if y + lh > PH - marg: printer.newPage(); y = marg
                        pnt.setPen(QColor(20, 20, 20))
                        pnt.drawText(marg, y + bfm.ascent(), ' '.join(cur)); y += lh
                    cur, cur_w = [word], ww
            if cur:
                if y + lh > PH - marg: printer.newPage(); y = marg
                pnt.drawText(marg, y + bfm.ascent(), ' '.join(cur)); y += lh

        pnt.end()
        QMessageBox.information(self, "Export Complete", f"Saved:\n{path}")

    # ── Style helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _style_btn(btn, col: str):
        btn.setStyleSheet(
            f"QPushButton{{background:{col};color:white;border-radius:6px;"
            "font-size:13px;font-weight:bold;}}"
        )

    @staticmethod
    def _apply_color_btn(btn, color: QColor):
        fg = "black" if color.lightness() > 140 else "white"
        btn.setStyleSheet(
            f"QPushButton{{background:{color.name()};color:{fg};"
            "border-radius:4px;font-size:13px;}}"
        )
        btn.setText(f"●  {color.name().upper()}")

    # ── Close ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._debounce.stop()
        self._save_data["last_text"] = self._editor.toPlainText()
        _write_save(self._save_data)
        self.prompter.stop_mic()
        if HOTKEY_OK:
            try: _kb.remove_all_hotkeys()
            except Exception: pass
        self.prompter.notes_window.close()
        self.prompter.close()
        event.accept()



# ══════════════════════════════════════════════════════════════════════════════
#  App Icon  (drawn programmatically — no external file needed)
# ══════════════════════════════════════════════════════════════════════════════
def _make_icon():
    """
    Teleprompter-inspired icon:
      • Dark gradient rounded-square background
      • Three horizontal text lines (scroll metaphor)
      • Amber focus band across the middle line
      • Small green play-triangle in the bottom-right corner
    """
    from PyQt5.QtGui import QPixmap, QIcon, QBrush, QLinearGradient, QPolygon
    from PyQt5.QtCore import QPoint
    sz = 256
    px = QPixmap(sz, sz)
    px.fill(Qt.transparent)
    p  = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)

    # Background
    bg = QLinearGradient(0, 0, 0, sz)
    bg.setColorAt(0, QColor(28, 28, 40))
    bg.setColorAt(1, QColor(12, 12, 22))
    p.setBrush(QBrush(bg)); p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, sz - 8, sz - 8, 36, 36)

    # Border glow
    p.setPen(QPen(QColor(80, 160, 255, 55), 3))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(4, 4, sz - 8, sz - 8, 36, 36)

    # Three lines
    lx, lw, lh, r = 38, sz - 76, 18, 6
    ys = [82, 128, 174]

    # Focus band behind middle line
    p.setBrush(QColor(255, 200, 60, 38)); p.setPen(Qt.NoPen)
    p.drawRoundedRect(lx - 6, ys[1] - 4, lw + 12, lh + 8, 5, 5)

    for i, y in enumerate(ys):
        p.setPen(Qt.NoPen)
        if i == 1:
            g2 = QLinearGradient(lx, y, lx + lw, y)
            g2.setColorAt(0.0, QColor(255, 225, 80, 230))
            g2.setColorAt(1.0, QColor(255, 190, 30, 180))
            p.setBrush(QBrush(g2))
            w = lw
        else:
            p.setBrush(QColor(200, 200, 220, 110 if i == 0 else 75))
            w = int(lw * (0.72 if i == 0 else 0.55))
        p.drawRoundedRect(lx, y, w, lh, r, r)

    # Guide lines
    p.setPen(QPen(QColor(255, 200, 60, 115), 2))
    for dy in (-4, lh + 8):
        p.drawLine(lx - 10, ys[1] + dy, lx + lw + 10, ys[1] + dy)

    # Play triangle (bottom-right)
    tx, ty, ts = sz - 62, sz - 62, 34
    tri = QPolygon([QPoint(tx, ty + ts), QPoint(tx, ty), QPoint(tx + ts, ty + ts // 2)])
    p.setBrush(QColor(52, 199, 89, 215)); p.setPen(Qt.NoPen)
    p.drawPolygon(tri)

    p.end()
    return QIcon(px)


# ══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ══════════════════════════════════════════════════════════════════════════════
def _dark_palette() -> QPalette:
    pal = QPalette(); C = QColor
    pal.setColor(QPalette.Window,          C(38, 38, 38))
    pal.setColor(QPalette.WindowText,      C(220, 220, 220))
    pal.setColor(QPalette.Base,            C(26, 26, 26))
    pal.setColor(QPalette.AlternateBase,   C(38, 38, 38))
    pal.setColor(QPalette.Text,            C(220, 220, 220))
    pal.setColor(QPalette.Button,          C(52, 52, 52))
    pal.setColor(QPalette.ButtonText,      C(220, 220, 220))
    pal.setColor(QPalette.Highlight,       C(52, 152, 219))
    pal.setColor(QPalette.HighlightedText, C(255, 255, 255))
    return pal


def _arrange_windows(panel, prompter) -> None:
    """
    Place the two windows side-by-side on startup:
      • Control panel  → left side of screen, vertically centered
      • Prompter       → immediately to the right of the panel, same top edge,
                         fills the remaining horizontal space
    """
    screen = QApplication.primaryScreen()
    if screen is None:
        return
    sg = screen.availableGeometry()   # respects taskbar / dock

    # Let Qt size the panel naturally first
    panel.adjustSize()
    pw = panel.width()
    ph = min(panel.height(), sg.height() - 40)
    panel.resize(pw, ph)

    # Panel: 20 px from left edge, vertically centered
    px_pos = sg.x() + 20
    py_pos = sg.y() + (sg.height() - ph) // 2
    panel.move(px_pos, py_pos)

    # Prompter: right-adjacent to panel, same top, fills remaining width
    gap = 12
    tx  = px_pos + pw + gap
    ty  = py_pos
    tw  = max(640, sg.x() + sg.width() - tx - 20)
    th  = min(560, sg.height() - 40)
    prompter.resize(tw, th)
    prompter.move(tx, ty)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())

    icon = _make_icon()
    app.setWindowIcon(icon)

    prompter = TeleprompterWindow()
    prompter.setWindowIcon(icon)

    panel = ControlPanel(prompter)
    panel.setWindowIcon(icon)

    # Position windows before showing — no visible jump
    _arrange_windows(panel, prompter)

    panel.show()
    prompter.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
