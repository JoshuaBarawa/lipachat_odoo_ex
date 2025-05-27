{
    'name': 'LipaChat WhatsApp Gateway',
    'version': '1.0.0',
    'category': 'Communication',
    'summary': 'Send WhatsApp messages through LipaChat Gateway',
    'description': '''
        LipaChat WhatsApp Gateway Integration
        ===================================
        
        This module integrates Odoo with LipaChat WhatsApp Gateway API to:
        * Send text messages
        * Send media messages (images, videos, documents)
        * Send interactive buttons
        * Send interactive lists
        * Create and manage message templates
        * Track message delivery status
        
        Features:
        ---------
        * Easy API key configuration
        * Contact integration with WhatsApp numbers
        * Message history tracking
        * Template management
        * Automated notifications
        
        Setup:
        ------
        1. Get your API key from https://app.lipachat.com/auth/signup
        2. Configure your API key in Settings > LipaChat Configuration
        3. Start sending WhatsApp messages from contacts, sales, or any module
    ''',
    'author': 'LipaChat Gateway',
    'website': 'https://lipachat.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/lipachat_data.xml',
        'views/lipachat_config_views.xml',
        'views/lipachat_message_views.xml',
        'views/lipachat_template_views.xml',
        'views/res_partner_views.xml',
        'views/lipachat_menus.xml',
        'wizard/send_whatsapp_wizard_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
    'external_dependencies': {
        'python': ['requests'],
    },
    'assets': {
    'web.assets_backend': [
        'lipachat_whatsapp/static/src/scss/lipachat_styles.scss',
    ],
   },
}