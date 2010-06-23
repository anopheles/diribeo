# -*- coding: utf-8 -*-

__author__ = 'David Kaufman'
__version__ = '0.0.1dev'
__license__ = 'pending'

import datetime
import json
import re
import sys
import os
import hashlib
import logging
import shutil
import subprocess

from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt
from collections import defaultdict


# Initialize the logger
log_filename = "logger_output.out"
logging.basicConfig(filename=log_filename,  format='%(asctime)s %(levelname)s %(message)s', level=logging.DEBUG, filemode='w')


class EpisodeTableModel(QtCore.QAbstractTableModel):
    def __init__(self, series, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.series = series        
        self.episodes = self.series.episodes

        self.row_lookup = lambda episode: ["", episode.title, episode.date, episode.plot]
        self.column_lookup = ["", "Title", "Date", "Plot Summary"]

    def insert_episode(self, episode):
        self.episodes.append(episode)
        self.insertRows(0,0,None) 

    def insertRows(self, row, count, modelindex):
        self.beginInsertRows(QtCore.QModelIndex(), row, count)
        self.endInsertRows()
        return True    
    
    def set_generator(self, generator):
        self.generator = generator

    def rowCount(self, index):
        return len(self.episodes)

    def columnCount(self, index):
        return len(self.column_lookup)

    def data(self, index, role):
        episode = self.episodes[index.row()]        
        if role == QtCore.Qt.DisplayRole: 
            return QtCore.QString(unicode(self.row_lookup(episode)[index.column()]))  
        elif role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                return create_default_image(episode)
        elif role == QtCore.Qt.BackgroundRole:
            return self.get_gradient_bg(episode.descriptor[0])
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        return QtCore.QVariant()     

    def get_gradient_bg(self, index):            
        gradient = QtGui.QLinearGradient(0, 0, 0, 200)
        backgroundcolor = get_color_shade(index, 5)
        comp_backgroundcolor =  get_complementary_color(backgroundcolor)
        gradient.setColorAt(0.0, comp_backgroundcolor.lighter(50))
        gradient.setColorAt(1.0, comp_backgroundcolor.lighter(150))
        return QtGui.QBrush(gradient)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                #the column
                return QtCore.QString(self.column_lookup[section])

class MovieClipAssociator(QtCore.QThread):
    ''' This class is responsible for associating a movie clip with a given episode.
        It emits various signals which can be used for feedback.
    '''
    
    finished = QtCore.pyqtSignal("PyQt_PyObject")
    waiting = QtCore.pyqtSignal()
    already_exists = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject") # This signal is emitted when the movieclip is already in the dict and in the folder
    filesystem_error = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    already_exists_in_another = QtCore.pyqtSignal() # Emitted when movieclip is in _another_ episode
    
    def __init__(self, filepath, movie):
        QtCore.QThread.__init__(self)
        self.movie = movie
        self.filepath = unicode(filepath) 

    def run(self):
        self.identifier = self.movie.get_identifier()
        
        if not os.path.isfile(self.filepath) or not settings.is_valid_file_extension(self.filepath):
            self.filesystem_error.emit(self.movie, self.filepath)
        else:
            self.waiting.emit()
            
            self.clip = MovieClip(self.filepath, identifier = self.movie.identifier)
            
            # Check and see if the movieclip is already associated with _another_ movie and display warning
            unique = movieclips.check_unique(self.clip, self.identifier)
            
            if not unique:
                self.already_exists_in_another.emit()
                self.exec_()
            else:
                self.assign()
            
    def assign(self):
            """ Here is a list of possibilities that might occur:
                    a) The clip is already in the movieclip dict and in its designated folder
                    b) The clip is already in the movieclip dict, but not in its designated folder
                    c) The clip is not in the movieclip dict but already in the folder
                    d) The clip is not in the movieclip dict and not in the folder
            """
            
            filename = os.path.basename(self.filepath)
            
            # Calculate hypothetical filepath
            destination = settings.calculate_filepath(self.movie, filename)
            directory = os.path.dirname(destination)
            
            if self.clip in movieclips[self.identifier]:
                
                if os.path.isfile(destination):
                    # a)
                    self.already_exists.emit(self.movie, self.filepath)
                    move_to_folder = False
                    add_to_movieclips = False                    
                else:
                    # b)
                    move_to_folder = True
                    add_to_movieclips = False
                    
            else:
                if os.path.isfile(destination):
                    # c)
                    move_to_folder = True
                    add_to_movieclips = True
                else:
                    # d)
                    move_to_folder = True
                    add_to_movieclips = True      
            
            if move_to_folder:
                # If there's a collison, rename the current file
                filename = settings.get_collision_free_filename(destination)
                
                # Move the file to the actual folder
                settings.move_file_to_folder_structure(self.movie, self.filepath, new_filename = filename)
                
                # Update the filepath of the clip            
                self.clip.filepath = os.path.join(directory, filename)

            if add_to_movieclips:
                # Add the clips to the movie clips manager
                movieclips.add(self.clip)                
                
            if move_to_folder or add_to_movieclips:
                # Save the movie clips to file
                save_movieclips()    
                            
            self.finished.emit(self.movie)


class MovieClipAssigner(QtCore.QThread):
    ''' This class is responsible for assigning a movie clip to a unknown episode.
        It calculates the hash value of a the given file and looks for matches in appropiate data structures.
        If no matches are found the "no_association_found' signal is emitted.
        If one or more matches are found the movie clip file is moved/copied to the designated folder.
    '''
    
    finished = QtCore.pyqtSignal()
    waiting = QtCore.pyqtSignal()
    no_association_found = QtCore.pyqtSignal()
    
    def __init__(self, filepath):
        QtCore.QThread.__init__(self)
        self.filepath = filepath
        
    def run(self):
        self.waiting.emit()
        
        movieclip = MovieClip(self.filepath)        
        possible_episodes, possible_movieclips = movieclips.get_episode_and_movieclip_list_with_matching_checksums(movieclip.checksum)        
        if len(possible_episodes) == 0:
            self.no_association_found.emit()
        else:
            self.assign(possible_episodes[0], possible_movieclips[0])
           
        self.finished.emit()

    def assign(self, episode, movieclip):
        # Calculate destination of movieclip
        destination = settings.calculate_filepath(episode, os.path.basename(self.filepath))
        
        # Extract directory
        directory = os.path.dirname(destination)
        
        # Check if there is already a file with the same name associated
        filename = settings.get_collision_free_filename(destination)                
        
        # Move the file to its folder
        settings.move_file_to_folder_structure(episode, self.filepath, new_filename = filename)
        
        # Change filepath on movieclip object
        movieclip.filepath = os.path.join(directory, filename)
        
        # Save movieclips to file 
        save_movieclips() 


class LocalSearch(QtGui.QFrame):

    def __init__(self, parent=None):
        QtGui.QFrame.__init__(self, parent)       

        self.setFrameShape(QtGui.QFrame.StyledPanel)
        localframelayout = QtGui.QVBoxLayout(self)
        self.setLayout(localframelayout)

        localsearchlabel = QtGui.QLabel("Serie's title: ")
        self.localsearchbutton = QtGui.QPushButton("Search")
        self.localsearchfield = QtGui.QLineEdit()        

        self.localseriestree = QtGui.QTreeWidget()
        self.localseriestree.setColumnCount(1)
        self.localseriestree.setHeaderLabels(["Series"])        
        self.localseriestree.setAnimated(True)
        self.localseriestree.setHeaderHidden(True)
        self.initial_build_tree()

        localsearchgrid = QtGui.QGridLayout()
        localsearchgrid.addWidget(localsearchlabel, 1 , 0)
        localsearchgrid.addWidget(self.localsearchfield, 1, 1)     
        localsearchgrid.addWidget(self.localsearchbutton, 1, 2)    

        localframelayout.addLayout(localsearchgrid)
        localframelayout.addWidget(self.localseriestree)
        
        self.toplevel_items = []
        
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):
        try:
            filepath = os.path.abspath(unicode(event.mimeData().urls()[0].toLocalFile()))
            mainwindow.find_episode_to_movieclip(filepath)
            event.accept()
        except IndexError:
            pass

    def sort_tree(self):
        # This also sorts children which produces a unwanted sorting
        pass
        #self.localseriestree.sortItems(0, Qt.AscendingOrder)


    def remove_series(self, series):        
        count = self.localseriestree.topLevelItemCount()
        for number in range(count):            
            item = self.localseriestree.topLevelItem(number)
            if item.series == series:
                delete_item = item
                
        self.localseriestree.removeItemWidget(delete_item, 0)
        self.localseriestree.takeTopLevelItem(self.localseriestree.indexOfTopLevelItem(delete_item))

    def insert_top_level_item(self, series):
        item = QtGui.QTreeWidgetItem([series.title])
        item.series = series        
        self.toplevel_items.append(item)
        self.localseriestree.addTopLevelItem(item)
        self.localseriestree.setCurrentItem(item)
        self.sort_tree()
            

    def initial_build_tree(self):
        for series in series_list:                 
            parent_series = QtGui.QTreeWidgetItem([series.title])
            parent_series.series = series
            self.build_subtree(parent_series)


    def build_subtree(self, parent_series):
        seasons = parent_series.series.get_seasons()
        for seasonnumber in seasons:
            child_season = QtGui.QTreeWidgetItem(parent_series,["Season " + str(seasonnumber)])
            child_season.series = parent_series.series
            for episode in seasons[seasonnumber]:
                child_episode = QtGui.QTreeWidgetItem(child_season,[episode.title]) 
                child_episode.series = parent_series.series
        self.localseriestree.addTopLevelItem(parent_series)

    def update_tree(self, series):    
        for toplevelitem in self.toplevel_items:
            if series == toplevelitem.series:                    
                self.build_subtree(toplevelitem)


class MovieClipInformationWidget(QtGui.QFrame):
    
    update = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, movieclip, movie, parent = None):
        QtGui.QFrame.__init__(self, parent)
        self.gridlayout = QtGui.QGridLayout()
        self.setLayout(self.gridlayout)
        self.setFrameShape(QtGui.QFrame.StyledPanel)
        
        self.control_layout = QtGui.QHBoxLayout()
        
        self.movieclip = movieclip
        self.movie = movie
        
        available = True
        if not os.path.isfile(movieclip.filepath):
            self.setStyleSheet("color:red")
            available = False
                    
        self.title = QtGui.QLabel()
        icon_start = QtGui.QIcon("images/media-playback-start.png")
        icon_remove = QtGui.QIcon("images/edit-clear.png")
        icon_delete = QtGui.QIcon("images/process-stop.png")
        icon_open = QtGui.QIcon("images/document-open.png")
        
        self.play_button = QtGui.QPushButton(icon_start, "")  
        self.remove_button = QtGui.QPushButton(icon_remove, "") 
        self.delete_button = QtGui.QPushButton(icon_delete, "")
        self.open_button = QtGui.QPushButton(icon_open, "")  
        
        if available:
            self.control_layout.addWidget(self.delete_button)
            self.control_layout.addWidget(self.play_button)
            self.control_layout.addWidget(self.open_button)
        
        self.control_layout.addWidget(self.remove_button)
        
        self.gridlayout.addWidget(QtGui.QLabel("Filename"), 0, 0)            
        self.gridlayout.addWidget(self.title, 1, 0)        
        self.gridlayout.addLayout(self.control_layout, 2, 0)
       
        self.play_button.clicked.connect(self.play)        
        self.delete_button.clicked.connect(self.delete)
        self.remove_button.clicked.connect(self.remove)
        self.open_button.clicked.connect(self.open_folder)
        
        self.load_information(movieclip)        

    def mousePressEvent(self, event):
        #TODO
        
        child = self.childAt(event.pos())
        if not child:
            return
        
        print type(event)
        print child, child.text()
            
        itemData = QtCore.QByteArray()
        dataStream = QtCore.QDataStream(itemData, QtCore.QIODevice.WriteOnly)
        dataStream << self.title.text() << QtCore.QPoint(event.pos() - self.rect().topLeft())

        mimeData = QtCore.QMimeData()
        mimeData.setData('application/x-fridgemagnet', itemData)
        mimeData.setText(self.title.text())
        
        image = QtGui.QPixmap.grabWidget(self, 0, 0, self.width(), self.height())
    
        drag = QtGui.QDrag(self)
        drag.setMimeData(mimeData)
        drag.setHotSpot(event.pos() - self.rect().topLeft())
        drag.setPixmap(image)

        self.hide()

        if drag.exec_(QtCore.Qt.MoveAction | QtCore.Qt.CopyAction, QtCore.Qt.CopyAction) == QtCore.Qt.MoveAction:
            print "close"
            self.close()
        else:
            print "show"
            self.show()

    def open_folder(self):
        try:
            os.startfile(self.movieclip.get_folder())
        except AttributeError:
            # Not very portable            
            subprocess.Popen(['nautilus', self.movieclip.get_folder()])
    
    def load_information(self, movieclip):
        self.title.setText(movieclip.get_filename())
     
    def delete(self):
        self.movieclip.delete_file_in_deployment_folder(self.movie.series)
        self.remove()
      
    def remove(self):
        movieclips.remove(self.movieclip, self.movie.get_identifier()) 
        self.update.emit(self.movie)
    
    def play(self):
        if os.path.isfile(self.movieclip.filepath):
            os.startfile(os.path.normpath(self.movieclip.filepath))

class MovieClipOverviewWidget(QtGui.QWidget):
    def __init__(self, parent = None, movieclips = None):
        QtGui.QWidget.__init__(self, parent)
        self.vbox = QtGui.QVBoxLayout()
        self.setLayout(self.vbox)        
        self.movieclipinfos = []
        self.draghere_label = QtGui.QLabel("To add movie clips drag them here")                
        self.vbox.addWidget(self.draghere_label)
    
    def load_movieclips(self, movie):
        
        self.remove_old_entries()
        assert len(self.movieclipinfos) == 0
                
        movieclips =  movie.get_movieclips()
        
        if movieclips != None and len(movieclips) > 0:
            self.draghere_label.setVisible(False)
            if movieclips != None:
                for movieclip in movieclips:
                    add = True
                    if not settings.get("show_all_movieclips"):
                        if not os.path.isfile(movieclip.filename):
                            add = False                    
                    if add:
                        info_item = MovieClipInformationWidget(movieclip, movie)
                        info_item.update.connect(self.load_movieclips)
                        self.movieclipinfos.append(info_item)
                        self.vbox.addWidget(info_item)
        else:
            self.draghere_label.setVisible(True)

    def remove_old_entries(self):
        for movieclipinfo in self.movieclipinfos:
            self.vbox.removeWidget(movieclipinfo)
            movieclipinfo.deleteLater()
        self.movieclipinfos = []


class SeriesInformationCategory(QtGui.QWidget):
    def __init__(self, label_name, type = QtGui.QLabel, spacing = 25, default = "-", parent = None):
        QtGui.QWidget.__init__(self, parent)        
        
        self.layout = QtGui.QVBoxLayout()
        self.setLayout(self.layout)
        self.spacing = spacing
        self.default = default
        self.title_label = QtGui.QLabel(label_name)
        default_font = self.title_label.font()
        default_font.setBold(True)       
        self.title_label.setFont(default_font)
        
        self.content = type()         
        
        self.layout.addWidget(self.title_label)
        self.layout.addWidget(self.content)
        self.layout.addSpacing(self.spacing)
        
    def set_content(self, input):
        self.content.setText(input)
        
    def set_description(self, input):
        self.title_label.setText(input)
        
    def setText(self, text):
        if text == None or text == "":
            text = self.default           
        self.set_content(text)

    def reset(self):
        self.set_content(self.default)


class SeriesInformationControls(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        header_layout = QtGui.QHBoxLayout()    
        self.update_button = QtGui.QPushButton("Update")
        self.delete_button = QtGui.QPushButton("Delete")
        header_layout.addWidget(self.delete_button)
        header_layout.addWidget(self.update_button)
        self.setLayout(header_layout)

class SeriesInformationWidget(QtGui.QWidget):
    
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)        
        
        self.layout = layout = QtGui.QVBoxLayout()
        self.setLayout(layout)              
        layout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
           
        self.nothing_to_see_here = QtGui.QLabel("There's nothing to see here")
        self.seenit = SeriesInformationCategory("Seen it?", type = QtGui.QCheckBox)
        self.title = SeriesInformationCategory("Title", type = SeriesInformationControls)
        self.movieclipwidget = SeriesInformationCategory("Movie Clips", type = MovieClipOverviewWidget)        
        self.director = SeriesInformationCategory("Director")
        self.rating = SeriesInformationCategory("Ratings")
        self.airdate = SeriesInformationCategory("Airdate")
        self.plot = SeriesInformationCategory("Plot", type = QtGui.QTextEdit)
        self.genre = SeriesInformationCategory("Genre")
        
        self.main_widgets = [self.title, self.seenit, self.movieclipwidget, self.director, self.rating, self.airdate, self.plot, self.genre]
        
        for widget in self.main_widgets:
            layout.addWidget(widget)
            
        self.nothing_to_see_here.hide()
        layout.addWidget(self.nothing_to_see_here)
        
        self.delete_button = self.title.content.delete_button
        self.update_button = self.title.content.update_button
        
        self.show_main_widget(False)
        
        self.setAcceptDrops(True)

    def main_widget_set_visibility(self, show):
        if show:
            for widget in self.main_widgets:
                widget.show() 
        else:
            for widget in self.main_widgets:
                widget.hide() 
                       
    def show_main_widget(self, show):
        if show:
            self.main_widget_set_visibility(True)
            self.nothing_to_see_here.hide()
        else:
            self.main_widget_set_visibility(False)
            self.nothing_to_see_here.show()

 
    def clear_all_info(self):
        self.show_main_widget(False)

    def load_information(self, movie):
        self.movie = movie
        
        self.show_main_widget(True)
        
        if isinstance(self.movie, Series):
            self.delete_button.setVisible(True)
            self.plot.setVisible(False)
            self.rating.setVisible(False)
        else:
            self.rating.setVisible(True)
            self.rating.setText(movie.get_ratings()) 
            self.plot.setText(movie.plot)
            self.plot.setVisible(True)
            self.delete_button.setVisible(False)
        
        # Handle the title
        try:
            self.title.set_description(movie.series[0] + " - " + movie.title + " - " + movie.get_descriptor())
        except AttributeError:
            self.title.set_description(movie.title)
        
        self.director.setText(movie.director) 
        self.airdate.setText(str(movie.date))
        self.genre.setText(movie.genre)
        self.movieclipwidget.content.load_movieclips(movie)          

        
    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):        
        try:
            filepath = event.mimeData().urls()[0].toLocalFile()
            mainwindow.add_movieclip_to_episode(filepath, self.movie)
            
        except AttributeError, IndexError:
            pass
        event.accept() 

            
class EpisodeViewWidget(QtGui.QTableView):    
    def __init__(self, parent = None):
        QtGui.QTableView.__init__(self, parent)
        self.verticalHeader().setDefaultSectionSize(125)
        self.horizontalHeader().setStretchLastSection(True)
        self.setShowGrid(False)
        self.setSelectionBehavior(QtGui.QTableView.SelectRows)

class SeriesInformationDock(QtGui.QDockWidget):
    def __init__(self, parent = None):
        QtGui.QDockWidget.__init__(self, parent)
        self.seriesinfo = SeriesInformationWidget() 
        scrollArea = QtGui.QScrollArea()
        scrollArea.setMinimumWidth(300) # TODO
        scrollArea.setWidget(self.seriesinfo)
        self.setWidget(scrollArea)
        self.setWindowTitle("Additional Information")
        self.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)

            
class LocalSearchDock(QtGui.QDockWidget):
    def __init__(self, parent = None):
        QtGui.QDockWidget.__init__(self, parent)
        self.local_search = LocalSearch()
        self.setWindowTitle("Local Library")
        self.tab = QtGui.QTabWidget()
        self.tab.setTabPosition(QtGui.QTabWidget.South)
        self.tab.addTab(self.local_search, "Local Library")
        self.dummywidget = QtGui.QWidget()
        self.tab.addTab(self.dummywidget, QtGui.QIcon("images/plus.png"), "Add Series")
        self.setWidget(self.tab)
        self.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        
        # Handle signals
        self.tab.currentChanged.connect(self.handle_tab_change)
        self.wizard = SeriesAdderWizard()
        
    def handle_tab_change(self, index):
        if index == self.tab.indexOf(self.dummywidget):
            self.tab.setCurrentWidget(self.local_search)
            self.wizard.restart()
            self.wizard.show()


class SeriesAdderWizard(QtGui.QWizard):
    selection_finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, parent = None):
       QtGui.QWizard.__init__(self, parent) 
       self.online_search = OnlineSearch()
       self.addPage(self.online_search)
       self.accepted.connect(self.wizard_complete)
    
    def wizard_complete(self):
        self.selection_finished.emit(self.online_search.onlineserieslist.selectedItems())

class SeriesSearchWorker(QtCore.QThread):
   
    def __init__(self, serieslist, searchfield, parent = None):
        QtCore.QThread.__init__(self, parent)
        self.serieslist = serieslist
        self.searchfield = searchfield

    def run(self):
        self.serieslist.clear()        
        result = imdbwrapper.search_movie(self.searchfield.text())
        for series_widget_item in result:             
            self.serieslist.addItem(series_widget_item)        
        
class OnlineSearch(QtGui.QWizardPage):
    def __init__(self, parent = None):
        QtGui.QWizardPage.__init__(self, parent)

        onlinelayout = QtGui.QVBoxLayout(self)
        self.setTitle("Online Search")
        self.setSubTitle("This is a ...")
        self.setLayout(onlinelayout)   

        onlinesearchlabel = QtGui.QLabel("Serie's title: ")
        self.onlinesearchbutton = QtGui.QPushButton("Search")
        self.onlinesearchfield = QtGui.QLineEdit()        
        self.onlineserieslist = QtGui.QListWidget()

        onlinesearchgrid = QtGui.QGridLayout()
        onlinesearchgrid.addWidget(onlinesearchlabel, 1 , 0)
        onlinesearchgrid.addWidget(self.onlinesearchfield, 1, 1)     
        onlinesearchgrid.addWidget(self.onlinesearchbutton, 1, 2)         

        onlinelayout.addLayout(onlinesearchgrid)
        onlinelayout.addWidget(self.onlineserieslist)
        
        self.seriessearcher = SeriesSearchWorker(self.onlineserieslist, self.onlinesearchfield)
        self.onlinesearchbutton.clicked.connect(self.search, Qt.QueuedConnection)
   
    def initializePage(self):
        self.onlineserieslist.clear()
        self.onlinesearchfield.clear()       
        
    def keyPressEvent(self, event):
       if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):           
           self.search()             
                  
    def search(self):
        if len(self.onlinesearchfield.text()) > 0:            
            self.seriessearcher.run()
            
        
class ModelFiller(QtCore.QThread):
    
    # Initialize various signals.
    waiting = QtCore.pyqtSignal()
    insert_into_tree = QtCore.pyqtSignal("PyQt_PyObject")
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal()
    update_tree = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, model, view, movie = None):
        QtCore.QThread.__init__(self)
        self.movie = movie
        self.model = model
        self.view = view
        self.series = self.model.series
        self.model.set_generator(imdbwrapper.get_episodes(movie))

    def run(self): 
                    
        episode_counter = 0

        # Make the progress bar idle
        self.insert_into_tree.emit(self.series)  
        self.waiting.emit()        
        self.view.seriesinfo.load_information(self.series)
        imdbwrapper.get_more_information(self.series, self.movie)
        self.view.seriesinfo.load_information(self.series)
            

        for episode, episodenumber in self.model.generator:            
            self.model.insert_episode(episode)            
            episode_counter += 1
            if episode_counter % 8 == 0:
                self.progress.emit(episode_counter, episodenumber)        
                
        save_series()            
        self.finished.emit()
        self.update_tree.emit(self.series)

class SeriesProgressbar(QtGui.QProgressBar):
    def __init__(self, parent=None, tablemodel = None):
        QtGui.QProgressBar.__init__(self, parent)
        self.workers = {}
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_progressbar)

    def waiting(self):        
        self.setValue(-1)
        self.setMinimum(0)
        self.setMaximum(0)  

    def stop(self):     
        self.setValue(-1)
        self.setMinimum(0)
        self.setMaximum(1)
        QtGui.QProgressBar.reset(self)

    def refresh_progressbar(self):
        current, maximum = map(sum, zip(*self.workers.values()))
        self.setValue(current)
        self.setMaximum(maximum)        

    def operation_finished(self):
        try:
            del self.workers[self.sender()]
        except KeyError:
            # Thread has already been deleted
            pass
        if len(self.workers) == 0:
            self.stop()
            self.timer.stop()

    def update_bar(self, current, maximum):        
        self.workers[self.sender()] = [current, maximum]
        if not self.timer.isActive():
            self.timer.start(1000);

class MainWindow(QtGui.QMainWindow):
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)

        self.existing_series = None # stores the currently active series object
        
        self.tableview = EpisodeViewWidget()
        self.setCentralWidget(self.tableview)

        # Initialize the status bar
        statusbar = QtGui.QStatusBar()
        statusbar.showMessage("Ready")
        self.setStatusBar(statusbar)
        
        # Initialize the progress bar and assign to the statusbar
        self.progressbar = SeriesProgressbar()  
        self.progressbar.setMaximumHeight(10)
        self.progressbar.setMaximumWidth(100)
        
        statusbar.addPermanentWidget(self.progressbar)        

        # Initialize the tool bar
        self.addToolBar(ToolBar())
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        # Initialize local search
        local_search_dock = self.local_search_dock = LocalSearchDock()
        self.local_search = local_search_dock.local_search
        
        # Initialize online search
        series_info_dock = SeriesInformationDock()
        self.seriesinfo =  series_info_dock.seriesinfo
        
        # Manage the docks
        self.addDockWidget(Qt.LeftDockWidgetArea, local_search_dock)                            
        self.addDockWidget(Qt.RightDockWidgetArea, series_info_dock)
       
        self.local_search_dock.wizard.selection_finished.connect(self.load_items_into_table)
        self.local_search.localseriestree.itemClicked.connect(self.load_into_local_table)         
        self.seriesinfo.delete_button.clicked.connect(self.delete_series)
        
        self.load_all_series_into_their_table()
        
        self.tableview.setModel(None)
        
        self.setWindowTitle("Diribeo")
        self.resize_to_percentage(66)
        self.center()

    def no_association_found(self):
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "No Association found", "")
        messagebox.setText("No association found")
        messagebox.setInformativeText("ballala")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText("")
        messagebox.exec_()
        
        try:
            self.sender().finished.emit()
        except AttributeError:
            pass
            

    def already_exists_warning(self, movie, filepath):
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated", "")
        messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
        messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with this episode")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText(filepath)
        messagebox.exec_()

    def filesystem_error_warning(self, movie, filepath):
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Filesystem Error", "")
        messagebox.setText("You must add a movie clip file to an episode.")
        messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText(filepath)
        messagebox.exec_()

    def display_duplicate_warning(self):
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated", "")
        messagebox.setText("The movie clip is already associated with another movie.")
        messagebox.setInformativeText("Are you sure you want to assign this movie clip to this movie")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel) 
        result = messagebox.exec_()
        if result == QtGui.QMessageBox.Ok:
            self.sender().assign()
        else:
            self.sender().finished.emit(self.sender().movie)
            self.sender().quit()


    def find_episode_to_movieclip(self, filepath):
        job = MovieClipAssigner(filepath)
        
        job.no_association_found.connect(self.no_association_found)
        job.waiting.connect(self.progressbar.waiting, type = QtCore.Qt.QueuedConnection)
        job.finished.connect(self.progressbar.stop, type = QtCore.Qt.QueuedConnection)
        
        jobs.append(job)            
        job.start()

    def add_movieclip_to_episode(self, filepath, movie):
        
        job = MovieClipAssociator(filepath, movie) 
        
        job.waiting.connect(self.progressbar.waiting, type = QtCore.Qt.QueuedConnection)
        job.finished.connect(self.progressbar.stop, type = QtCore.Qt.QueuedConnection)

        job.finished.connect(self.seriesinfo.load_information)
        job.already_exists.connect(self.already_exists_warning) 
        job.already_exists_in_another.connect(self.display_duplicate_warning)             
        job.filesystem_error.connect(self.filesystem_error_warning)
        
        jobs.append(job)
        job.start()
    
    def delete_series(self):                
        series = self.existing_series       
        
        # Make sure that you're actually deleting a series
        if series is not None:
            # Deletes the item in the tree widget
            self.local_search.remove_series(series)
            
            # Delete the series in the series_list
            for i, available_series in enumerate(series_list):
                if series == available_series:
                    del series_list[i]       
                    
            # Delete the series's tablemodel
            del active_table_models[series] 
            
            self.tableview.setModel(None)
            
            # Clear all information in the series information widget
            self.seriesinfo.clear_all_info()
            
            save_series()
        
    def center(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        size =  self.geometry()
        self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)


    def resize_to_percentage(self, percentage):
        screen = QtGui.QDesktopWidget().screenGeometry()
        self.resize(screen.width()*percentage/100.0, screen.height()*percentage/100.0)

    def load_into_local_table(self):
        index = self.local_search.localseriestree.selectionModel().currentIndex()
        parent = index
        indextrace = [] 

        while(parent.isValid() and parent.parent().isValid()): 
            parent = parent.parent()
            indextrace.append(parent)

        selected_items = self.local_search.localseriestree.selectedItems()
        
        if len(selected_items) > 0:
            existing_series = self.existing_series = selected_items[0].series                

            self.load_existing_series_into_table(existing_series)
            load_info = existing_series        
    
            if len(indextrace) == 0:
                #clicked on a series
                goto_row = 0            
            elif len(indextrace) == 1:
                #clicked on a season            
                goto_row = existing_series.accumulate_episode_count(index.row()-1)            
            else:
                #clicked on an episode            
                goto_row = existing_series.accumulate_episode_count(index.parent().row()-1) + index.row()             
                load_info = existing_series[goto_row]
    
            goto_index = active_table_models[existing_series].index(goto_row, 0)
    
            self.seriesinfo.load_information(load_info)
    
            self.tableview.scrollTo(goto_index, QtGui.QAbstractItemView.PositionAtTop)

    def load_episode_information_at_index(self, selected, deselected):        
        try:
            index = selected.indexes()[0]
            last_selection_model = self.tableview.selectionModel()
            
            same_row = False
            try:
                if self.last_selected_index.row() == index.row() and self.last_selection_model == last_selection_model:
                    same_row = True
            except AttributeError:
                pass
            
            if not same_row:
                self.seriesinfo.load_information(self.existing_series[index.row()])
                self.last_selected_index = index  
                self.last_selection_model = last_selection_model               
                self.tableview.selectRow(index.row())
  
        except IndexError:  
            pass  


    def load_all_series_into_their_table(self):
        for series in series_list:
            self.load_existing_series_into_table(series)        

    def load_existing_series_into_table(self, series):
        try:
            self.tableview.setModel(active_table_models[series]) 
            self.tableview.selectionModel().selectionChanged.connect(self.load_episode_information_at_index)
        except KeyError:                    
            active_table_models[series] = model = EpisodeTableModel(series)
            self.tableview.setModel(model)            
            
            
    def load_items_into_table(self, items):
        """ Loads the selected episodes from the clicked series in the onlineserieslist """
        
        assert len(items) == 1 # Make sure only one item is passed to this function since more than one item can cause concurrency problems     
        
        for item in items:           
            movie = item.movie

            existing_series = imdbwrapper.get_series_from_movie(movie)            
            
            if existing_series is None: 
                current_series = Series(item.title)
                series_list.append(current_series)
                active_table_models[current_series] = model = EpisodeTableModel(current_series)
                self.tableview.setModel(model)
                self.tableview.selectionModel().selectionChanged.connect(self.load_episode_information_at_index)
                
                self.existing_series = current_series                
                job = ModelFiller(model, self, movie = movie)
                
                job.finished.connect(self.progressbar.operation_finished, type = QtCore.Qt.QueuedConnection)
                job.waiting.connect(self.progressbar.waiting, type = QtCore.Qt.QueuedConnection)
                job.progress.connect(self.progressbar.update_bar, type = QtCore.Qt.QueuedConnection)
                job.update_tree.connect(self.local_search.update_tree, type = QtCore.Qt.QueuedConnection)
                job.insert_into_tree.connect(self.local_search.insert_top_level_item, type = QtCore.Qt.QueuedConnection)

                jobs.append(job)
                job.start()
                                  
            else:
                self.load_existing_series_into_table(existing_series)



class ToolBar(QtGui.QToolBar):
    def __init__(self, parent = None):
        QtGui.QToolBar.__init__(self, parent)
        icon = QtGui.QIcon("images/network-error.png")
        action = QtGui.QAction(icon, "test", self)
        self.addAction(action)


class SeriesWidgetItem(QtGui.QListWidgetItem):
    def __init__(self, movie, title, parent = None):
        QtGui.QListWidgetItem.__init__(self, parent)        
        self.movie = movie
        self.title = title
        self.setText(title)

def SeriesOrganizerDecoder(dct):
    if '__date__' in dct:
        return datetime.date.fromordinal(dct["ordinal"])

    if '__episode__' in dct:
        return Episode(title = dct["title"], descriptor = dct["descriptor"], series = dct["series"], plot = dct['plot'], date = dct["date"], identifier = dct["identifier"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], runtime = dct["runtime"])

    if '__series__' in dct:
        return Series(dct["title"], identifier = dct["identifier"], episodes = dct["episodes"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], date = dct["date"])

    if '__movieclip__' in dct:        
        return MovieClip(dct['filepath'], identifier = dct['identifier'], filesize = dct['filesize'], checksum = dct['checksum'])
    
    if '__movieclips__' in dct:        
        return MovieClipManager(dictionary = dct['dictionary'])
    
    if '__settings__' in dct:
        return Settings(settings = dct['settings'])
    
    if '__set__' in dct:
        return set(dct['contents'])
    
    return dct


class SeriesOrganizerEncoder(json.JSONEncoder):
    def default(self, obj):
        
        if isinstance(obj, Episode):
            return { "__episode__" : True, "title" : obj.title, "descriptor" : obj.descriptor, "series" : obj.series, "plot" : obj.plot, "date" : obj.date, "identifier" : obj.identifier, "rating" : obj.rating, "director" : obj.director, "runtime" : obj.runtime, "genre" : obj.genre}

        if isinstance(obj, datetime.date):
            return { "__date__" : True, "ordinal" : obj.toordinal()}

        if isinstance(obj, Series):
            return { "__series__" : True, "title" : obj.title, "episodes" : obj.episodes, "identifier" : obj.identifier, "rating" : obj.rating,  "director" : obj.director, "genre" : obj.genre, "date" : obj.date}

        if isinstance(obj, MovieClip):
            return { "__movieclip__" : True, "filepath" : obj.filepath, "filesize" : obj.filesize, "checksum" : obj.checksum, "identifier" : obj.identifier}        
        
        if isinstance(obj, Settings):
            return { "__settings__" : True, "settings" : obj.settings} 
            
        if isinstance(obj, MovieClipManager):
            return { "__movieclips__" : True, "dictionary" : obj.dictionary}                
        
        if isinstance(obj, set):
            return { "__set__" : True, "contents" : list(obj)}
        
        if isinstance(obj, QtCore.QString):
            return unicode(obj)        
        
        return json.JSONEncoder.default(self, obj)



class Settings(object):
    def __init__(self, settings = None):
        
        if settings == None:
            self.settings = {"copy_associated_movieclips" : True, 
                             "deployment_folder" : os.path.join(self.get_user_dir(),".diribeo"),
                             "automatic_thumbnail_creation" : False,
                             "show_all_movieclips" : True}
        else:
            self.settings = settings      


    def get(self, attribute_name):
        try:
            return self.settings[attribute_name]
        except KeyError:
            pass

    def get_collision_free_filename(self, destination):
        
        filename = os.path.basename(destination)
        directory = os.path.dirname(destination)
        
        if os.path.isfile(destination):
            #Collision detected:            
            split = os.path.splitext(filename)            
            index = 1 
            while(os.path.isfile(os.path.join(directory, filename))):
                filename = split[0] + " " + str(index) + split[1]
                index += 1
        return filename
            

    def get_user_dir(self):
        ''' Returns the user/Home directory of the user running this application. '''        
        return os.path.expanduser("~")
        
    
    def create_deployment_folder(self):
        ''' Creates the deployment folder if it doesn't exist '''
        if not os.path.exists(self.get("deployment_folder")):
            os.makedirs(self.get("deployment_folder"))
            

    def is_valid_file_extension(self, filepath):
        ''' Checks if the given filepath's filename has a proper movie clip extension ''' 
        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)
        
        if ext.lower().endswith(("mkv", "avi", "mpgeg", "mpg", "wmv")):
            return True


    def calculate_filepath(self, episode, filename):
        ''' Calculates the destination filepath of a given episode '''
        return os.path.join(self.settings["deployment_folder"], episode.series[0], "Season " + str(episode.descriptor[0]), filename)


    def move_file_to_folder_structure(self, episode, filepath, new_filename = None):
        ''' This method is responsible for moving the given file (filepath) to the calculated destination.
            It is also possible to define a new filename with the help of the new_filename parameter.
        '''
        
        if new_filename is not None:
            filename = new_filename
        else:
            filename = os.path.basename(filepath)
        
        destination = self.calculate_filepath(episode, filename)
        directory = os.path.dirname(destination)
        
        if not os.path.exists(directory):
            os.makedirs(directory) 
        
        # Copy / Move movie clip
        if self.settings["copy_associated_movieclips"]:                
            shutil.copyfile(filepath, destination)
        else:
            shutil.move(filepath, destination)

            
def create_default_image(episode):
    multiplikator = 5
    width = 16 * multiplikator
    heigth = 10 * multiplikator
    spacing = 1.25

    #extract text
    text = episode.series[0] + "\n" + episode.get_descriptor()

    #initalize pixmap object
    pixmap = QtGui.QPixmap(width, heigth)
    pixmap.fill(QtGui.QColor(255,255,255, 0))
    paint = QtGui.QPainter()        
    paint.begin(pixmap)
    paint.setRenderHint(QtGui.QPainter.Antialiasing)        

    #draw background
    gradient = QtGui.QLinearGradient(0, 0, 0, heigth*2)
    backgroundcolor = get_color_shade(episode.descriptor[0], 5)
    comp_backgroundcolor =  get_complementary_color(backgroundcolor)
    gradient.setColorAt(0.0, comp_backgroundcolor.lighter(50))
    gradient.setColorAt(1.0, comp_backgroundcolor.lighter(150))
    paint.setBrush(gradient)
    paint.setPen(QtGui.QPen(QtGui.QColor("black"), 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
    paint.drawRoundedRect(QtCore.QRect(spacing, spacing, width-spacing*2, heigth-spacing*2), 20, 15)

    #draw text
    paint.setFont(QtGui.QFont('Arial', 8))
    paint.setPen(QtGui.QColor("black"))
    paint.drawText(QtCore.QRect(spacing, spacing, width-spacing*2, heigth-spacing*2), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, text)        

    #end painting
    paint.end()

    return pixmap

def get_complementary_color(qtcolor):
    h, s, v, a = qtcolor.getHsv()    
    h = (h + 180) % 360     
    return QtGui.QColor.fromHsv(h, s, v, a)


def get_color_shade(index, number_of_colors):      
    return [QtGui.QColor.fromHsvF(colornumber/float(number_of_colors), 1, 0.9, 0.25) for colornumber in range(number_of_colors)][index % number_of_colors]

class MovieClip(object):
    def __init__(self, filepath, identifier = None, filesize = None, checksum = None):
        self.filepath = filepath
                    
        self.identifier = identifier
        
        if checksum is None:
            self.get_checksum()
        else:
            self.checksum = checksum
            
        if filesize is None:
            self.get_filesize()
        else:
            self.filesize = filesize
            
        self.thumbnails = []
        
    def get_filename(self):
        return os.path.basename(self.filepath)    
    
    def get_thumbnails(self):
        """ This function gathers the thumbnails and adds them to the dedicated thumnails list"""
        pass
        
    def get_checksum(self):
        try:
            return self.checksum
        except AttributeError:
            """This function calculates the SHA224 checksum of the given file and returns it"""
    
            checksum = hashlib.sha224()
            
            # Opening the file in binary mode is very important otherwise something completly different is calculated
            with open(self.filepath, "rb") as f:            
                for line in f:
                    checksum.update(line)
            f.close()
    
            self.checksum = checksum.hexdigest()
            return self.checksum

    def merge(self, other):
        """ This function merges the current movie clip object with another one.
        The current movie clip will be updated.
        
        To be able to merge two movie clips both movie clips must have the same checksum.
        If this is not the case a TypeError exception is raised.
        
        """
        if self == other:
            self.identifier.update(other.identifier)
        else:
            raise TypeError, "You're trying to merge two movie clips which don't have the same checksum"
        
    def get_filesize(self):
        try:
            return self.filesize
        except AttributeError:
            """This function calculates the file size in bytes of the given file and returns the result"""
            assert os.path.isfile(self.filepath)
    
            self.filesize = os.path.getsize(self.filepath)
            return self.filesize


    def get_folder(self):
        if os.path.isfile(self.filepath):
            return os.path.dirname(self.filepath)

    def delete_file_in_deployment_folder(self, series_name):
        if os.path.isfile(self.filepath):
            os.remove(self.filepath)
    
    def __eq__(self, other):
        if self.checksum == other.checksum:
            return True
    
    def __hash__(self):
        return hash(self.checksum)
        
    def __repr__(self):
        return "M(" + self.filepath + ")"
    
class IMDBWrapper(object):
    def __init__(self):
        #Import the imdb package.
        import imdb

        #Create the object that will be used to access the IMDb's database.
        self.ia  = imdb.IMDb(loggginLevel = "critical", proxy = "") # by default access the web.        


    def imdb_tv_series_to_series(self, imdb_identifier):        

        #Search for a movie (get a list of Movie objects).
        imdb_series = self.ia.get_movie(str(imdb_identifier))

        #Make sure that imdb movie is an actual tv series
        assert imdb_series.get('kind') == "tv series"

        self.get_episodes(imdb_series)


    def get_episodes(self, imdb_series):
        #Get more information about the series
        self.ia.update(imdb_series)

        #Get information about the episodes
        self.ia.update(imdb_series, 'episodes')

        seasons = imdb_series.get('episodes')

        numberofepisodes = imdb_series.get('number of episodes') - 1

        # Import helpers form imdb to sort episodes
        from imdb import helpers

        #Sort Episodes
        helpers.sortedEpisodes(seasons)

        #Ratings
        self.ia.update(imdb_series, 'episodes rating')        
        ratings = imdb_series.get('episodes rating')        

        for seasonnumber in seasons.iterkeys():
            if type(seasonnumber) == type(1):
                for imdb_episode_number in seasons[seasonnumber]:  
                    imdb_episode = seasons[seasonnumber][imdb_episode_number]                       
                    episode = Episode(title = imdb_episode.get('title'), descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], series = (imdb_series.get('title'), imdb_series.movieID), date = imdb_episode.get('original air date'), plot = imdb_episode.get('plot'), identifier = {"imdb" : imdb_episode.movieID}, rating = {"imdb" : self.get_rating(ratings, imdb_episode)})
                    yield episode, numberofepisodes

        return


    def get_more_information(self, series, movie):
        self.ia.update(movie)
        series.identifier = {"imdb" : movie.movieID}
        series.rating = {"imdb" : [movie.get("rating"), movie.get("votes")]}
        try:
            series.director = "\n".join(person['name'] for person in movie.get("director"))
        except TypeError:
            pass
        series.genre = "\n".join(movie.get("genre"))
        series.date = movie.get('year')


    def search_movie(self, title): 
        query = self.ia.search_movie(title)

        output = []
        # filter out unwanted movies:
        for movie in query:
            if movie.get('kind') == "tv series":
                output.append(SeriesWidgetItem(movie, movie.get('smart long imdb canonical title')))

        return output


    def get_series_from_movie(self, movie):
        """ Checks if the IMDB movie is already present in the series list.
        If it is presents it returns the series object. None otherwise.          
        """
        for series in series_list:
            try:
                if series.identifier["imdb"] == movie.movieID:
                    return series
            except KeyError, TypeError:
                pass

    def get_rating(self, ratings, imdb_episode):
        try:
            for single_rating in ratings:
                if single_rating["episode"] == imdb_episode:
                    return [single_rating["rating"], single_rating["votes"]]                
        except TypeError:
            pass               


    def release_dates_to_datetimedate(self, imdbdatelist):
        """ This function converts the release dates used by imdbpy into a datetime object.
        Right now it only converts the USA release date into its proper format and returns it """

        for imdbdate in imdbdatelist:
            matching = re.match(r"(\w+)::(.*)", imdbdate)
            if matching.group(1) == "USA":
                datematching = re.match(r"(\d+) (\w+) (\d+)", matching.group(2))
                try:
                    return datetime.date(int(datematching.group(3)), self.month_to_integer(datematching.group(2)), int(datematching.group(1)))
                except AttributeError:
                    logging.debug("Error: Date " + imdbdate) 

    def month_to_integer(self, monthname):
        return { "January" : 1, "February" : 2, "March": 3, "April" : 4, "May" : 5, "June" : 6,
                 "July" : 7, "August" : 8, "September" : 9, "October" : 10, "November" : 11, "December" : 12}[monthname]

class Series(object):
    def __init__(self, title, identifier = None, episodes = None, rating = None, director = "", genre = "", date = ""):
        self.title = title

        if episodes == None:
            episodes = []
            
        if identifier == None:
            identifier = {}

        self.episodes = episodes
        self.rating = rating
        self.identifier = identifier
        self.director = director
        self.genre = genre
        self.date = date

    def __getitem__(self, key):
        ''' Returns the n-th episode of the series '''
        return self.episodes[key]

    def __len__(self):
        ''' Returns the number of episodes '''
        return len(self.episodes)

    def __repr__(self):
        return "S(" + self.title + " E: " + str(len(self.episodes)) + ")"

    def get_seasons(self):
        ''' Returns a dictionary of seasons. Each season contains a list of episodes '''
        try:
            return self.seasons
        except AttributeError:
            self.seasons = {}

            for episode in self.episodes:
                try:
                    self.seasons[episode.descriptor[0]].append(episode)
                except KeyError:
                    self.seasons[episode.descriptor[0]] = []
                    self.seasons[episode.descriptor[0]].append(episode)

            return self.seasons

    def accumulate_episode_count(self, season):
        ''' This function adds all the preceeding episodes of the given season
        and returns the accumulated value '''

        seasons = self.get_seasons()        
        accumulated_sum = 0
        for index, seasonnumber in enumerate(seasons):
            if index - 1 == season:
                break
            accumulated_sum += len(seasons[seasonnumber])

        return accumulated_sum


    def get_movieclips(self):
        return None
        
    def get_identifier(self):
        return self.identifier.items()[0]

class Episode(object):
    def __init__(self, title = "", descriptor = None, series = "", date = None, plot = "", identifier = None, rating = None, director = "", runtime = "", genre = ""):
        
        self.title = title
        self.descriptor = descriptor
        self.series = series
        self.plot = plot
        self.date = date
        self.identifier = identifier
        self.rating = rating
        self.director = director
        self.runtime = runtime
        self.genre = genre


    def __repr__(self):
        return "E(" + str(self.series) + " - " + str(self.title) + " " + str(self.descriptor[0]) + "x" + str(self.descriptor[1]) +  " " + str(self.date) + ")"

    def __cmp__(self, other):
        try:
            other = other.date
        except (TypeError, AttributeError):
            pass
        return cmp(self.date, other)

    def __eq__(self, other):
        return self.title == other.title and self.descriptor == other.descriptor

    def get_descriptor(self):
        return str(self.descriptor[0]) + "x" + str(self.descriptor[1])

    def get_movieclips(self):
        try:
            return movieclips[self.get_identifier()]
        except KeyError:
            pass
    
    def get_identifier(self):
        # Use the first key as unique identifier. Note that this is propably not a good idea!
        return self.identifier.items()[0]
        
    def get_ratings(self):
        return_text = ""
        for rating in self.rating:
            try:
                return_text = str(rating).upper() + ": " + str(self.rating[rating][0]) + " (" + str(self.rating[rating][1]) + ")\n" + return_text
            except TypeError:
                pass
        return return_text 

class MovieClipManager(object):
    def __init__(self, dictionary = None):
        if dictionary == None:
            self.dictionary = {"imdb" : {}}       
        else:
            self.dictionary = dictionary

    def __getitem__(self, identifier):
       
        implementation, key = identifier
        try:            
            return self.dictionary[implementation][key]
        except KeyError:
            logging.debug("Key Error in Movieclip manager")
            
        return [] # Returns an empty list, to produce a empty iterator

    
    def get_episode_and_movieclip_list_with_matching_checksums(self, checksum):
        ''' This function searches for the given checksum in the internal data structures.
            It returns two lists as a tuple. The first beign a list of episodes. The second
            beign a list of movie clips which match the checksum.
        '''
        episode_list = []
        movieclip_list = []
        for implementation in self.dictionary:
            for key in self.dictionary[implementation]:
                for movieclip in self.dictionary[implementation][key]:
                    if movieclip.checksum == checksum:
                        movieclip_list.append(movieclip)
                        episode_list.append(self.from_movieclip_to_episode(movieclip))
                       
        return episode_list, movieclip_list
    
    
    def from_movieclip_to_episode(self, movieclip):
        ''' This function searches through the series_list and returns the 
            first episode which is associated to the given movie clip
        '''        
        for series in series_list:
            for episode in series.episodes:
                if episode.identifier == movieclip.identifier:
                    return episode
                

    def check_unique(self, movieclip, identifier):
        ''' Checks if the given movie clip hasn't been assigned to a different epsiode '''
        
        implementation, key = identifier
        for another_key in self.dictionary[implementation]:
            if another_key != key:
                if movieclip in self.dictionary[implementation][another_key]:
                    return False
        return True
        
    def add(self, movieclip):
        implementation, key = movieclip.identifier.items()[0]       
        try:
             self.dictionary[implementation][key].append(movieclip)
        except KeyError:           
            self.dictionary[implementation][key] = []
            self.dictionary[implementation][key].append(movieclip) 

    def remove(self, movieclip, identifier):
        implementation, key = identifier
        self.dictionary[implementation][key].remove(movieclip)
        save_movieclips()

    def __iter__(self):
        return self.dictionary.iteritems()

def load_series():
    return load_file("series.json", [])    
    
def load_movieclips():
    return load_file("movieclips.json", MovieClipManager())

def save_series():
    save_file("series.json", series_list)

def save_movieclips():
    save_file("movieclips.json", movieclips)

def load_settings():
    return load_file("settings.json", Settings())

def save_settings():
    save_file("settings.json", settings)


def save_file(filename, contents):
    with open(filename, "w") as f:
        f.write(json.dumps(contents, sort_keys = True, indent = 4, cls = SeriesOrganizerEncoder, encoding = "utf-8"))
    f.close()     

def load_file(filename, default_value):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            filecontents = f.read()
        f.close() 
        try:
            return json.loads(filecontents, object_hook = SeriesOrganizerDecoder, encoding = "utf-8")
        except ValueError: 
            return default_value
    
    return default_value  


if __name__ == "__main__":

    app = QtGui.QApplication(sys.argv)
    
    imdbwrapper = IMDBWrapper()
    active_table_models = {}    
    jobs = []
    series_list = load_series()
    movieclips = load_movieclips()
    settings = load_settings()

    mainwindow = MainWindow()
    mainwindow.show()
    
    app.exec_()



