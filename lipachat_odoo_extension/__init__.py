from . import models
from . import wizard

from . import models
from . import wizard

def uninstall_hook(env):
    """Clean up cron jobs when uninstalling the module"""
    import logging
    
    _logger = logging.getLogger(__name__)
    
    # Search by name and model
    cron_jobs = env['ir.cron'].search([
        ('name', '=', 'Auto Fetch WhatsApp Messages'),
        ('model_id.model', '=', 'lipachat.message'),
    ])
    
    if cron_jobs:
        _logger.info(f"Found {len(cron_jobs)} cron job(s) to remove")
        for cron in cron_jobs:
            _logger.info(f"Stopping cron job: {cron.name}")
            # First deactivate
            cron.active = False
            # Then delete
            cron.unlink()
        _logger.info("All matching cron jobs removed")
    else:
        _logger.warning("No matching cron jobs found")