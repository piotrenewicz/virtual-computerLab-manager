import utils as u
from flask import Blueprint, render_template#, request, redirect, session


core_app = Blueprint('core', __name__, template_folder='templates')


@core_app.route('/group-overview', methods=('GET',))
def overview():

    return render_template('overview.html')


# @login_app.route('/login/logout', methods=('GET', 'POST'))
# def logout():
#     session.pop('login', None)
#     session.pop('permLevel', None)
#     return redirect(request.referrer)