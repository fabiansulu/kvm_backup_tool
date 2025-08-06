# Changelog - KVM Backup Tool

## Version 2.0 - 6 août 2025

### ✨ Nouvelles fonctionnalités
- **Onglet "À propos"** : Informations sur le développeur et l'application
  - Crédit développeur : authentik
  - Lien cliquable vers https://fabiansulu.com
  - Informations techniques et version
  - Design professionnel avec sections organisées

### 🔧 Améliorations techniques précédentes
- **Mode headless** : Sauvegarde automatique sans interface graphique
- **Authentification SSH** : Support mot de passe avec dialogue sécurisé
- **Validation robuste** : Contrôle des IP, noms d'hôte et expressions cron
- **Interface restauration** : Bouton actualisation et chargement automatique
- **Logging professionnel** : Rotation des logs et gestion d'erreurs
- **Support CLI** : Arguments `--auto`, `--list-vms`, `--config`

### 🛠️ Corrections
- Validation IP/hostname simplifiée et plus fiable
- Expression cron avec support `*/X` pour intervalles
- Gestion d'erreurs silencieuse au démarrage
- Retry logic pour connexions SSH

### 📋 Interface utilisateur
- **4 onglets** : Sauvegarde, Restauration, Configuration, À propos
- **Design moderne** : Utilisation de ttk.LabelFrame et organisation claire
- **Liens interactifs** : Lien vers le site du développeur cliquable
- **Messages informatifs** : Feedback utilisateur amélioré

### 🔒 Sécurité
- Authentification SSH par mot de passe
- Validation stricte des entrées utilisateur
- Checksums SHA256 pour l'intégrité des données
- Logs sécurisés avec rotation automatique

### 🚀 Production Ready
- Configuration persistante via JSON
- Intégration cron pour automatisation
- Gestion d'erreurs robuste
- Mode CLI pour scripts et automation

---
**Développé par** : authentik  
**Site web** : https://fabiansulu.com  
**Licence** : © 2025 - Tous droits réservés
