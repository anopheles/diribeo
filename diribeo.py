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

from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt


# Initialize the logger
log_filename = "logger_output.out"
logging.basicConfig(filename=log_filename,  format='%(asctime)s %(levelname)s %(message)s', level=logging.DEBUG, filemode='w')


class EpisodeTableModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None, episodes = None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        if episodes == None:
            self.episodes = []
        else:
            self.episodes = episodes

        self.row_lookup = lambda episode: ["", episode.title, episode.date, episode.plot]
        self.column_lookup = ["", "Title", "Date", "Plot Summary"]

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
        return Qt.ItemIsEnabled

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                #the column
                return QtCore.QString(self.column_lookup[section])

    def insertRows(self, row, count, modelindex):
        self.beginInsertRows(QtCore.QModelIndex(), row, count)
        self.endInsertRows()
        return True  

class OnlineSearch(QtGui.QFrame):
    def __init__(self, parent = None):
        QtGui.QFrame.__init__(self, parent)

        self.setFrameShape(QtGui.QFrame.StyledPanel)
        onlinelayout = QtGui.QVBoxLayout(self)
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

    def remove_series(self, series):        
        count = self.localseriestree.topLevelItemCount()
        for number in range(count):            
            item = self.localseriestree.topLevelItem(number)
            if item.series == series:
                delete_item = item                    
        self.localseriestree.removeItemWidget(delete_item, 0)

    def sort_tree(self):
        self.localseriestree.sortItems(0, Qt.AscendingOrder)

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
        self.sort_tree()

    def update_tree(self, series):    
        for toplevelitem in self.toplevel_items:
            if series == toplevelitem.series:                    
                self.build_subtree(toplevelitem)


class MovieClipInformationWidget(QtGui.QFrame):
    def __init__(self, movieclip, parent = None):
        QtGui.QFrame.__init__(self, parent)
        self.boxlayout = QtGui.QVBoxLayout()
        self.setLayout(self.boxlayout)
        self.setFrameShape(QtGui.QFrame.StyledPanel)
        
        self.title = QtGui.QLabel("")
        
        self.boxlayout.addWidget(QtGui.QLabel("Filename"))
        self.boxlayout.addWidget(self.title)
        self.boxlayout.addStretch(2)
        self.load_information(movieclip)
        
    def load_information(self, movieclip):
        self.title.setText(os.path.basename(movieclip.filepath))
        

class MovieClipOverviewWidget(QtGui.QWidget):
    def __init__(self, parent = None, movieclips = None):
        QtGui.QWidget.__init__(self, parent)
        self.vbox = QtGui.QVBoxLayout()
        self.setLayout(self.vbox)        
        self.movieclipinfos = []
        self.draghere_label = QtGui.QLabel("To add movie clips drag them here")                
        self.vbox.addWidget(self.draghere_label)
      
    
    def load_movieclips(self, movieclips):
        self.remove_old_entries()
        assert len(self.movieclipinfos) == 0
        if movieclips != None and len(movieclips) > 0:
            self.draghere_label.setVisible(False)
            if movieclips != None:
                for movieclip in movieclips:
                    info_item = MovieClipInformationWidget(movieclip)
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
        
        
    def setText(self, text):
        if text == None or text == "":
            text = self.default
            
        self.set_content(text)


    def reset(self):
        self.set_content(self.default)


class SeriesInformationWidget(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        
        
        layout = QtGui.QVBoxLayout(self)
        layout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.setLayout(layout)
        
        self.seenit = SeriesInformationCategory("Seen it?", type = QtGui.QCheckBox)
        self.movieclipwidget = SeriesInformationCategory("Movie Clips", type = MovieClipOverviewWidget)        
        self.director = SeriesInformationCategory("Director")
        self.rating = SeriesInformationCategory("Ratings")
        self.airdate = SeriesInformationCategory("Airdate")
        self.plot = SeriesInformationCategory("Plot", type = QtGui.QTextEdit)
        self.genre = SeriesInformationCategory("Genre") 
        
        
        self.header_layout = QtGui.QHBoxLayout()
        self.title = QtGui.QLabel()        
        self.update_button = QtGui.QPushButton("Update")
        self.delete_button = QtGui.QPushButton("Delete")
        self.header_layout.addWidget(self.delete_button)
        self.header_layout.addWidget(self.update_button)
        layout.addWidget(self.title)
        layout.addLayout(self.header_layout)
        layout.addSpacing(25)
        
        layout.addWidget(self.movieclipwidget)
        layout.addWidget(self.seenit)
        layout.addWidget(self.director)
        layout.addWidget(self.rating)
        layout.addWidget(self.airdate)
        layout.addWidget(self.plot)
        layout.addWidget(self.genre)
        
        self.setAcceptDrops(True)
    
    def clear_all_info(self):
        self.rating.reset()
        self.genre.reset()
        self.director.reset()  
            

    def load_information(self, movie):             
        
        self.movie = movie
        
        if isinstance(self.movie, Series):
            self.delete_button.setVisible(True)
            self.plot.setVisible(False)
        else:
            self.rating.setText(movie.get_ratings())
            self.plot.setText(str(movie.plot))
            self.plot.setVisible(True)
            self.delete_button.setVisible(False)
        
        # Handle the title
        try:
            self.title.setText(movie.series + " - " + movie.title + " - " + movie.get_descriptor())
        except AttributeError:
            self.title.setText(movie.title)
            
        self.director.setText(movie.director) 
        self.airdate.setText(str(movie.date))
        self.genre.setText(movie.genre)
        self.movieclipwidget.content.load_movieclips(movie.get_movieclips())               

        
    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):        
        try:
            filepath = event.mimeData().urls()[0].toLocalFile()
            job = MovieClipAssociator(filepath, self.movie)
            job.finished.connect(self.load_information)
            job.already_exists.connect(self.already_exists_warning)
            job.filesystem_error.connect(self.filesystem_error_warning)
            jobs.append(job)
            job.start()
            
        except AttributeError:
            pass
        event.accept()        

    def already_exists_warning(self, movie, filepath):
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "Movie Clip already associated.", "")
        messagebox.setText("You're trying to assign a movie clip multiple times.")
        messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with another episode")
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


class MovieClipAssociator(QtCore.QThread):
    
    finished = QtCore.pyqtSignal("PyQt_PyObject")
    already_exists = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    filesystem_error = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    
    def __init__(self, filepath, movie):
        QtCore.QThread.__init__(self)
        self.movie = movie
        self.filepath = unicode(filepath)
        
    def run(self):
        key = self.movie.get_identifier()
        
        if os.path.isfile(self.filepath) == False:
            self.filesystem_error.emit(self.movie, self.filepath)
        else:
            clip = MovieClip(self.filepath, self.movie.identifier)
            add = True
            for identifier in movieclip_dict:
                if clip in movieclip_dict[identifier]:
                    self.already_exists.emit(self.movie, self.filepath)
                    add = False

            if add is True:
                try:
                    movieclip_dict[key].append(clip)
                except KeyError:
                    movieclip_dict[key] = []
                    movieclip_dict[key].append(clip)
                
                self.finished.emit(self.movie)
                save_movieclips()             


            
class EpisodeViewWidget(QtGui.QWidget):    
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)         
        mainbox = QtGui.QVBoxLayout()
        self.setLayout(mainbox)
    
        #init table view        
        self.tableview = QtGui.QTableView(self) 
        self.tableview.verticalHeader().setDefaultSectionSize(125)
        self.tableview.horizontalHeader().setStretchLastSection(True)
        self.tableview.setShowGrid(False)  

        mainbox.addWidget(self.tableview)
        self.setLayout(mainbox)



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
        self.tab.addTab(QtGui.QWidget(), "+")
        self.setWidget(self.tab)
        self.setFeatures(QtGui.QDockWidget.DockWidgetMovable | QtGui.QDockWidget.DockWidgetFloatable)
        
        # Handle signals
        self.tab.currentChanged.connect(self.handle_tab_change)
        self.wizard = SeriesAdderWizard()
        
    def handle_tab_change(self, index):
        if index == 1:
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
    progress = QtCore.pyqtSignal("PyQt_PyObject", int, int)
    finished = QtCore.pyqtSignal("PyQt_PyObject")
    update_tree = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, model, series, view, movie = None):
        QtCore.QThread.__init__(self)
        self.movie = movie
        self.model = model
        self.series = series
        self.view = view

        self.model.set_generator(imdbwrapper.get_episodes(movie))

    def run(self): 
                    
        self.episode_counter = 0

        # Make the progress bar idle
        self.insert_into_tree.emit(self.series)  
        self.waiting.emit()        
        self.view.seriesinfo.load_information(self.series)
        imdbwrapper.get_more_information(self.series, self.movie)
        self.view.seriesinfo.load_information(self.series)
              


        for episode, episodenumber in self.model.generator:            
            self.model.episodes.append(episode)
            self.series.episodes.append(episode)
            self.model.insertRows(0,0, QtCore.QModelIndex())
            self.episode_counter += 1
            if self.episode_counter % 8 == 0:
                self.progress.emit(self, self.episode_counter, episodenumber)        
                
        save_series()            
        self.finished.emit(self)        

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

    def reset(self):        
        self.setValue(-1)
        self.setMinimum(0)
        self.setMaximum(1)
        QtGui.QProgressBar.reset(self)

    def refresh_progressbar(self):
        current, maximum = map(sum, zip(*self.workers.values()))
        self.setValue(current)
        self.setMaximum(maximum)        

    def operation_finished(self, thread):
        try:
            del self.workers[thread]
        except KeyError:
            # Thread has already been deleted
            pass
        if len(self.workers) == 0:
            self.reset()
            self.timer.stop()

    def update_bar(self, thread, current, maximum):        
        self.workers[thread] = [current, maximum]
        if not self.timer.isActive():
            self.timer.start(1000);

class MainWindow(QtGui.QMainWindow):
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)

        self.existing_series = None # stores the currently active series object
        
        episode_table_widget = EpisodeViewWidget()        
        self.setCentralWidget(episode_table_widget)
        
        self.tableview = episode_table_widget.tableview

        #initalize the status bar
        statusbar = QtGui.QStatusBar()
        statusbar.showMessage("Ready")
        self.setStatusBar(statusbar)
        
        # Initialize the progress bar and assign to the statusbar
        self.progressbar = SeriesProgressbar()  
        self.progressbar.setMaximumHeight(10)
        self.progressbar.setMaximumWidth(100)
        
        statusbar.addPermanentWidget(self.progressbar)        

        #initalize the tool bar
        self.addToolBar(ToolBar())
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        # Initialize local search
        local_search_dock = self.local_search_dock = LocalSearchDock()
        self.local_search = local_search_dock.local_search
        
        
        # Initialize online search
        series_info_dock = SeriesInformationDock()
        self.seriesinfo =  series_info_dock.seriesinfo
        
        
        # Manage the docs
        self.addDockWidget(Qt.LeftDockWidgetArea, local_search_dock)                            
        self.addDockWidget(Qt.RightDockWidgetArea, series_info_dock)
       
        #self.local_search_dock.selection_finished.connect(None)
        self.local_search_dock.wizard.selection_finished.connect(self.load_items_into_table)
        self.local_search.localseriestree.selectionModel().selectionChanged.connect(self.load_into_local_table)         
        self.seriesinfo.delete_button.clicked.connect(self.delete_series)       
        
        self.load_all_series_into_their_table()
        self.tableview.setModel(None)
        
        self.setWindowTitle("Diribeo")
        self.resize_to_percentage(66)
        self.center()
        
        
    def delete_series(self):
        #TODO this doesn't work on series which have been downloaded in the current session        
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

    def load_episode_information_at_index(self, index, previous):
        #if previous.isValid():
        self.seriesinfo.load_information(self.existing_series[index.row()])

    def load_all_series_into_their_table(self):
        for series in series_list:
            self.load_existing_series_into_table(series)        

    def load_existing_series_into_table(self, series):
        try:
            self.tableview.setModel(active_table_models[series]) 
            self.tableview.selectionModel().currentRowChanged.connect(self.load_episode_information_at_index)           
        except KeyError:                    
            active_table_models[series] = model = EpisodeTableModel(episodes = series.episodes)
            self.tableview.setModel(model)            
            
            
    def load_items_into_table(self, items):
        """ Loads the selected episodes from the clicked series in the onlineserieslist """
        
        for item in items:           
            movie = item.movie

            existing_series = imdbwrapper.get_series_from_movie(movie)
            
            
            if existing_series is None: 
                current_series = Series(item.title)
                series_list.append(current_series)
                active_table_models[current_series] = model = EpisodeTableModel()
                self.tableview.setModel(model)
                self.tableview.selectionModel().currentRowChanged.connect(self.load_episode_information_at_index)
                
                self.existing_series = current_series                
                job = ModelFiller(model, current_series, self, movie = movie)
                
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
        return MovieClip(dct['filepath'], dct['identifier'], filesize = dct['filesize'], checksum = dct['checksum'])
    
    if '__settings__' in dct:
        return Settings() # TODO
    
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
            return { "__settings__" : True, "copy_movieclips" : obj.copy_associated_movieclips, "deployment_folder" : obj.deployment_folder, "thumbnail_creation" : obj.automatic_thumbnail_creation} 
        
        if isinstance(obj, QtCore.QString):
            return unicode(obj)        
        
        return json.JSONEncoder.default(self, obj)


def create_default_image(episode):
    multiplikator = 5
    width = 16 * multiplikator
    heigth = 10 * multiplikator
    spacing = 1.25

    #extract text
    text = episode.series + "\n" + episode.get_descriptor()

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
    def __init__(self, filepath, identifier, filesize = None, checksum = None):
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
        self.ia  = imdb.IMDb(loggginLevel = "critical") # by default access the web.        


    def imdb_tv_series_to_series(self, imdb_identifier):        

        #Search for a movie (get a list of Movie objects).
        imdb_series = self.ia.get_movie(str(imdb_identifier))

        #Make sure that imdb movie is an actual tv series
        assert imdb_series['kind'] == "tv series"

        self.get_episodes(imdb_series)


    def get_episodes(self, imdb_series):
        #Get more information about the series
        self.ia.update(imdb_series)

        #Get information about the episodes
        self.ia.update(imdb_series, 'episodes')

        seasons = imdb_series.get('episodes')

        numberofepisodes = imdb_series['number of episodes'] - 1

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
                    episode = Episode(title = imdb_episode.get('title'), descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], series = imdb_series.get('title'), date = imdb_episode.get('original air date'), plot = imdb_episode.get('plot'), identifier = {"imdb" : imdb_episode.movieID}, rating = {"imdb" : self.get_rating(ratings, imdb_episode)})
                    yield episode, numberofepisodes

        return 


    def get_more_information(self, series, movie):
        self.ia.update(movie)
        series.identifier = {"imdb" : movie.movieID}
        series.rating = {"imdb" : [movie.get("rating"), movie.get("votes")]}
        series.director = "\n".join(person['name'] for person in movie.get("director"))
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
        """ Returns the n-th episode of the series """
        return self.episodes[key]

    def __len__(self):
        """ Returns the number of episodes """
        return len(self.episodes)

    def __repr__(self):
        return "S(" + self.title + " E: " + str(len(self.episodes)) + ")"

    def get_seasons(self):
        """ Returns a dictionary of seasons. Each season contains a list of episodes """
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


    def get_episodes(self):
        for episode in self.episodes:
            yield episode, len(self.episodes)


    def accumulate_episode_count(self, season):
        """This function adds all the preceeding episodes of the given season
        and returns the accumulated value"""

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
        return str((self.identifier.keys()[0], self.identifier[self.identifier.keys()[0]]))

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
        return str(self.descriptor[0]) + " x " + str(self.descriptor[1])

    def get_movieclips(self):
        try:
            return movieclip_dict[self.get_identifier()]
        except KeyError:
            pass
    
    def get_identifier(self):
        # Use the first key as unique identifier. Note that this is propably not a good idea!
        return self.identifier.keys()[0] + self.identifier[self.identifier.keys()[0]]
        
    def get_ratings(self):
        return_text = ""
        for rating in self.rating:
            return_text = str(rating).upper() + ": " + str(self.rating[rating][0]) + " (" + str(self.rating[rating][1]) + ")\n"
        return return_text 


class Settings(object):
    def __init__(self):    

        ''' Defines if newly assigned movieclips are copied into their respective directory structure.
            If this property is false this implies that the original file is moved instead of copied.     
        '''
        self.copy_associated_movieclips = True
        
        
        ''' Defines the folder in which all importan information is saved conserning this application.
            Note that this musn't be the execution directory of this application.
        '''
        self.deployment_folder = os.path.join(self.get_user_dir,".diribeo")
        
        
        ''' Specifies if thumbnails should be created as soon as the movie clip gets associated with an 
            episode or series
        '''       
        self.automatic_thumbnail_creation = False        


    def get_user_dir(self):
        ''' Returns the user/Home directory of the user running this application. '''        
        return os.path.expanduser("~")
        
    
    def create_deployment_folder(self):
        ''' Creates the deployment folder if it doesn't exist '''
        if not os.path.exists(self.deployment_folder):
            os.makedirs(self.deployment_folder)
            

def load_series():
    return load_file("series.json", [])    
    
def load_movieclips():
    return load_file("movieclips.json", {})

def save_series():
    save_file("series.json", series_list)

def save_movieclips():
    save_file("movieclips.json", movieclip_dict)

def load_settings():
    return load_file("settings.json", {})

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
    movieclip_dict = load_movieclips()
    settings = load_settings()

    mainwindow = MainWindow()
    mainwindow.show()
    
    app.exec_()



