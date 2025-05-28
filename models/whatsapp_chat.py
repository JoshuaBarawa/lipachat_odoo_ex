from odoo import models, fields, api

class WhatsappChat(models.TransientModel):
    _name = 'whatsapp.chat'
    _description = 'WhatsApp Chat Mock Static'
    _transient = True  # Because it’s just for demo, transient model (no DB storage)

    # Static mock contacts as a selection field
    contact = fields.Selection(
        [('alice', 'Alice'), ('bob', 'Bob'), ('charlie', 'Charlie')],
        string="Contact",
        required=True,
        default='alice',
    )
    messages = fields.Text(string="Chat Messages", readonly=True)
    new_message = fields.Text(string="New Message")

    @api.onchange('contact')
    def _onchange_contact(self):
        mock_chats = {
            'alice': "Alice: Hi there!\nYou: Hello Alice!",
            'bob': "Bob: How's it going?\nYou: All good, Bob!",
            'charlie': "Charlie: Let's meet up.\nYou: Sure thing, Charlie!",
        }
        self.messages = mock_chats.get(self.contact, '')

    def send_message(self):
        if self.new_message:
            self.messages = (self.messages or '') + f"\nYou: {self.new_message}"
            self.new_message = ''
