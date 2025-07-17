from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import logging

_logger = logging.getLogger(__name__)

class LipachatConfig(models.Model):
    _name = 'lipachat.config'
    _description = 'Lipachat Configuration'
    _rec_name = 'name'

    name = fields.Char('Configuration Name', required=True, default='Lipachat Gateway')
    api_key = fields.Char('API Key', help='Get your API key from https://app.lipachat.com/auth/signup')
    api_base_url = fields.Char('API Base URL', default='https://gateway.lipachat.com/api/v1', required=True)
    default_from_number = fields.Char('From Number', help='Default WhatsApp Business number (e.g., 254110090747)')
    active = fields.Boolean('Active', default=True)
    test_connection = fields.Boolean('Test Connection', compute='_compute_test_connection')

    last_sync_time = fields.Datetime('Last Successful Sync')
    last_sync_status = fields.Selection([
        ('success', 'Success'),
        ('no_new_messages', 'No New Messages'),
        ('failed', 'Failed')
    ], string='Last Sync Status')
    sync_frequency = fields.Integer(
        'Sync Frequency (minutes)',
        default=1,
        help="How often to check for new messages (in minutes)"
    )
    
    @api.depends('api_key', 'api_base_url')
    def _compute_test_connection(self):
        for record in self:
            record.test_connection = bool(record.api_key and record.api_base_url)

    
    def force_sync_now(self):
        """Manually trigger immediate message sync"""
        self.env['lipachat.message'].auto_fetch_messages()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Triggered'),
                'message': _('Message synchronization has been manually triggered.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def test_api_connection(self):
        """Test API connection"""
        if not self.api_key:
            raise ValidationError(_('Please configure your API key first.'))
        
        try:
            headers = {
                'apiKey': self.api_key,
                'Content-Type': 'application/json'
            }
            # Test with template list endpoint
            response = requests.get(
                f"{self.api_base_url}/template/{self.default_from_number or '254110090747'}",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('API connection successful!'),
                        'type': 'success',
                    }
                }
            else:
                raise ValidationError(_('API connection failed. Status: %s') % response.status_code)
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))
    
    @api.model
    def get_active_config(self):
        """Get active configuration"""
        config = self.search([('active', '=', True)], limit=1)
        if not config:
            raise ValidationError(_('No active LipaChat configuration found. Please configure the API settings.'))
        return config