import utils as u
from flask import Blueprint, render_template, request, redirect, session


login_app = Blueprint('login', __name__, template_folder='templates')


@login_app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        if u.perform_login():
            return redirect(session.pop('login/return', None) or request.root_url)
        # posted wrong login info

    return render_template('login.html')


@login_app.route('/login/logout', methods=('GET', 'POST'))
def logout():
    session.pop('login', None)
    session.pop('permLevel', None)
    return redirect(request.root_url)
