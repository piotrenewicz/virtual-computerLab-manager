def init():
    import sqlite3

    connection = sqlite3.connect('database.db')

    with open('schema.sql') as f:
        connection.executescript(f.read())

    cur = connection.cursor()
    cur.execute("INSERT INTO config(option, value) VALUES (?, ?)", ("first-run", 1))
    connection.commit()
    connection.close()


if __name__ == "__main__":
    init()
