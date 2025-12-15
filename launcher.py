import sys
import os
import io
import zipfile
import requests
import shutil
import minecraft_launcher_lib as mll
from pathlib import Path
from packaging import version
import logging
from datetime import datetime
import hashlib
import json
import psutil

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QPushButton, QProgressBar, QLineEdit, QTextEdit, 
                               QTabWidget, QGraphicsOpacityEffect, QFrame, QStackedWidget, 
                               QCheckBox, QScrollArea, QGridLayout)
from PySide6.QtCore import (Qt, QThread, Signal, QTimer, QProcess, QPropertyAnimation, 
                            QEasingCurve, QRect, QPoint, Property, QUrl, QParallelAnimationGroup,
                            QSequentialAnimationGroup, QSize, QPropertyAnimation)
from PySide6.QtGui import QFont, QTextCursor, QColor, QDesktopServices

# ========== CONFIG ==========
CONFIG = {
    "base_url": "https://raw.githubusercontent.com/NotLoann/loannsmp-modpack/main/",
    "ram_gb": 4,
    "keep_launcher_open": True, # ACTIVÉ PAR DÉFAUT
    "discord_url": "https://discord.gg/x3GtCqqXXj"
}

MINECRAFT_DIR = mll.utils.get_minecraft_directory()
MODS_DIR = os.path.join(MINECRAFT_DIR, "mods")
VERSION_FILE = os.path.join(MINECRAFT_DIR, "loannsmp_version.json")
INSTALLED_FORGE_VERSION = None


# ========== CUSTOM CHECKBOX ==========

class ModernCheckBox(QWidget):
    stateChanged = Signal(int)
    
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.checked = False
        self.text = text
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.switch_container = QFrame()
        self.switch_container.setFixedSize(44, 24)
        self.switch_container.setStyleSheet("""
            QFrame {
                background: #E9ECEF;
                border-radius: 12px;
            }
        """)
        
        self.switch_circle = QFrame(self.switch_container)
        self.switch_circle.setFixedSize(18, 18)
        self.switch_circle.move(3, 3)
        self.switch_circle.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border-radius: 9px;
            }
        """)
        
        layout.addWidget(self.switch_container)
        
        label = QLabel(text)
        label.setStyleSheet("color: #495057; font-size: 11px; font-weight: 500;")
        layout.addWidget(label)
        layout.addStretch()
        
        self.anim_circle = QPropertyAnimation(self.switch_circle, b"pos")
        self.anim_circle.setDuration(200)
        self.anim_circle.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    def mousePressEvent(self, event):
        self.toggle()
    
    def toggle(self):
        self.checked = not self.checked
        
        if self.checked:
            self.anim_circle.setStartValue(QPoint(3, 3))
            self.anim_circle.setEndValue(QPoint(23, 3))
            self.switch_container.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #667EEA, stop:1 #764BA2);
                    border-radius: 12px;
                }
            """)
        else:
            self.anim_circle.setStartValue(QPoint(23, 3))
            self.anim_circle.setEndValue(QPoint(3, 3))
            self.switch_container.setStyleSheet("""
                QFrame {
                    background: #E9ECEF;
                    border-radius: 12px;
                }
            """)
        
        self.anim_circle.start()
        self.stateChanged.emit(2 if self.checked else 0)
    
    def isChecked(self):
        return self.checked
    
    def setChecked(self, checked):
        if self.checked != checked:
            self.toggle()


# ========== TAB BAR ANIMÉ ==========

class AnimatedTabBar(QWidget):
    tab_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_index = 0
        self.indicator_pos = 0
        
        self.setFixedHeight(50)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.buttons = []
        self.tabs = ["🎮 Launcher", "⚙️ Options", "📊 Stats", "📝 Console"]
        
        for i, tab in enumerate(self.tabs):
            btn = QPushButton(tab)
            btn.setFixedHeight(50)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #ADB5BD;
                    border: none;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:checked {
                    color: #667EEA;
                }
                QPushButton:hover {
                    color: #5568D3;
                    background: rgba(102, 126, 234, 0.05);
                }
            """)
            btn.clicked.connect(lambda checked, idx=i: self.on_tab_clicked(idx))
            layout.addWidget(btn)
            self.buttons.append(btn)
        
        self.buttons[0].setChecked(True)
        
        self.indicator = QFrame(self)
        self.indicator.setFixedHeight(3)
        self.indicator.setStyleSheet("background: #667EEA; border-radius: 2px;")
        self.indicator.raise_()
    
    def on_tab_clicked(self, index):
        for i, btn in enumerate(self.buttons):
            btn.setChecked(i == index)
        
        old_index = self.current_index
        self.current_index = index
        self.animate_indicator(old_index, index)
        self.tab_changed.emit(index)
    
    def animate_indicator(self, from_idx, to_idx):
        btn_width = self.width() / len(self.buttons)
        start_x = int(from_idx * btn_width)
        end_x = int(to_idx * btn_width)
        
        self.anim = QPropertyAnimation(self, b"indicator_position")
        self.anim.setDuration(300)
        self.anim.setStartValue(start_x)
        self.anim.setEndValue(end_x)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
    
    def get_indicator_position(self):
        return self.indicator_pos
    
    def set_indicator_position(self, pos):
        self.indicator_pos = pos
        btn_width = self.width() / len(self.buttons)
        self.indicator.setGeometry(int(pos), self.height() - 3, int(btn_width), 3)
    
    indicator_position = Property(int, get_indicator_position, set_indicator_position)
    
    def update_indicator_position(self):
        btn_width = self.width() / len(self.buttons)
        x = int(self.current_index * btn_width)
        self.indicator.setGeometry(x, self.height() - 3, int(btn_width), 3)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_indicator_position()


# ========== LOGGER ==========

class ColoredTextEditLogger(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
    
    def emit(self, record):
        try:
            msg = self.format(record)
            color = '#0DBC79'
            
            if '✅' in msg or '🎉' in msg:
                color = '#38EF7D'
            elif '⚠️' in msg or '🔒' in msg:
                color = '#FFD93D'
            elif '❌' in msg:
                color = '#FF6B6B'
            elif '🔍' in msg or '📦' in msg or '🔨' in msg:
                color = '#667EEA'
            
            formatted = f'<span style="color: {color};">{msg}</span>'
            self.text_edit.append(formatted)
            self.text_edit.moveCursor(QTextCursor.MoveOperation.End)
        except:
            pass


# ========== WORKERS (identiques, version courte) ==========

class UpdateChecker(QThread):
    installation_valid = Signal(bool)
    modpack_unavailable = Signal()
    
    def run(self):
        try:
            logging.info("🔍 Vérification de l'installation...")
            try:
                resp = requests.get(CONFIG["base_url"] + "modpack.txt", timeout=10)
                remote_url = resp.text.strip()
                if remote_url.lower() == "none":
                    logging.info("⚠️ Le modpack n'est pas encore disponible")
                    self.modpack_unavailable.emit()
                    return
            except Exception as e:
                logging.warning(f"⚠️ Impossible de vérifier la disponibilité: {e}")
                self.installation_valid.emit(False)
                return
            
            forge_installed = False
            try:
                forge_version = mll.forge.find_forge_version("1.20.1")
                if forge_version:
                    versions = mll.utils.get_installed_versions(MINECRAFT_DIR)
                    installed_forge = mll.forge.forge_to_installed_version(forge_version)
                    forge_installed = any(v["id"] == installed_forge for v in versions)
                    if forge_installed:
                        global INSTALLED_FORGE_VERSION
                        INSTALLED_FORGE_VERSION = forge_version
                        logging.info(f"✅ Forge {forge_version} détecté")
            except Exception as e:
                logging.warning(f"⚠️ Erreur vérification Forge: {e}")
            
            try:
                resp = requests.get(CONFIG["base_url"] + "modpack.txt", timeout=10)
                remote_hash = hashlib.md5(resp.text.strip().encode()).hexdigest()
                local_hash = None
                if os.path.exists(VERSION_FILE):
                    try:
                        with open(VERSION_FILE, 'r') as f:
                            local_hash = json.load(f).get('modpack_hash')
                    except:
                        pass
                
                mods_exist = os.path.exists(MODS_DIR) and len(list(Path(MODS_DIR).glob("*.jar"))) > 0
                
                if local_hash == remote_hash and mods_exist and forge_installed:
                    logging.info("✅ Installation à jour !")
                    self.installation_valid.emit(True)
                else:
                    if not mods_exist:
                        logging.info("⚠️ Aucun mod installé")
                    elif local_hash != remote_hash:
                        logging.info("⚠️ Mise à jour disponible")
                    elif not forge_installed:
                        logging.info("⚠️ Forge non installé")
                    self.installation_valid.emit(False)
            except Exception as e:
                logging.warning(f"⚠️ Impossible de vérifier la version: {e}")
                self.installation_valid.emit(False)
        except Exception as e:
            logging.error(f"❌ Erreur vérification: {e}")
            self.installation_valid.emit(False)


class InstallWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)
    log = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._running = True
    
    def run(self):
        try:
            self.log.emit("="*70)
            self.log.emit("📦 TÉLÉCHARGEMENT DES MODS")
            self.log.emit("="*70)
            self.progress.emit(5, "Récupération du lien...")
            self.log.emit("Lecture de modpack.txt...")
            try:
                resp = requests.get(CONFIG["base_url"] + "modpack.txt", timeout=15)
                url = resp.text.strip()
                if not url:
                    self.log.emit("❌ modpack.txt est vide")
                    self.finished.emit(False, "Erreur lien modpack")
                    return
                if url.lower() == "none":
                    self.log.emit("❌ Le modpack n'est pas encore sorti")
                    self.finished.emit(False, "Modpack pas encore sorti")
                    return
                if not url.startswith(('http://', 'https://')):
                    self.log.emit(f"❌ URL invalide dans modpack.txt: {url}")
                    self.finished.emit(False, "URL invalide")
                    return
                self.log.emit(f"✅ URL récupérée avec succès")
            except Exception as e:
                self.log.emit(f"❌ Erreur lors de la lecture de modpack.txt: {e}")
                self.finished.emit(False, "Erreur URL")
                return
            
            self.progress.emit(10, "Téléchargement...")
            self.log.emit(f"Téléchargement du modpack...")
            try:
                resp = requests.get(url, stream=True, timeout=120)
                resp.raise_for_status()
                total_size = int(resp.headers.get('content-length', 0))
                if total_size > 0:
                    self.log.emit(f"Taille du fichier: {total_size / (1024*1024):.2f} MB")
                data = io.BytesIO()
                downloaded = 0
                for chunk in resp.iter_content(8192):
                    if not self._running:
                        return
                    if chunk:
                        data.write(chunk)
                        downloaded += len(chunk)
                self.log.emit(f"✅ Téléchargement terminé: {downloaded / (1024*1024):.2f} MB")
            except Exception as e:
                self.log.emit(f"❌ Erreur téléchargement: {e}")
                self.finished.emit(False, "Erreur téléchargement")
                return
            
            self.progress.emit(30, "Extraction...")
            try:
                os.makedirs(MODS_DIR, exist_ok=True)
                old_mods = list(Path(MODS_DIR).glob("*.jar"))
                if old_mods:
                    self.log.emit(f"Suppression de {len(old_mods)} ancien(s) mod(s)...")
                    for mod in old_mods:
                        try:
                            mod.unlink()
                        except:
                            pass
                self.log.emit("Extraction du ZIP...")
                data.seek(0)
                with zipfile.ZipFile(data) as z:
                    jars = [f for f in z.namelist() if f.endswith('.jar') and not f.startswith('__MACOSX')]
                    if not jars:
                        self.log.emit("❌ Aucun fichier .jar trouvé")
                        self.finished.emit(False, "Aucun mod")
                        return
                    self.log.emit(f"Extraction de {len(jars)} mod(s):")
                    count = 0
                    for jar in jars:
                        try:
                            name = os.path.basename(jar)
                            if name:
                                content = z.read(jar)
                                with open(os.path.join(MODS_DIR, name), 'wb') as f:
                                    f.write(content)
                                self.log.emit(f"  ✓ {name}")
                                count += 1
                        except:
                            pass
                    self.log.emit(f"\n✅ {count} mod(s) installé(s)")
            except Exception as e:
                self.log.emit(f"❌ Erreur extraction: {e}")
                self.finished.emit(False, "Erreur extraction")
                return
            
            try:
                hash_val = hashlib.md5(url.encode()).hexdigest()
                with open(VERSION_FILE, 'w') as f:
                    json.dump({'modpack_hash': hash_val, 'url': url}, f)
            except:
                pass
            
            self.progress.emit(50, "Recherche Forge...")
            self.log.emit("\n🔍 RECHERCHE DE FORGE")
            try:
                forge_ver = mll.forge.find_forge_version("1.20.1")
                if not forge_ver:
                    self.finished.emit(False, "Forge introuvable")
                    return
                self.log.emit(f"✅ Forge: {forge_ver}")
            except Exception as e:
                self.finished.emit(False, "Erreur Forge")
                return
            
            try:
                versions = mll.utils.get_installed_versions(MINECRAFT_DIR)
                installed = mll.forge.forge_to_installed_version(forge_ver)
                if any(v["id"] == installed for v in versions):
                    global INSTALLED_FORGE_VERSION
                    INSTALLED_FORGE_VERSION = forge_ver
                    self.log.emit("✅ Forge déjà installé")
                    self.progress.emit(100, "Terminé !")
                    self.finished.emit(True, "Prêt")
                    return
            except:
                pass
            
            self.progress.emit(60, "Installation Forge...")
            self.log.emit("\n🔨 INSTALLATION DE FORGE")
            try:
                def status_cb(s):
                    if self._running:
                        self.log.emit(s)
                callback = {
                    "setStatus": status_cb,
                    "setProgress": lambda p: None,
                    "setMax": lambda m: None
                }
                mll.forge.install_forge_version(forge_ver, MINECRAFT_DIR, callback=callback)
                INSTALLED_FORGE_VERSION = forge_ver
                self.log.emit("\n🎉 INSTALLATION TERMINÉE")
                self.progress.emit(100, "Terminé !")
                self.finished.emit(True, "Prêt")
            except Exception as e:
                self.log.emit(f"❌ Erreur: {e}")
                self.finished.emit(False, "Erreur Forge")
        except Exception as e:
            self.log.emit(f"❌ ERREUR: {e}")
            self.finished.emit(False, "Erreur")
    
    def stop(self):
        self._running = False


class UninstallWorker(QThread):
    finished = Signal(bool, str)
    log = Signal(str)
    
    def run(self):
        try:
            self.log.emit("\n🗑️  DÉSINSTALLATION...")
            if os.path.exists(MODS_DIR):
                count = len(list(Path(MODS_DIR).glob("*.jar")))
                shutil.rmtree(MODS_DIR)
                os.makedirs(MODS_DIR)
                self.log.emit(f"✅ {count} mods supprimés")
            versions_dir = os.path.join(MINECRAFT_DIR, "versions")
            if os.path.exists(versions_dir):
                for v in Path(versions_dir).iterdir():
                    if "forge" in v.name.lower():
                        shutil.rmtree(v)
                        self.log.emit(f"✅ {v.name} supprimé")
            if os.path.exists(VERSION_FILE):
                os.remove(VERSION_FILE)
            global INSTALLED_FORGE_VERSION
            INSTALLED_FORGE_VERSION = None
            self.log.emit("✅ Terminé")
            self.finished.emit(True, "OK")
        except Exception as e:
            self.log.emit(f"❌ Erreur: {e}")
            self.finished.emit(False, str(e))


# ========== UI PRINCIPALE ==========

class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workers = []
        self.minecraft_process = None
        self.game_running = False
        self.init_ui()
        self.setup_logging()
        self.startup_animation()
        QTimer.singleShot(800, self.check_installation)
        
        # Timer pour mettre à jour les stats
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_stats)
        self.stats_timer.start(1000)
    
    def setup_logging(self):
        handler = ColoredTextEditLogger(self.console)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
        
        logging.info("=== Loann SMP Launcher ===")
        logging.info(f"Démarrage: {datetime.now().strftime('%H:%M:%S')}")
        logging.info(f"Dossier: {MINECRAFT_DIR}\n")
    
    def startup_animation(self):
        self.opacity = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity)
        
        fade = QPropertyAnimation(self.opacity, b"opacity")
        fade.setDuration(500)
        fade.setStartValue(0)
        fade.setEndValue(1)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        geo = self.geometry()
        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(500)
        slide.setStartValue(QPoint(geo.x(), geo.y() - 50))
        slide.setEndValue(QPoint(geo.x(), geo.y()))
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.startup_group = QParallelAnimationGroup()
        self.startup_group.addAnimation(fade)
        self.startup_group.addAnimation(slide)
        self.startup_group.start()
    
    def init_ui(self):
        self.setWindowTitle("LoannSMP Launcher")
        self.setFixedSize(800, 750)  # Hauteur ajustée pour la page Options
        
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - 800) // 2
        y = (screen.height() - 750) // 2 
        self.move(x, y)
        
        self.setStyleSheet("QMainWindow { background: #FFFFFF; }")
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setStyleSheet("background: #FFFFFF; border-bottom: 1px solid #E9ECEF;")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 25, 30, 15)
        header_layout.setSpacing(6)
        
        title = QLabel("LoannSMP")
        title.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        title.setStyleSheet("color: #667EEA; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        
        subtitle = QLabel("Launcher cracké pour LoannSMP")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet("color: #6C757D; border: none;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle)
        
        layout.addWidget(header)
        
        self.tab_bar = AnimatedTabBar()
        self.tab_bar.tab_changed.connect(self.switch_page)
        layout.addWidget(self.tab_bar)
        
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: #F8F9FA;")
        
        self.stack.addWidget(self.create_launcher_page())
        self.stack.addWidget(self.create_options_page())
        self.stack.addWidget(self.create_stats_page())
        self.stack.addWidget(self.create_console_page())
        
        layout.addWidget(self.stack)
    
    def create_launcher_page(self):
        page = QWidget()
        page.setStyleSheet("background: #F8F9FA;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 30, 50, 30)
        layout.setSpacing(15)
        
        pseudo_label = QLabel("Pseudo Minecraft")
        pseudo_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 11px;")
        layout.addWidget(pseudo_label)
        
        self.username = QLineEdit()
        self.username.setPlaceholderText("Entre ton pseudo...")
        self.username.setFixedHeight(45)
        self.username.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                border: 2px solid #E9ECEF;
                border-radius: 10px;
                padding: 0 16px;
                font-size: 14px;
                color: #212529;
            }
            QLineEdit:focus {
                border: 2px solid #667EEA;
            }
            QLineEdit:hover {
                border: 2px solid #CED4DA;
            }
        """)
        layout.addWidget(self.username)
        
        layout.addSpacing(8)
        
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #E9ECEF;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667EEA, stop:1 #764BA2);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress)
        
        self.status = QLabel("Vérification...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #667EEA; font-weight: 600; font-size: 12px; padding: 8px;")
        layout.addWidget(self.status)
        
        layout.addSpacing(12)
        
        self.install_btn = QPushButton("📦 Installer les mods")
        self.install_btn.setFixedHeight(48)
        self.install_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.clicked.connect(self.install)
        self.install_btn.setEnabled(False)
        self.install_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667EEA, stop:1 #764BA2);
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5568D3, stop:1 #6A4291);
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        layout.addWidget(self.install_btn)
        
        self.launch_btn = QPushButton("🚀 Lancer Minecraft")
        self.launch_btn.setFixedHeight(48)
        self.launch_btn.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.setEnabled(False)
        self.launch_btn.clicked.connect(self.launch)
        self.launch_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #11998E, stop:1 #38EF7D);
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover:enabled {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0F8478, stop:1 #30D66D);
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        layout.addWidget(self.launch_btn)
        
        layout.addStretch()
        
        return page
    
    def create_options_page(self):
        page = QWidget()
        page.setStyleSheet("background: #F8F9FA;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(45, 25, 45, 25)
        layout.setSpacing(18)
        
        # RAM
        ram_label = QLabel("💾 Mémoire RAM")
        ram_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        layout.addWidget(ram_label)
        
        ram_container = QHBoxLayout()
        ram_container.setSpacing(12)
        
        minus_container = QWidget()
        minus_layout = QVBoxLayout(minus_container)
        minus_layout.setContentsMargins(0, 0, 0, 0)
        minus_layout.setSpacing(0)
        
        self.minus_btn = QPushButton("-")
        self.minus_btn.setFixedSize(50, 50)
        self.minus_btn.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        self.minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minus_btn.clicked.connect(self.decrease_ram)
        self.minus_btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #667EEA;
                border: 2px solid #E9ECEF;
                border-radius: 25px;
                padding-bottom: 4px; /* Ajustement pour remonter le texte */
            }
            QPushButton:hover:enabled {
                background: #667EEA;
                color: white;
                border: 2px solid #667EEA;
            }
            QPushButton:disabled {
                background: #F8F9FA;
                color: #CED4DA;
                border: 2px solid #E9ECEF;
            }
        """)
        minus_layout.addWidget(self.minus_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        ram_container.addWidget(minus_container)
        
        self.ram_display = QLabel(f"{CONFIG['ram_gb']} Go")
        self.ram_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ram_display.setFixedHeight(50)
        self.ram_display.setStyleSheet("""
            QLabel {
                background: #FFFFFF;
                border: 2px solid #E9ECEF;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
                color: #212529;
            }
        """)
        ram_container.addWidget(self.ram_display, 1) 
        
        plus_container = QWidget()
        plus_layout = QVBoxLayout(plus_container)
        plus_layout.setContentsMargins(0, 0, 0, 0)
        plus_layout.setSpacing(0)
        
        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(50, 50)
        self.plus_btn.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
        self.plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus_btn.clicked.connect(self.increase_ram)
        self.plus_btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #667EEA;
                border: 2px solid #E9ECEF;
                border-radius: 25px;
                padding-bottom: 4px; /* Ajustement pour remonter le texte */
            }
            QPushButton:hover:enabled {
                background: #667EEA;
                color: white;
                border: 2px solid #667EEA;
            }
            QPushButton:disabled {
                background: #F8F9FA;
                color: #CED4DA;
                border: 2px solid #E9ECEF;
            }
        """)
        plus_layout.addWidget(self.plus_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        ram_container.addWidget(plus_container)
        
        layout.addLayout(ram_container)
        
        ram_hint = QLabel("Recommandé: 4-8 Go")
        ram_hint.setStyleSheet("color: #6C757D; font-size: 10px;")
        layout.addWidget(ram_hint)
        
        layout.addSpacing(12)
        
        # Préférences
        prefs_label = QLabel("🎯 Préférences")
        prefs_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        layout.addWidget(prefs_label)
        
        self.keep_open_switch = ModernCheckBox("Garder le launcher ouvert")
        # Utiliser la valeur par défaut du CONFIG (maintenant True)
        self.keep_open_switch.setChecked(CONFIG["keep_launcher_open"]) 
        self.keep_open_switch.stateChanged.connect(self.toggle_keep_open)
        layout.addWidget(self.keep_open_switch)
        
        layout.addSpacing(12)
        
        # Actions rapides
        actions_label = QLabel("🔧 Actions rapides")
        actions_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        layout.addWidget(actions_label)
        
        actions_grid = QGridLayout()
        actions_grid.setSpacing(10)
        
        open_mc_btn = self.create_action_button("📂 Dossier Minecraft", lambda: os.startfile(MINECRAFT_DIR))
        actions_grid.addWidget(open_mc_btn, 0, 0)
        
        copy_logs_btn = self.create_action_button("📋 Copier les logs", self.copy_logs)
        actions_grid.addWidget(copy_logs_btn, 0, 1)
        
        discord_btn = self.create_action_button("💬 Rejoindre Discord", self.open_discord)
        actions_grid.addWidget(discord_btn, 1, 0, 1, 2)
        
        layout.addLayout(actions_grid)
        
        layout.addSpacing(12)
        
        # Désinstallation
        uninstall_label = QLabel("🗑️ Désinstallation")
        uninstall_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        layout.addWidget(uninstall_label)
        
        self.uninstall_btn = QPushButton("Désinstaller Forge et mods")
        self.uninstall_btn.setFixedHeight(42)
        self.uninstall_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.uninstall_btn.clicked.connect(self.uninstall)
        self.uninstall_btn.setStyleSheet("""
            QPushButton {
                background: #DC3545;
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #C82333;
            }
        """)
        layout.addWidget(self.uninstall_btn)
        
        hint = QLabel("⚠️ Supprime tout Forge et les mods")
        hint.setStyleSheet("color: #DC3545; font-size: 9px;")
        layout.addWidget(hint)
        
        layout.addStretch()
        
        QTimer.singleShot(0, self.update_ram_buttons)
        
        return page
    
    def create_stats_page(self):
        page = QWidget()
        page.setStyleSheet("background: #F8F9FA;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(45, 30, 45, 30)
        layout.setSpacing(18)
        
        # Message si le jeu n'est pas lancé
        self.stats_not_running = QLabel("🎮 Lancez Minecraft pour voir les statistiques")
        self.stats_not_running.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stats_not_running.setStyleSheet("""
            QLabel {
                color: #6C757D;
                font-size: 15px;
                font-weight: 600;
                padding: 80px 20px;
            }
        """)
        layout.addWidget(self.stats_not_running)
        
        # Container des stats
        self.stats_container = QWidget()
        stats_layout = QVBoxLayout(self.stats_container)
        stats_layout.setSpacing(15)
        
        self.cpu_card = self.create_stat_card("🔥 CPU", "0%", "#667EEA")
        stats_layout.addWidget(self.cpu_card)
        
        self.ram_card = self.create_stat_card("💾 RAM du jeu", "0 MB", "#11998E")
        stats_layout.addWidget(self.ram_card)
        
        self.system_ram_card = self.create_stat_card("🖥️ RAM Système", f"{psutil.virtual_memory().percent}%", "#FF9500")
        stats_layout.addWidget(self.system_ram_card)
        
        self.playtime_card = self.create_stat_card("⏱️ Temps de jeu", "00:00:00", "#764BA2")
        stats_layout.addWidget(self.playtime_card)
        
        stats_layout.addStretch()
        self.stats_container.hide()
        
        layout.addWidget(self.stats_container)
        layout.addStretch()
        
        self.start_time = None
        
        return page
    
    def create_stat_card(self, title, value, color):
        card = QFrame()
        card.setFixedHeight(80)
        card.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border-left: 4px solid {color};
                border-radius: 10px;
            }}
            QFrame:hover {{
                background: #F8F9FA;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 14, 24, 14)
        card_layout.setSpacing(5)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #6C757D;")
        card_layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color};")
        card_layout.addWidget(value_label)
        
        card.value_label = value_label
        
        return card
    
    def update_stats(self):
        if not self.game_running or not self.minecraft_process:
            self.stats_not_running.show()
            self.stats_container.hide()
            return
        
        self.stats_not_running.hide()
        self.stats_container.show()
        
        try:
            mc_pid = self.minecraft_process.processId()
            if mc_pid:
                process = psutil.Process(mc_pid)
                
                cpu_percent = process.cpu_percent(interval=0.1)
                self.cpu_card.value_label.setText(f"{cpu_percent:.1f}%")
                
                ram_mb = process.memory_info().rss / (1024 * 1024)
                self.ram_card.value_label.setText(f"{ram_mb:.0f} MB")
                
                system_ram = psutil.virtual_memory().percent
                self.system_ram_card.value_label.setText(f"{system_ram:.1f}%")
                
                if self.start_time:
                    elapsed = datetime.now() - self.start_time
                    hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    self.playtime_card.value_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        except:
            pass
    
    def create_action_button(self, text, callback):
        btn = QPushButton(text)
        btn.setFixedHeight(42)
        btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Connecter l'action directement pour la fiabilité
        btn.clicked.connect(callback) 
        # Connecter l'animation pour le feedback visuel
        btn.clicked.connect(lambda: self.animate_button_click(btn)) 
        
        btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF;
                color: #667EEA;
                border: 2px solid #E9ECEF;
                border-radius: 8px;
                text-align: center;
            }
            QPushButton:hover {
                background: #667EEA;
                color: white;
                border: 2px solid #667EEA;
            }
        """)
        return btn
    
    def animate_button_click(self, button):
        anim = QPropertyAnimation(button, b"geometry")
        anim.setDuration(100)
        
        geo = button.geometry()
        shrink_geo = QRect(geo.x() + 3, geo.y() + 2, geo.width() - 6, geo.height() - 4)
        
        anim.setStartValue(geo)
        anim.setEndValue(shrink_geo)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        anim_back = QPropertyAnimation(button, b"geometry")
        anim_back.setDuration(100)
        anim_back.setStartValue(shrink_geo)
        anim_back.setEndValue(geo)
        anim_back.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        seq = QSequentialAnimationGroup()
        seq.addAnimation(anim)
        seq.addAnimation(anim_back)
        seq.start()
    
    def create_console_page(self):
        page = QWidget()
        page.setStyleSheet("background: #F8F9FA;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(15, 15, 15, 15)
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            QTextEdit {
                background: #1E1E1E;
                color: #0DBC79;
                border: 2px solid #E9ECEF;
                border-radius: 10px;
                padding: 14px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9px;
                line-height: 1.4;
            }
        """)
        layout.addWidget(self.console)
        
        return page
    
    def toggle_keep_open(self, state):
        CONFIG["keep_launcher_open"] = (state == 2)
    
    def copy_logs(self):
        logs_dir = os.path.join(MINECRAFT_DIR, "logs")
        latest_log = os.path.join(logs_dir, "latest.log")
        
        if os.path.exists(latest_log):
            try:
                with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                clipboard = QApplication.clipboard()
                clipboard.setText(content)
                
                logging.info("✅ Logs copiés dans le presse-papier !")
                self.status.setText("✅ Logs copiés !")
                self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 12px;")
            except Exception as e:
                logging.error(f"❌ Erreur copie logs: {e}")
        else:
            logging.warning("⚠️ Aucun fichier de logs trouvé")
    
    def open_discord(self):
        QDesktopServices.openUrl(QUrl(CONFIG["discord_url"]))
        logging.info("💬 Ouverture du Discord...")
    
    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
    
    def decrease_ram(self):
        if CONFIG["ram_gb"] > 2:
            CONFIG["ram_gb"] -= 1
            self.ram_display.setText(f"{CONFIG['ram_gb']} Go")
            self.update_ram_buttons()
            self.animate_ram_bounce()
    
    def increase_ram(self):
        if CONFIG["ram_gb"] < 16:
            CONFIG["ram_gb"] += 1
            self.ram_display.setText(f"{CONFIG['ram_gb']} Go")
            self.update_ram_buttons()
            self.animate_ram_bounce()
    
    def animate_ram_bounce(self):
        anim = QPropertyAnimation(self.ram_display, b"geometry")
        anim.setDuration(150)
        
        geo = self.ram_display.geometry()
        bounce_geo = QRect(geo.x(), geo.y() - 5, geo.width(), geo.height() + 10)
        
        anim.setStartValue(geo)
        anim.setKeyValueAt(0.5, bounce_geo)
        anim.setEndValue(geo)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
    
    def update_ram_buttons(self):
        self.minus_btn.setEnabled(CONFIG["ram_gb"] > 2)
        self.plus_btn.setEnabled(CONFIG["ram_gb"] < 16)
    
    def check_installation(self):
        worker = UpdateChecker()
        worker.installation_valid.connect(self.on_check)
        worker.modpack_unavailable.connect(lambda: self.on_check(False))
        worker.start()
        self.workers.append(worker)
    
    def on_check(self, valid):
        if valid:
            self.status.setText("✅ Prêt à jouer !")
            self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 12px;")
            self.launch_btn.setEnabled(True)
            self.install_btn.setText("✅ À jour")
        else:
            self.status.setText("Installation requise")
            self.status.setStyleSheet("color: #FF9500; font-weight: 600; font-size: 12px;")
            self.install_btn.setEnabled(True)
    
    def install(self):
        self.install_btn.setEnabled(False)
        self.status.setText("Installation...")
        self.console.clear()
        
        worker = InstallWorker()
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_install_done)
        worker.log.connect(lambda msg: logging.info(msg))
        worker.start()
        self.workers.append(worker)
    
    def on_progress(self, val, text):
        self.progress.setValue(val)
        self.status.setText(text)
    
    def on_install_done(self, success, msg):
        if success:
            self.status.setText("✨ Prêt !")
            self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 12px;")
            self.launch_btn.setEnabled(True)
            self.install_btn.setText("✅ À jour")
        else:
            if msg == "Modpack pas encore sorti":
                self.status.setText("🔒 Pas encore sorti")
                self.install_btn.setText("🔒 Indisponible")
            else:
                self.status.setText(f"❌ {msg}")
                self.status.setStyleSheet("color: #DC3545; font-weight: 600; font-size: 12px;")
                self.install_btn.setEnabled(True)
    
    def uninstall(self):
        self.uninstall_btn.setEnabled(False)
        worker = UninstallWorker()
        worker.finished.connect(self.on_uninstall_done)
        worker.log.connect(lambda msg: logging.info(msg))
        worker.start()
        self.workers.append(worker)
    
    def on_uninstall_done(self, success, msg):
        self.uninstall_btn.setEnabled(True)
        if success:
            self.launch_btn.setEnabled(False)
            self.install_btn.setEnabled(True)
            self.install_btn.setText("📦 Installer les mods")
            self.status.setText("Installation requise")
    
    def launch(self):
        user = self.username.text().strip()
        if not user:
            self.status.setText("⚠️ Pseudo requis")
            return
        
        if not INSTALLED_FORGE_VERSION:
            return
        
        self.launch_btn.setEnabled(False)
        logging.info("\n🚀 LANCEMENT DE MINECRAFT")
        
        try:
            ver = mll.forge.forge_to_installed_version(INSTALLED_FORGE_VERSION)
            ram = CONFIG["ram_gb"]
            
            logging.info(f"Utilisateur: {user}")
            logging.info(f"RAM: {ram} Go\n")
            
            opts = {
                "username": user,
                "uuid": "",
                "token": "",
                "jvmArguments": [f"-Xmx{ram}G", f"-Xms{ram//2}G"],
            }
            
            cmd = mll.command.get_minecraft_command(ver, MINECRAFT_DIR, opts)
            
            self.minecraft_process = QProcess(self)
            self.minecraft_process.readyReadStandardOutput.connect(
                lambda: logging.info(bytes(self.minecraft_process.readAllStandardOutput()).decode('utf-8', errors='ignore'))
            )
            self.minecraft_process.finished.connect(self.on_mc_finished)
            self.minecraft_process.start(cmd[0], cmd[1:])
            
            self.game_running = True
            self.start_time = datetime.now()
            self.status.setText("🎮 En cours...")
            
            if not CONFIG["keep_launcher_open"]:
                QTimer.singleShot(3000, self.hide)
        except Exception as e:
            logging.error(f"❌ Erreur: {e}")
            self.launch_btn.setEnabled(True)
    
    def on_mc_finished(self, exit_code, exit_status):
        logging.info(f"\n🛑 Minecraft fermé")
        self.status.setText("Prêt")
        self.launch_btn.setEnabled(True)
        self.game_running = False
        self.start_time = None
        
        if not self.isVisible():
            self.show()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LoannSMP Launcher")
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
