import bottle
import simplejson as json

bottle.debug(True)

from bottle import route, template, request, AppEngineServer
from downloads import get_stored_downloads, get_single_download, store_newest_downloads

single_download = get_single_download()

@route("/tasks/currentversion_v1")
def currentversion():
    return template("currentversion_v1", version=json.dumps(single_download["version"]))


@route("/tasks/updatedownloads_v1")
def update_downloads():
    credentials = (request.GET.get('username'), request.GET.get('password'))
    if store_newest_downloads(credentials) is not None:
        return "OK"

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
