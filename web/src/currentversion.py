import cgi

from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

class Version(db.Model):
    number = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)


versions = db.GqlQuery("SELECT * FROM Version ORDER BY date DESC LIMIT 1")

# Force site to send data
def return_version():
    for version in versions:
        return version.number