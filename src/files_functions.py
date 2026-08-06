# from dotenv import find_dotenv, load_dotenv
# from decouple import config

def get_copernicus_key():
     
     from dotenv import find_dotenv, load_dotenv
     from decouple import config
     """
     This function returns the key and user of the web data acces
     """
     if not find_dotenv(".env"):
         raise FileNotFoundError("File not found: '.env'")
     _ = load_dotenv(find_dotenv(".env"))
     user = config("COPERNICUS_USER", cast=str)
     key = config("COPERNICUS_KEY", cast=str)
     return user, key, _


def get_ecmwf_key():
     
     from dotenv import find_dotenv, load_dotenv
     from decouple import config
     """
     This function returns the key and user of the web data acces
     """
     if not find_dotenv(".env"):
         raise FileNotFoundError("File not found: '.env'")
     _ = load_dotenv(find_dotenv(".env"))
     url = config("ECMWF_URL", cast=str)
     key = config("ECMWF_KEY", cast=str)
     email = config("ECMWF_EMAIL", cast=str)
     return url, key, email


def load_config(config_file):
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("config", config_file)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    return config