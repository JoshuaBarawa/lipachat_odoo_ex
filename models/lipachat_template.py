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
    language = fields.Selection(
        selection=[('en', 'English'), ('es', 'Spanish'), ('fr', 'French')],
        string='Language',
        default='en',
        required=True
    )
    category = fields.Selection([
        ('MARKETING', 'Marketing'),
        ('UTILITY', 'Utility'),
        ('AUTHENTICATION', 'Authentication')
    ], 'Category', required=True, default='UTILITY')
    
    phone_number = fields.Char('Phone Number', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], 'Status', default='draft', readonly=True)
    
    # Header components
    header_type = fields.Selection([
        ('TEXT', 'Text'),
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document')
    ], 'Type', default='TEXT')
    header_text = fields.Char('Text')
    header_media = fields.Binary('Media File', help="Upload media file for header")
    
    # Body component
    body_text = fields.Text('Body Text', required=True)
    
    # Footer component (optional)
    footer_text = fields.Char('Text')
    
    # Buttons (optional, max 3)
    button_1_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number')
    ], 'Type', default='QUICK_REPLY')
    button_1_text = fields.Char('Text')
    button_1_url = fields.Char('URL', help="For URL button type only")
    button_1_phone = fields.Char('Phone Number', help="For PHONE_NUMBER button type only")
    
    button_2_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number')
    ], 'Type', default='QUICK_REPLY')
    button_2_text = fields.Char('Text')
    button_2_url = fields.Char('URL', help="For URL button type only")
    button_2_phone = fields.Char('Phone Number', help="For PHONE_NUMBER button type only")
    
    button_3_type = fields.Selection([
        ('QUICK_REPLY', 'Quick Reply'),
        ('URL', 'URL'),
        ('PHONE_NUMBER', 'Phone Number')
    ], 'Type', default='QUICK_REPLY')
    button_3_text = fields.Char('Text')
    button_3_url = fields.Char('URL', help="For URL button type only")
    button_3_phone = fields.Char('Phone Number', help="For PHONE_NUMBER button type only")
    
    component_data = fields.Text('Component Data (JSON)', compute='_compute_component_data', store=True)
    
    @api.depends('header_type', 'header_text', 'header_media', 
                'body_text', 'footer_text',
                'button_1_text', 'button_1_type', 'button_1_url', 'button_1_phone',
                'button_2_text', 'button_2_type', 'button_2_url', 'button_2_phone',
                'button_3_text', 'button_3_type', 'button_3_url', 'button_3_phone')
    def _compute_component_data(self):
        """Compute component data JSON in simplified format"""
        for record in self:
            component = {}
            
            # Header
            if record.header_type and (record.header_text or record.header_media):
                header_data = {'format': record.header_type}
                if record.header_type == 'TEXT' and record.header_text:
                    header_data['text'] = record.header_text
                elif record.header_media:
                    header_data['media'] = True  # Placeholder for actual media ID
                
                component['header'] = header_data
            
            # Body
            component['body'] = {'text': record.body_text}
            
            # Footer
            if record.footer_text:
                component['footer'] = {'text': record.footer_text}
            
            # Buttons
            buttons = []
            for i in range(1, 4):
                button_text = getattr(record, f'button_{i}_text')
                if button_text:
                    button_type = getattr(record, f'button_{i}_type')
                    button_data = {
                        'type': button_type,
                        'text': button_text
                    }
                    if button_type == 'URL':
                        button_url = getattr(record, f'button_{i}_url')
                        if button_url:
                            button_data['url'] = button_url
                    elif button_type == 'PHONE_NUMBER':
                        button_phone = getattr(record, f'button_{i}_phone')
                        if button_phone:
                            button_data['phone_number'] = button_phone
                    buttons.append(button_data)
            
            if buttons:
                component['buttons'] = buttons
            
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