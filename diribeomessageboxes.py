# -*- coding: utf-8 -*-
'''
Created on 05.07.2010

@author: anopheles
'''
import os

from PyQt4 import QtGui


def nothing_found_warning():
    #TODO        
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "NOTHING FOUND", "")
    messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
    messagebox.setInformativeText("The movie clip is already associated with this episode")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok)
    messagebox.exec_()


             
def error_in_thumbnail_creation_warning(movieclip, episode):
    #TODO
    filepath = movieclip.filepath
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "ERROR in THUMBNAIL creation", "")
    messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
    messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with this episode")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(filepath)
    messagebox.exec_()

def already_exists_warning(movie, filepath):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated", "")
    messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
    messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with this episode")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(filepath)
    messagebox.exec_()

def filesystem_error_warning(movie, filepath):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Filesystem Error", "")
    messagebox.setText("You must add a movie clip file to an episode.")
    messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(filepath)
    messagebox.exec_()

def no_internet_connection_warning():
    #TODO
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "NO INTERNET CONNECTION", "")
    messagebox.setText("You must add a movie clip file to an episode.")
    messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText("nothing")
    messagebox.exec_()


def association_found_info(movie, episode):
    #TODO
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "Association FOUND", "")
    messagebox.setText("You must add a movie clip file to an episode.")
    messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText(str(episode))
    messagebox.exec_()

def no_association_found(self, mainwindow):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "No Association found", "")
    messagebox.setText("No association found")
    messagebox.setInformativeText("ballala")
    feeling_lucky_button = messagebox.addButton("Feeling Lucky", QtGui.QMessageBox.AcceptRole)
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
    messagebox.setDetailedText("")
    messagebox.exec_()
    
    try:
        if messagebox.clickedButton() == feeling_lucky_button:                
            mainwindow.guess_episode_with_movieclip(self.sender().movieclip, self.sender().series)
            self.sender().quit()
    except AttributeError:
        pass

def display_duplicate_warning(self):
    messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated", "")
    messagebox.setText("The movie clip is already associated with another movie.")
    messagebox.setInformativeText("Are you sure you want to assign this movie clip to this movie")
    messagebox.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel) 
    result = messagebox.exec_()
    
    if result == QtGui.QMessageBox.Ok:
        self.sender().assign()
    else:
        self.sender().load_information.emit(self.sender().episode)
        self.sender().quit()