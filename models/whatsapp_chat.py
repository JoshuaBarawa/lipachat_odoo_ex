# whatsapp_chat.py

from odoo import models, fields, api
from datetime import datetime, timedelta
import logging
import json # Import json for RPC response
from odoo.exceptions import ValidationError
import re
import requests
import uuid

_logger = logging.getLogger(__name__)

class WhatsappChat(models.TransientModel):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Chat View Only'

    contact = fields.Char(string="Selected Contact")
    contact_partner_id = fields.Integer(string="Selected Contact Partner ID")
    contacts_html = fields.Html(string="Conversations", compute="_compute_contacts_html")
    messages_html = fields.Html(string="Chat Messages", compute="_compute_messages_html")
    messages = fields.One2many('lipachat.message', compute='_compute_messages', string='Messages')
    new_message = fields.Text(string="New Message")
    last_refresh = fields.Datetime(string="Last Refresh", default=fields.Datetime.now) # Keep for potential manual refresh or other computes


    template_id = fields.Many2one('lipachat.template', string="Template")
    template_preview = fields.Html(string="Template Preview", compute="_compute_template_preview")

    template_message_textarea = fields.Text()
    template_media_url = fields.Char(string="Media URL", help="URL for media in template header")
    show_media_url_field = fields.Boolean(compute="_compute_show_media_url_field")

    session_start_time = fields.Datetime(string="Session Start Time")
    session_duration = fields.Integer(string="Session Duration (seconds)", default=300)  # 5 minutes
    session_active = fields.Boolean(string="Session Active", default=False)
    session_remaining_time = fields.Integer(string="Session Remaining Time", compute="_compute_session_remaining")

    can_send_message = fields.Boolean(compute='_compute_can_send_message')
    show_template = fields.Boolean(compute='_compute_show_template')
    show_message_section = fields.Boolean(compute='_compute_show_message_section')
    

    # Template fields
    template_name = fields.Many2one('lipachat.template', nolabel="1")
    template_header_text = fields.Text()
    template_body_text = fields.Text()
    template_header_type = fields.Char('Header Type', store=False)
   
    
    template_media_url = fields.Char('Media URL')
    template_variables = fields.Json('Template Variables', compute='_compute_template_variables', store=False)
    template_placeholders = fields.Json('Placeholder Values', default='[]')
    partner_id = fields.Many2one('res.partner', 'Contact')
    message_id = fields.Char('Message ID', required=True, default=lambda self: str(uuid.uuid4()))

    template_variable_values = fields.Char('Body Variables')


    template_components = fields.Json('Template Components')

    @api.onchange('template_name')
    def _onchange_template_name(self):
        """Update header type when template changes"""
        if self.template_name:
            self.template_header_type = self.template_name.header_type
            self.template_body_text = self.template_name.body_text

            self.template_variable_values = False
            self.template_placeholders = []

            _logger.info("Template header type: %s", self.template_header_type)
        else:
            self.template_header_type = False
            self.template_variable_values = False
            self.template_placeholders = []
        

    def _compute_template_variables(self, template):
        _logger.info("Extracting template variables: ", template.name)
        if template and template.body_text:
            # Find all variables like {{1}}, {{2}}, etc.
            variables = re.findall(r'\{\{(\d+)\}\}', template.body_text)
            self.template_variables = list(set(variables))  # Remove duplicates
        else:
            self.template_variables = '[]'
        _logger.info("Extracted this variables: ", self.template_variables)

    
    # @api.onchange('template_name', 'template_media_url')
    def _prepare_template_components(self, template, placeholders, media_url=None):
        """Prepare the components dictionary for template messages"""
        components = {}

        # varibale_values = [item.strip() for item in placeholders.split(",") if item.strip()]
        # Prepare placeholders FIRST
        _logger.info("Placeholders returned : %s", placeholders)


        if not template:
            return components
        
        try:
            # Get variables - ensure we have a list
            # variables = []
            # if self.template_variables:
            #     if isinstance(self.template_variables, str):
            #         try:
            #             variables = json.loads(self.template_variables)
            #         except json.JSONDecodeError:
            #             variables = [self.template_variables]
            #     else:
            #         variables = self.template_variables
            
            # # Sanitize all values
            # sanitized_vars = []
            # for var in variables:
            #     if var is None:
            #         sanitized_vars.append("")
            #     else:
            #         sanitized = str(var)
            #         sanitized = sanitized.replace('\\', '\\\\')
            #         sanitized = sanitized.replace('"', '\\"')
            #         sanitized_vars.append(sanitized)
            
            # Build components based on header type
            if template.header_type in ["IMAGE", "VIDEO", "DOCUMENT"]:
                components = {
                    "header": {
                        'type': template.header_type,
                        'mediaUrl': media_url or self.template_media_url or ""
                    },
                    'body': {
                        'placeholders': placeholders
                    }  
                }
            else:
                components = {
                    "header": {
                        'type': "TEXT",
                        'parameter': placeholders
                    },
                    'body': {
                        'placeholders': placeholders
                    }  
                }
                
        except Exception as e:
            _logger.error(f"Template component preparation failed: {str(e)}")
            raise ValidationError("Failed to prepare template components. Please check your input.")
        
        self.template_components = json.dumps(components)
        return components
    

    
    def send_template_message_v2(self, partner_id, template_id, placeholders, media_url=None):
        """Send WhatsApp template message with improved error handling and session checks"""
        try:
            config = self.env['lipachat.config'].search([('active', '=', True)], limit=1)
            if not config:
                raise ValidationError("No active LipaChat configuration found")

            partner = self.env['res.partner'].browse(partner_id)
            if not partner.exists():
                raise ValidationError("Selected contact not found")
            
            template = self.env['lipachat.template'].search([('name', '=', template_id)], limit=1)
            if not template.exists():
                raise ValidationError("Selected template not found")

            # Check if session already exists
            session_info = self.rpc_get_session_info(partner_id)
            session_active = session_info.get('active', False)
            
            components2 = self._prepare_template_components(template, placeholders, media_url)
            _logger.info(f"Template component data: "+json.dumps(components2))

            if isinstance(components2, str):
                try:
                    components2 = json.loads(components2)
                except json.JSONDecodeError as e:
                    raise ValidationError(f"Invalid template components format: {str(e)}")

            template_data = {
                'name': template.name,
                'languageCode': template.language or 'en',
                'components': components2
            }

            headers = {
                'apiKey': config.api_key,
                'Content-Type': 'application/json'
            }

            data = {
                "messageId": str(uuid.uuid4()),
                "to": partner.mobile or partner.phone,
                "from": config.default_from_number,
                "template": template_data
            }

            _logger.info(f"Template component data: "+json.dumps(data))

            response = requests.post(
                f"{config.api_base_url}/whatsapp/template",
                headers=headers,
                json=data,
                timeout=30
            )

            response_data = response.json() if response.content else {}

            if response_data.get('status') == 'success':
                # Create message record with proper placeholder handling
                placeholders = []
                if components2.get('body', {}).get('placeholders'):
                    placeholders = components2['body']['placeholders']
                
                self.env['lipachat.message'].create({
                    'partner_id': partner_id,
                    'phone_number': partner.mobile or partner.phone,
                    'config_id': config.id,
                    'template_name': template.id,
                    'message_type': 'template',
                    'message_text': f"Template: {template.name}",
                    "media_type": template.header_type,
                    "template_media_url": media_url,
                    "template_placeholders": placeholders,
                    'state': 'sent'
                })

                # Only start new session if one doesn't already exist
                session_started = False
                if not session_active:
                    session_started = self.start_session_tracking(partner.id)
                    _logger.info(f"New session started for partner {partner.id}")
                else:
                    _logger.info(f"Using existing session for partner {partner.id}")
                
                self._clear_template_data()
                
                return {
                    'status': 'success',
                    'message': 'Template message sent successfully!',
                    'session_started': session_started,
                    'session_info': self.rpc_get_session_info(partner.id)
                }
            else:
                error_msg = response_data.get('message', 'Unknown error')
                raise ValidationError(f"Failed to send template: {error_msg}")

        except Exception as e:
            _logger.error(f"Template sending failed: {str(e)}")
            raise ValidationError(f"Failed to send template message: {str(e)}")

        
    
    def _clear_template_data(self):
        """Clear template form data after sending"""
        self.write({
            'template_name': False,
            'template_header_text': '',
            'template_header_type': '',
            'template_media_url': '',
            'template_variables': '',
            'template_placeholders': [],
            'template_variable_values': False,
            'template_components': False
        })



    @api.depends('session_active', 'contact_partner_id')
    def _compute_can_send_message(self):
        _logger.info("Records to process: %s", self)
        _logger.info("Number of records: %s", len(self))
        
        if not self:
            _logger.info("No records to process - self is empty")
            return
        
        for record in self:
            _logger.info("Processing record ID: %s", record.id)
            _logger.info("Record session_active: %s", record.session_active)
            _logger.info("Record contact_partner_id: %s", record.contact_partner_id)
            _logger.info("Record contact_partner_id (bool): %s", bool(record.contact_partner_id))
            
            record.can_send_message = record.session_active and bool(record.contact_partner_id)
            _logger.info("Computed can_send_message: %s", record.can_send_message)


    @api.depends('session_active', 'contact_partner_id')
    def _compute_show_template(self):
        _logger.info("Records to process: %s", self)
        _logger.info("Number of records: %s", len(self))
        
        if not self:
            _logger.info("No records to process - self is empty")
            return
        
        for record in self:
            _logger.info("Processing record ID: %s", record.id)
            _logger.info("Record session_active: %s", record.session_active)
            _logger.info("Record contact_partner_id: %s", record.contact_partner_id)
            _logger.info("Record contact_partner_id (bool): %s", bool(record.contact_partner_id))
            
            record.show_template = bool(record.contact_partner_id) and not record.session_active
            _logger.info("Computed show_template: %s", record.show_template)
    

    @api.depends('contact_partner_id')
    def _compute_show_message_section(self):
        
        for record in self:
            record.show_message_section = bool(record.contact_partner_id)
            _logger.info("Computed show message section: %s", record.show_message_section)




    @api.depends('session_start_time', 'session_duration')
    def _compute_session_remaining(self):
        for record in self:
            if record.session_start_time and record.session_active:
                elapsed = (fields.Datetime.now() - record.session_start_time).total_seconds()
                remaining = max(0, record.session_duration - elapsed)
                record.session_remaining_time = int(remaining)
                
                # Auto-expire session if time is up
                if remaining <= 0:
                    record.session_active = False
            else:
                record.session_remaining_time = 0



    def start_session_tracking(self, partner_id):
        """Start or extend session tracking for a contact"""
        # Check if session already exists and is active
        existing_session = self.search([
            ('contact_partner_id', '=', partner_id),
            ('create_uid', '=', self.env.uid),
            ('session_active', '=', True)
        ], limit=1)
        
        now = fields.Datetime.now()
        
        if existing_session:
            # Extend existing session
            existing_session.write({
                'session_start_time': now,
                'session_active': True,
                'session_duration': 300  # 5 minutes
            })
            _logger.info(f"Extended existing session for partner {partner_id}")
            return False  # Didn't start new session, just extended
        else:
            # Create new session
            self.create({
                'contact_partner_id': partner_id,
                'contact': self.env['res.partner'].browse(partner_id).name,
                'session_start_time': now,
                'session_active': True,
                'session_duration': 300  # 5 minutes
            })
            _logger.info(f"Started new session for partner {partner_id}")
            return True  # New session started
    


    @api.model
    def rpc_get_session_info(self, partner_id):
        """Get session information for a specific partner"""
        session = self.search([
            ('contact_partner_id', '=', partner_id),
            ('create_uid', '=', self.env.uid),
            ('session_active', '=', True)
        ], limit=1)
        
        if session and session.session_start_time:
            elapsed = (fields.Datetime.now() - session.session_start_time).total_seconds()
            remaining = max(0, session.session_duration - elapsed)
            
            # Auto-expire if time is up
            if remaining <= 0:
                session.session_active = False
                return {'active': False}
            
            return {
                'active': True,
                'start_time': session.session_start_time.isoformat(),
                'remaining_time': int(remaining),
                'duration': session.session_duration
            }
        return {'active': False}




    @api.depends('template_id')
    def _compute_show_media_url_field(self):
        for record in self:
            record.show_media_url_field = record.template_id and record.template_id.header_type == 'IMAGE'

    @api.depends('template_id')
    def _compute_template_preview(self):
        for record in self:
            if not record.template_id:
                record.template_preview = False
                continue
                
            preview_lines = []
            if record.template_id.header_type == 'text' and record.template_id.header_text:
                preview_lines.append(f"<strong>Header (Text):</strong> {record.template_id.header_text}")
            elif record.template_id.header_type == 'media':
                media_type = record.template_id.header_media_type or 'media'
                preview_lines.append(f"<strong>Header ({media_type.title()}):</strong> Requires URL")
                
            if record.template_id.body_text:
                preview_lines.append(f"<strong>Body:</strong> {record.template_id.body_text}")
            if record.template_id.footer_text:
                preview_lines.append(f"<strong>Footer:</strong> {record.template_id.footer_text}")
                
            record.template_preview = "<br>".join(preview_lines) if preview_lines else "No preview available"


    
    @api.onchange('template_id')
    def _onchange_template_id(self):
        """Insert template content into message field when selected"""
        if self.template_id:
            self.template_media_url = False
            if self.template_id.body_text:
                self.template_message_textarea = self.template_id.body_text



    def send_template_message(self, partner_id, template_id, media_url=None):
        """
        Dedicated method for sending template messages
        """
        if not partner_id:
            raise ValidationError("Please select a contact first")

        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise ValidationError("Selected contact not found")

        template = self.env['lipachat.template'].search([('name', '=', template_id)], limit=1)
        if not template.exists():
            raise ValidationError("Selected template not found: ", template_id)

        config = self.env['lipachat.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise ValidationError("No active LipaChat configuration found")

        try:
            # Prepare template components
            components = {
                'body': {
                    'placeholders': []
                }
            }

            # Handle header based on template type
            if template.header_type == 'text' and template.header_text:
                components['header'] = {
                    'type': 'TEXT',
                    'parameter': template.header_text
                }
            elif template.header_type == 'media' and media_url:
                components['header'] = {
                    'type': template.header_media_type.upper(),  # IMAGE, VIDEO, DOCUMENT
                    'mediaUrl': media_url
                }

            message = self.env['lipachat.message'].create({
                'partner_id': partner.id,
                'phone_number': partner.mobile or partner.phone,
                'config_id': config.id,
                'message_type': 'template',
                'template_name': template.name,
                'state': 'draft'
            })

            # Send the message
            message.send_template_message({
                'name': template.name,
                'languageCode': template.language_code or 'en',
                'components': components
            })

            return {
                'status': 'success',
                'message': f'Template message sent to {partner.name}'
            }
        except Exception as e:
            _logger.error(f"Failed to send template message: {str(e)}")
            raise ValidationError(f"Failed to send template message: {str(e)}")
        



    
    def get_available_templates(self):
        """Return available templates for RPC"""
        templates = self.env['lipachat.template'].search([('status', '=', 'approved')])
        return [{
            'id': t.id,
            'name': t.name,
            'body_text': t.body_text,
            'header_text': t.header_text,
            'footer_text': t.footer_text
        } for t in templates]

    @api.model
    def create(self, vals):
        """
        Simplified create method - let JavaScript handle contact selection for faster loading
        """
        return super().create(vals)

    @api.depends('contact_partner_id', 'last_refresh')
    def _compute_contacts_html(self):
        """
        Computes the HTML for the list of conversations (contacts) on the left panel.
        Groups messages by partner and shows the latest message and count.
        Highlights the currently selected contact.
        
        IMPORTANT: The JavaScript in here will be modified to use RPC.
        """
        for record in self:
            _logger.debug(f"Computing contacts_html for record ID: {record.id}, selected_partner_id: {record.contact_partner_id}")
            
            messages = self.env['lipachat.message'].search([
                ('state', 'in', ['sent', 'delivered', 'failed', 'received']), 
                ('is_bulk_template', '=', False),
                ('partner_id', '!=', False)
            ])
            
            contacts_data = {}
            for msg in messages:
                partner = msg.partner_id
                if partner and partner.active:
                    if partner.id not in contacts_data:
                        contacts_data[partner.id] = {
                            'name': partner.name,
                            'phone': msg.phone_number or partner.mobile or partner.phone,
                            'latest_message': '',
                            'latest_date': datetime.min,
                            'message_count': 0
                        }
                    
                    contacts_data[partner.id]['message_count'] += 1
                    
                    if msg.create_date and msg.create_date > contacts_data[partner.id]['latest_date']:
                        contacts_data[partner.id]['latest_message'] = msg.message_text[:50] + '...' if len(msg.message_text or '') > 50 else (msg.message_text or '')
                        contacts_data[partner.id]['latest_date'] = msg.create_date

            sorted_contacts = sorted(contacts_data.items(), 
                                   key=lambda x: x[1]['latest_date'], 
                                   reverse=True)

            html = '<div class="contacts-list">'
            if not sorted_contacts:
                html += '<p class="text-muted" style="padding: 10px;">No conversations found. Send a message to start chatting or wait for incoming messages.</p>'
            else:
                for partner_id, contact_info in sorted_contacts:
                    selected_style = ''
                    selected_class = ''
                    if record.contact_partner_id == partner_id:
                        selected_style = 'background-color: #e8f5e8; border: 2px solid #25D366;'
                        selected_class = 'selected'
                    
                    session = self.env['whatsapp.chat'].search([
                    ('contact_partner_id', '=', partner_id),
                    ('create_uid', '=', self.env.uid)], limit=1)
                    is_expired = not (session and session.session_active)
                    contact_color = 'red' if is_expired else '#25D366'
                    
                    # No need to escape for onlick here, as it's handled by a global JS handler now
                    html += f'''
                    <div class="contact-item {selected_class}" data-partner-id="{partner_id}" data-contact-name="{contact_info['name']}" 
                         style="padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; border-radius: 5px; margin-bottom: 5px; {selected_style}"
                         onmouseover="if(!this.classList.contains('selected')) this.style.backgroundColor='#f8f9fa'" 
                         onmouseout="if(!this.classList.contains('selected')) this.style.backgroundColor='white'">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong style="color: #25D366;">{contact_info['name']}</strong>
                                <br>
                                <small style="color: #666;">{contact_info['phone'] or 'No phone'}</small>
                                <br>
                                <small style="color: #888; font-style: italic;">{contact_info['latest_message']}</small>
                            </div>
                            <div style="text-align: right;">
                                <small style="color: #999;">{contact_info['latest_date'].strftime('%m/%d %H:%M') if contact_info['latest_date'] and contact_info['latest_date'] != datetime.min else ''}</small>
                                <br>
                                <span style="background: #25D366; color: white; border-radius: 10px; padding: 2px 6px; font-size: 11px;">
                                    {contact_info['message_count']} msg{'s' if contact_info['message_count'] != 1 else ''}
                                </span>
                            </div>
                        </div>
                    </div>
                    '''
            html += '</div>'
            
            # Remove all the embedded <script> tags from here.
            # We will handle JavaScript in a separate, persistent asset file.
            record.contacts_html = html

    @api.depends('contact_partner_id', 'last_refresh')
    def _compute_messages_html(self):
        """
        This compute method will now primarily serve the initial load.
        Subsequent message updates will be handled client-side via RPC.
        """
        for record in self:
            _logger.debug(f"Computing messages_html for record ID: {record.id}, selected_partner_id: {record.contact_partner_id}")
            if not record.contact_partner_id:
                record.messages_html = '''
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; color: #666; height: 300px;">
                    <div style="font-size: 48px; margin-bottom: 20px;">💬</div>
                    <h3>Select a contact to view messages</h3>
                    <p>Choose a conversation from the left panel to start viewing messages</p>
                </div>
                '''
                continue

            # Fetch messages only for the current selected contact
            messages_data = self._get_messages_for_partner(record.contact_partner_id)
            
            if not messages_data:
                record.messages_html = f'''
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; color: #666; height: 300px;">
                    <div style="font-size: 36px; margin-bottom: 15px;">📭</div>
                    <h4>No messages found</h4>
                    <p>No conversation history with {record.contact}</p>
                    <small>Start by sending a message below</small>
                </div>
                '''
                continue

            html = '<div class="chat-messages" style="max-height: 400px; overflow-y: auto; padding: 10px;" id="chat-messages-container">'
            
            for msg_data in messages_data:
                # Use the helper to render message HTML
                html += self._render_message_html(msg_data, record.contact)
            
            html += '</div>'
            # Remove the embedded <script> for auto-scroll here too.
            record.messages_html = html


    def _render_message_html(self, msg_data, contact_name):
        """
        Helper method to render a single message HTML bubble.
        This allows both compute methods and RPC methods to use it.
        """
        status_color = {
            'sent': '#25D366',
            'delivered': '#34B7F1', 
            'failed': '#dc3545',
            'draft': '#6c757d',
            'received': '#A9A9A9' 
        }.get(msg_data['state'], '#6c757d')
        
        status_icon = {
            'sent': '✓',
            'delivered': '✓✓',
            'failed': '✗',
            'draft': '○',
            'received': '←' 
        }.get(msg_data['state'], '○')

        is_sent_by_me = (msg_data['state'] in ['sent', 'delivered', 'failed', 'draft']) 
        bubble_align = 'margin-left: auto;' if is_sent_by_me else 'margin-right: auto;'
        bubble_background = '#d9fdd3' if is_sent_by_me else '#ffffff'

        content = "Unsupported Message Type"
        if msg_data['message_type'] == 'text':
            # Convert line breaks to HTML <br> tags and escape HTML
            message_text = msg_data['message_text'] or 'Empty message'
            # First escape HTML entities to prevent XSS
            import html
            escaped_text = html.escape(message_text)
            # Then convert line breaks to <br> tags
            content = escaped_text.replace('\n', '<br>')
        elif msg_data['message_type'] == 'media':
            content = f"📎 {msg_data['media_type'].title()} Media"
            if msg_data['caption']:
                # Also handle line breaks in captions
                import html
                escaped_caption = html.escape(msg_data['caption'])
                formatted_caption = escaped_caption.replace('\n', '<br>')
                content += f": {formatted_caption}"
        elif msg_data['message_type'] == 'template':
            content = f"📋 Template: {msg_data['template_name'].name}"

        # Format date for display
        msg_date_obj = datetime.fromisoformat(msg_data['create_date']) if msg_data['create_date'] else None
        msg_date_display = msg_date_obj.strftime('%m/%d/%Y %H:%M') if msg_date_obj else ''
        
        return f'''
        <div class="message-bubble" 
            style="background: {bubble_background}; font-size: 13px; max-width: 65%; padding: 4px 12px; line-height: 1.4; position: relative; margin: 8px 0; border-radius: 7.5px; position: relative; {bubble_align} box-shadow: 0 1px 0.5px rgba(0,0,0,0.1);">
            <div style="">
                <strong style="color: {status_color};">{'You' if is_sent_by_me else contact_name}</strong>
                <small style="color: #666; float: right; font-size: 12px;">{msg_date_display}</small>
            </div>
            <div style="word-wrap: break-word; white-space: normal;">
                {content}
            </div>
            <div style="text-align: right; font-size: 12px; color: {status_color};">
                <span title="{msg_data['state'].title()}">{status_icon} {msg_data['state'].title()}</span>
                {f'<br><span style="color: #dc3545; font-size: 11px;">Error: {html.escape(msg_data["error_message"])}</span>' if msg_data["state"] == 'failed' and msg_data["error_message"] else ''}
            </div>
        </div>
        '''


    def _get_messages_for_partner(self, partner_id, last_message_id=None):
        """
        Helper method to fetch and format messages for a partner.
        Can be called internally by computes or by RPC.
        """
        domain = [
            ('partner_id', '=', partner_id),
            ('is_bulk_template', '=', False)
        ]
        if last_message_id:
            domain.append(('id', '>', last_message_id))
        
        messages = self.env['lipachat.message'].search(domain, order='create_date asc')
        
        return [{
            'id': msg.id,
            'message_text': msg.message_text,
            'create_date': msg.create_date.isoformat() if msg.create_date else None,
            'state': msg.state,
            'message_type': msg.message_type,
            'media_type': msg.media_type,
            'caption': msg.caption,
            'template_name': msg.template_name,
            'error_message': msg.error_message
        } for msg in messages]

    @api.depends('contact_partner_id', 'last_refresh')
    def _compute_messages(self):
        for record in self:
            if record.contact_partner_id:
                messages = self.env['lipachat.message'].search([
                    ('partner_id', '=', record.contact_partner_id),
                    ('is_bulk_template', '=', False)
                ], order='create_date desc')
                record.messages = messages
            else:
                record.messages = self.env['lipachat.message']

    def send_message(self):
        """
        Send a WhatsApp message. This method is called via RPC from the JavaScript client.
        The message content and contact info are taken from the current record.
        """
        self.ensure_one()
        
        # Get values from the current record
        if not self.contact_partner_id:
            raise UserError("Please select a contact first")
        
        if not self.new_message or not self.new_message.strip():
            raise UserError("Please enter a message")
        
        partner = self.env['res.partner'].browse(self.contact_partner_id)
        if not partner.exists():
            raise UserError("Selected contact not found")
        
        config = self.env['lipachat.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError("No active LipaChat configuration found")
        
        try:
            # Create the message directly without relying on the transient record
            message = self.env['lipachat.message'].create({
                'partner_id': partner.id,
                'phone_number': partner.mobile or partner.phone,
                'config_id': config.id,
                'message_type': 'text',
                'message_text': self.new_message.strip(),
                'state': 'draft'
            })
            
            message.send_message()
            self.new_message = ''  # Clear the message field
            
            return {
                'status': 'success',
                'message': f'Message sent to {partner.name}'
            }
        except Exception as e:
            _logger.error(f"Failed to send message: {str(e)}")
            raise UserError(f"Failed to send message: {str(e)}")
    

    @api.model
    def rpc_send_message(self, partner_id, message_text):
        """Dedicated RPC method for sending messages with session validation"""
        if not partner_id:
            raise UserError("Please select a contact first")
        
        if not message_text or not message_text.strip():
            raise UserError("Please enter a message")
        
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise UserError("Selected contact not found")
        
        config = self.env['lipachat.config'].search([('active', '=', True)], limit=1)
        if not config:
            raise UserError("No active LipaChat configuration found")
        
        try:
            # Check session status first
            session_info = self.rpc_get_session_info(partner_id)
            if not session_info.get('active'):
                raise UserError(
                    "No active session. Please send a template message first to start a session."
                )
            
            message = self.env['lipachat.message'].create({
                'partner_id': partner.id,
                'phone_number': partner.mobile or partner.phone,
                'config_id': config.id,
                'message_type': 'text',
                'message_text': message_text.strip(),
                'state': 'draft'
            })
            
            message.send_message()
            
            # Don't start new session - just use existing one
            _logger.info(f"Using existing session for partner {partner.id}")
            
            return {
                'status': 'success',
                'message': f'Message sent to {partner.name}',
                'session_started': False,  # No new session started
                'session_info': session_info  # Return current session info
            }
        except Exception as e:
            _logger.error(f"Failed to send message: {str(e)}")
            raise UserError(f"Failed to send message: {str(e)}")
    


    @api.model
    def rpc_get_messages_html(self, partner_id):
        """
        New RPC method to fetch messages and render their HTML for a given partner.
        This will be called by JavaScript to update the chat area without a full reload.
        """
        _logger.info(f"RPC: rpc_get_messages_html called for partner_id: {partner_id}")
        if not partner_id:
            return "" # Return empty string if no partner

        messages_data = self._get_messages_for_partner(partner_id)
        
        # Get the contact name for rendering the messages
        partner = self.env['res.partner'].browse(partner_id)
        contact_name = partner.name if partner.exists() else "Unknown Contact"

        html_content = ""
        if not messages_data:
            html_content = f'''
            <div style="flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; color: #666; height: 300px;">
                <div style="font-size: 36px; margin-bottom: 15px;">📭</div>
                <h4>No messages found</h4>
                <p>No conversation history with {contact_name}</p>
                <small>Start by sending a message below</small>
            </div>
            '''
        else:
            for msg_data in messages_data:
                html_content += self._render_message_html(msg_data, contact_name)
        
        return html_content

    @api.model
    def rpc_get_contacts_html(self):
        """
        New RPC method to fetch and render the contacts list HTML.
        This can be used to refresh the left panel without a full form reload.
        """
        # Re-use the logic from _compute_contacts_html but without record context
        # This will simulate the compute, but can be called directly by JS
        
        messages = self.env['lipachat.message'].search([
            ('state', 'in', ['sent', 'delivered', 'failed', 'received']), 
            ('is_bulk_template', '=', False),
            ('partner_id', '!=', False)
        ])
        
        contacts_data = {}
        for msg in messages:
            partner = msg.partner_id
            if partner and partner.active:
                if partner.id not in contacts_data:
                    contacts_data[partner.id] = {
                        'name': partner.name,
                        'phone': msg.phone_number or partner.mobile or partner.phone,
                        'latest_message': '',
                        'latest_date': datetime.min,
                        'message_count': 0
                    }
                
                contacts_data[partner.id]['message_count'] += 1
                
                if msg.create_date and msg.create_date > contacts_data[partner.id]['latest_date']:
                    contacts_data[partner.id]['latest_message'] = msg.message_text[:50] + '...' if len(msg.message_text or '') > 50 else (msg.message_text or '')
                    contacts_data[partner.id]['latest_date'] = msg.create_date

        sorted_contacts = sorted(contacts_data.items(), 
                               key=lambda x: x[1]['latest_date'], 
                               reverse=True)

        html = '<div class="contacts-list">'
        if not sorted_contacts:
            html += '<p class="text-muted" style="padding: 10px;">No conversations found. Send a message to start chatting or wait for incoming messages.</p>'
        else:
            # Need to get the currently selected partner ID from the transient model instance.
            # Since this is an @api.model method, we don't have 'self' as a recordset.
            # We'll rely on the JS to re-apply the selection highlight after updating this HTML.
            
            # For simplicity, let's assume the JS will manage the 'selected' class.
            # So, the `selected_style` and `selected_class` logic is removed from Python for this RPC.
            # It will be applied by JS based on `data-partner-id`.
            
            for partner_id, contact_info in sorted_contacts:
                html += f'''
                <div class="contact-item" data-partner-id="{partner_id}" data-contact-name="{contact_info['name']}" 
                     style="padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; border-radius: 5px; margin-bottom: 5px;"
                     onmouseover="if(!this.classList.contains('selected')) this.style.backgroundColor='#f8f9fa'" 
                     onmouseout="if(!this.classList.contains('selected')) this.style.backgroundColor='white'">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong style="color: #25D366;">{contact_info['name']}</strong>
                            <br>
                            <small style="color: #666;">{contact_info['phone'] or 'No phone'}</small>
                            <br>
                            <small style="color: #888; font-style: italic;">{contact_info['latest_message']}</small>
                        </div>
                        <div style="text-align: right;">
                            <small style="color: #999;">{contact_info['latest_date'].strftime('%m/%d %H:%M') if contact_info['latest_date'] and contact_info['latest_date'] != datetime.min else ''}</small>
                            <br>
                            <span style="background: #25D366; color: white; border-radius: 10px; padding: 2px 6px; font-size: 11px;">
                                {contact_info['message_count']} msg{'s' if contact_info['message_count'] != 1 else ''}
                            </span>
                        </div>
                    </div>
                </div>
                '''
        html += '</div>'
        return html
    

    @api.model
    def get_most_recent_contact(self):
        """
        New RPC method to immediately get the most recent contact for faster initialization
        """
        most_recent_message = self.env['lipachat.message'].search([
            ('is_bulk_template', '=', False),
            ('partner_id', '!=', False)
        ], order='create_date desc', limit=1)
        
        if most_recent_message and most_recent_message.partner_id:
            return {
                'partner_id': most_recent_message.partner_id.id,
                'name': most_recent_message.partner_id.name
            }
        
        return {}
    
    @api.model
    def get_initial_chat_data(self):
        """Include session info in initial load"""
        most_recent = self.get_most_recent_contact()
        if not most_recent:
            return {
                'contacts_html': self.rpc_get_contacts_html(),
                'messages_html': '',
                'partner_id': False,
                'session_info': {'active': False}
            }
        
        return {
            'partner_id': most_recent['partner_id'],
            'partner_name': most_recent['name'],
            'contacts_html': self.rpc_get_contacts_html(),
            'messages_html': self.rpc_get_messages_html(most_recent['partner_id']),
            'session_info': self.rpc_get_session_info(most_recent['partner_id'])
        }

    