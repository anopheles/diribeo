# -*- coding: utf-8 -*-
'''
Created on 05.07.2010

@author: anopheles
'''

import hashlib
import shlex
import glob
import uuid
import functools
import os
import subprocess
import re
import diribeomessageboxes

from diribeomodel import settings, movieclips, series_list, MovieClip, NoConnectionAvailable, imdbwrapper
from operator import itemgetter
from PyQt4 import QtCore

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


class MovieClipGuesser(WorkerThread):
    ''' This class searches for a match in all given episodes. It returns
        a list of possible episodes from which the user can choose one.
        It heavily uses the damerau�levenshtein distance
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
        self.filepath = os.path.normpath(movieclip.filepath)
        self.movieclip = movieclip 
        self.episode = episode
        self.image_list = []    
        self.description = "Generating thumbnails"       
        self.number_of_thumbnails = 18    


    def get_duration_from_ffprobe_output(self, text):
        matching = re.search(r'([0-9][0-9]):([0-9][0-9]):([0-9][0-9]).([0-9][0-9])', text)  
        print text    
        return int(matching.group(1))*60*60 + int(matching.group(2))*60 + int(matching.group(3))


    def run(self):
        self.waiting.emit()
        
        # Get length of video clip
        length_command = 'ffmpeg -i "' + self.filepath + '"'
        length_command_args = shlex.split(str(length_command))
        length_process = subprocess.Popen(length_command_args, stderr=subprocess.PIPE, stdout=subprocess.PIPE).communicate()       
        duration = self.get_duration_from_ffprobe_output(length_process[1])
        print duration
        
        #ffmpeg -i foo.avi -r 1 -s WxH -f image2 foo-%03d.jpeg
        #http://www.ffmpeg.org/ffmpeg-doc.html
        #i = filename, r = framerate, s = size, f = force format, t=duration in s
        #http://debuggable.com/posts/FFMPEG_multiple_thumbnails:4aded79c-6744-4bc1-b30e-59bccbdd56cb
        
        interval = duration/self.number_of_thumbnails
        unique_identifier = str(uuid.uuid4())
        self.prefix = os.path.join(settings.get_thumbnail_folder(), unique_identifier)
        
        for index in range(1, self.number_of_thumbnails+1):
            destination = os.path.join(settings.get_thumbnail_folder(), unique_identifier + "-" + "%03d" % index + ".png") 
            command = 'ffmpeg -ss ' + str(index*interval) + ' -i "'+ self.filepath + '" -vframes 1 -vcodec png -f image2 "' + destination + '"'           
            args = shlex.split(str(command)) # does not support unicode input
            proc = subprocess.Popen(args, shell = True, stdout=subprocess.PIPE)
            proc.wait()
            self.progress.emit(index, self.number_of_thumbnails)  
                  
        self.collect_images()
        
        if len(self.image_list) > 0:
            self.movieclip.thumbnails = self.image_list
            self.thumbnails_created.emit(self.episode)
        else:
            self.error_in_thumbnail_creation.emit()
        
        self.finished.emit()
    
    def collect_images(self):
        filelist = glob.glob(self.prefix + "*.png")
        for file in filelist:
            self.image_list.append(file)
        

class SeriesSearchWorker(WorkerThread):
    no_connection_available = QtCore.pyqtSignal() # Is emitted whenever there is no active internet connection available
    nothing_found = QtCore.pyqtSignal()
    results = QtCore.pyqtSignal("PyQt_PyObject")
   
    def __init__(self, searchfield):
        WorkerThread.__init__(self)
        self.searchfield = searchfield
        self.no_connection_available.connect(diribeomessageboxes.no_internet_connection_warning)
        self.description = "Searching for Series"

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