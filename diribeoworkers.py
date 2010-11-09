# -*- coding: utf-8 -*-

import hashlib
import shlex
import glob
import uuid
import functools
import os
import subprocess
import re
import diribeomessageboxes
import collections

from diribeomodel import settings, movieclips, series_list, MovieClip, NoInternetConnectionAvailable, MovieClipAssociation
from diribeowrapper import library
from operator import itemgetter
from PyQt4 import QtCore


class WorkerThread(QtCore.QThread):
    
    # Define various signals        
    waiting = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    
    def __init__(self):
        QtCore.QThread.__init__(self)
        # Additional thread information
        self.description = "" # The description which is shown in the statusbar
        self.additional_descriptions = collections.defaultdict(lambda : str()) 


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
    
    
    def calculate_checksum(self, filepath):
        self.filesize = os.path.getsize(filepath)
    
        # For debugging purposes
        def print_progress(byte_count, filesize):
            print '\r%d/%d %6.2f' % (byte_count,
                                 filesize,
                                 100.0 * byte_count / filesize),
    
        with open(filepath, "rb") as iso_file:
            checksum = self.hash_file(iso_file, hashlib.sha224(), self.progress.emit)
            return checksum

    def dameraulevenshtein(self, seq1, seq2):
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


class AssignerThread(WorkerThread):
    no_association_found = QtCore.pyqtSignal()
    already_exists = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject") # This signal is emitted when the movieclip is already in the dict and in the folder
    association_found = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    filesystem_error = QtCore.pyqtSignal("PyQt_PyObject")
    already_exists_in_another = QtCore.pyqtSignal() # Emitted when movieclip is in _another_ episode
    load_information = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self):
        WorkerThread.__init__(self)


class MultipleAssignerThread(WorkerThread):
    
    result = QtCore.pyqtSignal("PyQt_PyObject")
    
    
    def __init__(self, filepath_dir_list, series):
        WorkerThread.__init__(self)
        self.filepath_dir_list = filepath_dir_list
        self.series = series

        hint = ""
        if self.series is not None:
            hint = " Hint: " + series.title
            
        self.description = "Assigning multiple clips " + hint
    
    def create_episode_list(self, series):
                
        episode_list = []
        if self.series is None:        
            for series in series_list:
                for episode in series.episodes:
                    episode_list.append(episode)
        else:
            for episode in self.series:
                episode_list.append(episode)
        
        return episode_list
    
    
    def create_filepath_list(self, filepath_dir_list):
        filepath_list = []
        
        for single_file_or_dir in filepath_dir_list:
            if os.path.isdir(str(single_file_or_dir)):
                        for root, dirs, files in os.walk(str(single_file_or_dir)):
                            for single_file in files:
                                    filepath_list.append(os.path.join(root,single_file))
            else:
                filepath_list.append(str(single_file_or_dir))
        
        return filepath_list
    
    
    def run(self):
        
        self.waiting.emit()
        
        self.filepath_list = self.create_filepath_list(self.filepath_dir_list)
        
        ''' Algorithm description:
        
            for each file do:
                a) see if file is valid:
            
                b) generate hash of file and look if an association exists, remember result
                
                c) if no association exists, generate levenshtein, remember result
            
            emit result into appropiate editor
        
        '''
        
        movieclip_associations = []
        
        filepath_list_length = len(self.filepath_list)
        for index, filepath in enumerate(self.filepath_list):
            
            movieclip_association = MovieClipAssociation(filepath)
            movieclip_associations.append(movieclip_association)
        
            self.additional_descriptions["progress"] = "%s from %s" % (index+1, filepath_list_length)
            filename, ext = os.path.splitext(os.path.basename(filepath))
            
            if not os.path.isfile(filepath) or not settings.is_valid_file_extension(filepath):
                # a)
                movieclip_association.message = movieclip_association.INVALID_FILE
                movieclip_association.skip = True
            else:
                # b)
                checksum = None
                if settings.get("hash_movieclips"):
                    self.additional_descriptions["hash"] = "Calculating hash"
                    checksum = self.calculate_checksum(filepath)
                    self.additional_descriptions["hash"] = ""
                    
                movieclip = MovieClip(filepath, checksum = checksum)
                
                if settings.get("hash_movieclips"):        
                    episode_dict = movieclips.get_episode_dict_with_matching_checksums(movieclip.checksum)
                
                if not (not settings.get("hash_movieclips") or len(episode_dict.items()) == 0 or episode_dict.items()[0][0] is None):
                    episode = episode_dict.items()[0][0]                        
                    found_movieclip = episode_dict.items()[0][1]
                    movieclip_association.episode_scores_list = [(episode, 0)]
                    movieclip_association.movieclip = found_movieclip
                    movieclip_association.message = movieclip_association.ASSOCIATION_FOUND
                else:
                    # c)
                    self.additional_descriptions["guess"] = "Guessing episode"
                    episode_list = self.create_episode_list(self.series)
                    
                    episode_list_length = len(episode_list)
                    counter = 0
                    total_score = 0
                    episode_score_list = []
                    import multiprocessing
                    p = multiprocessing.Pool()
                    #result = p.map(lambda x: x**2, range(20))
                    #print result
                    for episode in episode_list:
                        score = min([self.dameraulevenshtein(title, filename) for title in episode.get_alternative_titles() + [episode.get_normalized_name()]])
                        episode_score_list.append([episode, score])
                        self.progress.emit(counter, episode_list_length)
                        total_score += score 
                        counter += 1
                    
                    episode_score_list.sort(key = itemgetter(1))
                    
                    movieclip_association.movieclip = movieclip
                    movieclip_association.episode_scores_list = episode_score_list
                    movieclip_association.message = movieclip_association.ASSOCIATION_GUESSED
                    movieclip_association.episode_score_information["mean"] = float(total_score) / float(counter)
                    movieclip_association.episode_score_information["median"] = self.get_median([score for episode, score in episode_score_list])
                    self.additional_descriptions["guess"] = ""
        
        self.result.emit(movieclip_associations)
        self.finished.emit()


    def get_median(self, values):
        ''' Calculates the median of a sorted list of numbers
        '''
        count = len(values)
        if count % 2 == 1:
            return values[(count+1)/2-1]
        else:
            lower = values[count/2-1]
            upper = values[count/2]
            return (float(lower + upper)) / 2


class MultipleMovieClipAssociator(AssignerThread):
    ''' This class is responsible for associating a movie clip with a given episode.
        It emits various signals which can be used for feedback.
    '''
    
    def __init__(self, movieclip_associations):
        AssignerThread.__init__(self)
        self.movieclip_associations = movieclip_associations
        self.description = "Assigning movieclip to a given episode" 

    def run(self):
        self.waiting.emit()
        
        movieclip_associations_length = len(self.movieclip_associations)
        
        
        for index, movieclip_association in enumerate(self.movieclip_associations):
            assert not movieclip_association.skip
            
            filepath = movieclip_association.filepath
            
            if os.path.isdir(filepath):
                self.filesystem_error.emit(filepath)
            else:            
                self.additional_descriptions["progress"] = "%s from %s" % (index+1, movieclip_associations_length)
                
                episode = movieclip_association.get_associated_episode_score()[0]
                
                if movieclip_association.movieclip is None:
                    checksum = None
                    if settings.get("hash_movieclips"):
                        self.additional_descriptions["hash"] = "Calculating hash"
                        checksum = self.calculate_checksum(filepath)
                        self.additional_descriptions["hash"] = ""
                        
                    movieclip_association.movieclip = MovieClip(filepath, checksum = checksum)
                movieclip_association.movieclip.identifier = episode.identifier
                
                if not os.path.isfile(filepath) or not settings.is_valid_file_extension(filepath):
                    self.filesystem_error.emit(filepath)
                elif settings.get("hash_movieclips") and not movieclips.check_unique(movieclip_association.movieclip, episode.get_identifier()):
                    self.already_exists_in_another.emit()
                else:
                    self.assign(movieclip_association)
        
        self.finished.emit()
    
    def assign(self, movieclip_association):
        """ Here is a list of possibilities that might occur:
                a) The clip is already in the movieclip dict and in its designated folder
                b) The clip is already in the movieclip dict, but not in its designated folder
                c) The clip is not in the movieclip dict but already in the folder
                d) The clip is not in the movieclip dict and not in the folder
        """
        
        filename = os.path.basename(movieclip_association.filepath)
        episode, score = movieclip_association.get_associated_episode_score()
        
        # Calculate hypothetical filepath
        destination = settings.calculate_filepath(episode, filename)
        directory = os.path.dirname(destination)
        
        if movieclip_association.movieclip in movieclips[episode.get_identifier()]:
            
            if os.path.isfile(destination):
                # a)
                self.already_exists.emit(episode, movieclip_association.filepath)
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
            filename = settings.get_unique_filename(destination, episode)
            
            # Move the file to the actual folder
            self.additional_descriptions["moving"] = "Moving/Copying movieclip to destination"
            settings.move_file_to_folder_structure(episode, movieclip_association.filepath, new_filename = filename)
            self.additional_descriptions["moving"] = ""
            
            # Update the filepath of the clip        
            movieclip_association.movieclip.filepath = os.path.join(directory, filename)
    
        if add_to_movieclips:
            # Add the clips to the movie clips manager
            movieclips.add(movieclip_association.movieclip)                  
                    
        self.load_information.emit(episode)


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
        self.number_of_thumbnails = settings.get("number_of_thumbnails")  


    def get_duration_from_ffprobe_output(self, text):
        print text
        matching = re.search(r'([0-9][0-9]):([0-9][0-9]):([0-9][0-9]).([0-9][0-9])', text)  
        return int(matching.group(1))*60*60 + int(matching.group(2))*60 + int(matching.group(3))


    def run(self):
        self.waiting.emit()
        
        
        # Delete the already generated thumbnails of the movieclip
        self.movieclip.delete_thumbnails()
        
        
        # Get length of video clip
        length_command = 'ffmpeg -i "' + self.filepath + '"'
        length_command_args = shlex.split(str(length_command))
        try:       
            length_process = subprocess.Popen(length_command_args, stderr=subprocess.PIPE, stdout=subprocess.PIPE).communicate()
            duration = self.get_duration_from_ffprobe_output(length_process[1])
        except (AttributeError, OSError) as e:
            self.error_in_thumbnail_creation.emit()
            self.finished.emit()
            return
        
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
        


class MovieUpdater(WorkerThread):
    def __init__(self, movie):
        WorkerThread.__init__(self)
        self.movie = movie
        self.description =  "Updating movie"
        
    def run(self):
        self.waiting.emit()
        
        library.update_movie(self.movie)
        
        self.finished.emit()
    


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
            result = library.search_movie(self.searchfield.text())
            if len(result) == 0:
                self.nothing_found.emit()
            else:                
                self.results.emit(result)
        except NoInternetConnectionAvailable:
            self.no_connection_available.emit()
        
        self.finished.emit()

class ModelFiller(WorkerThread):
    
    # Initialize various signals.
    insert_into_tree = QtCore.pyqtSignal("PyQt_PyObject")
    update_tree = QtCore.pyqtSignal("PyQt_PyObject")
    update_tableview = QtCore.pyqtSignal("PyQt_PyObject")
    update_seriesinformation = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, model, movie):
        WorkerThread.__init__(self)
        self.movie = movie
        self.model = model
        self.series = self.model.series
        self.model.generator = library.get_episodes(movie, self.series.identifier.keys()[0])
        self.description = "Filling a model"

    def run(self): 
                    
        episode_counter = 0

        # Make the progress bar idle
        self.insert_into_tree.emit(self.series)  
        self.waiting.emit()     
        self.update_seriesinformation.emit(self.series)   
        library.get_more_information(self.series, self.movie, self.series.identifier.keys()[0])
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