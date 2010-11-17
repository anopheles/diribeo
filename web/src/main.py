import bottle

from bottle import route, view, template
from google.appengine.ext.webapp import util

bottle.debug(False)

@route("/currentversion")
def update():
	return template("currentversion")

@route("/contribute")
def contribute():
	return template("contribute")

@route("/tutorial")
def tutorial():
	return template("tutorial")

@route("/contact")
def contact():
	return template("contact")

@route("/faq")
def faq():
	return template("faq")

@route("/:overview")
@route("/")		
def default(overview=""):
	return template("overview")


util.run_wsgi_app(bottle.default_app())
