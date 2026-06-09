import json

def update_locales():
    with open('app/admin/locales/en.json', 'r', encoding='utf-8') as f:
        en = json.load(f)
    with open('app/admin/locales/fr.json', 'r', encoding='utf-8') as f:
        fr = json.load(f)

    en['dashboard'] = {
        'page_title': 'Dashboard — BARROW.AI',
        'header_title': 'Dashboard',
        'kpi_conversations': 'Conversations (7d)',
        'kpi_voice': 'Voice Success Rate',
        'kpi_docs': 'Indexed Documents',
        'kpi_latency': 'p95 Latency',
        'chart_messages_title': 'Messages per Day',
        'chart_7d': '7 days',
        'chart_30d': '30 days',
        'chart_latency_title': 'Latency per Component',
        'recent_conv_title': 'Recent Conversations',
        'see_all': 'See All',
        'th_message': 'Message',
        'th_confidence': 'Confidence',
        'th_date': 'Date',
        'quick_links_title': 'Quick Access',
        'ql_import': 'Import Document',
        'ql_add_admin': 'Add Admin',
        'ql_audit': 'Audit Logs',
        'ql_conversations': 'Conversations',
        'health_title': 'System Health',
        'js': {
            'unavailable': 'Unavailable',
            'no_conversations': 'No conversations',
            'healthy': 'Healthy',
            'degraded': 'Degraded',
            'error': 'Error',
            'health_error': 'Unable to reach health service',
            'verifying': 'Verifying...'
        }
    }

    fr['dashboard'] = {
        'page_title': 'Tableau de bord — BARROW.AI',
        'header_title': 'Tableau de bord',
        'kpi_conversations': 'Conversations (7j)',
        'kpi_voice': 'Taux vocal réussi',
        'kpi_docs': 'Documents indexés',
        'kpi_latency': 'Latence p95',
        'chart_messages_title': 'Messages par jour',
        'chart_7d': '7 jours',
        'chart_30d': '30 jours',
        'chart_latency_title': 'Latence par composant',
        'recent_conv_title': 'Conversations récentes',
        'see_all': 'Voir tout',
        'th_message': 'Message',
        'th_confidence': 'Confiance',
        'th_date': 'Date',
        'quick_links_title': 'Accès rapide',
        'ql_import': 'Importer document',
        'ql_add_admin': 'Ajouter admin',
        'ql_audit': 'Audit logs',
        'ql_conversations': 'Conversations',
        'health_title': 'Santé du système',
        'js': {
            'unavailable': 'Indisponible',
            'no_conversations': 'Aucune conversation',
            'healthy': 'Sain',
            'degraded': 'Dégradé',
            'error': 'Erreur',
            'health_error': 'Impossible de joindre le service de santé',
            'verifying': 'Vérification…'
        }
    }

    with open('app/admin/locales/en.json', 'w', encoding='utf-8') as f:
        json.dump(en, f, indent=2, ensure_ascii=False)
    with open('app/admin/locales/fr.json', 'w', encoding='utf-8') as f:
        json.dump(fr, f, indent=2, ensure_ascii=False)

def patch_dashboard():
    with open('app/admin/templates/dashboard/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    replacements = [
        ('Tableau de bord — BARROW.AI', '{{ t.dashboard.page_title }}'),
        ('{% block page_title %}Tableau de bord{% endblock %}', '{% block page_title %}{{ t.dashboard.header_title }}{% endblock %}'),
        ('<div class="stat-label">Conversations (7j)</div>', '<div class="stat-label">{{ t.dashboard.kpi_conversations }}</div>'),
        ('<div class="stat-label">Taux vocal réussi</div>', '<div class="stat-label">{{ t.dashboard.kpi_voice }}</div>'),
        ('<div class="stat-label">Documents indexés</div>', '<div class="stat-label">{{ t.dashboard.kpi_docs }}</div>'),
        ('<div class="stat-label">Latence p95</div>', '<div class="stat-label">{{ t.dashboard.kpi_latency }}</div>'),
        ('<div class="card-title">Messages par jour</div>', '<div class="card-title">{{ t.dashboard.chart_messages_title }}</div>'),
        ('>7 jours<', '>{{ t.dashboard.chart_7d }}<'),
        ('>30 jours<', '>{{ t.dashboard.chart_30d }}<'),
        ('<div class="card-title">Latence par composant</div>', '<div class="card-title">{{ t.dashboard.chart_latency_title }}</div>'),
        ('<div class="card-title">Conversations récentes</div>', '<div class="card-title">{{ t.dashboard.recent_conv_title }}</div>'),
        ('>Voir tout<', '>{{ t.dashboard.see_all }}<'),
        ('<th>Message</th>', '<th>{{ t.dashboard.th_message }}</th>'),
        ('<th>Confiance</th>', '<th>{{ t.dashboard.th_confidence }}</th>'),
        ('<th>Date</th>', '<th>{{ t.dashboard.th_date }}</th>'),
        ('<div class="card-title">Accès rapide</div>', '<div class="card-title">{{ t.dashboard.quick_links_title }}</div>'),
        ('<span>Importer document</span>', '<span>{{ t.dashboard.ql_import }}</span>'),
        ('<span>Ajouter admin</span>', '<span>{{ t.dashboard.ql_add_admin }}</span>'),
        ('<span>Audit logs</span>', '<span>{{ t.dashboard.ql_audit }}</span>'),
        ('<span>Conversations</span>', '<span>{{ t.dashboard.ql_conversations }}</span>'),
        ('<div class="card-title">Santé du système</div>', '<div class="card-title">{{ t.dashboard.health_title }}</div>'),
        ('>Vérification…<', '>{{ t.dashboard.js.verifying }}<'),
        ("'Indisponible'", "'{{ t.dashboard.js.unavailable }}'"),
        ("'Aucune conversation'", "'{{ t.dashboard.js.no_conversations }}'"),
        ("'Sain'", "'{{ t.dashboard.js.healthy }}'"),
        ("'Dégradé'", "'{{ t.dashboard.js.degraded }}'"),
        ("'Erreur'", "'{{ t.dashboard.js.error }}'"),
        ("'Impossible de joindre le service de santé'", "'{{ t.dashboard.js.health_error }}'")
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    with open('app/admin/templates/dashboard/index.html', 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    update_locales()
    patch_dashboard()
    print('Dashboard patched successfully.')
