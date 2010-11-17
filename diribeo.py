# -*- coding: utf-8 -*-
from lxml.html.defs import general_block_tags


__author__ = 'David Kaufman'
__version__ = (0,0,3,"dev")
__license__ = 'MIT'


import sys
import os
import logging as log

import subprocess
import functools
import collections

import diribeomessageboxes
import diribeomodel
import diribeowrapper
import diribeoutils


from diribeomodel import Series, Episode, MovieClipAssociation, Settings
from diribeoworkers import SeriesSearchWorker, ModelFiller, MultipleMovieClipAssociator, ThumbnailGenerator, MultipleAssignerThread, MovieUpdater, VersionChecker


from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt


# Initialize logger
log_filename = "logger_output.out"
log.basicConfig(filename=log_filename,  format='%(asctime)s %(levelname)s %(message)s', level=log.DEBUG, filemode='w')


class WorkerThreadManager(object):
    def __init__(self):
        self.worker_thread_dict = {}
        self.statusbar = QtGui.QStatusBar()
        self.progressbar = DiribeoProgressbar()
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_statusbar) 
        self.timer.timeout.connect(self.refresh_progressbar) 
        self.ready = "Ready"
        self.statusbar.showMessage(self.ready) 
        self.statusbar.addPermanentWidget(self.progressbar)       
        

    def process_finished(self, worker_thread):
        try:
            del self.worker_thread_dict[worker_thread]
        except KeyError:
            # Thread has already been deleted
            pass
        
        if len(self.worker_thread_dict) == 0:
            self.statusbar.showMessage(self.ready)
            self.timer.stop()
            self.progressbar.stop()

    def process_waiting(self, worker_thread):
        self.progressbar.waiting()

    def process_progress(self, worker_thread, current, maximum):
        self.worker_thread_dict[worker_thread] = [current, maximum]
        
    def append(self, worker_thread):     
        worker_thread.waiting.connect(functools.partial(self.process_waiting, worker_thread))
        worker_thread.finished.connect(functools.partial(self.process_finished, worker_thread))
        worker_thread.progress.connect(functools.partial(self.process_progress, worker_thread))
                
        self.worker_thread_dict[worker_thread] = [0,0]
        if not self.timer.isActive():
            self.timer.timeout.emit()
            self.timer.start(1000)  

    
    def refresh_progressbar(self):
        current, maximum = map(sum, zip(*self.worker_thread_dict.values()))
        self.progressbar.setValue(current)
        self.progressbar.setMaximum(maximum)  
    
    def refresh_statusbar(self):
        list_of_descriptions = []
        for worker_thread in self.worker_thread_dict.items():
            additional_description = ""
            descriptions = worker_thread[0].additional_descriptions.items()
            if len(descriptions ) != 0:
                additional_description = " (" + " ".join([description[1] for description in descriptions]) + ")"
            list_of_descriptions.append(worker_thread[0].description + additional_description)
        
        if len(list_of_descriptions) > 0:
            self.statusbar.showMessage(", ".join(list_of_descriptions))
        else:
            self.statusbar.showMessage(self.ready) 



class DiribeoProgressbar(QtGui.QProgressBar):
    def __init__(self, parent=None):
        QtGui.QProgressBar.__init__(self, parent)
        self.workers = {}        

    def waiting(self):        
        self.setValue(-1)
        self.setMinimum(0)
        self.setMaximum(0)  

    def stop(self):     
        self.setValue(-1)
        self.setMinimum(0)
        self.setMaximum(1)
        QtGui.QProgressBar.reset(self)
             

class EpisodeTableModel(QtCore.QAbstractTableModel):
    def __init__(self, series, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.series = series        
        self.episodes = self.series.episodes
        self.filled = False
        
        self.row_lookup = lambda episode: ["", episode.title, episode.seen_it, episode.date, episode.plot]
        self.column_lookup = ["", "Title", "Seen it?", "Date", "Plot Summary"]
        
        

    def insert_episode(self, episode):
        self.episodes.append(episode)

    def rowCount(self, index):
        return len(self.episodes)

    def columnCount(self, index):
        return len(self.column_lookup)

    def data(self, index, role):
        episode = self.episodes[index.row()]
        
        picture, title, seen_it, date, plot_summary = range(5)
           
        if role == QtCore.Qt.DisplayRole:
            if index.column() != seen_it:
                return QtCore.QString(unicode(self.row_lookup(episode)[index.column()])) 
         
        elif role == QtCore.Qt.DecorationRole:
            if index.column() == picture:
                return diribeoutils.create_default_image(episode, additional_text = str(episode.number))
        
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == seen_it:
                if episode.seen_it:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
            
        elif role == QtCore.Qt.BackgroundRole:
            if not episode.seen_it:
                return diribeoutils.get_gradient_background(episode.descriptor[0], saturation = 0.25)
            return diribeoutils.get_gradient_background(episode.descriptor[0], saturation = 0.5)
        
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        return QtCore.QVariant()     


    def refresh_table(self):
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.episodes)-1, len(self.column_lookup)-1))
    
    def refresh_row(self, row):
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.column_lookup)-1))
    
    def setData(self, index, value, role = Qt.EditRole):
        if role == Qt.CheckStateRole:
            boolean_value = False
            if value == Qt.Checked:
                boolean_value = True
            self.episodes[index.row()].seen_it = boolean_value 
            self.dataChanged.emit(index, index)
            return True
        if role == Qt.EditRole:
            if index.column() == 4:
                self.episodes[index.row()].plot = value.toString()
                self.dataChanged.emit(index, index)
                return True
        return False

    def flags(self, index):        
        if index.column() == 2:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
        if index.column() == 4:
            return Qt.ItemIsEnabled | Qt.ItemIsEditable | Qt.ItemIsSelectable        
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                #the column
                return QtCore.QString(self.column_lookup[section])

class LocalTreeWidget(QtGui.QTreeWidget):
    def __init__(self, parent=None):
        QtGui.QTreeWidget.__init__(self, parent)     
        
        
        self.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):
        series = None
        try:
            dropIndex = self.indexAt(event.pos())
            series = self.itemFromIndex(dropIndex).series
        except AttributeError:
            pass #No Series Affinity
            
        filepath_dir_list = [url.toLocalFile() for url in event.mimeData().urls()]    
        mainwindow.multiple_assigner(filepath_dir_list, series)
        event.accept()
        
class LocalSearch(QtGui.QFrame):

    def __init__(self, parent=None):
        QtGui.QFrame.__init__(self, parent)
                
        localframelayout = QtGui.QVBoxLayout(self)
        self.setLayout(localframelayout)      

        self.localseriestree = LocalTreeWidget()
        self.localseriestree.setColumnCount(1)
        self.localseriestree.setHeaderLabels(["Series"])        
        self.localseriestree.setAnimated(True)
        self.localseriestree.setHeaderHidden(True)
        self.toplevel_items = []
        self.initial_build_tree()

        localframelayout.addWidget(self.localseriestree)


    def sort_tree(self):
        self.localseriestree.sortItems(0, Qt.AscendingOrder)


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
            self.toplevel_items.append(parent_series)
            parent_series.series = series
            self.build_subtree(parent_series)


    def build_subtree(self, parent_series):
        seasons = parent_series.series.get_seasons()
        for seasonnumber in seasons:
            child_season = QtGui.QTreeWidgetItem(parent_series,["Season " + str('%0.2d' % seasonnumber)])
            child_season.series = parent_series.series
            for episode in seasons[seasonnumber]:
                child_episode = QtGui.QTreeWidgetItem(child_season,[episode.title]) 
                child_episode.series = parent_series.series
        self.localseriestree.addTopLevelItem(parent_series)


    def update_tree(self, series):    
        for toplevelitem in self.toplevel_items:
            if series == toplevelitem.series:
                toplevelitem.takeChildren()
                self.build_subtree(toplevelitem)


class MovieClipInformationWidget(QtGui.QFrame):
    
    update = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, movieclip, movie, parent = None):
        QtGui.QFrame.__init__(self, parent)
        self.vbox = QtGui.QVBoxLayout()
        self.gridlayout = QtGui.QGridLayout()
        self.thumbnail_gridlayout = QtGui.QGridLayout()
        self.vbox.addLayout(self.gridlayout)
        self.vbox.addLayout(self.thumbnail_gridlayout)
        self.setLayout(self.vbox)
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
        icon_thumbnail = QtGui.QIcon("images/applications-multimedia.png")
        
        self.play_button = QtGui.QPushButton(icon_start, "")  
        self.remove_button = QtGui.QPushButton(icon_remove, "") 
        self.delete_button = QtGui.QPushButton(icon_delete, "")
        self.open_button = QtGui.QPushButton(icon_open, "")  
        self.thumbnail_button = QtGui.QPushButton(icon_thumbnail, "")
        
        if available:
            self.control_layout.addWidget(self.delete_button)
            self.control_layout.addWidget(self.play_button)
            self.control_layout.addWidget(self.open_button)
            self.control_layout.addWidget(self.thumbnail_button)
            
            for index, filepath in enumerate(self.movieclip.thumbnails):
                if os.path.exists(filepath):
                    temp_label = QtGui.QLabel()
                    qimage = QtGui.QImage(filepath)
                    pixmap = QtGui.QPixmap.fromImage(qimage)
                    pixmap = pixmap.scaledToWidth(100)
                    
                    temp_label.setPixmap(pixmap)
                    temp_label.setToolTip("<img src= '"+ filepath +"'>")
                    self.thumbnail_gridlayout.addWidget(temp_label, index/2, index % 2)
        
        self.control_layout.addWidget(self.remove_button)
        
        self.gridlayout.addWidget(QtGui.QLabel("Filename"), 0, 0)            
        self.gridlayout.addWidget(self.title, 1, 0)        
        self.gridlayout.addLayout(self.control_layout, 2, 0)
       
        self.play_button.clicked.connect(self.play)        
        self.delete_button.clicked.connect(self.delete)
        self.remove_button.clicked.connect(self.remove)
        self.open_button.clicked.connect(self.open_folder)
        self.thumbnail_button.clicked.connect(functools.partial(mainwindow.generate_thumbnails, self.movie, self.movieclip))
        
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
        folder = self.movieclip.get_folder()
        if folder is not None: 
            try:
                os.startfile(folder) # Unix systems do not have startfile
            except AttributeError:         
                subprocess.Popen(['xdg-open', self.movieclip.get_folder()])
        
    def load_information(self, movieclip):
        self.title.setText(movieclip.get_filename())
     
    def delete(self):
        self.movieclip.delete_file_in_deployment_folder()
        self.movieclip.delete_thumbnails()
        self.remove()
      
    def remove(self):
        movieclips.remove(self.movieclip, self.movie.get_identifier()) 
        self.update.emit(self.movie)
    
    def play(self):
        filepath = os.path.normpath(self.movieclip.filepath)
        if os.path.isfile(filepath):            
            try:
                os.startfile(filepath) # Unix systems do not have startfile
            except AttributeError:
                subprocess.Popen(['xdg-open', filepath])

class MovieClipOverviewWidget(QtGui.QWidget):
    def __init__(self, parent = None, movieclips = None):
        QtGui.QWidget.__init__(self, parent)
        self.vbox = QtGui.QVBoxLayout()
        self.setLayout(self.vbox)        
        self.movieclipinfos = []   
        open_folder_icon = QtGui.QIcon("images/plus.png")
        self.open_folder_button = QtGui.QPushButton(open_folder_icon, "To add a movie clip drag it here or simply click this button")
        self.vbox.addWidget(self.open_folder_button)
        self.movie = None
    
    def load_movieclips(self, movie):
        self.remove_old_entries()
        assert len(self.movieclipinfos) == 0
                
        movieclips =  movie.get_movieclips()
        
        if len(movieclips) > 0:
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


    def remove_old_entries(self):
        for movieclipinfo in self.movieclipinfos:
            self.vbox.removeWidget(movieclipinfo)
            movieclipinfo.deleteLater()
        self.movieclipinfos = []


class SeriesInformationCategory(QtGui.QWidget):
    def __init__(self, label_name, type = QtGui.QLabel, spacing = 25, default = "-", disabled = False, parent = None):
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
        
        if disabled:
            self.content.setEnabled(False)        
        
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
        self.goto_series_button = QtGui.QPushButton("Go to Series")
        
        header_layout.addWidget(self.delete_button)
        header_layout.addWidget(self.update_button)
        header_layout.addWidget(self.goto_series_button)
        self.setLayout(header_layout)

class SeriesInformationWidget(QtGui.QStackedWidget):
    
    def __init__(self, parent = None):
        QtGui.QStackedWidget.__init__(self, parent)              
        
        self.main_widget = QtGui.QWidget()        
        main_widget_layout = QtGui.QVBoxLayout()
        main_widget_layout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.main_widget.setLayout(main_widget_layout)
        
        self.seenit = SeriesInformationCategory("Seen it?", type = QtGui.QCheckBox, disabled = True)
        self.title = SeriesInformationCategory("Title", type = SeriesInformationControls)
        self.movieclipwidget = SeriesInformationCategory("Movie Clips", type = MovieClipOverviewWidget)
        self.source = SeriesInformationCategory("Source")        
        self.director = SeriesInformationCategory("Director")
        self.rating = SeriesInformationCategory("Ratings")
        self.airdate = SeriesInformationCategory("Air Date")
        self.plot = SeriesInformationCategory("Plot", type = QtGui.QTextEdit, disabled = True)
        self.genre = SeriesInformationCategory("Genre")
        
        self.main_widgets = [self.title, self.seenit, self.movieclipwidget, self.director, self.source, self.rating, self.airdate, self.plot, self.genre]
        
        for widget in self.main_widgets:
            main_widget_layout.addWidget(widget)
        
        self.nothing_to_see_here_widget = QtGui.QWidget()
        
        self.delete_button = self.title.content.delete_button
        self.update_button = self.title.content.update_button
        self.goto_series_button = self.title.content.goto_series_button
        
        self.addWidget(self.main_widget)
        self.addWidget(self.nothing_to_see_here_widget)
        
        self.setCurrentWidget(self.nothing_to_see_here_widget)
        
        self.setAcceptDrops(True)
 
    def clear_all_info(self):
        self.setCurrentWidget(self.nothing_to_see_here_widget)

    def load_information(self, movie):
        print "loading information"
        self.movie = movie
        
        self.setCurrentWidget(self.main_widget)

        try:
            self.plot.content.textChanged.disconnect()
        except TypeError:
            pass
            
        if isinstance(self.movie, Series):
            self.delete_button.setVisible(True)
            self.goto_series_button.setVisible(False)
            self.plot.setVisible(False)
            self.rating.setVisible(False)
            self.seenit.setVisible(False)
        else:
            self.rating.setVisible(True)
            self.rating.setText(movie.get_ratings())
            self.plot.setText(movie.plot)
            self.plot.setVisible(True)
            self.delete_button.setVisible(False)
            self.goto_series_button.setVisible(True)
            self.seenit.setVisible(True)
            self.seenit.content.setChecked(self.movie.seen_it)
        
        # Handle the title
        try:
            self.title.set_description(movie.series[0] + " - " + movie.title + " - " + movie.get_descriptor())
        except AttributeError:
            self.title.set_description(movie.title)
        
        self.director.setText(movie.director) 
        self.airdate.setText(str(movie.date))
        self.genre.setText(movie.genre)
        self.source.setText(movie.identifier.keys()[0])
        
        try:
            self.movieclipwidget.content.open_folder_button.clicked.disconnect()
        except TypeError:
            pass
        self.movieclipwidget.content.open_folder_button.clicked.connect(functools.partial(mainwindow.start_assign_dialog, movie))
        
        
        try:
            self.update_button.clicked.disconnect()
        except TypeError:
            pass
        self.update_button.clicked.connect(functools.partial(mainwindow.update_movie, movie))
        
        
        try:
            self.goto_series_button.clicked.disconnect()
        except TypeError:
            pass
        self.goto_series_button.clicked.connect(functools.partial(mainwindow.load_series_info_from_episode, movie))
        
                
        self.movieclipwidget.content.load_movieclips(movie)   
        
    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):        
        try:
            filepaths = [url.toLocalFile() for url in event.mimeData().urls()]            
            if isinstance(self.movie, Episode):
                mainwindow.add_movieclip_to_episode(filepaths[0], self.movie)
            else:
                mainwindow.multiple_assigner(filepaths, self.movie)
            
        except (AttributeError, IndexError):
            pass
        event.accept() 

class EpisodeTableWidget(QtGui.QTableView):    
    def __init__(self, overview, parent = None):
        QtGui.QTableView.__init__(self, parent)
        
        self.overview = overview
        self.verticalHeader().setDefaultSectionSize(125)
        self.horizontalHeader().setStretchLastSection(True)
        self.setShowGrid(False)
        self.setSelectionBehavior(QtGui.QTableView.SelectRows)
        self.setAcceptDrops(True)


    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event): 
        filepaths = [url.toLocalFile() for url in event.mimeData().urls()] 
        series = mainwindow.existing_series
        dropIndex = self.indexAt(event.pos())   
        mainwindow.add_movieclip_to_episode(filepaths[0], series[dropIndex.row()])
        event.accept() 

    def setModel(self, model):
        try:
            if model.filled:
                QtGui.QTableView.setModel(self, model)               
                model.dataChanged.connect(self.callback)
                self.selectionModel().selectionChanged.connect(self.callback)
                self.overview.stacked_widget.setCurrentWidget(self)
            else:
                self.overview.stacked_widget.setCurrentWidget(self.overview.waiting_widget)

        except AttributeError:
            self.overview.stacked_widget.setCurrentWidget(self.overview.getting_started_widget)

class EpisodeOverviewWidget(QtGui.QWidget):    
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        
        self.stacked_widget = QtGui.QStackedWidget() 
        
        self.tableview = EpisodeTableWidget(self)        
        self.waiting_widget = WaitingWidget() 
        self.getting_started_widget = GettingStartedWidget() 
        
        self.stacked_widget.addWidget(self.tableview)
        self.stacked_widget.addWidget(self.waiting_widget)
        self.stacked_widget.addWidget(self.getting_started_widget)
        self.stacked_widget.setCurrentWidget(self.waiting_widget)
        
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(self.stacked_widget)
        self.setLayout(vbox)

class GettingStartedWidget(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        vbox = QtGui.QVBoxLayout()
        vbox.addWidget(QtGui.QLabel("Getting started!"))
        vbox.addStretch(20)
        self.setLayout(vbox)


class SeriesInformationDock(QtGui.QDockWidget):
    def __init__(self, parent = None):
        QtGui.QDockWidget.__init__(self, parent)
        self.seriesinfo = SeriesInformationWidget() 
        scrollArea = QtGui.QScrollArea()
        scrollArea.setWidgetResizable(True)
        #scrollArea.setMinimumWidth(325) # TODO
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
        
    def handle_tab_change(self, index):
        if index == self.tab.indexOf(self.dummywidget):
            self.tab.setCurrentWidget(self.local_search)
            mainwindow.start_series_adder_wizard()





class MultipleAssociationWizard(QtGui.QWizard):
    selection_finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, movieclip_associations, parent = None):
        QtGui.QWizard.__init__(self, parent)    
        self.movieclip_associations = movieclip_associations
        diribeoutils.resize_to_percentage(self, 50) 
        self.addPage(MultipleAssociationTable(movieclip_associations))
        self.accepted.connect(self.wizard_complete)
    
    def wizard_complete(self):        
        filtered_movieclip_associations = [movieclip_asssociation for movieclip_asssociation in self.movieclip_associations if not movieclip_asssociation.skip]        
        mainwindow.add_movieclip_associations_to_episodes(filtered_movieclip_associations)


class MultipleAssociationTableModel(QtCore.QAbstractTableModel):
    def __init__(self, movieclip_associations, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.movieclip_associations = movieclip_associations
        
        self.column_lookup = ["Filename", "Message", "Skip?", "Association"]
        self.movieclipassociation_messages = {MovieClipAssociation.ASSOCIATION_FOUND : "Association found",
                                              MovieClipAssociation.ASSOCIATION_GUESSED : "Guessed episode",
                                              MovieClipAssociation.INVALID_FILE : "Invalid file"}
     
    def rowCount(self, index):
        return len(self.movieclip_associations)

    def columnCount(self, index):
        return len(self.column_lookup)
    
    def data(self, index, role):
        movieclip_association = self.movieclip_associations[index.row()]
        
        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return QtCore.QString(os.path.basename(movieclip_association.filepath))
            elif  index.column() == 1:
                message_text = self.movieclipassociation_messages[movieclip_association.message]
                return QtCore.QString(message_text)
            elif index.column() == 3:
                try:
                    return movieclip_association.episode_scores_list
                except KeyError:
                    return QtCore.QVariant()
        
        if role == QtCore.Qt.ToolTipRole:
            if index.column() == 3:
                information = movieclip_association.episode_score_information
                return QtCore.QString("Mean %s\nMedian: %s" % (information["mean"], information["median"]))
        
          
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 2:
                if movieclip_association.message == movieclip_association.INVALID_FILE:
                    return Qt.Checked
                if movieclip_association.skip:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
              
        elif role == QtCore.Qt.BackgroundRole:
            if movieclip_association.skip:
                return diribeoutils.get_gradient(QtGui.QColor(Qt.red))
            try:
                episode, score = movieclip_association.get_associated_episode_score()  
                if score < 8:
                    return diribeoutils.get_gradient(QtGui.QColor(Qt.green))
                elif score < 20:
                    return diribeoutils.get_gradient(QtGui.QColor(Qt.yellow))
                else:
                    return diribeoutils.get_gradient(QtGui.QColor(Qt.red))
            except KeyError:
                pass     
            return diribeoutils.get_gradient(QtGui.QColor(Qt.green))
                
        return QtCore.QVariant()       
     
    def flags(self, index):    
        movieclip_association = self.movieclip_associations[index.row()]
            
        if index.column() == 2: # Skip
            if movieclip_association.message == movieclip_association.INVALID_FILE:
                return  Qt.ItemIsSelectable
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
        if index.column() == 3: 
            return Qt.ItemIsEnabled | Qt.ItemIsEditable        
        return Qt.ItemIsEnabled  
        

    def setData(self, index, value, role = Qt.EditRole):
        movieclip_association = self.movieclip_associations[index.row()]
        
        if role == Qt.CheckStateRole:
            boolean_value = False
            if value == Qt.Checked:
                boolean_value = True            
            movieclip_association.skip = boolean_value 
            self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 3))
            return True
        
        if role == Qt.EditRole:
            if index.column() == 3:
                movieclip_association.episode_list_reference = value
                self.dataChanged.emit(self.index(index.row(), 0), self.index(index.row(), 3))
                return True
        return False
                          
    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                #the column
                return QtCore.QString(self.column_lookup[section])     
                     
class MultipleAssociationTable(QtGui.QWizardPage):
    def __init__(self, movieclip_associations, parent = None):
        QtGui.QWizardPage.__init__(self, parent)
        self.movieclip_associations = movieclip_associations
        self.setTitle("Multiple Assigner")
        self.setSubTitle("This is a ...")
        self.tableview = QtGui.QTableView()
        self.tableview.setShowGrid(False)
        self.tablemodel = MultipleAssociationTableModel(movieclip_associations)
        self.tableview.setItemDelegate(ComboBoxDelegate(movieclip_associations, self.tablemodel))
        self.tableview.horizontalHeader().setStretchLastSection(True)
        
        self.tableview.setModel(self.tablemodel)
        self.tableview.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)
        
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)
        
        vbox.addWidget(self.tableview)
            

class ComboBoxDelegate(QtGui.QStyledItemDelegate):
    def __init__(self, movieclip_associations, model,  parent = None):
        QtGui.QStyledItemDelegate.__init__(self, parent)
        self.movieclip_associations = movieclip_associations
        self.selections = collections.defaultdict(lambda: int())
    
    def paint(self, painter, option, index):
        
        movieclip_association = self.movieclip_associations[index.row()]
        
        if index.column() == 3:
            try:
                painter.fillRect(option.rect, index.model().data(index, role = QtCore.Qt.BackgroundRole))
                if movieclip_association.message != movieclip_association.INVALID_FILE:
                    episode, score = movieclip_association.episode_scores_list[self.selections[index.row()]]
                    painter.drawText(option.rect, QtCore.Qt.AlignVCenter, episode.get_normalized_name() + " Score: " + str(score))
                
            except KeyError:
                pass  
        else:
            QtGui.QStyledItemDelegate.paint(self, painter, option, index)
        
    
    def createEditor(self, parent, option, index):
        movieclip_association = self.movieclip_associations[index.row()]
        
        if index.column() == 3:
            editor = QtGui.QComboBox(parent)
            
            try:
                for index, [episode, score] in enumerate(movieclip_association.episode_scores_list):
                    editor.insertItem(index, episode.get_normalized_name() + " Score: " + str(score))
                    editor.setItemData(index, score, role = Qt.ToolTipRole)
                return editor
            except KeyError:
                pass

    def setEditorData(self, comboBox, index):        
        comboBox.setCurrentIndex(self.selections[index.row()])

    def setModelData(self, comboBox, model, index):
        value = comboBox.currentIndex()
        self.selections[index.row()] = value 
        comboBox.setCurrentIndex(value)
        model.setData(index, value, QtCore.Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)           

class SeriesAdderWizard(QtGui.QWizard):
    selection_finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, jobs, parent = None):
        QtGui.QWizard.__init__(self, parent)         
        self.online_search = OnlineSearch(jobs)
        self.addPage(self.online_search)
        self.accepted.connect(self.wizard_complete)
    
    def wizard_complete(self):
        self.selection_finished.emit(self.online_search.onlineserieslist.selectedItems())
       
        
class OnlineSearch(QtGui.QWizardPage):
    def __init__(self, jobs, parent = None):
        QtGui.QWizardPage.__init__(self, parent)

        self.jobs = jobs

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
        
        self.seriessearcher = SeriesSearchWorker(self.onlinesearchfield)
        self.seriessearcher.nothing_found.connect(diribeomessageboxes.nothing_found_warning)
        self.seriessearcher.results.connect(self.add_items)
        self.onlinesearchbutton.clicked.connect(self.search, Qt.QueuedConnection)    
        
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):           
            self.search()             
                  
    def search(self):      
        if len(self.onlinesearchfield.text()) > 0:  
            self.jobs.append(self.seriessearcher)          
            self.seriessearcher.start()
            
    def add_items(self, items):
        self.onlineserieslist.clear()
        for downloaded_series in items:
            self.onlineserieslist.addItem(SeriesWidgetItem(downloaded_series)) 

class WaitingWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        hbox = QtGui.QHBoxLayout()
        vbox = QtGui.QVBoxLayout()
        self.setAutoFillBackground(True)
        
        vbox.setSpacing(3)
        vbox.addStretch(10)
        vbox.addWidget(AnimatedLabel("images/process-working.png", 8, 4))
        vbox.addWidget(QtGui.QLabel("Downloading ..."))
        vbox.addStretch(20)
        
        hbox.setSpacing(3)
        hbox.addStretch(20)
        hbox.addLayout(vbox)
        hbox.addStretch(20)
        
        self.setLayout(hbox)
 
class About(QtGui.QDialog):
    def __init__(self, jobs, parent = None):
        QtGui.QDialog.__init__(self, parent) 
        diribeoutils.resize_to_percentage(self, 25) 
        self.setWindowTitle('About') 
        
        self.jobs = jobs
        self.vboxlayout = QtGui.QVBoxLayout()
        self.update_layout = QtGui.QHBoxLayout()  
        self.setLayout(self.vboxlayout)
        diribeo_icon = QtGui.QIcon("images/diribeo_logo.png")
        self.diribeo_button = QtGui.QPushButton()
        self.diribeo_button.setIcon(diribeo_icon)
        self.diribeo_button.setIconSize(QtCore.QSize(200,200))
        self.diribeo_button.clicked.connect(functools.partial(QtGui.QDesktopServices.openUrl, QtCore.QUrl("http://www.diribeo.de")))
        
        self.vboxlayout.addWidget(self.diribeo_button)
        self.vboxlayout.addWidget(QtGui.QLabel("Diribeo is an open source application. To get more information about it check out http://www.diribeo.de"))
        self.vboxlayout.addLayout(self.update_layout)
        
        
        self.update_image_label = QtGui.QLabel()
        self.update_label = QtGui.QLabel("Checking for updates ...")
        self.update_layout.addWidget(self.update_image_label)
        self.update_layout.addWidget(self.update_label)
        self.update_layout.addStretch(1)
        
        self.get_version_update()

    def get_version_update(self):
        job = VersionChecker(__version__)
        job.finished.connect(self.update_version)
        self.jobs.append(job)
        job.start()

    
    def version_to_string(self, version):
        return ".".join([str(x) for x in version])
    
    def update_version(self, version):
        text = ""
        pixmap_location = ""
        
        
        if version == __version__:
            text = "Diribeo is up-to-date (%s)" % self.version_to_string(__version__)
            pixmap_location = "images/emblem-favorite.png"
        elif version > __version__:
            text = "There is a newer version available. Your version is %s, version available is %s" % (self.version_to_string(__version__), self.version_to_string(version))
            pixmap_location = "images/face-sad.png"
        else:
            text = "W0ot? Your version is newer than the newest version! Get lost!"
            pixmap_location = "images/face-surprise.png"
             
        self.update_label.setText(text)
        self.update_image_label.setPixmap(QtGui.QPixmap(pixmap_location))

class SourceSelectionSettings(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        
        self.hboxlayout = QtGui.QHBoxLayout()
        self.setLayout(self.hboxlayout)
        
        self.source_settings_groupbox = QtGui.QGroupBox("Sources")
        self.form_layout = QtGui.QFormLayout()
        self.source_settings_groupbox.setLayout(self.form_layout)
        self.hboxlayout.addWidget(self.source_settings_groupbox)
        
        self.implementation_checkboxes = {}
        
        for implementation in settings.get_sources():
            self.implementation_checkboxes[implementation] = current_checkbox = QtGui.QCheckBox()
            current_checkbox.setChecked(settings.settings["sources"][implementation])
            self.form_layout.addRow(implementation, current_checkbox)
        
class StatisticsSettings(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        
        self.hboxlayout = QtGui.QHBoxLayout()
        self.setLayout(self.hboxlayout)
        
        self.statistics_settings_groupbox = QtGui.QGroupBox("Statistics")
        self.form_layout = QtGui.QFormLayout()
        self.statistics_settings_groupbox.setLayout(self.form_layout)
        self.hboxlayout.addWidget(self.statistics_settings_groupbox)
        
class GeneralSettings(QtGui.QWidget):
    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        
        self.hboxlayout = QtGui.QHBoxLayout()
        self.setLayout(self.hboxlayout)
        
        self.general_settings_groupbox = QtGui.QGroupBox("General Settings")
        self.hboxlayout.addWidget(self.general_settings_groupbox)
        
        self.form_layout = QtGui.QFormLayout()
        self.general_settings_groupbox.setLayout(self.form_layout)
        
        self.copy_associated_movieclips_checkbox = QtGui.QCheckBox()
        self.copy_associated_movieclips_checkbox.setChecked(settings.get("copy_associated_movieclips"))
        
        self.automatic_thumbnail_creation_checkbox = QtGui.QCheckBox()
        self.automatic_thumbnail_creation_checkbox.setChecked(settings.get("automatic_thumbnail_creation"))
        
        self.show_all_movieclips_checkbox = QtGui.QCheckBox()
        self.show_all_movieclips_checkbox.setChecked(settings.get("show_all_movieclips"))
        
        self.normalize_names_checkbox = QtGui.QCheckBox()
        self.normalize_names_checkbox.setChecked(settings.get("normalize_names"))
        
        self.hash_movieclips_checkbox = QtGui.QCheckBox()
        self.hash_movieclips_checkbox.setChecked(settings.get("hash_movieclips"))
        
        
        self.number_of_thumbnails_edit = QtGui.QLineEdit(str(settings.get("number_of_thumbnails")))
        
        self.deployment_folder_edit = QtGui.QLineEdit(str(settings.get("deployment_folder")))

        
        self.form_layout.addRow("Copy assoicated movieclips", self.copy_associated_movieclips_checkbox)
        self.form_layout.addRow("Automatically create thumbnails", self.automatic_thumbnail_creation_checkbox)
        self.form_layout.addRow("Show all movieclips", self.show_all_movieclips_checkbox)
        self.form_layout.addRow("Normalize names", self.normalize_names_checkbox)
        self.form_layout.addRow("Hash movieclips", self.hash_movieclips_checkbox)
        self.form_layout.addRow("Number of thumbnails created", self.number_of_thumbnails_edit)
        self.form_layout.addRow("Deployment folder", self.deployment_folder_edit)



class SettingsEditor(QtGui.QDialog):
    def __init__(self, parent = None):
        QtGui.QDialog.__init__(self, parent)
            
        diribeoutils.resize_to_percentage(self, 50)

        self.main_layout = QtGui.QVBoxLayout()
        self.header_layout = QtGui.QHBoxLayout()
        self.button_layout = QtGui.QHBoxLayout()  
        self.view_layout = QtGui.QHBoxLayout()      
        self.setLayout(self.main_layout)
        
        self.stacked_widget = QtGui.QStackedWidget()
        
        self.setWindowTitle('Settings')
        
        # Create General Settings Groupbox
        self.general_settings_groupbox = GeneralSettings()
        self.stacked_widget.addWidget(self.general_settings_groupbox)
        
        # Create Sources Settings Groupbox
        self.sources_settings_groupbox = SourceSelectionSettings()
        self.stacked_widget.addWidget(self.sources_settings_groupbox)
       
        # Create Statistic Settings Groupbox
        self.statistic_settings_groupbox = StatisticsSettings()
        self.stacked_widget.addWidget(self.statistic_settings_groupbox)       
       
        
        # Build chooser which is at the left side of the window
        self.chooser_toolbar = QtGui.QToolBar()
        self.chooser_toolbar.setOrientation(Qt.Vertical)
        self.chooser_toolbar.setIconSize(QtCore.QSize(128, 128))
        
        # Create buttons
        
        # Create general button 
        icon_general_settings = QtGui.QIcon("images/dialog-information.png")
        general_settings_button = QtGui.QToolButton()
        general_settings_button.setIcon(icon_general_settings)
        general_settings_button.setText("General Settings")
        general_settings_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        general_settings_button.clicked.connect(functools.partial(self.stacked_widget.setCurrentWidget, self.general_settings_groupbox))
        
        
        # Create sources button
        icon_source_settings = QtGui.QIcon("images/internet-web-browser.png")
        source_settings_button = QtGui.QToolButton()
        source_settings_button.setIcon(icon_source_settings)
        source_settings_button.setText("Sources")
        source_settings_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        source_settings_button.clicked.connect(functools.partial(self.stacked_widget.setCurrentWidget, self.sources_settings_groupbox))
        
        
        # Statistic settings
        icon_statistic_settings = QtGui.QIcon("images/applications-accessories.png")
        statistic_settings_button = QtGui.QToolButton()
        statistic_settings_button.setIcon(icon_statistic_settings)
        statistic_settings_button.setText("Statistics")
        statistic_settings_button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        statistic_settings_button.clicked.connect(functools.partial(self.stacked_widget.setCurrentWidget, self.statistic_settings_groupbox))
        
        
        self.chooser_toolbar.addWidget(general_settings_button)
        self.chooser_toolbar.addWidget(source_settings_button)
        self.chooser_toolbar.addWidget(statistic_settings_button)
        
        self.default_settings_button = QtGui.QPushButton('Reset to default settings', self)
        self.default_settings_button.clicked.connect(self.reset_settings)
        
        self.view_layout.addWidget(self.chooser_toolbar)
        self.view_layout.addWidget(self.stacked_widget)
        
        self.okay_button = QtGui.QPushButton("Save settings")
        self.okay_button.pressed.connect(self.save_settings)
        self.cancel_button = QtGui.QPushButton("Discard changes")
        self.cancel_button.pressed.connect(self.hide)
        
        self.button_layout.addStretch(1)
        self.button_layout.addWidget(self.okay_button)
        self.button_layout.addWidget(self.cancel_button)
        
        self.main_layout.addLayout(self.view_layout)
        self.main_layout.addWidget(self.default_settings_button)
        self.main_layout.addLayout(self.button_layout)   
        

    def reset_settings(self):
        settings.reset()
        self.hide()
        
    def save_settings(self):
        # Handle General Settings
        settings["copy_associated_movieclips"] = self.general_settings_groupbox.copy_associated_movieclips_checkbox.checkState()
        settings["automatic_thumbnail_creation"] = self.general_settings_groupbox.automatic_thumbnail_creation_checkbox.checkState()
        settings["show_all_movieclips"] = self.general_settings_groupbox.show_all_movieclips_checkbox.checkState()
        settings["normalize_names"] = self.general_settings_groupbox.normalize_names_checkbox.checkState()
        settings["hash_movieclips"] = self.general_settings_groupbox.hash_movieclips_checkbox.checkState()
        try:
            settings["number_of_thumbnails"] = int(self.general_settings_groupbox.number_of_thumbnails_edit.text())
        except ValueError:
            settings["number_of_thumbnails"] = 8
        
        settings["deployment_folder"] = str(self.general_settings_groupbox.deployment_folder_edit.text())
        
        
        # Handle Source Settings
        checkbox_dict = self.sources_settings_groupbox.implementation_checkboxes
        settings.settings["sources"] = dict([[implementation, bool(checkbox_dict[implementation].checkState())] for implementation in  checkbox_dict])
        
        self.hide()

class MainWindow(QtGui.QMainWindow):
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)

        self.existing_series = None # stores the currently active series object
        
        self.episode_overview_widget = EpisodeOverviewWidget()   
        self.setCentralWidget(self.episode_overview_widget)
        self.tableview = self.episode_overview_widget.tableview
        self.tableview.callback = self.load_episode_information_at_index
        self.tableview.horizontalHeader().setResizeMode(QtGui.QHeaderView.ResizeToContents)

        # Initialize worker thread manager
        self.jobs = WorkerThreadManager()

        # Initialize the status bar        
        self.setStatusBar(self.jobs.statusbar)
        
        # Initialize the progress bar and assign to the statusbar
        self.progressbar = self.jobs.progressbar  
        self.progressbar.setMaximumHeight(10)
        self.progressbar.setMaximumWidth(100)
        
        # Initialize local and online search
        local_search_dock = self.local_search_dock = LocalSearchDock()
        self.local_search = local_search_dock.local_search
        
        # Initialize series info doc
        series_info_dock = SeriesInformationDock()
        self.seriesinfo =  series_info_dock.seriesinfo
        
        self.build_menu_bar()
        
        # Manage the docks
        self.addDockWidget(Qt.LeftDockWidgetArea, local_search_dock)                            
        self.addDockWidget(Qt.RightDockWidgetArea, series_info_dock)
        
        self.local_search.localseriestree.itemClicked.connect(self.load_into_local_table)         
        self.seriesinfo.delete_button.clicked.connect(self.delete_series)
        self.seriesinfo.tableview = self.tableview
        
        self.load_all_series_into_their_table()
        self.tableview.setModel(None)
        
        self.setWindowTitle("Diribeo")
        diribeoutils.resize_to_percentage(self, 75)
        self.center()

    def build_menu_bar(self):
        menubar = self.menuBar()
        settings = menubar.addMenu('&Settings')
        change_settings = QtGui.QAction(QtGui.QIcon(), 'Change Settings', self)
        change_settings.triggered.connect(self.start_settings_editor)
        settings.addAction(change_settings)
        
        help = menubar.addMenu('&Help')
        about = QtGui.QAction(QtGui.QIcon(), 'About', self)
        about.triggered.connect(self.start_about)
        help.addAction(about)


    def closeEvent(self, event):
        self.hide()
        settings.save_configs()
    
    
    def start_about(self):
        about = About(self.jobs)
        about.show()
        about.exec_()
    
    def start_settings_editor(self):
        settings = SettingsEditor()
        settings.show()
        settings.exec_()
    
    def start_series_adder_wizard(self):
        wizard = SeriesAdderWizard(self.jobs)
        wizard.selection_finished.connect(self.load_items_into_table)             
        wizard.show()
        wizard.exec_()
     
    def update_movie(self, movie):
        job = MovieUpdater(movie)
        job.finished.connect(functools.partial(self.seriesinfo.load_information, movie))
        job.finished.connect(functools.partial(self.rebuild_after_update, movie))
        self.jobs.append(job)
        job.start()
    
    def load_series_info_from_episode(self, episode):
        assert isinstance(episode, Episode)
        self.seriesinfo.load_information(episode.get_series())
    
    
    def start_multiple_association_wizard(self, movieclip_associations):
        wizard = MultipleAssociationWizard(movieclip_associations)
        wizard.show()
        wizard.exec_()
    
    def start_assign_dialog(self, movie):
        
        if isinstance(movie, Episode):
            filepath = QtGui.QFileDialog.getOpenFileName(directory = settings.get_user_dir())
            if filepath != "":
                mainwindow.add_movieclip_to_episode(filepath, movie)
                
        else:
            filepath_dir_list = QtGui.QFileDialog.getOpenFileNames(directory = settings.get_user_dir())
            mainwindow.multiple_assigner(filepath_dir_list, movie)
        
    
    def start_association_wizard(self, filepath, episodes, movieclip):
        association_wizard = AssociationWizard(episodes, os.path.basename(filepath))
        association_wizard.selection_finished.connect(functools.partial(self.add_movieclip_to_episode, filepath, movieclip = movieclip), Qt.QueuedConnection)
        association_wizard.show()
        association_wizard.exec_()

    def generate_thumbnails(self, episode, movieclip):
        job = ThumbnailGenerator(movieclip, episode)
        job.thumbnails_created.connect(self.seriesinfo.load_information, Qt.QueuedConnection)
        job.error_in_thumbnail_creation.connect(functools.partial(diribeomessageboxes.error_in_thumbnail_creation_warning, movieclip, episode), Qt.QueuedConnection)        
        self.jobs.append(job)
        job.start()

    
    def multiple_assigner(self, filepath_dir_list, series):
        if len(filepath_dir_list) > 0:
            job = MultipleAssignerThread(filepath_dir_list, series)
            job.result.connect(self.start_multiple_association_wizard, Qt.QueuedConnection)
            self.jobs.append(job)
            job.start()
        

    def add_movieclip_to_episode(self, filepath, movie):
        movieclip_association = MovieClipAssociation(str(filepath))            
        movieclip_association.episode_scores_list = [[movie, 0]]
        mainwindow.add_movieclip_associations_to_episodes([movieclip_association])

    def add_movieclip_associations_to_episodes(self, movieclip_associations):      
        job = MultipleMovieClipAssociator(movieclip_associations) 
        job.load_information.connect(self.seriesinfo.load_information, Qt.QueuedConnection)
        job.already_exists.connect(diribeomessageboxes.already_exists_warning, Qt.QueuedConnection)
        job.already_exists_in_another.connect(diribeomessageboxes.display_duplicate_warning, Qt.QueuedConnection)
        job.filesystem_error.connect(diribeomessageboxes.filesystem_error_warning, Qt.QueuedConnection)
        self.jobs.append(job)
        job.start()
    

    def rebuild_after_update(self, movie):
        if isinstance(movie, Series):
            self.local_search.update_tree(movie)
            active_table_models[movie].refresh_table()
        else:
            active_table_models[movie.get_series()].refresh_row(movie.number-1)
        
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
                    
            # Delete the series's table model
            del active_table_models[series] 
            
            self.tableview.setModel(None)
            
            # Clear all information in the series information widget
            self.seriesinfo.clear_all_info()
        
    def center(self):
        screen = QtGui.QDesktopWidget().screenGeometry()
        size =  self.geometry()
        self.move((screen.width()-size.width())/2, (screen.height()-size.height())/2)


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
            series_load_info = existing_series        
    
            if len(indextrace) == 0:
                #clicked on a series
                goto_row = 0            
            elif len(indextrace) == 1:
                #clicked on a season            
                goto_row = existing_series.accumulate_episode_count(index.row()-1)            
            else:
                #clicked on an episode            
                goto_row = existing_series.accumulate_episode_count(index.parent().row()-1) + index.row()             
                series_load_info = existing_series[goto_row]
    
            goto_index = active_table_models[existing_series].index(goto_row, 0)
    
            self.seriesinfo.load_information(series_load_info)
    
            self.tableview.scrollTo(goto_index, QtGui.QAbstractItemView.PositionAtTop)

    def load_episode_information_at_index(self, selected, deselected):
        index = QtCore.QModelIndex()       
        try:
            index = selected.indexes()[0]
        except AttributeError:
            index = selected
        except IndexError, TypeError:  
            pass
        finally:
            self.seriesinfo.load_information(self.existing_series[index.row()])


    def load_all_series_into_their_table(self):
        for series in series_list:
            self.load_existing_series_into_table(series)        

    def load_existing_series_into_table(self, series):
        self.existing_series = series
        try:
            self.tableview.setModel(active_table_models[series]) 
        except KeyError:
            active_table_models[series] = model = EpisodeTableModel(series)
            model.filled = True
            self.tableview.setModel(model)
            
            
    def load_items_into_table(self, series_items):
        ''' Loads the selected episodes from the online serieslist into its designated model.
            If the series already exists the already existing series is loaded into the table view.
        '''
        
        assert len(series_items) <= 1 # Make sure only one item is passed to this function since more than one item can cause concurrency problems     
        
        for series_item in series_items:
            downloaded_series = series_item.downloaded_series           
            movie = downloaded_series.internal_representation
            identifier = downloaded_series.identifier

            self.existing_series = existing_series = library.get_series_from_identifier(identifier)            
            
            if existing_series is None: 
                current_series = Series(downloaded_series.title, identifier = identifier)
                series_list.append(current_series)
                active_table_models[current_series] = model = EpisodeTableModel(current_series)
                self.tableview.setModel(model)
                
                self.existing_series = current_series                
                job = ModelFiller(model, movie)
                job.update_tree.connect(self.local_search.update_tree, type = QtCore.Qt.QueuedConnection)
                job.update_seriesinformation.connect(self.seriesinfo.load_information, type = QtCore.Qt.QueuedConnection)
                job.update_tableview.connect(self.tableview.setModel)
                job.insert_into_tree.connect(self.local_search.insert_top_level_item, type = QtCore.Qt.QueuedConnection)
                self.jobs.append(job)
                job.start()
                                  
            else:
                self.load_existing_series_into_table(existing_series)


class AssociationWizard(QtGui.QWizard):
    selection_finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, episodes, filename, parent = None):
        QtGui.QWizard.__init__(self, parent)
        self.episode_chooser = EpisodeChooser(episodes, filename)
        self.addPage(self.episode_chooser)
        self.accepted.connect(self.wizard_complete)

    def wizard_complete(self):
        self.selection_finished.emit(self.episode_chooser.get_selected_episode())

class EpisodeChooser(QtGui.QWizardPage):    
    
    def __init__(self, episodes_scores, filename, parent = None):
        QtGui.QWizardPage.__init__(self, parent) 
        self.episodes_scores = episodes_scores
        self.setTitle("Episode Chooser")
        self.setSubTitle("If you're only seeing crap, its probably your fault. \nThe original filename is: " + filename)
        layout = QtGui.QVBoxLayout()
        self.setLayout(layout)
        self.episode_list = QtGui.QListWidget()
        layout.addWidget(self.episode_list)
        
        for episode_score in episodes_scores:
            self.episode_list.addItem(EpisodeWidgetItem(episode_score))

        self.episode_list.setSelection(QtCore.QRect(0,0,1,1), QtGui.QItemSelectionModel.Select)
        
    def get_selected_episode(self):
        try:
            return self.episode_list.selectedItems()[0].episode
        except IndexError:
            pass

class EpisodeWidgetItem(QtGui.QListWidgetItem):
    def __init__(self, episode_score,  parent = None):
        QtGui.QListWidgetItem.__init__(self, parent)
        episode, score = episode_score
        self.episode = episode     
        title = episode.get_normalized_name()
        self.setText(title)
        self.setToolTip("Score: " + str(score))    

class ToolBar(QtGui.QToolBar):
    def __init__(self, parent = None):
        QtGui.QToolBar.__init__(self, parent)
        icon = QtGui.QIcon("images/network-error.png")
        action = QtGui.QAction(icon, "test", self)
        self.addAction(action)


class AnimatedLabel(QtGui.QLabel):    
    #http://www.qtcentre.org/threads/26911-PNG-based-animation
    def __init__(self, image, imageCount_x, imageCount_y, parent=None):
        QtGui.QLabel.__init__(self, parent)
        
        assert os.path.isfile(image), "Image is not a valid file: " + image + " " + os.getcwd()
    
        self.pixmaps = []
        self.currentPixmap = 1
        self.timer = QtCore.QTimer()
        img = QtGui.QImage()
        img.load(image)
        subImageHeight = img.height() / imageCount_y
        subImageWidth = img.width() / imageCount_x
        
        for i in range(imageCount_y):
            for p in range(imageCount_x):
                subImage = img.copy(p * subImageHeight, i * subImageWidth, subImageWidth, subImageHeight)
                self.pixmaps.append(QtGui.QPixmap.fromImage(subImage))

        self.timer.timeout.connect(self.changeImage)
        self.timer.start(25)
        self.changeImage()
    
    def changeImage(self):
        if self.currentPixmap >= len(self.pixmaps):
            self.currentPixmap  = 1
        
        self.setPixmap(self.pixmaps[self.currentPixmap])
        self.currentPixmap += 1 


class SeriesWidgetItem(QtGui.QListWidgetItem):
    def __init__(self, downloaded_series, parent = None):
        QtGui.QListWidgetItem.__init__(self, parent)
        self.downloaded_series = downloaded_series
        self.setText(self.downloaded_series.title)
        self.setToolTip(self.downloaded_series.identifier.keys()[0])
       
if __name__ == "__main__":

    app = QtGui.QApplication(sys.argv)
    
    library = diribeowrapper.library
    active_table_models = {}

    settings = diribeomodel.settings
    series_list = diribeomodel.series_list
    movieclips = diribeomodel.movieclips    

    mainwindow = MainWindow()
    mainwindow.show()
    
    app.exec_()