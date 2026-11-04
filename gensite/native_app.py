"""Gensite native studio. No server, Chromium, or polling on the start view."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys
import threading
import time

STARTED = time.perf_counter()
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap, QPen, QLinearGradient
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QLineEdit, QFormLayout,
    QSpinBox, QComboBox, QStackedWidget, QToolBar, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QScrollArea, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QCheckBox, QProgressBar, QColorDialog, QFrame,
    QSizePolicy, QInputDialog)

from .engine import Settings, Engine, safe_name
from .publisher import Publisher, validate_site
from .native_assets import icon, thumbnail

ROOT = Path(__file__).resolve().parents[1]  # repository root; data folders live here
HERMES_CHOICE = 'Hermes (default)'
QSS = '''
QWidget { background:#17191f; color:#e1e4ed; font-family:"Segoe UI"; font-size:13px; }
QMainWindow, QDialog { background:#17191f; }
QToolBar { background:#1d2028; border:0; border-bottom:1px solid #343844; spacing:8px; padding:9px; }
QToolButton { background:transparent; border:1px solid transparent; border-radius:5px; padding:7px 10px; }
QToolButton:hover { background:#303544; }
QToolButton:disabled { color:#697184; }
QToolBar QLabel, QToolBar QWidget { background:transparent; }
QToolButton#publishTool { background:#b9c9ff; color:#16223e; font-weight:600; }
QToolButton#publishTool:disabled { background:#252c3b; color:#697184; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background:#111319; border:1px solid #383d4b; border-radius:5px; padding:8px; selection-background-color:#5369b8; }
QLineEdit:focus, QPlainTextEdit:focus { border:1px solid #8a9dff; }
QPushButton { background:#2a2e3a; border:1px solid #414757; border-radius:5px; padding:9px 16px; }
QPushButton:hover { background:#3b4255; border-color:#8193df; }
QPushButton:disabled { color:#6f7586; background:#22252e; }
QPushButton#primary { background:#bdc8ff; color:#161d38; border:0; font-weight:600; }
QLabel#eyebrow { color:#9caaf2; font-size:11px; font-weight:700; }
QLabel#hero { font-size:32px; font-weight:600; color:#f1f2f8; }
QLabel#muted { color:#989fb1; }
QLabel#panelTitle { font-size:11px; font-weight:700; color:#9ca4b8; padding:14px 7px; }
QWidget#navigator { background:#1c2028; }
QWidget#inspector { background:#20242d; }
QWidget#composer { background:#20242d; border:1px solid #363d4b; border-radius:12px; }
QWidget#composer QLabel, QWidget#inspector QLabel, QWidget#navigator QLabel { background:transparent; border:0; }
QWidget#inspectorForm { background:transparent; }
QPushButton#chip { background:transparent; border:1px solid #3b4352; color:#b7c1d5; padding:6px 10px; font-size:11px; }
QHeaderView::section { background:#1c2028; color:#929db3; border:0; padding:8px 4px; font-size:10px; font-weight:600; }
QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
QScrollBar::handle:vertical { background:#454e62; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QTreeWidget { background:#191c23; border:0; outline:none; padding:6px; }
QTreeWidget::item { padding:8px 4px; }
QTreeWidget::item:selected { background:#343c58; border-radius:4px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#20242d; padding:11px 22px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#c7d0ff; border-bottom:2px solid #aabaff; }
QSplitter::handle { background:#343844; width:1px; }
QScrollArea { background:#0d0f14; border:0; }
QProgressBar { border:0; background:#282e3e; max-height:4px; }
QProgressBar::chunk { background:#aabaff; }
QStatusBar { color:#a5adc0; background:#1d2028; border-top:1px solid #343844; }
QCheckBox { spacing:8px; }
QDialogButtonBox QPushButton { min-width:80px; }
'''


# Marduk191 artwork direction: storm slate, silver seams, copper active controls.
# Static material cues only; no textures behind fields or animated effects.
QSS += '''
QWidget { background:#1e2530; color:#dce2ec; }
QMainWindow, QDialog { background:#1e2530; }
QToolBar { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #363c4d,stop:1 #272e3d); border-top:1px solid #73768e; border-bottom:1px solid #60677e; }
QToolBar QLabel, QToolBar QWidget { background:transparent; color:#e0e4ed; }
QToolButton { color:#d4dce9; background:transparent; }
QToolButton:hover { background:#424a5e; border-color:#69758d; }
QToolButton:disabled { color:#7c879c; }
QToolButton#publishTool { background:#bb825e; color:#121a28; border:1px solid #e2b28f; font-weight:600; }
QToolButton#publishTool:disabled { background:#373d49; color:#8992a2; border-color:#4c5466; }
QWidget#navigator, QWidget#inspector { background:#262d38; }
QWidget#composer { background:#29313f; border:1px solid #667087; border-radius:9px; }
QWidget#inspectorForm { background:transparent; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background:#19212c; color:#e2e7f0; border:1px solid #4b566b; selection-background-color:#4c5477; selection-color:white; }
QLineEdit:focus, QPlainTextEdit:focus { border:1px solid #a1aad8; }
QPushButton { background:#333d4e; color:#e0e5ef; border:1px solid #626d83; }
QPushButton:hover { background:#424b60; border-color:#a1a9ce; }
QPushButton:disabled { background:#2b3341; color:#7e899e; }
QPushButton#primary { background:#bf8965; color:#151b26; border:1px solid #e4b799; font-weight:600; }
QPushButton#primary:disabled { background:#363f50; color:#8995a9; border-color:#505c73; }
QPushButton#chip { background:#242c39; color:#c0c9dc; border:1px solid #515d74; }
QLabel#hero { color:#edf0f7; }
QLabel#muted { color:#a3afc3; }
QLabel#panelTitle { color:#b2bdd0; }
QTreeWidget { background:#262d38; color:#ced7e6; }
QTreeWidget::item:selected { background:#40465e; color:#f2c9ac; }
QTreeWidget::item:hover { background:#343d50; }
QHeaderView::section { background:#262d38; color:#9eaac0; }
QTabBar::tab { background:#252e3c; color:#a9b5cb; }
QTabBar::tab:selected { background:#303a4a; color:#edc3a5; border-bottom:2px solid #c08b68; }
QSplitter::handle { background:#596379; }
QScrollArea { background:#161c25; }
QScrollBar::handle:vertical { background:#66738a; }
QStatusBar { color:#a8b4c9; background:#252d3b; border-top:1px solid #556077; }
QProgressBar { background:#374254; }
QProgressBar::chunk { background:#c08b68; }
'''


# The live theme is a single authored stylesheet, not accumulated legacy skins.
QSS = (Path(__file__).resolve().parent / 'native_theme.qss').read_text(encoding='utf-8')


def style_window_title(window):
    """Match native Windows chrome to the studio without custom window controls."""
    if sys.platform != 'win32':
        return
    import ctypes
    hwnd = int(window.winId())
    apply = ctypes.windll.dwmapi.DwmSetWindowAttribute
    apply.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    for attribute, value in ((20, 1), (35, 0x00191412), (36, 0x00E5E9EB)):
        color = ctypes.c_uint(value)
        apply(hwnd, attribute, ctypes.byref(color), ctypes.sizeof(color))


def app_icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor('#242d3c'))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 15, 15)
    silver = QLinearGradient(10,10,54,54)
    silver.setColorAt(0,QColor('#f0f3f6'))
    silver.setColorAt(.4,QColor('#aeb9c9'))
    silver.setColorAt(.68,QColor('#73829c'))
    silver.setColorAt(1,QColor('#d9dfe9'))
    p.setBrush(Qt.BrushStyle.NoBrush)
    pen = QPen(silver,7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(13,13,38,38,36*16,285*16)
    p.drawLine(34,33,51,33)
    p.setPen(QPen(QColor('#c28b67'),1))
    p.drawLine(18,55,47,55)
    p.end()
    return QIcon(pix)


class AtmospherePanel(QWidget):
    """One cached static artwork, outside all editable controls."""
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(320)
        self.setMaximumWidth(520)
        source = Path(path)
        if not source.is_file():
            source = ROOT/'assets/marduk191-ref-3.jpg'
        self.art = QPixmap(str(source)) if source.is_file() else QPixmap()
        self.scaled = QPixmap()
        self.mark = app_icon().pixmap(44,44)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.art.isNull():
            self.scaled = self.art.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(),QColor('#182330'))
        if not self.scaled.isNull():
            painter.drawPixmap((self.width()-self.scaled.width())//2,(self.height()-self.scaled.height())//2,self.scaled)
        shade = QLinearGradient(0,self.height()*.4,0,self.height())
        shade.setColorAt(0,QColor(14,22,33,0))
        shade.setColorAt(1,QColor(14,22,33,225))
        painter.fillRect(self.rect(),shade)
        painter.drawPixmap(28,28,self.mark)
        painter.setPen(QColor('#eef1f5'))
        painter.setFont(QFont('Segoe UI',36,QFont.Weight.DemiBold))
        painter.drawText(32,self.height()-66,'Gensite')
        painter.setPen(QColor('#d4deec'))
        painter.setFont(QFont('Segoe UI',12))
        painter.drawText(34,self.height()-36,'Make a place on the web.')
        painter.end()


class Job(QThread):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel = threading.Event()

    def run(self):
        try:
            self.succeeded.emit(self.operation(self.progress.emit, self.cancel))
        except Exception as exc:
            self.failed.emit(str(exc))


class PublishDialog(QDialog):
    def __init__(self, studio, check_status=True):
        super().__init__(studio)
        self.studio = studio
        self.readiness = {}
        self.setWindowTitle('Publish to GitHub Pages')
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        title = QLabel('A live home for your website.')
        title.setObjectName('hero')
        layout.addWidget(title)
        self.validation = validate_site(studio.site)
        self.preflight = QLabel(('Static preflight passed · '+str(len(self.validation['files']))+' files') if self.validation['valid'] else 'Preflight failed: '+'; '.join(self.validation['errors']))
        self.preflight.setWordWrap(True)
        layout.addWidget(self.preflight)
        self.status = QLabel('Checking Git and GitHub CLI…' if check_status else 'GitHub not checked')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.repository = QLineEdit(studio.state.get('form',{}).get('repository',''))
        self.repository.setPlaceholderText('owner/repository — exact target')
        form.addRow('Repository', self.repository)
        self.expected_url = QLabel('https://owner.github.io/repository/')
        self.expected_url.setObjectName('muted')
        self.expected_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow('Pages URL',self.expected_url)
        self.create = QCheckBox('Create this PUBLIC repository if it does not exist')
        form.addRow(self.create)
        self.init_empty = QCheckBox('If the repository is empty, add a README first (an empty repository cannot host Pages)')
        self.init_empty.setChecked(False)
        form.addRow(self.init_empty)
        layout.addLayout(form)
        self.confirm = QCheckBox('I confirm this website and the selected repository may become public.')
        self.confirm.setChecked(False)
        layout.addWidget(self.confirm)
        note = QLabel('Publishes to the isolated gensite-pages branch. The default branch is preserved.\nOnly allowlisted static files are uploaded; editor backups and generation logs stay local.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(500)
        self.output.setPlainText('\n'.join(self.validation['warnings']))
        layout.addWidget(self.output, 1)
        self.result_label = QLabel('')
        self.result_label.setOpenExternalLinks(True)
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        row = QHBoxLayout()
        self.check_button = QPushButton('Check GitHub')
        self.check_button.clicked.connect(self.check_status)
        row.addWidget(self.check_button)
        row.addStretch()
        self.publish_button = QPushButton('Publish website')
        self.publish_button.setObjectName('primary')
        self.publish_button.setEnabled(False)
        self.publish_button.clicked.connect(self.publish)
        row.addWidget(self.publish_button)
        close = QPushButton('Close')
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self.repository.textChanged.connect(self.update_enabled)
        self.repository.editingFinished.connect(self.preview_target)
        self.repository.editingFinished.connect(self.tidy_repository)
        self.confirm.toggled.connect(self.update_enabled)
        if check_status:
            self.check_status()

    def set_readiness(self, result):
        self.readiness = result
        self.status.setText(('Signed in as '+str(result.get('account'))) if result.get('authenticated') else ' '.join(result.get('diagnostics',[])))
        self.update_enabled()

    def target(self):
        from .publisher import normalize_repository
        return normalize_repository(self.repository.text())

    def tidy_repository(self):
        """Pasted GitHub URLs (https://github.com/owner/repo.git) become owner/repo."""
        target = self.target()
        if target != self.repository.text():
            self.repository.setText(target)

    def update_enabled(self, *args):
        import re
        target = self.target()
        valid_target = bool(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',target)) and not target.endswith('.git')
        if valid_target:
            owner,repo = target.split('/')
            self.expected_url.setText('https://'+owner+'.github.io/'+('' if repo.lower() == owner.lower()+'.github.io' else repo+'/'))
        reasons = []
        if not valid_target:
            reasons.append('Enter the repository as owner/name (a pasted GitHub URL is fine).')
        if not self.confirm.isChecked():
            reasons.append('Tick the public-confirmation box.')
        if not self.validation['valid']:
            reasons.append('The site did not pass the static preflight.')
        if not (self.readiness.get('git') and self.readiness.get('gh') and self.readiness.get('authenticated')):
            reasons.append('GitHub is not ready: press Check GitHub.')
        if self.studio.busy:
            reasons.append('Another job is running.')
        self.publish_button.setEnabled(not reasons)
        self.publish_button.setToolTip('' if not reasons else 'Not yet: ' + ' '.join(reasons))
        if not valid_target and self.repository.text().strip():
            self.result_label.setText('Not yet: ' + reasons[0])
        elif self.result_label.text().startswith('Not yet'):
            self.result_label.setText('')

    def check_status(self):
        self.studio.run_job('Checking GitHub tools',lambda log,cancel:Publisher(log,cancel).status(),self.set_readiness)

    def preview_target(self):
        import re
        target = self.target()
        if re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',target) and not target.endswith('.git'):
            self.studio.set_repository(target)

    def publish(self):
        target = self.target()
        reply = QMessageBox.question(self,'Confirm public deployment',f'Publish {self.studio.site}\n\nto {target} on GitHub Pages?\n\nThe selected content may be public.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.studio.set_repository(target)
        self.publish_button.setEnabled(False)
        create = self.create.isChecked()
        initialize_empty = self.init_empty.isChecked()
        self.studio.run_job('Publishing to '+target,lambda log,cancel:Publisher(log,cancel).publish(self.studio.site,target,create=create,confirm=True,initialize_empty=initialize_empty),self.published,progress=self.output.appendPlainText)

    def published(self, result):
        import html
        url = str(result.get('url',''))
        self.result_label.setText(html.escape(str(result.get('status','')))+' · <a href="'+html.escape(url,quote=True)+'">'+html.escape(url)+'</a>')
        self.output.appendPlainText('\n'.join(result.get('diagnostics',[])))
        self.studio.state['publish_result'] = result
        self.studio.persist_state()
        self.update_enabled()

    def closeEvent(self, event):
        if self.studio.busy:
            self.studio.statusBar().showMessage('Job is still running. Use Cancel job in the studio to stop it.')
            event.ignore()
        else:
            event.accept()


class MainWindow(QMainWindow):
    def __init__(self, state_path=None):
        super().__init__()
        self.state_path = Path(state_path or ROOT/'settings.json')
        self.state = self._load_state()
        self.settings = Settings(**{k:v for k,v in self.state.get('settings', {}).items() if k in asdict(Settings())})
        self.canvas = None
        self.site = None
        self.current_page = None
        self.worker = None
        self.busy = False
        self.job_result = None
        self.job_error = ''
        self.dirty = False
        self.selection = {}
        self.setWindowTitle('Gensite — Website studio')
        self.setWindowIcon(app_icon())
        self.resize(1440, 920)
        self.setMinimumSize(1000, 680)
        self.setStyleSheet(QSS)
        self.actions = {}
        toolbar = QToolBar('Studio')
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(2,0,14,0)
        mark = QLabel()
        mark.setPixmap(app_icon().pixmap(32,32))
        brand_layout.addWidget(mark)
        wordmark = QLabel('GENSITE')
        wordmark.setStyleSheet('font-weight:600; letter-spacing:2px; color:#dce2ef;')
        brand_layout.addWidget(wordmark)
        toolbar.addWidget(brand)
        for name, shortcut in [('New','Ctrl+N'), ('Open','Ctrl+O'), ('Save','Ctrl+S'), ('Revise','Ctrl+R')]:
            action = QAction(name, self)
            action.setIcon(icon(name))
            action.setShortcut(shortcut)
            toolbar.addAction(action)
            self.actions[name] = action
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.project_label = QLabel('NEW WEBSITE   ')
        self.project_label.setMaximumWidth(220)
        self.project_label.setMinimumWidth(0)
        self.project_label.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.project_label.setStyleSheet('color:#9daac2; font-size:11px;')
        toolbar.addWidget(self.project_label)
        for name in ['Activity', 'Settings', 'Publish']:
            action = QAction(name, self)
            action.setIcon(icon(name))
            toolbar.addAction(action)
            self.actions[name] = action
            if name == 'Publish':
                toolbar.widgetForAction(action).setObjectName('publishTool')
        self.stack = QStackedWidget()
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0,0,0,0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.stack,1)
        self.job_panel = QWidget()
        jl = QVBoxLayout(self.job_panel)
        jl.setContentsMargins(16,8,16,8)
        jr = QHBoxLayout()
        self.job_label = QLabel('Ready')
        jr.addWidget(self.job_label,1)
        self.cancel_button = QPushButton('Cancel job')
        self.cancel_button.clicked.connect(self.cancel_job)
        jr.addWidget(self.cancel_button)
        jl.addLayout(jr)
        self.progress = QProgressBar()
        self.progress.setRange(0,0)
        jl.addWidget(self.progress)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(600)
        self.activity.setMaximumHeight(110)
        jl.addWidget(self.activity)
        self.job_panel.hide()
        self.actions['Activity'].setCheckable(True)
        self.actions['Activity'].toggled.connect(self.job_panel.setVisible)
        central_layout.addWidget(self.job_panel)
        self.setCentralWidget(central)
        self.new_view = QWidget()
        self.stack.addWidget(self.new_view)
        outer = QHBoxLayout(self.new_view)
        outer.setContentsMargins(0,0,0,0)
        outer.setSpacing(0)
        self.atmosphere = AtmospherePanel(ROOT/'assets/studio-atmosphere.png')
        self.template_canvas = None
        self.template_server = None
        self.template_stack = QStackedWidget()
        self.template_stack.setMinimumWidth(320)
        self.template_stack.setMaximumWidth(520)
        self.template_stack.addWidget(self.atmosphere)
        self.template_preview_panel = QWidget()
        template_layout = QVBoxLayout(self.template_preview_panel)
        template_layout.setContentsMargins(12, 16, 12, 12)
        template_layout.setSpacing(10)
        self.template_preview_title = QLabel('Template preview')
        self.template_preview_title.setWordWrap(True)
        self.template_preview_title.setStyleSheet('font-size:16px; font-weight:600;')
        template_layout.addWidget(self.template_preview_title)
        self.template_preview_layout = template_layout
        self.template_stack.addWidget(self.template_preview_panel)
        outer.addWidget(self.template_stack,2)
        card = QWidget()
        card.setObjectName('promptWorkspace')
        card.setMaximumWidth(960)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(48,24,48,24)
        layout.setSpacing(12)
        title = QLabel('What are we building?')
        title.setObjectName('hero')
        layout.addWidget(title)
        sub = QLabel('Start with a brief. Refine every detail on the canvas.')
        sub.setObjectName('muted')
        sub.setWordWrap(True)
        layout.addWidget(sub)
        self.name = QLineEdit(self.state.get('form', {}).get('name', 'Untitled website'))
        self.name.setObjectName('projectName')
        self.name.setPlaceholderText('Website name')
        layout.addWidget(self.name)
        self.prompt = QPlainTextEdit()
        self.prompt.setObjectName('briefComposer')
        self.prompt.setPlaceholderText('A refined website for a woodland retreat. Warm editorial typography,\nforest photography, generous space. Include stays, experiences and contact…')
        self.prompt.setMinimumHeight(120)
        self.prompt.setMaximumHeight(180)
        self.prompt.setPlainText(self.state.get('form', {}).get('purpose', ''))
        layout.addWidget(self.prompt)
        examples = QHBoxLayout()
        for label, text in [('Architecture studio','A refined architecture studio website with a strong image-led homepage, selected projects, our approach, and contact. Warm natural materials, large editorial typography.'),('Independent shop','An independent ceramics studio website with a collection overview, studio story, stockists, and contact. A quiet tactile aesthetic; no fake checkout or backend.'),('Portfolio','A distinctive personal portfolio with selected work, an about section, and contact. Confident typography, generous negative space, excellent mobile navigation.')]:
            chip = QPushButton(label)
            chip.setObjectName('chip')
            chip.clicked.connect(lambda checked=False,text=text:self.prompt.setPlainText(text))
            examples.addWidget(chip)
        examples.addStretch()
        layout.addLayout(examples)
        template_row = QHBoxLayout()
        template_row.addWidget(QLabel('Page template'))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem('Custom · Start from your brief','')
        self.preset_preview_button = QPushButton('Preview template')
        self.preset_preview_button.setEnabled(False)
        template_row.addWidget(self.preset_combo,1)
        template_row.addWidget(self.preset_preview_button)
        layout.addLayout(template_row)
        self.preset_detail = QLabel('Page templates guide the generated website, not the studio interface.')
        self.preset_detail.setObjectName('muted')
        self.preset_detail.setWordWrap(True)
        layout.addWidget(self.preset_detail)
        self.preset_combo.currentIndexChanged.connect(self.preset_changed)
        self.preset_preview_button.clicked.connect(self.preview_preset)
        try:
            from .preset_catalog import load_presets
            for preset in load_presets():
                self.preset_combo.addItem(preset['name'],preset['id'])
            selected_preset = self.preset_combo.findData(self.state.get('form',{}).get('preset',''))
            if selected_preset >= 0:
                self.preset_combo.setCurrentIndex(selected_preset)
        except (ImportError,OSError,ValueError,KeyError,TypeError):
            pass
        self.options_toggle = QPushButton('▸  Generation options — style, number of images, art direction')
        self.options_toggle.setObjectName('optionsToggle')
        self.options_toggle.setCheckable(True)
        layout.addWidget(self.options_toggle)
        self.options_panel = QWidget()
        options_layout = QVBoxLayout(self.options_panel)
        options_layout.setContentsMargins(0, 2, 0, 4)
        options_layout.setSpacing(10)
        self.options_panel.hide()
        self.options_toggle.toggled.connect(self.options_panel.setVisible)
        self.options_toggle.toggled.connect(lambda on: self.options_toggle.setText(('▾' if on else '▸')+'  Generation options — style, number of images, art direction'))
        layout.addWidget(self.options_panel)
        row = QHBoxLayout()
        self.style = QComboBox()
        self.style.setEditable(True)
        self.style.addItems(['Editorial & refined', 'Minimal & architectural', 'Warm & organic', 'Bold & expressive', 'Clean & professional'])
        self.style.setCurrentText(self.state.get('form', {}).get('style', 'Editorial & refined'))
        row.addWidget(QLabel('Style'))
        row.addWidget(self.style, 1)
        row.addWidget(QLabel('Images'))
        self.image_count = QSpinBox()
        self.image_count.setRange(0, 12)
        self.image_count.setValue(int(self.state.get('form', {}).get('image_count', 1)))
        row.addWidget(self.image_count)
        options_layout.addLayout(row)
        self.art = QLineEdit(self.state.get('form', {}).get('art_direction', ''))
        self.art.setPlaceholderText('Image art direction — lighting, composition, subject, mood')
        options_layout.addWidget(self.art)
        llm_row = QHBoxLayout()
        llm_row.addWidget(QLabel('Text model'))
        self.llm_combo = QComboBox()
        self.llm_combo.setEditable(True)
        self.llm_combo.setToolTip('Who writes the website code. Hermes (default), or the loopback URL of an OpenAI-compatible server such as llama.cpp. You can type any http://127.0.0.1:PORT/v1 address.')
        self.llm_combo.addItems([HERMES_CHOICE, 'http://127.0.0.1:8080/v1'])
        saved_endpoint = self.settings.llm_endpoint.strip()
        if saved_endpoint and self.llm_combo.findText(saved_endpoint) < 0:
            self.llm_combo.addItem(saved_endpoint)
        self.llm_combo.setCurrentText(saved_endpoint or HERMES_CHOICE)
        llm_row.addWidget(self.llm_combo, 1)
        options_layout.addLayout(llm_row)
        buttons = QHBoxLayout()
        self.open_button = QPushButton('Open existing website')
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        self.generate_button = QPushButton('Generate website')
        self.generate_button.setIcon(icon('Arrow','#151b26'))
        self.generate_button.setObjectName('primary')
        buttons.addWidget(self.generate_button)
        layout.addLayout(buttons)
        note = QLabel('Built for GitHub Pages · Nothing published until you confirm')
        note.setObjectName('muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        # Scroll instead of compressing: opening options or the activity panel
        # must never squash fields into each other on small/scaled displays.
        card_scroll = QScrollArea()
        card_scroll.setObjectName('promptScroll')
        card_scroll.setFrameShape(QFrame.Shape.NoFrame)
        card_scroll.setWidgetResizable(True)
        card_scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        card_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        card_scroll.setStyleSheet('QScrollArea#promptScroll, QScrollArea#promptScroll > QWidget > QWidget { background:transparent; }')
        card_scroll.setWidget(card)
        self.card_scroll = card_scroll
        outer.addWidget(card_scroll, 3)
        self.statusBar().showMessage('Ready — describe a website or open a project')
        self.actions['New'].triggered.connect(self.new_website)
        self.actions['Open'].triggered.connect(self.open_dialog)
        self.open_button.clicked.connect(self.open_dialog)
        self.actions['Save'].setEnabled(False)
        self.actions['Revise'].setEnabled(False)
        self.actions['Publish'].setEnabled(False)
        self.generate_button.clicked.connect(self.start_generation)
        self.actions['Revise'].triggered.connect(self.revision_dialog)
        self.actions['Settings'].triggered.connect(self.settings_dialog)
        self.actions['Publish'].triggered.connect(self.publish_dialog)
        self.resume_button = QPushButton('Resume last project')
        self.resume_button.setVisible(bool(self.state.get('last_site')))
        self.resume_button.clicked.connect(self.resume_project)
        buttons.insertWidget(1,self.resume_button)
        self.stack.currentChanged.connect(self._sync_workspace_actions)
        self._sync_workspace_actions()
        self.root_ready_seconds = time.perf_counter() - STARTED

    def showEvent(self, event):
        super().showEvent(event)
        style_window_title(self)

    def _sync_workspace_actions(self, *_):
        editing = self.stack.currentWidget() is not self.new_view
        for label in ('Save', 'Revise', 'Publish'):
            self.actions[label].setVisible(editing)

    def _load_state(self):
        try:
            result = json.loads(self.state_path.read_text(encoding='utf-8'))
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError):
            return {}

    def new_website(self):
        self.stack.setCurrentWidget(self.new_view)
        self.prompt.setFocus()

    def resume_project(self):
        if self.site:
            self.stack.setCurrentWidget(self.editor)
        elif self.state.get('last_site'):
            self.open_site(self.state['last_site'])

    def preset_changed(self, index):
        identity = self.preset_combo.currentData()
        self.preset_preview_button.setEnabled(bool(identity))
        if not identity:
            self.preset_detail.setText('Page templates guide the generated website, not the studio interface.')
            self.template_stack.setCurrentWidget(self.atmosphere)
            if self.template_canvas:
                self.template_canvas.stop()
            if self.template_server:
                self.template_server.close()
                self.template_server = None
            return
        try:
            from .preset_catalog import get_preset
            preset = get_preset(identity)
            self.preset_detail.setText(str(preset.get('summary','')))
            self.show_inline_template(preset)
        except (ImportError,OSError,ValueError,KeyError) as exc:
            self.preset_detail.setText('Template unavailable: '+str(exc))

    def show_inline_template(self, preset):
        """Selection shows the actual page in-place, without another click."""
        from .native_preview import SiteServer
        from .native_canvas import SiteCanvas
        path = (ROOT / preset['preview']).resolve()
        self.template_source()
        if self.template_server:
            self.template_server.close()
        if self.template_canvas is None:
            self.template_canvas = SiteCanvas(self.template_preview_panel)
            self.template_canvas.setMinimumHeight(300)
            self.template_canvas.setZoomFactor(0.45)
            self.template_preview_layout.addWidget(self.template_canvas, 1)
        self.template_preview_title.setText(preset['name'] + ' · live preview')
        self.template_server = SiteServer(path.parent, 'template-preview')
        self.template_stack.setCurrentWidget(self.template_preview_panel)
        self.template_canvas.open(self.template_server.url + path.name,
                                  self.template_server.origin, edit=False)

    def template_source(self):
        identity = self.preset_combo.currentData()
        if not identity:
            return ''
        from .preset_catalog import get_preset
        path = (ROOT/get_preset(identity)['preview']).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or path.stat().st_size > 512*1024:
            raise ValueError('Template source must be a local HTML file smaller than 512 KiB.')
        return path.read_text(encoding='utf-8-sig')

    def preview_preset(self):
        try:
            from .preset_catalog import get_preset
            from .native_preview import SiteServer
            from .native_canvas import SiteCanvas
            preset = get_preset(self.preset_combo.currentData())
            path = (ROOT/preset['preview']).resolve()
            self.template_source()  # Validate the exact catalog path before serving it.
            dialog = QDialog(self)
            dialog.setWindowTitle('Page template · '+preset['name'])
            dialog.resize(1050,760)
            layout = QVBoxLayout(dialog)
            info = QLabel(preset['summary']+'\nThis is a template preview, not your generated project. Your content and images are created by Generate.')
            info.setWordWrap(True)
            layout.addWidget(info)
            server = SiteServer(path.parent,'template-preview')
            canvas = SiteCanvas(dialog)
            layout.addWidget(canvas,1)
            canvas.open(server.url+path.name,server.origin,edit=False)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            dialog.exec()
            canvas.dispose()
            server.close()
        except (ImportError,OSError,ValueError,KeyError) as exc:
            self.error(str(exc))

    def open_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, 'Open generated website or project', str(ROOT/'projects'))
        if folder:
            self.open_site(folder)

    def open_site(self, folder):
        if not self.confirm_discard():
            return
        from .native_preview import SiteServer
        path = Path(folder).resolve()
        if path.is_file():
            path = path.parent
        if not (path/'index.html').is_file() and (path/'site'/'index.html').is_file():
            path /= 'site'
        if not (path/'index.html').is_file():
            raise ValueError('Choose a project or site folder containing index.html.')
        if not hasattr(self, 'editor'):
            self.build_editor()
        if getattr(self, 'server', None):
            self.server.close()
        self.site = path
        project_name = path.parent.name
        try:
            manifest = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
            project_name = str(manifest.get('name') or project_name)
            self.name.setText(project_name)
            self.image_count.setValue(len(manifest.get('images',[])))
        except (OSError,ValueError,TypeError,AttributeError):
            pass
        repository = self.state.get('form', {}).get('repository', '').split('/')[-1] or 'preview-repo'
        self.server = SiteServer(path, repository)
        self.pages.clear()
        self.files = sorted(p.name for p in path.glob('*.html') if not p.is_symlink())
        for name in self.files:
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            self.pages.addTopLevelItem(item)
        self.assets.clear()
        for file in sorted(path.rglob('*')):
            if file.is_file() and file.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.svg','.gif','.avif'} and file.resolve().is_relative_to(path):
                self.assets.addItem(thumbnail(file),file.relative_to(path).as_posix())
        self.stack.setCurrentWidget(self.editor)
        self.project_label.setText(project_name[:32]+'   ')
        self.resume_button.setText('Return to project')
        self.resume_button.setVisible(True)
        self.setWindowTitle(project_name+' — Gensite')
        for key in ['Save','Revise','Publish']:
            self.actions[key].setEnabled(True)
        self.load_page('index.html')
        self.persist_state()

    def build_editor(self):
        self.editor = QWidget()
        self.stack.addWidget(self.editor)
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        site_bar = QWidget()
        site_bar.setObjectName('siteBar')
        bar_layout = QHBoxLayout(site_bar)
        bar_layout.setContentsMargins(14, 10, 14, 10)
        bar_layout.setSpacing(10)
        bar_label = QLabel('WHOLE SITE')
        bar_label.setObjectName('panelTitle')
        bar_layout.addWidget(bar_label)
        self.site_prompt = QLineEdit()
        self.site_prompt.setObjectName('sitePrompt')
        self.site_prompt.setPlaceholderText('Describe a change to the entire site — e.g. “make it darker and more dramatic”, “add a pricing page”, “warmer type”')
        self.site_prompt.setToolTip('Rewrites the whole site from your current edited pages and saves the result as a new project. The old one is kept.')
        bar_layout.addWidget(self.site_prompt, 1)
        self.site_prompt_button = QPushButton('Revise site')
        self.site_prompt_button.setObjectName('primary')
        bar_layout.addWidget(self.site_prompt_button)
        self.site_prompt.returnPressed.connect(self.revise_whole_site)
        self.site_prompt_button.clicked.connect(self.revise_whole_site)
        layout.addWidget(site_bar)
        split = QSplitter()
        layout.addWidget(split, 1)
        left = QWidget()
        left.setObjectName('navigator')
        left.setMinimumWidth(180)
        left.setMaximumWidth(330)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8,0,8,8)
        label = QLabel('WORKSPACE')
        label.setObjectName('panelTitle')
        ll.addWidget(label)
        self.pages = QTreeWidget()
        self.pages.setHeaderLabel('PAGES')
        ll.addWidget(self.pages, 1)
        self.outline = QTreeWidget()
        self.outline.setHeaderLabel('DOCUMENT OUTLINE')
        ll.addWidget(self.outline, 2)
        label = QLabel('ASSETS')
        label.setObjectName('panelTitle')
        ll.addWidget(label)
        self.assets = QComboBox()
        ll.addWidget(self.assets)
        split.addWidget(left)
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0,0,0,0)
        cl.setSpacing(0)
        tools = QHBoxLayout()
        tools.setContentsMargins(12,9,12,9)
        self.mode = QComboBox()
        self.mode.addItems(['Edit', 'Preview'])
        tools.addWidget(self.mode)
        self.location = QLabel('index.html')
        self.location.setObjectName('muted')
        tools.addWidget(self.location, 1)
        self.viewport = QComboBox()
        self.viewport.addItems(['Full width', 'Tablet · 768', 'Mobile · 390'])
        tools.addWidget(self.viewport)
        self.reload_button = QPushButton('Reload')
        tools.addWidget(self.reload_button)
        cl.addLayout(tools)
        self.tabs = QTabWidget()
        cl.addWidget(self.tabs, 1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.canvas_host = QWidget()
        self.canvas_host.setStyleSheet('background:#161c25;')
        self.canvas_layout = QVBoxLayout(self.canvas_host)
        self.canvas_layout.setContentsMargins(20,20,20,20)
        from .native_canvas import SiteCanvas
        self.canvas = SiteCanvas()
        self.canvas_layout.addWidget(self.canvas, 1, Qt.AlignmentFlag.AlignHCenter)
        self.scroll.setWidget(self.canvas_host)
        self.tabs.addTab(self.scroll, 'Canvas')
        self.code = QPlainTextEdit()
        self.code.setFont(QFont('Cascadia Code', 11))
        self.code.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.tabs.addTab(self.code, 'Code')
        split.addWidget(center)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setMinimumWidth(260)
        inspector_scroll.setMaximumWidth(360)
        inspector = QWidget()
        inspector.setObjectName('inspector')
        il = QVBoxLayout(inspector)
        il.setContentsMargins(16,0,16,16)
        title = QLabel('ELEMENT INSPECTOR')
        title.setObjectName('panelTitle')
        il.addWidget(title)
        self.element_label = QLabel('Select an element on the canvas')
        self.element_label.setTextFormat(Qt.TextFormat.PlainText)
        self.element_label.setWordWrap(True)
        il.addWidget(self.element_label)
        self.inspector_form = QWidget()
        self.inspector_form.setObjectName('inspectorForm')
        form = QFormLayout(self.inspector_form)
        form.setContentsMargins(0,16,0,0)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        self.element_text = QPlainTextEdit()
        self.element_text.setMaximumHeight(100)
        form.addRow('Text', self.element_text)
        warning = QLabel('Editing text replaces nested inline content.')
        warning.setObjectName('muted')
        warning.setWordWrap(True)
        form.addRow(warning)
        color_row = QWidget()
        cr = QHBoxLayout(color_row)
        cr.setContentsMargins(0,0,0,0)
        self.color = QLineEdit()
        cr.addWidget(self.color)
        color_button = QPushButton('…')
        color_button.setMaximumWidth(40)
        color_button.clicked.connect(self.choose_color)
        cr.addWidget(color_button)
        form.addRow('Color', color_row)
        self.background = QLineEdit()
        form.addRow('Background', self.background)
        self.font = QLineEdit()
        form.addRow('Font', self.font)
        self.font_size = QSpinBox()
        self.font_size.setRange(1,300)
        self.font_size.setSuffix(' px')
        form.addRow('Size', self.font_size)
        self.padding = QSpinBox()
        self.padding.setRange(0,500)
        self.padding.setSuffix(' px')
        form.addRow('Padding', self.padding)
        self.padding.setToolTip('Padding in pixels, applied to all four sides')
        self.image = QLineEdit()
        form.addRow('Image', self.image)
        self.image.setToolTip('Site-relative image path')
        self.image_width = QSpinBox()
        self.image_width.setRange(0, 20000)
        self.image_width.setSuffix(' px')
        self.image_width.setSpecialValueText('Auto')
        self.image_width.setToolTip('Image width in pixels (height follows). You can also drag the blue square at the image corner on the canvas. Auto = the site\'s own sizing.')
        form.addRow('Width', self.image_width)
        image_button = QPushButton('Replace image…')
        self.image_button = image_button
        image_button.clicked.connect(self.replace_image)
        form.addRow(image_button)
        self.generate_image_button = QPushButton('Generate new image…')
        self.generate_image_button.setToolTip('Render a new image from a prompt with local ComfyUI and use it here. The old image is kept.')
        self.generate_image_button.clicked.connect(self.generate_new_image)
        form.addRow(self.generate_image_button)
        self.apply_button = QPushButton('Apply changes')
        self.apply_button.setObjectName('primary')
        self.apply_button.clicked.connect(self.apply_inspector)
        form.addRow(self.apply_button)
        il.addWidget(self.inspector_form)
        self.inspector_form.setEnabled(False)
        il.addStretch()
        hint = QLabel('Edit selects elements. Preview runs the saved website without editor scripts, under the repository URL path.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        il.addWidget(hint)
        inspector_scroll.setWidget(inspector)
        split.addWidget(inspector_scroll)
        split.setSizes([210, 930, 290])
        split.setStretchFactor(1, 1)
        self.pages.itemClicked.connect(lambda item, column: self.switch_page(item.data(0, Qt.ItemDataRole.UserRole)))
        self.outline.itemClicked.connect(lambda item, column: self.canvas.select(item.data(0, Qt.ItemDataRole.UserRole)))
        self.canvas.selected.connect(self.selected_element)
        self.canvas.loaded.connect(self.canvas_loaded)
        self.viewport.currentIndexChanged.connect(lambda i:self.set_viewport([0,768,390][i]))
        self.mode.currentTextChanged.connect(self.change_mode)
        self.reload_button.clicked.connect(self.reload_canvas)
        self.code.textChanged.connect(self.code_changed)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.actions['Save'].triggered.connect(self.save_page)

    def load_page(self, filename):
        if filename not in self.files:
            return
        self.current_page = filename
        self.selection = {}
        self.inspector_form.setEnabled(False)
        self.outline.clear()
        self.set_code((self.site/filename).read_text(encoding='utf-8-sig'))
        self.set_dirty(False)
        self.location.setText(filename)
        self.canvas.open(self.server.url+filename, self.server.origin, self.mode.currentText() == 'Edit')
        self.set_viewport([0,768,390][self.viewport.currentIndex()])

    def switch_page(self, filename):
        if self.confirm_discard():
            self.load_page(filename)

    def canvas_loaded(self, ok):
        if not ok:
            self.statusBar().showMessage('Page failed to load — check relative paths in Code')
            return
        url = self.canvas.url().toString()
        self.location.setText(QUrl(url).path())
        if url.startswith(self.server.url):
            page = QUrl(url).path().split('/')[-1] or 'index.html'
            if page in self.files and page != self.current_page:
                self.current_page = page
                self.set_code((self.site/page).read_text(encoding='utf-8-sig'))
        self.statusBar().showMessage(('Editing · ' if self.mode.currentText() == 'Edit' else 'Preview · ')+self.canvas.url().toString())
        if self.mode.currentText() == 'Edit':
            self.canvas.outline(self.fill_outline)

    def fill_outline(self, entries):
        self.outline.clear()
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    item = QTreeWidgetItem([' '.join(str(entry.get('label','')).split())])
                    item.setData(0, Qt.ItemDataRole.UserRole, entry.get('selector',''))
                    self.outline.addTopLevelItem(item)

    def selected_element(self, selection):
        if self.mode.currentText() != 'Edit':
            return
        self.selection = selection
        self.inspector_form.setEnabled(True)
        self.element_label.setText('<'+selection.get('tag','element')+'>')
        self.element_text.setPlainText(selection.get('text',''))
        self.color.setText(selection.get('color',''))
        self.background.setText(selection.get('backgroundColor',''))
        self.font.setText(selection.get('fontFamily',''))
        for widget, key in [(self.font_size,'fontSize'), (self.padding,'padding')]:
            try:
                widget.setValue(round(float(selection.get(key,'0').replace('px',''))))
            except ValueError:
                widget.setValue(0)
        self.image.setText(selection.get('image',''))
        self.image.setEnabled(selection.get('tag') == 'img')
        self.image_width.setEnabled(selection.get('tag') == 'img')
        try:
            self.image_width.setValue(max(0, int(selection.get('width', 0))) if selection.get('tag') == 'img' else 0)
        except (TypeError, ValueError):
            self.image_width.setValue(0)
        if selection.get('resized'):
            self.set_dirty(True)
        self.element_text.setEnabled(selection.get('tag') != 'img')
        form = self.inspector_form.layout()
        form.setRowVisible(self.image,selection.get('tag') == 'img')
        form.setRowVisible(self.image_width,selection.get('tag') == 'img')
        form.setRowVisible(self.image_button,selection.get('tag') == 'img')
        form.setRowVisible(self.generate_image_button,selection.get('tag') == 'img')

    def choose_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.color.setText(color.name())

    def apply_inspector(self):
        if not self.selection or not self.canvas.edit:
            return
        values = {}
        old = self.selection
        if self.element_text.toPlainText() != old.get('text') and old.get('tag') != 'img':
            values['text'] = self.element_text.toPlainText()
        for key, value in [('color', self.color.text()), ('backgroundColor', self.background.text()), ('fontFamily',self.font.text()), ('fontSize',str(self.font_size.value())+'px'), ('padding',str(self.padding.value())+'px')]:
            if value != old.get(key):
                values[key] = value
        if old.get('tag') == 'img' and self.image.text() != old.get('image'):
            name = self.image.text().strip()
            target = (self.site/name).resolve()
            if not target.is_relative_to(self.site) or not target.is_file() or name.startswith('/'):
                self.error('Choose an existing image inside this site, using a relative path.')
                return
            values['image'] = name
        if old.get('tag') == 'img' and self.image_width.value() != int(old.get('width', 0) or 0):
            values['width'] = self.image_width.value()
        self.canvas.apply(values, lambda ok:self.set_dirty(True) if ok else self.error('Select an element first.'))

    def default_image_prompt(self, src):
        """Prompt that made this image (manifest), else the art direction."""
        try:
            data = json.loads((self.site/'manifest.json').read_text(encoding='utf-8-sig'))
            for entry in reversed(data.get('images', [])):
                if isinstance(entry, dict) and entry.get('filename') == src and entry.get('prompt'):
                    return str(entry['prompt'])
        except (OSError, ValueError, AttributeError):
            pass
        return self.art.text().strip() or self.name.text().strip()

    def generate_new_image(self):
        if self.selection.get('tag') != 'img' or not self.site or self.busy:
            self.error('Select an image on the canvas first.')
            return
        src = (self.selection.get('image') or '').strip()
        prompt, ok = QInputDialog.getMultiLineText(self, 'Generate new image', 'Image prompt (edit to change what is drawn). The current image is kept in assets/.', self.default_image_prompt(src))
        if not ok or not prompt.strip():
            return
        site = self.site
        def done(path):
            self.assets.addItem(path)
            self.image.setText(path)
            self.apply_inspector()
            self.statusBar().showMessage('New image applied · Save to keep it')
        self.run_job('Generating image',lambda log,cancel:Engine(self.settings,log,cancel).generate_image(site,prompt),done)

    def replace_image(self):
        if self.selection.get('tag') != 'img':
            self.error('Select an image on the canvas first.')
            return
        filename, _ = QFileDialog.getOpenFileName(self, 'Replace image', '', 'Images (*.png *.jpg *.jpeg *.webp *.gif *.avif *.svg)')
        if filename:
            import shutil
            import uuid
            source = Path(filename)
            assets = self.site/'assets'
            assets.mkdir(exist_ok=True)
            name = 'assets/'+safe_name(source.stem, 'image')[:40]+'_'+uuid.uuid4().hex[:8]+source.suffix.lower()
            shutil.copyfile(source, self.site/name)
            self.assets.addItem(name)
            self.image.setText(name)
            self.apply_inspector()

    def set_viewport(self, width):
        if not self.canvas:
            return
        self.canvas_layout.setAlignment(self.canvas, Qt.AlignmentFlag.AlignHCenter if width else Qt.AlignmentFlag(0))
        if width:
            self.canvas.setFixedWidth(width)
        else:
            self.canvas.setMinimumWidth(1)
            self.canvas.setMaximumWidth(16777215)
            self.canvas.resize(max(1,self.scroll.viewport().width()-40), self.canvas.height())
        self.canvas.setMinimumHeight(max(400, self.scroll.viewport().height()-40))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.canvas:
            self.set_viewport([0,768,390][self.viewport.currentIndex()])

    def set_code(self, html):
        self._setting_code = True
        self.code.setPlainText(html)
        self._setting_code = False
        self.code_dirty = False

    def code_changed(self):
        if not getattr(self,'_setting_code',False):
            self.code_dirty = True
            self.set_dirty(True)

    def set_dirty(self, value):
        self.dirty = bool(value)
        self.setWindowModified(self.dirty)
        self.actions['Save'].setText('Save •' if value else 'Save')

    def tab_changed(self, index):
        if index == 1 and self.canvas.edit and self.canvas.ready and not self.code_dirty:
            self.canvas.snapshot(lambda html:self.set_code(html) if isinstance(html,str) and not self.code_dirty else None)
        elif index == 0 and self.code_dirty:
            self.save_page(reload=True)

    def _write_page(self, html, reload=False):
        if not isinstance(html, str) or '<html' not in html.lower():
            self.error('No complete HTML document to save.')
            return
        import hashlib
        import uuid
        path = self.site/self.current_page
        if path.is_symlink() or not path.resolve().is_relative_to(self.site):
            self.error('Refusing to overwrite an unsafe page path.')
            return
        backup = ROOT/'.native-backups'/hashlib.sha256(str(self.site).encode()).hexdigest()[:16]
        backup.mkdir(parents=True, exist_ok=True)
        (backup/(self.current_page+'.'+uuid.uuid4().hex+'.bak')).write_bytes(path.read_bytes())
        temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            temporary.write_text(html, encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        self.set_code(html)
        self.set_dirty(False)
        self.statusBar().showMessage('Saved '+str(path)+' · Backup outside published output')
        if reload:
            self.canvas.open(self.server.url+self.current_page,self.server.origin,self.mode.currentText() == 'Edit')

    def save_page(self, checked=False, reload=False, callback=None):
        if not self.site:
            return
        def done(html):
            try:
                self._write_page(html,reload)
                if callback and not self.dirty:
                    callback()
            except (OSError,ValueError) as exc:
                self.error(str(exc))
        if self.tabs.currentIndex() == 1 or self.code_dirty:
            done(self.code.toPlainText())
        elif self.canvas.edit:
            self.canvas.snapshot(done)
        elif callback:
            callback()

    def confirm_discard(self):
        if not self.dirty:
            return True
        return QMessageBox.question(self,'Unsaved changes','Discard unsaved changes?',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def change_mode(self, mode):
        def change():
            self.inspector_form.setEnabled(False)
            self.selection = {}
            self.outline.clear()
            self.tabs.setCurrentIndex(0)
            self.canvas.open(self.server.url+self.current_page,self.server.origin,mode == 'Edit')
        if self.dirty:
            self.save_page(callback=change)
        else:
            change()

    def reload_canvas(self):
        if self.confirm_discard():
            self.load_page(self.current_page)

    def llm_endpoint_value(self):
        text = self.llm_combo.currentText().strip()
        return '' if not text or text == HERMES_CHOICE else text

    def persist_state(self):
        self.settings = replace(self.settings, llm_endpoint=self.llm_endpoint_value())
        self.state.update(settings=asdict(self.settings), last_site=str(self.site or ''))
        form = self.state.setdefault('form',{})
        form.update(name=self.name.text(),purpose=self.prompt.toPlainText(),style=self.style.currentText(),image_count=self.image_count.value(),art_direction=self.art.text(),preset=self.preset_combo.currentData() or '')
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temporary = self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.state,indent=2),encoding='utf-8')
        temporary.replace(self.state_path)

    def run_job(self, title, operation, success, progress=None):
        if self.busy:
            self.statusBar().showMessage('A job is already running. Cancel it or wait for completion.')
            return False
        self.busy = True
        self.job_result = None
        self.job_error = ''
        self.job_label.setText(title)
        self.actions['Activity'].setChecked(True)
        self.progress.show()
        self.cancel_button.setEnabled(True)
        self.activity.appendPlainText(title)
        self.generate_button.setEnabled(False)
        for action in self.actions.values():
            action.setEnabled(False)
        if hasattr(self,'editor'):
            self.editor.setEnabled(False)
        job = Job(operation,self)
        self.worker = job
        job.progress.connect(self.activity.appendPlainText)
        job.progress.connect(self.statusBar().showMessage)
        if progress:
            job.progress.connect(progress)
        job.succeeded.connect(lambda result:setattr(self,'job_result',result))
        job.failed.connect(lambda error:setattr(self,'job_error',error))
        def finish():
            self.busy = False
            self.progress.hide()
            self.cancel_button.setEnabled(False)
            self.generate_button.setEnabled(True)
            for key, action in self.actions.items():
                action.setEnabled(key not in {'Save','Revise','Publish'} or bool(self.site))
            if hasattr(self,'editor'):
                self.editor.setEnabled(True)
            if self.job_error:
                self.job_label.setText('Job stopped · '+self.job_error)
                self.activity.appendPlainText(self.job_error)
                self.statusBar().showMessage(self.job_error)
            else:
                self.job_label.setText('Complete')
                try:
                    success(self.job_result)
                except (OSError,ValueError) as exc:
                    self.error(str(exc))
            job.deleteLater()
            self.worker = None
        job.finished.connect(finish)
        job.start()
        return True

    def cancel_job(self):
        if self.worker and self.busy:
            self.worker.cancel.set()
            if getattr(self, '_reference_broker', None) is not None:
                self._reference_broker.cancel_pending()
            self.cancel_button.setEnabled(False)
            self.job_label.setText('Cancelling current job safely…')

    def brief(self):
        brief = ('Website name: '+self.name.text()+'\nPurpose and required pages/sections: '+self.prompt.toPlainText()+'\nVisual style: '+self.style.currentText()+'\nImage art direction: '+self.art.text()+'\nUse semantic accessible HTML, responsive layouts, and relative local links. This site will be published under a GitHub Pages repository subpath.')
        identity = self.preset_combo.currentData()
        if identity:
            from .preset_catalog import preset_brief
            brief += '\n'+preset_brief(identity)+'\nUse the following original page template as design context, not final business content. The user brief and explicit requests take priority. Replace demo imagery with the requested generated local images.\n<template-source>\n'+self.template_source()+'\n</template-source>'
        return brief

    def prepare_reference_browser(self):
        """Create only the signal broker here, on the UI thread; Chromium stays lazy."""
        if getattr(self, '_reference_broker', None) is None:
            from .reference_browser import ReferenceBrowserBroker
            self._reference_broker = ReferenceBrowserBroker(self)

    def generation_engine(self, log, cancel):
        engine = Engine(self.settings, log, cancel)
        engine.reference_reader = self._reference_broker.read
        return engine

    def start_generation(self):
        if not self.prompt.toPlainText().strip() or not self.name.text().strip():
            self.error('Enter a website name and a description first.')
            return
        if not self.confirm_discard():
            return
        self.set_dirty(False)
        self.persist_state()
        brief, name, count = self.brief(), self.name.text(), self.image_count.value()
        self.prepare_reference_browser()
        self.run_job('Generating '+name,lambda log,cancel:self.generation_engine(log,cancel).generate(brief,name,count),self.generation_complete)

    def generation_complete(self, site):
        self.actions['Activity'].setChecked(False)
        self.open_site(site)
        self.statusBar().showMessage('Website generated · Select any element to refine it')

    def revision_dialog(self):
        if not self.site:
            return
        revision, ok = QInputDialog.getMultiLineText(self,'Revise website','Describe the change. Your current edited pages and selected element are included.','')
        if ok and revision.strip():
            self.start_revision(revision)

    def revise_whole_site(self):
        text = self.site_prompt.text().strip()
        if not text:
            self.statusBar().showMessage('Describe the change you want to make to the whole site.')
            return
        if not self.site or self.busy:
            return
        self.site_prompt.clear()
        self.start_revision(text, whole_site=True)

    def start_revision(self, revision, whole_site=False):
        if not self.site or self.busy:
            return
        selected = '' if whole_site else json.dumps(self.selection, ensure_ascii=False)
        def revise():
            source = '\n'.join('PAGE '+file+'\n'+(self.site/file).read_text(encoding='utf-8-sig') for file in self.files)
            scope = 'Apply this change consistently across the ENTIRE site (every page, shared styles, navigation and footer).' if whole_site else 'Selected element: '+selected
            brief = self.brief()+'\nRevision instructions: '+revision+'\n'+scope+'\nRevise this CURRENT edited site. Preserve unaffected content and design. Return a complete new project, never alter the old one.\n<previous-site>\n'+source+'\n</previous-site>'
            count = self.image_count.value()
            name = self.name.text()
            self.persist_state()
            self.prepare_reference_browser()
            self.run_job('Revising '+name,lambda log,cancel:self.generation_engine(log,cancel).generate(brief,name,count),self.generation_complete)
        if self.dirty:
            self.save_page(callback=revise)
        else:
            revise()

    def settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Workspace settings')
        dialog.resize(680,320)
        layout = QVBoxLayout(dialog)
        note = QLabel('Reuse existing local services. These settings never edit Hermes config or workflow node values; model/provider are passed per run.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        inputs = {}
        for key, label in [('comfy_url','ComfyUI loopback URL'),('workflow','ComfyUI API workflow'),('hermes_command','Hermes executable'),('hermes_model','Hermes model (optional)'),('hermes_provider','Hermes provider (optional)')]:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0,0,0,0)
            field = QLineEdit(getattr(self.settings,key))
            inputs[key] = field
            rl.addWidget(field,1)
            if key in ('workflow','hermes_command'):
                choose = QPushButton('Browse…')
                def browse(checked=False, field=field, key=key):
                    filename,_ = QFileDialog.getOpenFileName(dialog,'Choose '+key,'','JSON (*.json)' if key == 'workflow' else 'Executable (*.exe)')
                    if filename:
                        field.setText(filename)
                choose.clicked.connect(browse)
                rl.addWidget(choose)
            form.addRow(label,row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        check = QPushButton('Check connections (read-only)')
        layout.addWidget(check)
        def save_values():
            settings = replace(self.settings, **{key:field.text().strip() for key,field in inputs.items()})
            # Engine validates loopback URLs without invoking any service.
            Engine(settings,lambda message:None,threading.Event())
            self.settings = settings
            self.persist_state()
        def check_values():
            try:
                save_values()
                dialog.accept()
                self.run_job('Checking connections',lambda log,cancel:Engine(self.settings,log,cancel).check(),lambda result:self.activity.appendPlainText(json.dumps(result,indent=2)))
            except (ValueError,OSError) as exc:
                self.error(str(exc))
        check.clicked.connect(check_values)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                save_values()
            except (ValueError,OSError) as exc:
                self.error(str(exc))

    def set_repository(self, repository):
        self.state.setdefault('form',{})['repository'] = repository
        self.persist_state()
        slug = repository.split('/')[-1]
        if self.site and slug != self.server.repository:
            from .native_preview import SiteServer
            self.server.close()
            self.server = SiteServer(self.site,slug)
            self.canvas.open(self.server.url+self.current_page,self.server.origin,self.mode.currentText() == 'Edit')

    def publish_dialog(self):
        if not self.site or self.busy:
            return
        def show():
            self.publish_window = PublishDialog(self)
            self.publish_window.show()
        if self.dirty:
            self.save_page(callback=show)
        else:
            show()

    def error(self, message):
        QMessageBox.warning(self,'Gensite',message)

    def closeEvent(self, event):
        if not self.confirm_discard():
            event.ignore()
            return
        if self.worker and self.worker.isRunning():
            self.error('Cancel the current job and wait for it to finish before closing.')
            event.ignore()
            return
        self.persist_state()
        if self.template_canvas:
            self.template_canvas.dispose()
            self.template_canvas = None
        if self.template_server:
            self.template_server.close()
            self.template_server = None
        if self.canvas:
            self.canvas.dispose()
        if getattr(self,'server',None):
            self.server.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description='Gensite native website studio')
    parser.add_argument('--open', type=Path, help='Open a generated project or site folder')
    parser.add_argument('--state', type=Path, help='Alternative settings file for isolated testing')
    parser.add_argument('--check', action='store_true', help='Verify native runtime without opening a window')
    args = parser.parse_args()
    if args.check:
        print('Gensite native runtime ready · Python '+sys.version.split()[0])
        return 0
    if sys.stderr is None:
        sys.stderr = sys.stdout = open(ROOT/'native-app.log','a',encoding='utf-8',buffering=1)
    app = QApplication(sys.argv)
    app.setApplicationName('Gensite')
    app.setStyle('Fusion')
    def exception_hook(kind, value, trace):
        import traceback
        traceback.print_exception(kind,value,trace)
        QMessageBox.critical(None,'Gensite — action failed',str(value)+'\n\nSee native-app.log for details when launched from the desktop.')
    sys.excepthook = exception_hook
    window = MainWindow(state_path=args.state)
    window.show()
    if args.open:
        try:
            window.open_site(args.open)
        except (OSError,ValueError) as exc:
            window.error(str(exc))
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
