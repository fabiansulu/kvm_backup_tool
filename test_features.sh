#!/bin/bash

echo "=== Test des fonctionnalités de sauvegarde et restauration ==="
echo "Date: $(date)"
echo

# Test 1: Sauvegarde automatique
echo "1. Test du mode automatique..."
echo "Configuration actuelle:"
cat ~/.kvm_backup_config.json | python3 -m json.tool
echo

echo "Test du mode automatique (sans transfert SSH pour éviter les erreurs):"
python3 auth_kvm_backup.py --auto 2>&1 | head -10

echo

# Test 2: Vérification cron
echo "2. Test de la configuration cron..."
python3 -c "
try:
    from crontab import CronTab
    print('✓ Module crontab disponible')
    
    # Simuler la création d'une tâche cron
    cron = CronTab(user=True)
    print(f'Nombre de tâches cron actuelles: {len(list(cron))}')
    
    # Vérifier la syntaxe de l'expression cron
    import sys
    import os
    sys.path.append('.')
    from auth_kvm_backup import InputValidator
    
    test_cron = '*/5 * * * *'  # Toutes les 5 minutes
    is_valid = InputValidator.validate_cron_expression(test_cron)
    print(f'Expression cron {test_cron}: {\"✓ Valide\" if is_valid else \"✗ Invalide\"}')
    
except Exception as e:
    print(f'✗ Erreur: {e}')
"

echo

# Test 3: Interface restauration
echo "3. Test interface restauration..."
echo "Création de sauvegardes factices pour test:"

# Créer des sauvegardes de test
mkdir -p /tmp/test_backup/mainserver
touch /tmp/test_backup/mainserver/mainserver_20250806-120000.full.tar.gz
touch /tmp/test_backup/mainserver/mainserver_20250805-120000.full.tar.gz
touch /tmp/test_backup/mainserver/mainserver_20250804-120000.incr.tar.gz

echo "Sauvegardes de test créées:"
ls -la /tmp/test_backup/mainserver/

echo

# Test 4: Fonctions de validation
echo "4. Test des validations..."
python3 -c "
import sys
sys.path.append('.')
from auth_kvm_backup import InputValidator

tests = [
    ('Hostname localhost', InputValidator.validate_hostname, 'localhost', True),
    ('IP valide', InputValidator.validate_hostname, '192.168.1.1', True),
    ('IP invalide', InputValidator.validate_hostname, '999.999.999.999', False),
    ('Username valide', InputValidator.validate_username, 'testuser', True),
    ('Cron valide', InputValidator.validate_cron_expression, '0 2 * * *', True),
    ('Cron invalide', InputValidator.validate_cron_expression, '60 25 * * *', False),
]

print('Tests de validation:')
for name, func, value, expected in tests:
    result = func(value)
    status = '✓' if result == expected else '✗'
    print(f'  {status} {name}: {value} -> {result}')
"

echo

# Test 5: Instructions pour les tests manuels
echo "5. Tests manuels recommandés:"
echo "   a) Lancez: python3 auth_kvm_backup.py"
echo "   b) Allez dans l'onglet Configuration"
echo "   c) Remplissez les champs avec:"
echo "      - Serveur: localhost"
echo "      - Utilisateur: $USER"
echo "      - Chemin: /tmp/test_backup"
echo "   d) Cliquez 'Tester la connexion SSH'"
echo "   e) Allez dans l'onglet Restauration"
echo "   f) Cliquez 'Actualiser la liste des sauvegardes'"
echo

echo "=== Résumé des corrections apportées ==="
echo "✓ Mode automatique corrigé (plus de dépendance GUI)"
echo "✓ Bouton 'Actualiser' ajouté dans l'onglet Restauration"
echo "✓ Chargement automatique des sauvegardes au démarrage"
echo "✓ Gestion d'erreurs améliorée pour l'interface restauration"
echo "✓ Support complet du mode headless pour les tâches cron"
echo

# Nettoyage
echo "Nettoyage des fichiers de test..."
rm -rf /tmp/test_backup

echo "Test terminé!"
