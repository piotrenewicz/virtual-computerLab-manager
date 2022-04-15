from service_utils import *
from flask import session, request, flash



def check_configured():
    try:
        first_run = get_config_value('first-run')
    except sqlite3.OperationalError:
        first_run = None
    if first_run is None:
        import init_database
        init_database.init()
        return False
    elif first_run == 1:
        return False
    elif first_run == 0:
        return True
    else:
        raise Exception("Non-binary first-run value!")



def active_section(section_id, when_active, when_hidden):
    def is_active(section_id):
        if session.get('config/active_section') is None:
            if section_id == 1:
                return True
            return False
        elif session['config/active_section'] == section_id:
            return True
        return False

    if is_active(section_id):
        return when_active
    return when_hidden



def form_reader(section):
    if section == 1:
        return {
            'host': request.form.get('InputProxmoxAddress'),
            'user': request.form.get('InputProxmoxBotUser'),
            'password': request.form.get('InputProxmoxBotPass'),
            'verify_ssl': 0 if request.form.get('InputProxmoxSSL') is None else 1
        }
    elif section == 2:
        return {
            'url': request.form.get('InputLdapAddress'),
            'base': request.form.get('InputLdapBase'),
            'filter': request.form.get('InputLdapFilter')
        }
    elif section == 4:
        return {
            'userID': request.form.get('InputPermUser'),
            'perm': request.form.get('InputPermPerm')
        }
    elif section == 5:
        return {
            'SECRET_KEY': request.form.get('SECRET_KEY'),
            'first-run': 0 if request.form.get('InputFirstRun') else 1
        }


def check_proxmox(kwargs):
    try:
        ProxmoxAPI(**kwargs)
    except Exception as e:
        flash(e.__repr__(), 'error')
        return False
    return True


def check_ldap(kwargs):
    try:
        user_count = len(get_ldap_users(kwargs, False))
    except Exception as e:
        flash(e.__repr__(), 'error')
        return False
    if user_count == 0:
        flash("Filter returned 0 users!", 'error')
        return False
    flash("Filter returned {} users!".format(user_count), 'info')
    return True


def validate_connection_params(target):
    kwargs = form_reader(target)
    if target == 1:
        return check_proxmox(kwargs)
    elif target == 2:
        return check_ldap(kwargs)