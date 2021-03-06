import traceback

import requests.exceptions

import utils as u
from flask import Flask, render_template, request, url_for, redirect, session, flash
from subviews.configview import config_app
from subviews.loginview import login_app
from subviews.coreview import core_app
from subviews.dependentsview import dependency_app

app = Flask(__name__)
u.configured = u.check_configured()

app.config.update(
    SECRET_KEY=u.get_config_value('SECRET_KEY') or "DEFAULT SECRET KEY. NOT VERY SECRET",
    # SESSION_COOKIE_SECURE=True,  # uncomment this line in production with https to ensure sessions can't get leaked
)

app.register_blueprint(config_app)
app.register_blueprint(login_app)
app.register_blueprint(core_app)
app.register_blueprint(dependency_app)


@app.context_processor
def inject_default_context():
    return dict(
        toast_category_map={
            'error': 'bg-danger bg-opacity-75 text-light',
            'info': 'bg-warning bg-opacity-75',
            'success': 'bg-success bg-opacity-75 text-light',
        },

    )


@app.before_request
def verify_session():
    if not u.configured or \
            request.path.startswith((url_for('login.login'), url_for('static', filename=''))):
        return None

    if not session.get('login'):
        session['login/return'] = request.url
        return redirect(url_for('login.login'))

    if request.path == url_for('config.sync_database', target=2) and session.get('permLevel') == 3:
        return None  # allow syncing proxmox vms to vm maintainers.

    if request.path.startswith(url_for('config.configuration')) and session.get('permLevel') != 4:
        flash('Brak Uprawnień, Odmowa Dostępu', 'error')
        return redirect(request.referrer or '/')


@app.route('/set_preferred_userquery/<int:handle_type>', methods=('POST',))
def user_type_select(handle_type):
    session['preferUserQuery'] = handle_type
    _ = request.get_data()
    return redirect(request.referrer or '/')


@app.route('/')
def index():
    return redirect(url_for('core.group_list' if u.configured else 'config.configuration'))


@app.errorhandler(requests.exceptions.RequestException)
@app.errorhandler(u.ResourceException)
def handle_basic_error(error):
    flash(error.__repr__(), 'error')
    return redirect(request.referrer or '/')


@app.errorhandler(KeyError)
def handle_proxmox_errors(error):
    flash(traceback.format_exc(), 'error')
    return redirect(request.referrer or '/')


# great idea for production, when you don't want to leak server code.
# @app.errorhandler(Exception)
# def unexpected_exception_handler(error):
#     if app.env == 'production':
#         return 'Internal Error', 500
#     else:
#         raise error


# when shipping remember to put a block here, we don't want to allow production use of development mode
if __name__ == "__main__":
    def get_ip():
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    app.env = "development"
    app.run(host=get_ip(), port=5000, debug=True)
