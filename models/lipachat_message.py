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
    
    # Add field to track if this is a bulk message template
    is_bulk_template = fields.Boolean('Is Bulk Template', default=False)
    bulk_parent_id = fields.Many2one('lipachat.message', 'Bulk Parent Message')
    
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
    
    # Computed field for truncated message display
    message_text_short = fields.Char('Content Preview', compute='_compute_message_text_short', store=False)

    @api.depends('message_text')
    def _compute_message_text_short(self):
        for record in self:
            if record.message_text:
                # Truncate to 50 characters and add ellipsis if longer
                if len(record.message_text) > 50:
                    record.message_text_short = record.message_text[:50] + '...'
                else:
                    record.message_text_short = record.message_text
            else:
                record.message_text_short = ''

    @api.constrains('partner_id', 'partner_ids', 'phone_number')
    def _check_recipients(self):
        for record in self:
            if not record.partner_id and not record.partner_ids and not record.phone_number:
                raise ValidationError(_("You must specify at least one recipient (contact)"))
            
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

        # Determine recipients
        recipients = []
        if self.phone_number:
            recipients.append({
                'phone': self._clean_phone_number(self.phone_number),
                'name': self.partner_id.name if self.partner_id else self.phone_number,
                'partner_id': self.partner_id.id if self.partner_id else False
            })
        if self.partner_ids:
            for partner in self.partner_ids:
                phone = partner.mobile or partner.phone
                if phone:
                    recipients.append({
                        'phone': self._clean_phone_number(phone),
                        'name': partner.name,
                        'partner_id': partner.id
                    })
        
        if not recipients:
            raise ValidationError(_("No valid recipients found. Please check phone numbers."))
        
        # Always create individual message records, even for single recipients
        return self._send_bulk_messages(recipients, config)

    def _send_bulk_messages(self, recipients, config):
        """Create individual message records for each recipient and send them"""
        # Mark current record as bulk template only if more than one recipient
        if len(recipients) > 1:
            self.is_bulk_template = True
        else:
            # For single recipient, update current record with recipient info
            recipient = recipients[0]
            self.partner_id = recipient['partner_id'] if recipient['partner_id'] else False
            self.phone_number = recipient['phone']
            # Send directly without creating a copy
            return self._send_single_message(recipient, config)
        
        self.state = 'draft'  # Keep template as draft
        
        individual_messages = []
        
        for recipient in recipients:
            # Create individual message record
            individual_msg = self.copy({
                'partner_id': recipient['partner_id'],
                'partner_ids': [(5, 0, 0)],  # Clear many2many field
                'phone_number': recipient['phone'],
                'is_bulk_template': False,
                'bulk_parent_id': self.id,
                'message_id': str(uuid.uuid4()),  # New unique ID
            })
            individual_messages.append(individual_msg)
        
        # Send each individual message
        success_count = 0
        for msg in individual_messages:
            try:
                recipient = {
                    'phone': msg.phone_number,
                    'name': msg.partner_id.name if msg.partner_id else msg.phone_number,
                    'partner_id': msg.partner_id.id if msg.partner_id else False
                }
                if msg._send_single_message(recipient, config):
                    success_count += 1
            except Exception as e:
                _logger.error(f"Failed to send individual message {msg.id}: {str(e)}")
        
        # Update bulk template status
        total_messages = len(individual_messages)
        if success_count == total_messages:
            self.state = 'sent'
        elif success_count == 0:
            self.state = 'failed'
        else:
            self.state = 'partially_sent'
        
        # Update summary fields on template
        sent_contacts = [msg.partner_id.name or msg.phone_number for msg in individual_messages if msg.state == 'sent']
        failed_contacts = [f"{msg.partner_id.name or msg.phone_number}: {msg.error_message}" for msg in individual_messages if msg.state == 'failed']
        
        self.sent_contacts = ', '.join(sent_contacts) if sent_contacts else ''
        self.failed_contacts = '\n'.join(failed_contacts) if failed_contacts else ''
        
        return True

    def _send_single_message(self, recipient, config):
        """Send message to a single recipient"""
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            send_method = getattr(self, f'_send_{self.message_type}_message')
            if send_method(config, headers, recipient):
                self.state = 'sent'
                self.sent_contacts = f"{recipient['name']} ({recipient['phone']})"
                return True
            else:
                self.state = 'failed'
                self.error_message = "Unexpected API response status"
                self.failed_contacts = f"{recipient['name']} ({recipient['phone']}): Unexpected status"
                return False
        except Exception as e:
            _logger.error(f"Failed to send to {recipient['phone']}: {str(e)}")
            self.state = 'failed'
            self.error_message = str(e)
            self.failed_contacts = f"{recipient['name']} ({recipient['phone']}): {str(e)}"
            return False
    
    def _send_text_message(self, config, headers, recipient):
        data = {
            "message": self.message_text,
            "messageId": self.message_id,
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/message/text",
            headers=headers,
            json=data,
            timeout=30
        )
        
        return self._handle_response(response)
    
    def _send_media_message(self, config, headers, recipient):
        data = {
            "messageId": self.message_id,
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
        
        return self._handle_response(response)
    
    def _send_buttons_message(self, config, headers, recipient):
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "text": self.body_text,
            "buttons": buttons_data,
            "messageId": self.message_id,
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/interactive/buttons",
            headers=headers,
            json=data,
            timeout=30
        )
        
        return self._handle_response(response)
    
    def _send_list_message(self, config, headers, recipient):
        buttons_data = json.loads(self.buttons_data) if self.buttons_data else []
        
        data = {
            "headerText": self.header_text,
            "body": self.body_text,
            "buttonText": self.button_text,
            "buttons": buttons_data,
            "messageId": self.message_id,
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number
        }
        
        response = requests.post(
            f"{config.api_url}/whatsapp/interactive/list",
            headers=headers,
            json=data,
            timeout=30
        )
        
        return self._handle_response(response)
    
    def _send_template_message(self, config, headers, recipient):
        template_data = json.loads(self.template_data) if self.template_data else {}
        
        data = {
            "messageId": self.message_id,
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
        
        return self._handle_response(response)
    
    def _handle_response(self, response):
        """Handle API response and update message status accordingly"""
        try:
            response_data = response.json()
            
            # Check for successful status codes (2xx range)
            if response.status_code // 100 != 2:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                _logger.error(error_msg)
                raise ValidationError(error_msg)
            
            # Check the actual response content for success
            if response_data.get('status') != 'success':
                error_msg = response_data.get('message') or response.text
                _logger.error(f"API Error: {error_msg}")
                raise ValidationError(f"API Error: {error_msg}")
            
            # If we get here, the message was successfully sent
            self.response_data = json.dumps(response_data)
            
            # Check the actual message status in the response
            if response_data.get('data', {}).get('status') == 'SENT':
                return True
            else:
                _logger.warning(f"Message sent but with unexpected status: {response_data}")
                return False
                
        except json.JSONDecodeError:
            error_msg = f"Invalid JSON response: {response.text}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        

    # Add to LipachatMessage class
    @api.onchange('message_type')
    def _onchange_message_type(self):
        """Set default values and visibility when message type changes"""
        for record in self:
            # Clear fields when changing message type
            if record.message_type != 'text':
                record.message_text = False
            if record.message_type != 'media':
                record.media_type = False
                record.media_url = False
                record.caption = False
            if record.message_type != 'buttons':
                record.body_text = False
                record.buttons_data = False
            if record.message_type != 'list':
                record.header_text = False
                record.body_text = False
                record.button_text = False
                record.buttons_data = False
            if record.message_type != 'template':
                record.template_name = False
                record.template_language = 'en'
                record.template_data = False