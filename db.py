# from flask_mysqldb import MySQL

# mysql = MySQL()

# def init_db(app):
#     app.config['MYSQL_HOST'] = 'localhost'
#     app.config['MYSQL_USER'] = 'root'
#     app.config['MYSQL_PASSWORD'] = 'password'
#     app.config['MYSQL_DB'] = 'mess_management'

#     mysql.init_app(app)

from flask_mysqldb import MySQL

mysql = MySQL()

# Used by JWT token signing — keep this secret in production
JWT_SECRET  = 'mess_management_jwt_secret_cs432'
JWT_EXPIRY_HOURS = 24   # token valid for 24 hours

def init_db(app):
    app.config['MYSQL_HOST']     = 'localhost'
    app.config['MYSQL_USER']     = 'root'
    app.config['MYSQL_PASSWORD'] = 'Teja@0909'
    app.config['MYSQL_DB']       = 'mess_management'

    mysql.init_app(app)