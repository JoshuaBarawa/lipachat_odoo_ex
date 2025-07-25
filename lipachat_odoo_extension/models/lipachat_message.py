from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, timezone
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
    template_placeholders = fields.Text('Placeholder Values')
    
    # Status fields
    state = fields.Selection([
        ('DRAFT', 'DRAFT'),
        ('SENT', 'SENT'),
        ('DELIVERED', 'DELIVERED'),
        ('READ', 'READ'),
        ('FAILED', 'FAILED'),
        ('RECEIVED', 'RECEIVED'),
    ], string='Status', default='DRAFT')

    direction = fields.Selection([
    ('INBOUND', 'INBOUND'),
    ('OUTBOUND', 'OUTBOUND')
    ], string='Direction', compute='_compute_direction', store=True)
    
    error_message = fields.Text('Error Message')
    response_data = fields.Text('API Response')
    sent_contacts = fields.Text('Sent To', readonly=True)
    failed_contacts = fields.Text('Failed To', readonly=True)
    
    # Computed field for truncated message display
    message_text_short = fields.Char('Content Preview', compute='_compute_message_text_short', store=False)

    last_sync_time = fields.Datetime('Last Sync Time', readonly=True)
    is_synced = fields.Boolean('Synced to System', default=True)

    @api.depends('is_incoming')
    def _compute_direction(self):
        for record in self:
            record.direction = 'INBOUND' if record.is_incoming else 'OUTBOUND'


    def _get_template_domain(self):
        """Return domain to filter templates based on approval status"""
        return [('status', '=', 'approved')]
    
    # @api.model
    def fetch_all_messages(self):
        """Manual trigger for fetching messages"""
        try:
            configs = self.env['lipachat.config'].search([('active', '=', True)])
            
            if not configs:
                raise ValidationError(_("No active LipaChat configuration found."))
            
            total_new = 0
            
            for config in configs:
                try:
                    _, new = self._fetch_messages_for_config(config)
                    total_new += new
                except Exception as e:
                    _logger.error(f"Failed to fetch messages for config {config.name}: {str(e)}")
                    continue
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Messages Synced',
                    'message': '%d new messages added.' % total_new,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Sync Failed',
                    'message': 'Error fetching messages: %s' % str(e),
                    'type': 'danger',
                    'sticky': True,
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
            # Initialize variables
            all_messages = []
            page = 0
            total_pages = 1  # Will be updated from first response
            page_size = 100  # Maximum page size to reduce number of requests
            
            # First request to get total pages without parameters
            initial_response = requests.get(
                f"{config.api_base_url}/whatsapp/message",
                headers=headers,
                timeout=30
            )
            
            if initial_response.status_code != 200:
                raise ValidationError(_("Failed to fetch messages: HTTP %d - %s") % 
                                    (initial_response.status_code, initial_response.text))
            
            try:
                initial_data = initial_response.json()
                total_pages = initial_data.get('totalPages', 1)
                _logger.info(f"Total pages to fetch: {total_pages}")
            except ValueError as e:
                _logger.error(f"Invalid JSON response: {initial_response.text}")
                raise ValidationError(_("Invalid API response format"))
            
            # Now fetch all pages with pagination
            while page < total_pages:
                params = {
                    'page': page,
                    'size': page_size
                }
                
                response = requests.get(
                    f"{config.api_base_url}/whatsapp/message",
                    headers=headers,
                    params=params,
                    timeout=30
                )
                
                _logger.info(f"Fetching page {page + 1}/{total_pages} with size {page_size}")
                
                if response.status_code != 200:
                    _logger.error(f"Failed to fetch page {page}: HTTP {response.status_code}")
                    page += 1
                    continue  # Skip to next page instead of failing completely
                
                try:
                    response_data = response.json()
                    messages = response_data.get('data', [])
                    
                    if messages:
                        all_messages.extend(messages)
                        _logger.info(f"Fetched {len(messages)} messages from page {page + 1}")
                    
                    # Update total pages in case it changed
                    current_total = response_data.get('totalPages', total_pages)
                    if current_total != total_pages:
                        _logger.info(f"Total pages updated from {total_pages} to {current_total}")
                        total_pages = current_total
                    
                except ValueError as e:
                    _logger.error(f"Invalid JSON in page {page}: {response.text}")
                    page += 1
                    continue
                
                page += 1
            
            _logger.info(f"Total messages fetched: {len(all_messages)}")
            return self._process_fetched_messages(all_messages, config)
            
        except requests.exceptions.RequestException as e:
            _logger.error(f"Network error while fetching messages: {str(e)}")
            raise ValidationError(_("Network error while fetching messages: %s") % str(e))
        
        
    

    @api.model
    def auto_fetch_messages(self):
        """Automatically fetch new messages from all active configurations"""
        _logger.info("=== Starting auto_fetch_messages at %s ===", fields.Datetime.now())
        try:
            # Get all active configurations
            configs = self.env['lipachat.config'].search([('active', '=', True)])
            
            if not configs:
                _logger.info("No active LipaChat configurations found for auto-fetch")
                return True
                
            total_new = 0
            
            for config in configs:
                try:
                    # Fetch and process messages
                    _, new = self._fetch_messages_for_config(config)
                    total_new += new
                    
                    # Update last sync time
                    config.write({
                        'last_sync_time': fields.Datetime.now(),
                        'last_sync_status': 'success' if new > 0 else 'no_new_messages'
                    })
                    
                except Exception as e:
                    _logger.error(f"Failed to auto-fetch messages for config {config.name}: {str(e)}")
                    config.write({
                        'last_sync_time': fields.Datetime.now(),
                        'last_sync_status': 'failed'
                    })
                    continue
            
            _logger.info(f"Auto-fetch completed. {total_new} new messages added.")
            return True
            
        except Exception as e:
            _logger.error(f"Critical error in auto_fetch_messages: {str(e)}", exc_info=True)
            return False
        

    
    def _process_fetched_messages(self, messages, config):
        """Process and store fetched messages"""
        fetched_count = len(messages)
        new_count = 0
        
        _logger.info(f"Processing {fetched_count} messages")
        
        for msg_data in messages:
            try:
                # Skip if no message ID
                if not msg_data.get('id'):
                    _logger.warning("Skipping message with no ID")
                    continue
                    
                # Check if message already exists with improved logic
                existing_msg = self._find_existing_message(msg_data, config)
                
                if existing_msg:
                    # Update existing message status if needed
                    _logger.debug(f"Updating existing message {msg_data.get('id')}")
                    self._update_existing_message(existing_msg, msg_data)
                else:
                    # Create new message record
                    _logger.debug(f"Creating new message {msg_data.get('id')}")
                    self._create_message_from_api_data(msg_data, config)
                    new_count += 1
                    
            except Exception as e:
                _logger.error(f"Error processing message {msg_data.get('id', 'unknown')}: {str(e)}")
                continue
        
        _logger.info(f"Processed {fetched_count} messages, {new_count} new messages added")
        return fetched_count, new_count
    



    def _find_existing_message(self, msg_data, config):
        """Find existing message using multiple criteria to avoid duplicates"""
        api_message_id = str(msg_data.get('id'))
        wa_message_id = msg_data.get('waMessageId')
        direction = msg_data.get('direction', '').upper()
        
        # First, try to find by incoming_message_id (for all messages)
        existing_msg = self.search([
            ('incoming_message_id', '=', api_message_id),
            ('config_id', '=', config.id)
        ], limit=1)
        
        if existing_msg:
            return existing_msg
        
        # If not found and we have a waMessageId, try to find by message_id
        if wa_message_id:
            existing_msg = self.search([
                ('message_id', '=', wa_message_id),
                ('config_id', '=', config.id)
            ], limit=1)
            
            if existing_msg:
                return existing_msg
        
        # For outbound messages, also check by phone number, message content, and approximate time
        if direction == 'OUTBOUND':
            contact_data = msg_data.get('contact', {})
            phone_number = contact_data.get('phoneNumber', '')
            message_text = msg_data.get('text', '')
            
            if phone_number and message_text:
                # Look for messages sent to same number with same content within last hour
                created_at = self._parse_timestamp(msg_data.get('createdAt'))
                time_window_start = created_at - timedelta(hours=1)
                time_window_end = created_at + timedelta(hours=1)
                
                existing_msg = self.search([
                    ('phone_number', '=', phone_number),
                    ('message_text', '=', message_text),
                    ('config_id', '=', config.id),
                    ('is_incoming', '=', False),
                    ('create_date', '>=', time_window_start),
                    ('create_date', '<=', time_window_end)
                ], limit=1)
                
                if existing_msg:
                    return existing_msg
        

        # def _create_message_record_safe(self, vals_without_timestamps, create_date, write_date):
        #     """Safely create message record with proper timestamp handling"""
        #     record = self.create(vals_without_timestamps)
            
        #     # Then update the timestamps directly in the database
        #     # This bypasses Odoo's ORM restrictions on system fields
        #     self.env.cr.execute("""
        #         UPDATE %s 
        #         SET create_date = %%s, write_date = %%s 
        #         WHERE id = %%s
        #     """ % record._table, (create_date, write_date, record.id))
            
        #     # Invalidate cache to ensure the updated values are reflected
        #     record.invalidate_cache(['create_date', 'write_date'])
            
        #     _logger.debug(f"Updated message {record.id} with create_date: {create_date}, write_date: {write_date}")
        #     return record

        return False
    




    def _create_message_from_api_data(self, msg_data, config):
        """Create a new message record from API data"""
        try:
            # Determine if it's incoming or outgoing
            direction = msg_data.get('direction', '').upper()
            is_incoming = direction == 'INBOUND'
            
            # Get contact information
            contact_data = msg_data.get('contact', {})
            phone_number = contact_data.get('phoneNumber', '')
            username = contact_data.get('name', '')
            
            # Find or create partner
            partner_id = False
            if phone_number:
                phone_clean = self._clean_phone_number(phone_number)
                partner = self._find_or_create_partner(phone_clean, username)
                partner_id = partner.id if partner else False
            
            # Determine message type and content
            msg_type = msg_data.get('type', '').upper()
            message_type = 'text'  # default
            message_text = msg_data.get('text', '')
            media_type = False
            media_url = False
            caption = False
            
            if msg_type == 'IMAGE':
                message_type = 'media'
                media_type = 'IMAGE'
                try:
                    metadata = json.loads(msg_data.get('metadata', '{}'))
                    media_url = metadata.get('url', '')
                    caption = metadata.get('caption', '')
                except json.JSONDecodeError:
                    _logger.warning(f"Could not parse metadata for message {msg_data.get('id')}")
            
            elif msg_type == 'TEMPLATE':
                message_type = 'template'
            
            # Map status
            api_status = msg_data.get('status', '').upper()
            if is_incoming and not api_status:
                api_status = 'RECEIVED'

            status_mapping = {
                'READ': 'READ',
                'DELIVERED': 'DELIVERED',
                'SENT': 'SENT',
                'FAILED': 'FAILED',
                'RECEIVED': 'RECEIVED',
            }
            state = status_mapping.get(api_status, 'RECEIVED' if is_incoming else 'SENT')
        
            
            # Parse timestamps
            created_at = self._parse_timestamp(msg_data.get('createdAt'))
            updated_at = self._parse_timestamp(msg_data.get('updatedAt'))
            
            vals = {
                'incoming_message_id': str(msg_data.get('id')),
                'message_id': msg_data.get('waMessageId') or str(uuid.uuid4()),
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
                'direction': 'INBOUND' if is_incoming else 'OUTBOUND',
                'received_at': created_at,
                'create_date': created_at,
                'write_date': updated_at,
                'response_data': json.dumps(msg_data, indent=2),
            }
            
            _logger.debug(f"Creating message with vals: {vals}")

            # Create the record first without timestamps
            vals_without_timestamps = vals.copy()
            create_date = vals_without_timestamps.pop('create_date')
            write_date = vals_without_timestamps.pop('write_date')

            record = self.create(vals_without_timestamps)

             # Then update the timestamps directly in the database
            # This bypasses Odoo's ORM restrictions on system fields
            self.env.cr.execute("""
                UPDATE %s 
                SET create_date = %%s, write_date = %%s 
                WHERE id = %%s
            """ % record._table, (create_date, write_date, record.id))
            
            # Invalidate cache to ensure the updated values are reflected
            record.invalidate_model(['create_date', 'write_date'])
            
            _logger.debug(f"Updated message {record.id} with create_date: {create_date}, write_date: {write_date}")
        
        
            return record
            
        except Exception as e:
            _logger.error(f"Failed to create message from API data: {str(e)}")
            raise

    
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
        if not api_status:
            return 'draft'
        
        api_status = api_status.lower()
        status_mapping = {
            'read': 'READ',
            'delivered': 'DELIVERED',
            'sent': 'SENT',
            'failed': 'FAILED',
            'received': 'RECEIVED',
            'pending': 'DRAFT',
        }
        return status_mapping.get(api_status, 'RECEIVED' if self.is_incoming else 'SENT')
    
    
    def _parse_timestamp(self, timestamp):
        """Parse timestamp from API response with better error handling"""
        if not timestamp:
            return fields.Datetime.now()
        
        try:
            # Handle different timestamp formats
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                # Try different datetime formats
                formats_to_try = [
                    '%Y-%m-%dT%H:%M:%S.%f%z',  # 2025-06-24T08:25:02.508+00:00
                    '%Y-%m-%dT%H:%M:%S.%fZ',   # 2025-06-24T08:25:02.508Z
                    '%Y-%m-%dT%H:%M:%S%z',     # 2025-06-24T08:25:02+00:00
                    '%Y-%m-%dT%H:%M:%SZ',      # 2025-06-24T08:25:02Z
                    '%Y-%m-%d %H:%M:%S',       # 2025-06-24 08:25:02
                ]
                
                for fmt in formats_to_try:
                    try:
                        parsed_dt = datetime.strptime(timestamp, fmt)
                        # Convert to UTC if it's a naive datetime
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
                        # Convert to naive datetime in UTC for Odoo
                        return parsed_dt.replace(tzinfo=None)
                    except ValueError:
                        continue
                        
            _logger.warning(f"Could not parse timestamp format: {timestamp}")
            return fields.Datetime.now()
            
        except Exception as e:
            _logger.warning(f"Failed to parse timestamp {timestamp}: {str(e)}")
            return fields.Datetime.now()
        

    
    def _find_or_create_partner(self, phone_number, name):
        """Find or create partner with guaranteed name fallback"""
        if not phone_number:
            _logger.warning("No phone number provided for partner lookup")
            return False
        
        # Clean the phone number
        phone_clean = self._clean_phone_number(phone_number)
        
        # Determine the final name to use
        if not name or not isinstance(name, str) or not name.strip():
            final_name = f"WhatsApp Contact {phone_clean}"
            _logger.debug(f"Using fallback name: {final_name}")
        else:
            final_name = name.strip()
            _logger.debug(f"Using provided name: {final_name}")
        
        # Find existing partner by phone
        partner = self.env['res.partner'].search([
            '|',
            ('phone', '=', phone_clean),
            ('mobile', '=', phone_clean)
        ], limit=1)
        
        if partner:
            # Update name if different (except for companies)
            if not partner.is_company and partner.name != final_name:
                try:
                    partner.name = final_name
                    _logger.debug(f"Updated partner {partner.id} name to '{final_name}'")
                except Exception as e:
                    _logger.error(f"Couldn't update partner name: {str(e)}")
            return partner
        
        # Create new partner
        try:
            partner = self.env['res.partner'].create({
                'name': final_name,
                'mobile': phone_clean,
                'phone': phone_clean,
                'is_company': False,
            })
            _logger.info(f"Created new partner {partner.id} with name '{final_name}'")
            return partner
        except Exception as e:
            _logger.error(f"Partner creation failed: {str(e)} - Using ultimate fallback")
            # Ultimate fallback if even this fails
            return self.env['res.partner'].create({
                'name': f"WhatsApp Contact {phone_clean}",
                'mobile': phone_clean,
                'phone': phone_clean,
                'is_company': False,
            })
        
    
    def _get_whatsapp_category_id(self, name):
        """Get or create WhatsApp contact category"""
        category = self.env['res.partner.category'].search([('name', '=', name)], limit=1)
        if not category:
            category = self.env['res.partner.category'].create({
                'name': name,
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
            self.state = 'SENT'
        elif success_count == 0:
            self.state = 'FAILED'
        else:
            self.state = 'partially_sent'
        
        # Update summary fields on template
        sent_contacts = [msg.partner_id.name or msg.phone_number for msg in individual_messages if msg.state == 'SENT']
        failed_contacts = [f"{msg.partner_id.name or msg.phone_number}: {msg.error_message}" for msg in individual_messages if msg.state == 'FAILED']
        
        self.sent_contacts = ', '.join(sent_contacts) if sent_contacts else ''
        self.failed_contacts = '\n'.join(failed_contacts) if failed_contacts else ''
        
        return True

    def _send_single_message(self, recipient, config):
        if not config.api_key:
            raise ValidationError(_("Please configure your API key before sending messages."))

        headers = {
            'apiKey': config.api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            # Send the message
            send_method = getattr(self, f'_send_{self.message_type}_message')
            result = send_method(config, headers, recipient)
            if isinstance(result, dict):
                if 'notification' in result:
                    # Show the notification to the user
                    return result['notification']
                
                if result.get('status', False):
                    self.state = 'SENT'
                    self.sent_contacts = f"{recipient['name']} ({recipient['phone']})"
                    return True
                else:
                    return False
                
            if result:
                self.state = 'SENT'
                self.sent_contacts = f"{recipient['name']} ({recipient['phone']})"
                return True
            
            else:
                if self.state == 'DRAFT':
                    return False  # Already handled in _handle_response
                
                fail_reason = "Unexpected API response status"
                self.write({
                    'state': 'FAILED',
                    'error_message': fail_reason,
                    'fail_reason': fail_reason
                })
                return False
                
        except Exception as e:
            fail_reason = str(e)
            _logger.error(f"Failed to send to {recipient['phone']}: {fail_reason}")
            self.write({
                'state': 'FAILED',
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
        
            # Check for the specific sandbox session error
            if (response_data.get('status') == 'error' and 
                "24-hour sandbox session window" in response_data.get('message', '')):
                error_msg = response_data.get('message')
                _logger.warning(f"Session window error: {error_msg}")
                # Show notification to user without marking as failed

                self.state = 'DRAFT'
                self.response_data = json.dumps(response_data)
                return {
                'notification': {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("Contact Session Expired"),
                        'message': error_msg,
                        'type': 'warning',
                        'sticky': True,
                    }
                },
                'status': False
            }
            
            
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

    




from odoo import models, fields

class IrCronInherit(models.Model):
    _inherit = 'ir.cron'

    # Simply extend the interval_type selection to include seconds
    interval_type = fields.Selection([
        ('seconds', 'Seconds'),
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')], string='Interval Unit', default='months')

    # Optional: Add a constraint to prevent too frequent executions
    @api.constrains('interval_type', 'interval_number')
    def _check_interval_seconds(self):
        for record in self:
            if record.interval_type == 'seconds' and record.interval_number < 60:
                raise ValidationError(
                    "Minimum interval for seconds is 10 seconds to prevent system overload."
                )

# You'll also need to update the _intervalTypes mapping in the base cron module
# But since we can't modify core files, we need to monkey-patch it
from odoo.addons.base.models.ir_cron import _intervalTypes
from dateutil.relativedelta import relativedelta

# Add seconds to the interval types mapping
_intervalTypes['seconds'] = lambda interval: relativedelta(seconds=interval)