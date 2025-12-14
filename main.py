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

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QProgressBar, QLineEdit, QTextEdit, 
                             QTabWidget, QGraphicsOpacityEffect)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QProcess, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QTextCursor

# ========== CONFIG ==========
CONFIG = {
    "base_url": "https://raw.githubusercontent.com/NotLoann/loannsmp-modpack/main/",
    "ram_gb": 4
}

MINECRAFT_DIR = mll.utils.get_minecraft_directory()
MODS_DIR = os.path.join(MINECRAFT_DIR, "mods")
VERSION_FILE = os.path.join(MINECRAFT_DIR, "loannsmp_version.json")
INSTALLED_FORGE_VERSION = None

# ========== LOGGER ==========

class QTextEditLogger(logging.Handler):
    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
    
    def emit(self, record):
        try:
            msg = self.format(record)
            from PyQt6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(
                self.text_edit,
                "append",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, msg)
            )
        except:
            pass

# ========== WORKERS ==========

class UpdateChecker(QThread):
    update_available = pyqtSignal(bool, str, str)
    installation_valid = pyqtSignal(bool)
    modpack_unavailable = pyqtSignal()
    
    def run(self):
        try:
            logging.info("🔍 Vérification de l'installation...")
            
            # Vérifie disponibilité modpack
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
            
            # Vérifie Forge
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
            
            # Vérifie version mods
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
            
            # Vérifie MAJ launcher
            try:
                resp = requests.get(CONFIG["base_url"] + "update.json", timeout=10)
                data = resp.json()
                self.update_available.emit(False, "", "")
            except:
                self.update_available.emit(False, "", "")
        except Exception as e:
            logging.error(f"❌ Erreur vérification: {e}")
            self.installation_valid.emit(False)


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    log = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._running = True
    
    def run(self):
        try:
            self.log.emit("="*70)
            self.log.emit("📦 TÉLÉCHARGEMENT DES MODS")
            self.log.emit("="*70)
            
            # 1. Récupère URL
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
            
            # 2. Télécharge ZIP
            self.progress.emit(10, "Téléchargement...")
            self.log.emit(f"Téléchargement du modpack depuis: {url[:50]}...")
            self.log.emit("Cela peut prendre du temps selon la taille...")
            
            try:
                resp = requests.get(url, stream=True, timeout=120)
                resp.raise_for_status()
                
                total_size = int(resp.headers.get('content-length', 0))
                if total_size > 0:
                    self.log.emit(f"Taille du fichier: {total_size / (1024*1024):.2f} MB")
                
                data = io.BytesIO()
                downloaded = 0
                
                self.log.emit("Téléchargement en cours...")
                for chunk in resp.iter_content(8192):
                    if not self._running:
                        self.log.emit("Téléchargement annulé")
                        return
                    if chunk:
                        data.write(chunk)
                        downloaded += len(chunk)
                
                self.log.emit(f"✅ Téléchargement terminé: {downloaded / (1024*1024):.2f} MB")
            except requests.Timeout:
                self.log.emit("❌ Timeout lors du téléchargement (fichier trop gros ou connexion lente)")
                self.finished.emit(False, "Erreur téléchargement")
                return
            except Exception as e:
                self.log.emit(f"❌ Erreur téléchargement: {e}")
                self.finished.emit(False, "Erreur téléchargement")
                return
            
            # 3. Extrait mods
            self.progress.emit(30, "Extraction...")
            
            try:
                os.makedirs(MODS_DIR, exist_ok=True)
                self.log.emit(f"Dossier mods: {MODS_DIR}")
                
                # Supprime anciens mods
                old_mods = list(Path(MODS_DIR).glob("*.jar"))
                if old_mods:
                    self.log.emit(f"Suppression de {len(old_mods)} ancien(s) mod(s)...")
                    for mod in old_mods:
                        try:
                            mod.unlink()
                        except Exception as e:
                            self.log.emit(f"⚠️ Impossible de supprimer {mod.name}: {e}")
                
                # Extrait
                self.log.emit("Extraction du ZIP...")
                data.seek(0)
                
                with zipfile.ZipFile(data) as z:
                    jars = [f for f in z.namelist() if f.endswith('.jar') and not f.startswith('__MACOSX') and not os.path.basename(f).startswith('.')]
                    
                    if not jars:
                        self.log.emit("❌ Aucun fichier .jar trouvé dans le ZIP")
                        self.finished.emit(False, "Aucun mod")
                        return
                    
                    self.log.emit(f"Extraction de {len(jars)} mod(s):")
                    
                    count = 0
                    for jar in jars:
                        try:
                            if not self._running:
                                return
                            
                            name = os.path.basename(jar)
                            if not name:
                                continue
                            
                            content = z.read(jar)
                            output_path = os.path.join(MODS_DIR, name)
                            
                            with open(output_path, 'wb') as f:
                                f.write(content)
                            
                            self.log.emit(f"  ✓ {name}")
                            count += 1
                        except Exception as e:
                            self.log.emit(f"  ⚠️ Erreur extraction {jar}: {e}")
                    
                    if count == 0:
                        self.log.emit("❌ Aucun mod extrait")
                        self.finished.emit(False, "Aucun mod")
                        return
                    
                    self.log.emit(f"\n✅ {count} mod(s) installé(s) avec succès")
            except zipfile.BadZipFile:
                self.log.emit("❌ Le fichier téléchargé n'est pas un ZIP valide")
                self.finished.emit(False, "ZIP invalide")
                return
            except Exception as e:
                self.log.emit(f"❌ Erreur extraction: {e}")
                self.finished.emit(False, "Erreur extraction")
                return
            
            # Sauvegarde version
            try:
                hash_val = hashlib.md5(url.encode()).hexdigest()
                data_to_save = {
                    'modpack_hash': hash_val,
                    'modpack_url': url,
                    'install_date': datetime.now().isoformat()
                }
                with open(VERSION_FILE, 'w') as f:
                    json.dump(data_to_save, f, indent=2)
                self.log.emit("✅ Version sauvegardée")
            except Exception as e:
                self.log.emit(f"⚠️ Impossible de sauvegarder la version: {e}")
            
            self.progress.emit(40, "Mods installés")
            self.log.emit("\n✅ Mods installés avec succès\n")
            
            # 4. Installe Forge
            self.log.emit("="*70)
            self.log.emit("🔍 RECHERCHE DE FORGE")
            self.log.emit("="*70)
            self.progress.emit(50, "Recherche Forge...")
            
            try:
                forge_ver = mll.forge.find_forge_version("1.20.1")
                if not forge_ver:
                    self.log.emit("❌ Forge introuvable")
                    self.finished.emit(False, "Forge introuvable")
                    return
                
                self.log.emit(f"✅ Forge trouvé: {forge_ver}\n")
            except Exception as e:
                self.log.emit(f"❌ Erreur recherche Forge: {e}")
                self.finished.emit(False, "Erreur Forge")
                return
            
            # Vérifie si déjà installé
            try:
                versions = mll.utils.get_installed_versions(MINECRAFT_DIR)
                installed = mll.forge.forge_to_installed_version(forge_ver)
                if any(v["id"] == installed for v in versions):
                    self.log.emit("✅ Forge déjà installé, passage à la suite")
                    global INSTALLED_FORGE_VERSION
                    INSTALLED_FORGE_VERSION = forge_ver
                    self.log.emit("\n" + "="*70)
                    self.log.emit("🎉 INSTALLATION TERMINÉE AVEC SUCCÈS")
                    self.log.emit("="*70)
                    self.progress.emit(100, "Terminé !")
                    self.finished.emit(True, "Prêt")
                    return
            except:
                pass
            
            # Installe Forge
            self.log.emit("="*70)
            self.log.emit("🔨 INSTALLATION DE FORGE")
            self.log.emit("Cela peut prendre plusieurs minutes...")
            self.log.emit("="*70)
            self.progress.emit(60, "Installation Forge...")
            
            try:
                self.log.emit(f"Début de l'installation de {forge_ver}")
                self.log.emit("Les logs détaillés s'affichent ci-dessous:\n")
                
                last_status = [""]
                
                def status_cb(s):
                    if self._running:
                        try:
                            last_status[0] = s
                            self.log.emit(s)
                            display = s[:45] + "..." if len(s) > 45 else s
                            self.progress.emit(70, display)
                        except:
                            pass
                
                def progress_cb(p):
                    if self._running:
                        try:
                            actual = 60 + int(p * 0.35)
                            display = last_status[0][:45] if last_status[0] else f"{p}%"
                            self.progress.emit(actual, display)
                        except:
                            pass
                
                callback = {
                    "setStatus": status_cb,
                    "setProgress": progress_cb,
                    "setMax": lambda m: None
                }
                
                mll.forge.install_forge_version(forge_ver, MINECRAFT_DIR, callback=callback)
                
                if not self._running:
                    return
                
                INSTALLED_FORGE_VERSION = forge_ver
                self.log.emit(f"\n✅ Forge {forge_ver} installé avec succès")
                
                self.log.emit("\n" + "="*70)
                self.log.emit("🎉 INSTALLATION TERMINÉE AVEC SUCCÈS")
                self.log.emit("="*70)
                self.progress.emit(100, "Terminé !")
                self.finished.emit(True, "Prêt")
            except Exception as e:
                self.log.emit(f"❌ Erreur installation Forge: {e}")
                self.finished.emit(False, "Erreur Forge")
                return
                
        except Exception as e:
            self.log.emit(f"❌ ERREUR CRITIQUE: {e}")
            import traceback
            self.log.emit(traceback.format_exc())
            self.finished.emit(False, "Erreur critique")
    
    def stop(self):
        self._running = False


class UninstallWorker(QThread):
    finished = pyqtSignal(bool, str)
    log = pyqtSignal(str)
    
    def run(self):
        try:
            self.log.emit("\n🗑️  DÉSINSTALLATION EN COURS...")
            
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
                self.log.emit("✅ Version supprimée")
            
            global INSTALLED_FORGE_VERSION
            INSTALLED_FORGE_VERSION = None
            self.log.emit("🎉 Désinstallation terminée")
            self.finished.emit(True, "OK")
        except Exception as e:
            self.log.emit(f"❌ Erreur: {e}")
            self.finished.emit(False, str(e))


# ========== UI ==========

class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.workers = []
        self.minecraft_process = None
        self.init_ui()
        self.setup_logging()
        self.fade_in()
        QTimer.singleShot(500, self.check_installation)
    
    def setup_logging(self):
        handler = QTextEditLogger(self.console)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
        
        logging.info("=== LoannSMP Launcher ===")
        logging.info(f"Heure de démarrage: {datetime.now().strftime('%H:%M:%S')}")
        logging.info(f"Répertoire Minecraft: {MINECRAFT_DIR}")
        logging.info("Console initialisée.\n")
    
    def fade_in(self):
        self.opacity = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity)
        self.anim = QPropertyAnimation(self.opacity, b"opacity")
        self.anim.setDuration(600)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
    
    def init_ui(self):
        self.setWindowTitle("LoannSMP Launcher")
        self.setFixedSize(650, 580)
        self.setStyleSheet("QMainWindow { background: #FFFFFF; }")
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(30, 25, 30, 15)
        header_layout.setSpacing(6)
        
        title = QLabel("LoannSMP")
        title.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        title.setStyleSheet("color: #667EEA;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)
        
        subtitle = QLabel("Bienvenue sur le launcher de LoannSMP.")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet("color: #6C757D;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle)
        
        desc = QLabel("l'application est pas totalement terminée donc il peut y avoir des bugs.\nmettez à jour l'application quand vous le pouvez sur le repo github")
        desc.setFont(QFont("Segoe UI", 9))
        desc.setStyleSheet("color: #ADB5BD;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(desc)
        
        layout.addWidget(header)
        
        # Badge MAJ
        self.update_badge = QLabel("🔔 Mise à jour disponible")
        self.update_badge.setStyleSheet("""
            background: #FF9500;
            color: white;
            padding: 5px 14px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 10px;
        """)
        self.update_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_badge.hide()
        layout.addWidget(self.update_badge, 0, Qt.AlignmentFlag.AlignCenter)
        
        # Tabs
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: white;
            }
            QTabBar::tab {
                background: transparent;
                color: #ADB5BD;
                padding: 10px 24px;
                font-size: 12px;
                font-weight: 600;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                color: #667EEA;
                border-bottom: 2px solid #667EEA;
            }
            QTabBar::tab:hover {
                color: #764BA2;
            }
        """)
        layout.addWidget(tabs)
        
        # === LAUNCHER ===
        launcher = QWidget()
        launcher_layout = QVBoxLayout(launcher)
        launcher_layout.setContentsMargins(40, 15, 40, 20)
        launcher_layout.setSpacing(12)
        
        pseudo_label = QLabel("Pseudo Minecraft (crack)")
        pseudo_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 11px;")
        launcher_layout.addWidget(pseudo_label)
        
        self.username = QLineEdit()
        self.username.setPlaceholderText("Entre ton pseudo...")
        self.username.setFixedHeight(38)
        self.username.setStyleSheet("""
            QLineEdit {
                background: #F8F9FA;
                border: 2px solid #E9ECEF;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 13px;
                color: #212529;
            }
            QLineEdit:focus {
                border: 2px solid #667EEA;
                background: white;
            }
        """)
        launcher_layout.addWidget(self.username)
        
        launcher_layout.addSpacing(3)
        
        self.progress = QProgressBar()
        self.progress.setFixedHeight(5)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #F1F3F5;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667EEA, stop:1 #764BA2);
                border-radius: 2px;
            }
        """)
        launcher_layout.addWidget(self.progress)
        
        self.status = QLabel("Vérification...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #667EEA; font-weight: 600; font-size: 11px;")
        launcher_layout.addWidget(self.status)
        
        launcher_layout.addSpacing(5)
        
        self.install_btn = QPushButton("📦 Installer les mods")
        self.install_btn.setFixedHeight(40)
        self.install_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
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
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5568D3, stop:1 #6A4291);
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        launcher_layout.addWidget(self.install_btn)
        
        self.launch_btn = QPushButton("🚀 Lancer Minecraft")
        self.launch_btn.setFixedHeight(40)
        self.launch_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
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
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0F8478, stop:1 #30D66D);
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        launcher_layout.addWidget(self.launch_btn)
        
        launcher_layout.addStretch()
        
        footer = QLabel("play.loannsmp.fr")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #CED4DA; font-size: 9px;")
        launcher_layout.addWidget(footer)
        
        # === OPTIONS ===
        options = QWidget()
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(40, 20, 40, 20)
        options_layout.setSpacing(18)
        
        opt_title = QLabel("⚙️ Paramètres")
        opt_title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        opt_title.setStyleSheet("color: #212529;")
        options_layout.addWidget(opt_title)
        
        # RAM avec boutons + et -
        ram_label = QLabel("💾 Mémoire RAM allouée")
        ram_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        options_layout.addWidget(ram_label)
        
        ram_container = QHBoxLayout()
        ram_container.setSpacing(10)
        
        self.minus_btn = QPushButton("−")
        self.minus_btn.setFixedSize(45, 45)
        self.minus_btn.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.minus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minus_btn.clicked.connect(self.decrease_ram)
        self.minus_btn.setStyleSheet("""
            QPushButton {
                background: #667EEA;
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #5568D3;
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        ram_container.addWidget(self.minus_btn)
        
        self.ram_display = QLabel(f"{CONFIG['ram_gb']} Go")
        self.ram_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ram_display.setFixedHeight(45)
        self.ram_display.setStyleSheet("""
            QLabel {
                background: #F8F9FA;
                border: 2px solid #E9ECEF;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                color: #212529;
            }
        """)
        ram_container.addWidget(self.ram_display, 1)
        
        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(45, 45)
        self.plus_btn.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plus_btn.clicked.connect(self.increase_ram)
        self.plus_btn.setStyleSheet("""
            QPushButton {
                background: #667EEA;
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #5568D3;
            }
            QPushButton:disabled {
                background: #E9ECEF;
                color: #ADB5BD;
            }
        """)
        ram_container.addWidget(self.plus_btn)
        
        options_layout.addLayout(ram_container)
        
        ram_hint = QLabel("Si vous avez -8Go de ram, dépassez pas les 4Go alloués.\nSi vous avez 16Go de ram ou plus, mettez 8+ Go.")
        ram_hint.setStyleSheet("color: #6C757D; font-size: 10px;")
        options_layout.addWidget(ram_hint)
        
        options_layout.addSpacing(8)
        
        # Désinstaller
        uninstall_label = QLabel("🗑️ Désinstallation du modpack")
        uninstall_label.setStyleSheet("color: #495057; font-weight: 600; font-size: 12px;")
        options_layout.addWidget(uninstall_label)
        
        self.uninstall_btn = QPushButton("Désinstaller")
        self.uninstall_btn.setFixedHeight(40)
        self.uninstall_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.uninstall_btn.clicked.connect(self.uninstall)
        self.uninstall_btn.setStyleSheet("""
            QPushButton {
                background: #FF3B30;
                color: white;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: #E0342A;
            }
        """)
        options_layout.addWidget(self.uninstall_btn)
        
        hint = QLabel("⚠️ Supprime tous les mods téléchargés et Forge.")
        hint.setStyleSheet("color: #FF9500; font-size: 10px;")
        options_layout.addWidget(hint)
        
        options_layout.addStretch()
        
        # === CONSOLE ===
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.setContentsMargins(12, 12, 12, 12)
        
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet("""
            QTextEdit {
                background: #1E1E1E;
                color: #0DBC79;
                border: 2px solid #E9ECEF;
                border-radius: 8px;
                padding: 12px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 9px;
                line-height: 1.3;
            }
        """)
        console_layout.addWidget(self.console)
        
        tabs.addTab(launcher, "Launcher")
        tabs.addTab(options, "Options")
        tabs.addTab(console_widget, "Console")
        
        self.update_ram_buttons()
    
    def decrease_ram(self):
        if CONFIG["ram_gb"] > 2:
            CONFIG["ram_gb"] -= 1
            self.ram_display.setText(f"{CONFIG['ram_gb']} Go")
            self.update_ram_buttons()
    
    def increase_ram(self):
        if CONFIG["ram_gb"] < 16:
            CONFIG["ram_gb"] += 1
            self.ram_display.setText(f"{CONFIG['ram_gb']} Go")
            self.update_ram_buttons()
    
    def update_ram_buttons(self):
        self.minus_btn.setEnabled(CONFIG["ram_gb"] > 2)
        self.plus_btn.setEnabled(CONFIG["ram_gb"] < 16)
    
    def check_installation(self):
        worker = UpdateChecker()
        worker.installation_valid.connect(self.on_check)
        worker.modpack_unavailable.connect(lambda: self.on_check(False))
        worker.update_available.connect(self.on_update)
        worker.start()
        self.workers.append(worker)
    
    def on_check(self, valid):
        if valid:
            self.status.setText("✅ Prêt à jouer !")
            self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 11px;")
            self.launch_btn.setEnabled(True)
            self.install_btn.setText("✅ À jour")
        else:
            self.status.setText("Installation requise")
            self.status.setStyleSheet("color: #FF9500; font-weight: 600; font-size: 11px;")
            self.install_btn.setEnabled(True)
    
    def on_update(self, has, ver, changelog):
        if has:
            self.update_badge.show()
    
    def install(self):
        self.install_btn.setEnabled(False)
        self.status.setText("Installation en cours...")
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
            self.status.setText("✨ Prêt à jouer !")
            self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 11px;")
            self.launch_btn.setEnabled(True)
            self.install_btn.setText("✅ À jour")
            self.update_badge.hide()
        else:
            if msg == "Modpack pas encore sorti":
                self.status.setText("🔒 Modpack pas encore sorti")
                self.status.setStyleSheet("color: #FF9500; font-weight: 600; font-size: 11px;")
                self.install_btn.setText("🔒 Pas encore disponible")
            else:
                self.status.setText(f"❌ {msg}")
                self.status.setStyleSheet("color: #FF3B30; font-weight: 600; font-size: 11px;")
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
            self.status.setStyleSheet("color: #FF9500; font-weight: 600; font-size: 11px;")
    
    def launch(self):
        user = self.username.text().strip()
        if not user:
            self.status.setText("⚠️ Pseudo requis")
            self.status.setStyleSheet("color: #FF9500; font-weight: 600; font-size: 11px;")
            return
        
        if not INSTALLED_FORGE_VERSION:
            return
        
        self.launch_btn.setEnabled(False)
        logging.info("\n" + "="*70)
        logging.info("🚀 LANCEMENT DE MINECRAFT")
        logging.info("="*70)
        
        try:
            ver = mll.forge.forge_to_installed_version(INSTALLED_FORGE_VERSION)
            ram = CONFIG["ram_gb"]
            
            logging.info(f"Utilisateur: {user}")
            logging.info(f"Version: {ver}")
            logging.info(f"RAM: {ram} Go")
            
            opts = {
                "username": user,
                "uuid": "",
                "token": "",
                "jvmArguments": [f"-Xmx{ram}G", f"-Xms{ram//2}G"],
            }
            
            cmd = mll.command.get_minecraft_command(ver, MINECRAFT_DIR, opts)
            
            self.minecraft_process = QProcess(self)
            self.minecraft_process.readyReadStandardOutput.connect(self.on_mc_stdout)
            self.minecraft_process.readyReadStandardError.connect(self.on_mc_stderr)
            self.minecraft_process.finished.connect(self.on_mc_finished)
            self.minecraft_process.start(cmd[0], cmd[1:])
            
            logging.info("✅ Minecraft lancé avec succès")
            logging.info("Le launcher reste ouvert pour afficher les logs\n")
            self.status.setText("🎮 Minecraft en cours...")
            self.status.setStyleSheet("color: #11998E; font-weight: 600; font-size: 11px;")
        except Exception as e:
            logging.error(f"❌ Erreur lancement: {e}")
            self.launch_btn.setEnabled(True)
    
    def on_mc_stdout(self):
        if self.minecraft_process:
            data = bytes(self.minecraft_process.readAllStandardOutput()).decode('utf-8', errors='ignore')
            for line in data.split('\n'):
                if line.strip():
                    logging.info(line)
    
    def on_mc_stderr(self):
        if self.minecraft_process:
            data = bytes(self.minecraft_process.readAllStandardError()).decode('utf-8', errors='ignore')
            for line in data.split('\n'):
                if line.strip():
                    logging.warning(line)
    
    def on_mc_finished(self, exit_code, exit_status):
        logging.info(f"\n🛑 Minecraft fermé (code: {exit_code})")
        self.status.setText("Prêt à relancer")
        self.status.setStyleSheet("color: #667EEA; font-weight: 600; font-size: 11px;")
        self.launch_btn.setEnabled(True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LoannSMP Launcher")
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
