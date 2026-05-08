SETTING_AUTO_MEDICAL_RECORD = 'auto_create_medical_record'
SETTING_AUTO_INVOICE_ON_DONE = 'auto_create_invoice_on_done'

DEFAULT_ORG_SETTINGS = {
    SETTING_AUTO_MEDICAL_RECORD: False,
    SETTING_AUTO_INVOICE_ON_DONE: False,
    'require_confirmation_before_start': False,
    'allow_anonymous_walkin': False,
    'show_status_change_history': True,
}


def get_org_setting(org, key):
    settings = getattr(org, 'settings', None)
    if settings and hasattr(settings, key):
        return getattr(settings, key)
    return DEFAULT_ORG_SETTINGS[key]
