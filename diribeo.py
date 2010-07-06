# -*- coding: utf-8 -*-

__author__ = 'David Kaufman'
__version__ = '0.0.1dev'
__license__ = 'pending'


import sys
import os
import logging as log

import subprocess
import functools
import diribeomessageboxes
import diribeomodel

from diribeomodel import Series, Episode, save_configs
from diribeoworkers import SeriesSearchWorker, ModelFiller, MovieClipAssigner, ThumbnailGenerator, MovieClipAssociator, MovieClipGuesser
from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt


# Initialize the logger
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
        list_of_descriptions = [worker_thread[0].description for worker_thread in self.worker_thread_dict.items()]
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

    def set_generator(self, generator):
        self.generator = generator

    def rowCount(self, index):
        return len(self.episodes)

    def columnCount(self, index):
        return len(self.column_lookup)

    def data(self, index, role):
        episode = self.episodes[index.row()]        
        if role == QtCore.Qt.DisplayRole:
            if index.column() != 2:
                return QtCore.QString(unicode(self.row_lookup(episode)[index.column()])) 
         
        elif role == QtCore.Qt.DecorationRole:
            if index.column() == 0:
                return create_default_image(episode, additional_text = str(len(episode.get_thumbnails())))
        
        elif role == QtCore.Qt.CheckStateRole:
            if index.column() == 2:
                if self.row_lookup(episode)[2]:
                    return Qt.Checked
                else:
                    return Qt.Unchecked
            
        elif role == QtCore.Qt.BackgroundRole:
            if not episode.seen_it:
                return self.get_gradient_bg(episode.descriptor[0])
            return self.get_gradient_bg(episode.descriptor[0], saturation = 0.5)
        
        elif role == QtCore.Qt.TextAlignmentRole:
            return QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter

        return QtCore.QVariant()     

    
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
    
    def get_gradient_bg(self, index, saturation = 0.25):            
        gradient = QtGui.QLinearGradient(0, 0, 0, 200)
        backgroundcolor = get_color_shade(index, 5, saturation)
        comp_backgroundcolor =  get_complementary_color(backgroundcolor)
        gradient.setColorAt(0.0, comp_backgroundcolor.lighter(50))
        gradient.setColorAt(1.0, comp_backgroundcolor.lighter(150))
        return QtGui.QBrush(gradient)

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
            
        try:
            for filepath in event.mimeData().urls():
                filepath = os.path.abspath(unicode(filepath.toLocalFile()))            
                mainwindow.find_episode_to_movieclip(filepath, series)
            event.accept()
        except IndexError:
            pass
        
        
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
        self.initial_build_tree()

        localframelayout.addWidget(self.localseriestree)
        
        self.toplevel_items = []


    def sort_tree(self):
        # This also sorts children which produces a unwanted sorting
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
            
            print "debug"
            
            for index, filepath in enumerate(self.movieclip.thumbnails):
                if os.path.exists(filepath):
                    temp_label = QtGui.QLabel()
                    qimage = QtGui.QImage(filepath)
                    pixmap = QtGui.QPixmap.fromImage(qimage)
                    pixmap = pixmap.scaledToWidth(100)
                    
                    temp_label.setPixmap(pixmap)
                    temp_label.setToolTip("<img src=':"+ filepath +"'>")
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
        # Not really pythonic
        if folder is not None: 
            try:
                os.startfile(folder) # Linux does not have startfile
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
        filepath = os.path.normpath(self.movieclip.filepath)
        if os.path.isfile(filepath):            
            try:
                os.startfile(filepath) # Linux does not have startfile
            except AttributeError:
                # Not very portable  
                subprocess.Popen(['vlc', filepath])

class MovieClipOverviewWidget(QtGui.QWidget):
    def __init__(self, parent = None, movieclips = None):
        QtGui.QWidget.__init__(self, parent)
        self.vbox = QtGui.QVBoxLayout()
        self.setLayout(self.vbox)        
        self.movieclipinfos = []   
        open_folder_icon = QtGui.QIcon("images/plus.png")
        self.open_folder_button = QtGui.QPushButton(open_folder_icon, "To add movie clips drag them here or click here")
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

class SeriesInformationWidget(QtGui.QStackedWidget):
    
    def __init__(self, parent = None):
        QtGui.QStackedWidget.__init__(self, parent)              
        
        self.main_widget = QtGui.QWidget()        
        main_widget_layout = QtGui.QVBoxLayout()
        main_widget_layout.setSizeConstraint(QtGui.QLayout.SetFixedSize)
        self.main_widget.setLayout(main_widget_layout)
        
        self.seenit = SeriesInformationCategory("Seen it?", type = QtGui.QCheckBox)
        self.title = SeriesInformationCategory("Title", type = SeriesInformationControls)
        self.movieclipwidget = SeriesInformationCategory("Movie Clips", type = MovieClipOverviewWidget)        
        self.director = SeriesInformationCategory("Director")
        self.rating = SeriesInformationCategory("Ratings")
        self.airdate = SeriesInformationCategory("Air Date")
        self.plot = SeriesInformationCategory("Plot", type = QtGui.QTextEdit)
        self.genre = SeriesInformationCategory("Genre")
        
        self.main_widgets = [self.title, self.seenit, self.movieclipwidget, self.director, self.rating, self.airdate, self.plot, self.genre]
        
        for widget in self.main_widgets:
            main_widget_layout.addWidget(widget)
        
        self.nothing_to_see_here_widget = QtGui.QWidget()
        
        self.delete_button = self.title.content.delete_button
        self.update_button = self.title.content.update_button
        
        self.seenit.content.clicked.connect(self.save_seen_it)
        
        self.addWidget(self.main_widget)
        self.addWidget(self.nothing_to_see_here_widget)
        
        self.setCurrentWidget(self.nothing_to_see_here_widget)
        
        self.setAcceptDrops(True)
    
    def save_plot(self):
        text = self.plot.content.toPlainText()
        index = self.tablemodel.index(self.movie.number - 1, 4) #TODO        
        self.tablemodel.setData(index, QtCore.QVariant(text))
        self.plot.content.moveCursor(QtGui.QTextCursor.End)
        
    
    def save_seen_it(self):
        index = self.tablemodel.index(self.movie.number - 1, 2) #TODO
        value = Qt.Unchecked
        if self.seenit.content.isChecked():
            value = Qt.Checked              
        self.tablemodel.setData(index, value, role = Qt.CheckStateRole)
 
    def clear_all_info(self):
        self.setCurrentWidget(self.nothing_to_see_here_widget)

    def load_information(self, movie):
        print "loading information"
        self.movie = movie
        
        self.setCurrentWidget(self.main_widget)
        
        try:            
            self.tablemodel = active_table_models[self.movie.get_series()]
            self.tableview.setModel(self.tablemodel)
            #self.tableview.selectRow(self.movie.number) TODO
        except AttributeError:
            self.tablemodel = None
        
        try:
            self.plot.content.textChanged.disconnect()
        except TypeError:
            pass
            
        
        if isinstance(self.movie, Series):
            self.delete_button.setVisible(True)
            self.plot.setVisible(False)
            self.rating.setVisible(False)
            self.seenit.setVisible(False)
        else:
            self.rating.setVisible(True)
            self.rating.setText(movie.get_ratings()) 
            self.plot.setText(movie.plot)
            self.plot.setVisible(True)
            self.delete_button.setVisible(False)
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
        
        try:
            self.movieclipwidget.content.open_folder_button.clicked.disconnect()
        except TypeError:
            pass
        self.movieclipwidget.content.open_folder_button.clicked.connect(functools.partial(mainwindow.start_assign_dialog, movie))
        self.movieclipwidget.content.load_movieclips(movie)  
        
        self.plot.content.textChanged.connect(self.save_plot)        
        
    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        
    def dropEvent(self, event):        
        try:
            filepath = event.mimeData().urls()[0].toLocalFile()
            if isinstance(self.movie, Episode):
                mainwindow.add_movieclip_to_episode(filepath, self.movie)
            else:
                mainwindow.find_episode_to_movieclip(filepath, self.movie)
            
        except AttributeError, IndexError:
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

    def set_callback(self, callback):
        self.callback = callback

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
        scrollArea.setMinimumWidth(325) # TODO
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
        for item in items:
            movie, title = item
            self.onlineserieslist.addItem(SeriesWidgetItem(movie, title)) 

class WaitingWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        hbox = QtGui.QHBoxLayout()
        vbox = QtGui.QVBoxLayout()
        self.setAutoFillBackground(True)
        #self.setStyleSheet("background-color: white")
        
        #palette = self.palette()
        #palette.setColor(QtGui.QPalette.Window, Qt.white)
        #self.setPalette(palette)
        vbox.setSpacing(3)
        vbox.addStretch(10)
        vbox.addWidget(AnimatedLabel("images/process-working.png", 8, 4))
        vbox.addWidget(QtGui.QLabel("Downloading ..."))
        vbox.addStretch(20)
        #self.setLayout(vbox)
        
        hbox.setSpacing(3)
        hbox.addStretch(20)
        hbox.addLayout(vbox)
        hbox.addStretch(20)
        
        self.setLayout(hbox)
    

class MainWindow(QtGui.QMainWindow):
    def __init__(self, parent = None):
        QtGui.QMainWindow.__init__(self, parent)

        self.existing_series = None # stores the currently active series object
        
        self.episode_overview_widget = EpisodeOverviewWidget()   
        self.setCentralWidget(self.episode_overview_widget)
        self.tableview = self.episode_overview_widget.tableview
        self.tableview.set_callback(self.load_episode_information_at_index)

        # Initialize worker thread manager
        self.jobs = WorkerThreadManager()

        # Initialize the status bar        
        self.setStatusBar(self.jobs.statusbar)
        
        # Initialize the progress bar and assign to the statusbar
        self.progressbar = self.jobs.progressbar  
        self.progressbar.setMaximumHeight(10)
        self.progressbar.setMaximumWidth(100)
        
        # Initialize the tool bar
        self.toolbar = ToolBar()
        self.addToolBar(self.toolbar)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        # Initialize local and online search
        local_search_dock = self.local_search_dock = LocalSearchDock()
        self.local_search = local_search_dock.local_search
        
        # Initialize series info doc
        series_info_dock = SeriesInformationDock()
        self.seriesinfo =  series_info_dock.seriesinfo
        
        # Manage the docks
        self.addDockWidget(Qt.LeftDockWidgetArea, local_search_dock)                            
        self.addDockWidget(Qt.RightDockWidgetArea, series_info_dock)
        
        self.local_search.localseriestree.itemClicked.connect(self.load_into_local_table)         
        self.seriesinfo.delete_button.clicked.connect(self.delete_series)
        self.seriesinfo.tableview = self.tableview
        
        self.load_all_series_into_their_table()
        self.tableview.setModel(None)
        
        self.setWindowTitle("Diribeo")
        self.resize_to_percentage(66)
        self.center()


    def closeEvent(self, event):
        save_configs()
    
    def start_series_adder_wizard(self):
        wizard = SeriesAdderWizard(self.jobs)
        wizard.selection_finished.connect(self.load_items_into_table)             
        wizard.show()
        wizard.exec_()
    
    def start_assign_dialog(self, movie):
        filepath = QtGui.QFileDialog.getOpenFileName(directory = settings.get_user_dir())
        if filepath != "":
            if isinstance(movie, Episode):
                mainwindow.add_movieclip_to_episode(filepath, movie)
            else:
                mainwindow.find_episode_to_movieclip(filepath, movie)
        
    
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

    def guess_episode_with_movieclip(self, movieclip, series):
        job = MovieClipGuesser(movieclip, series)
        job.possible_matches_found.connect(self.start_association_wizard, Qt.QueuedConnection)
        self.jobs.append(job)
        job.start()

    def find_episode_to_movieclip(self, filepath, series):        
        job = MovieClipAssigner(filepath, series)
        job.no_association_found.connect(functools.partial(diribeomessageboxes.no_association_found, self, self))     
        job.already_exists.connect(diribeomessageboxes.already_exists_warning, Qt.QueuedConnection)
        job.association_found.connect(diribeomessageboxes.association_found_info, Qt.QueuedConnection)
        job.filesystem_error.connect(diribeomessageboxes.filesystem_error_warning, Qt.QueuedConnection)
        self.jobs.append(job)       
        job.start()

    def add_movieclip_to_episode(self, filepath, episode, movieclip = None):        
        job = MovieClipAssociator(filepath, episode, movieclip = movieclip) 
        job.load_information.connect(self.seriesinfo.load_information, Qt.QueuedConnection)
        job.already_exists.connect(diribeomessageboxes.already_exists_warning, Qt.QueuedConnection) 
        job.already_exists_in_another.connect(functools.partial(diribeomessageboxes.display_duplicate_warning, self), Qt.QueuedConnection)             
        job.filesystem_error.connect(diribeomessageboxes.filesystem_error_warning, Qt.QueuedConnection)
        self.jobs.append(job)
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
        index = QtCore.QModelIndex()       
        try:
            index = selected.indexes()[0]
        except AttributeError:
            index = selected
        except IndexError, TypeError:  
            pass
        finally:
            self.seriesinfo.load_information(self.existing_series[index.row()])           
            self.tableview.selectRow(index.row())


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
            
            
    def load_items_into_table(self, items):
        ''' Loads the selected episodes from the online serieslist into its designated model.
            If the series already exists the already existing series is loaded into the table view.
        '''
        
        assert len(items) <= 1 # Make sure only one item is passed to this function since more than one item can cause concurrency problems     
        
        for item in items:           
            movie = item.movie

            self.existing_series = existing_series = imdbwrapper.get_series_from_movie(movie)            
            
            if existing_series is None: 
                current_series = Series(item.title)
                series_list.append(current_series)
                active_table_models[current_series] = model = EpisodeTableModel(current_series)
                self.tableview.setModel(model)
                
                self.existing_series = current_series                
                job = ModelFiller(model, movie = movie)
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
        
        assert os.path.isfile(image), "Image is not a valid file: " + image
    
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
    def __init__(self, movie, title, parent = None):
        QtGui.QListWidgetItem.__init__(self, parent)        
        self.movie = movie
        self.title = title
        self.setText(title)


            
def create_default_image(episode, additional_text = ""):
    multiplikator = 5
    width = 16 * multiplikator
    heigth = 10 * multiplikator
    spacing = 1.25

    #extract text
    text = episode.series[0] + "\n" + episode.get_descriptor() + "\n" + additional_text

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


def get_color_shade(index, number_of_colors, saturation = 0.25):      
    return [QtGui.QColor.fromHsvF(colornumber/float(number_of_colors), 1, 0.9, saturation) for colornumber in range(number_of_colors)][index % number_of_colors]


if __name__ == "__main__":

    app = QtGui.QApplication(sys.argv)
    
    imdbwrapper = diribeomodel.imdbwrapper
    active_table_models = {}

    settings = diribeomodel.settings
    series_list = diribeomodel.series_list
    movieclips = diribeomodel.movieclips    

    mainwindow = MainWindow()
    mainwindow.show()
    
    app.exec_()