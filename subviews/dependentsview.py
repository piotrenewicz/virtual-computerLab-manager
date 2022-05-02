import utils as u
from flask import Blueprint, render_template

dependency_app = Blueprint('dep', __name__, template_folder='templates')


@dependency_app.route('/depend/')
def dependents_view():
    with u.db_session() as cursor:
        cursor.execute('select node from vmid_table group by node')
        cluster = {row['node']: {} for row in cursor.fetchall()}
        for node in cluster.keys():
            cursor.execute('select vmid from vmid_table where type = 1 and node = ?', (node,))
            cluster[node] = {row['vmid']: {} for row in cursor.fetchall()}
            for template in cluster[node].keys():
                cursor.execute('select allocationID, groupID, allocationName from allocation_table where templateID = ?', (template,))
                cluster[node][template] = cursor.fetchall()
    return render_template('dependents.html', cluster=cluster)

#    cluster: {
#       'pve': {  # node on cluster
#           102: [  # template found on node
#               {  # allocation of that template
#                   'allocationID': 1,
#                   'allocationName': 'lab3',
#                   'groupID': 1,
#               },
#               {
#                   'allocationID': 3,
#                   'allocationName': 'mmx',
#                   'groupID': 2,
#               }
#           ],
#           103: [
#               {
#                   'allocationID': 2
#                   'allocationName': 'lk',
#                   'groupID': 3,
#               }
#           ]
#       }
#   }
#
