# -*- coding: utf-8 -*-

import hashlib
import glob
import uuid
import urllib2
import functools
import os
import json
import diribeomessageboxes
import collections

from diribeomodel import settings, movieclips, series_list, MovieClip, NoInternetConnectionAvailable, DownloadError, MovieClipAssociation, PlacementPolicy
from diribeowrapper import library
from operator import itemgetter
from pyffmpegwrapper.video_inspector import VideoInspector
from pyffmpegwrapper.video_encoder import VideoEncoder
from pyffmpegwrapper.errors import FFMpegException

from PyQt4 import QtCore

HOMEPAGE_URL = "http://www.diribeo.de"

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

def dameraulevenshtein(seq1, seq2):
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
    
    def __init__(self, filepath_dir_list, series, pool):
        WorkerThread.__init__(self)
        self.filepath_dir_list = filepath_dir_list
        self.series = series
        self.pool = pool

        hint = ""
        if self.series is not None:
            hint = " Hint: " + series.title
            
        self.description = "Assigning multiple clips " + hint
    
    def create_episode_list(self, series, filename):                
        episode_list = []
        if self.series is None:        
            for series in series_list:
                for episode in series.episodes:
                    episode.filename = filename
                    episode_list.append(episode)
        else:
            for episode in self.series:
                episode.filename = filename
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
            self.progress.emit(index, filepath_list_length)
            
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
                    episode_list = self.create_episode_list(self.series, filename)
                    
                    result = self.pool.map_async(generate_episode_score_list, episode_list)
                    episode_score_list = result.get(timeout=100)
                    
                    episode_score_list.sort(key=itemgetter(1))
                    total_score = sum([score for episode, score in episode_score_list])
                    counter = len(episode_score_list)
                    
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



def generate_episode_score_list(episode):
    score = min([dameraulevenshtein(title, episode.filename) for title in episode.get_alternative_titles() + [episode.get_normalized_name()]])
    return [episode, score]


class ThumbnailGatherer(WorkerThread):

    def __init__(self, pixmap_cache):
        WorkerThread.__init__(self)
        self.pixmap_cache = pixmap_cache
        self.description = "Loading Pixmaps"

    def run(self):
        for movieclip in movieclips:
            for filepath, timecode in movieclip.thumbnails:
                    self.pixmap_cache.get_pixmap(filepath)
        self.finished.emit()


class VersionChecker(WorkerThread):
    finished = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, reference_version):
        WorkerThread.__init__(self)
        self.description = "Checking for updates"
        self.reference_version = reference_version
        
    def run(self):
        self.waiting.emit()
        try:
            content = urllib2.urlopen(HOMEPAGE_URL+"/tasks/currentversion_v1").read()
            version = tuple(json.loads(content)["version"])
            self.finished.emit(version)
        except urllib2.URLError:
            self.finished.emit("ERROR")

class MultipleMovieClipAssociator(AssignerThread):
    ''' This class is responsible for associating a movie clip with a given episode.
        It emits various signals which can be used for feedback.
    '''
    finished = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    generate_thumbnails = QtCore.pyqtSignal("PyQt_PyObject", "PyQt_PyObject")
    
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
                        
                    movieclip_association.movieclip = MovieClip(filepath, checksum=checksum)
                movieclip_association.movieclip.identifier = episode.identifier
                
                if not os.path.isfile(filepath) or not settings.is_valid_file_extension(filepath):
                    self.filesystem_error.emit(filepath)
                elif settings.get("hash_movieclips") and not movieclips.check_unique(movieclip_association.movieclip, episode.get_identifier()):
                    self.already_exists_in_another.emit()
                else:
                    self.assign(movieclip_association)
                    self.generate_thumbnails.emit(episode, movieclip_association.movieclip)
                    
        self.finished.emit(episode, movieclip_association.movieclip)
    
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
        
        
        if move_to_folder and (movieclip_association.placement_policy != PlacementPolicy.DONT_TOUCH):
            # Check if there is already a file with the same name, normalizes file name if set to do so
            filename = settings.get_unique_filename(destination, episode)
            
            # Move the file to the actual folder
            copy_move = "Moving"
            if settings.get("placement_policy") == PlacementPolicy.COPY:
                copy_move = "Copying"
            self.additional_descriptions["moving"] = "%s movie clip to destination" % copy_move
            settings.move_file_to_folder_structure(episode, movieclip_association.filepath, movieclip_association.placement_policy, new_filename=filename)
            self.additional_descriptions["moving"] = ""
            
            
            # Set the old file path to the current one
            movieclip_association.movieclip.old_filepath = movieclip_association.movieclip.filepath
            
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
        self.timecode = []  
        self.description = "Generating thumbnails"       
        self.number_of_thumbnails = settings.get("number_of_thumbnails")  


    def run(self):
        self.waiting.emit()
        
        # Delete the already generated thumbnails of the movieclip
        self.movieclip.delete_thumbnails()

        try:
            video = VideoInspector(self.filepath)
            duration = video.duration()
            self.movieclip.duration = duration
            self.movieclip.dimensions = video.dimension()
        except (AttributeError, OSError, FFMpegException) as error:
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
        video_encoder = VideoEncoder(self.filepath)
        
        for index in range(1, self.number_of_thumbnails+1):
            time = index*interval
            self.timecode.append(time)
            destination = os.path.join(settings.get_thumbnail_folder(), unique_identifier + "-%03d" % index + ".png")
            video_encoder.execute(
                '%(ffmpeg_bin)s -ss '+ str(time) +' -y -i "%(input_file)s" -vframes 1 -vcodec png -f image2 "%(output_file)s"',
                destination,
            )
            self.progress.emit(index, self.number_of_thumbnails)  
                  
        self.collect_images()
        
        if len(self.image_list) > 0:
            self.movieclip.thumbnails = zip(self.image_list, self.timecode)            
            self.thumbnails_created.emit(self.episode)
        else:
            self.error_in_thumbnail_creation.emit()
        
        self.finished.emit()
    
    def collect_images(self):
        filelist = glob.glob(self.prefix + "*.png")
        for file in filelist:
            if os.path.exists(file):
                self.image_list.append(file)
        


class MovieUpdater(WorkerThread):
    download_error = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, movie):
        WorkerThread.__init__(self)
        self.movie = movie
        self.description = "Updating movie"
        
    def run(self):
        self.waiting.emit()
        try:
            library.update_movie(self.movie)
        except DownloadError:
            self.download_error.emit(self.movie)
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
            result = library.search_movie(self.searchfield.text(), settings.settings["sources"])
            if result:
                self.results.emit(result)
            else:                
                self.nothing_found.emit()
        except NoInternetConnectionAvailable:
            self.no_connection_available.emit()
        
        self.finished.emit()

class ModelFiller(WorkerThread):
    
    # Initialize various signals.
    insert_into_tree = QtCore.pyqtSignal("PyQt_PyObject")
    download_error = QtCore.pyqtSignal("PyQt_PyObject")
    update_tree = QtCore.pyqtSignal("PyQt_PyObject")
    update_tableview = QtCore.pyqtSignal("PyQt_PyObject")
    update_seriesinformation = QtCore.pyqtSignal("PyQt_PyObject")
    
    def __init__(self, model, movie):
        WorkerThread.__init__(self)
        self.movie = movie
        self.model = model
        self.series = self.model.series
        self.model.generator = library.get_episodes(movie, self.series.identifier.keys()[0])
        self.description = "Downloading Series"

    def run(self): 
                    
        episode_counter = 0

        # Make the progress bar idle
        self.waiting.emit()     
        self.insert_into_tree.emit(self.series)  
        self.update_seriesinformation.emit(self.series)   
        library.get_more_information(self.series, self.movie, self.series.identifier.keys()[0])
        self.update_seriesinformation.emit(self.series)  
        
        try:    
            for episode, episodenumber in self.model.generator:
                self.model.insert_episode(episode)            
                episode_counter += 1
                if episode_counter % 8 == 0:
                    self.progress.emit(episode_counter, episodenumber)        
        except DownloadError:
            self.download_error.emit(self.series)
        
        self.model.filled = True          
        self.finished.emit()
        self.update_tree.emit(self.series)
        self.update_tableview.emit(self.model)
        
        