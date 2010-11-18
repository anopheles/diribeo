import cgi

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

import urllib2

try:
    import simplejson as json
except ImportError:
    import json
    

class Version(db.Model):
    number = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)

    def get_current_version(self):
        url = "https://github.com/anopheles/diribeo/raw/master/diribeo.py"
        try:
            result = urllib2.urlopen(url)
            for line in result:
                if "__version__" in line:
                    return ("{" + line.replace("=",":").replace("__", '"').replace("(", "[").replace(")", "]}")).replace("\n", "")
        except urllib2.URLError, e:
            pass


current_version = Version()
current_version.number = current_version.get_current_version()  
current_version.put() 
