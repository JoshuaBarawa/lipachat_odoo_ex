from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from odoo.exceptions import UserError
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
    partner_id = fields.Many2one('res.partner', 'Contact', help='Select a contact to send this message to')
    view_phone_number = fields.Char('Contact Phone')
    phone_number = fields.Char('Phone Number')
    fail_reason = fields.Text('Fail Reason', readonly=True)
    
    # Add field to track if this is a bulk message template
    is_bulk_template = fields.Boolean('Is Bulk Template', default=False)
    bulk_parent_id = fields.Many2one('lipachat.message', 'Bulk Parent Message')
    
    # Add fields for incoming messages
    is_incoming = fields.Boolean('Is Incoming Message', default=False)
    incoming_message_id = fields.Char('Incoming Message ID')
    received_at = fields.Datetime('Received At')
    
    config_id = fields.Many2one(
        'lipachat.config',
        string='Configuration',
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
    caption = fields.Char('Caption')
    
    # Interactive fields
    header_text = fields.Char('Header Text')
    body_text = fields.Text('Body Text')
    button_text = fields.Char('Button Text')
    buttons_data = fields.Text('Buttons Data (JSON)')
    
    # Template fields
    template_name = fields.Many2one('lipachat.template', string='Template', domain=lambda self: self._get_template_domain())
    template_media_url = fields.Char('Media URL', readonly="state != 'draft'")
    template_variables = fields.Char('Template Variables', compute='_compute_template_variables', store=False)
    template_placeholders = fields.Text('Placeholder Values', default='[]')
    
    # Status fields
    state = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
        ('received', 'Received'),  # For incoming messages
    ], 'Status', default='draft')
    
    error_message = fields.Text('Error Message')
    response_data = fields.Text('API Response')
    sent_contacts = fields.Text('Sent To', readonly=True)
    failed_contacts = fields.Text('Failed To', readonly=True)
    
    # Computed field for truncated message display
    message_text_short = fields.Char('Content Preview', compute='_compute_message_text_short', store=False)

    def _get_template_domain(self):
        """Return domain to filter templates based on approval status"""
        return [('status', '=', 'approved')]
    
    # @api.model
    def fetch_all_messages(self):
        """Fetch all messages from LipaChat API and sync with local database"""
        configs = self.env['lipachat.config'].search([('active', '=', True)])
        
        if not configs:
            raise ValidationError(_("No active LipaChat configuration found."))
        
        total_fetched = 0
        total_new = 0
        
        for config in configs:
            try:
                fetched, new = self._fetch_messages_for_config(config)
                total_fetched += fetched
                total_new += new
            except Exception as e:
                _logger.error(f"Failed to fetch messages for config {config.id}: {str(e)}")
                continue
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Messages Synced'),
                'message': _('Fetched %d messages, %d new messages added.') % (total_fetched, total_new),
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _fetch_messages_for_config(self, config):
        """Fetch messages for a specific configuration"""
        if not config.api_key:
            raise ValidationError(_("API key not configured for %s") % config.name)
        
        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            # Fetch messages from API
            response = requests.get(
                f"{config.api_base_url}/whatsapp/message",
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                raise ValidationError(_("Failed to fetch messages: HTTP %d") % response.status_code)
            
            response_data = response.json()
            
            if response_data.get('status') != 'success':
                raise ValidationError(_("API Error: %s") % response_data.get('message', 'Unknown error'))
            
            messages = response_data.get('data', [])
            if not isinstance(messages, list):
                messages = [messages] if messages else []
            
            return self._process_fetched_messages(messages, config)
            
        except requests.exceptions.RequestException as e:
            raise ValidationError(_("Network error while fetching messages: %s") % str(e))
    
    def _process_fetched_messages(self, messages, config):
        """Process and store fetched messages"""
        fetched_count = len(messages)
        new_count = 0
        
        for msg_data in messages:
            try:
                # Check if message already exists
                existing_msg = self.search([
                    ('incoming_message_id', '=', msg_data.get('id')),
                    ('config_id', '=', config.id)
                ], limit=1)
                
                if existing_msg:
                    # Update existing message status if needed
                    self._update_existing_message(existing_msg, msg_data)
                else:
                    # Create new message record
                    self._create_message_from_api_data(msg_data, config)
                    new_count += 1
                    
            except Exception as e:
                _logger.error(f"Error processing message {msg_data.get('id', 'unknown')}: {str(e)}")
                continue
        
        return fetched_count, new_count
    
    def _create_message_from_api_data(self, msg_data, config):
        """Create a new message record from API data"""
        # Determine if it's incoming or outgoing
        is_incoming = msg_data.get('direction') == 'incoming' or msg_data.get('from') != config.default_from_number
        
        # Find or create contact
        partner_id = False
        phone_number = msg_data.get('from') if is_incoming else msg_data.get('to')
        
        if phone_number:
            phone_clean = self._clean_phone_number(phone_number)
            partner = self._find_or_create_partner(phone_clean)
            if partner:
                partner_id = partner.id
        
        # Determine message type and content
        message_type = 'text'
        message_text = ''
        media_type = False
        media_url = False
        caption = False
        
        if msg_data.get('type') == 'text':
            message_type = 'text'
            message_text = msg_data.get('text', {}).get('body', '') if isinstance(msg_data.get('text'), dict) else str(msg_data.get('text', ''))
        elif msg_data.get('type') in ['image', 'video', 'document', 'audio']:
            message_type = 'media'
            media_type = msg_data.get('type').upper()
            media_content = msg_data.get(msg_data.get('type'), {})
            media_url = media_content.get('link') or media_content.get('url')
            caption = media_content.get('caption', '')
            message_text = caption
        
        # Determine status
        state = 'received' if is_incoming else self._map_api_status_to_state(msg_data.get('status'))
        
        # Parse timestamp
        received_at = self._parse_timestamp(msg_data.get('timestamp'))
        
        vals = {
            'incoming_message_id': msg_data.get('id'),
            'message_id': msg_data.get('id') or str(uuid.uuid4()),
            'partner_id': partner_id,
            'phone_number': phone_number,
            'config_id': config.id,
            'message_type': message_type,
            'message_text': message_text,
            'media_type': media_type,
            'media_url': media_url,
            'caption': caption,
            'state': state,
            'is_incoming': is_incoming,
            'received_at': received_at,
            'response_data': json.dumps(msg_data),
        }
        
        return self.create(vals)
    
    def _update_existing_message(self, existing_msg, msg_data):
        """Update existing message with new status information"""
        new_status = self._map_api_status_to_state(msg_data.get('status'))
        if existing_msg.state != new_status:
            existing_msg.write({
                'state': new_status,
                'response_data': json.dumps(msg_data),
            })
    
    def _map_api_status_to_state(self, api_status):
        """Map API status to internal state"""
        status_mapping = {
            'sent': 'sent',
            'delivered': 'delivered',
            'read': 'read',
            'failed': 'failed',
            'pending': 'draft',
        }
        return status_mapping.get(api_status, 'draft')
    
    def _parse_timestamp(self, timestamp):
        """Parse timestamp from API response"""
        if not timestamp:
            return fields.Datetime.now()
        
        try:
            # Handle different timestamp formats
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                # Try different datetime formats
                for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S']:
                    try:
                        return datetime.strptime(timestamp, fmt)
                    except ValueError:
                        continue
        except Exception as e:
            _logger.warning(f"Failed to parse timestamp {timestamp}: {str(e)}")
        
        return fields.Datetime.now()
    
    def _find_or_create_partner(self, phone_number):
        """Find existing partner by phone or create a new one"""
        if not phone_number:
            return False
        
        # Search for existing partner
        partner = self.env['res.partner'].search([
            '|',
            ('phone', 'ilike', phone_number),
            ('mobile', 'ilike', phone_number)
        ], limit=1)
        
        if partner:
            return partner
        
        # Create new partner
        try:
            partner = self.env['res.partner'].create({
                'name': f"WhatsApp Contact {phone_number}",
                'mobile': phone_number,
                'is_company': False,
                'category_id': [(4, self._get_whatsapp_category_id())],
            })
            return partner
        except Exception as e:
            _logger.error(f"Failed to create partner for {phone_number}: {str(e)}")
            return False
    
    def _get_whatsapp_category_id(self):
        """Get or create WhatsApp contact category"""
        category = self.env['res.partner.category'].search([('name', '=', 'WhatsApp Contact')], limit=1)
        if not category:
            category = self.env['res.partner.category'].create({
                'name': 'WhatsApp Contact',
                'color': 10,  # Green color
            })
        return category.id

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        for record in self:
            if record.partner_id:
                record.view_phone_number = record.partner_id.mobile or record.partner_id.phone
                record.phone_number = record.partner_id.mobile or record.partner_id.phone
            else:
                record.view_phone_number = False
                record.phone_number = False

    @api.depends('template_name')
    def _compute_template_variables(self):
        for record in self:
            if record.template_name and record.template_name.body_text:
                # Find all variables like {{1}}, {{2}}, etc.
                variables = re.findall(r'\{\{(\d+)\}\}', record.template_name.body_text)
                record.template_variables = json.dumps(list(set(variables)))  # Remove duplicates
            else:
                record.template_variables = '[]'

    def _prepare_template_components(self):
        """Prepare the components dictionary for template messages"""
        components = {}
        
        # Add header if media URL is provided
        if self.template_media_url:
            components['header'] = {
                'type': 'IMAGE',
                'mediaUrl': self.template_media_url
            }
        
        # Handle body components
        if self.template_variables:
            try:
                # Get placeholders - handle both string JSON and direct values
                placeholders = []
                if self.template_placeholders:
                    # First try to parse as JSON
                    try:
                        parsed = json.loads(self.template_placeholders)
                        if isinstance(parsed, list):
                            placeholders = parsed
                        else:
                            placeholders = [parsed]
                    except json.JSONDecodeError:
                        # If not valid JSON, treat as direct string value
                        placeholders = [self.template_placeholders]
                
                # Convert all placeholders to strings without extra escaping
                sanitized_placeholders = []
                for placeholder in placeholders:
                    if placeholder is None:
                        sanitized_placeholders.append("")
                    else:
                        # Convert to string without adding extra quotes
                        sanitized_placeholders.append(str(placeholder))
                
                if sanitized_placeholders:
                    components['body'] = {
                        'placeholders': sanitized_placeholders
                    }
                
            except Exception as e:
                _logger.error(f"Error processing template placeholders: {str(e)}")
                raise ValidationError(_("Invalid template placeholder values. Please check your input."))
                
        return components

    @api.depends('message_text', 'message_type', 'template_name')
    def _compute_message_text_short(self):
        for record in self:
            try:
                if record.message_type == 'template' and record.template_name:
                    # Show template name for template messages
                    record.message_text_short = record.template_name.name
                elif record.message_text:
                    # Truncate to 50 characters and add ellipsis if longer
                    if len(record.message_text) > 50:
                        record.message_text_short = record.message_text[:50] + '...'
                    else:
                        record.message_text_short = record.message_text
                else:
                    record.message_text_short = ''
            except Exception as e:
                _logger.error(f"Error computing message_text_short: {str(e)}")
                record.message_text_short = ''

    @api.constrains('partner_id', 'phone_number')
    def _check_recipients(self):
        for record in self:
            if not record.partner_id and not record.phone_number:
                raise ValidationError(_("You must specify either a contact or a phone number"))
    
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
        """Send WhatsApp message via LipaChat API to one contact"""
        config = self.config_id
        if not config:
            raise ValidationError(_("Please select a valid LipaChat configuration."))

        # Determine recipient
        recipient = {}
        if self.partner_id:
            phone = self.partner_id.mobile or self.partner_id.phone
            if not phone:
                raise ValidationError(_("Selected contact doesn't have a phone number"))
            recipient = {
                'phone': self._clean_phone_number(phone),
                'name': self.partner_id.name,
                'partner_id': self.partner_id.id
            }
        elif self.phone_number:
            recipient = {
                'phone': self._clean_phone_number(self.phone_number),
                'name': self.phone_number,
                'partner_id': False
            }
        
        if not recipient:
            raise ValidationError(_("No valid recipient found. Please check phone number."))
        
        return self._send_single_message(recipient, config)

    def _send_bulk_messages(self, recipients, config):
        """Create individual message records for each recipient and send them"""
        # Mark current record as bulk template only if more than one recipient
        if not config.api_key:
            raise ValidationError(_("Please configure you API key before sending messages."))
        
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
        """Send message to a single recipient with session validation"""
        if not config.api_key:
            raise ValidationError(_("Please configure your API key before sending messages."))

        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            partner_id = recipient.get('partner_id')
            session_active = False
            
            # Check session status if we have a partner_id
            if partner_id:
                whatsapp_chat = self.env['whatsapp.chat']
                session_info = whatsapp_chat.rpc_get_session_info(partner_id)
                session_active = session_info.get('active', False)
                
                # Block non-template messages if no active session
                if not session_active and self.message_type != 'template':
                    fail_reason = _(
                        "No active session. Send a template message first to start a session."
                    )
                    self.write({
                        'state': 'failed',
                        'error_message': fail_reason,
                        'fail_reason': fail_reason
                    })
                    return False
            
            # Send the message
            send_method = getattr(self, f'_send_{self.message_type}_message')
            if send_method(config, headers, recipient):
                self.state = 'sent'
                self.sent_contacts = f"{recipient['name']} ({recipient['phone']})"
                
                # Start new session only if:
                # 1. We have a partner_id
                # 2. It's a template message
                # 3. No active session exists
                if partner_id and self.message_type == 'template' and not session_active:
                    session_started = whatsapp_chat.start_session_tracking(partner_id)
                    _logger.info(f"New session started for partner {partner_id}")
                elif session_active:
                    _logger.info(f"Using existing active session for partner {partner_id}")
                
                return True
            else:
                fail_reason = "Unexpected API response status"
                self.write({
                    'state': 'failed',
                    'error_message': fail_reason,
                    'fail_reason': fail_reason
                })
                return False
                
        except Exception as e:
            fail_reason = str(e)
            _logger.error(f"Failed to send to {recipient['phone']}: {fail_reason}")
            self.write({
                'state': 'failed',
                'error_message': fail_reason,
                'fail_reason': fail_reason
            })
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
            f"{config.api_base_url}/whatsapp/media",
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
            f"{config.api_base_url}/whatsapp/interactive/buttons",
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
            f"{config.api_base_url}/whatsapp/interactive/list",
            headers=headers,
            json=data,
            timeout=30
        )
        
        return self._handle_response(response)

    def _send_template_message(self, config, headers, recipient):
        components = self._prepare_template_components()
        
        # Ensure components are properly formatted
        if 'body' in components and 'placeholders' in components['body']:
            # Verify placeholders is a list, not a JSON string
            if isinstance(components['body']['placeholders'], str):
                try:
                    components['body']['placeholders'] = json.loads(components['body']['placeholders'])
                except json.JSONDecodeError:
                    components['body']['placeholders'] = [components['body']['placeholders']]
        
        data = {
            "messageId": self.message_id,
            "to": recipient['phone'],
            "from": self.from_number or config.default_from_number,
            "template": {
                "name": self.template_name.name,
                "languageCode": "en",
                "components": components
            }
        }
        
        _logger.info("Sending template with data: %s", json.dumps(data, indent=2))
        
        response = requests.post(
            f"{config.api_base_url}/whatsapp/template",
            headers=headers,
            json=data,  # Let the requests library handle JSON serialization
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