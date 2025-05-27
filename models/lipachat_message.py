from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import requests
import json
import uuid
import logging
import re

_logger = logging.getLogger(__name__)

class LipachatMessage(models.Model):
    _name = 'lipachat.message'
    _description = 'WhatsApp Messages'
    _order = 'create_date desc'
    _rec_name = 'message_id'

    message_id = fields.Char('Message ID', required=True, default=lambda self: str(uuid.uuid4()))
    partner_id = fields.Many2one('res.partner', 'Contact')
    partner_ids = fields.Many2many(
        'res.partner',
        string='Contacts',
        help='Select multiple contacts to send this message to'
    )
    phone_number = fields.Char('Phone Number')
    
    config_id = fields.Many2one(
        'lipachat.config',
        string='LipaChat Configuration',
        domain=[('active', '=', True)],
        required=True,
        help='Select LipaChat config to use for sending this message'
    )
    
    from_number = fields.Char(
        'From Number',
        related='config_id.default_from_number',
        readonly=True,
        store=False,
    )
    
    message_type = fields.Selection([
        ('text', 'Text Message'),
        ('media', 'Media Message'),
        ('buttons', 'Interactive Buttons'),
        ('list', 'Interactive List'),
        ('template', 'Template Message'),
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
    
    # Status fields
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('partially_sent', 'Partially Sent')
    ], 'Status', default='draft')
    
    error_message = fields.Text('Error Message')
    response_data = fields.Text('API Response')
    sent_contacts = fields.Text('Sent To', readonly=True)
    failed_contacts = fields.Text('Failed To', readonly=True)

    @api.constrains('partner_id', 'partner_ids', 'phone_number')
    def _check_recipients(self):
        for record in self:
            if not record.partner_id and not record.partner_ids and not record.phone_number:
                raise ValidationError(_("You must specify at least one recipient (contact or phone number)"))
            
    @api.constrains('message_type', 'message_text')
    def _check_message_content(self):
        for record in self:
            if record.message_type == 'text' and not record.message_text:
                raise ValidationError(_("Message text is required for text messages"))
            
    def _clean_phone_number(self, phone):
        """Remove all non-digit characters from phone number"""
        if not phone:
            return phone
        # Remove all non-digit characters
        cleaned = re.sub(r'[^\d]', '', phone)
        # Remove leading 0 if present (for Kenya numbers)
        if cleaned.startswith('0'):
            cleaned = cleaned[1:]
        return cleaned


    def send_message(self):
        """Send WhatsApp message via LipaChat API to one or multiple contacts"""
        config = self.config_id
        if not config:
            raise ValidationError(_("Please select a valid LipaChat configuration."))

        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        # Determine recipients
        recipients = []
        if self.phone_number:
            recipients.append({
                'phone': self._clean_phone_number(self.phone_number),
                'name': self.partner_id.name if self.partner_id else self.phone_number
            })
        if self.partner_ids:
            for partner in self.partner_ids:
                phone = partner.mobile or partner.phone
                if phone:
                    recipients.append({
                        'phone': self._clean_phone_number(phone),
                        'name': partner.name
                    })
        
        if not recipients:
            raise ValidationError(_("No valid recipients found. Please check phone numbers."))
        
        success_count = 0
        failed_contacts = []
        sent_contacts = []
        
        try:
            for recipient in recipients:
                try:
                    if self.message_type == 'text':
                        self._send_text_message(config, headers, recipient)
                    elif self.message_type == 'media':
                        self._send_media_message(config, headers, recipient)
                    elif self.message_type == 'buttons':
                        self._send_buttons_message(config, headers, recipient)
                    elif self.message_type == 'list':
                        self._send_list_message(config, headers, recipient)
                    elif self.message_type == 'template':
                        self._send_template_message(config, headers, recipient)
                    
                    success_count += 1
                    sent_contacts.append(recipient['name'])
                except Exception as e:
                    _logger.error(f"Failed to send to {recipient['phone']}: {str(e)}")
                    failed_contacts.append(f"{recipient['name']} ({recipient['phone']}): {str(e)}")
            
            # Update message status based on results
            if success_count == len(recipients):
                self.state = 'sent'
            elif success_count == 0:
                self.state = 'failed'
            else:
                self.state = 'partially_sent'
            
            self.sent_contacts = ', '.join(sent_contacts)
            self.failed_contacts = '\n'.join(failed_contacts)
                
        except Exception as e:
            self.state = 'failed'
            self.error_message = str(e)
            _logger.error(f"Failed to send WhatsApp messages: {e}")

    
    def _send_text_message(self, config, headers, recipient):
        data = {
            "message": self.message_text,
            "messageId": str(uuid.uuid4()),  # New ID for each recipient
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/message/text",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_media_message(self, config, headers, recipient):
        data = {
            "messageId": str(uuid.uuid4()),
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number,
            "mediaType": self.media_type,
            "mediaUrl": self.media_url,
            "caption": self.caption or ""
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/media",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_buttons_message(self, config, headers, recipient):
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "text": self.body_text,
            "buttons": buttons_data,
            "messageId": str(uuid.uuid4()),
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/interactive/buttons",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_list_message(self, config, headers, recipient):
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "headerText": self.header_text,
            "body": self.body_text,
            "buttonText": self.button_text,
            "buttons": buttons_data,
            "messageId": str(uuid.uuid4()),
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/interactive/list",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _send_template_message(self, config, headers, recipient):
        template_data = json.loads(self.template_data) if self.template_data else {}
        
        data = {
            "messageId": str(uuid.uuid4()),
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number,
            "template": {
                "name": self.template_name,
                "languageCode": self.template_language,
                "components": template_data
            }
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/template",
            headers=headers,
            json=data,
            timeout=30
        )
        
        self._handle_response(response)
    
    def _handle_response(self, response):
        if response.status_code != 200:
            raise ValidationError(f"HTTP {response.status_code}: {response.text}")