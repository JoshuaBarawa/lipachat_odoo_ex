# whatsapp_chat.py

from odoo import models, fields, api
from datetime import datetime, timedelta
import logging
import json # Import json for RPC response

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

    @api.model
    def create(self, vals):
        """
        Overrides the create method to automatically select the most recent
        contact when the chat interface is opened (i.e., a new transient
        record is created).
        """
        res = super().create(vals)
        if not res.contact_partner_id:
            # Find the most recent message to determine the default selected contact
            most_recent_message = self.env['lipachat.message'].search([
                ('is_bulk_template', '=', False),
                ('partner_id', '!=', False)
            ], order='create_date desc', limit=1)
            
            if most_recent_message and most_recent_message.partner_id:
                # Update the new transient record with the most recent contact's info
                res.write({
                    'contact_partner_id': most_recent_message.partner_id.id,
                    'contact': most_recent_message.partner_id.name,
                    # No need to set last_refresh here for initial load as computes will run
                })
                _logger.info(f"Automatically selected contact: {most_recent_message.partner_id.name} (ID: {most_recent_message.partner_id.id}) on chat load.")
        return res

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
        bubble_background = '#e0ffc6' if is_sent_by_me else '#ffffff'

        content = "Unsupported Message Type"
        if msg_data['message_type'] == 'text':
            content = msg_data['message_text'] or 'Empty message'
        elif msg_data['message_type'] == 'media':
            content = f"📎 {msg_data['media_type'].title()} Media"
            if msg_data['caption']:
                content += f": {msg_data['caption']}"
        elif msg_data['message_type'] == 'template':
            content = f"📋 Template: {msg_data['template_name']}"

        # Format date for display
        msg_date_obj = datetime.fromisoformat(msg_data['create_date']) if msg_data['create_date'] else None
        msg_date_display = msg_date_obj.strftime('%m/%d/%Y %H:%M') if msg_date_obj else ''
        
        return f'''
        <div class="message-bubble" 
             style="background: {bubble_background}; padding: 10px; margin: 8px 0; border-radius: 18px; position: relative; max-width: 80%; {bubble_align} border: 1px solid #ddd;">
            <div style="margin-bottom: 5px;">
                <strong style="color: {status_color};">{'You' if is_sent_by_me else contact_name}</strong>
                <small style="color: #666; float: right;">{msg_date_display}</small>
            </div>
            <div style="margin-bottom: 8px; word-wrap: break-word;">
                {content}
            </div>
            <div style="text-align: right; font-size: 12px; color: {status_color};">
                <span title="{msg_data['state'].title()}">{status_icon} {msg_data['state'].title()}</span>
                {f'<br><span style="color: #dc3545; font-size: 11px;">Error: {msg_data["error_message"]}</span>' if msg_data["state"] == 'failed' and msg_data["error_message"] else ''}
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
        """
        Dedicated RPC method for sending messages that doesn't rely on transient record state
        """
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
            message = self.env['lipachat.message'].create({
                'partner_id': partner.id,
                'phone_number': partner.mobile or partner.phone,
                'config_id': config.id,
                'message_type': 'text',
                'message_text': message_text.strip(),
                'state': 'draft'
            })
            
            message.send_message()
            return {
                'status': 'success',
                'message': f'Message sent to {partner.name}'
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
    