import bottle
from bottle import route, run

bottle.debug(True)

from bottle import route, view, template
from google.appengine.ext.webapp import util 


@route("/contribute")
def contribute():
	print template("contribute")

@route("/tutorial")
def tutorial():
	print template("tutorial")

@route("/contact")
def contact():
	print template("contact")

@route("/faq")
def faq():
	print template("faq")

@route("/:overview")
@route("/")		
def default(overview=""):
	print template("overview")


util.run_wsgi_app(bottle.default_app())
