from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class LipachatTemplate(models.Model):
    _name = 'lipachat.template'
    _description = 'WhatsApp Message Templates'
    _rec_name = 'name'

    name = fields.Char('Template Name', required=True)
    language = fields.Char('Language', default='en', required=True)
    category = fields.Selection([
        ('MARKETING', 'Marketing'),
        ('UTILITY', 'Utility'),
        ('AUTHENTICATION', 'Authentication')
    ], 'Category', required=True, default='UTILITY')
    
    phone_number = fields.Char('Phone Number', required=True)
    template_id = fields.Char('Template ID')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], 'Status', default='draft')
    
    # Component fields
    header_format = fields.Selection([
        ('TEXT', 'Text'),
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document')
    ], 'Header Format')
    header_text = fields.Char('Header Text')
    header_example = fields.Char('Header Example')
    media_id = fields.Char('Media ID')
    
    body_text = fields.Text('Body Text', required=True)
    body_examples = fields.Text('Body Examples (JSON)')
    
    footer_text = fields.Char('Footer Text')
    
    # Buttons
    buttons_data = fields.Text('Buttons Data (JSON)')
    
    # Authentication specific
    add_security_recommendation = fields.Boolean('Add Security Recommendation')
    code_expiration_minutes = fields.Integer('Code Expiration Minutes')
    
    component_data = fields.Text('Component Data (JSON)', compute='_compute_component_data', store=True)
    
    @api.depends('header_format', 'header_text', 'header_example', 'media_id', 
                 'body_text', 'body_examples', 'footer_text', 'buttons_data',
                 'add_security_recommendation', 'code_expiration_minutes')
    def _compute_component_data(self):
        """Compute component data JSON"""
        for record in self:
            component = {}
            
            # Header
            if record.header_format and record.header_text:
                component['header'] = {
                    'format': record.header_format,
                    'text': record.header_text
                }
                if record.header_example:
                    component['header']['example'] = record.header_example
            elif record.media_id:
                component['header'] = {
                    'format': record.header_format,
                    'mediaId': record.media_id
                }
            
            # Body
            body_component = {'text': record.body_text}
            if record.body_examples:
                try:
                    examples = json.loads(record.body_examples)
                    body_component['examples'] = examples
                except:
                    pass
            
            if record.category == 'AUTHENTICATION':
                body_component['addSecurityRecommendation'] = record.add_security_recommendation
            
            component['body'] = body_component
            
            # Footer
            if record.footer_text:
                footer_component = {'text': record.footer_text}
                if record.category == 'AUTHENTICATION' and record.code_expiration_minutes:
                    footer_component['codeExpirationMinutes'] = record.code_expiration_minutes
                component['footer'] = footer_component
            
            # Buttons
            if record.buttons_data:
                try:
                    buttons = json.loads(record.buttons_data)
                    component['buttons'] = buttons
                except:
                    pass
            
            record.component_data = json.dumps(component, indent=2)
    
    def create_template(self):
        """Create template via API"""
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        data = {
            'name': self.name,
            'language': self.language,
            'category': self.category,
            'component': json.loads(self.component_data)
        }
        
        try:
            response = requests.post(
                f"{config.api_base_url}/template/{self.phone_number}",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                self.status = 'submitted'
                response_data = response.json()
                if 'id' in response_data:
                    self.template_id = response_data['id']
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Template created successfully!'),
                        'type': 'success',
                    }
                }
            else:
                raise ValidationError(_('Failed to create template: %s') % response.text)
                
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))
    
    def sync_templates(self):
        """Sync templates from API"""
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(
                f"{config.api_base_url}/template/{self.phone_number}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                templates = response.json()
                # Process and update local templates
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Templates synchronized successfully!'),
                        'type': 'success',
                    }
                }
            else:
                raise ValidationError(_('Failed to sync templates: %s') % response.text)
                
        except requests.RequestException as e:
            raise ValidationError(_('Connection error: %s') % str(e))
