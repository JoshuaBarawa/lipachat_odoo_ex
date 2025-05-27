from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import uuid

class SendWhatsappWizard(models.TransientModel):
    _name = 'send.whatsapp.wizard'
    _description = 'Send WhatsApp Message Wizard'

    partner_id = fields.Many2one('res.partner', 'Contact', required=True)
    phone_number = fields.Char('Phone Number', required=True)
    from_number = fields.Char('From Number')
    
    message_type = fields.Selection([
        ('text', 'Text Message'),
        ('media', 'Media Message'),
        ('buttons', 'Interactive Buttons'),
        ('list', 'Interactive List'),
        ('template', 'Template Message'),
        ('flow', 'WhatsApp Flow')
    ], 'Message Type', default='text', required=True)
    
    # Text message
    message_text = fields.Text('Message')
    
    # Media message
    media_type = fields.Selection([
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('DOCUMENT', 'Document'),
        ('AUDIO', 'Audio')
    ], 'Media Type')
    media_url = fields.Char('Media URL')
    caption = fields.Text('Caption')
    
    # Interactive buttons
    header_text = fields.Char('Header Text')
    body_text = fields.Text('Body Text')
    button_text = fields.Char('Button Text')
    button_1_id = fields.Char('Button 1 ID', default='1')
    button_1_title = fields.Char('Button 1 Title')
    button_2_id = fields.Char('Button 2 ID', default='2')
    button_2_title = fields.Char('Button 2 Title')
    button_3_id = fields.Char('Button 3 ID', default='3')
    button_3_title = fields.Char('Button 3 Title')
    
    # Template
    template_id = fields.Many2one('lipachat.template', 'Template')
    template_data = fields.Text('Template Parameters (JSON)')
    
    # Flow
    flow_id = fields.Many2one('lipachat.flow', 'Flow')
    flow_cta = fields.Char('Flow CTA')
    flow_screen = fields.Char('Flow Screen')
    flow_data = fields.Text('Flow Data (JSON)')
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.phone_number = self.partner_id.whatsapp_number or self.partner_id.mobile or self.partner_id.phone
    
    def send_message(self):
        """Send WhatsApp message"""
        if not self.phone_number:
            raise ValidationError(_('Phone number is required.'))
        
        config = self.env['lipachat.config'].get_active_config()
        
        # Create message record
        message_data = {
            'partner_id': self.partner_id.id,
            'phone_number': self.phone_number,
            'from_number': self.from_number or config.default_from_number,
            'message_type': self.message_type,
        }
        
        if self.message_type == 'text':
            message_data.update({
                'message_text': self.message_text,
            })
        elif self.message_type == 'media':
            message_data.update({
                'media_type': self.media_type,
                'media_url': self.media_url,
                'caption': self.caption,
            })
        elif self.message_type == 'buttons':
            buttons = []
            if self.button_1_title:
                buttons.append({'id': self.button_1_id, 'title': self.button_1_title})
            if self.button_2_title:
                buttons.append({'id': self.button_2_id, 'title': self.button_2_title})
            if self.button_3_title:
                buttons.append({'id': self.button_3_id, 'title': self.button_3_title})
            
            message_data.update({
                'body_text': self.body_text,
                'buttons_data': json.dumps(buttons),
            })
        elif self.message_type == 'template':
            message_data.update({
                'template_name': self.template_id.name if self.template_id else '',
                'template_language': self.template_id.language if self.template_id else 'en',
                'template_data': self.template_data or '{}',
            })
        elif self.message_type == 'flow':
            message_data.update({
                'flow_id': self.flow_id.flow_id if self.flow_id else '',
                'flow_cta': self.flow_cta,
                'flow_screen': self.flow_screen,
                'flow_data': self.flow_data or '{}',
                'body_text': self.body_text,
            })
        
        message = self.env['lipachat.message'].create(message_data)
        message.send_message()
        
        if message.state == 'sent':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('WhatsApp message sent successfully!'),
                    'type': 'success',
                }
            }
        else:
            raise ValidationError(_('Failed to send message: %s') % message.error_message)
            