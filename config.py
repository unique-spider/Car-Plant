import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "carplant-secret-key-change-in-prod")

    DB_HOST     = os.environ.get("DB_HOST", "localhost")
    DB_USER     = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "Anbu&2006")
    DB_NAME     = os.environ.get("DB_NAME", "car_plant_db")
    DB_PORT     = int(os.environ.get("DB_PORT", "3306"))
