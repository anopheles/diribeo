from google.appengine.ext import db

DEFAULT_USERNAME = "username"
DEFAULT_PASSWORD = "password"

class Credential(db.Model):
    username = db.StringProperty()
    password = db.StringProperty()

def get_credential():
    credentials = db.GqlQuery("SELECT * FROM Credential")
    for credential in credentials:
        if credential.username is not None and credential.username != DEFAULT_USERNAME:
            return credential.username, credential.password

def initialize():
    cred = Credential()
    cred.username = DEFAULT_PASSWORD
    cred.password = DEFAULT_USERNAME
    cred.put()