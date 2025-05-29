from odoo import models, fields, api
from datetime import datetime, timedelta

class WhatsappChat(models.TransientModel):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Chat View Only'

    contact = fields.Char(string="Selected Contact")
    contact_partner_id = fields.Integer(string="Selected Contact Partner ID")
    contacts_html = fields.Html(string="Contacts", compute="_compute_contacts_html")
    messages_html = fields.Html(string="Chat Messages", compute="_compute_messages_html")
    messages = fields.One2many('lipachat.message', compute='_compute_messages', string='Messages')
    new_message = fields.Text(string="New Message")
    last_refresh = fields.Datetime(string="Last Refresh", default=fields.Datetime.now)

    @api.depends()
    def _compute_contacts_html(self):
        for record in self:
            # Get all sent messages with contacts
            messages = self.env['lipachat.message'].search([
                ('state', '=', 'sent'),
                ('is_bulk_template', '=', False),
                ('partner_id', '!=', False)
            ])
            
            # Group by contact and get latest message info
            contacts_data = {}
            for msg in messages:
                partner = msg.partner_id
                if partner.id not in contacts_data:
                    contacts_data[partner.id] = {
                        'name': partner.name,
                        'phone': msg.phone_number or partner.mobile or partner.phone,
                        'latest_message': msg.message_text[:50] + '...' if len(msg.message_text or '') > 50 else (msg.message_text or ''),
                        'latest_date': msg.create_date,
                        'message_count': 0
                    }
                contacts_data[partner.id]['message_count'] += 1
                
                # Update if this message is more recent
                if msg.create_date > contacts_data[partner.id]['latest_date']:
                    contacts_data[partner.id]['latest_message'] = msg.message_text[:50] + '...' if len(msg.message_text or '') > 50 else (msg.message_text or '')
                    contacts_data[partner.id]['latest_date'] = msg.create_date

            # Sort contacts by latest message date (most recent first)
            sorted_contacts = sorted(contacts_data.items(), 
                                   key=lambda x: x[1]['latest_date'], 
                                   reverse=True)

            html = '<div class="contacts-list">'
            if not sorted_contacts:
                html += '<p class="text-muted">No conversations found. Send a message to start chatting.</p>'
            else:
                for partner_id, contact_info in sorted_contacts:
                    # Add selection highlight if this is the selected contact
                    selected_style = ''
                    if record.contact_partner_id == partner_id:
                        selected_style = 'background-color: #e8f5e8; border: 2px solid #25D366;'
                    
                    html += f'''
                    <div class="contact-item" data-partner-id="{partner_id}" data-contact-name="{contact_info['name']}" 
                         style="padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; border-radius: 5px; margin-bottom: 5px; {selected_style}"
                         onmouseover="if(!this.classList.contains('selected')) this.style.backgroundColor='#f8f9fa'" 
                         onmouseout="if(!this.classList.contains('selected')) this.style.backgroundColor='white'"
                         onclick="selectContact('{contact_info['name']}', {partner_id})">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong style="color: #25D366;">{contact_info['name']}</strong>
                                <br>
                                <small style="color: #666;">{contact_info['phone'] or 'No phone'}</small>
                                <br>
                                <small style="color: #888; font-style: italic;">{contact_info['latest_message']}</small>
                            </div>
                            <div style="text-align: right;">
                                <small style="color: #999;">{contact_info['latest_date'].strftime('%m/%d %H:%M')}</small>
                                <br>
                                <span style="background: #25D366; color: white; border-radius: 10px; padding: 2px 6px; font-size: 11px;">
                                    {contact_info['message_count']} msg{'s' if contact_info['message_count'] != 1 else ''}
                                </span>
                            </div>
                        </div>
                    </div>
                    '''
            html += '</div>'
            
            # Add JavaScript for contact selection and auto-refresh
            html += f'''
            <script>
                function selectContact(contactName, partnerId) {{
                    // Find the contact field and set its value
                    var contactField = document.querySelector('input[name="contact"]');
                    var partnerIdField = document.querySelector('input[name="contact_partner_id"]');
                    
                    if (contactField && contactField.value !== contactName) {{
                        contactField.value = contactName;
                        contactField.dispatchEvent(new Event('change'));
                    }}
                    if (partnerIdField && partnerIdField.value !== partnerId.toString()) {{
                        partnerIdField.value = partnerId;
                        partnerIdField.dispatchEvent(new Event('change'));
                    }}
                    
                    // Highlight selected contact
                    document.querySelectorAll('.contact-item').forEach(function(item) {{
                        item.style.backgroundColor = 'white';
                        item.style.border = '1px solid #eee';
                        item.classList.remove('selected');
                    }});
                    
                    var selectedItem = event.target.closest('.contact-item');
                    selectedItem.style.backgroundColor = '#e8f5e8';
                    selectedItem.style.border = '2px solid #25D366';
                    selectedItem.classList.add('selected');
                    
                    // Trigger form reload to update messages
                    setTimeout(function() {{
                        var form = document.querySelector('form');
                        if (form) {{
                            // Trigger a soft refresh by dispatching change event
                            var event = new Event('odoo-will-refresh');
                            form.dispatchEvent(event);
                        }}
                    }}, 100);
                }}
                
                // Auto-refresh functionality
                var autoRefreshInterval;
                
                function startAutoRefresh() {{
                    // Clear existing interval
                    if (autoRefreshInterval) {{
                        clearInterval(autoRefreshInterval);
                    }}
                    
                    // Start new interval (refresh every 10 seconds)
                    autoRefreshInterval = setInterval(function() {{
                        // Only refresh if a contact is selected
                        var contactField = document.querySelector('input[name="contact"]');
                        if (contactField && contactField.value) {{
                            // Trigger a subtle refresh of messages
                            var messagesContainer = document.querySelector('.chat-messages-container');
                            if (messagesContainer) {{
                                // Add a loading indicator
                                var loadingDiv = document.createElement('div');
                                loadingDiv.innerHTML = '<small style="color: #666; float: right;">Checking for new messages...</small>';
                                loadingDiv.style.position = 'absolute';
                                loadingDiv.style.top = '10px';
                                loadingDiv.style.right = '20px';
                                loadingDiv.style.zIndex = '1000';
                                messagesContainer.appendChild(loadingDiv);
                                
                                // Remove loading indicator after 2 seconds
                                setTimeout(function() {{
                                    if (loadingDiv.parentNode) {{
                                        loadingDiv.parentNode.removeChild(loadingDiv);
                                    }}
                                }}, 2000);
                                
                                // Trigger field recomputation
                                var partnerIdField = document.querySelector('input[name="contact_partner_id"]');
                                if (partnerIdField) {{
                                    partnerIdField.dispatchEvent(new Event('change'));
                                }}
                            }}
                        }}
                    }}, 10000); // 10 seconds
                }}
                
                // Start auto-refresh when page loads
                document.addEventListener('DOMContentLoaded', function() {{
                    startAutoRefresh();
                }});
                
                // Restart auto-refresh if form is reloaded
                setTimeout(function() {{
                    startAutoRefresh();
                }}, 1000);
            </script>
            '''
            
            record.contacts_html = html

    @api.depends('contact', 'contact_partner_id')
    def _compute_messages_html(self):
        for record in self:
            if not record.contact_partner_id:
                record.messages_html = '''
                <div style="flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column; color: #666; height: 300px;">
                    <div style="font-size: 48px; margin-bottom: 20px;">💬</div>
                    <h3>Select a contact to view messages</h3>
                    <p>Choose a conversation from the left panel to start viewing messages</p>
                </div>
                '''
                continue

            # Get messages for selected contact
            messages = self.env['lipachat.message'].search([
                ('partner_id', '=', record.contact_partner_id),
                ('is_bulk_template', '=', False)
            ], order='create_date asc')

            if not messages:
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
            
            for msg in messages:
                # Determine message status styling
                status_color = {
                    'sent': '#25D366',
                    'delivered': '#34B7F1', 
                    'failed': '#dc3545',
                    'draft': '#6c757d'
                }.get(msg.state, '#6c757d')
                
                status_icon = {
                    'sent': '✓',
                    'delivered': '✓✓',
                    'failed': '✗',
                    'draft': '○'
                }.get(msg.state, '○')

                # Message content based on type
                if msg.message_type == 'text':
                    content = msg.message_text or 'Empty message'
                elif msg.message_type == 'media':
                    content = f"📎 {msg.media_type.title()} Media"
                    if msg.caption:
                        content += f": {msg.caption}"
                elif msg.message_type == 'template':
                    content = f"📋 Template: {msg.template_name}"
                else:
                    content = f"💬 {msg.message_type.title()} Message"

                # Format date
                msg_date = msg.create_date.strftime('%m/%d/%Y %H:%M')
                
                # Check if message is recent (within last 5 minutes) for highlighting
                is_recent = (datetime.now() - msg.create_date.replace(tzinfo=None)) < timedelta(minutes=5)
                recent_style = 'animation: pulse 1s ease-in-out;' if is_recent else ''
                
                html += f'''
                <div class="message-bubble" style="background: #f0f0f0; padding: 10px; margin: 8px 0; border-radius: 18px; position: relative; max-width: 80%; margin-left: auto; border-left: 4px solid {status_color}; {recent_style}">
                    <div style="margin-bottom: 5px;">
                        <strong style="color: #25D366;">You</strong>
                        <small style="color: #666; float: right;">{msg_date}</small>
                    </div>
                    <div style="margin-bottom: 8px; word-wrap: break-word;">
                        {content}
                    </div>
                    <div style="text-align: right; font-size: 12px; color: {status_color};">
                        <span title="{msg.state.title()}">{status_icon} {msg.state.title()}</span>
                        {f'<br><span style="color: #dc3545; font-size: 11px;">Error: {msg.error_message}</span>' if msg.state == 'failed' and msg.error_message else ''}
                    </div>
                </div>
                '''
            
            html += '''
            </div>
            <script>
                // Auto-scroll to bottom of messages
                setTimeout(function() {
                    var messagesContainer = document.getElementById('chat-messages-container');
                    if (messagesContainer) {
                        messagesContainer.scrollTop = messagesContainer.scrollHeight;
                    }
                }, 100);
            </script>
            '''
            record.messages_html = html

    @api.depends('contact_partner_id')
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
        """Create and send a new message to the selected contact"""
        self.ensure_one()
        if not self.contact_partner_id or not self.new_message.strip():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please select a contact and enter a message.',
                    'type': 'warning'
                }
            }

        # Get the partner
        partner = self.env['res.partner'].browse(self.contact_partner_id)
        if not partner.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Selected contact not found.',
                    'type': 'danger'
                }
            }

        # Get active LipaChat config
        config = self.env['lipachat.config'].search([('active', '=', True)], limit=1)
        if not config:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'No active LipaChat configuration found. Please configure LipaChat first.',
                    'type': 'danger'
                }
            }

        try:
            # Create the message record
            message = self.env['lipachat.message'].create({
                'partner_id': partner.id,
                'phone_number': partner.mobile or partner.phone,
                'config_id': config.id,
                'message_type': 'text',
                'message_text': self.new_message,
                'state': 'draft'
            })

            # Send the message
            message.send_message()

            # Clear the input
            self.new_message = ''

            # Update last refresh time
            self.last_refresh = fields.Datetime.now()

            # Return success notification with form reload
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
                'params': {
                    'notification': {
                        'title': 'Success',
                        'message': f'Message sent to {partner.name}',
                        'type': 'success'
                    }
                }
            }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to send message: {str(e)}',
                    'type': 'danger'
                }
            }

    def refresh_chat(self):
        """Refresh the chat interface - FIXED VERSION"""
        self.ensure_one()
        
        # Update last refresh time
        self.last_refresh = fields.Datetime.now()
        
        # Force recompute of all computed fields
        self._compute_contacts_html()
        self._compute_messages_html()
        self._compute_messages()
        
        # Return a proper reload action instead of the non-existent 'do_nothing'
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
            'params': {
                'notification': {
                    'title': 'Refreshed',
                    'message': 'Chat interface updated',
                    'type': 'info'
                }
            }
        }

    @api.model
    def get_latest_messages(self, partner_id, last_message_id=None):
        """API method to get latest messages for real-time updates"""
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
            'create_date': msg.create_date.isoformat(),
            'state': msg.state,
            'message_type': msg.message_type,
            'media_type': msg.media_type,
            'caption': msg.caption,
            'template_name': msg.template_name,
            'error_message': msg.error_message
        } for msg in messages]