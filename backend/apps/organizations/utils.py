DEFAULT_ORG_SETTINGS = {
    'auto_create_medical_record': True,
    'auto_create_invoice_on_done': True,
    'require_confirmation_before_start': False,
    'allow_anonymous_walkin': False,
    'show_status_change_history': True,
}


def get_org_setting(org, key):
    settings = getattr(org, 'settings', None)
    if settings and hasattr(settings, key):
        return getattr(settings, key)
    return DEFAULT_ORG_SETTINGS[key]
