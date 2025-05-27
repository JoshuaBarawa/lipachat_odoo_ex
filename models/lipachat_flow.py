from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class LipachatFlow(models.Model):
    _name = 'lipachat.flow'
    _description = 'WhatsApp Flows'
    _rec_name = 'name'

    name = fields.Char('Flow Name', required=True)
    phone_number = fields.Char('Phone Number', required=True)
    categories = fields.Selection([
        ('SIGN_UP', 'Sign Up'),
        ('SIGN_IN', 'Sign In'),
        ('APPOINTMENT_BOOKING', 'Appointment Booking'),
        ('LEAD_GENERATION', 'Lead Generation'),
        ('CONTACT_US', 'Contact Us'),
        ('CUSTOMER_SATISFACTION', 'Customer Satisfaction'),
        ('OTHER', 'Other')
    ], 'Categories', default='OTHER', required=True)
    
    flow_id = fields.Char('Flow ID')
    flow_file = fields.Char('Flow File Name', help='JSON file name for the flow definition')
    flow_json = fields.Text('Flow JSON', help='Flow definition in JSON format')
    
    status = fields.Selection([
        ('draft', 'Draft'),
        ('created', 'Created'),
        ('published', 'Published'),
        ('failed', 'Failed')
    ], 'Status', default='draft')
    
    preview_url = fields.Char('Preview URL')
    error_message = fields.Text('Error Message')
    
    def create_flow(self):
        """Create flow via API"""
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        data = {
            'phoneNumber': self.phone_number,
            'name': self.name,
            'categories': self.categories,
            'file': self.flow_file or f"{self.name.lower().replace(' ', '_')}.json"
        }
        
        try:
            response = requests.post(
                f"{config.api_base_url}/whatsapp/manage/flow",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                self.status = 'created'
                response_data = response.json()
                if 'id' in response_data:
                    self.flow_id = response_data['id']
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Flow created successfully!'),
                        'type': 'success',
                    }
                }
            else:
                self.status = 'failed'
                self.error_message = response.text
                raise ValidationError(_('Failed to create flow: %s') % response.text)
                
        except requests.RequestException as e:
            self.status = 'failed'
            self.error_message = str(e)
            raise ValidationError(_('Connection error: %s') % str(e))
    
    def get_preview_url(self):
        """Get flow preview URL"""
        if not self.flow_id:
            raise ValidationError(_('Flow must be created first.'))
        
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(
                f"{config.api_base_url}/whatsapp/manage/flow/{self.flow_id}/preview/url",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if 'preview_url' in response_data:
                    self.preview_url = response_data['preview_url']
                return {
                    'type': 'ir.actions.act_url',
                    'url': self.preview_url,
                    'target': 'new',
                }
            else:
                raise ValidationError(_('Failed to get preview URL: %s') % response.text)
                
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))
    
    def publish_flow(self):
        """Publish flow"""
        if not self.flow_id:
            raise ValidationError(_('Flow must be created first.'))
        
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(
                f"{config.api_base_url}/whatsapp/manage/flow/{self.flow_id}/publish",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                self.status = 'published'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Flow published successfully!'),
                        'type': 'success',
                    }
                }
            else:
                raise ValidationError(_('Failed to publish flow: %s') % response.text)
                
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))
