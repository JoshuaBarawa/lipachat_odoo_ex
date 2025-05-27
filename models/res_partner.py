from odoo import models, fields, api, _

class ResPartner(models.Model):
    _inherit = 'res.partner'

    whatsapp_number = fields.Char('WhatsApp Number', help='WhatsApp number in international format (e.g., 254712345678)')
    lipachat_message_ids = fields.One2many('lipachat.message', 'partner_id', 'WhatsApp Messages')
    lipachat_message_count = fields.Integer('WhatsApp Messages', compute='_compute_lipachat_message_count')
    
    @api.depends('lipachat_message_ids')
    def _compute_lipachat_message_count(self):
        for partner in self:
            partner.lipachat_message_count = len(partner.lipachat_message_ids)
    
    def send_whatsapp_message(self):
        """Open wizard to send WhatsApp message"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'send.whatsapp.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_phone_number': self.whatsapp_number or self.mobile or self.phone,
            }
        }
    
    def view_whatsapp_messages(self):
        """View WhatsApp messages for this contact"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Messages'),
            'res_model': 'lipachat.message',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id}
        }