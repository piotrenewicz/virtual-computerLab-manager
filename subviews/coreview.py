import utils as u
from flask import Blueprint, render_template, request, redirect, session, url_for


core_app = Blueprint('core', __name__, template_folder='templates')


@core_app.route('/group-overview', methods=('GET',))
def overview():
    with u.db_session() as cursor:
        cursor.execute('select groupID, groupName from group_table')
        groups = cursor.fetchall()

    return render_template('overview.html', groups=groups)


@core_app.route('/group/<int:group_id>/')
def group_detail(group_id:int):
    group_info = {'id': group_id}
    with u.db_session() as cursor:
        cursor.execute('select groupName from group_table where groupID= ?', (group_id,))
        group_info['name'] = u.one_row_fix(cursor.fetchone())
        cursor.execute('''
            select ut.userID, ut.fullname 
            from user_table ut inner join group_content gc 
            on ut.userID = gc.userID
            where gc.groupID = ?
        ''', (group_id,))
        group_info['members'] = cursor.fetchall()
        cursor.execute('select allocationID, allocationName from allocation_table where groupID = ?', (group_id,))
        group_info['alloc'] = cursor.fetchall()

    dir = [("Grupa:"+group_info['name'], '#')]

    return render_template('group.html', group_info=group_info, dir=dir)


@core_app.route('/group-new/')
def add_group():
    with u.db_session() as cursor:
        cursor.execute("insert into group_table(groupName) values ('New Group') RETURNING groupID;")
        new_id = u.one_row_fix(cursor.fetchone())

    return redirect(url_for('core.group_detail', group_id=new_id))


