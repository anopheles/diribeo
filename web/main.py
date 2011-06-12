import bottle

bottle.debug(True)

from bottle import route, template, AppEngineServer
from downloads import get_stored_downloads, get_single_download

single_download = get_single_download()

@route("/tasks/currentversion_v1")
def currentversion():
	return template("currentversion_v1", version=single_download["version"])

@route("/downloads")
def downloads():
	return template("downloads", single_download=single_download, downloads=get_stored_downloads())

@route("/contribute")
def contribute():
	return template("contribute", single_download=single_download)

@route("/tutorial")
def tutorial():
	return template("tutorial", single_download=single_download)

@route("/contact")
def contact():
	return template("contact", single_download=single_download)

@route("/faq")
def faq():
	return template("faq", single_download=single_download)

@route("/:overview")
@route("/")		
def default(overview=""):
	return template("overview", single_download=single_download)


bottle.run(server=AppEngineServer)
