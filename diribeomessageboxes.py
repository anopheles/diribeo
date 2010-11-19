# -*- coding: utf-8 -*-

import os

from PyQt4 import QtGui


def nothing_found_warning():      
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "Nothing was found", "")
    messagebox.setText("Nothing was found.")
    messagebox.setInformativeText("Make sure that you type in a valid series name and have at least one source selected.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok)
    messagebox.exec_()
             
def error_in_thumbnail_creation_warning(movieclip, episode):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Error in thumbnail creation", "")
    messagebox.setText("There was an error while trying to create the thumbnails for the episode: %s" % episode.get_normalized_name())
    messagebox.setInformativeText("Make sure that you have ffmpeg installed correctly.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.exec_()

def already_exists_warning(movie, filepath):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie clip already associated", "")
    messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
    messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with this episode.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(filepath)
    messagebox.exec_()

def no_internet_connection_warning():
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "No internet connection", "")
    messagebox.setText("There is no internet connection available. You must have a internet connection in order to download series.")
    messagebox.setInformativeText("Make sure that you have a internet connection.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok)
    messagebox.exec_()
    
def filesystem_error_warning(filepath):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Filesystem Error", "")
    messagebox.setText("You must add a movie clip file to an episode.")
    messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(filepath)
    messagebox.exec_()
    
def display_duplicate_warning():
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated", "")
    messagebox.setText("The movie clip is already associated with another movie.")
    messagebox.setInformativeText("This movie clip won't be added to the selected episode.")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel) 
    messagebox.exec_()