import mysql.connector

dataBase = mysql.connector.connect(
    host="localhost",
    user="root",
    password="password",

)

cursorObject = dataBase.cursor()
cursorObject.execute("CREATE DATABASE elderco")

print("All Done!")