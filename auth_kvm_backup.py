#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import libvirt
import subprocess
import os
import paramiko
from datetime import datetime
import json
import tarfile
import shutil
from crontab import CronTab
import logging
from logging.handlers import RotatingFileHandler
import re
import xml.etree.ElementTree as ET
import hashlib
import sys
import hashlib
import sys
import argparse

class InputValidator:
    """Classe pour valider les entrées utilisateur"""
    
    @staticmethod
    def validate_hostname(hostname):
        """Valide un nom d'hôte ou une IP"""
        if not hostname:
            return False
        
        # Vérifier si c'est une IP
        if '.' in hostname and all(part.isdigit() for part in hostname.split('.')):
            parts = hostname.split('.')
            if len(parts) == 4:
                try:
                    return all(0 <= int(part) <= 255 for part in parts)
                except ValueError:
                    return False
        
        # Sinon vérifier le hostname
        hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        return bool(re.match(hostname_pattern, hostname))
    
    @staticmethod
    def validate_username(username):
        """Valide un nom d'utilisateur"""
        if not username:
            return False
        # Nom d'utilisateur Linux valide
        pattern = r'^[a-z_][a-z0-9_-]*[$]?$'
        return bool(re.match(pattern, username)) and len(username) <= 32
    
    @staticmethod
    def validate_path(path):
        """Valide un chemin Unix"""
        if not path:
            return False
        # Chemin Unix valide
        pattern = r'^(/[^/\x00]*)+/?$'
        return bool(re.match(pattern, path))
    
    @staticmethod
    def validate_cron_expression(cron_expr):
        """Valide une expression cron"""
        if not cron_expr:
            return False
        parts = cron_expr.split()
        if len(parts) != 5:
            return False
        
        # Valider chaque partie de l'expression cron
        patterns = [
            r'^(\*|([0-5]?[0-9])|(\*/[0-9]+))$',  # minutes (avec support */X)
            r'^(\*|([01]?[0-9]|2[0-3])|(\*/[0-9]+))$',  # heures (avec support */X)
            r'^(\*|([1-2]?[0-9]|3[01])|(\*/[0-9]+))$',  # jour du mois (avec support */X)
            r'^(\*|([1-9]|1[0-2])|(\*/[0-9]+))$',  # mois (avec support */X)
            r'^(\*|[0-6]|(\*/[0-9]+))$'  # jour de la semaine (avec support */X)
        ]
        
        for i, part in enumerate(parts):
            if not re.match(patterns[i], part):
                return False
        return True

class Logger:
    """Classe pour gérer le logging professionnel"""
    
    def __init__(self, name='kvm_backup', log_file='/var/log/kvm_backup.log'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Créer le répertoire de logs s'il n'existe pas
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
            except PermissionError:
                # Fallback vers le répertoire utilisateur
                log_file = os.path.expanduser('~/kvm_backup.log')
        
        # Handler pour fichier avec rotation
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=10*1024*1024, backupCount=5
            )
            file_handler.setLevel(logging.INFO)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
        except PermissionError:
            pass  # Si on ne peut pas écrire les logs, on continue sans
        
        # Handler pour console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def info(self, message):
        self.logger.info(message)
    
    def error(self, message):
        self.logger.error(message)
    
    def warning(self, message):
        self.logger.warning(message)
    
    def debug(self, message):
        self.logger.debug(message)

class PasswordDialog:
    """Dialogue pour saisir le mot de passe SSH"""
    
    def __init__(self, parent):
        self.password = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Authentification SSH")
        self.dialog.geometry("300x150")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centrer la fenêtre
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        # Interface
        ttk.Label(self.dialog, text="Mot de passe SSH:").pack(pady=10)
        
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self.dialog, textvariable=self.password_var, show="*", width=30)
        self.password_entry.pack(pady=5)
        self.password_entry.focus()
        
        # Boutons
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="OK", command=self.ok_clicked).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Annuler", command=self.cancel_clicked).pack(side='left', padx=5)
        
        # Bind Enter key
        self.dialog.bind('<Return>', lambda e: self.ok_clicked())
        self.dialog.bind('<Escape>', lambda e: self.cancel_clicked())
    
    def ok_clicked(self):
        self.password = self.password_var.get()
        self.dialog.destroy()
    
    def cancel_clicked(self):
        self.password = None
        self.dialog.destroy()

class KVMBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sauvegarde KVM - Version Production")
        self.root.geometry("900x700")
        
        # Initialiser le logger
        self.logger = Logger()
        self.logger.info("Démarrage de l'application KVM Backup")
        
        # Configuration
        self.config_file = os.path.expanduser("~/.kvm_backup_config.json")
        self.load_config()
        
        # Variables pour stocker les credentials temporairement
        self.ssh_password = None
        
        # Style
        self.style = ttk.Style()
        self.style.configure('TNotebook.Tab', padding=[10, 5])
        self.style.configure('TButton', padding=5)
        
        # Notebook (onglets)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Onglet Sauvegarde
        self.backup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.backup_tab, text='Sauvegarde')
        self.setup_backup_tab()
        
        # Onglet Restauration
        self.restore_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.restore_tab, text='Restauration')
        self.setup_restore_tab()
        
        # Onglet Configuration
        self.config_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text='Configuration')
        self.setup_config_tab()
        
        # Onglet Crédits
        self.credits_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.credits_tab, text='À propos')
        self.setup_credits_tab()
        
        # Charger les VMs au démarrage
        self.populate_vm_list()
    
    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = {
                "backup_host": "",
                "backup_user": "",
                "backup_path": "/backup/kvm",
                "auto_backup": False,
                "backup_freq": "0 2 * * *",
                "selected_vms": {}
            }
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)
    
    def setup_backup_tab(self):
        # Frame pour la liste des VMs
        vm_frame = ttk.LabelFrame(self.backup_tab, text="Machines Virtuelles", padding=10)
        vm_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Treeview pour les VMs
        self.vm_tree = ttk.Treeview(vm_frame, columns=('name', 'backup'), show='headings')
        self.vm_tree.heading('name', text='Nom de la VM')
        self.vm_tree.heading('backup', text='Sauvegarder')
        self.vm_tree.column('name', width=300)
        self.vm_tree.column('backup', width=100, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(vm_frame, orient='vertical', command=self.vm_tree.yview)
        self.vm_tree.configure(yscrollcommand=scrollbar.set)
        
        self.vm_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Frame pour les options de sauvegarde
        options_frame = ttk.Frame(self.backup_tab)
        options_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(options_frame, text="Type de sauvegarde:").pack(side='left')
        
        self.backup_type = tk.StringVar(value="full")
        ttk.Radiobutton(options_frame, text="Complète", variable=self.backup_type, value="full").pack(side='left', padx=5)
        ttk.Radiobutton(options_frame, text="Incrémentielle", variable=self.backup_type, value="incr").pack(side='left', padx=5)
        
        # Bouton de sauvegarde
        ttk.Button(self.backup_tab, text="Lancer la sauvegarde", command=self.start_backup).pack(pady=10)
        
        # Console de sortie
        output_frame = ttk.LabelFrame(self.backup_tab, text="Journal", padding=10)
        output_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, height=10)
        self.output_text.pack(fill='both', expand=True)
    
    def setup_restore_tab(self):
        # Frame principal
        main_frame = ttk.Frame(self.restore_tab)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Bouton d'actualisation
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Button(button_frame, text="Actualiser la liste des sauvegardes", 
                  command=self.populate_restore_list).pack(side='left')
        
        # Treeview pour les sauvegardes disponibles
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill='both', expand=True)
        
        self.restore_tree = ttk.Treeview(tree_frame, columns=('vm', 'date', 'type'), show='headings')
        self.restore_tree.heading('vm', text='Machine Virtuelle')
        self.restore_tree.heading('date', text='Date')
        self.restore_tree.heading('type', text='Type')
        self.restore_tree.column('vm', width=250)
        self.restore_tree.column('date', width=150)
        self.restore_tree.column('type', width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.restore_tree.yview)
        self.restore_tree.configure(yscrollcommand=scrollbar.set)
        
        self.restore_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Bouton de restauration
        ttk.Button(self.restore_tab, text="Restaurer la sauvegarde sélectionnée", 
                  command=self.restore_backup).pack(pady=10)
        
        # Charger automatiquement la liste si les paramètres sont configurés
        if self.config.get("backup_host") and self.config.get("backup_user"):
            # Essayer de charger avec un délai
            self.root.after(1000, self.try_populate_restore_list)
    
    def setup_config_tab(self):
        # Configuration du serveur de backup
        ttk.Label(self.config_tab, text="Serveur de backup:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.backup_host = ttk.Entry(self.config_tab)
        self.backup_host.insert(0, self.config.get("backup_host", ""))
        self.backup_host.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        
        ttk.Label(self.config_tab, text="Utilisateur:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.backup_user = ttk.Entry(self.config_tab)
        self.backup_user.insert(0, self.config.get("backup_user", ""))
        self.backup_user.grid(row=1, column=1, sticky='ew', padx=5, pady=5)
        
        ttk.Label(self.config_tab, text="Chemin sur le serveur:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.backup_path = ttk.Entry(self.config_tab)
        self.backup_path.insert(0, self.config.get("backup_path", "/backup/kvm"))
        self.backup_path.grid(row=2, column=1, sticky='ew', padx=5, pady=5)
        
        # Mot de passe SSH
        ttk.Label(self.config_tab, text="Mot de passe SSH:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.ssh_password_entry = ttk.Entry(self.config_tab, show="*")
        self.ssh_password_entry.grid(row=3, column=1, sticky='ew', padx=5, pady=5)
        
        # Sauvegarde automatique
        self.auto_backup = tk.BooleanVar(value=self.config.get("auto_backup", False))
        ttk.Checkbutton(self.config_tab, text="Sauvegarde automatique", variable=self.auto_backup).grid(row=4, column=0, columnspan=2, sticky='w', padx=5, pady=5)
        
        ttk.Label(self.config_tab, text="Fréquence (cron):").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.backup_freq = ttk.Entry(self.config_tab)
        self.backup_freq.insert(0, self.config.get("backup_freq", "0 2 * * *"))
        self.backup_freq.grid(row=5, column=1, sticky='ew', padx=5, pady=5)
        
        # Bouton de test de connexion
        ttk.Button(self.config_tab, text="Tester la connexion SSH", 
                  command=self.test_ssh_connection).grid(row=6, column=0, columnspan=2, pady=5)
        
        # Bouton de sauvegarde de configuration
        ttk.Button(self.config_tab, text="Enregistrer la configuration", 
                  command=self.save_configuration).grid(row=7, column=0, columnspan=2, pady=10)
    
    def setup_credits_tab(self):
        """Configuration de l'onglet Crédits/À propos"""
        # Frame principal avec padding
        main_frame = ttk.Frame(self.credits_tab, padding=20)
        main_frame.pack(fill='both', expand=True)
        
        # Titre de l'application
        title_label = ttk.Label(main_frame, text="KVM Backup Tool", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 10))
        
        # Version
        version_label = ttk.Label(main_frame, text="Version Production 2.0", 
                                 font=('Arial', 10))
        version_label.pack(pady=(0, 20))
        
        # Description
        description_text = """
Application de sauvegarde et restauration pour machines virtuelles KVM.
Fonctionnalités principales :
• Sauvegarde complète et incrémentielle
• Transfert automatique vers serveur distant
• Planification automatique avec cron
• Vérification d'intégrité SHA256
• Interface graphique intuitive
        """.strip()
        
        description_label = ttk.Label(main_frame, text=description_text, 
                                     font=('Arial', 10), justify='left')
        description_label.pack(pady=(0, 30))
        
        # Section développeur
        dev_frame = ttk.LabelFrame(main_frame, text="Développeur", padding=15)
        dev_frame.pack(fill='x', pady=(0, 20))
        
        # Nom du développeur
        dev_name_label = ttk.Label(dev_frame, text="Développé par : authentik", 
                                  font=('Arial', 11, 'bold'))
        dev_name_label.pack(anchor='w')
        
        # Lien vers le site
        link_frame = ttk.Frame(dev_frame)
        link_frame.pack(anchor='w', pady=(5, 0))
        
        ttk.Label(link_frame, text="Site web : ").pack(side='left')
        
        # Créer un lien cliquable
        link_label = ttk.Label(link_frame, text="https://fabiansulu.com", 
                              foreground='blue', cursor='hand2',
                              font=('Arial', 10, 'underline'))
        link_label.pack(side='left')
        
        # Fonction pour ouvrir le lien
        def open_website(event):
            import webbrowser
            webbrowser.open("https://fabiansulu.com")
        
        link_label.bind("<Button-1>", open_website)
        
        # Informations techniques
        tech_frame = ttk.LabelFrame(main_frame, text="Informations techniques", padding=15)
        tech_frame.pack(fill='x')
        
        tech_info = """Python 3 • Tkinter • libvirt • paramiko • qemu-img"""
        tech_label = ttk.Label(tech_frame, text=tech_info, font=('Arial', 9))
        tech_label.pack()
        
        # Copyright en bas
        copyright_label = ttk.Label(main_frame, text="© 2025 authentik - Tous droits réservés", 
                                   font=('Arial', 8), foreground='gray')
        copyright_label.pack(side='bottom', pady=(20, 0))
    
    def populate_vm_list(self):
        self.vm_tree.delete(*self.vm_tree.get_children())
        try:
            conn = libvirt.open('qemu:///system')
            if conn is None:
                self.log_output("Échec de la connexion à l'hyperviseur KVM")
                return
            
            domains = conn.listAllDomains(0)
            for domain in domains:
                vm_name = domain.name()
                selected = self.config["selected_vms"].get(vm_name, False)
                self.vm_tree.insert('', 'end', values=(vm_name, '✓' if selected else ''))
            
            conn.close()
        except Exception as e:
            self.log_output(f"Erreur: {str(e)}")
            self.logger.error(f"Erreur lors du peuplement de la liste VM: {str(e)}")
    
    def get_vm_disks(self, xml_config):
        """Extraire les chemins des disques depuis la configuration XML"""
        try:
            root = ET.fromstring(xml_config)
            disks = []
            
            # Rechercher tous les éléments disk
            for disk in root.findall(".//disk[@type='file']"):
                source = disk.find("source")
                if source is not None and source.get("file"):
                    disk_path = source.get("file")
                    if os.path.exists(disk_path):
                        disks.append(disk_path)
                    else:
                        self.logger.warning(f"Disque non trouvé: {disk_path}")
            
            return disks
        except ET.ParseError as e:
            self.logger.error(f"Erreur lors de l'analyse XML: {str(e)}")
            return []
    
    def try_populate_restore_list(self):
        """Essayer de charger la liste des sauvegardes sans afficher d'erreurs"""
        try:
            self.populate_restore_list()
        except Exception as e:
            self.logger.info(f"Impossible de charger les sauvegardes au démarrage: {str(e)}")
            # Ajouter un message informatif dans l'interface
            self.restore_tree.insert('', 'end', values=('Info', 'Cliquez sur "Actualiser" pour voir les sauvegardes', 'Configuration requise'))
    
    def populate_restore_list(self):
        self.restore_tree.delete(*self.restore_tree.get_children())
        try:
            ssh = self.create_ssh_connection()
            sftp = ssh.open_sftp()
            backup_path = self.config["backup_path"]
            
            try:
                dirs = sftp.listdir(backup_path)
                for vm_dir in dirs:
                    vm_backup_path = f"{backup_path}/{vm_dir}"
                    try:
                        backups = sftp.listdir(vm_backup_path)
                        for backup in backups:
                            if backup.endswith(".full.tar.gz"):
                                backup_type = "Complète"
                            elif backup.endswith(".incr.tar.gz"):
                                backup_type = "Incrémentielle"
                            else:
                                continue
                            
                            date_str = backup.split("_")[1].split(".")[0]
                            backup_date = datetime.strptime(date_str, "%Y%m%d-%H%M%S")
                            self.restore_tree.insert('', 'end', 
                                                   values=(vm_dir, backup_date.strftime("%Y-%m-%d %H:%M:%S"), backup_type))
                    except IOError:
                        continue
            except IOError:
                self.log_output("Aucune sauvegarde trouvée sur le serveur distant")
            
            sftp.close()
            ssh.close()
        except Exception as e:
            self.log_output(f"Erreur lors de la récupération des sauvegardes: {str(e)}")
            self.logger.error(f"Erreur lors de la récupération des sauvegardes: {str(e)}")
    
    def start_backup(self):
        selected_items = self.vm_tree.selection()
        if not selected_items:
            messagebox.showwarning("Avertissement", "Aucune machine virtuelle sélectionnée")
            return
        
        selected_vms = [self.vm_tree.item(item)['values'][0] for item in selected_items]
        backup_type = self.backup_type.get()
        
        self.log_output(f"Début de la sauvegarde {'complète' if backup_type == 'full' else 'incrémentielle'} pour les VMs: {', '.join(selected_vms)}")
        
        # Démarrer la sauvegarde dans un thread séparé pour ne pas bloquer l'interface
        import threading
        threading.Thread(target=self.perform_backup, args=(selected_vms, backup_type), daemon=True).start()
    
    def perform_backup(self, vm_names, backup_type):
        temp_dir = "/tmp/kvm_backup"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            conn = libvirt.open('qemu:///system')
            if conn is None:
                self.log_output("Échec de la connexion à l'hyperviseur KVM")
                return
            
            for vm_name in vm_names:
                try:
                    domain = conn.lookupByName(vm_name)
                    if domain is None:
                        self.log_output(f"VM {vm_name} non trouvée")
                        continue
                    
                    # Sauvegarde de la configuration XML
                    xml_config = domain.XMLDesc(0)
                    xml_file = os.path.join(temp_dir, f"{vm_name}.xml")
                    with open(xml_file, 'w') as f:
                        f.write(xml_config)
                    
                    # Obtenir les disques de la VM via l'analyse XML
                    disks = self.get_vm_disks(xml_config)
                    self.logger.info(f"Disques trouvés pour {vm_name}: {disks}")
                    
                    # Sauvegarder chaque disque
                    for disk_path in disks:
                        if not os.path.exists(disk_path):
                            self.log_output(f"Disque {disk_path} non trouvé pour {vm_name}")
                            continue
                        
                        disk_name = os.path.basename(disk_path)
                        backup_file = os.path.join(temp_dir, f"{vm_name}_{disk_name}")
                        
                        if backup_type == "full":
                            subprocess.run(["qemu-img", "convert", "-O", "qcow2", disk_path, backup_file], check=True)
                        else:
                            snapshot_file = os.path.join(temp_dir, f"{vm_name}_snapshot.qcow2")
                            subprocess.run(["qemu-img", "create", "-f", "qcow2", "-b", disk_path, snapshot_file], check=True)
                            subprocess.run(["qemu-img", "convert", "-O", "qcow2", snapshot_file, backup_file], check=True)
                            os.remove(snapshot_file)
                    
                    # Créer une archive
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    archive_name = f"{vm_name}_{timestamp}.{backup_type}.tar.gz"
                    archive_path = os.path.join(temp_dir, archive_name)
                    
                    with tarfile.open(archive_path, "w:gz") as tar:
                        tar.add(xml_file, arcname=f"{vm_name}.xml")
                        for file in os.listdir(temp_dir):
                            if file.startswith(f"{vm_name}_") and file.endswith(".qcow2"):
                                tar.add(os.path.join(temp_dir, file), arcname=file)
                    
                    # Transférer vers le serveur de backup
                    self.transfer_to_backup(vm_name, archive_path)
                    
                    # Calculer et sauvegarder le checksum
                    checksum = self.calculate_file_checksum(archive_path)
                    checksum_file = f"{archive_path}.sha256"
                    with open(checksum_file, 'w') as f:
                        f.write(f"{checksum}  {os.path.basename(archive_path)}\n")
                    self.transfer_to_backup(vm_name, checksum_file)
                    
                    self.log_output(f"Sauvegarde de {vm_name} terminée avec succès (SHA256: {checksum[:16]}...)")
                    self.logger.info(f"Sauvegarde de {vm_name} terminée avec checksum: {checksum}")
                
                except Exception as e:
                    self.log_output(f"Erreur lors de la sauvegarde de {vm_name}: {str(e)}")
                    self.logger.error(f"Erreur lors de la sauvegarde de {vm_name}: {str(e)}")
            
            conn.close()
        
        except Exception as e:
            self.log_output(f"Erreur générale lors de la sauvegarde: {str(e)}")
            self.logger.error(f"Erreur générale lors de la sauvegarde: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def calculate_file_checksum(self, file_path):
        """Calculer le checksum SHA256 d'un fichier"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul du checksum pour {file_path}: {str(e)}")
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul du checksum pour {file_path}: {str(e)}")
            return None
    
    def create_ssh_connection(self, max_retries=3):
        """Créer une connexion SSH sécurisée avec retry et authentification par mot de passe"""
        import time
        
        # Demander le mot de passe si pas encore saisi
        if not self.ssh_password:
            password_dialog = PasswordDialog(self.root)
            self.root.wait_window(password_dialog.dialog)
            if password_dialog.password:
                self.ssh_password = password_dialog.password
            else:
                raise Exception("Mot de passe SSH requis")
        
        for attempt in range(max_retries):
            try:
                ssh = paramiko.SSHClient()
                
                # Configuration pour accepter les clés inconnues en dev
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connexion avec mot de passe et timeout
                ssh.connect(
                    hostname=self.config["backup_host"],
                    username=self.config["backup_user"],
                    password=self.ssh_password,
                    timeout=30,
                    auth_timeout=30,
                    banner_timeout=30
                )
                
                self.logger.info(f"Connexion SSH établie vers {self.config['backup_host']}")
                return ssh
                
            except paramiko.AuthenticationException:
                self.logger.error("Échec d'authentification SSH - Mot de passe incorrect")
                self.ssh_password = None  # Réinitialiser pour redemander
                raise Exception("Mot de passe SSH incorrect")
                
            except Exception as e:
                self.logger.warning(f"Tentative {attempt + 1}/{max_retries} échouée: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Backoff exponentiel
                else:
                    raise e
    
    def transfer_to_backup(self, vm_name, local_path):
        """Transférer un fichier vers le serveur de backup avec gestion d'erreurs"""
        try:
            ssh = self.create_ssh_connection()
            sftp = ssh.open_sftp()
            
            remote_vm_dir = f"{self.config['backup_path']}/{vm_name}"
            try:
                sftp.mkdir(remote_vm_dir)
            except IOError:
                pass  # Le répertoire existe déjà
            
            remote_path = f"{remote_vm_dir}/{os.path.basename(local_path)}"
            sftp.put(local_path, remote_path)
            
            sftp.close()
            ssh.close()
            
            self.log_output(f"Fichier transféré vers {remote_path}")
            self.logger.info(f"Transfert réussi: {local_path} -> {remote_path}")
        except Exception as e:
            self.log_output(f"Erreur lors du transfert: {str(e)}")
            self.logger.error(f"Erreur lors du transfert de {local_path}: {str(e)}")
            raise
    
    def restore_backup(self):
        selected_item = self.restore_tree.selection()
        if not selected_item:
            messagebox.showwarning("Avertissement", "Aucune sauvegarde sélectionnée")
            return
        
        item = self.restore_tree.item(selected_item)
        vm_name = item['values'][0]
        backup_date = item['values'][1]
        
        if not messagebox.askyesno("Confirmation", f"Voulez-vous vraiment restaurer {vm_name} (sauvegarde du {backup_date})?"):
            return
        
        self.log_output(f"Début de la restauration de {vm_name} (sauvegarde du {backup_date})")
        
        import threading
        threading.Thread(target=self.perform_restore, args=(vm_name, backup_date), daemon=True).start()
    
    def perform_restore(self, vm_name, backup_date):
        try:
            ssh = self.create_ssh_connection()
            
            sftp = ssh.open_sftp()
            backup_path = f"{self.config['backup_path']}/{vm_name}"
            
            date_str = datetime.strptime(backup_date, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d-%H%M%S")
            backup_file = None
            for file in sftp.listdir(backup_path):
                if date_str in file:
                    backup_file = file
                    break
            
            if backup_file is None:
                self.log_output("Fichier de sauvegarde non trouvé")
                return
            
            local_temp_dir = "/tmp/kvm_restore"
            os.makedirs(local_temp_dir, exist_ok=True)
            local_archive_path = os.path.join(local_temp_dir, backup_file)
            sftp.get(f"{backup_path}/{backup_file}", local_archive_path)
            
            sftp.close()
            ssh.close()
            
            # Extraire l'archive
            with tarfile.open(local_archive_path, "r:gz") as tar:
                tar.extractall(path=local_temp_dir)
            
            # Restaurer la configuration XML
            xml_file = os.path.join(local_temp_dir, f"{vm_name}.xml")
            if not os.path.exists(xml_file):
                self.log_output("Fichier de configuration XML non trouvé")
                return
            
            with open(xml_file, 'r') as f:
                xml_config = f.read()
            
            # Vérifier si la VM existe déjà
            conn = libvirt.open('qemu:///system')
            if conn is None:
                self.log_output("Échec de la connexion à l'hyperviseur KVM")
                return
            
            try:
                existing_vm = conn.lookupByName(vm_name)
                if existing_vm is not None:
                    if existing_vm.isActive():
                        existing_vm.destroy()
                    existing_vm.undefine()
            except libvirt.libvirtError:
                pass
            
            # Restaurer les disques
            disk_files = [f for f in os.listdir(local_temp_dir) if f.startswith(f"{vm_name}_") and f.endswith(".qcow2")]
            for disk_file in disk_files:
                disk_path = os.path.join("/var/lib/libvirt/images", disk_file)
                src_path = os.path.join(local_temp_dir, disk_file)
                
                shutil.copy2(src_path, disk_path)
                os.chmod(disk_path, 0o660)
                
                xml_config = xml_config.replace(os.path.basename(src_path), disk_file)
            
            # Recréer la VM
            conn.defineXML(xml_config)
            conn.close()
            
            self.log_output(f"Restauration de {vm_name} terminée avec succès")
            messagebox.showinfo("Succès", "Restauration terminée avec succès")
        
        except Exception as e:
            self.log_output(f"Erreur lors de la restauration: {str(e)}")
            messagebox.showerror("Erreur", f"Erreur lors de la restauration: {str(e)}")
        finally:
            shutil.rmtree(local_temp_dir, ignore_errors=True)
    
    def save_configuration(self):
        # Valider les entrées
        backup_host = self.backup_host.get().strip()
        backup_user = self.backup_user.get().strip()
        backup_path = self.backup_path.get().strip()
        backup_freq = self.backup_freq.get().strip()
        
        # Validation des champs
        errors = []
        if not InputValidator.validate_hostname(backup_host):
            errors.append("Nom d'hôte ou IP invalide")
        
        if not InputValidator.validate_username(backup_user):
            errors.append("Nom d'utilisateur invalide")
        
        if not InputValidator.validate_path(backup_path):
            errors.append("Chemin de sauvegarde invalide")
        
        if self.auto_backup.get() and not InputValidator.validate_cron_expression(backup_freq):
            errors.append("Expression cron invalide (format: minute heure jour mois jour_semaine)")
        
        if errors:
            error_msg = "Erreurs de validation:\n" + "\n".join(f"- {error}" for error in errors)
            messagebox.showerror("Erreurs de validation", error_msg)
            self.logger.error(f"Erreurs de validation: {errors}")
            return
        
        # Sauvegarder la configuration
        self.config["backup_host"] = backup_host
        self.config["backup_user"] = backup_user
        self.config["backup_path"] = backup_path
        self.config["auto_backup"] = self.auto_backup.get()
        self.config["backup_freq"] = backup_freq
        
        # Capturer le mot de passe SSH s'il est saisi
        if self.ssh_password_entry.get():
            self.ssh_password = self.ssh_password_entry.get()
        
        self.save_config()
        self.logger.info("Configuration sauvegardée avec succès")
        
        if self.config["auto_backup"]:
            self.setup_cron_job()
        
        self.log_output("Configuration enregistrée")
        messagebox.showinfo("Succès", "Configuration enregistrée avec succès")
    
    def test_ssh_connection(self):
        """Tester la connexion SSH avec les paramètres actuels"""
        # Valider les champs obligatoires
        backup_host = self.backup_host.get().strip()
        backup_user = self.backup_user.get().strip()
        
        if not backup_host:
            messagebox.showerror("Erreur", "Veuillez saisir l'adresse du serveur de backup")
            return
        
        if not backup_user:
            messagebox.showerror("Erreur", "Veuillez saisir le nom d'utilisateur")
            return
        
        # Sauvegarder temporairement la config pour le test
        old_config = self.config.copy()
        self.config["backup_host"] = backup_host
        self.config["backup_user"] = backup_user
        
        try:
            self.log_output("Test de connexion SSH en cours...")
            ssh = self.create_ssh_connection()
            
            # Test simple : lister le répertoire home
            stdin, stdout, stderr = ssh.exec_command('pwd')
            result = stdout.read().decode().strip()
            
            ssh.close()
            
            self.log_output(f"✓ Connexion SSH réussie ! Répertoire: {result}")
            messagebox.showinfo("Succès", f"Connexion SSH établie avec succès !\nRépertoire distant: {result}")
            
        except Exception as e:
            error_msg = str(e)
            self.log_output(f"✗ Échec de la connexion SSH: {error_msg}")
            messagebox.showerror("Erreur de connexion", f"Impossible de se connecter au serveur SSH:\n{error_msg}")
            
        finally:
            # Restaurer l'ancienne config
            self.config = old_config
    
    def setup_cron_job(self):
        try:
            cron = CronTab(user=True)
            cron.remove_all(comment="kvm_backup")
            
            job = cron.new(command=f"python3 {os.path.abspath(__file__)} --auto", comment="kvm_backup")
            job.setall(self.config["backup_freq"])
            
            cron.write()
            self.log_output(f"Tâche cron configurée: {self.config['backup_freq']}")
        except Exception as e:
            self.log_output(f"Erreur lors de la configuration cron: {str(e)}")
    
    def log_output(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.output_text.insert('end', f"[{timestamp}] {message}\n")
        self.output_text.see('end')
        self.output_text.update_idletasks()

def main():
    """Point d'entrée principal avec support CLI"""
    parser = argparse.ArgumentParser(description='KVM Backup Tool')
    parser.add_argument('--auto', action='store_true', 
                        help='Mode automatique (sans GUI)')
    parser.add_argument('--config', type=str, 
                        help='Chemin vers le fichier de configuration')
    parser.add_argument('--list-vms', action='store_true',
                        help='Lister les VMs disponibles')
    
    args = parser.parse_args()
    
    if args.auto:
        # Mode automatique sans GUI
        from pathlib import Path
        
        config_file = args.config or os.path.expanduser("~/.kvm_backup_config.json")
        
        if not Path(config_file).exists():
            print(f"Erreur: Fichier de configuration non trouvé: {config_file}")
            sys.exit(1)
        
        # Créer une instance sans GUI pour la sauvegarde automatique
        backup_engine = KVMBackupEngine(config_file)
        backup_engine.run_auto_backup()
    
    elif args.list_vms:
        # Lister les VMs
        try:
            conn = libvirt.open('qemu:///system')
            if conn is None:
                print("Erreur: Impossible de se connecter à l'hyperviseur KVM")
                sys.exit(1)
            
            domains = conn.listAllDomains(0)
            print("VMs disponibles:")
            for domain in domains:
                status = "En cours" if domain.isActive() else "Arrêtée"
                print(f"  - {domain.name()} ({status})")
            
            conn.close()
        except Exception as e:
            print(f"Erreur: {str(e)}")
            sys.exit(1)
    
    else:
        # Mode GUI par défaut
        root = tk.Tk()
        app = KVMBackupGUI(root)
        root.mainloop()

class KVMBackupEngine:
    """Moteur de sauvegarde sans interface graphique pour l'automatisation"""
    
    def __init__(self, config_file):
        self.config_file = config_file
        self.logger = Logger()
        self.load_config()
    
    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.error(f"Erreur lors du chargement de la configuration: {str(e)}")
            raise
    
    def run_auto_backup(self):
        """Exécuter la sauvegarde automatique"""
        self.logger.info("Démarrage de la sauvegarde automatique")
        
        try:
            # Récupérer les VMs sélectionnées
            selected_vms = [vm for vm, selected in self.config.get("selected_vms", {}).items() if selected]
            
            if not selected_vms:
                self.logger.warning("Aucune VM sélectionnée pour la sauvegarde automatique")
                return
            
            # Exécuter la sauvegarde directement sans GUI
            self.perform_backup_headless(selected_vms, "full")
            
            self.logger.info("Sauvegarde automatique terminée")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde automatique: {str(e)}")
    
    def perform_backup_headless(self, vm_names, backup_type):
        """Effectuer une sauvegarde sans interface graphique"""
        temp_dir = "/tmp/kvm_backup"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            import libvirt
            import subprocess
            import tarfile
            import xml.etree.ElementTree as ET
            
            conn = libvirt.open('qemu:///system')
            if conn is None:
                self.logger.error("Échec de la connexion à l'hyperviseur KVM")
                return
            
            for vm_name in vm_names:
                try:
                    domain = conn.lookupByName(vm_name)
                    if domain is None:
                        self.logger.warning(f"VM {vm_name} non trouvée")
                        continue
                    
                    # Sauvegarde de la configuration XML
                    xml_config = domain.XMLDesc(0)
                    xml_file = os.path.join(temp_dir, f"{vm_name}.xml")
                    with open(xml_file, 'w') as f:
                        f.write(xml_config)
                    
                    # Obtenir les disques de la VM via l'analyse XML
                    disks = self.get_vm_disks_headless(xml_config)
                    self.logger.info(f"Disques trouvés pour {vm_name}: {disks}")
                    
                    # Sauvegarder chaque disque
                    for disk_path in disks:
                        if not os.path.exists(disk_path):
                            self.logger.warning(f"Disque {disk_path} non trouvé pour {vm_name}")
                            continue
                        
                        disk_name = os.path.basename(disk_path)
                        backup_file = os.path.join(temp_dir, f"{vm_name}_{disk_name}")
                        
                        if backup_type == "full":
                            subprocess.run(["qemu-img", "convert", "-O", "qcow2", disk_path, backup_file], check=True)
                        else:
                            snapshot_file = os.path.join(temp_dir, f"{vm_name}_snapshot.qcow2")
                            subprocess.run(["qemu-img", "create", "-f", "qcow2", "-b", disk_path, snapshot_file], check=True)
                            subprocess.run(["qemu-img", "convert", "-O", "qcow2", snapshot_file, backup_file], check=True)
                            os.remove(snapshot_file)
                    
                    # Créer une archive
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    archive_name = f"{vm_name}_{timestamp}.{backup_type}.tar.gz"
                    archive_path = os.path.join(temp_dir, archive_name)
                    
                    with tarfile.open(archive_path, "w:gz") as tar:
                        tar.add(xml_file, arcname=f"{vm_name}.xml")
                        for file in os.listdir(temp_dir):
                            if file.startswith(f"{vm_name}_") and file.endswith(".qcow2"):
                                tar.add(os.path.join(temp_dir, file), arcname=file)
                    
                    # Calculer le checksum
                    checksum = self.calculate_file_checksum_headless(archive_path)
                    checksum_file = f"{archive_path}.sha256"
                    with open(checksum_file, 'w') as f:
                        f.write(f"{checksum}  {os.path.basename(archive_path)}\n")
                    
                    self.logger.info(f"Sauvegarde de {vm_name} terminée (taille: {os.path.getsize(archive_path)} bytes)")
                    self.logger.info(f"Checksum SHA256: {checksum}")
                    
                except Exception as e:
                    self.logger.error(f"Erreur lors de la sauvegarde de {vm_name}: {str(e)}")
            
            conn.close()
        
        except Exception as e:
            self.logger.error(f"Erreur générale lors de la sauvegarde: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def get_vm_disks_headless(self, xml_config):
        """Extraire les chemins des disques depuis la configuration XML (version headless)"""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_config)
            disks = []
            
            # Rechercher tous les éléments disk
            for disk in root.findall(".//disk[@type='file']"):
                source = disk.find("source")
                if source is not None and source.get("file"):
                    disk_path = source.get("file")
                    if os.path.exists(disk_path):
                        disks.append(disk_path)
                    else:
                        self.logger.warning(f"Disque non trouvé: {disk_path}")
            
            return disks
        except ET.ParseError as e:
            self.logger.error(f"Erreur lors de l'analyse XML: {str(e)}")
            return []
    
    def calculate_file_checksum_headless(self, file_path):
        """Calculer le checksum SHA256 d'un fichier (version headless)"""
        import hashlib
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.error(f"Erreur lors du calcul du checksum pour {file_path}: {str(e)}")
            return None

if __name__ == "__main__":
    main()
