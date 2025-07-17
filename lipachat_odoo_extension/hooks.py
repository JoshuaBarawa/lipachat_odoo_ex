from odoo import api, SUPERUSER_ID
from datetime import datetime, timedelta

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref('your_module.ir_cron_auto_fetch_messages')
    if cron:
        cron.write({
            'nextcall': (datetime.now() + timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
        })