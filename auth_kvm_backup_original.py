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

class KVMBackupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Sauvegarde KVM")
        self.root.geometry("900x700")
        
        # Configuration
        self.config_file = os.path.expanduser("~/.kvm_backup_config.json")
        self.load_config()
        
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
        # Treeview pour les sauvegardes disponibles
        self.restore_tree = ttk.Treeview(self.restore_tab, columns=('vm', 'date', 'type'), show='headings')
        self.restore_tree.heading('vm', text='Machine Virtuelle')
        self.restore_tree.heading('date', text='Date')
        self.restore_tree.heading('type', text='Type')
        self.restore_tree.column('vm', width=250)
        self.restore_tree.column('date', width=150)
        self.restore_tree.column('type', width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.restore_tab, orient='vertical', command=self.restore_tree.yview)
        self.restore_tree.configure(yscrollcommand=scrollbar.set)
        
        self.restore_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y')
        
        # Bouton de restauration
        ttk.Button(self.restore_tab, text="Restaurer la sauvegarde sélectionnée", 
                  command=self.restore_backup).pack(pady=10)
    
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
        
        # Sauvegarde automatique
        self.auto_backup = tk.BooleanVar(value=self.config.get("auto_backup", False))
        ttk.Checkbutton(self.config_tab, text="Sauvegarde automatique", variable=self.auto_backup).grid(row=3, column=0, columnspan=2, sticky='w', padx=5, pady=5)
        
        ttk.Label(self.config_tab, text="Fréquence (cron):").grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.backup_freq = ttk.Entry(self.config_tab)
        self.backup_freq.insert(0, self.config.get("backup_freq", "0 2 * * *"))
        self.backup_freq.grid(row=4, column=1, sticky='ew', padx=5, pady=5)
        
        # Bouton de sauvegarde de configuration
        ttk.Button(self.config_tab, text="Enregistrer la configuration", 
                  command=self.save_configuration).grid(row=5, column=0, columnspan=2, pady=10)
    
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
    
    def populate_restore_list(self):
        self.restore_tree.delete(*self.restore_tree.get_children())
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.config["backup_host"],
                username=self.config["backup_user"]
            )
            
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
                    
                    # Obtenir les disques de la VM
                    disks = []
                    for disk in domain.listAllDevices(0):
                        disks.append(disk.source())
                    
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
                    
                    self.log_output(f"Sauvegarde de {vm_name} terminée avec succès")
                
                except Exception as e:
                    self.log_output(f"Erreur lors de la sauvegarde de {vm_name}: {str(e)}")
            
            conn.close()
        
        except Exception as e:
            self.log_output(f"Erreur générale lors de la sauvegarde: {str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def transfer_to_backup(self, vm_name, local_path):
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.config["backup_host"],
                username=self.config["backup_user"]
            )
            
            sftp = ssh.open_sftp()
            
            remote_vm_dir = f"{self.config['backup_path']}/{vm_name}"
            try:
                sftp.mkdir(remote_vm_dir)
            except IOError:
                pass
            
            remote_path = f"{remote_vm_dir}/{os.path.basename(local_path)}"
            sftp.put(local_path, remote_path)
            
            sftp.close()
            ssh.close()
            
            self.log_output(f"Fichier transféré vers {remote_path}")
        except Exception as e:
            self.log_output(f"Erreur lors du transfert: {str(e)}")
    
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
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.config["backup_host"],
                username=self.config["backup_user"]
            )
            
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
        self.config["backup_host"] = self.backup_host.get()
        self.config["backup_user"] = self.backup_user.get()
        self.config["backup_path"] = self.backup_path.get()
        self.config["auto_backup"] = self.auto_backup.get()
        self.config["backup_freq"] = self.backup_freq.get()
        
        self.save_config()
        
        if self.config["auto_backup"]:
            self.setup_cron_job()
        
        self.log_output("Configuration enregistrée")
        messagebox.showinfo("Succès", "Configuration enregistrée avec succès")
    
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

if __name__ == "__main__":
    root = tk.Tk()
    app = KVMBackupGUI(root)
    root.mainloop()
