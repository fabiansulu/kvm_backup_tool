# KVM Backup Tool - Version Production

## Vue d'ensemble
Outil de sauvegarde et restauration pour machines virtuelles KVM avec interface graphique et mode CLI, conçu pour un usage en production.

## Améliorations apportées (Version Production)

### 🔒 Sécurité
- **Validation robuste des entrées** : Validation regex pour hostnames, usernames, chemins et expressions cron
- **Authentification SSH sécurisée** : Support authentification par mot de passe avec dialogue sécurisé
- **Gestion SSH robuste** : Utilisation d'`AutoAddPolicy`, timeout configurables, test de connexion intégré
- **Retry automatique** : Reconnexion automatique avec backoff exponentiel en cas d'échec réseau

### 📊 Robustesse et Monitoring
- **Logging professionnel** : Utilisation du module `logging` avec rotation automatique des fichiers
- **Checksums SHA256** : Vérification de l'intégrité des sauvegardes
- **Gestion d'erreurs complète** : Traitement détaillé des exceptions à tous les niveaux
- **Extraction correcte des disques VM** : Analyse XML au lieu de l'API défaillante

### 🔧 Fonctionnalités avancées
- **Interface CLI** : Mode automatique pour scripts et cron
- **Architecture modulaire** : Séparation des responsabilités (GUI, Engine, Validation, Logging)
- **Support multi-environnement** : Détection automatique des permissions et fallback

## Installation

### Prérequis
```bash
# Dépendances système
sudo apt-get install python3 python3-pip libvirt-dev

# Modules Python
pip3 install tkinter libvirt-python paramiko python-crontab
```

### Configuration
1. Copiez le fichier de configuration exemple :
   ```bash
   cp example_config.json ~/.kvm_backup_config.json
   ```

2. Éditez la configuration :
   ```json
   {
       "backup_host": "votre-serveur-backup.com",
       "backup_user": "votre-utilisateur",
       "backup_path": "/backup/kvm",
       "auto_backup": true,
       "backup_freq": "0 2 * * *",
       "selected_vms": {
           "vm1": true,
           "vm2": false
       }
   }
   ```

3. **Authentification SSH** :
   - L'application utilise l'authentification par **mot de passe**
   - Le mot de passe est demandé via un dialogue sécurisé lors de la première connexion
   - Testez votre connexion via l'onglet Configuration → "Tester la connexion SSH"

## Utilisation

### Mode GUI (Interface graphique)
```bash
python3 auth_kvm_backup.py
```

### Mode CLI (Automatisation)
```bash
# Lister les VMs disponibles
python3 auth_kvm_backup.py --list-vms

# Sauvegarde automatique
python3 auth_kvm_backup.py --auto

# Avec fichier de configuration personnalisé
python3 auth_kvm_backup.py --auto --config /path/to/config.json
```

### Planification automatique
La tâche cron est configurée automatiquement via l'interface. Vérification manuelle :
```bash
crontab -l | grep kvm_backup
```

## Validation et Tests

### Test complet
```bash
./test_improvements.sh
```

### Tests individuels
```bash
# Validation syntaxe
python3 -m py_compile auth_kvm_backup.py

# Test validation entrées
python3 -c "from auth_kvm_backup import InputValidator; print(InputValidator.validate_hostname('192.168.1.1'))"

# Test CLI
python3 auth_kvm_backup.py --help
```

## Architecture

### Classes principales
- **`InputValidator`** : Validation des entrées utilisateur
- **`Logger`** : Gestion du logging professionnel
- **`KVMBackupGUI`** : Interface graphique
- **`KVMBackupEngine`** : Moteur de sauvegarde sans GUI

### Flux de sauvegarde
1. Validation de la configuration
2. Connexion sécurisée à libvirt
3. Extraction des disques via analyse XML
4. Création des sauvegardes (complètes/incrémentielle)
5. Calcul des checksums SHA256
6. Transfert sécurisé vers serveur de backup
7. Nettoyage des fichiers temporaires

## Logs et Monitoring

### Emplacements des logs
- Principal : `/var/log/kvm_backup.log` (si permissions)
- Fallback : `~/kvm_backup.log`

### Format des logs
```
2025-08-06 14:30:15,123 - INFO - Démarrage de l'application KVM Backup
2025-08-06 14:30:16,456 - INFO - Connexion SSH établie vers backup.example.com
2025-08-06 14:30:45,789 - INFO - Sauvegarde de vm1 terminée avec checksum: a1b2c3...
```

## Sécurité

### Bonnes pratiques implémentées
- ✅ Validation de toutes les entrées utilisateur
- ✅ Authentification SSH par mot de passe sécurisée
- ✅ Test de connexion intégré dans l'interface
- ✅ Timeout sur toutes les connexions réseau
- ✅ Logging des accès et erreurs
- ✅ Nettoyage sécurisé des fichiers temporaires

### Recommandations additionnelles
- Configurer un utilisateur dédié pour les sauvegardes
- Restreindre les permissions SSH côté serveur
- Utiliser un VPN ou tunnel SSH pour les connexions distantes
- Mettre en place une surveillance des logs
- Tester régulièrement les restaurations

## Dépannage

### Problèmes courants

#### Échec de connexion libvirt
```bash
# Vérifier le service
sudo systemctl status libvirtd

# Permissions utilisateur
sudo usermod -a -G libvirt $USER
newgrp libvirt
```

#### Problèmes SSH
```bash
# Test de connectivité
ssh -v utilisateur@serveur-backup

# Vérifier les clés
ssh-keygen -l -f ~/.ssh/id_ed25519.pub
```

#### Erreurs de permissions
```bash
# Répertoire de logs
sudo mkdir -p /var/log
sudo chown $USER:$USER /var/log/kvm_backup.log

# Répertoires temporaires
sudo mkdir -p /tmp/kvm_backup
sudo chown $USER:$USER /tmp/kvm_backup
```

## Performance et Limites

### Recommandations production
- **Taille max par VM** : 500GB (ajustable)
- **Fréquence recommandée** : Quotidienne pour VMs critiques
- **Rétention** : 7 jours local, 30 jours distant
- **Bande passante** : Prévoir 10% de la taille totale des VMs

### Optimisations possibles
- Compression personnalisée des archives
- Transferts parallèles pour plusieurs VMs
- Déduplication côté serveur
- Intégration avec solutions de monitoring (Nagios, Zabbix)

## Contributions et Support

Ce code est maintenant prêt pour un usage en production avec toutes les améliorations de sécurité et robustesse nécessaires.

### Version
- **Version originale** : Prototype fonctionnel
- **Version actuelle** : 2.0 - Production Ready
- **Date de mise à jour** : Août 2025

### Auteur
Améliorations de production implementées par GitHub Copilot.
