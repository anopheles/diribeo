import cgi

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import db

import urllib2
import simplejson as json
import re

class Version(db.Model):
    number = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)

    def get_current_version(self):
        url = "https://github.com/anopheles/diribeo/raw/master/diribeo.py"
        try:
            result = urllib2.urlopen(url)
            for line in result:
                if "__version__" in line:
                    m = re.search(r"(.*)=(.*)", line)
                    version = [x for x in re.split('\W+', m.group(2)) if x != ""]
                    dictionary = {"version" : self.integerfy(version)}
                    return json.dumps(dictionary)
        except urllib2.URLError, e:
            print e
            return None

    def integerfy(self, input):
        output = []
        for x in input:
            try:
                output.append(int(x))
            except ValueError:
                output.append(x)
        return output


current_version = Version()
current_version.number = current_version.get_current_version()  
current_version.put() 
