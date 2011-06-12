import time
import re
import simplejson as json
import credentials as credentials_module

from pyfilehoster import RapidShareAPI, HotFileAPI
from google.appengine.ext import db

class Downloads(db.Model):
    downloads_string = db.TextProperty()
    date = db.DateTimeProperty(auto_now_add=True)


def get_stored_downloads():
    downloads_list = db.GqlQuery("SELECT * FROM Downloads ORDER BY date DESC")
    download_dict = None
    for downloads in downloads_list:
        if downloads.downloads_string is not None:
            download_dict = json.loads(downloads.downloads_string)
            break

    #Uncomment the following line to directly use http as input
    #download_dict = store_newest_downloads()
    return download_dict

def get_single_download():
    """
        returns the most recent rapidshare download link
    """
    try:
        return get_stored_downloads()["Rapidshare"][0]
    except TypeError:
        pass

def store_newest_downloads(update_credentials):
    download_links = dict()
    credentials = credentials_module.get_credential()

    if update_credentials == credentials:
        rsapi = RapidShareAPI(credentials=credentials) #folderid="6834"
        download_links["Rapidshare"] = rsapi.get_download_links(fields="filename,size,uploadtime")

        hfapi = HotFileAPI(credentials=credentials)
        download_links["Hotfile"] = hfapi.get_download_links(folderid="1701142", hashid="2e37c99")

        result = {}

        for hoster, downloads in download_links.iteritems():
            for properties in downloads.itervalues():
                try:
                    # Convert time string into a more readable form:
                    properties["date"] = time.ctime(float(properties["uploadtime"]))
                except KeyError:
                    pass

                properties["version"] = None

                try:
                    version = re.search(r'diribeowin32_([\w].*).zip', properties["filename"]).group(1)
                    properties["version"] = version

                    # only add if version info has been extracted properly
                    try:
                        result[hoster].append(properties)
                    except KeyError:
                        result[hoster] = list()
                        result[hoster].append(properties)

                except AttributeError:
                    pass # version info could not be extracted


        downloads = Downloads()
        downloads.downloads_string = json.dumps(result)
        downloads.put()

        # Sort each downloads by version
        for hoster, download_links in result.iteritems():
            result[hoster] = tuple(sorted(download_links, key=lambda item: item["version"], reverse=True))

        return result