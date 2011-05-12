''' This script is responsible for creating a feasible windows version of diribeo.
It does this by following http://ms4py.org/2010/05/05/python-portable-windows/ 


The only thing this script does is copy the diribeo folder into the right place
and simply zips the result into a single file.

Currently there is no installer.


Some code taken from http://bytes.com/topic/python/answers/851018-how-zip-directory-python-using-zipfile
'''

from __future__ import division

import shutil
import zipfile
import os
import subprocess
import shlex
import sys

from ftplib import FTP
from functools import partial

# Declare some hosting constants, these are used ase identifiers
HF = "hotfile"
RS = "rapidshare"

# Defines the block size of the chucks being uploaded
UPLOAD_BLOCKSIZE = 8192 * 2 ** 2

zip_name = "diribeowin32.zip"
assemble_folder = "diribeowin32"

def makeArchive(fileList, archive):
    """
    'fileList' is a list of file names - full path each name
    'archive' is the file name for the archive with a full path
    """

    a = zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED)
    for f in fileList:
        print "archiving file %s" % f
        a.write(f)
    a.close()


def dirEntries(dir_name, subdir, *args):
    '''Return a list of file names found in directory 'dir_name'
    If 'subdir' is True, recursively access subdirectories under 'dir_name'.
    Additional arguments, if any, are file extensions to match filenames. Matched
        file names are added to the list.
    If there are no additional arguments, all files found in the directory are
        added to the list.
    Example usage: fileList = dirEntries(r'H:\TEMP', False, 'txt', 'py')
        Only files with 'txt' and 'py' extensions will be added to the list.
    Example usage: fileList = dirEntries(r'H:\TEMP', True)
        All files and all the files in subdirectories under H:\TEMP will be added
        to the list.
    '''
    fileList = []
    for file in os.listdir(dir_name):
        dirfile = os.path.join(dir_name, file)
        if os.path.isfile(dirfile):
            if not args:
                fileList.append(dirfile)
            else:
                if os.path.splitext(dirfile)[1][1:] in args:
                    fileList.append(dirfile)
        # recursively access file names in subdirectories
        elif os.path.isdir(dirfile) and subdir:
            print "Accessing directory:", dirfile
            fileList.extend(dirEntries(dirfile, subdir, *args))
    return fileList


def delete_everything(top):
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))


def ignore_dir(current_dir, sub_files):
    nogoes = shutil.ignore_patterns("*.pyc")(current_dir, sub_files)
    if current_dir == "../../diribeo":
        return set(["ffmpeg.exe", ".git", ".settings", "externals & studies", "tests", ".gitignore", ".project",
                    ".pydevproject", "logger_output.out", "web"]).union(nogoes)
    return nogoes


class Counter():
    def __init__(self):
        self.value = 1

    def increment(self):
        self.value += 1


def upload_feedback(hoster, counter, uploaded_date):
    file_size = os.path.getsize(zip_name)
    counter.increment()
    upload_progress = (counter.value * UPLOAD_BLOCKSIZE) / file_size
    print 'Uploading to: %s %.2f%%' % (hoster, upload_progress * 100)


def upload(*mode, **kwargs):
    try:
        credentials = kwargs['credentials']
    except KeyError:
        credentials = None

    if credentials is not None:
        username, password = credentials
        
        if RS in mode:
            print "Uploading to Rapidshare"
            args = shlex.split("perl rsapiresume.pl %s %s %s 1 2" % (zip_name, username, password))
            subprocess.Popen(args, shell=True).communicate()
            print "Finished Uploading to Rapidshare"

        if HF in mode:
            print "Uploading to Hotfile"
            ftp = FTP('ftp.hotfile.com')
            ftp.login(user="schleifer", passwd=password)
            ftp.storbinary('STOR diribeo/' + zip_name, open(zip_name, 'rb'), blocksize=UPLOAD_BLOCKSIZE,
                           callback=partial(upload_feedback, HF, Counter()))
            ftp.quit()
            print "Finished Uploading to Hofile"

if __name__ == "__main__":
    try:
        credentials = sys.argv[1:3]
    except ValueError:
        print "No credentials specified"

    assemble_folder_path = os.path.join(assemble_folder, "diribeo")
    if os.path.isdir(assemble_folder_path):
        print "Deleting diribeo"
        shutil.rmtree(assemble_folder_path)

    print "Starting copy"
    shutil.copytree("../src", assemble_folder_path, ignore=ignore_dir)
    print "Finished copy action"

    makeArchive(dirEntries(assemble_folder, True), zip_name)
    print "Finished creating archieve"

    print "Uploading File"
    upload(HF, credentials=credentials)
    print "Finished uploading File"