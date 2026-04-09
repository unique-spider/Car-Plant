import mysql.connector

conn = mysql.connector.connect(
    host="127.0.0.1",
    user="root",
    password="Anbu&2006",
    database="car_plant_db",
    auth_plugin="mysql_native_password",
)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS ISSUE_LOG (
    Issue_ID       INT AUTO_INCREMENT PRIMARY KEY,
    Car_ID         INT NOT NULL,
    Reporter_ID    INT NOT NULL,
    Description    TEXT NOT NULL,
    Status         ENUM('open', 'resolved') NOT NULL DEFAULT 'open',
    Created_At     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Resolved_At    TIMESTAMP NULL,
    CONSTRAINT fk_il_car FOREIGN KEY (Car_ID) REFERENCES CAR_PRODUCTION(Car_ID) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_il_reporter FOREIGN KEY (Reporter_ID) REFERENCES USER(User_ID) ON DELETE RESTRICT ON UPDATE CASCADE
)
""")
conn.commit()
cursor.close()
conn.close()
print("Table created successfully!")
