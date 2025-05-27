from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import uuid
import logging

_logger = logging.getLogger(__name__)

class LipachatMessage(models.Model):
    _name = 'lipachat.message'
    _description = 'WhatsApp Messages'
    _order = 'create_date desc'
    _rec_name = 'message_id'

    message_id = fields.Char('Message ID', required=True, default=lambda self: str(uuid.uuid4()))
    partner_id = fields.Many2one('res.partner', 'Contact', required=True)
    phone_number = fields.Char('Phone Number', required=True)
    from_number = fields.Char('From Number', required=True)
    message_type = fields.Selection([
        ('text', 'Text Message'),
        ('media', 'Media Message'),
        ('buttons', 'Interactive Buttons'),
        ('list', 'Interactive List'),
        ('template', 'Template Message'),
        ('flow', 'WhatsApp Flow')
    ], 'Message Type', required=True, default='text')
    
    # Text message fields
    message_text = fields.Text('Message Text')
    
    # Media message fields
    media_type = fields.Selection([
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document'),
        ('AUDIO', 'Audio')
    ], 'Media Type')
    media_url = fields.Char('Media URL')
    caption = fields.Text('Caption')
    
    # Interactive fields
    header_text = fields.Char('Header Text')
    body_text = fields.Text('Body Text')
    button_text = fields.Char('Button Text')
    buttons_data = fields.Text('Buttons Data (JSON)')
    
    # Template fields
    template_name = fields.Char('Template Name')
    template_language = fields.Char('Template Language', default='en')
    template_data = fields.Text('Template Data (JSON)')
    
    # Flow fields
    flow_id = fields.Char('Flow ID')
    flow_cta = fields.Char('Flow CTA')
    flow_screen = fields.Char('Flow Screen')
    flow_data = fields.Text('Flow Data (JSON)')
    
    # Status fields
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed')
    ], 'Status', default='draft')
    
    error_message = fields.Text('Error Message')
    response_data = fields.Text('API Response')
    
    def send_message(self):
        """Send WhatsApp message via LipaChat API"""
        config = self.env['lipachat.config'].get_active_config()
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            if self.message_type == 'text':
                self._send_text_message(config, headers)
            elif self.message_type == 'media':
                self._send_media_message(config, headers)
            elif self.message_type == 'buttons':
                self._send_buttons_message(config, headers)
            elif self.message_type == 'list':
                self._send_list_message(config, headers)
            elif self.message_type == 'template':
                self._send_template_message(config, headers)
            elif self.message_type == 'flow':
                self._send_flow_message(config, headers)
                
        except Exception as e:
            self.state = 'failed'
            self.error_message = str(e)
            _logger.error(f"Failed to send WhatsApp message: {e}")
    
    def _send_text_message(self, config, headers):
        """Send text message"""
        data = {
            "message": self.message_text,
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/message/text",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_media_message(self, config, headers):
        """Send media message"""
        data = {
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number,
            "mediaType": self.media_type,
            "mediaUrl": self.media_url,
            "caption": self.caption or ""
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/media",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_buttons_message(self, config, headers):
        """Send interactive buttons message"""
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "text": self.body_text,
            "buttons": buttons_data,
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/interactive/buttons",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_list_message(self, config, headers):
        """Send interactive list message"""
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "headerText": self.header_text,
            "body": self.body_text,
            "buttonText": self.button_text,
            "buttons": buttons_data,
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/interactive/list",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_template_message(self, config, headers):
        """Send template message"""
        template_data = json.loads(self.template_data) if self.template_data else {}
        
        data = {
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number,
            "template": {
                "name": self.template_name,
                "languageCode": self.template_language,
                "components": template_data
            }
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/template",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_flow_message(self, config, headers):
        """Send WhatsApp flow message"""
        flow_data = json.loads(self.flow_data) if self.flow_data else {}
        
        data = {
            "messageId": self.message_id,
            "to": self.phone_number,
            "from": self.from_number or config.default_from_number,
            "text": self.body_text,
            "flowId": self.flow_id,
            "flowCta": self.flow_cta,
            "screen": self.flow_screen,
            "data": flow_data
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/interactive/flows",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _handle_response(self, response):
        """Handle API response"""
        self.response_data = response.text
        
        if response.status_code == 200:
            self.state = 'sent'
            self.error_message = False
        else:
            self.state = 'failed'
            self.error_message = f"HTTP {response.status_code}: {response.text}"
