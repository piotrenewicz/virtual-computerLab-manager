import sqlite3

connection = sqlite3.connect('database.db')

with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

#  cur.execute("INSERT INTO vmid_table(vmid, type) VALUES (?, ?)", (1, 0))
connection.commit()
connection.close()
