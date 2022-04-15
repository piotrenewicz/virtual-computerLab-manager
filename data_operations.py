import sqlite3

class db_session(object):
    def __init__(self, filename='database.db'):
        self.filename = filename

    def __enter__(self):
        self.conn = sqlite3.connect(self.filename)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.commit()
        self.conn.close()


def with_database(funciton):
    def wrapped(*args, **kwargs):
        if not 'cursor' in kwargs or type(kwargs['cursor']) != sqlite3.Cursor:
            with db_session() as cursor:
                result = funciton(*args, **kwargs, cursor=cursor)
        else:
            result = funciton(*args, **kwargs)
        return result

    return wrapped


def one_row_fix(row: (sqlite3.Row, None)):
    if row is None:
        return None
    if len(row.keys()) == 1:
        return row[0]
    return dict(row)

@with_database
def get_config_section(section: int, cursor: sqlite3.Cursor):
    cursor.execute('select option, value from config where section == ?', (section,))
    return {row['option']: row['value'] for row in cursor.fetchall()}

@with_database
def get_config_value(option: str, cursor: sqlite3.Cursor):
    cursor.execute('select value from config where option == ?', (option,))
    return one_row_fix(cursor.fetchone())


#
# this next function is really cool
# what happens is: I have an optional argument followed by a required argument
# In python normally that would be a syntax error,
# but the underlying reason for that error, isn't about required state, it's about (*args, **kwargs)
# usually in such situation required also means positional. And optional also means keyword
# the trick is to create a required keyword argument. We can't use '=', because that would make it optional.
#
# Now the special thing about my def below is the "*," argument.
# I found out about that functionality here: https://stackoverflow.com/questions/56939639/default-values-for-positional-function-arguments-in-python
# What it does, is explicitly mark the starting point of the keyword only argument section.
# by_permission being before the *, is an optional keyword argument, that can be called positionally.
# cursor being after the *, can't be positional, it is defined as a keyword only argument,
# which means we don't need '=' to comply with the argtype order, and can make that arg required.
#

@with_database
def get_users(by_permission:(None, int, list) = None, *, cursor: sqlite3.Cursor):
    if by_permission is None:
        return cursor.execute('select userID, fullname from user_table').fetchall()
    if not by_permission is list:
        by_permission = [by_permission]
    output = []
    for permission in by_permission:
        cursor.execute('select userID, fullname from user_table where userPermission = ?', (permission,))
        output.extend(cursor.fetchall())
    return output
