import json

def update_locales():
    with open('app/admin/locales/en.json', 'r', encoding='utf-8') as f:
        en = json.load(f)
    with open('app/admin/locales/fr.json', 'r', encoding='utf-8') as f:
        fr = json.load(f)

    en['users'] = {
        'page_title': 'Administrators — BARROW.AI',
        'header_title': 'Administrators',
        'breadcrumb_users': 'Users',
        'card_title': 'Administrator Accounts',
        'loading': 'Loading...',
        'search_placeholder': 'Search by email or name...',
        'role_all': 'All roles',
        'role_superadmin': 'Superadmin',
        'role_admin': 'Admin',
        'role_auditor': 'Auditor',
        'role_viewer': 'Viewer',
        'add_btn': 'Add',
        'th_user': 'User',
        'th_role': 'Role',
        'th_2fa': '2FA',
        'th_status': 'Status',
        'th_created': 'Created at',
        'th_actions': 'Actions',
        'modal_title': 'Confirm deletion',
        'modal_body': 'You are about to deactivate the administrator',
        'modal_warning': 'This action is reversible.',
        'btn_cancel': 'Cancel',
        'btn_deactivate': 'Deactivate',
        'js': {
            'accounts': 'account(s)',
            'no_users': 'No administrator found',
            'active': 'Active',
            'inactive': 'Inactive',
            'enabled': 'Enabled',
            'disabled': 'Disabled',
            'edit': 'Edit',
            'deactivate': 'Deactivate',
            'success_deactivate': 'Administrator deactivated'
        }
    }

    fr['users'] = {
        'page_title': 'Administrateurs — BARROW.AI',
        'header_title': 'Administrateurs',
        'breadcrumb_users': 'Utilisateurs',
        'card_title': 'Comptes administrateurs',
        'loading': 'Chargement…',
        'search_placeholder': 'Rechercher par email ou nom…',
        'role_all': 'Tous les rôles',
        'role_superadmin': 'Superadmin',
        'role_admin': 'Admin',
        'role_auditor': 'Auditeur',
        'role_viewer': 'Viewer',
        'add_btn': 'Ajouter',
        'th_user': 'Utilisateur',
        'th_role': 'Rôle',
        'th_2fa': '2FA',
        'th_status': 'Statut',
        'th_created': 'Créé le',
        'th_actions': 'Actions',
        'modal_title': 'Confirmer la suppression',
        'modal_body': "Vous êtes sur le point de désactiver l'administrateur",
        'modal_warning': 'Cette action est réversible.',
        'btn_cancel': 'Annuler',
        'btn_deactivate': 'Désactiver',
        'js': {
            'accounts': 'compte',
            'no_users': 'Aucun administrateur trouvé',
            'active': 'Actif',
            'inactive': 'Inactif',
            'enabled': 'Activé',
            'disabled': 'Désactivé',
            'edit': 'Modifier',
            'deactivate': 'Désactiver',
            'success_deactivate': 'Administrateur désactivé'
        }
    }

    with open('app/admin/locales/en.json', 'w', encoding='utf-8') as f:
        json.dump(en, f, indent=2, ensure_ascii=False)
    with open('app/admin/locales/fr.json', 'w', encoding='utf-8') as f:
        json.dump(fr, f, indent=2, ensure_ascii=False)

def patch_users():
    with open('app/admin/templates/users/list.html', 'r', encoding='utf-8') as f:
        content = f.read()

    replacements = [
        ('Administrateurs — BARROW.AI', '{{ t.users.page_title }}'),
        ('{% block page_title %}Administrateurs{% endblock %}', '{% block page_title %}{{ t.users.header_title }}{% endblock %}'),
        ('<span>Utilisateurs</span>', '<span>{{ t.users.breadcrumb_users }}</span>'),
        ('<div class="card-title">Comptes administrateurs</div>', '<div class="card-title">{{ t.users.card_title }}</div>'),
        ('Chargement…', '{{ t.users.loading }}'),
        ('placeholder="Rechercher par email ou nom…"', 'placeholder="{{ t.users.search_placeholder }}"'),
        ('Tous les rôles', '{{ t.users.role_all }}'),
        ('>Superadmin<', '>{{ t.users.role_superadmin }}<'),
        ('>Admin<', '>{{ t.users.role_admin }}<'),
        ('>Auditeur<', '>{{ t.users.role_auditor }}<'),
        ('>Viewer<', '>{{ t.users.role_viewer }}<'),
        ('Ajouter\n', '{{ t.users.add_btn }}\n'),
        ('<th>Utilisateur</th>', '<th>{{ t.users.th_user }}</th>'),
        ('<th>Rôle</th>', '<th>{{ t.users.th_role }}</th>'),
        ('<th>2FA</th>', '<th>{{ t.users.th_2fa }}</th>'),
        ('<th>Statut</th>', '<th>{{ t.users.th_status }}</th>'),
        ('<th>Créé le</th>', '<th>{{ t.users.th_created }}</th>'),
        ('<th>Actions</th>', '<th>{{ t.users.th_actions }}</th>'),
        ('Confirmer la suppression', '{{ t.users.modal_title }}'),
        ('Vous êtes sur le point de désactiver l\'administrateur', '{{ t.users.modal_body }}'),
        ('Cette action est réversible.', '{{ t.users.modal_warning }}'),
        ('>Annuler<', '>{{ t.users.btn_cancel }}<'),
        (' Désactiver<', ' {{ t.users.btn_deactivate }}<'),
        ("`${data.total} compte${data.total !== 1 ? 's' : ''}`", "`${data.total} ${data.total !== 1 ? '{{ t.users.js.accounts }}s' : '{{ t.users.js.accounts }}'}`"),
        ('Aucun administrateur trouvé', '{{ t.users.js.no_users }}'),
        (">Activé<", ">{{ t.users.js.enabled }}<"),
        (">Désactivé<", ">{{ t.users.js.disabled }}<"),
        (">Actif<", ">{{ t.users.js.active }}<"),
        (">Inactif<", ">{{ t.users.js.inactive }}<"),
        ("title=\"Modifier\"", "title=\"{{ t.users.js.edit }}\""),
        ("title=\"Désactiver\"", "title=\"{{ t.users.js.deactivate }}\""),
        ("Administrateur désactivé", "{{ t.users.js.success_deactivate }}")
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    with open('app/admin/templates/users/list.html', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    update_locales()
    patch_users()
    print('Users patched successfully.')
