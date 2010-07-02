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
import logging as log
import shutil
import subprocess
import functools
import shlex
import glob
import uuid


from PyQt4 import QtGui
from PyQt4 import QtCore
from PyQt4.QtCore import Qt
from operator import itemgetter




# Initialize the logger
log_filename = "logger_output.out"
log.basicConfig(filename=log_filename,  format='%(asctime)s %(levelname)s %(message)s', level=log.DEBUG, filemode='w')


class WorkerThread(QtCore.QThread):
    
    # Define various signals        
    waiting = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    
    # Additional thread information
    description = "" # The description which is shown in the statusbar
    
    def __init__(self):
        QtCore.QThread.__init__(self)


class AssignerThread(WorkerThread):
    no_association_found = QtCore.pyqtSignal()
    already_exists = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject") # This signal is emitted when the movieclip is already in the dict and in the folder
    association_found = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    filesystem_error = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    already_exists_in_another = QtCore.pyqtSignal() # Emitted when movieclip is in _another_ episode
    load_information = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self):
        WorkerThread.__init__(self)

    def hash_file(self, file_obj,
                  hasher,
                  callback=lambda byte_count: None,
                  blocksize=4096):
        
        byte_count = 0
        for block in iter(functools.partial(file_obj.read, blocksize), ''):
            hasher.update(block)
            byte_count += len(block)
            # The next line is very important! If you use progress.emit as callback it prevents a deadlock under some conditions
            if byte_count % blocksize ** 2 == 0:                  
                callback(byte_count, self.filesize)
        return hasher.hexdigest()  
    
    
    def calculate_checksum(self):
        self.filesize = os.path.getsize(self.filepath)
    
        # For debugging purposes
        def print_progress(byte_count, filesize):
            print '\r%d/%d %6.2f' % (byte_count,
                                 filesize,
                                 100.0 * byte_count / filesize),
    
        with open(self.filepath, "rb") as iso_file:
            checksum = self.hash_file(iso_file, hashlib.sha224(), self.progress.emit)
            return checksum
        
    

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



class MovieClipGuesser(WorkerThread):
    ''' This class searches for a match in all given episodes. It returns
        a list of possible episodes from which the user can choose one.
        It heavily uses the damerau–levenshtein distance
    '''
    possible_matches_found = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject", "PyQt_PyObject")  # This signal is emitted when possible episodes are found
    
    def __init__(self, movieclip, series):
        WorkerThread.__init__(self)
        self.filepath = movieclip.filepath
        self.movieclip = movieclip
        self.series = series # Can be none
        hint = ""
        if self.series is not None:
            hint = " Hint: " + series.title
            
        self.description = "Guessing a movieclip" + hint
     
    def run(self):
        #TODO CLEAN UP
        self.waiting.emit()
        
        filename, ext = os.path.splitext(os.path.basename(self.filepath))
        
        episode_list = []
        if self.series is None:        
            for series in series_list:
                for episode in series.episodes:
                    episode_list.append(episode)
        else:
            for episode in self.series:
                episode_list.append(episode)

        answer_dict = {}
        
        episode_list_length = len(episode_list)
        counter = 0
        
        for index, episode in enumerate(episode_list):
            title = episode.get_normalized_name()
            alternative_title = episode.get_alternative_name()
            score = min(self.dameraulevenshtein(title, filename),self.dameraulevenshtein(alternative_title, filename))
            answer_dict[episode] = score
            self.progress.emit(counter, episode_list_length)
            counter += 1
        
        items = answer_dict.items()
        items.sort(key = itemgetter(1))

        self.finished.emit()
        
        self.possible_matches_found.emit(self.filepath, items, self.movieclip)
            
        
    def dameraulevenshtein(self, seq1, seq2, lower = False):
        if lower:
            seq1 = seq1.lower()
            seq2 = seq2.lower()
        """Calculate the Damerau-Levenshtein distance between sequences.
    
        This distance is the number of additions, deletions, substitutions,
        and transpositions needed to transform the first sequence into the
        second. Although generally used with strings, any sequences of
        comparable objects will work.
    
        Transpositions are exchanges of *consecutive* characters; all other
        operations are self-explanatory.
    
        This implementation is O(N*M) time and O(M) space, for N and M the
        lengths of the two sequences.
    
        >>> dameraulevenshtein('ba', 'abc')
        2
        >>> dameraulevenshtein('fee', 'deed')
        2
    
        It works with arbitrary sequences too:
        >>> dameraulevenshtein('abcd', ['b', 'a', 'c', 'd', 'e'])
        2
        """
        # codesnippet:D0DE4716-B6E6-4161-9219-2903BF8F547F
        # Conceptually, this is based on a len(seq1) + 1 * len(seq2) + 1 matrix.
        # However, only the current and two previous rows are needed at once,
        # so we only store those.
        oneago = None
        thisrow = range(1, len(seq2) + 1) + [0]
        for x in xrange(len(seq1)):
            # Python lists wrap around for negative indices, so put the
            # leftmost column at the *end* of the list. This matches with
            # the zero-indexed strings and saves extra calculation.
            twoago, oneago, thisrow = oneago, thisrow, [0] * len(seq2) + [x + 1]
            for y in xrange(len(seq2)):
                delcost = oneago[y] + 1
                addcost = thisrow[y - 1] + 1
                subcost = oneago[y - 1] + (seq1[x] != seq2[y])
                thisrow[y] = min(delcost, addcost, subcost)
                # This block deals with transpositions
                if (x > 0 and y > 0 and seq1[x] == seq2[y - 1]
                    and seq1[x-1] == seq2[y] and seq1[x] != seq2[y]):
                    thisrow[y] = min(thisrow[y], twoago[y - 2] + 1)
        return thisrow[len(seq2) - 1]
    
            

class MovieClipAssociator(AssignerThread):
    ''' This class is responsible for associating a movie clip with a given episode.
        It emits various signals which can be used for feedback.
    '''
    
    def __init__(self, filepath, episode, movieclip = None):
        AssignerThread.__init__(self)
        self.episode = episode
        self.filepath = unicode(filepath)
        self.description = "Assigning movieclip to a given episode" 
        
        if movieclip is not None:
            self.clip = movieclip
            # Update identifier
            self.clip.identifier = self.episode.identifier
        else:
            self.clip = None
                        

    def run(self):
        self.identifier = self.episode.get_identifier()
        
        if not os.path.isfile(self.filepath) or not settings.is_valid_file_extension(self.filepath):
            self.filesystem_error.emit(self.episode, self.filepath)
            self.finished.emit()
        else:
            self.waiting.emit()
            if self.clip is None:
                self.checksum = self.calculate_checksum()
            else:
                self.checksum = self.clip.checksum  
        
            if self.clip is None:
                self.clip = MovieClip(self.filepath, identifier = self.episode.identifier, checksum = self.checksum)        
            # Check and see if the movieclip is already associated with _another_ movie and display warning
            unique = movieclips.check_unique(self.clip, self.identifier)
            
            if not unique:
                self.already_exists_in_another.emit()            
            else:
                self.assign()
    
    def assign(self):
        """ Here is a list of possibilities that might occur:
                a) The clip is already in the movieclip dict and in its designated folder
                b) The clip is already in the movieclip dict, but not in its designated folder
                c) The clip is not in the movieclip dict but already in the folder
                d) The clip is not in the movieclip dict and not in the folder
        """
        
        self.waiting.emit()
        
        filename = os.path.basename(self.filepath)
        
        # Calculate hypothetical filepath
        destination = settings.calculate_filepath(self.episode, filename)
        directory = os.path.dirname(destination)
        
        if self.clip in movieclips[self.identifier]:
            
            if os.path.isfile(destination):
                # a)
                self.already_exists.emit(self.episode, self.filepath)
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
            # Check if there is already a file with the same name, normalizes file name if set to do so
            filename = settings.get_unique_filename(destination, self.episode)
            
            # Move the file to the actual folder
            settings.move_file_to_folder_structure(self.episode, self.filepath, new_filename = filename)
            
            # Update the filepath of the clip            
            self.clip.filepath = os.path.join(directory, filename)
    
        if add_to_movieclips:
            # Add the clips to the movie clips manager
            movieclips.add(self.clip)                  
                        
        self.load_information.emit(self.episode)
        self.finished.emit()


     

class MovieClipAssigner(AssignerThread):
    ''' This class is responsible for assigning a movie clip to a unknown episode.
        It calculates the hash value of a the given file and looks for matches in appropiate data structures.
        If no matches are found the "no_association_found' signal is emitted.
        If one or more matches are found the movie clip file is moved/copied to the designated folder.
    '''
    
    def __init__(self, filepath, series):
        AssignerThread.__init__(self)
        self.filepath = unicode(filepath)
        self.series = series # Can be none
        
        hint = ""
        if self.series is not None:
            hint = " Hint: " + series.title
            
        self.description = "Assigning movieclip to a unknown episode" + hint
        
        
    def run(self):
        if not os.path.isfile(self.filepath) or not settings.is_valid_file_extension(self.filepath):
            self.filesystem_error.emit(None, self.filepath)
            self.finished.emit()
        else:           
            self.waiting.emit()     
            self.movieclip = MovieClip(self.filepath, checksum = self.calculate_checksum())
                    
            episode_dict = movieclips.get_episode_dict_with_matching_checksums(self.movieclip.checksum)
                    
            if len(episode_dict.items()) == 0 or episode_dict.items()[0][0] is None:
                self.no_association_found.emit()
                self.finished.emit()   
            else:
                # Assign first movieclip to first episode and first movieclip found
                self.assign(episode_dict.items()[0][0], episode_dict.items()[0][1])
        
    def assign(self, episode, movieclip):        
        
        # Calculate destination of movieclip
        destination = settings.calculate_filepath(episode, os.path.basename(self.filepath))
        
        
        if os.path.isfile(destination):
            # The movie clip is already at its destination
            self.already_exists.emit(movieclip, destination)        
        else:        
            # Extract directory
            directory = os.path.dirname(destination)
            
            # Check if there is already a file with the same name, normalizes file name if set to do so
            filename = settings.get_unique_filename(destination, episode)
            
            # Move the file to its folder
            settings.move_file_to_folder_structure(episode, self.filepath, new_filename = filename)
            
            # Emit associating found signal
            self.association_found.emit(movieclip, episode)
            
            # Change filepath on movieclip object
            movieclip.filepath = os.path.join(directory, filename)
            
        self.finished.emit()
 
 
class ThumbnailGenerator(WorkerThread):
    thumbnails_created = QtCore.pyqtSignal("PyQt_PyObject")
    error_in_thumbnail_creation = QtCore.pyqtSignal()
    
    def __init__(self, movieclip, episode):
        WorkerThread.__init__(self)
        self.filepath = movieclip.filepath
        self.movieclip = movieclip 
        self.episode = episode
        self.image_list = []    
        self.description = "Generating thumbnails"           

    def is_temp_dir_empty(self):
        filelist = glob.glob("*.jpeg")        
        if len(filelist) == 0:
            return True        

    def run(self):
        self.waiting.emit()
        #ffmpeg -i foo.avi -r 1 -s WxH -f image2 foo-%03d.jpeg
        #http://www.ffmpeg.org/ffmpeg-doc.html
        #i = filename, r = framerate, s = size, f = force format, t=duration in s
        unique_identifier = str(uuid.uuid4())
        self.prefix = os.path.join(settings.get_thumbnail_folder(), unique_identifier)
        destination = os.path.join(settings.get_thumbnail_folder(), unique_identifier + "-%03d.jpeg") 
        command = 'ffmpeg -i "'+ os.path.normpath(self.filepath) + '" -r 1/12  -t 50 -ss 90 -f image2 "' + destination + '"'              
        args = shlex.split(str(command)) # does not support unicode input
        proc = subprocess.Popen(args, shell = True, stdout=subprocess.PIPE)
        proc.wait()        
        self.collect_images()
        
        if len(self.image_list) > 0:
            self.movieclip.thumbnails = self.image_list
            self.thumbnails_created.emit(self.episode)
        else:
            self.error_in_thumbnail_creation.emit()
        
        self.finished.emit()
    
    def collect_images(self):
        filelist = glob.glob(self.prefix + "*.jpeg")
        for file in filelist:
            self.image_list.append(file)
        

class SeriesSearchWorker(WorkerThread):
    no_connection_available = QtCore.pyqtSignal() # Is emitted whenever there is no active internet connection available
    nothing_found = QtCore.pyqtSignal()
    results = QtCore.pyqtSignal("PyQt_PyObject")
   
    def __init__(self, searchfield):
        WorkerThread.__init__(self)
        self.searchfield = searchfield
        self.no_connection_available.connect(mainwindow.no_internet_connection_warning)

    def run(self):
        self.waiting.emit()
        
        try:
            result = imdbwrapper.search_movie(self.searchfield.text())
            if len(result) == 0:
                self.nothing_found.emit()
            else:                
                self.results.emit(result)
        except NoConnectionAvailable:
            self.no_connection_available.emit()
        
        self.finished.emit()


class ModelFiller(WorkerThread):
    
    # Initialize various signals.
    insert_into_tree = QtCore.pyqtSignal("PyQt_PyObject")
    update_tree = QtCore.pyqtSignal("PyQt_PyObject")
    update_tableview = QtCore.pyqtSignal("PyQt_PyObject")
    update_seriesinformation = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, model, movie = None):
        WorkerThread.__init__(self)
        self.movie = movie
        self.model = model
        self.series = self.model.series
        self.model.set_generator(imdbwrapper.get_episodes(movie))
        self.description = "Filling a model"

    def run(self): 
                    
        episode_counter = 0

        # Make the progress bar idle
        self.insert_into_tree.emit(self.series)  
        self.waiting.emit()     
        self.update_seriesinformation.emit(self.series)   
        imdbwrapper.get_more_information(self.series, self.movie)
        self.update_seriesinformation.emit(self.series)  
            

        for episode, episodenumber in self.model.generator:            
            self.model.insert_episode(episode)            
            episode_counter += 1
            if episode_counter % 8 == 0:
                self.progress.emit(episode_counter, episodenumber)        
        
        self.model.filled = True          
        self.finished.emit()
        self.update_tree.emit(self.series)
        self.update_tableview.emit(self.model)
             

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
        self.vbox = QtGui.QVBoxLayout()
        self.gridlayout = QtGui.QGridLayout()
        self.vbox.addLayout(self.gridlayout)
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
            
            for filepath in self.movieclip.thumbnails:
                if os.path.exists(filepath):
                    temp_label = QtGui.QLabel()
                    qimage = QtGui.QImage(filepath)
                    pixmap = QtGui.QPixmap.fromImage(qimage)
                    pixmap = pixmap.scaledToWidth(200)
                    
                    temp_label.setPixmap(pixmap)
                    self.vbox.addWidget(temp_label)
        
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
        self.airdate = SeriesInformationCategory("Air Date")
        self.plot = SeriesInformationCategory("Plot", type = QtGui.QTextEdit)
        self.genre = SeriesInformationCategory("Genre")
        
        self.main_widgets = [self.title, self.seenit, self.movieclipwidget, self.director, self.rating, self.airdate, self.plot, self.genre]
        
        for widget in self.main_widgets:
            layout.addWidget(widget)
            
        self.nothing_to_see_here.hide()
        layout.addWidget(self.nothing_to_see_here)
        
        self.delete_button = self.title.content.delete_button
        self.update_button = self.title.content.update_button
        
        self.seenit.content.clicked.connect(self.save_seen_it)
        self.show_main_widget(False)
        
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
        
        try:
            self.tablemodel = active_table_models[self.movie.get_series()]
        except AttributeError:
            self.tablemodel = None
        
        try:
            self.plot.content.textChanged.disconnect()
        except TypeError:
            pass
            
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
        
    def handle_tab_change(self, index):
        if index == self.tab.indexOf(self.dummywidget):
            self.tab.setCurrentWidget(self.local_search)
            mainwindow.start_series_adder_wizard()


class SeriesAdderWizard(QtGui.QWizard):
    selection_finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, parent = None):
        QtGui.QWizard.__init__(self, parent) 
        self.online_search = OnlineSearch()
        self.addPage(self.online_search)
        self.accepted.connect(self.wizard_complete)
    
    def wizard_complete(self):
        self.selection_finished.emit(self.online_search.onlineserieslist.selectedItems())
       
        
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
        
        self.seriessearcher = SeriesSearchWorker(self.onlinesearchfield)
        self.seriessearcher.nothing_found.connect(mainwindow.nothing_found_warning)
        self.seriessearcher.results.connect(self.add_items)
        self.onlinesearchbutton.clicked.connect(self.search, Qt.QueuedConnection)    
        
    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):           
            self.search()             
                  
    def search(self):      
        if len(self.onlinesearchfield.text()) > 0:            
            self.seriessearcher.start()
            
    def add_items(self, items):
        self.onlineserieslist.clear()
        for item in items:
            self.onlineserieslist.addItem(item) 

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
        
        self.jobs.statusbar.addPermanentWidget(self.progressbar)        

        # Initialize the tool bar
        self.toolbar = ToolBar()
        self.addToolBar(self.toolbar)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        
        # Initialize local and online search
        local_search_dock = self.local_search_dock = LocalSearchDock()
        self.local_search = local_search_dock.local_search
        
        # Initialize online doc
        series_info_dock = SeriesInformationDock()
        self.seriesinfo =  series_info_dock.seriesinfo
        
        # Manage the docks
        self.addDockWidget(Qt.LeftDockWidgetArea, local_search_dock)                            
        self.addDockWidget(Qt.RightDockWidgetArea, series_info_dock)
        
        self.local_search.localseriestree.itemClicked.connect(self.load_into_local_table)         
        self.seriesinfo.delete_button.clicked.connect(self.delete_series)
        
        self.load_all_series_into_their_table()
        self.tableview.setModel(None)
        
        self.setWindowTitle("Diribeo")
        self.resize_to_percentage(66)
        self.center()


    def closeEvent(self, event):
        save_movieclips()
        save_series()
        save_settings()

    def no_association_found(self):
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


    def nothing_found_warning(self):
        #TODO        
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "NOTHING FOUND", "")
        messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
        messagebox.setInformativeText("The movie clip is already associated with this episode")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok)
        messagebox.exec_()


                 
    def error_in_thumbnail_creation_warning(self, movieclip, episode):
        #TODO
        filepath = movieclip.filepath
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Warning, "ERROR in THUMBNAIL creation", "")
        messagebox.setText("You're trying to assign a movie clip to the same movie multiple times.")
        messagebox.setInformativeText("The movie clip (" + os.path.basename(filepath) + ") is already associated with this episode")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText(filepath)
        messagebox.exec_()

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

    def no_internet_connection_warning(self):
        #TODO
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "NO INTERNET CONNECTION", "")
        messagebox.setText("You must add a movie clip file to an episode.")
        messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText("nothing")
        messagebox.exec_()
    
    
    def association_found_info(self, movie, episode):
        #TODO
        messagebox = QtGui.QMessageBox(QtGui.QMessageBox.Information, "Association FOUND", "")
        messagebox.setText("You must add a movie clip file to an episode.")
        messagebox.setInformativeText("Make sure that the movie clip you want to add has a proper extension and is not a folder")
        messagebox.setStandardButtons(QtGui.QMessageBox.Ok) 
        messagebox.setDetailedText(str(episode))
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
            self.sender().load_information.emit(self.sender().episode)
            self.sender().quit()

    
    def start_series_adder_wizard(self):
        wizard = SeriesAdderWizard()
        wizard.selection_finished.connect(self.load_items_into_table)             
        wizard.show()
        wizard.exec_()
    
    def start_assign_dialog(self, movie):
        filepath = QtGui.QFileDialog.getOpenFileName(self)
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
        job.error_in_thumbnail_creation.connect(functools.partial(self.error_in_thumbnail_creation_warning, movieclip, episode), Qt.QueuedConnection)        
        self.jobs.append(job)
        job.start()

    def guess_episode_with_movieclip(self, movieclip, series):
        job = MovieClipGuesser(movieclip, series)
        job.possible_matches_found.connect(self.start_association_wizard, Qt.QueuedConnection)
        self.jobs.append(job)
        job.start()

    def find_episode_to_movieclip(self, filepath, series):        
        job = MovieClipAssigner(filepath, series) 
        job.no_association_found.connect(self.no_association_found)     
        job.already_exists.connect(self.already_exists_warning, Qt.QueuedConnection)
        job.association_found.connect(self.association_found_info, Qt.QueuedConnection)
        job.filesystem_error.connect(self.filesystem_error_warning, Qt.QueuedConnection)
        self.jobs.append(job)       
        job.start()

    def add_movieclip_to_episode(self, filepath, episode, movieclip = None):        
        job = MovieClipAssociator(filepath, episode, movieclip = movieclip) 
        job.load_information.connect(self.seriesinfo.load_information, Qt.QueuedConnection)
        job.already_exists.connect(self.already_exists_warning, Qt.QueuedConnection) 
        job.already_exists_in_another.connect(self.display_duplicate_warning, Qt.QueuedConnection)             
        job.filesystem_error.connect(self.filesystem_error_warning, Qt.QueuedConnection)
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

def SeriesOrganizerDecoder(dct):
    if '__date__' in dct:
        return datetime.date.fromordinal(dct["ordinal"])

    if '__episode__' in dct:
        return Episode(title = dct["title"], descriptor = dct["descriptor"], series = dct["series"], plot = dct['plot'], date = dct["date"], identifier = dct["identifier"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], runtime = dct["runtime"], seen_it = dct["seen_it"], number = dct["number"])

    if '__series__' in dct:
        return Series(dct["title"], identifier = dct["identifier"], episodes = dct["episodes"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], date = dct["date"])

    if '__movieclip__' in dct:        
        return MovieClip(dct['filepath'], identifier = dct['identifier'], filesize = dct['filesize'], checksum = dct['checksum'], thumbnails = dct["thumbnails"])
    
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
            return { "__episode__" : True, "title" : obj.title, "descriptor" : obj.descriptor, "series" : obj.series, "plot" : obj.plot, "date" : obj.date, "identifier" : obj.identifier, "rating" : obj.rating, "director" : obj.director, "runtime" : obj.runtime, "genre" : obj.genre, "seen_it" : obj.seen_it, "number" : obj.number}

        if isinstance(obj, datetime.date):
            return { "__date__" : True, "ordinal" : obj.toordinal()}

        if isinstance(obj, Series):
            return { "__series__" : True, "title" : obj.title, "episodes" : obj.episodes, "identifier" : obj.identifier, "rating" : obj.rating,  "director" : obj.director, "genre" : obj.genre, "date" : obj.date}

        if isinstance(obj, MovieClip):
            return { "__movieclip__" : True, "filepath" : obj.filepath, "filesize" : obj.filesize, "checksum" : obj.checksum, "identifier" : obj.identifier, "thumbnails" : obj.thumbnails}        
        
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
                             "deployment_folder" : os.path.join(self.get_user_dir(),"Series"),
                             "automatic_thumbnail_creation" : False,
                             "show_all_movieclips" : True,
                             "normalize_names" : True,
                             "thumbnail_folder" : "images"}
        else:
            self.settings = settings      


        self.valid_extensions = ("mkv", "avi", "mpgeg", "mpg", "wmv", "mp4")

    def get(self, attribute_name):
        try:
            return self.settings[attribute_name]
        except KeyError:
            pass

    def get_thumbnail_folder(self):        
        thumbnail_folder = os.path.join(os.getcwd(), self.settings["thumbnail_folder"])
        if not os.path.exists(thumbnail_folder):
            os.makedirs(thumbnail_folder)
        
        return thumbnail_folder


    def get_normalized_filename(self, filename, episode):
        name, ext = os.path.splitext(filename)
        return episode.get_normalized_name() + ext
    
    
    def get_unique_filename(self, filepath, episode):
        
        directory, filename = os.path.split(filepath)
                
        if self.settings["normalize_names"]:
            filename = self.get_normalized_filename(filename, episode)
           
        return self.get_collision_free_filename(os.path.join(directory, filename))

    def get_collision_free_filename(self, filepath):
        
        directory, filename = os.path.split(filepath)
        
        if os.path.isfile(filepath):
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
 

    def is_valid_file_extension(self, filepath):
        ''' Checks if the given filepath's filename has a proper movie clip extension ''' 
        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)
        
        if ext.lower().endswith(self.valid_extensions):
            return True


    def calculate_filepath(self, episode, filename, normalize = True):
        ''' Calculates the destination filepath of a given episode '''
        if self.settings["normalize_names"] and normalize:
            filename = self.get_normalized_filename(filename, episode)
        return os.path.join(self.settings["deployment_folder"], episode.series[0], "Season " + str(episode.descriptor[0]), filename)


    def move_file_to_folder_structure(self, episode, filepath, new_filename = None):
        ''' This method is responsible for moving the given file, specified via filepath, to the calculated destination.
            It is also possible to define a new filename with the help of the new_filename parameter.
        '''
        
        if new_filename is not None:
            filename = new_filename
        else:
            filename = os.path.basename(filepath)
        
        # Force normalization off
        destination = self.calculate_filepath(episode, filename, normalize = False)

        directory = os.path.dirname(destination)
        
        if not os.path.exists(directory):
            os.makedirs(directory) 
        
        # Copy / Move movie clip
        if self.settings["copy_associated_movieclips"]:                
            shutil.copyfile(filepath, destination)
        else:
            shutil.move(filepath, destination)

            
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

class MovieClip(object):
    def __init__(self, filepath, identifier = None, filesize = None, checksum = None, thumbnails = None):
        self.filepath = filepath
                    
        self.identifier = identifier 
        self.checksum = checksum
            
        if filesize is None:
            self.get_filesize()
        else:
            self.filesize = filesize
        
        if thumbnails is None:
            thumbnails = []    
        self.thumbnails = thumbnails
        
    def get_filename(self):
        return os.path.basename(self.filepath)    
    
    def get_thumbnails(self):
        """ This function gathers the thumbnails and adds them to the dedicated thumnails list"""
        pass

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



class NoConnectionAvailable(Exception):
    def __init__(self):
        pass

    
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

        counter = 1
        for seasonnumber in seasons.iterkeys():
            if type(seasonnumber) == type(1):
                for imdb_episode_number in seasons[seasonnumber]:  
                    imdb_episode = seasons[seasonnumber][imdb_episode_number]                       
                    episode = Episode(title = imdb_episode.get('title'), descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], series = (imdb_series.get('title'), {"imdb" : imdb_series.movieID}), date = imdb_episode.get('original air date'), plot = imdb_episode.get('plot'), identifier = {"imdb" : imdb_episode.movieID}, rating = {"imdb" : self.get_rating(ratings, imdb_episode)}, number = counter)
                    counter += 1
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
        from imdb import IMDbError 
        try: 
            output = []
            query = self.ia.search_movie(title)
            for movie in query:
                if movie.get('kind') == "tv series":
                    output.append(SeriesWidgetItem(movie, movie.get('smart long imdb canonical title')))
            return output
        except IMDbError:
            raise NoConnectionAvailable

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
                    log.debug("Error: Date " + imdbdate) 

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
        self.season = {}
    
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
        return []
        
    def get_identifier(self):
        return self.identifier.items()[0]

class Episode(object):
    def __init__(self, title = "", descriptor = None, series = "", date = None, plot = "", identifier = None, rating = None, director = "", runtime = "", genre = "", seen_it = False, number = 0):
        
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
        self.seen_it = seen_it
        self.number = number


    def __repr__(self):
        return "E(" + str(self.series[0]) + " - " + str(self.title) + " " + str(self.descriptor[0]) + "x" + str(self.descriptor[1]) +  " " + str(self.date) + ")"

    def __cmp__(self, other):
        try:
            other = other.date
        except (TypeError, AttributeError):
            pass
        return cmp(self.date, other)

    def __eq__(self, other):
        return self.title == other.title and self.descriptor == other.descriptor
    
    
    def get_series(self):
        for series in series_list:
            if series.identifier == self.series[1]:
                return series
    
    def get_descriptor(self):
        return str(self.descriptor[0]) + "x" + str('%0.2d' % self.descriptor[1])

    def get_alternative_descriptor(self):
        return "S" + str('%0.2d' % self.descriptor[0]) + "E" + str('%0.2d' % self.descriptor[1])

    
    def get_thumbnails(self):
        thumbnail_list = []
        for movieclip in self.get_movieclips():
            thumbnail_list += movieclip.thumbnails
        return thumbnail_list
    
    def get_movieclips(self):
        try:
            return movieclips[self.get_identifier()]
        except KeyError:
            return [] #return an empty list    
    
    def get_normalized_name(self):
        return self.series[0] + " " + self.get_descriptor() + " - " + self.title
    
    def get_alternative_name(self):
        return self.series[0] + " " + self.get_alternative_descriptor()
    
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
            self.dictionary = {"imdb" : {}} #TODO  
        else:
            self.dictionary = dictionary

    def __getitem__(self, identifier):
       
        implementation, key = identifier
        try:            
            return self.dictionary[implementation][key]
        except KeyError:
            log.debug("Key Error in Movieclip manager")
            
        return [] # Returns an empty list, to produce a empty iterator

    
    def get_episode_dict_with_matching_checksums(self, checksum):
        ''' This function searches for the given checksum in the internal data structures.
            It returns two lists as a tuple. The first beign a list of episodes. The second
            beign a list of movie clips which match the checksum.
        '''
        
        episode_dict = {} # episode are keys, movieclips are values
        
        for implementation in self.dictionary:
            for key in self.dictionary[implementation]:
                for movieclip in self.dictionary[implementation][key]:
                    if movieclip.checksum == checksum:
                        episode_dict[self.from_movieclip_to_episode(movieclip)] = movieclip 
                       
        return episode_dict
    
    
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

    settings = load_settings()
    series_list = load_series()
    movieclips = load_movieclips()    

    mainwindow = MainWindow()
    mainwindow.show()
    
    app.exec_()