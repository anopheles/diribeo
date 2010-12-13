import bottle

#bottle.debug(True)

import currentversion

from bottle import route, view, template, AppEngineServer
from google.appengine.ext.appstats.recording import appstats_wsgi_middleware

from google.appengine.ext.webapp import util

import simplejson as json 

# Taken from main diribeo app
def version_to_string(version):
	version = json.loads(version)["version"]
	return ".".join([str(x) for x in version])

version = currentversion.return_version()
edited_version = version_to_string(version)
	
@route("/tasks/currentversion_v1")
def currentversion():
	return template("currentversion_v1", version = version)

@route("/contribute")
def contribute():
	return template("contribute", version = edited_version)

@route("/tutorial")
def tutorial():
	return template("tutorial", version = edited_version)

@route("/contact")
def contact():
	return template("contact", version = edited_version)

@route("/faq")
def faq():
	return template("faq", version = edited_version)

@route("/:overview")
@route("/")		
def default(overview=""):
	return template("overview", version = edited_version)


bottle.run(server=AppEngineServer)
